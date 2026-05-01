import os
import re
import pandas as pd
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR, MASTER_DATA_PATH, FUND_PATTERN


def build_master_data():
    print("🚀 Arkafon veri işleme motoru başlatılıyor...")

    all_files = sorted([f for f in os.listdir(
        RAW_DATA_DIR) if f.endswith(".parquet")])

    if not all_files:
        print("❌ Hata: data/raw/ klasöründe hiç parquet dosyası bulunamadı!")
        return

    all_daily_flows = []
    prev_df = None

    for file_name in all_files:
        try:
            date_str = file_name.split('_')[-1].replace('.parquet', '')
            current_date = pd.to_datetime(date_str, format="%d.%m.%Y")
        except Exception:
            continue

        file_path = os.path.join(RAW_DATA_DIR, file_name)

        try:
            df = pd.read_parquet(file_path)
        except Exception:
            print(f"⚠️ Bozuk dosya okunamadı, atlanıyor: {file_name}")
            continue

        # --- KRİTİK DÜZELTME: Kolonlardaki gizli boşlukları temizle ve hepsini BÜYÜK harf yap ---
        df.columns = df.columns.str.strip().str.upper()

        # Eğer bu dosyada aradığımız hayati kolonlar yoksa, hiç uğraşma diğer güne geç
        if not all(col in df.columns for col in ["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]):
            print(f"⚠️ Eksik kolonlu yapı, atlanıyor: {file_name}")
            continue

        # Filtreleme
        df_filtered = df[df["FONUNVAN"].str.contains(
            FUND_PATTERN, flags=re.IGNORECASE, regex=True)].copy()
        df_filtered = df_filtered[["FONKODU",
                                   "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]]

        if prev_df is not None:
            merged = pd.merge(df_filtered, prev_df, on="FONKODU",
                              how="left", suffixes=("", "_prev"))
            merged["net_giris_tl"] = (
                merged["TEDPAYSAYISI"] - merged["TEDPAYSAYISI_prev"].fillna(0)) * merged["FIYAT"]

            merged["tarih"] = current_date
            final_df = merged[["tarih", "FONKODU", "FONUNVAN", "net_giris_tl"]]

            all_daily_flows.append(final_df)

        prev_df = df_filtered[["FONKODU", "TEDPAYSAYISI"]].copy()

    if all_daily_flows:
        print("📦 Parçalar birleştiriliyor...")
        master_df = pd.concat(all_daily_flows, ignore_index=True)
        os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
        master_df.to_parquet(MASTER_DATA_PATH)
        print(
            f"✅ Başarılı! {len(master_df)} satırlık master veri oluşturuldu.")
        print(f"📍 Dosya Konumu: {MASTER_DATA_PATH}")
    else:
        print("⚠️ Hesaplanacak geçerli veri bulunamadı.")


if __name__ == "__main__":
    build_master_data()
