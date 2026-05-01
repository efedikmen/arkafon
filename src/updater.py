import os
import glob
import time
import pandas as pd
from datetime import date, datetime, timedelta
from tefas_client import Tefas
from src.config import RAW_DATA_DIR


def get_missing_dates(start_date=date(2025, 9, 27)):
    """Klasörde eksik olan tarihleri (boş günleri) bulur."""

    files = glob.glob(os.path.join(RAW_DATA_DIR, "tefas_data_*.parquet"))

    existing_dates = set()

    for f in files:
        try:
            date_str = os.path.basename(f).replace(
                "tefas_data_", "").replace(".parquet", "")
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            existing_dates.add(parsed_date)
        except:
            pass

    # Bugünün tarihi
    today = date.today()

    # Tüm olması gereken tarihleri oluştur
    all_dates = set()
    current = start_date
    while current <= today:
        all_dates.add(current)
        current += timedelta(days=1)

    # Eksik günleri bul
    missing_dates = sorted(all_dates - existing_dates)

    return missing_dates


def fetch_missing_data():
    missing_dates = get_missing_dates()
    if not missing_dates:
        print("✅ Tüm veriler zaten güncel! İndirilecek yeni gün yok.")
        return

    start_date = missing_dates[0]
    end_date = missing_dates[-1]

    if start_date > end_date:
        print("✅ Tüm veriler zaten güncel! İndirilecek yeni gün yok.")
        return

    print(
        f"📡 Kaldığımız yerden devam ediliyor: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")

    # Blokları 10 güne düşürdük (Sunucuyu yormamak için)
    chunk_size = timedelta(days=10)
    current_start = start_date

    with Tefas() as tefas:
        while current_start <= end_date:
            current_end = current_start + chunk_size
            if current_end > end_date:
                current_end = end_date

            print(
                f"\n⏳ İndiriliyor: {current_start.strftime('%d.%m.%Y')} - {current_end.strftime('%d.%m.%Y')}...")

            try:
                all_funds_data = tefas.fetch(
                    start_date=current_start,
                    end_date=current_end
                )

                if all_funds_data:
                    flattened_data = []
                    for code, fund_obj in all_funds_data.items():
                        for history in fund_obj.history:
                            flattened_data.append({
                                "tarih": history.date,
                                "FONKODU": code,
                                "FONUNVAN": fund_obj.title,
                                "FIYAT": history.price,
                                "TEDPAYSAYISI": history.number_of_shares
                            })

                    if flattened_data:
                        master_update_df = pd.DataFrame(flattened_data)
                        dates_found = master_update_df["tarih"].unique()

                        for c_date in dates_found:
                            date_str = pd.to_datetime(
                                c_date).strftime("%d.%m.%Y")
                            file_path = os.path.join(
                                RAW_DATA_DIR, f"tefas_data_{date_str}.parquet")

                            if not os.path.exists(file_path):
                                daily_df = master_update_df[master_update_df["tarih"] == c_date].copy(
                                )
                                daily_df.drop(
                                    columns=["tarih"]).to_parquet(file_path)
                                print(f"  ✅ {date_str} kaydedildi.")
                else:
                    print("  ⚠️ Bu aralıkta veri bulunamadı (Tatil dönemi olabilir).")

            except Exception as e:
                print(
                    f"  ❌ TEFAS sunucusu yanıt vermedi ({type(e).__name__}). Hız limiti aşılmış olabilir.")
                print(
                    "  🛑 İşlem durduruluyor. Lütfen 5-10 dakika bekleyip kodu tekrar çalıştırın.")
                break  # Patlamak yerine güvenli çıkış yap

            # Bir sonraki bloğa geç
            current_start = current_end + timedelta(days=1)

            # TEFAS'a nefes aldır (5 Saniye Mola)
            time.sleep(5)

    print("\n✨ İndirme Oturumu Tamamlandı.")


if __name__ == "__main__":
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    fetch_missing_data()
