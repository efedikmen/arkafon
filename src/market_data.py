import yfinance as yf
import pandas as pd
import os
import requests
from datetime import datetime, date
from src.config import DATA_DIR  # Config dosyasından veri ana dizinini alıyoruz

# Piyasaların kaydedileceği yol
MARKET_DATA_PATH = os.path.join(DATA_DIR, "processed", "market_data.parquet")


def update_market_data(tcmb_api_key=None):

    tcmb_api_key = tcmb_api_key or os.getenv("TCMB_API_KEY")

    if tcmb_api_key:
        print("🔑 TCMB API key bulundu")
    else:
        print("⚠️ TCMB API key yok, Yahoo verisi kullanılacak")

    print("📈 Piyasa verileri güncelleniyor...")
    start_date = "2020-01-01"
    end_date = date.today().strftime('%Y-%m-%d')

    # 1. YAHOO FINANCE'TEN ALTIN (ve yedek USD/TRY) ÇEK
    # GC=F -> Altın (Gold Futures), TRY=X -> USD/TRY
    tickers = ["GC=F", "TRY=X"]
    print("  ⏳ Yahoo Finance'ten Altın ve Kur verileri çekiliyor...")
    df_yf = yf.download(tickers, start=start_date,
                        end=end_date, progress=False)

    # Sadece kapanış (Close) fiyatlarını alıyoruz
    df = df_yf['Close'].reset_index()
    # Sütun isimlerini temizle
    df.columns = ['tarih', 'gold_usd', 'usd_try_yf']
    df['tarih'] = pd.to_datetime(df['tarih']).dt.normalize()

    # 2. TCMB RESMİ KURU (EVDS API)
    # Eğer API Key yoksa Yahoo'nun bankalararası kurunu TCMB gibi kabul edeceğiz
    df['usd_try'] = df['usd_try_yf']

    if tcmb_api_key:
        print("  ⏳ TCMB EVDS'den resmi USD/TRY kurları çekiliyor...")
        try:
            url = f"https://evds2.tcmb.gov.tr/service/evds/series=TP.DK.USD.S.YTL&startDate=01-01-2020&endDate={date.today().strftime('%d-%m-%Y')}&type=json"
            headers = {"key": tcmb_api_key}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                tcmb_data = response.json().get('items', [])
                tcmb_df = pd.DataFrame(tcmb_data)
                tcmb_df['tarih'] = pd.to_datetime(
                    tcmb_df['Tarih'], format="%d-%m-%Y")
                tcmb_df['TP_DK_USD_S_YTL'] = pd.to_numeric(
                    tcmb_df['TP_DK_USD_S_YTL'], errors='coerce')

                # Yahoo tarihleriyle TCMB tarihlerini birleştir
                df = df.merge(
                    tcmb_df[['tarih', 'TP_DK_USD_S_YTL']], on='tarih', how='left')
                # TCMB verisi olan günlerde TCMB'yi, olmayan günlerde (tatiller vb) Yahoo'yu kullan
                df['usd_try'] = df['TP_DK_USD_S_YTL'].combine_first(
                    df['usd_try_yf'])
                df.drop(columns=['TP_DK_USD_S_YTL'], inplace=True)
                print("  ✅ TCMB kurları başarıyla entegre edildi.")
        except Exception as e:
            print(
                f"  ❌ TCMB verisi çekilemedi, Yahoo kuru ile devam ediliyor: {e}")

    # Eksik verileri (hafta sonu vb.) bir önceki günün kapanışıyla doldur (Forward Fill)
    df = df.ffill()

    # Parquet olarak kaydet
    os.makedirs(os.path.dirname(MARKET_DATA_PATH), exist_ok=True)
    df.to_parquet(MARKET_DATA_PATH)
    print("✅ Piyasa verileri master dosyaya kaydedildi!")


def get_market_data(start_date, end_date):
    """API'nin grafiği çizerken okuyacağı çok hızlı fonksiyon"""
    if not os.path.exists(MARKET_DATA_PATH):
        # İlk çalışmada dosya yoksa indir
        update_market_data()

    df = pd.read_parquet(MARKET_DATA_PATH)
    mask = (df['tarih'] >= pd.to_datetime(start_date)) & (
        df['tarih'] <= pd.to_datetime(end_date))
    return df[mask].set_index('tarih')


if __name__ == "__main__":
    # Test etmek için direkt çalıştırılabilir
    update_market_data()
