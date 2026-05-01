import os
import pandas as pd
from src.config import RAW_DATA_DIR, PROCESSED_DATA_DIR, MASTER_DATA_PATH


def build_master_data():
    print("🚀 Bloomberg Terminal Standartlarında ETL Motoru Başlatılıyor...")

    all_files = sorted([f for f in os.listdir(
        RAW_DATA_DIR) if f.endswith(".parquet")])
    if not all_files:
        print("❌ Hata: data/raw/ klasöründe veri yok!")
        return

    all_dfs = []

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
            continue

        df.columns = df.columns.str.strip().str.upper()

        if not all(col in df.columns for col in ["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]):
            continue

        # Sadece temiz kolonları al ve listeye ekle
        df_filtered = df[["FONKODU", "FONUNVAN",
                          "FIYAT", "TEDPAYSAYISI"]].copy()
        df_filtered["FONKODU"] = df_filtered["FONKODU"].astype(
            str).str.strip()  # Boşluklardan kurtul
        df_filtered["tarih"] = current_date
        all_dfs.append(df_filtered)

    if not all_dfs:
        print("⚠️ Hesaplanacak geçerli veri bulunamadı.")
        return

    print("📦 Veriler birleştiriliyor (Vektörel Hesaplama)...")
    master_df = pd.concat(all_dfs, ignore_index=True)

    # 1. KRİTİK ADIM: Fon koduna ve tarihe göre kesin sıralama
    master_df = master_df.sort_values(by=["FONKODU", "tarih"])

    # 2. KRİTİK ADIM: Önceki günün payını yan kolona kaydır
    master_df["TEDPAYSAYISI_prev"] = master_df.groupby(
        "FONKODU")["TEDPAYSAYISI"].shift(1)

    # 3. GERÇEK NAKİT AKIŞI HESABI
    # Eğer previous NaN ise (verinin ilk günü), farkı 0 kabul et. Böylece Portföy büyüklüğü Inflow gibi görünmez!
    master_df["pay_farki"] = master_df["TEDPAYSAYISI"] - \
        master_df["TEDPAYSAYISI_prev"]
    master_df["pay_farki"] = master_df["pay_farki"].fillna(0)

    master_df["net_giris_tl"] = master_df["pay_farki"] * master_df["FIYAT"]

    # 4. Tasnifleme (Classifier)
    print("🔍 Fonlar SPK standartlarına göre tasnif ediliyor...")
    from src.classifier import classify_fund
    unique_funds = master_df[["FONKODU", "FONUNVAN"]].drop_duplicates()
    unique_funds[["ana_kategori", "alt_kategori"]] = pd.DataFrame(
        unique_funds["FONUNVAN"].apply(classify_fund).tolist(),
        index=unique_funds.index
    )

    master_df = master_df.merge(
        unique_funds[["FONKODU", "ana_kategori", "alt_kategori"]], on="FONKODU", how="left")

    # Final formatı
    final_cols = ["tarih", "FONKODU", "FONUNVAN", "FIYAT",
                  "net_giris_tl", "ana_kategori", "alt_kategori"]
    master_df = master_df[final_cols]

    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
    master_df.to_parquet(MASTER_DATA_PATH)
    print(
        f"✅ Başarılı! {len(master_df)} satırlık gerçek nakit akışı verisi oluşturuldu.")


if __name__ == "__main__":
    build_master_data()
