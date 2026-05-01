import streamlit as st
import plotly.express as px
import os
from src.calculations import load_data, filter_data, get_kpi_metrics, get_top_funds, get_trend_data

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Arkafon | Paranın İzini Sürün",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PREMIUM CSS ENJEKSİYONU ---
st.markdown("""
<style>
    /* 1. Gereksiz Streamlit Menülerini Gizle */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 2. Ana Arka Plan */
    .stApp { background-color: #06090E; }
    
    /* 3. Sidebar (Logo Arka Planı ile Uyumlu Derin Lacivert) */
    [data-testid="stSidebar"] {
        background-color: #021035;
        border-right: 1px solid #1A2436;
    }
    
    /* Markdown içindeki boşlukları sıfırla */
    .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
df = load_data()

# --- YAN MENÜ (SIDEBAR) ---
logo_path = os.path.join("app", "assets", "logo.png")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)

st.sidebar.title("Kontrol Paneli")

# Default'u senin ekran görüntündeki gibi Yılbaşından Bugüne yaptım
zaman_araligi = st.sidebar.radio("Analiz Aralığı", [
                                 "Bugün", "Son 7 Gün", "Son 30 Gün", "Yılbaşından Bugüne"], index=3)

ana_kategoriler = ["PPF (TL)", "Tahvil (TL)", "Hisse (TL)", "Döviz", "Serbest Fon",
                   "Fon Sepeti", "Katılım Fonu", "Değişken Fon", "Karma Fon", "Diğer"]
# İSTEK 2: Default boş gelsin
secilen_ana_kategori = st.sidebar.multiselect(
    "Ana Kategori", options=ana_kategoriler, default=[])

secilen_alt_kategori = []
if "Döviz" in secilen_ana_kategori:
    alt_kategoriler = ["Kıymetli Maden / Emtia", "Eurobond",
                       "Yabancı Hisse", "Yabancı Tahvil", "Genel Döviz"]
    secilen_alt_kategori = st.sidebar.multiselect(
        "Döviz Kırılımları", options=alt_kategoriler, default=[])

st.sidebar.markdown("---")
if not df.empty:
    son_tarih = df["tarih"].max().strftime("%d.%m.%Y")
    st.sidebar.caption(f"Veriseti Son Güncelleme: **{son_tarih}**")

# --- ANA EKRAN ---
st.title("Arkafon")
st.markdown("### Paranın İzini Sürün")
st.markdown("---")

if df.empty:
    st.warning(
        "Veri bulunamadı. Lütfen önce veri motorunu (src/data_loader.py) çalıştırın.")
    st.stop()

filtered_df = filter_data(
    df, zaman_araligi, secilen_ana_kategori, secilen_alt_kategori)
total_inflow, top_fund, unique_funds = get_kpi_metrics(filtered_df)

# --- KUSURSUZ METRİK KARTLARI (HTML/CSS) ---
# İSTEK 1: Toplam rakamın sığması için font-size 1.5rem yapıldı, white-space: nowrap eklendi ve ₺ simgesi rakama bitişik yazıldı.
st.markdown(f"""
<div style="display: flex; gap: 20px; margin-bottom: 25px; flex-wrap: wrap;">
    <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
        <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">Toplam Net Giriş (TL)</p>
        <p style="color: #FFFFFF; font-size: 1.5rem; font-weight: 700; margin: 0; white-space: nowrap; letter-spacing: -0.5px;">₺{total_inflow:,.0f}</p>
    </div>
    <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
        <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">En Çok Giriş Alan Fon</p>
        <p style="color: #00D2FF; font-size: 1.1rem; font-weight: 700; margin: 0; line-height: 1.4; word-wrap: break-word;">{top_fund}</p>
    </div>
    <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
        <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">İncelenen Fon Sayısı</p>
        <p style="color: #FFFFFF; font-size: 1.8rem; font-weight: 700; margin: 0;">{unique_funds}</p>
    </div>
</div>
""", unsafe_allow_html=True)

# --- GRAFİKLER ---
if not filtered_df.empty:

    st.subheader("Zaman İçindeki Para Akışı (Kümülatif Trend)")
    trend_df = get_trend_data(filtered_df)

    if not trend_df.empty:
        color_map = {
            "TEFAS TOPLAM": "#FFFFFF",
            "Döviz": "#00D2FF", "Hisse (TL)": "#3A7BD5", "PPF (TL)": "#F59E0B",
            "Tahvil (TL)": "#10B981", "Serbest Fon": "#8B5CF6", "Katılım Fonu": "#EC4899",
            "Fon Sepeti": "#14B8A6", "Değişken Fon": "#F43F5E", "Karma Fon": "#8B9BB4", "Diğer": "#64748B"
        }

        fig_trend = px.line(
            trend_df, x="tarih", y="kumulatif_giris", color="ana_kategori", color_discrete_map=color_map,
            labels={
                "kumulatif_giris": "Kümülatif Net Giriş (TL)", "tarih": "Tarih", "ana_kategori": ""}
        )

        for trace in fig_trend.data:
            if trace.name == "TEFAS TOPLAM":
                trace.line.width = 4
            else:
                trace.line.width = 2

        fig_trend.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
            # İSTEK 3: Lejantı en soldan başlatıp, fontu 9'a çekerek tek satıra zorluyoruz
            legend=dict(
                orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0,
                font=dict(size=9, color="#8B9BB4"), itemwidth=30, tracegroupgap=1
            ),
            margin=dict(l=0, r=0, t=20, b=0), font=dict(color="#8B9BB4")
        )
        fig_trend.update_yaxes(showgrid=True, gridcolor="rgba(139,155,180,0.1)",
                               zeroline=True, zerolinecolor="rgba(255,255,255,0.2)")
        fig_trend.update_xaxes(showgrid=False)

        st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_chart, col_table = st.columns([2, 1])
    with col_chart:
        st.subheader("Top 10 Fon (Net Giriş)")
        top_funds_df = get_top_funds(filtered_df, top_n=10)

        fig = px.bar(
            top_funds_df, x="FONKODU", y="net_giris_tl", hover_data=["FONUNVAN"],
            labels={"net_giris_tl": "Net Giriş (TL)", "FONKODU": "Fon Kodu"}, color="net_giris_tl",
            color_continuous_scale=["#121826", "#3A7BD5", "#00D2FF"]
        )

        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_showscale=False, font=dict(color="#8B9BB4")
        )
        fig.update_yaxes(showgrid=True, gridcolor="rgba(139,155,180,0.1)")
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader("Liderlik Tablosu")
        display_df = top_funds_df[["FONKODU", "net_giris_tl"]].copy()
        display_df["net_giris_tl"] = display_df["net_giris_tl"].apply(
            lambda x: f"₺ {x:,.0f}")
        st.dataframe(display_df, hide_index=True, use_container_width=True)
else:
    st.info("Kategori Seçimi Bekleniyor...")
