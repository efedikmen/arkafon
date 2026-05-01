import pandas as pd
import streamlit as st
import os
from src.config import MASTER_DATA_PATH


@st.cache_data
def load_data():
    """
    İşlenmiş Parquet dosyasını RAM'e alır. 
    @st.cache_data dekoratörü sayesinde bu işlem uygulama açıldığında sadece 1 kez yapılır.
    """
    if not os.path.exists(MASTER_DATA_PATH):
        return pd.DataFrame()
    return pd.read_parquet(MASTER_DATA_PATH)


def filter_data(df, period_string, selected_main, selected_sub):
    if df.empty:
        return df

    # 1. Kategori Filtresi (Doğrudan yeni kolonlardan okuyoruz)
    if selected_main:
        # Eğer Döviz seçildiyse ama alt kategori de belirtildiyse ikisini de dikkate al
        if "Döviz" in selected_main and selected_sub:
            df = df[
                (df["ana_kategori"].isin([m for m in selected_main if m != "Döviz"])) |
                ((df["ana_kategori"] == "Döviz") &
                 (df["alt_kategori"].isin(selected_sub)))
            ]
        else:
            df = df[df["ana_kategori"].isin(selected_main)]

    # 2. Tarih Filtresi
    max_date = df["tarih"].max()

    if period_string == "Bugün":
        df = df[df["tarih"] == max_date]
    elif period_string == "Son 7 Gün":
        df = df[df["tarih"] >= (max_date - pd.Timedelta(days=7))]
    elif period_string == "Son 30 Gün":
        df = df[df["tarih"] >= (max_date - pd.Timedelta(days=30))]
    elif period_string == "Yılbaşından Bugüne":
        start_of_year = pd.Timestamp(year=int(max_date.year), month=1, day=1)
        df = df[df["tarih"] >= start_of_year]

    return df


def get_kpi_metrics(df):
    """Üst barda gösterilecek özet rakamları hesaplar."""
    if df.empty:
        return 0, "-", 0

    total_inflow = df["net_giris_tl"].sum()

    # En çok net giriş alan fonu bul
    fund_flows = df.groupby("FONUNVAN")["net_giris_tl"].sum()
    top_fund = fund_flows.idxmax() if not fund_flows.empty else "-"

    # Benzersiz fon sayısı
    unique_funds = df["FONKODU"].nunique()

    return total_inflow, top_fund, unique_funds


def get_top_funds(df, top_n=10):
    """Liderlik tablosu (Bar Chart) için en iyi fonları getirir."""
    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby(["FONKODU", "FONUNVAN"])[
        "net_giris_tl"].sum().reset_index()
    # Büyükten küçüğe sırala
    sorted_funds = grouped.sort_values(
        by="net_giris_tl", ascending=False).head(top_n)
    return sorted_funds


def get_trend_data(df):
    """Zaman içindeki kümülatif net girişi kategoriler bazında ve TEFAS Toplam olarak hesaplar."""
    if df.empty:
        return pd.DataFrame()

    # 1. Kategori bazında kümülatif hesaplama
    daily_grouped = df.groupby(["tarih", "ana_kategori"])[
        "net_giris_tl"].sum().reset_index()
    daily_grouped = daily_grouped.sort_values(by="tarih")
    daily_grouped["kumulatif_giris"] = daily_grouped.groupby("ana_kategori")[
        "net_giris_tl"].cumsum()

    # 2. TEFAS Genel Toplam hesaplama (Sistemdeki tüm seçili verinin toplamı)
    total_grouped = df.groupby(["tarih"])["net_giris_tl"].sum().reset_index()
    total_grouped = total_grouped.sort_values(by="tarih")
    total_grouped["kumulatif_giris"] = total_grouped["net_giris_tl"].cumsum()
    # Ayrı bir çizgi olarak ekliyoruz
    total_grouped["ana_kategori"] = "TEFAS TOPLAM"

    # 3. İkisini birleştir
    final_trend = pd.concat([daily_grouped, total_grouped], ignore_index=True)

    return final_trend
