"""
updater.py — Günlük Cron Job Entry Point
Çalışma zamanı: Her gün 18:30 (TEFAS kapanış sonrası, iş günleri)

crontab:
  30 18 * * 1-5 cd /srv/arkafon && python src/updater.py >> logs/cron.log 2>&1
"""
import os
import glob
import time
import subprocess
import pandas as pd
from datetime import date, datetime
from tefas_client import Tefas
from src.config import RAW_DATA_DIR


def fetch_daily_data():
    print(f"🤖 Arkafon Veri Botu — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    files = glob.glob(os.path.join(RAW_DATA_DIR, "tefas_data_*.parquet"))
    existing_dates = set()
    for f in files:
        try:
            date_str = os.path.basename(f).replace("tefas_data_", "").replace(".parquet", "")
            existing_dates.add(datetime.strptime(date_str, "%d.%m.%Y").date())
        except Exception:
            pass

    start_date = date(2020, 8, 24)  # TEFAS açılış tarihi
    end_date = date.today()
    expected_dates = set(pd.bdate_range(start=start_date, end=end_date).date)
    missing_dates = sorted(expected_dates - existing_dates)

    if not missing_dates:
        print("✅ Tüm günler güncel, yeni veri yok.")
        return False

    print(f"🔍 Eksik/yeni gün: {len(missing_dates)}")

    with Tefas() as tefas:
        for missing_date in missing_dates:
            date_str = missing_date.strftime("%d.%m.%Y")
            file_path = os.path.join(RAW_DATA_DIR, f"tefas_data_{date_str}.parquet")
            print(f"⏳ {date_str} çekiliyor...")
            try:
                data = tefas.fetch(start_date=missing_date, end_date=missing_date)
                if data:
                    flattened = [
                        {
                            "FONKODU": code,
                            "FONUNVAN": fund_obj.title,
                            "FIYAT": h.price,
                            "TEDPAYSAYISI": h.number_of_shares,
                        }
                        for code, fund_obj in data.items()
                        for h in fund_obj.history
                    ]
                    if flattened:
                        pd.DataFrame(flattened).to_parquet(file_path)
                        print(f"  ✅ {date_str} kaydedildi ({len(flattened)} kayıt)")
                else:
                    # Resmi tatil — hayalet dosya
                    pd.DataFrame(
                        columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]
                    ).to_parquet(file_path)
                    print(f"  ⚠️  {date_str} boş (tatil?), hayalet oluşturuldu")
            except Exception as e:
                print(f"  ❌ {date_str} hata: {type(e).__name__}: {e}")
            time.sleep(3)

    return True


def run_etl():
    print("🔄 ETL (data_loader) başlatılıyor...")
    subprocess.run(["python", "-m", "src.data_loader"], check=True)
    print("✅ ETL tamamlandı")


def run_export():
    print("📦 JSON export başlatılıyor...")
    subprocess.run(["python", "-m", "src.export_json"], check=True)
    print("✅ JSON export tamamlandı")


if __name__ == "__main__":
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    is_updated = fetch_daily_data()

    if is_updated:
        try:
            run_etl()
            run_export()
            print("🚀 Pipeline tamamlandı. Site güncellendi!")
        except subprocess.CalledProcessError as e:
            print(f"❌ Pipeline hatası: {e}")
    else:
        print("ℹ️  Güncellenecek yeni veri yok, çıkılıyor.")
