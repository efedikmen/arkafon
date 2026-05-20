"""
export_json.py — Static JSON Generator
Çalışma zamanı: updater.py'dan ETL sonrası çağrılır
Çıktı: public/data/*.json  (Vite build'e dahil edilir)

Her JSON dosyası tek bir sayfanın ihtiyacını karşılar.
Browser canlı API yerine bu dosyaları okur → Zero server load.
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, date

from src.config import MASTER_DATA_PATH, BASE_DIR

OUTPUT_DIR = os.path.join(BASE_DIR, "public", "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _jdump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
    print(f"  ✅ {os.path.basename(path)}")


def _safe(v):
    """Convert numpy/nan to JSON-safe Python scalar."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def fmt_money(v: float) -> str:
    if not v or pd.isna(v):
        return "₺0"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1e12:
        return f"{sign}₺{abs_v/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{sign}₺{abs_v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{sign}₺{abs_v/1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{sign}₺{abs_v/1e3:.2f}K"
    return f"{sign}₺{abs_v:.0f}"


def build_all():
    print("📦 JSON Exporter başlatılıyor...")
    if not os.path.exists(MASTER_DATA_PATH):
        print("❌ master_flow_data.parquet bulunamadı!")
        return

    df = pd.read_parquet(MASTER_DATA_PATH)
    print(f"   {len(df):,} satır, {df['FONKODU'].nunique():,} fon yüklendi")

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "last_data_date": df["tarih"].max().strftime("%Y-%m-%d") if not df.empty else None,
        "total_rows": int(len(df)),
    }

    # ── 1. MACRO PULSE ────────────────────────────────────────────────────
    _build_macro(df, meta)

    # ── 2. FLOW MAP ──────────────────────────────────────────────────────
    _build_flow(df, meta)

    # ── 3. MONEY PIE ─────────────────────────────────────────────────────
    _build_money_pie(df, meta)

    # ── 4. BY TYPE ────────────────────────────────────────────────────────
    _build_by_type(df, meta)

    # ── 5. FUND INDEX (for drilldown autocomplete) ────────────────────────
    _build_fund_index(df, meta)

    print("🚀 Tüm JSON'lar hazır!")


def _build_macro(df: pd.DataFrame, meta: dict):
    """macro.json — Macro Pulse sayfası için tüm widget verileri."""
    # KPI
    total_inflow = float(df["net_giris_tl"].sum())
    unique_funds = int(df["FONKODU"].nunique())
    top_series = df.groupby(["FONKODU", "FONUNVAN"])["net_giris_tl"].sum()
    top_code, top_name = top_series.idxmax() if not top_series.empty else ("-", "-")

    # Kümülatif trend (son 365 gün)
    cutoff = df["tarih"].max() - pd.Timedelta(days=365)
    trend_df = (
        df[df["tarih"] >= cutoff]
        .groupby("tarih")["net_giris_tl"]
        .sum()
        .reset_index()
        .sort_values("tarih")
    )
    trend_df["cumulative"] = trend_df["net_giris_tl"].cumsum()
    trend_df["tarih"] = trend_df["tarih"].dt.strftime("%Y-%m-%d")

    # Top 10 fon (tüm zaman)
    top10 = (
        df.groupby(["FONKODU", "FONUNVAN"])["net_giris_tl"]
        .sum()
        .reset_index()
        .sort_values("net_giris_tl", ascending=False)
        .head(10)
    )

    # Universe (son 90 gün, top 30)
    recent = df[df["tarih"] >= df["tarih"].max() - pd.Timedelta(days=90)]
    universe = (
        recent.groupby(["FONKODU", "FONUNVAN", "ana_kategori"], dropna=False)
        .agg(
            netInflow=("net_giris_tl", "sum"),
            first_price=("FIYAT", "first"),
            last_price=("FIYAT", "last"),
        )
        .reset_index()
    )
    universe["perfYTD"] = (
        (universe["last_price"] - universe["first_price"]) / universe["first_price"]
    ).replace([np.inf, -np.inf], np.nan).fillna(0)
    universe = universe.sort_values("netInflow", ascending=False).head(30)

    _jdump(
        {
            "meta": meta,
            "kpi": {
                "total_net_inflow": _safe(total_inflow),
                "total_net_inflow_fmt": fmt_money(total_inflow),
                "unique_funds": unique_funds,
                "top_fund": {"code": top_code, "name": top_name},
            },
            "trend": [
                {
                    "date": r["tarih"],
                    "daily": _safe(r["net_giris_tl"]),
                    "cumulative": _safe(r["cumulative"]),
                }
                for _, r in trend_df.iterrows()
            ],
            "top10": [
                {
                    "code": r["FONKODU"],
                    "name": r["FONUNVAN"],
                    "netInflow": _safe(r["net_giris_tl"]),
                    "netInflow_fmt": fmt_money(r["net_giris_tl"]),
                }
                for _, r in top10.iterrows()
            ],
            "universe": [
                {
                    "code": r["FONKODU"],
                    "name": r["FONUNVAN"],
                    "category": r["ana_kategori"] or "Diğer",
                    "netInflow": _safe(r["netInflow"]),
                    "netInflow_fmt": fmt_money(r["netInflow"]),
                    "perfYTD": _safe(r["perfYTD"]),
                }
                for _, r in universe.iterrows()
            ],
        },
        os.path.join(OUTPUT_DIR, "macro.json"),
    )


def _build_flow(df: pd.DataFrame, meta: dict):
    """flow.json — Sankey akış haritası."""
    # Son 30 gün varsayılan; tüm kategoriler
    recent = df[df["tarih"] >= df["tarih"].max() - pd.Timedelta(days=30)]
    flow = recent.groupby("ana_kategori")["net_giris_tl"].sum().reset_index()
    flow = flow[flow["net_giris_tl"].abs() > 1000]

    INFLOW_NODE = "Sermaye Girişi"
    OUTFLOW_NODE = "Sermaye Çıkışı"
    cats = flow["ana_kategori"].tolist()
    all_names = [INFLOW_NODE, OUTFLOW_NODE] + cats
    idx = {n: i for i, n in enumerate(all_names)}

    # AUM per category (cumulative)
    aum = df.groupby("ana_kategori")["net_giris_tl"].sum().to_dict()
    nodes = [{"name": n, "aum": _safe(aum.get(n, 0))} for n in all_names]
    links = []
    for _, row in flow.iterrows():
        val = float(row["net_giris_tl"])
        cat = row["ana_kategori"]
        cat_aum = float(aum.get(cat, 0))
        if val > 0:
            links.append({"source": idx[INFLOW_NODE], "target": idx[cat],
                          "value": val, "type": "inflow", "cat_aum": cat_aum})
        elif val < 0:
            links.append({"source": idx[cat], "target": idx[OUTFLOW_NODE],
                          "value": abs(val), "type": "outflow", "cat_aum": cat_aum})

    # Also provide per-period slices (7D, 30D, 90D, YTD, ALL)
    slices = {}
    today = df["tarih"].max()
    year_start = pd.Timestamp(today.year, 1, 1)
    periods = {
        "7D": today - pd.Timedelta(days=7),
        "30D": today - pd.Timedelta(days=30),
        "90D": today - pd.Timedelta(days=90),
        "YTD": year_start,
        "ALL": df["tarih"].min(),
    }
    for label, start in periods.items():
        s = df[df["tarih"] >= start]
        cat_flows = s.groupby("ana_kategori")["net_giris_tl"].sum()
        slices[label] = {
            k: _safe(v) for k, v in cat_flows.items()
        }

    _jdump(
        {"meta": meta, "nodes": nodes, "links": links, "slices": slices},
        os.path.join(OUTPUT_DIR, "flow.json"),
    )


def _build_money_pie(df: pd.DataFrame, meta: dict):
    """money_pie.json — AUM dağılımı pasta grafiği."""
    # Son günün verisi = toplam yönetilen varlık tahmini
    last_date = df["tarih"].max()
    latest = df[df["tarih"] == last_date]

    # Her kategorinin toplam AUM'u (pay sayısı × fiyat)
    if "TEDPAYSAYISI" not in df.columns:
        # Parquet'te TEDPAYSAYISI yoksa net_giris birikimi ile proxy
        cat_aum = (
            df.groupby("ana_kategori")["net_giris_tl"]
            .sum()
            .abs()
            .reset_index()
            .rename(columns={"net_giris_tl": "aum"})
        )
    else:
        latest["aum"] = latest["TEDPAYSAYISI"] * latest["FIYAT"]
        cat_aum = (
            latest.groupby("ana_kategori")["aum"]
            .sum()
            .reset_index()
        )

    total = cat_aum["aum"].sum()
    cat_aum["pct"] = (cat_aum["aum"] / total * 100).round(2)
    cat_aum = cat_aum.sort_values("aum", ascending=False)

    # Historical monthly snapshot for donut trend
    df["month"] = df["tarih"].dt.to_period("M")
    monthly = (
        df.groupby(["month", "ana_kategori"])["net_giris_tl"]
        .sum()
        .reset_index()
    )
    monthly["month"] = monthly["month"].astype(str)

    _jdump(
        {
            "meta": meta,
            "total_aum": _safe(total),
            "total_aum_fmt": fmt_money(total),
            "breakdown": [
                {
                    "category": r["ana_kategori"],
                    "aum": _safe(r["aum"]),
                    "aum_fmt": fmt_money(r["aum"]),
                    "pct": _safe(r["pct"]),
                }
                for _, r in cat_aum.iterrows()
            ],
            "monthly_flows": [
                {
                    "month": r["month"],
                    "category": r["ana_kategori"],
                    "flow": _safe(r["net_giris_tl"]),
                }
                for _, r in monthly.iterrows()
            ],
        },
        os.path.join(OUTPUT_DIR, "money_pie.json"),
    )


def _build_by_type(df: pd.DataFrame, meta: dict):
    """by_type.json — Kategori karşılaştırma (bar + line per type)."""
    today = df["tarih"].max()

    periods = {
        "7D": today - pd.Timedelta(days=7),
        "30D": today - pd.Timedelta(days=30),
        "90D": today - pd.Timedelta(days=90),
        "YTD": pd.Timestamp(today.year, 1, 1),
        "ALL": df["tarih"].min(),
    }

    comparison = []
    for label, start in periods.items():
        s = df[df["tarih"] >= start]
        grp = s.groupby("ana_kategori").agg(
            inflow=("net_giris_tl", "sum"),
            fund_count=("FONKODU", "nunique"),
            first_price=("FIYAT", "first"),
            last_price=("FIYAT", "last"),
        ).reset_index()
        grp["perf"] = (
            (grp["last_price"] - grp["first_price"]) / grp["first_price"]
        ).replace([np.inf, -np.inf], np.nan).fillna(0)

        comparison.append({
            "period": label,
            "categories": [
                {
                    "category": r["ana_kategori"],
                    "inflow": _safe(r["inflow"]),
                    "inflow_fmt": fmt_money(r["inflow"]),
                    "fund_count": int(r["fund_count"]),
                    "perf": _safe(r["perf"]),
                }
                for _, r in grp.sort_values("inflow", ascending=False).iterrows()
            ],
        })

    # Weekly heatmap: category × week → net flow
    df["week"] = df["tarih"].dt.to_period("W").astype(str)
    heatmap_raw = (
        df.groupby(["week", "ana_kategori"])["net_giris_tl"]
        .sum()
        .reset_index()
        .tail(200)  # last ~20 weeks × 10 categories
    )

    _jdump(
        {
            "meta": meta,
            "comparison": comparison,
            "heatmap": [
                {
                    "week": r["week"],
                    "category": r["ana_kategori"],
                    "flow": _safe(r["net_giris_tl"]),
                }
                for _, r in heatmap_raw.iterrows()
            ],
        },
        os.path.join(OUTPUT_DIR, "by_type.json"),
    )


def _build_fund_index(df: pd.DataFrame, meta: dict):
    """fund_index.json — Drilldown autocomplete + per-fund summary."""
    summary = (
        df.groupby(["FONKODU", "FONUNVAN", "ana_kategori"], dropna=False)
        .agg(
            total_inflow=("net_giris_tl", "sum"),
            first_price=("FIYAT", "first"),
            last_price=("FIYAT", "last"),
            data_start=("tarih", "min"),
            data_end=("tarih", "max"),
        )
        .reset_index()
    )
    summary["perf_all"] = (
        (summary["last_price"] - summary["first_price"]) / summary["first_price"]
    ).replace([np.inf, -np.inf], np.nan).fillna(0)
    summary["data_start"] = summary["data_start"].dt.strftime("%Y-%m-%d")
    summary["data_end"] = summary["data_end"].dt.strftime("%Y-%m-%d")

    _jdump(
        {
            "meta": meta,
            "funds": [
                {
                    "code": r["FONKODU"],
                    "name": r["FONUNVAN"],
                    "category": r["ana_kategori"] or "Diğer",
                    "total_inflow": _safe(r["total_inflow"]),
                    "perf_all": _safe(r["perf_all"]),
                    "last_price": _safe(r["last_price"]),
                    "data_start": r["data_start"],
                    "data_end": r["data_end"],
                }
                for _, r in summary.sort_values("total_inflow", ascending=False).iterrows()
            ],
        },
        os.path.join(OUTPUT_DIR, "fund_index.json"),
    )


if __name__ == "__main__":
    build_all()
