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


def get_filtered_df(start: str = "", end: str = "", categories: str = ""):
    f_df = df.copy()
    if f_df.empty:
        return f_df

    if categories:
        cat_list = [c.strip() for c in categories.split(",")]
        f_df = f_df[f_df["ana_kategori"].isin(cat_list)]

    # STRICT ABSOLUTE DATES
    if start and start != "undefined":
        f_df = f_df[f_df["tarih"] >= pd.to_datetime(start)]
    if end and end != "undefined":
        f_df = f_df[f_df["tarih"] <= pd.to_datetime(end)]

    return f_df

# --- 1. ENDPOINT: Makro Pazar KPI'ları ---


@app.get("/api/macro/kpi")
def get_macro_kpi(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"total_net_inflow": 0, "unique_funds": 0, "top_fund": "-"}

    total_inflow = float(f_df["net_giris_tl"].sum())
    unique_funds = int(f_df["FONKODU"].nunique())

    top_fund_series = f_df.groupby("FONKODU")["net_giris_tl"].sum()
    top_fund_code = top_fund_series.idxmax() if not top_fund_series.empty else "-"

    return {"total_net_inflow": total_inflow, "unique_funds": unique_funds, "top_fund": top_fund_code}

# --- 2. ENDPOINT: Zaman İçindeki Akış (Trend) ---


@app.get("/api/macro/trend")
def get_macro_trend(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
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
def get_macro_top10(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []

    top = f_df.groupby(["FONKODU", "FONUNVAN"])[
        "net_giris_tl"].sum().reset_index()
    top = top.sort_values("net_giris_tl", ascending=False).head(10)
    return top.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "net_giris_tl": "netInflow"}).to_dict(orient="records")

# --- 4. ENDPOINT: Tüm Fon Evreni ---


@app.get("/api/macro/universe")
def get_macro_universe(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
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
def get_fund_details(fund_code: str, start: str = "", end: str = ""):
    f_df = df[df["FONKODU"] == fund_code].sort_values("tarih")
    if f_df.empty:
        return {"error": "Fon bulunamadı"}

    # MUTLAK TARİH FİLTRESİNİ UYGULA
    if start and start != "undefined":
        f_df = f_df[f_df["tarih"] >= pd.to_datetime(start)]
    if end and end != "undefined":
        f_df = f_df[f_df["tarih"] <= pd.to_datetime(end)]

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

# --- 7. ENDPOINT: Sankey Akış Verisi ---


@app.get("/api/macro/flow")
def get_macro_flow(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}

    # 1. Kaynak (Kategori) -> Hedef (Fon Kodu) bazlı grupla
    flow_df = f_df.groupby(["ana_kategori", "FONKODU"])[
        "net_giris_tl"].sum().reset_index()

    # 2. Sadece pozitif akışları (girişleri) al - Sankey negatif değer sevmez
    flow_df = flow_df[flow_df["net_giris_tl"] > 0]

    # 3. Görsel karmaşayı önlemek için en büyük 20 akışı al
    flow_df = flow_df.sort_values("net_giris_tl", ascending=False).head(20)

    # 4. Sankey Formatı Hazırlama (Nodes & Links)
    nodes = []
    links = []

    # Benzersiz isimler listesi (Kategoriler + Fonlar)
    all_names = pd.concat(
        [flow_df["ana_kategori"], flow_df["FONKODU"]]).unique().tolist()
    nodes = [{"name": name} for name in all_names]

    # İsimlerin index'lerini bulup linkleri oluştur
    name_to_idx = {name: i for i, name in enumerate(all_names)}

    for _, row in flow_df.iterrows():
        links.append({
            "source": name_to_idx[row["ana_kategori"]],
            "target": name_to_idx[row["FONKODU"]],
            "value": round(float(row["net_giris_tl"]), 2)
        })

    return {"nodes": nodes, "links": links}


# --- 8. ENDPOINT: Makro Akış (Sistem İçi vs Sistem Dışı Sankey) ---
@app.get("/api/macro/flow-sankey")
def get_macro_flow_sankey(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}

    # 1. Seçili Dönem İçi Akış (Net Flow)
    flow_df = f_df.groupby("ana_kategori")["net_giris_tl"].sum().reset_index()
    flow_df = flow_df[flow_df["net_giris_tl"].abs() > 1000]

    if flow_df.empty:
        return {"nodes": [], "links": []}

    # 2. TOPLAM HACİM (AUM) HESAPLAMASI: Başlangıçtan 'end' tarihine kadar kümülatif
    end_dt = pd.to_datetime(
        end) if end and end != "undefined" else df["tarih"].max()
    cat_list = flow_df["ana_kategori"].tolist()

    aum_df = df[(df["ana_kategori"].isin(cat_list)) & (df["tarih"] <= end_dt)]
    aum_dict = aum_df.groupby("ana_kategori")["net_giris_tl"].sum().to_dict()

    INFLOW_NODE = "Sermaye Girişi"
    OUTFLOW_NODE = "Sermaye Çıkışı"

    # Node'lara AUM bilgisini ekliyoruz (Giriş/Çıkış ana kütlelerine 0 veriyoruz)
    all_names = [INFLOW_NODE, OUTFLOW_NODE] + cat_list
    nodes = [{"name": name, "aum": aum_dict.get(
        name, 0)} for name in all_names]
    name_to_idx = {name: i for i, name in enumerate(all_names)}

    links = []
    for _, row in flow_df.iterrows():
        val = float(row["net_giris_tl"])
        cat = row["ana_kategori"]
        cat_aum = float(aum_dict.get(cat, 0))  # O kategorinin Toplam Hacmi

        if val > 0:
            links.append({
                "source": name_to_idx[INFLOW_NODE],
                "target": name_to_idx[cat],
                "value": val,
                "type": "inflow",
                "cat_aum": cat_aum  # Link'in içine gömüyoruz
            })
        elif val < 0:
            links.append({
                "source": name_to_idx[cat],
                "target": name_to_idx[OUTFLOW_NODE],
                "value": abs(val),
                "type": "outflow",
                "cat_aum": cat_aum  # Link'in içine gömüyoruz
            })

    return {"nodes": nodes, "links": links}
