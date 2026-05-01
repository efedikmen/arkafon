import streamlit as st
import plotly.express as px
import os
import pandas as pd
from datetime import date, timedelta
from src.calculations import load_data, filter_data, get_kpi_metrics, get_top_funds, get_trend_data

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Arkafon | Paranın İzini Sürün",
    page_icon="assets/logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PREMIUM CSS ENJEKSİYONU ---
st.markdown("""
<style>
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp { background-color: #06090E; }
    [data-testid="stSidebar"] {
        background-color: #021035 !important;
        border-right: 1px solid #1A2436;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] {
        color: #8B9BB4 !important;
        font-size: 1.1rem;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        color: #00D2FF !important;
        border-bottom: 2px solid #00D2FF !important;
    }
    .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# --- VERİ YÜKLEME ---
df = load_data()

if df.empty:
    st.warning("Veri bulunamadı. Lütfen önce veri motorunu çalıştırın.")
    st.stop()

# --- 1. SESSION STATE YÖNETİMİ ---
min_date = df["tarih"].min().date()
max_date = df["tarih"].max().date()

if 'slider_range' not in st.session_state:
    # Uygulama ilk açıldığında default 2021 başı
    st.session_state.slider_range = (max(min_date, date(2021, 1, 1)), max_date)

# Dropdown değiştikçe slider'ı güncelleyen fonksiyon


def update_range():
    choice = st.session_state.quick_choice
    today = max_date

    if choice == "Son 7 Gün":
        new_start = today - timedelta(days=7)
    elif choice == "Son 30 Gün":
        new_start = today - timedelta(days=30)
    elif choice == "6 Ay":
        new_start = today - timedelta(days=180)
    elif choice == "Son 1 Yıl":
        new_start = today - timedelta(days=365)
    elif choice == "Yıl Başından Bugüne":
        new_start = date(today.year, 1, 1)
    else:
        return  # "(Seç)" durumunda slider'a dokunma

    st.session_state.slider_range = (max(min_date, new_start), today)


# --- 2. YAN MENÜ (SIDEBAR) ---
logo_path = os.path.join("app", "assets", "logo.png")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)

st.sidebar.title("Kontrol Paneli")

# HIZLI TARİH SEÇİMİ
st.sidebar.selectbox(
    "Hızlı Tarih Seçimi",
    options=["(Seç)", "Son 7 Gün", "Son 30 Gün", "6 Ay",
             "Yıl Başından Bugüne", "Son 1 Yıl"],
    key="quick_choice",
    on_change=update_range
)

# ZAMAN TÜNELİ SLIDER
st.sidebar.subheader("🗓️ Zaman Tüneli")
start_date, end_date = st.sidebar.slider(
    "Analiz Aralığı Seçin",
    min_value=min_date,
    max_value=max_date,
    key="slider_range",
    format="DD.MM.YYYY"
)

# KATEGORİ SEÇİMLERİ
st.sidebar.markdown("---")
ana_kategoriler = ["PPF (TL)", "Tahvil (TL)", "Hisse (TL)", "Döviz", "Serbest Fon",
                   "Fon Sepeti", "Katılım Fonu", "Değişken Fon", "Karma Fon", "Diğer"]
secilen_ana_kategori = st.sidebar.multiselect(
    "Ana Kategori", options=ana_kategoriler, default=[])

secilen_alt_kategori = []
if "Döviz" in secilen_ana_kategori:
    alt_kategoriler = ["Kıymetli Maden / Emtia", "Eurobond",
                       "Yabancı Hisse", "Yabancı Tahvil", "Döviz PPF"]
    secilen_alt_kategori = st.sidebar.multiselect(
        "Döviz Kırılımları", options=alt_kategoriler, default=[])

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Veriseti Son Güncelleme: **{max_date.strftime('%d.%m.%Y')}**")

# --- 3. VERİ FİLTRELEME (Single Source of Truth) ---
# Önce tarih filtresi (Slider değerleri ana kuraldır)
mask = (df["tarih"].dt.date >= start_date) & (df["tarih"].dt.date <= end_date)
filtered_df = df.loc[mask]

# Sonra kategori filtresi (Eski fonksiyonu sadece kategoriler için kullanıyoruz)
if secilen_ana_kategori:
    # "Slider Kullan" stringi filter_data içindeki tarih mantığını devre dışı bırakıp kategorileri işletir
    filtered_df = filter_data(
        filtered_df, "Slider Kullan", secilen_ana_kategori, secilen_alt_kategori)

# --- SEKME YAPISI ---
tab_pazar, tab_tekil = st.tabs(
    ["🌐 Makro Pazar Analizi", "🔍 Tekil Fon İncelemesi"])

# ==========================================
# 1. SEKME: MAKRO PAZAR ANALİZİ
# ==========================================
with tab_pazar:
    # Rakamları ve grafikleri hesapla
    total_inflow, top_fund, unique_funds = get_kpi_metrics(filtered_df)

    st.markdown(f"""
    <div style="display: flex; gap: 20px; margin-bottom: 25px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
            <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">Toplam Net Giriş (TL)</p>
            <p style="color: #FFFFFF; font-size: 1.5rem; font-weight: 700; margin: 0; white-space: nowrap; letter-spacing: -0.5px;">₺{total_inflow:,.0f}</p>
        </div>
        <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
            <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">En Çok Giriş Alan Fon</p>
            <p style="color: #00D2FF; font-size: 1.1rem; font-weight: 700; margin: 0; line-height: 1.4; word-wrap: break-word; overflow: visible;">{top_fund}</p>
        </div>
        <div style="flex: 1; min-width: 250px; background-color: #121826; border: 1px solid #1E273D; border-radius: 12px; padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
            <p style="color: #8B9BB4; font-size: 0.95rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px;">İncelenen Fon Sayısı</p>
            <p style="color: #FFFFFF; font-size: 1.8rem; font-weight: 700; margin: 0;">{unique_funds}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not filtered_df.empty:
        st.subheader("Zaman İçindeki Para Girişleri / Çıkışları")

        # TEFAS TOPLAM için ana veriyi sadece tarihe göre filtrele
        date_mask = (df["tarih"].dt.date >= start_date) & (
            df["tarih"].dt.date <= end_date)
        date_filtered_df = df.loc[date_mask]

        # Artık secilen_alt_kategori'yi de yolluyoruz ki motor parçalayıp parçalamayacağını bilsin
        trend_df = get_trend_data(
            filtered_df, date_filtered_df, secilen_alt_kategori)

        if not trend_df.empty:
            # "Döviz" ana kategorisinin rengini palete geri ekledik
            color_map = {
                "TEFAS TOPLAM": "#FFFFFF", "Hisse (TL)": "#3A7BD5", "PPF (TL)": "#F59E0B",
                "Tahvil (TL)": "#10B981", "Serbest Fon": "#8B5CF6", "Katılım Fonu": "#EC4899",
                "Fon Sepeti": "#14B8A6", "Değişken Fon": "#F43F5E", "Karma Fon": "#8B9BB4", "Diğer": "#64748B",
                "Döviz": "#00D2FF",  # <- EKLENDİ
                "Kıymetli Maden / Emtia": "#00D2FF", "Eurobond": "#0284C7", "Yabancı Hisse": "#38BDF8",
                "Yabancı Tahvil": "#7DD3FC", "Döviz PPF": "#BAE6FD"
            }

            fig_trend = px.line(trend_df, x="tarih", y="kumulatif_giris", color="kategori_etiketi",
                                color_discrete_map=color_map, labels={"kumulatif_giris": "Kümülatif Giriş (TL)", "tarih": "Tarih", "kategori_etiketi": "Kategori"})

            fig_trend.update_traces(
                hovertemplate="<b>%{data.name}</b>: ₺%{y:,.0f}<extra></extra>")

            for trace in fig_trend.data:
                trace.line.width = 4 if trace.name == "TEFAS TOPLAM" else 2

            fig_trend.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                # 2. DEĞİŞİKLİK: hoverlabel ile tooltip içindeki fontları ufaltıyoruz.
                hoverlabel=dict(
                    font_size=11,
                    font_family="sans-serif"
                ),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(
                    size=8, color="#8B9BB4"), itemwidth=30),
                margin=dict(l=0, r=0, t=30, b=0), font=dict(color="#8B9BB4")
            )

            fig_trend.update_yaxes(title="Kümülatif Giriş (TL)", showgrid=True,
                                   gridcolor="rgba(139,155,180,0.1)", zeroline=True, zerolinecolor="rgba(255,255,255,0.2)")
            fig_trend.update_xaxes(title="",
                                   showgrid=False,
                                   hoverformat="%d.%m.%Y")
            st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            st.subheader("Top 10 Fon (Net Giriş)")
            top_funds_df = get_top_funds(filtered_df, top_n=10)
            fig = px.bar(top_funds_df, x="FONKODU", y="net_giris_tl", hover_data=[
                         "FONUNVAN"], color="net_giris_tl", color_continuous_scale=["#121826", "#3A7BD5", "#00D2FF"])
            fig.update_traces(
                hovertemplate="<b>%{x}</b><br>Toplam Giriş: ₺%{y:,.0f}<extra></extra>")
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(
                l=0, r=0, t=10, b=0), coloraxis_showscale=False, font=dict(color="#8B9BB4"))
            st.plotly_chart(fig, use_container_width=True)

        with col_table:
            st.subheader("Liderlik Tablosu")
            display_df = top_funds_df[["FONKODU", "net_giris_tl"]].copy()
            display_df["net_giris_tl"] = display_df["net_giris_tl"].apply(
                lambda x: f"₺ {x:,.0f}")
            display_df.rename(columns={
                "net_giris_tl": "Net Giriş (TL)"
            }, inplace=True)
            st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.info("Kategori Seçimi Bekleniyor...")


# ==========================================
# 2. SEKME: TEKİL FON İNCELEMESİ (DRILL-DOWN)
# ==========================================
with tab_tekil:
    st.markdown("<br>", unsafe_allow_html=True)

    # Arama motoru için fon listesi
    unique_funds_list = df[["FONKODU", "FONUNVAN"]].drop_duplicates()
    search_options = (
        unique_funds_list["FONKODU"] + " - " + unique_funds_list["FONUNVAN"]).sort_values()

    selected_option = st.selectbox(
        "İncelemek istediğiniz fonu seçin veya kodunu yazın:",
        search_options,
        index=None,
        placeholder="Örn: GRO - GARANTİ PORTFÖY..."
    )

    if selected_option:
        target_kod = selected_option.split(" - ")[0]

        # --- KRİTİK GÜNCELLEME: Filtreleme artık Slider değerlerini (start_date, end_date) kullanıyor ---
        fund_data = df[
            (df["FONKODU"] == target_kod) &
            (df["tarih"].dt.date >= start_date) &
            (df["tarih"].dt.date <= end_date)
        ].sort_values("tarih")

        if not fund_data.empty:
            # Tekil Fon KPI
            f_inflow = fund_data["net_giris_tl"].sum()
            f_start = fund_data["FIYAT"].iloc[0]
            f_end = fund_data["FIYAT"].iloc[-1]
            f_perf = ((f_end - f_start) / f_start) * 100 if f_start > 0 else 0

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Dönemlik Toplam Akış", f"₺ {f_inflow:,.0f}")
            with c2:
                st.metric("Dönemlik Fiyat Performansı", f"% {f_perf:,.2f}")
            with c3:
                st.metric("Son Fiyat", f"₺ {f_end:,.6f}")

            # Grafikler
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**Fiyat Değişimi**")
                fig_p = px.line(fund_data, x="tarih", y="FIYAT", labels={
                    "tarih": "Tarih", "FIYAT": "Birim Pay Değeri (TL)"})
                fig_p.update_traces(
                    line_color="#00D2FF", hovertemplate="<b>%{x}</b><br>Birim Fiyat: ₺%{y:,.6f}<extra></extra>")
                fig_p.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(
                    color="#8B9BB4"), margin=dict(t=10, b=0, l=0, r=0))
                fig_p.update_yaxes(title="Birim Pay Değeri (TL)",
                                   showgrid=True, gridcolor="rgba(139,155,180,0.1)")
                fig_p.update_xaxes(title="", showgrid=False)
                st.plotly_chart(fig_p, use_container_width=True)

            with col_right:
                st.markdown("**Günlük Net Nakit Akışı**")
                fund_data["FlowType"] = fund_data["net_giris_tl"].apply(
                    lambda x: "Giriş" if x >= 0 else "Çıkış")
                fig_f = px.bar(fund_data, x="tarih", y="net_giris_tl", color="FlowType", color_discrete_map={
                    "Giriş": "#10B981", "Çıkış": "#F43F5E"}, labels={"tarih": "Tarih", "net_giris_tl": "Net Nakit Akışı (TL)"})
                fig_f.update_traces(
                    hovertemplate="<b>%{x}</b><br>Nakit Akışı: ₺%{y:,.0f}<extra></extra>")
                fig_f.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(
                    color="#8B9BB4"), showlegend=False, margin=dict(t=10, b=0, l=0, r=0))
                fig_f.update_yaxes(title="Net Nakit Akışı (TL)",
                                   showgrid=True, gridcolor="rgba(139,155,180,0.1)")
                fig_f.update_xaxes(title="", showgrid=False)
                st.plotly_chart(fig_f, use_container_width=True)

            # --- EKSTRA ANALİZ KATMANI ---
            st.markdown("---")
            col_info, col_raw = st.columns([1, 1])

            with col_info:
                st.markdown("**Fon Bilgileri & Risk**")
                volatility = fund_data["FIYAT"].pct_change().std(
                ) * (252**0.5) * 100  # Yıllıklandırılmış Volatilite

                info_df = pd.DataFrame({
                    "Özellik": ["İncelenen Gün", "En Yüksek Fiyat", "En Düşük Fiyat", "Tahmini Oynaklık (Yıllık)"],
                    "Değer": [len(fund_data), f"₺ {fund_data['FIYAT'].max():,.4f}", f"₺ {fund_data['FIYAT'].min():,.4f}", f"% {volatility:.2f}"]
                })
                st.table(info_df)

            with col_raw:
                st.markdown("**Ham Veri Tablosu**")
                # Kullanıcıya son günleri gösteren temiz bir tablo
                raw_display = fund_data[["tarih", "FIYAT", "net_giris_tl"]].sort_values(
                    "tarih", ascending=False).head(10)

                # Tarih ve Sayı Formatlamaları
                raw_display["tarih"] = raw_display["tarih"].dt.strftime(
                    '%d.%m.%Y')
                raw_display["FIYAT"] = raw_display["FIYAT"].apply(
                    lambda x: f"₺ {x:,.6f}")
                raw_display["net_giris_tl"] = raw_display["net_giris_tl"].apply(
                    lambda x: f"₺ {x:,.0f}")

                # Kolon isimlerini Türkçe ve daha şık yapalım (Opsiyonel ama önerilir)
                raw_display.rename(columns={
                    "tarih": "Tarih",
                    "FIYAT": "Fiyat",
                    "net_giris_tl": "Net Giriş (TL)"
                }, inplace=True)

                st.dataframe(
                    raw_display, use_container_width=True, hide_index=True)
