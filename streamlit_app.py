import os
import streamlit as st
import plotly.express as px
from src.calculations import load_data, filter_data, get_kpi_metrics, get_top_funds

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Arkafon | Paranın İzini Sürün",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- VERİ YÜKLEME ---
df = load_data()

# --- ANA BAŞLIK ---
st.title("Arkafon")
st.markdown("### Paranın İzini Sürün")
st.markdown("---")

# Veri yoksa kullanıcıyı uyar ve uygulamayı durdur
if df.empty:
    st.warning(
        "Veri bulunamadı. Lütfen önce veri motorunu (src/data_loader.py) çalıştırın.")
    st.stop()

# --- YAN MENÜ (SIDEBAR) ---
# Logo
st.sidebar.image(os.path.join("app", "assets", "logo.png"),
                 use_container_width=True)

st.sidebar.title("Kontrol Paneli")


zaman_araligi = st.sidebar.radio(
    "Analiz Aralığı",
    ["Bugün", "Son 7 Gün", "Son 30 Gün", "Yılbaşından Bugüne"],
    index=2
)

# Ana Kategori Seçimi
ana_kategoriler = ["PPF (TL)", "Tahvil (TL)", "Hisse (TL)", "Döviz", "Diğer"]
secilen_ana_kategori = st.sidebar.multiselect(
    "Ana Kategori",
    options=ana_kategoriler,
    default=[]
)

# Alt Kategori Seçimi (Sadece Döviz seçildiğinde ekrana gelir - Conditional UI)
secilen_alt_kategori = []
if "Döviz" in secilen_ana_kategori:
    alt_kategoriler = ["Kıymetli Maden / Emtia", "Eurobond",
                       "Yabancı Hisse", "Yabancı Tahvil", "Genel Döviz"]
    secilen_alt_kategori = st.sidebar.multiselect(
        "Döviz Kırılımları",
        options=alt_kategoriler,
        default=alt_kategoriler  # Varsayılan olarak hepsini seç
    )

st.sidebar.markdown("---")
# Dinamik olarak verinin son tarihini menüde gösterelim ki kullanıcı bilsin
son_tarih = df["tarih"].max().strftime("%d.%m.%Y")
st.sidebar.caption(f"Veriseti Son Güncelleme: **{son_tarih}**")

# --- İŞ MANTIĞI: FİLTRELEME ---
filtered_df = filter_data(
    df, zaman_araligi, secilen_ana_kategori, secilen_alt_kategori)

# --- ÖZET METRİKLER (KPI) ---
total_inflow, top_fund, unique_funds = get_kpi_metrics(filtered_df)

col1, col2, col3 = st.columns(3)

with col1:
    # Sayıyı formatlayarak göster (Örn: 1,500,000 TL)
    st.metric(label="Toplam Net Giriş (TL)", value=f"₺ {total_inflow:,.0f}")
with col2:
    st.metric(label="En Çok Giriş Alan Fon", value=top_fund)
with col3:
    st.metric(label="İncelenen Fon Sayısı", value=unique_funds)

st.markdown("<br>", unsafe_allow_html=True)

# --- GRAFİKLER VE LİDERLİK TABLOSU ---
if not filtered_df.empty:
    # Grafik daha geniş, tablo daha dar
    col_chart, col_table = st.columns([2, 1])

    with col_chart:
        st.subheader("Top 10 Fon (Net Giriş)")
        top_funds_df = get_top_funds(filtered_df, top_n=10)

        # Plotly ile minimalist bir Bar Chart
        fig = px.bar(
            top_funds_df,
            x="FONKODU",
            y="net_giris_tl",
            hover_data=["FONUNVAN"],
            labels={"net_giris_tl": "Net Giriş (TL)", "FONKODU": "Fon Kodu"},
            color="net_giris_tl",
            color_continuous_scale="Viridis"
        )
        # Arka planı şeffaf yapıp gridleri temizleyelim (Premium hissiyat için)
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_showscale=False  # Yandaki renk skalasını gizle
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader("Liderlik Tablosu")
        # Sadece kod ve değeri gösteren temiz bir tablo
        display_df = top_funds_df[["FONKODU", "net_giris_tl"]].copy()
        display_df["net_giris_tl"] = display_df["net_giris_tl"].apply(
            lambda x: f"₺ {x:,.0f}")
        st.dataframe(display_df, hide_index=True, use_container_width=True)

else:
    st.info("Seçilen filtrelere uygun veri bulunamadı.")
