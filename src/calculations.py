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


def filter_data(df, period_string, selected_categories):
    """Kullanıcının seçtiği tarih aralığına ve fon türüne göre DataFrame'i filtreler."""
    if df.empty:
        return df

    # 1. Kategori Filtresi (Regex ile çalışır)
    # Eğer kullanıcı "Döviz" ve "Altın" seçtiyse, ikisini arayacak bir regex stringi oluştur: "DÖVİZ|ALTIN"
    if selected_categories:
        search_pattern = "|".join([cat.upper() for cat in selected_categories])
        df = df[df["FONUNVAN"].str.contains(
            search_pattern, regex=True, na=False)]

    # 2. Tarih Filtresi
    max_date = df["tarih"].max()  # Verisetindeki en güncel tarih

    if period_string == "Bugün":
        df = df[df["tarih"] == max_date]
    elif period_string == "Son 7 Gün":
        df = df[df["tarih"] >= (max_date - pd.Timedelta(days=7))]
    elif period_string == "Son 30 Gün":
        df = df[df["tarih"] >= (max_date - pd.Timedelta(days=30))]
    elif period_string == "Yılbaşından Bugüne":
        start_of_year = pd.Timestamp(year=max_date.year, month=1, day=1)
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
