# Arkafon 📊

> **Paranın İzini Sürün:** TEFAS yatırım fonlarındaki nakit akışını ve trendleri analiz eden, yüksek performanslı ve minimalist finansal dashboard.

Arkafon, devasa boyutlardaki günlük TEFAS verilerini işleyerek, yatırımcıların pazar dinamiklerini ve fon kategorilerindeki net para giriş/çıkışlarını anlık olarak takip etmesini sağlar.

## 📠 Mimari Tasarım

1. **Data Pipeline (ETL):** Ham `.parquet` dosyaları Pandas ile okunur, net giriş/çıkış hesaplamaları yapılıp tek bir `master_flow_data.parquet`'e yazılır.
2. **API Katmanı (FastAPI):** Bellekteki veri, RESTful endpoint'ler üzerinden Frontend'e (React) sunulur. Master parquet'in dosya zaman damgası her istekte kontrol edilir; updater bot dosyayı yenilediyse işlem otomatik reload edilir.
3. **Güvenlik & Veritabanı:** JWT (Bcrypt + python-jose) ile kullanıcı oturumları, SQLAlchemy ile portföyler.

## 📂 Klasör Yapısı

```text
arkafon/
├── data/                   # Veri (Git'te yok)
│   ├── processed/
│   └── raw/
├── src/
│   ├── api.py              # FastAPI app & routes
│   ├── auth.py             # JWT, password hashing
│   ├── db.py               # SQLAlchemy models + Pydantic schemas
│   ├── config.py           # paths & env loading
│   ├── data_loader.py      # ETL
│   ├── market_data.py      # USD/TRY + Gold ingest
│   └── risk_metrics.py     # Sharpe, MDD, real returns, etc.
├── tests/                  # pytest suite (split-detection golden fixtures)
├── .env.example
├── requirements.txt
└── README.md
```

> **Note:** there is no Streamlit app. An older `src/calculations.py` Streamlit
> helper was removed; the production frontend is React (`arkafon-fe`).

## 🚀 Kurulum

```bash
python3 -m venv .arkafon_env
source .arkafon_env/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit secrets
```

### Veri hazırlığı

Ham TEFAS `.parquet` dosyalarını `data/raw/` altına koyun:

```bash
python -m src.data_loader
```

### API’yi çalıştırma

```bash
uvicorn src.api:app --reload
```

### Testler

```bash
pytest -q
```

## 🔐 Konfigürasyon

Tüm sırlar ve URL'ler `.env` dosyasından alınır (`python-dotenv` yüklüdür):

| Env | Açıklama | Varsayılan |
| --- | --- | --- |
| `ARKAFON_SECRET_KEY` | JWT imza anahtarı | dev fallback (production'da hata) |
| `ARKAFON_TOKEN_EXPIRE_MINUTES` | Token ömrü (dakika) | 10080 (7g) |
| `ARKAFON_DATABASE_URL` | SQLAlchemy URL | `sqlite:///./arkafon.db` |
| `CORS_ORIGINS` | Virgülle ayırılmış origin listesi | localhost dev portları |
| `ARKAFON_ADMIN_TOKEN` | `/api/admin/reload` koruma anahtarı | (ayarlı değilse endpoint disabled) |
| `TCMB_API_KEY` | EVDS resmi USD/TRY kuru | boş -> Yahoo kullanılır |

## 📄 Lisans

MIT.
