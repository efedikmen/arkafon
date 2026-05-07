"""Golden tests for the split-detection / net-flow math in data_loader.

These fixtures pin the expected output of the ETL on a tiny but representative
slice. A regression here is exactly the kind of silent bug that erodes trust
in the dashboard's numbers, so we lock the math down here.
"""
import os
import tempfile
from datetime import datetime

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def raw_files_dir(monkeypatch):
    """Build three synthetic daily parquets with a known split on day 3."""
    tmp = tempfile.mkdtemp()
    raw = os.path.join(tmp, "raw"); os.makedirs(raw)
    proc = os.path.join(tmp, "processed"); os.makedirs(proc)
    rows = [
        # day 1: AAA fund, 1m units at TL10
        ("AAA", "AAA Fund", 10.0, 1_000_000),
        ("BBB", "BBB Fund", 5.0, 200_000),
    ]
    pd.DataFrame(rows, columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]) \
        .to_parquet(os.path.join(raw, "tefas_01.01.2024.parquet"))
    rows = [
        # day 2: same prices, AAA gains 10k units (real inflow), BBB unchanged
        ("AAA", "AAA Fund", 10.0, 1_010_000),
        ("BBB", "BBB Fund", 5.0, 200_000),
    ]
    pd.DataFrame(rows, columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]) \
        .to_parquet(os.path.join(raw, "tefas_02.01.2024.parquet"))
    rows = [
        # day 3: AAA does a 10:1 split: price 1.0, units 10.1m. Net flow = 0.
        ("AAA", "AAA Fund", 1.0, 10_100_000),
        ("BBB", "BBB Fund", 5.0, 200_000),
    ]
    pd.DataFrame(rows, columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]) \
        .to_parquet(os.path.join(raw, "tefas_03.01.2024.parquet"))

    from src import config, data_loader
    monkeypatch.setattr(config, "RAW_DATA_DIR", raw)
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", proc)
    monkeypatch.setattr(config, "MASTER_DATA_PATH", os.path.join(proc, "master_flow_data.parquet"))
    monkeypatch.setattr(data_loader, "RAW_DATA_DIR", raw)
    monkeypatch.setattr(data_loader, "PROCESSED_DATA_DIR", proc)
    monkeypatch.setattr(data_loader, "MASTER_DATA_PATH", os.path.join(proc, "master_flow_data.parquet"))
    return os.path.join(proc, "master_flow_data.parquet")


def test_split_detection_does_not_create_phantom_inflow(raw_files_dir):
    from src.data_loader import build_master_data
    build_master_data()
    out = pd.read_parquet(raw_files_dir).sort_values(["FONKODU", "tarih"])

    aaa = out[out["FONKODU"] == "AAA"].set_index("tarih")["net_giris_tl"]
    # day 1 row: no "prev" so flow == 0
    assert aaa.iloc[0] == 0.0
    # day 2: real inflow of 10k units * TL10 = TL100k
    assert aaa.iloc[1] == pytest.approx(100_000.0, rel=1e-9)
    # day 3: 10:1 split must NOT register as a giant outflow.
    # After healing, the model treats prev units as 1.01m (1.01m * 10 -> 10.1m new).
    # Real units delta = 0 -> net_giris_tl ~ 0.
    assert abs(aaa.iloc[2]) < 1.0  # within rounding tolerance


def test_unrelated_fund_is_unaffected(raw_files_dir):
    from src.data_loader import build_master_data
    build_master_data()
    out = pd.read_parquet(raw_files_dir)
    bbb = out[out["FONKODU"] == "BBB"]["net_giris_tl"]
    # constant units & price -> no flow on any day
    assert (bbb.abs() < 1e-9).all()
