import os
import glob
import time
import pandas as pd
from datetime import date, datetime, timedelta
from tefas_client import Tefas
from src.config import RAW_DATA_DIR


def heal_missing_data():
    print("🩺 Arkafon Data Healer (Veri İyileştirme) Başlatılıyor...")

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

    # 2. Olması gereken İŞ GÜNLERİNİ (Pazartesi-Cuma) hesapla
    start_date = date(2025, 9, 27)  # Projemizin miladı
    end_date = date.today() - timedelta(days=1)

    # KRİTİK NOKTA: Sadece iş günlerini alıyoruz (Hafta sonları elendi)
    expected_dates = set(pd.bdate_range(start=start_date, end=end_date).date)

    # 3. Gerçek delikleri tespit et (Beklenen İş Günleri - Klasördeki Günler)
    missing_dates = sorted(expected_dates - existing_dates)

    if not missing_dates:
        print("✅ Veri tabanında hiçbir delik yok. Veri bütünlüğü %100!")
        return

    print(f"🔍 Tespit edilen eksik (delik) gün sayısı: {len(missing_dates)}")

    # 4. Eksik günleri nokta atışı TEFAS'tan iste
    with Tefas() as tefas:
        for missing_date in missing_dates:
            date_str = missing_date.strftime("%d.%m.%Y")
            file_path = os.path.join(
                RAW_DATA_DIR, f"tefas_data_{date_str}.parquet")

            print(f"⏳ Eksik yama yapılıyor: {date_str}...")
            try:
                # Sadece o eksik güne özel sorgu
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
                        print(f"  ✅ {date_str} başarıyla yamalandı.")
                else:
                    # Hafta içlerine denk gelen Resmi Tatiller (Örn: 29 Ekim, 1 Mayıs) boş döner.
                    print(
                        f"  ⚠️ {date_str} boş döndü (Büyük ihtimalle resmi tatil).")

                    # Opsiyonel Zeka: Resmi tatilleri her seferinde tekrar tekrar API'ye sormamak için
                    # içi boş bir "hayalet" parquet dosyası oluşturabilirsin.
                    # pd.DataFrame(columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]).to_parquet(file_path)

            except Exception as e:
                print(f"  ❌ Hata: {date_str} çekilemedi ({type(e).__name__}).")

            # API'yi yormamak için kısa mola
            time.sleep(10)


if __name__ == "__main__":
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    # Günlük rutinde veya sistemde bir boşluk olduğundan şüphelendiğinde bunu çalıştırabilirsin
    heal_missing_data()
