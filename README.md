# Arkafon 📊

> **Paranın İzini Sürün:** TEFAS yatırım fonlarındaki nakit akışını ve trendleri analiz eden, yüksek performanslı ve minimalist finansal dashboard.

Arkafon, devasa boyutlardaki günlük TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) verilerini işleyerek, yatırımcıların pazar dinamiklerini ve fon kategorilerindeki (Döviz, Altın, Hisse vb.) net para giriş/çıkışlarını anlık olarak takip etmesini sağlar. 

Uygulama, karmaşık finansal verileri "Separation of Concerns" (Sorumlulukların Ayrılması) prensibiyle işleyerek, arka planda ağır veri işleme görevlerini arayüzden tamamen izole eder.

## 📐 Mimari Tasarım

Arkafon, performansı maksimize etmek için üç katmanlı bir mimari kullanır:
1. **Data Pipeline (ETL):** Ham `.parquet` dosyaları Pandas ile okunur, net giriş/çıkış hesaplamaları hızlıca yapılarak belleğe alınır.
2. **API Katmanı (FastAPI):** Bellekteki (veya işlenmiş) veriler, milisaniyeler içinde RESTful uç noktalar (endpoints) üzerinden Frontend'e (React) sunulur.
3. **Güvenlik & Veritabanı:** Kullanıcı oturumları (Bcrypt + JWT) ve kişiselleştirilmiş fon sepetleri, SQLAlchemy ORM aracılığıyla SQLite veritabanında güvenle depolanır.
## 📂 Klasör Yapısı

Proje, temiz kod ve modülerlik standartlarına göre organize edilmiştir:

```text
arkafon/
├── data/                   # Veri Deposu (Git tarafından yok sayılır)
│   ├── processed/          # İşlenmiş ve optimize edilmiş ana veri setleri
│   └── raw/                # TEFAS'tan çekilen günlük ham parquet dosyaları
├── src/                    # Backend (İş Mantığı ve API) Katmanı
│   ├── api.py              # FastAPI ana uygulaması ve route tanımları
│   ├── auth.py             # JWT üretimi, şifre hashleme ve güvenlik
│   ├── db.py               # SQLAlchemy veritabanı modelleri ve şemalar
│   ├── config.py           # Ortam değişkenleri ve yollar
│   └── data_loader.py      # ETL süreçleri ve Parquet I/O işlemleri
├── .gitignore              # Versiyon kontrolü dışında bırakılacak dosyalar
├── requirements.txt        # Python bağımlılıkları
└── README.md               # Proje dokümantasyonu
```

## 🚀 Kurulum ve Çalıştırma

### 1. Gereksinimler
Projeyi çalıştırmak için sisteminizde Python 3.10+ kurulu olmalıdır. İzole bir çalışma ortamı için sanal ortam (`venv`) kullanılması tavsiye edilir.

```bash
# Repo'yu klonlayın veya dizine gidin
cd arkafon
```

# Sanal ortam oluşturun ve aktif edin (macOS/Linux)

```bash
python3 -m venv .arkafon_env
source .arkafon_env/bin/activate
```

# Bağımlılıkları yükleyin
```bash
pip install -r requirements.txt
```

## 2. Veri Hazırlığı

Ham TEFAS `.parquet` dosyalarını `data/raw/` dizininin içine yerleştirin. Ardından veri motorunu çalıştırarak işlenmiş ana dosyayı oluşturun:


```bash
python -m uvicorn src.api:app --reload
```

## 3. Uygulamayı Başlatma



```bash
# Veri hazırlığı tamamlandıktan sonra Streamlit sunucusunu başlatın:
streamlit run streamlit_app.py
```


## 🛠 Kullanılan Teknolojiler

* Dil: Python 3

* Web Çerçevesi: FastAPI, Uvicorn

* Veri İşleme: Pandas, PyArrow, NumPy

* Veritabanı & ORM: SQLite, SQLAlchemy

* Güvenlik: JWT (python-jose), Passlib (Bcrypt), Pydantic  
   

📄 Lisans

Bu proje MIT Lisansı altında lisanslanmıştır.