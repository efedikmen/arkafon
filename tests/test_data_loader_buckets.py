"""Tests for data_loader's category bucketing + output schema.

The big behavior change in the most recent BE refactor was: the master
parquet now carries TEDPAYSAYISI through to disk (export_json was
silently breaking without it) and a new be_kategori column that maps
the SPK-canonical category to one of the six dashboard buckets the FE
groups on. Both are pinned here.
"""
import os

import pandas as pd
import pytest

from src.data_loader import (
    _BE_BUCKET_MAP,
    _to_be_bucket,
    build_master_data,
)


# ────────────────────────────────────────────────────────────────────────
# _to_be_bucket: pure mapping logic
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ana,alt,expected", [
    # Exact mappings from the table.
    ("PPF (TL)",     "-",                          "Para Piyasası"),
    ("Hisse (TL)",   "-",                          "Hisse"),
    ("Tahvil (TL)",  "-",                          "Borçlanma"),
    ("Döviz",        "Kıymetli Maden / Emtia",     "Kıymetli Madenler"),
    ("Döviz",        "Eurobond",                   "Borçlanma"),
    ("Döviz",        "Yabancı Hisse",              "Hisse"),
    ("Döviz",        "Yabancı Tahvil",             "Borçlanma"),
    ("Döviz",        "Döviz PPF",                  "Para Piyasası"),
    ("Katılım Fonu", "-",                          "Uluslararası"),
    ("Fon Sepeti",   "-",                          "Değişken"),
    ("Serbest Fon",  "-",                          "Değişken"),
    ("Değişken Fon", "-",                          "Değişken"),
    ("Karma Fon",    "-",                          "Değişken"),
    ("Diğer",        "-",                          "Değişken"),
])
def test_to_be_bucket_exact_matches(ana, alt, expected):
    assert _to_be_bucket(ana, alt) == expected


def test_to_be_bucket_doviz_wildcard_fallback():
    """An unknown Döviz sub-category falls through the wildcard to Uluslararası."""
    assert _to_be_bucket("Döviz", "Made-Up Sub") == "Uluslararası"


def test_to_be_bucket_unknown_ana_falls_back_to_degisken():
    """An entirely unrecognized SPK category lands in Değişken so the FE
    never has to render an undefined bucket."""
    assert _to_be_bucket("Quantum Fonu", "-") == "Değişken"


def test_be_bucket_map_covers_every_target_category():
    """The mapping must produce all six FE buckets at least once — else the
    by-type chart will have a dead series."""
    produced = set(_BE_BUCKET_MAP.values())
    assert produced == {
        "Hisse", "Borçlanma", "Para Piyasası",
        "Kıymetli Madenler", "Uluslararası", "Değişken",
    }


# ────────────────────────────────────────────────────────────────────────
# Output schema — the regression that broke export_json before
# ────────────────────────────────────────────────────────────────────────

EXPECTED_SCHEMA = {
    "tarih", "FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI",
    "net_giris_tl", "ana_kategori", "alt_kategori", "be_kategori",
}


def test_master_parquet_has_expected_columns(seeded_master):
    out = pd.read_parquet(seeded_master["master"])
    assert set(out.columns) == EXPECTED_SCHEMA


def test_master_parquet_keeps_tedpaysayisi(seeded_master):
    """Regression: a prior refactor dropped TEDPAYSAYISI before save and
    crashed export_json. Lock it down — this column MUST persist."""
    out = pd.read_parquet(seeded_master["master"])
    assert "TEDPAYSAYISI" in out.columns
    assert (out["TEDPAYSAYISI"] > 0).all()


def test_master_parquet_has_be_kategori_for_every_row(seeded_master):
    out = pd.read_parquet(seeded_master["master"])
    assert out["be_kategori"].notna().all()
    # And every value is one of the known six buckets.
    assert set(out["be_kategori"].unique()).issubset({
        "Hisse", "Borçlanma", "Para Piyasası",
        "Kıymetli Madenler", "Uluslararası", "Değişken",
    })


# ────────────────────────────────────────────────────────────────────────
# Failure modes
# ────────────────────────────────────────────────────────────────────────

def test_build_master_data_returns_none_when_raw_dir_empty(tmp_data_dirs):
    assert build_master_data() is None


def test_build_master_data_skips_unparseable_filenames(tmp_data_dirs, write_daily):
    # One well-formed file…
    write_daily(tmp_data_dirs["raw"], "01.01.2024", [
        ("AAA", "Aaa Fund", 10.0, 1_000_000),
    ])
    # …and one bogus file that should be silently skipped.
    bogus = os.path.join(tmp_data_dirs["raw"], "bogus.parquet")
    pd.DataFrame({"a": [1]}).to_parquet(bogus)

    assert build_master_data() is not None
    out = pd.read_parquet(tmp_data_dirs["master"])
    assert len(out) == 1
    assert out["FONKODU"].iloc[0] == "AAA"
