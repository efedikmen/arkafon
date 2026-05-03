from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import os
from datetime import timedelta
from src.config import MASTER_DATA_PATH

app = FastAPI(title="Arkafon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Veri yükleniyor...")
if os.path.exists(MASTER_DATA_PATH):
    df = pd.read_parquet(MASTER_DATA_PATH)
else:
    df = pd.DataFrame()

# --- MERKEZİ FİLTRE MOTORU ---


def get_filtered_df(days: str = "ALL", categories: str = ""):
    f_df = df.copy()
    if f_df.empty:
        return f_df

    # 1. Kategori Filtresi
    if categories:
        cat_list = [c.strip() for c in categories.split(",")]
        f_df = f_df[f_df["ana_kategori"].isin(cat_list)]

    # 2. Tarih Filtresi
    if days and days.upper() != "ALL":
        try:
            d = int(days)
            max_date = f_df["tarih"].max()
            start_date = max_date - timedelta(days=d)
            f_df = f_df[f_df["tarih"] >= start_date]
        except ValueError:
            pass  # Eğer çevrilemez bir değer gelirse tarihi filtreleme

    return f_df

# --- 1. ENDPOINT: Makro Pazar KPI'ları ---


@app.get("/api/macro/kpi")
def get_macro_kpi(days: str = "ALL", categories: str = ""):
    f_df = get_filtered_df(days, categories)
    if f_df.empty:
        return {"total_net_inflow": 0, "unique_funds": 0, "top_fund": "-"}

    total_inflow = float(f_df["net_giris_tl"].sum())
    unique_funds = int(f_df["FONKODU"].nunique())

    top_fund_series = f_df.groupby("FONKODU")["net_giris_tl"].sum()
    top_fund_code = top_fund_series.idxmax() if not top_fund_series.empty else "-"

    return {"total_net_inflow": total_inflow, "unique_funds": unique_funds, "top_fund": top_fund_code}

# --- 2. ENDPOINT: Zaman İçindeki Akış (Trend) ---


@app.get("/api/macro/trend")
def get_macro_trend(days: str = "ALL", categories: str = ""):
    f_df = get_filtered_df(days, categories)
    if f_df.empty:
        return []

    trend = f_df.groupby("tarih")["net_giris_tl"].sum().reset_index()
    trend = trend.sort_values("tarih")
    trend["tarih"] = trend["tarih"].dt.strftime('%Y-%m-%d')
    # Kümülatif hesabı filtreli verinin başından itibaren sıfırdan başlasın
    trend["kumulatif_giris"] = trend["net_giris_tl"].cumsum()

    return trend.to_dict(orient="records")

# --- 3. ENDPOINT: Top 10 Fon ---


@app.get("/api/macro/top10")
def get_macro_top10(days: str = "ALL", categories: str = ""):
    f_df = get_filtered_df(days, categories)
    if f_df.empty:
        return []

    top = f_df.groupby(["FONKODU", "FONUNVAN"])[
        "net_giris_tl"].sum().reset_index()
    top = top.sort_values("net_giris_tl", ascending=False).head(10)
    return top.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "net_giris_tl": "netInflow"}).to_dict(orient="records")

# --- 4. ENDPOINT: Tüm Fon Evreni ---


@app.get("/api/macro/universe")
def get_macro_universe(days: str = "ALL", categories: str = ""):
    f_df = get_filtered_df(days, categories)
    if f_df.empty:
        return []

    grouped = f_df.groupby(["FONKODU", "FONUNVAN", "ana_kategori"], dropna=False).agg(
        netInflow=('net_giris_tl', 'sum'),
        first_price=('FIYAT', 'first'),
        last_price=('FIYAT', 'last')
    ).reset_index()

    grouped['perfYTD'] = (grouped['last_price'] -
                          grouped['first_price']) / grouped['first_price']
    grouped['perfYTD'] = grouped['perfYTD'].replace(
        [np.inf, -np.inf], np.nan).fillna(0)
    grouped['ana_kategori'] = grouped['ana_kategori'].fillna("Diğer")
    grouped = grouped.sort_values("netInflow", ascending=False).head(25)

    return grouped.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "ana_kategori": "category"}).to_dict(orient="records")

# --- 5. ENDPOINT: Tekil Fon Arama Listesi (Drill-down Sayfası İçin) ---


@app.get("/api/fund/list")
def get_fund_list():
    if df.empty:
        return []
    funds = df[["FONKODU", "FONUNVAN"]].drop_duplicates().dropna()
    return funds.rename(columns={"FONKODU": "code", "FONUNVAN": "name"}).to_dict(orient="records")


# --- 6. ENDPOINT: Tekil Fon Detayları (Drill-down Sayfası İçin) ---


@app.get("/api/fund/{fund_code}")
def get_fund_details(fund_code: str, days: str = "ALL"):
    f_df = df[df["FONKODU"] == fund_code].sort_values("tarih")
    if f_df.empty:
        return {"error": "Fon bulunamadı"}

    # TARİH FİLTRESİNİ UYGULA
    if days and days.upper() != "ALL":
        try:
            d = int(days)
            max_date = f_df["tarih"].max()
            start_date = max_date - timedelta(days=d)
            f_df = f_df[f_df["tarih"] >= start_date]
        except ValueError:
            pass

    if f_df.empty:
        return {"error": "Seçilen tarih aralığında veri bulunamadı"}

    inflow = float(f_df["net_giris_tl"].sum())
    start_p = float(f_df["FIYAT"].iloc[0])
    end_p = float(f_df["FIYAT"].iloc[-1])
    perf = ((end_p - start_p) / start_p) if start_p > 0 else 0

    chart_data = f_df[["tarih", "FIYAT", "net_giris_tl"]].copy()
    chart_data["tarih"] = chart_data["tarih"].dt.strftime('%Y-%m-%d')

    return {
        "kpi": {"inflow": inflow, "perf": perf, "latestPrice": end_p},
        "chart": chart_data.rename(columns={"tarih": "date", "FIYAT": "price", "net_giris_tl": "flow"}).to_dict(orient="records")
    }
