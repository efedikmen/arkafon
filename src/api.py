"""
Arkafon API — Slim Edition
- No auth, no portfolio, no risk metrics
- Serves static JSON for pre-rendered pages
- Only live endpoint: /api/fund/{code} for drilldown search
"""
import os
import json
import threading
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import MASTER_DATA_PATH

app = FastAPI(title="Arkafon API — Slim")

_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8080,http://127.0.0.1:8080,"
    "https://arkafon.com,https://www.arkafon.com",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Master parquet with hot-reload on mtime change ────────────────────────
_DF_LOCK = threading.RLock()
_DF_MTIME: float | None = None
df: pd.DataFrame = pd.DataFrame()


def _reload_master(force: bool = False) -> bool:
    global df, _DF_MTIME
    if not os.path.exists(MASTER_DATA_PATH):
        return False
    mtime = os.path.getmtime(MASTER_DATA_PATH)
    with _DF_LOCK:
        if not force and _DF_MTIME == mtime:
            return False
        df = pd.read_parquet(MASTER_DATA_PATH)
        _DF_MTIME = mtime
        return True


@app.on_event("startup")
def _initial_load():
    _reload_master(force=True)


# ── Fund search + detail (only live endpoint needed) ─────────────────────

@app.get("/api/fund/list")
def fund_list(q: str = "", page: int = 1, page_size: int = 50):
    _reload_master()
    if df.empty:
        return {"items": [], "total": 0}
    funds = df[["FONKODU", "FONUNVAN"]].drop_duplicates().dropna()
    if q:
        ql = q.strip().lower()
        mask = (
            funds["FONKODU"].str.lower().str.contains(ql, na=False)
            | funds["FONUNVAN"].str.lower().str.contains(ql, na=False)
        )
        funds = funds[mask]
    total = int(len(funds))
    start = (max(1, page) - 1) * page_size
    page_df = funds.iloc[start: start + page_size]
    return {
        "items": page_df.rename(
            columns={"FONKODU": "code", "FONUNVAN": "name"}
        ).to_dict(orient="records"),
        "total": total,
    }


@app.get("/api/fund/{fund_code}")
def fund_detail(fund_code: str, start: str = "", end: str = ""):
    _reload_master()
    f = df[df["FONKODU"] == fund_code].sort_values("tarih")
    if f.empty:
        raise HTTPException(404, "fund_not_found")
    if start:
        f = f[f["tarih"] >= pd.to_datetime(start)]
    if end:
        f = f[f["tarih"] <= pd.to_datetime(end)]
    if f.empty:
        raise HTTPException(404, "no_data_for_range")

    inflow = float(f["net_giris_tl"].sum())
    s_price = float(f["FIYAT"].iloc[0])
    e_price = float(f["FIYAT"].iloc[-1])
    perf = (e_price - s_price) / s_price if s_price > 0 else 0

    chart = (
        f[["tarih", "FIYAT", "net_giris_tl"]]
        .copy()
        .assign(tarih=lambda x: x["tarih"].dt.strftime("%Y-%m-%d"))
        .rename(columns={"tarih": "date", "FIYAT": "price", "net_giris_tl": "flow"})
        .to_dict(orient="records")
    )
    return {
        "code": fund_code,
        "name": f["FONUNVAN"].iloc[0],
        "category": f["ana_kategori"].iloc[0] if "ana_kategori" in f.columns else None,
        "kpi": {"inflow": inflow, "perf": perf, "latestPrice": e_price},
        "chart": chart,
    }


# ── Serve pre-built static JSON ───────────────────────────────────────────
# The export_json.py script writes to public/data/*.json after each cron run.
# Vite copies public/ into dist/ at build time, so in dev we serve from here.
# In production (nginx / Cloudflare Pages) these files are served as-is.

# Optional: mount for local dev only
if os.path.exists("public/data"):
    app.mount("/data", StaticFiles(directory="public/data"), name="data")
