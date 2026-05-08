import numpy as np
import pandas as pd
import pytest

from src import risk_metrics as rm


def _series(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def test_sharpe_returns_nan_on_zero_volatility():
    constant_returns = _series([0.001] * 30)
    assert pd.isna(rm.sharpe_ratio(constant_returns, rf_annual=0.0))


def test_sharpe_positive_for_positive_excess():
    np.random.seed(7)
    daily = np.random.normal(loc=0.0008, scale=0.005, size=252)
    s = rm.sharpe_ratio(_series(daily), rf_annual=0.05)
    assert s == pytest.approx(s, abs=1e-9)
    assert s > 0


def test_sortino_only_penalises_downside():
    # Same magnitude excess but skewed downside vs upside
    upside = _series([0.01] * 100)
    downside = _series([-0.01] * 100)
    assert rm.sortino_ratio(upside, rf_annual=0.0) > 0
    assert rm.sortino_ratio(downside, rf_annual=0.0) < 0


def test_max_drawdown_simple():
    s = _series([100, 110, 121, 90, 95, 130])
    out = rm.max_drawdown(s)
    # peak 121 -> trough 90 = -25.62%
    assert out["mdd"] == pytest.approx(-0.256198, abs=1e-4)


def test_correlation_diversification_warns_on_lockstep():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, size=100)
    prices = pd.DataFrame({
        "AAA": (1 + pd.Series(base, index=idx)).cumprod(),
        "BBB": (1 + pd.Series(base + rng.normal(0, 0.0001, 100), index=idx)).cumprod(),
        "CCC": (1 + pd.Series(rng.normal(0, 0.01, 100), index=idx)).cumprod(),
    })
    corr = rm.correlation_matrix(prices, ["AAA", "BBB", "CCC"])
    info = rm.diversification_score(corr)
    assert any("AAA" in w["pair"] and "BBB" in w["pair"] for w in info["warnings"])
    assert info["score"] < 100


def test_net_of_tax_only_taxes_gains():
    assert rm.net_of_tax_return(0.0, "Tahvil (TL)") == 0.0
    assert rm.net_of_tax_return(-0.1, "Tahvil (TL)") == -0.1  # losses untaxed
    assert rm.net_of_tax_return(0.20, "PPF (TL)") == pytest.approx(0.20)  # 0% PPF
    assert rm.net_of_tax_return(0.20, "Döviz") == pytest.approx(0.17, rel=1e-9)


def test_real_return_below_nominal_under_high_inflation():
    idx = pd.date_range("2024-01-01", periods=12, freq="M")
    nominal = pd.Series([100, 102, 105, 108, 112, 115, 118, 122, 125, 130, 135, 140], index=idx)
    cpi = pd.Series([100, 105, 110, 115, 121, 127, 134, 141, 148, 155, 163, 171], index=idx)
    real = rm.real_return_series(nominal, cpi)
    assert real.iloc[-1] < nominal.iloc[-1]


def test_category_zscore_flags_extreme_inflow():
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    rng = np.random.default_rng(0)
    cats = []
    for d in dates[:-1]:
        cats.append({"tarih": d, "ana_kategori": "Hisse (TL)",
                     "net_giris_tl": rng.normal(0, 1_000_000)})
    # Final day: massive 5-sigma outlier inflow
    cats.append({"tarih": dates[-1], "ana_kategori": "Hisse (TL)",
                 "net_giris_tl": 50_000_000})
    out = rm.category_flow_zscore(pd.DataFrame(cats), window=60)
    row = out[out["category"] == "Hisse (TL)"].iloc[0]
    assert row["signal"] == "crowded_long"
    assert row["z_score"] > 2.0
