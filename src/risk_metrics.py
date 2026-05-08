"""Risk and return analytics for ArkaFon portfolios and funds.

All inputs are pandas objects pulled from the master parquet. Functions are
pure: no I/O, no streamlit, no FastAPI dependencies. The api layer is
responsible for assembling DataFrames and serialising the response.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

# Trading days per year for annualisation. TEFAS publishes daily NAVs on
# business days, so 252 is the conventional choice.
TRADING_DAYS = 252

# Default risk-free rate (Turkish overnight repo, gross annualised). Callers
# can override via API query string.
DEFAULT_RF_ANNUAL = 0.45

# Threshold for treating a standard deviation as effectively zero. Pandas'
# .std() on an identical-value series leaks ~1e-19 of float-accumulation
# noise on some platforms, so a strict `== 0` check would miss it.
_STD_EPS = 1e-12

# Stopaj (withholding tax) lookup. SPK categorises funds by underlying assets;
# this map mirrors the rules in force from 2024 onwards. Anything not listed
# falls back to 10% which is the generic TEFAS rate.
STOPAJ_BY_CATEGORY: Dict[str, float] = {
    "PPF (TL)": 0.0,
    "Tahvil (TL)": 0.10,
    "Hisse (TL)": 0.0,
    "Karma Fon": 0.10,
    "Değişken Fon": 0.10,
    "Serbest Fon": 0.10,
    "Katılım Fonu": 0.10,
    "Fon Sepeti": 0.10,
    "Döviz": 0.15,
    "Diğer": 0.10,
}


def _pivot_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Long master-frame -> wide price matrix indexed by date."""
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index="tarih", columns="FONKODU", values="FIYAT")
    return pivot.sort_index().ffill().dropna(how="all", axis=1)


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns. Drops the first NaN row."""
    return prices.pct_change().dropna(how="all")


# -- 1. Sharpe / Sortino --------------------------------------------------

def sharpe_ratio(returns: pd.Series, rf_annual: float = DEFAULT_RF_ANNUAL) -> float:
    """Annualised Sharpe. Returns NaN when std is effectively zero."""
    r = returns.dropna()
    if r.empty:
        return float("nan")
    rf_daily = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = r - rf_daily
    sigma = float(excess.std(ddof=1))
    if pd.isna(sigma) or abs(sigma) < _STD_EPS:
        return float("nan")
    return float(excess.mean() / sigma * math.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, rf_annual: float = DEFAULT_RF_ANNUAL) -> float:
    """Like Sharpe but only penalises downside volatility.

    When there is no downside at all (every excess return >= 0) the ratio is
    mathematically undefined; we follow the common convention of returning
    +inf for positive mean excess and -inf for negative, NaN otherwise.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    rf_daily = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = r - rf_daily
    downside = excess.where(excess < 0, 0.0)
    dd_sigma = math.sqrt(float((downside ** 2).mean()))
    if pd.isna(dd_sigma) or abs(dd_sigma) < _STD_EPS:
        mean_excess = float(excess.mean())
        if mean_excess > 0:
            return float("inf")
        if mean_excess < 0:
            return float("-inf")
        return float("nan")
    return float(excess.mean() / dd_sigma * math.sqrt(TRADING_DAYS))


def portfolio_returns(prices: pd.DataFrame, codes: Iterable[str], weights: Optional[Dict[str, float]] = None) -> pd.Series:
    """Weighted daily returns for a basket. Equal-weight if weights omitted."""
    cols = [c for c in codes if c in prices.columns]
    if not cols:
        return pd.Series(dtype=float)
    rets = prices[cols].pct_change().dropna(how="all")
    if weights:
        w = pd.Series({c: float(weights.get(c, 0.0)) for c in cols})
        if w.sum() == 0:
            w = pd.Series(1.0 / len(cols), index=cols)
        else:
            w = w / w.sum()
    else:
        w = pd.Series(1.0 / len(cols), index=cols)
    return (rets[cols] * w).sum(axis=1)


# -- 2. Inflation-adjusted (real) returns ---------------------------------

def real_return_series(nominal_index: pd.Series, cpi: pd.Series) -> pd.Series:
    """Deflate a Base-100 nominal index by CPI to give real (purchasing-power) index.

    Both inputs must be indexed by date. CPI is forward-filled to daily.
    """
    if nominal_index.empty or cpi.empty:
        return pd.Series(dtype=float)
    cpi_daily = cpi.reindex(nominal_index.index).ffill().bfill()
    base_cpi = cpi_daily.iloc[0]
    if not base_cpi or pd.isna(base_cpi):
        return pd.Series(dtype=float)
    real = nominal_index * (base_cpi / cpi_daily)
    return real


# -- 3. Maximum Drawdown --------------------------------------------------

def max_drawdown(price_or_index: pd.Series) -> Dict[str, object]:
    """Largest peak-to-trough decline. Returns the magnitude plus dates."""
    s = price_or_index.dropna()
    if s.empty:
        return {"mdd": 0.0, "peak_date": None, "trough_date": None}
    running_peak = s.cummax()
    drawdown = (s - running_peak) / running_peak
    trough_idx = drawdown.idxmin()
    peak_idx = s.loc[:trough_idx].idxmax()
    return {
        "mdd": float(drawdown.min()),
        "peak_date": peak_idx.strftime("%Y-%m-%d") if peak_idx is not None else None,
        "trough_date": trough_idx.strftime("%Y-%m-%d") if trough_idx is not None else None,
    }


# -- 4. Correlation & diversification -------------------------------------

def correlation_matrix(prices: pd.DataFrame, codes: Iterable[str]) -> pd.DataFrame:
    cols = [c for c in codes if c in prices.columns]
    if len(cols) < 2:
        return pd.DataFrame()
    return prices[cols].pct_change().dropna(how="any").corr()


def diversification_score(corr: pd.DataFrame) -> Dict[str, object]:
    """0-100 score; lower average pairwise corr -> higher diversification."""
    if corr.empty or corr.shape[0] < 2:
        return {"score": 100.0, "avg_correlation": 0.0, "warnings": []}
    n = corr.shape[0]
    iu = np.triu_indices(n, k=1)
    pairwise = corr.values[iu]
    avg = float(np.nanmean(pairwise)) if pairwise.size else 0.0
    # Map [-1, 1] avg correlation to 0-100. avg=0 -> 100, avg=1 -> 0.
    score = max(0.0, min(100.0, (1.0 - avg) * 50.0 + 50.0))
    warnings: List[Dict[str, object]] = []
    codes = list(corr.columns)
    for i, j in zip(*iu):
        c = float(corr.iat[i, j])
        if c >= 0.9:
            warnings.append({
                "pair": [codes[i], codes[j]],
                "correlation": round(c, 3),
                "message": "Bu iki fon neredeyse birebir aynı yönde hareket ediyor.",
            })
    return {"score": round(score, 1), "avg_correlation": round(avg, 3), "warnings": warnings}


# -- 5. Tax (Stopaj) ------------------------------------------------------

def stopaj_rate(category: Optional[str]) -> float:
    if not category:
        return 0.10
    return STOPAJ_BY_CATEGORY.get(category, 0.10)


def net_of_tax_return(gross_return: float, category: Optional[str]) -> float:
    """Apply withholding tax only to the *gain* component."""
    if gross_return is None or math.isnan(gross_return):
        return float("nan")
    rate = stopaj_rate(category)
    if gross_return <= 0:
        return gross_return  # no tax on losses
    return gross_return * (1.0 - rate)


# -- 6. Flow sentiment / crowded trade ------------------------------------

def category_flow_zscore(flows: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Compute rolling z-score of net inflow per category.

    Input columns: tarih, ana_kategori, net_giris_tl.
    Output: most recent z-score per category, plus percentile ranking.
    """
    if flows.empty:
        return pd.DataFrame(columns=["category", "latest_inflow", "z_score", "percentile", "signal"])
    pivot = flows.pivot_table(index="tarih", columns="ana_kategori",
                              values="net_giris_tl", aggfunc="sum").fillna(0.0).sort_index()
    rolling_mean = pivot.rolling(window=window, min_periods=10).mean()
    rolling_std = pivot.rolling(window=window, min_periods=10).std(ddof=1)
    z = (pivot - rolling_mean) / rolling_std.replace(0.0, np.nan)
    out = []
    latest_date = pivot.index.max()
    for cat in pivot.columns:
        series = pivot[cat]
        z_latest = z[cat].iloc[-1] if cat in z.columns and not z[cat].dropna().empty else np.nan
        rank = series.rank(pct=True).iloc[-1] if not series.empty else np.nan
        if pd.isna(z_latest):
            signal = "neutral"
        elif z_latest > 2.0:
            signal = "crowded_long"
        elif z_latest < -2.0:
            signal = "crowded_short"
        elif z_latest > 1.0:
            signal = "hot"
        elif z_latest < -1.0:
            signal = "cold"
        else:
            signal = "neutral"
        out.append({
            "category": cat,
            "latest_inflow": float(series.loc[latest_date]) if latest_date in series.index else 0.0,
            "z_score": None if pd.isna(z_latest) else round(float(z_latest), 2),
            "percentile": None if pd.isna(rank) else round(float(rank) * 100, 1),
            "signal": signal,
        })
    return pd.DataFrame(out).sort_values("z_score", ascending=False, na_position="last")
