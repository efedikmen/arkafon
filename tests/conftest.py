"""Shared pytest fixtures.

The package-import shim must run for every test module. Beyond that, we
expose a handful of fixtures that build tiny synthetic parquet inputs so
each test module can exercise the pipeline without touching network or
real TEFAS data.
"""
import os
import sys
import tempfile

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def tmp_data_dirs(monkeypatch):
    """Point the pipeline's path constants at an isolated temp directory.

    Yields a dict of paths so tests can drop files in or read outputs.
    Every module-level path constant is patched (config.* AND the
    relevant pipeline modules that imported them at load time).
    """
    tmp = tempfile.mkdtemp(prefix="arkafon-test-")
    raw = os.path.join(tmp, "raw")
    proc = os.path.join(tmp, "processed")
    target = os.path.join(tmp, "out")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(proc, exist_ok=True)
    os.makedirs(target, exist_ok=True)

    master = os.path.join(proc, "master_flow_data.parquet")
    market = os.path.join(proc, "market_data.parquet")

    from src import config
    monkeypatch.setattr(config, "RAW_DATA_DIR", raw)
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", proc)
    monkeypatch.setattr(config, "MASTER_DATA_PATH", master)
    monkeypatch.setattr(config, "MARKET_DATA_PATH", market)

    # The pipeline modules captured the constants at import time. Patch
    # them too — otherwise the modules still see the original paths.
    patched_values = {
        "RAW_DATA_DIR": raw,
        "PROCESSED_DATA_DIR": proc,
        "MASTER_DATA_PATH": master,
        "MARKET_DATA_PATH": market,
    }
    for mod_name in ("src.data_loader", "src.export_json", "src.market_data", "src.updater"):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            for attr, value in patched_values.items():
                if hasattr(mod, attr):
                    monkeypatch.setattr(mod, attr, value)

    return {"raw": raw, "proc": proc, "target": target, "master": master, "market": market}


def _write_daily(raw_dir: str, date_str: str, rows):
    """Helper used by multiple test modules: drop one daily parquet."""
    pd.DataFrame(
        rows, columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]
    ).to_parquet(os.path.join(raw_dir, f"tefas_data_{date_str}.parquet"))


@pytest.fixture
def write_daily():
    """Expose the daily-file writer to tests that need to seed RAW_DATA_DIR."""
    return _write_daily


@pytest.fixture
def seeded_master(tmp_data_dirs, write_daily):
    """A master_flow_data.parquet with three sessions, four funds, real categories.

    Funds cover one of each be_kategori bucket so downstream tests can
    assert that the categorization survives the round-trip.
    """
    write_daily(tmp_data_dirs["raw"], "01.01.2024", [
        ("EQA", "İş Portföy Hisse Senedi Fonu",          12.00, 1_000_000),
        ("BND", "Garanti Borçlanma Araçları Fonu",       11.50,   800_000),
        ("PPF", "Ak Para Piyasası Fonu",                 10.05, 5_000_000),
        ("GLD", "QNB Altın Kıymetli Maden Fonu",          9.80,   500_000),
    ])
    write_daily(tmp_data_dirs["raw"], "02.01.2024", [
        ("EQA", "İş Portföy Hisse Senedi Fonu",          12.10, 1_020_000),  # +20k @ 12.10 ≈ +242k
        ("BND", "Garanti Borçlanma Araçları Fonu",       11.50,   790_000),  # -10k @ 11.50 ≈ -115k
        ("PPF", "Ak Para Piyasası Fonu",                 10.06, 5_010_000),  # +10k @ 10.06 ≈ +100.6k
        ("GLD", "QNB Altın Kıymetli Maden Fonu",          9.85,   500_000),  # flat
    ])
    write_daily(tmp_data_dirs["raw"], "03.01.2024", [
        ("EQA", "İş Portföy Hisse Senedi Fonu",          12.05, 1_025_000),  # +5k @ 12.05 ≈ +60k
        ("BND", "Garanti Borçlanma Araçları Fonu",       11.45,   795_000),  # +5k @ 11.45 ≈ +57k
        ("PPF", "Ak Para Piyasası Fonu",                 10.07, 5_015_000),  # +5k @ 10.07 ≈ +50k
        ("GLD", "QNB Altın Kıymetli Maden Fonu",          9.90,   505_000),  # +5k @ 9.90  ≈ +49.5k
    ])

    from src.data_loader import build_master_data
    build_master_data()
    return tmp_data_dirs


@pytest.fixture
def seeded_market(tmp_data_dirs):
    """A market_data.parquet with the same three sessions."""
    df = pd.DataFrame({
        "tarih":   pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "usd_try": [30.00, 30.10, 30.05],
        "gold_usd": [2050.0, 2060.0, 2055.0],
    })
    df.to_parquet(tmp_data_dirs["market"], index=False)
    return tmp_data_dirs
