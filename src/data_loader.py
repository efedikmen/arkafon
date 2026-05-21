"""Compile raw daily TEFAS parquet snapshots into one master file.

Pipeline stage 2 of 4 (updater -> **data_loader** -> market_data -> export_json).

The input is whatever TEFAS snapshots `updater.py` has accumulated in
``data/raw/tefas_data_DD.MM.YYYY.parquet``. The output is a single file
at ``data/processed/master_flow_data.parquet`` with these columns:

    tarih          datetime64[ns]  trade date, normalized
    FONKODU        object          fund code (string)
    FONUNVAN       object          official fund name
    FIYAT          float64         NAV price for the day
    TEDPAYSAYISI   float64         circulating shares on the day
    net_giris_tl   float64         net capital flow vs. previous session (TRY)
    ana_kategori   object          SPK-canonical category (classifier.py)
    alt_kategori   object          SPK-canonical sub-category
    be_kategori    object          one of six dashboard buckets used by the FE

``net_giris_tl`` uses a split-aware formula: when a fund's NAV changes by
more than 5x or less than 0.2x day-over-day, we treat it as a corporate
action (share-class split / reverse-split) and rescale the prior session's
share count by the nearest power of ten so the computed flow only
reflects subscriptions / redemptions.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

from src.classifier import classify_fund
from src.config import MASTER_DATA_PATH, PROCESSED_DATA_DIR, RAW_DATA_DIR

log = logging.getLogger(__name__)

REQUIRED_COLS = ("FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI")

# Bridge from classifier.py's SPK-canonical labels to the six dashboard
# buckets the frontend renders. Keys are (ana_kategori, alt_kategori);
# alt_kategori is matched first with a wildcard "*" fallback.
_BE_BUCKET_MAP = {
    ("PPF (TL)",      "*"): "Para Piyasası",
    ("Hisse (TL)",    "*"): "Hisse",
    ("Tahvil (TL)",   "*"): "Borçlanma",
    ("Döviz",         "Kıymetli Maden / Emtia"): "Kıymetli Madenler",
    ("Döviz",         "Eurobond"):               "Borçlanma",
    ("Döviz",         "Yabancı Hisse"):          "Hisse",
    ("Döviz",         "Yabancı Tahvil"):         "Borçlanma",
    ("Döviz",         "Döviz PPF"):              "Para Piyasası",
    ("Döviz",         "*"):                      "Uluslararası",
    ("Katılım Fonu",  "*"): "Uluslararası",
    ("Fon Sepeti",    "*"): "Değişken",
    ("Serbest Fon",   "*"): "Değişken",
    ("Değişken Fon",  "*"): "Değişken",
    ("Karma Fon",     "*"): "Değişken",
    ("Diğer",         "*"): "Değişken",
}


def _to_be_bucket(ana: str, alt: str) -> str:
    return (
        _BE_BUCKET_MAP.get((ana, alt))
        or _BE_BUCKET_MAP.get((ana, "*"))
        or "Değişken"
    )


def _load_daily_files() -> Optional[pd.DataFrame]:
    """Concat every well-formed raw parquet into a single long frame."""
    if not os.path.isdir(RAW_DATA_DIR):
        log.error("Raw data directory missing: %s", RAW_DATA_DIR)
        return None

    files = sorted(f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".parquet"))
    if not files:
        log.error("No raw parquet files found under %s", RAW_DATA_DIR)
        return None

    frames: List[pd.DataFrame] = []
    for name in files:
        # File name convention: tefas_data_DD.MM.YYYY.parquet
        try:
            date_str = name.split("_")[-1].removesuffix(".parquet")
            tarih = pd.to_datetime(date_str, format="%d.%m.%Y")
        except (ValueError, IndexError):
            log.warning("Skipping un-parseable filename: %s", name)
            continue

        try:
            df = pd.read_parquet(os.path.join(RAW_DATA_DIR, name))
        except (OSError, ValueError) as exc:
            log.warning("Skipping unreadable %s: %s", name, exc)
            continue

        df.columns = df.columns.str.strip().str.upper()
        if not all(c in df.columns for c in REQUIRED_COLS):
            log.warning("Skipping %s: missing required columns", name)
            continue

        df = df.loc[:, list(REQUIRED_COLS)].copy()
        df["FONKODU"] = df["FONKODU"].astype(str).str.strip()
        df["tarih"] = tarih
        frames.append(df)

    if not frames:
        log.error("No raw files yielded usable rows.")
        return None
    return pd.concat(frames, ignore_index=True)


def _correct_splits_and_compute_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Add net_giris_tl with corporate-action correction.

    For each fund, the previous session's share count is rescaled by the
    nearest power of ten whenever a >5x or <0.2x price jump suggests a
    split. The flow is then ``(shares_today - shares_yesterday_corrected)
    * price_today``, which cancels out the mechanical share-count change
    and leaves only real subscriptions / redemptions.
    """
    df = df.sort_values(["FONKODU", "tarih"]).reset_index(drop=True)

    grouped = df.groupby("FONKODU", sort=False)
    prev_price = grouped["FIYAT"].shift(1)
    prev_shares = grouped["TEDPAYSAYISI"].shift(1)

    # Detect split factor only where we have a previous session to compare.
    price_ratio = df["FIYAT"] / prev_price
    suspicious = (price_ratio > 5.0) | (price_ratio < 0.2)

    split_factor = pd.Series(1.0, index=df.index, dtype="float64")
    if suspicious.any():
        # Round the log10 of the ratio to nail down the cleanest power of ten
        # (e.g. 99.7 -> 100, 0.099 -> 0.1).
        split_factor.loc[suspicious] = 10.0 ** np.round(
            np.log10(price_ratio.loc[suspicious])
        )

    corrected_prev_shares = prev_shares / split_factor
    df["net_giris_tl"] = (
        (df["TEDPAYSAYISI"] - corrected_prev_shares).fillna(0.0)
        * df["FIYAT"]
    )

    return df


def _assign_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Attach ana_kategori / alt_kategori / be_kategori columns."""
    unique = df[["FONKODU", "FONUNVAN"]].drop_duplicates().copy()
    classified = unique["FONUNVAN"].apply(classify_fund).tolist()
    unique[["ana_kategori", "alt_kategori"]] = pd.DataFrame(classified, index=unique.index)
    unique["be_kategori"] = [_to_be_bucket(a, s) for a, s in classified]
    return df.merge(
        unique[["FONKODU", "ana_kategori", "alt_kategori", "be_kategori"]],
        on="FONKODU",
        how="left",
    )


def build_master_data() -> Optional[str]:
    """Run the full ETL. Returns the output path on success, or None."""
    log.info("Loading raw daily snapshots...")
    df = _load_daily_files()
    if df is None:
        return None

    log.info("Correcting splits and computing flows for %d rows...", len(df))
    df = _correct_splits_and_compute_flows(df)

    log.info("Assigning SPK and dashboard categories...")
    df = _assign_categories(df)

    final_cols = [
        "tarih", "FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI",
        "net_giris_tl", "ana_kategori", "alt_kategori", "be_kategori",
    ]
    df = df.loc[:, final_cols]

    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
    df.to_parquet(MASTER_DATA_PATH)
    log.info("Wrote %s (%d rows)", MASTER_DATA_PATH, len(df))
    return MASTER_DATA_PATH


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    build_master_data()
