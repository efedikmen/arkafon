"""
market_data.py — Currency marker ingest for the Jamstack pipeline.

Fetches USD/TRY spot and gold (XAU/USD spot, troy ounce) from Yahoo Finance
and persists them to ``data/processed/market_data.parquet`` with three
columns: ``tarih`` (date, normalized), ``usd_try`` (float), ``gold_usd``
(float).

The file is written idempotently: every run merges the current parquet
(if any) with freshly fetched rows, drops duplicate dates (keeping the
latest fetch), and re-writes the full file. This makes the script safe
to re-run on backfill days without losing prior history.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

from src.config import PROCESSED_DATA_DIR

MARKET_DATA_PATH = os.path.join(PROCESSED_DATA_DIR, "market_data.parquet")

USD_TRY_TICKER = "TRY=X"   # USD priced in TRY (i.e. how many TRY per 1 USD)
GOLD_TICKER = "GC=F"        # COMEX gold front-month futures, USD per troy ounce


def _yf_history(ticker: str, period: str) -> pd.DataFrame:
    """Thin wrapper around yfinance.Ticker(...).history with a clear error."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError(
            "yfinance is required for market_data.py. Install it with "
            "`pip install yfinance`."
        ) from e

    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned no rows for {ticker} ({period}).")
    return df


def _series_from_history(df: pd.DataFrame, col: str = "Close") -> pd.Series:
    s = df[col].copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s.groupby(s.index).last()
    return s.astype(float)


def fetch_markers(period: str = "5y") -> pd.DataFrame:
    """Fetch the full USD/TRY + gold history over the given lookback."""
    usd = _series_from_history(_yf_history(USD_TRY_TICKER, period))
    gold = _series_from_history(_yf_history(GOLD_TICKER, period))

    frame = pd.concat(
        [usd.rename("usd_try"), gold.rename("gold_usd")], axis=1
    ).dropna(how="all")
    frame = frame.ffill().dropna()
    frame.index.name = "tarih"
    return frame.reset_index()


def merge_and_write(fresh: pd.DataFrame, out_path: str = MARKET_DATA_PATH) -> pd.DataFrame:
    """Merge a freshly fetched frame with the on-disk parquet and persist."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if os.path.exists(out_path):
        existing = pd.read_parquet(out_path)
        existing["tarih"] = pd.to_datetime(existing["tarih"]).dt.normalize()
        combined = pd.concat([existing, fresh], ignore_index=True)
    else:
        combined = fresh.copy()

    combined["tarih"] = pd.to_datetime(combined["tarih"]).dt.normalize()
    combined = (
        combined.sort_values("tarih")
        .drop_duplicates(subset=["tarih"], keep="last")
        .reset_index(drop=True)
    )

    combined.to_parquet(out_path, index=False)
    return combined


def main(period: str = "5y") -> None:
    print(f"[market_data] Fetching USD/TRY and gold (period={period})...")
    fresh = fetch_markers(period=period)
    print(f"[market_data] Fetched {len(fresh)} dated observations.")

    combined = merge_and_write(fresh)
    latest = combined.iloc[-1]
    print(
        f"[market_data] Wrote {MARKET_DATA_PATH} "
        f"({len(combined)} rows; latest {latest['tarih'].strftime('%Y-%m-%d')}: "
        f"USD/TRY={latest['usd_try']:.4f}, gold_usd={latest['gold_usd']:.2f})."
    )


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "5y"
    main(period=period)
