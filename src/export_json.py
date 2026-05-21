"""Serialize the master parquet into the five static JSON payloads.

Pipeline stage 4 of 4 (updater -> data_loader -> market_data -> **export_json**).

Reads two parquet files:
    data/processed/master_flow_data.parquet  (per-fund daily ledger)
    data/processed/market_data.parquet       (USD/TRY + gold spot)

Writes five JSON files into ``<target>/`` (default ``../arkafon-fe/public/data/``):
    macro.json           KPIs, USD/TRY + Gram Gold series, latest spot rates
    fund_drilldown.json  per-fund 28-day ledger keyed by fund code
    all_funds.json       flat lookup index for the search box
    flow_sankey.json     top-10 inflow and outflow links for the network view
    money_pie.json       categorical allocation snapshots + diff table
    by_type.json         taxation split + 30-day stacked category trend

Heavy lifting (split correction, fund categorization) is done upstream in
``data_loader.py``. This module just slices, sums, formats.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd

from src.config import MARKET_DATA_PATH, MASTER_DATA_PATH

log = logging.getLogger(__name__)

# Troy ounce -> gram. Gold is priced per ounce in USD; we want TRY/gram.
GRAMS_PER_TROY_OUNCE = 31.1034768

# The six dashboard buckets data_loader assigns via be_kategori. Order
# matters for the deterministic series in by_type.json's trends array.
BE_CATEGORIES: Tuple[str, ...] = (
    "Hisse", "Borçlanma", "Para Piyasası",
    "Kıymetli Madenler", "Uluslararası", "Değişken",
)

# Buckets considered tax-exempt in the by_type.json snapshot. The rest
# fall under the standard stopaj (withholding) framework.
TAX_EXEMPT_BUCKETS = frozenset({"Hisse", "Para Piyasası"})


# ──────────────────────────────────────────────────────────────────────────
# Macro layer
# ──────────────────────────────────────────────────────────────────────────

def _macro_metrics(df_market: pd.DataFrame, on_date: pd.Timestamp) -> Dict[str, float]:
    """USD and gold spot for a given date. Returns sentinels on miss."""
    row = df_market[df_market["tarih"] == on_date]
    if row.empty:
        return {"usd": 1.0, "gold": 1.0}
    usd = float(row["usd_try"].iloc[0])
    gold = float(row["gold_usd"].iloc[0])
    return {"usd": usd, "gold": gold, "xau_try": usd * gold / GRAMS_PER_TROY_OUNCE}


def _pct_change(curr: float, prev: float) -> float:
    """Safe percentage change. Returns 0.0 when prev is falsy."""
    if not prev:
        return 0.0
    return round(((curr - prev) / prev) * 100, 2)


def _build_macro(
    df_flow_today: pd.DataFrame,
    df_market: pd.DataFrame,
    latest_date: pd.Timestamp,
    cumulative_inflows: float,
    total_net_inflow: float,
    top_fund_code: str,
) -> Dict:
    series = []
    for _, r in df_market.sort_values("tarih").tail(60).iterrows():
        usd, gold = float(r["usd_try"]), float(r["gold_usd"])
        series.append({
            "date": r["tarih"].strftime("%Y-%m-%d"),
            "usd_try": round(usd, 4),
            "gold_usd": round(gold, 2),
            "xau_try": round(usd * gold / GRAMS_PER_TROY_OUNCE, 2),
        })

    m0 = _macro_metrics(df_market, latest_date)
    m1 = _macro_metrics(df_market, latest_date - timedelta(days=1))
    m7 = _macro_metrics(df_market, latest_date - timedelta(days=7))

    market_cap_try = float((df_flow_today["FIYAT"] * df_flow_today["TEDPAYSAYISI"]).sum())
    unique_funds = int(df_flow_today["FONKODU"].nunique())
    usd_latest = m0["usd"] or 1.0

    return {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reference_date": latest_date.strftime("%Y-%m-%d"),
        },
        "stats": {
            "cumulative_inflows_try": round(cumulative_inflows, 2),
            "cumulative_inflows_usd": round(cumulative_inflows / usd_latest, 2),
            "total_net_inflow_try": round(total_net_inflow, 2),
            "total_net_inflow_usd": round(total_net_inflow / usd_latest, 2),
            "unique_funds": unique_funds,
            "top_fund": top_fund_code,
            "market_cap_try": round(market_cap_try, 2),
            "market_cap_usd": round(market_cap_try / usd_latest, 2),
            "usd_try_daily_pct":  _pct_change(m0["usd"],  m1["usd"]),
            "usd_try_weekly_pct": _pct_change(m0["usd"],  m7["usd"]),
            "gold_usd_daily_pct":  _pct_change(m0["gold"], m1["gold"]),
            "gold_usd_weekly_pct": _pct_change(m0["gold"], m7["gold"]),
            "usd_try_latest": round(usd_latest, 4),
            "gold_usd_latest": round(m0["gold"], 2),
            "xau_try_latest": round(m0.get("xau_try", usd_latest * m0["gold"] / GRAMS_PER_TROY_OUNCE), 2),
        },
        "series": series,
    }


# ──────────────────────────────────────────────────────────────────────────
# Drilldown layer (per-fund 28-day ledger)
# ──────────────────────────────────────────────────────────────────────────

def _build_drilldown(df_flow: pd.DataFrame, latest_date: pd.Timestamp) -> Tuple[Dict, List[Dict]]:
    """Per-fund 28-day ledger plus a flat code/name lookup."""
    window_start = latest_date - timedelta(days=45)  # 45-day window -> 28 trading sessions
    window = df_flow[df_flow["tarih"] >= window_start]

    drilldown: Dict[str, Dict] = {}
    lookup: List[Dict] = []

    for code, group in window.groupby("FONKODU", sort=False):
        rows = group.sort_values("tarih").tail(28)
        if rows.empty:
            continue
        name = str(rows["FONUNVAN"].iloc[-1])
        drilldown[code] = {
            "code": code,
            "name": name,
            "history": [
                {
                    "date": r.tarih.strftime("%Y-%m-%d"),
                    "price": round(float(r.FIYAT), 6),
                    "shares": float(r.TEDPAYSAYISI),
                    "net_flow_try": round(float(r.net_giris_tl), 2),
                }
                for r in rows.itertuples(index=False)
            ],
        }
        lookup.append({"code": code, "name": name})

    return drilldown, lookup


# ──────────────────────────────────────────────────────────────────────────
# Flow Sankey layer (top inflow / outflow funds for the latest session)
# ──────────────────────────────────────────────────────────────────────────

def _build_sankey(df_flow_today: pd.DataFrame) -> Dict:
    """Top 10 inflows + top 10 outflows for the latest session."""
    ranked = df_flow_today[["FONKODU", "net_giris_tl"]].sort_values(
        "net_giris_tl", ascending=False
    )
    top_in = ranked.head(10)
    top_out = ranked.tail(10)

    nodes: set[str] = set()
    links: List[Dict] = []

    for _, r in top_in.iterrows():
        v = float(r["net_giris_tl"])
        if v <= 0:
            continue
        nodes.add("Market Inflows")
        nodes.add(str(r["FONKODU"]))
        links.append({"source": "Market Inflows", "target": str(r["FONKODU"]), "value": round(v, 2)})

    for _, r in top_out.iterrows():
        v = float(r["net_giris_tl"])
        if v >= 0:
            continue
        nodes.add("Market Outflows")
        nodes.add(str(r["FONKODU"]))
        links.append({"source": str(r["FONKODU"]), "target": "Market Outflows", "value": round(abs(v), 2)})

    return {"nodes": [{"name": n} for n in nodes], "links": links}


# ──────────────────────────────────────────────────────────────────────────
# Allocation layer (money_pie.json)
# ──────────────────────────────────────────────────────────────────────────

def _category_caps(df: pd.DataFrame) -> Dict[str, float]:
    """Sum FIYAT*TEDPAYSAYISI grouped by be_kategori."""
    if df.empty:
        return {}
    caps = (df["FIYAT"] * df["TEDPAYSAYISI"]).groupby(df["be_kategori"]).sum()
    return {k: float(v) for k, v in caps.items()}


def _build_money_pie(
    df_flow: pd.DataFrame,
    df_today: pd.DataFrame,
    latest_date: pd.Timestamp,
    usd_latest: float,
) -> Tuple[Dict, Dict[str, float], Dict[str, float]]:
    """Allocation snapshot at T0 vs. T-30 plus a TRY/USD diff table."""
    t0_caps = _category_caps(df_today)

    t1_target = latest_date - timedelta(days=30)
    df_t1 = df_flow[df_flow["tarih"] == t1_target]
    if df_t1.empty:
        # Fall back to the earliest session we have data for.
        t1_target = df_flow["tarih"].min()
        df_t1 = df_flow[df_flow["tarih"] == t1_target]
    t1_caps = _category_caps(df_t1)

    table = []
    for cat in BE_CATEGORIES:
        start = t1_caps.get(cat, 0.0)
        end = t0_caps.get(cat, 0.0)
        diff = end - start
        pct = (diff / start * 100) if start > 0 else 0.0
        table.append({
            "asset_class": cat,
            "start_try": round(start, 2),
            "start_usd": round(start / usd_latest, 2),
            "end_try":   round(end,   2),
            "end_usd":   round(end   / usd_latest, 2),
            "diff_try":  round(diff,  2),
            "diff_usd":  round(diff  / usd_latest, 2),
            "pct":       round(pct,   2),
        })

    payload = {
        "metadata": {
            "start_date": t1_target.strftime("%Y-%m-%d"),
            "end_date":   latest_date.strftime("%Y-%m-%d"),
        },
        "allocation_start": [{"name": k, "value": round(v, 2)} for k, v in t1_caps.items()],
        "allocation_end":   [{"name": k, "value": round(v, 2)} for k, v in t0_caps.items()],
        "table_metrics": table,
    }
    return payload, t0_caps, t1_caps


# ──────────────────────────────────────────────────────────────────────────
# Type/tax layer (by_type.json)
# ──────────────────────────────────────────────────────────────────────────

def _build_by_type(
    df_flow: pd.DataFrame,
    t0_caps: Dict[str, float],
    usd_latest: float,
) -> Dict:
    """Tax-exempt / taxable snapshot plus 30-session stacked category trend."""
    exempt = sum(v for k, v in t0_caps.items() if k in TAX_EXEMPT_BUCKETS)
    taxable = sum(v for k, v in t0_caps.items() if k not in TAX_EXEMPT_BUCKETS)
    total = exempt + taxable

    last_dates = sorted(df_flow["tarih"].unique())[-30:]
    trends = []
    for d in last_dates:
        snap = df_flow[df_flow["tarih"] == d]
        caps = _category_caps(snap)
        record = {"date": pd.to_datetime(d).strftime("%Y-%m-%d")}
        for cat in BE_CATEGORIES:
            record[cat] = round(caps.get(cat, 0.0), 2)
        trends.append(record)

    return {
        "taxation_snapshot": {
            "tax_exempt_try": round(exempt, 2),
            "tax_exempt_usd": round(exempt / usd_latest, 2),
            "taxable_try":    round(taxable, 2),
            "taxable_usd":    round(taxable / usd_latest, 2),
            "ratio_exempt":   round((exempt / total * 100) if total > 0 else 0.0, 2),
        },
        "trends": trends,
    }


# ──────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────

def _dump(payload: object, path: str, *, indent: int | None = 2) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)


def build_static_matrices(target_dir: str) -> None:
    os.makedirs(target_dir, exist_ok=True)
    log.info("Compiling static payloads into %s", target_dir)

    if not os.path.exists(MASTER_DATA_PATH) or not os.path.exists(MARKET_DATA_PATH):
        raise FileNotFoundError(
            "Prerequisite parquets missing. Run data_loader and market_data first."
        )

    df_flow = pd.read_parquet(MASTER_DATA_PATH)
    df_market = pd.read_parquet(MARKET_DATA_PATH)
    df_flow["tarih"] = pd.to_datetime(df_flow["tarih"]).dt.normalize()
    df_market["tarih"] = pd.to_datetime(df_market["tarih"]).dt.normalize()

    if "be_kategori" not in df_flow.columns:
        raise RuntimeError(
            "master_flow_data.parquet lacks be_kategori. Rebuild via data_loader."
        )

    latest_date = df_flow["tarih"].max()
    log.info("Reference date: %s", latest_date.strftime("%Y-%m-%d"))

    df_today = df_flow[df_flow["tarih"] == latest_date]

    # Top-line aggregates (used by the macro layer).
    inflows = df_today["net_giris_tl"]
    cumulative_inflows = float(inflows[inflows > 0].sum())
    total_net_inflow = float(inflows.sum())
    top_idx = inflows.idxmax() if not inflows.empty else None
    top_fund_code = str(df_today.loc[top_idx, "FONKODU"]) if top_idx is not None else "N/A"

    # Macro
    macro = _build_macro(
        df_today, df_market, latest_date,
        cumulative_inflows, total_net_inflow, top_fund_code,
    )
    _dump(macro, os.path.join(target_dir, "macro.json"))

    # Drilldown
    drilldown, lookup = _build_drilldown(df_flow, latest_date)
    _dump(drilldown, os.path.join(target_dir, "fund_drilldown.json"), indent=None)
    _dump(lookup, os.path.join(target_dir, "all_funds.json"))

    # Sankey
    _dump(_build_sankey(df_today), os.path.join(target_dir, "flow_sankey.json"))

    # Money pie + by-type (share the t0_caps map)
    usd_latest = macro["stats"]["usd_try_latest"] or 1.0
    money_pie, t0_caps, _ = _build_money_pie(df_flow, df_today, latest_date, usd_latest)
    _dump(money_pie, os.path.join(target_dir, "money_pie.json"))
    _dump(_build_by_type(df_flow, t0_caps, usd_latest), os.path.join(target_dir, "by_type.json"))

    log.info("Static JSON generation complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", default="../arkafon-fe/public/data/",
        help="Output directory (default: ../arkafon-fe/public/data/)",
    )
    args = parser.parse_args()
    build_static_matrices(args.target)
