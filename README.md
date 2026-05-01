# Arkafon 📊

> **Paranın İzini Sürün:** TEFAS yatırım fonlarındaki nakit akışını ve trendleri analiz eden, yüksek performanslı ve minimalist finansal dashboard.

Arkafon, devasa boyutlardaki günlük TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) verilerini işleyerek, yatırımcıların pazar dinamiklerini ve fon kategorilerindeki (Döviz, Altın, Hisse vb.) net para giriş/çıkışlarını anlık olarak takip etmesini sağlar. 

Uygulama, karmaşık finansal verileri "Separation of Concerns" (Sorumlulukların Ayrılması) prensibiyle işleyerek, arka planda ağır veri işleme görevlerini arayüzden tamamen izole eder.

## 📐 Mimari Tasarım

Arkafon, performansı maksimize etmek için iki katmanlı bir mimari kullanır:
1. **Data Pipeline (ETL):** Ham `.parquet` dosyaları okunur, net giriş/çıkış hesaplamaları (TEDPAYSAYISI Δ * FIYAT) yapılır ve Streamlit'in belleğe saniyeler içinde alabileceği tek bir `master_flow_data.parquet` dosyasına sıkıştırılır.
2. **Presentation Layer (UI):** Streamlit ve Plotly kullanılarak, sadece önceden işlenmiş veriler üzerinde milisaniyelik filtreleme işlemleri yapılarak minimalist bir arayüz sunulur.

## 📂 Klasör Yapısı

Proje, temiz kod ve modülerlik standartlarına göre organize edilmiştir:

```text
arkafon/
├── app/                    # Frontend (Kullanıcı Arayüzü) Katmanı
│   ├── components/         # Modüler UI bileşenleri (Sidebar, Metrikler, Grafikler)
├── data/                   # Veri Deposu (Git tarafından yok sayılır)
│   ├── processed/          # İşlenmiş ve optimize edilmiş ana veri setleri
│   └── raw/                # TEFAS'tan çekilen günlük ham parquet dosyaları
├── notebooks/              # Veri keşfi ve prototipleme (Jupyter)
├── src/                    # Backend (İş Mantığı ve Veri İşleme) Katmanı
│   ├── calculations.py     # Finansal algoritmalar ve metrik hesaplamaları
│   ├── config.py           # Ortam değişkenleri, yollar ve regex pattern'ları
│   └── data_loader.py      # ETL süreçleri ve Parquet I/O işlemleri
├── .devcontainer/          # Geliştirme ortamı yapılandırması
├── .gitignore              # Versiyon kontrolü dışında bırakılacak dosyalar
├── requirements.txt        # Python bağımlılıkları
├── streamlit_app.py        # Streamlit uygulamasının ana giriş noktası
└── README.md               # Proje dokümantasyonu
```

## 🚀 Kurulum ve Çalıştırma

### 1. Gereksinimler
Projeyi çalıştırmak için sisteminizde Python 3.10+ kurulu olmalıdır. İzole bir çalışma ortamı için sanal ortam (`venv`) kullanılması tavsiye edilir.

```bash
# Repo'yu klonlayın veya dizine gidin
cd arkafon


# Sanal ortam oluşturun ve aktif edin (macOS/Linux)
python3 -m venv .arkafon_env
source .arkafon_env/bin/activate

# Bağımlılıkları yükleyin
pip install -r requirements.txt
```

## 2. Veri Hazırlığı

Ham TEFAS `.parquet` dosyalarını `data/raw/` dizininin içine yerleştirin. Ardından veri motorunu çalıştırarak işlenmiş ana dosyayı oluşturun:
```bash
# Bu komut raw dosyaları okur, net akışları hesaplar ve processed klasörüne kaydeder
python src/data_loader.py
```

## 3. Uygulamayı Başlatma

# Veri hazırlığı tamamlandıktan sonra Streamlit sunucusunu başlatın:
```bash
streamlit run streamlit_app.py
```
Uygulama varsayılan olarak http://localhost:8501 adresinde çalışacaktır.


## 🛠 Kullanılan Teknolojiler

Dil: Python 3

Veri İşleme: Pandas, PyArrow, NumPy

Arayüz: Streamlit

Görselleştirme: Plotly, Altair

Depolama: Apache Parquet formatı

## 📄 Lisans
Bu proje MIT Lisansı altında lisanslanmıştır.