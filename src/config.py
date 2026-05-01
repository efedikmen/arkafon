import os

# Ana Dizin (arkafon klasörü)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Veri Yolları
RAW_DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DATA_DIR = os.path.join(BASE_DIR, "data", "processed")

# İşlenmiş Ana Veri Dosyasının Yolu
MASTER_DATA_PATH = os.path.join(PROCESSED_DATA_DIR, "master_flow_data.parquet")

# Fon Filtresi (Senin orijinal kodundaki regex - Döviz, Altın vb.)
FUND_PATTERN = r"\b(?:DÖVİZ|YABANCI|KIYMETLİ|GÜMÜŞ|ALTIN\s)\b"
