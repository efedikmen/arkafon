import streamlit as st

# 1. Sayfa Ayarları (Streamlit'te her zaman en üstte olmalıdır)
st.set_page_config(
    page_title="Arkafon | Paranın İzini Sürün",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# TODO: İleride modüler yapıya geçtiğimizde bileşenleri buradan içe aktaracağız
# from app.components import sidebar, metrics, charts

# --- ANA EKRAN BAŞLIĞI ---
st.title("Arkafon")
st.markdown("### Paranın İzini Sürün")
st.markdown("---")

# --- YAN MENÜ (SIDEBAR) ---
st.sidebar.title("Kontrol Paneli")

# Tasarımsal olarak temiz duran sabit zaman segmentleri
zaman_araligi = st.sidebar.radio(
    "Analiz Aralığı",
    ["Bugün", "Son 7 Gün", "Son 30 Gün", "Yılbaşından Bugüne"],
    index=2  # Varsayılan olarak 'Son 30 Gün' seçili gelir
)

# İş mantığı bağlandığında config.py içindeki regex'ten beslenecek
fon_turu = st.sidebar.multiselect(
    "Fon Kategorisi",
    ["Döviz", "Altın", "Yabancı", "Hisse", "Kıymetli Madenler"],
    default=["Döviz", "Altın"]
)

st.sidebar.markdown("---")
st.sidebar.info("Modüler sistem hazır. Veri motoru bağlantısı bekleniyor...")

# --- ÖZET METRİKLER (KPI KARTLARI) ---
# Üç kolonlu temiz bir yerleşim (Placeholder - Veriler bağlanana kadar statik kalacak)
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Toplam Net Giriş", value="₺ 0.00", delta="0%")
with col2:
    st.metric(label="En Çok Giriş Alan Kategori", value="-", delta="-")
with col3:
    st.metric(label="İncelenen Fon Sayısı", value="0")

st.markdown("<br><br>", unsafe_allow_html=True)

# --- GRAFİK ALANI ---
st.info("💡 Veri motoru (src/calculations.py) entegre edildikten sonra trend grafikleri ve Liderlik Tablosu burada yer alacaktır.")
