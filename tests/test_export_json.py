"""Tests for src.export_json.

Mix of unit tests on the pure helpers (_pct_change, _category_caps,
_macro_metrics) and one integration test that runs build_static_matrices
end-to-end against synthetic parquets and asserts on the JSON schema
the FE consumes.
"""
import json
import os

import pandas as pd
import pytest

from src.export_json import (
    BE_CATEGORIES,
    GRAMS_PER_TROY_OUNCE,
    TAX_EXEMPT_BUCKETS,
    _build_sankey,
    _category_caps,
    _macro_metrics,
    _pct_change,
    build_static_matrices,
)


# ────────────────────────────────────────────────────────────────────────
# Pure helpers
# ────────────────────────────────────────────────────────────────────────

def test_pct_change_basic():
    assert _pct_change(110, 100) == 10.0
    assert _pct_change(90, 100) == -10.0


def test_pct_change_zero_prev_is_safe():
    assert _pct_change(50, 0) == 0.0
    assert _pct_change(0, 0) == 0.0


def test_pct_change_rounds_to_two_decimals():
    # 1/300 = 0.00333... → 0.33%
    assert _pct_change(301, 300) == 0.33


def test_macro_metrics_for_present_date():
    df = pd.DataFrame({
        "tarih":    pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "usd_try":  [30.0, 30.5],
        "gold_usd": [2000.0, 2050.0],
    })
    out = _macro_metrics(df, pd.Timestamp("2024-01-02"))
    assert out["usd"] == 30.5
    assert out["gold"] == 2050.0
    assert out["xau_try"] == pytest.approx(30.5 * 2050.0 / GRAMS_PER_TROY_OUNCE)


def test_macro_metrics_missing_date_returns_sentinel():
    df = pd.DataFrame({
        "tarih": pd.to_datetime(["2024-01-01"]), "usd_try": [30.0], "gold_usd": [2000.0],
    })
    out = _macro_metrics(df, pd.Timestamp("2099-12-31"))
    assert out == {"usd": 1.0, "gold": 1.0}


def test_category_caps_groups_by_be_kategori():
    df = pd.DataFrame({
        "FIYAT":        [10.0, 5.0, 20.0],
        "TEDPAYSAYISI": [100,  200, 50],
        "be_kategori":  ["Hisse", "Hisse", "Borçlanma"],
    })
    caps = _category_caps(df)
    assert caps["Hisse"] == pytest.approx(10*100 + 5*200)
    assert caps["Borçlanma"] == pytest.approx(20*50)


def test_category_caps_on_empty_frame():
    assert _category_caps(pd.DataFrame()) == {}


# ────────────────────────────────────────────────────────────────────────
# Sankey: positive flows in, negative flows out, near-zero dropped
# ────────────────────────────────────────────────────────────────────────

def test_sankey_partitions_in_and_out_correctly():
    df = pd.DataFrame({
        "FONKODU":      ["IN1", "IN2", "OUT1", "OUT2", "FLAT"],
        "net_giris_tl": [100.0, 50.0, -80.0, -10.0,    0.0],
    })
    payload = _build_sankey(df)
    sources = {l["source"] for l in payload["links"]}
    targets = {l["target"] for l in payload["links"]}
    assert "Market Inflows" in sources
    assert "Market Outflows" in targets

    in_codes  = {l["target"] for l in payload["links"] if l["source"] == "Market Inflows"}
    out_codes = {l["source"] for l in payload["links"] if l["target"] == "Market Outflows"}
    assert in_codes  == {"IN1", "IN2"}
    assert out_codes == {"OUT1", "OUT2"}
    # FLAT never lands in either set — zero-flow funds are filtered out.
    assert "FLAT" not in in_codes | out_codes


def test_sankey_outflow_value_is_unsigned():
    df = pd.DataFrame({
        "FONKODU":      ["OUT1"],
        "net_giris_tl": [-1234.5],
    })
    payload = _build_sankey(df)
    assert payload["links"][0]["value"] == 1234.5  # positive in the JSON


# ────────────────────────────────────────────────────────────────────────
# Module-level constants
# ────────────────────────────────────────────────────────────────────────

def test_be_categories_is_six_known_buckets():
    assert set(BE_CATEGORIES) == {
        "Hisse", "Borçlanma", "Para Piyasası",
        "Kıymetli Madenler", "Uluslararası", "Değişken",
    }


def test_tax_exempt_buckets_are_subset_of_categories():
    assert TAX_EXEMPT_BUCKETS.issubset(set(BE_CATEGORIES))


# ────────────────────────────────────────────────────────────────────────
# Integration: full pipeline writes the five expected JSON files
# ────────────────────────────────────────────────────────────────────────

EXPECTED_FILES = {
    "macro.json", "fund_drilldown.json", "all_funds.json",
    "flow_sankey.json", "money_pie.json", "by_type.json",
}


def _run_pipeline(seeded_master, seeded_market):
    """seeded_master and seeded_market both write to the same tmp_data_dirs."""
    target = seeded_master["target"]
    build_static_matrices(target)
    return target


def test_pipeline_writes_all_five_payloads(seeded_master, seeded_market):
    target = _run_pipeline(seeded_master, seeded_market)
    assert EXPECTED_FILES.issubset(set(os.listdir(target)))


def test_macro_json_schema(seeded_master, seeded_market):
    target = _run_pipeline(seeded_master, seeded_market)
    with open(os.path.join(target, "macro.json"), encoding="utf-8") as f:
        macro = json.load(f)
    # Required top-level keys.
    assert set(macro.keys()) >= {"metadata", "stats", "series"}
    # New keys added in the BE pipeline-completion PR.
    for k in ("usd_try_latest", "gold_usd_latest", "xau_try_latest"):
        assert k in macro["stats"], f"missing stats.{k}"
    # Series carries the three plot lines.
    assert macro["series"], "series must be non-empty"
    for row in macro["series"]:
        assert {"date", "usd_try", "gold_usd", "xau_try"} <= set(row.keys())


def test_drilldown_keys_match_lookup(seeded_master, seeded_market):
    target = _run_pipeline(seeded_master, seeded_market)
    with open(os.path.join(target, "fund_drilldown.json"), encoding="utf-8") as f:
        drill = json.load(f)
    with open(os.path.join(target, "all_funds.json"), encoding="utf-8") as f:
        lookup = json.load(f)
    drill_codes = set(drill.keys())
    lookup_codes = {f["code"] for f in lookup}
    assert drill_codes == lookup_codes


def test_money_pie_table_metrics_cover_all_be_categories(seeded_master, seeded_market):
    target = _run_pipeline(seeded_master, seeded_market)
    with open(os.path.join(target, "money_pie.json"), encoding="utf-8") as f:
        pie = json.load(f)
    classes_in_table = {row["asset_class"] for row in pie["table_metrics"]}
    assert classes_in_table == set(BE_CATEGORIES)


def test_by_type_trends_include_all_six_categories(seeded_master, seeded_market):
    target = _run_pipeline(seeded_master, seeded_market)
    with open(os.path.join(target, "by_type.json"), encoding="utf-8") as f:
        by_type = json.load(f)
    assert by_type["trends"], "trends must be non-empty"
    for point in by_type["trends"]:
        # Every category present so the FE area-chart stack lines up.
        for cat in BE_CATEGORIES:
            assert cat in point, f"trend point missing category: {cat}"


def test_build_raises_when_market_parquet_missing(seeded_master):
    """Pipeline must fail loudly on missing prerequisites, not generate
    half a payload set."""
    # seeded_master writes the master parquet, but NOT the market one.
    with pytest.raises(FileNotFoundError):
        build_static_matrices(seeded_master["target"])
