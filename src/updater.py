import os
import glob
import time
import subprocess
import pandas as pd
from datetime import date, datetime
from tefas_client import Tefas
from src.config import RAW_DATA_DIR


def fetch_daily_data():
    print("🤖 Arkafon Veri Botu (Self-Healer) Başlatılıyor...")

    # 1. Klasördeki mevcut tarihleri bul
    files = glob.glob(os.path.join(RAW_DATA_DIR, "tefas_data_*.parquet"))
    existing_dates = set()
    for f in files:
        try:
            date_str = os.path.basename(f).replace(
                "tefas_data_", "").replace(".parquet", "")
            existing_dates.add(datetime.strptime(date_str, "%d.%m.%Y").date())
        except:
            pass

    # 2. Olması gereken İŞ GÜNLERİNİ hesapla
    start_date = date(2026, 4, 30)  # Projemizin miladı
    # Bot 19:00'da çalıştığı için bugünün verisi gelmiş olur
    end_date = date.today()

    # Sadece iş günlerini alıyoruz (Hafta sonları elendi)
    expected_dates = set(pd.bdate_range(start=start_date, end=end_date).date)

    # 3. Gerçek delikleri tespit et (Beklenen İş Günleri - Klasördeki Günler)
    missing_dates = sorted(expected_dates - existing_dates)

    if not missing_dates:
        print("✅ Veritabanında hiçbir delik yok. Tüm günler güncel!")
        return False  # Yeni veri inmediğini belirt

    print(f"🔍 İndirilecek yeni/eksik iş günü sayısı: {len(missing_dates)}")

    # 4. Eksik günleri nokta atışı TEFAS'tan iste
    with Tefas() as tefas:
        for missing_date in missing_dates:
            date_str = missing_date.strftime("%d.%m.%Y")
            file_path = os.path.join(
                RAW_DATA_DIR, f"tefas_data_{date_str}.parquet")

            print(f"⏳ Çekiliyor: {date_str}...")
            try:
                data = tefas.fetch(start_date=missing_date,
                                   end_date=missing_date)

                if data:
                    flattened = []
                    for code, fund_obj in data.items():
                        for history in fund_obj.history:
                            flattened.append({
                                "tarih": history.date,
                                "FONKODU": code,
                                "FONUNVAN": fund_obj.title,
                                "FIYAT": history.price,
                                "TEDPAYSAYISI": history.number_of_shares
                            })

                    if flattened:
                        df = pd.DataFrame(flattened)
                        df.drop(columns=["tarih"]).to_parquet(file_path)
                        print(f"  ✅ {date_str} başarıyla kaydedildi.")
                else:
                    print(
                        f"  ⚠️ {date_str} boş döndü (Resmi tatil olabilir). Hayalet dosya oluşturuluyor...")
                    # Resmi tatilleri her seferinde tekrar sormamak için içi boş "hayalet" dosya
                    pd.DataFrame(
                        columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]).to_parquet(file_path)

            except Exception as e:
                print(f"  ❌ Hata: {date_str} çekilemedi ({type(e).__name__}).")

            # API'yi yormamak için kısa mola
            time.sleep(5)

    return True  # Yeni veri indiğini belirt


if __name__ == "__main__":
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    # 1. Yeni veya eksik verileri indir
    is_updated = fetch_daily_data()

    # 2. Eğer klasöre yeni bir dosya eklendiyse, Master Veriyi (ETL) tetikle
    if is_updated:
        print("🔄 Yeni veri tespit edildi, ETL (Data Loader) süreci başlatılıyor...")
        try:
            # İşletim sisteminde "python src/data_loader.py" komutunu çalıştırır
            subprocess.run(["python", "src/data_loader.py"], check=True)
            subprocess.run(["python", "src/market_data.py"], check=True)
            print("🚀 ETL tamamlandı. Arkafon API güncel veriyle hizmet vermeye hazır!")
        except subprocess.CalledProcessError:
            print("❌ ETL (Veri birleştirme) sürecinde bir hata oluştu!")
