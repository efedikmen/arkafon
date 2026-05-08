from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import os
from datetime import timedelta
from src.config import MASTER_DATA_PATH, BASE_DIR
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from src.db import get_db, User, Portfolio, PortfolioItem, UserCreate, UserLogin, UserResponse, Token, BasketUpdate
from src.auth import get_password_hash, verify_password, create_access_token, get_current_user
from src.market_data import get_market_data
from src import risk_metrics as rm

app = FastAPI(title="Arkafon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080",
                   "http://127.0.0.1:8080",
                   "http://localhost:5173",
                   "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Veri yükleniyor...")
if os.path.exists(MASTER_DATA_PATH):
    df = pd.read_parquet(MASTER_DATA_PATH)
else:
    df = pd.DataFrame()

# CPI (TÜFE) lazy-loaded once at startup. Used by the real-return endpoint.
CPI_PATH = os.path.join(BASE_DIR, "data", "cpi_tufe.csv")
if os.path.exists(CPI_PATH):
    _cpi = pd.read_csv(CPI_PATH, parse_dates=["date"]).set_index("date")["cpi"].sort_index()
else:
    _cpi = pd.Series(dtype=float)

# --- MERKEZİ FİLTRE MOTORU ---


def get_filtered_df(start: str = "", end: str = "", categories: str = ""):
    f_df = df.copy()
    if f_df.empty:
        return f_df

    if categories:
        cat_list = [c.strip() for c in categories.split(",")]
        f_df = f_df[f_df["ana_kategori"].isin(cat_list)]

    # STRICT ABSOLUTE DATES
    if start and start != "undefined":
        f_df = f_df[f_df["tarih"] >= pd.to_datetime(start)]
    if end and end != "undefined":
        f_df = f_df[f_df["tarih"] <= pd.to_datetime(end)]

    return f_df

# --- 1. ENDPOINT: Makro Pazar KPI'ları ---


@app.get("/api/macro/kpi")
def get_macro_kpi(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"total_net_inflow": 0, "unique_funds": 0, "top_fund": "-"}

    total_inflow = float(f_df["net_giris_tl"].sum())
    unique_funds = int(f_df["FONKODU"].nunique())

    top_fund_series = f_df.groupby("FONKODU")["net_giris_tl"].sum()
    top_fund_code = top_fund_series.idxmax() if not top_fund_series.empty else "-"

    return {"total_net_inflow": total_inflow, "unique_funds": unique_funds, "top_fund": top_fund_code}

# --- 2. ENDPOINT: Zaman İçindeki Akış (Trend) ---


@app.get("/api/macro/trend")
def get_macro_trend(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []

    trend = f_df.groupby("tarih")["net_giris_tl"].sum().reset_index()
    trend = trend.sort_values("tarih")
    trend["tarih"] = trend["tarih"].dt.strftime('%Y-%m-%d')
    # Kümülatif hesabı filtreli verinin başından itibaren sıfırdan başlasın
    trend["kumulatif_giris"] = trend["net_giris_tl"].cumsum()

    return trend.to_dict(orient="records")

# --- 3. ENDPOINT: Top 10 Fon ---


@app.get("/api/macro/top10")
def get_macro_top10(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []

    top = f_df.groupby(["FONKODU", "FONUNVAN"])[
        "net_giris_tl"].sum().reset_index()
    top = top.sort_values("net_giris_tl", ascending=False).head(10)
    return top.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "net_giris_tl": "netInflow"}).to_dict(orient="records")

# --- 4. ENDPOINT: Tüm Fon Evreni ---


@app.get("/api/macro/universe")
def get_macro_universe(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []

    grouped = f_df.groupby(["FONKODU", "FONUNVAN", "ana_kategori"], dropna=False).agg(
        netInflow=('net_giris_tl', 'sum'),
        first_price=('FIYAT', 'first'),
        last_price=('FIYAT', 'last')
    ).reset_index()

    grouped['perfYTD'] = (grouped['last_price'] -
                          grouped['first_price']) / grouped['first_price']
    grouped['perfYTD'] = grouped['perfYTD'].replace(
        [np.inf, -np.inf], np.nan).fillna(0)
    grouped['ana_kategori'] = grouped['ana_kategori'].fillna("Diğer")
    grouped = grouped.sort_values("netInflow", ascending=False).head(25)

    return grouped.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "ana_kategori": "category"}).to_dict(orient="records")

# --- 5. ENDPOINT: Tekil Fon Arama Listesi (Drill-down Sayfası İçin) ---


@app.get("/api/fund/list")
def get_fund_list():
    if df.empty:
        return []
    funds = df[["FONKODU", "FONUNVAN"]].drop_duplicates().dropna()
    return funds.rename(columns={"FONKODU": "code", "FONUNVAN": "name"}).to_dict(orient="records")


# --- 6. ENDPOINT: Tekil Fon Detayları (Drill-down Sayfası İçin) ---
@app.get("/api/fund/{fund_code}")
def get_fund_details(fund_code: str, start: str = "", end: str = ""):
    f_df = df[df["FONKODU"] == fund_code].sort_values("tarih")
    if f_df.empty:
        return {"error": "Fon bulunamadı"}

    # MUTLAK TARİH FİLTRESİNİ UYGULA
    if start and start != "undefined":
        f_df = f_df[f_df["tarih"] >= pd.to_datetime(start)]
    if end and end != "undefined":
        f_df = f_df[f_df["tarih"] <= pd.to_datetime(end)]

    if f_df.empty:
        return {"error": "Seçilen tarih aralığında veri bulunamadı"}

    inflow = float(f_df["net_giris_tl"].sum())
    start_p = float(f_df["FIYAT"].iloc[0])
    end_p = float(f_df["FIYAT"].iloc[-1])
    perf = ((end_p - start_p) / start_p) if start_p > 0 else 0

    chart_data = f_df[["tarih", "FIYAT", "net_giris_tl"]].copy()
    chart_data["tarih"] = chart_data["tarih"].dt.strftime('%Y-%m-%d')

    return {
        "kpi": {"inflow": inflow, "perf": perf, "latestPrice": end_p},
        "chart": chart_data.rename(columns={"tarih": "date", "FIYAT": "price", "net_giris_tl": "flow"}).to_dict(orient="records")
    }

# --- 7. ENDPOINT: Sankey Akış Verisi ---


@app.get("/api/macro/flow")
def get_macro_flow(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}

    # 1. Kaynak (Kategori) -> Hedef (Fon Kodu) bazlı grupla
    flow_df = f_df.groupby(["ana_kategori", "FONKODU"])[
        "net_giris_tl"].sum().reset_index()

    # 2. Sadece pozitif akışları (girişleri) al - Sankey negatif değer sevmez
    flow_df = flow_df[flow_df["net_giris_tl"] > 0]

    # 3. Görsel karmaşayı önlemek için en büyük 20 akışı al
    flow_df = flow_df.sort_values("net_giris_tl", ascending=False).head(20)

    # 4. Sankey Formatı Hazırlama (Nodes & Links)
    nodes = []
    links = []

    # Benzersiz isimler listesi (Kategoriler + Fonlar)
    all_names = pd.concat(
        [flow_df["ana_kategori"], flow_df["FONKODU"]]).unique().tolist()
    nodes = [{"name": name} for name in all_names]

    # İsimlerin index'lerini bulup linkleri oluştur
    name_to_idx = {name: i for i, name in enumerate(all_names)}

    for _, row in flow_df.iterrows():
        links.append({
            "source": name_to_idx[row["ana_kategori"]],
            "target": name_to_idx[row["FONKODU"]],
            "value": round(float(row["net_giris_tl"]), 2)
        })

    return {"nodes": nodes, "links": links}


# --- 8. ENDPOINT: Makro Akış (Sistem İçi vs Sistem Dışı Sankey) ---
@app.get("/api/macro/flow-sankey")
def get_macro_flow_sankey(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}

    # 1. Seçili Dönem İçi Akış (Net Flow)
    flow_df = f_df.groupby("ana_kategori")["net_giris_tl"].sum().reset_index()
    flow_df = flow_df[flow_df["net_giris_tl"].abs() > 1000]

    if flow_df.empty:
        return {"nodes": [], "links": []}

    # 2. TOPLAM HACİM (AUM) HESAPLAMASI: Başlangıçtan 'end' tarihine kadar kümülatif
    end_dt = pd.to_datetime(
        end) if end and end != "undefined" else df["tarih"].max()
    cat_list = flow_df["ana_kategori"].tolist()

    aum_df = df[(df["ana_kategori"].isin(cat_list)) & (df["tarih"] <= end_dt)]
    aum_dict = aum_df.groupby("ana_kategori")["net_giris_tl"].sum().to_dict()

    INFLOW_NODE = "Sermaye Girişi"
    OUTFLOW_NODE = "Sermaye Çıkışı"

    # Node'lara AUM bilgisini ekliyoruz (Giriş/Çıkış ana kütlelerine 0 veriyoruz)
    all_names = [INFLOW_NODE, OUTFLOW_NODE] + cat_list
    nodes = [{"name": name, "aum": aum_dict.get(
        name, 0)} for name in all_names]
    name_to_idx = {name: i for i, name in enumerate(all_names)}

    links = []
    for _, row in flow_df.iterrows():
        val = float(row["net_giris_tl"])
        cat = row["ana_kategori"]
        cat_aum = float(aum_dict.get(cat, 0))  # O kategorinin Toplam Hacmi

        if val > 0:
            links.append({
                "source": name_to_idx[INFLOW_NODE],
                "target": name_to_idx[cat],
                "value": val,
                "type": "inflow",
                "cat_aum": cat_aum  # Link'in içine gömüyoruz
            })
        elif val < 0:
            links.append({
                "source": name_to_idx[cat],
                "target": name_to_idx[OUTFLOW_NODE],
                "value": abs(val),
                "type": "outflow",
                "cat_aum": cat_aum  # Link'in içine gömüyoruz
            })

    return {"nodes": nodes, "links": links}


# --- 9. ENDPOINT: Portföy Kıyaslama Grafiği (Base 100) ---
@app.get("/api/portfolio/chart")
def get_portfolio_chart(funds: str = "", start: str = "", end: str = ""):
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return []

    try:
        pivot_df = f_df.pivot_table(
            index="tarih", columns="FONKODU", values="FIYAT")
        pivot_df = pivot_df.ffill().dropna(axis=1, how='all')

        if pivot_df.empty:
            return []

        base_prices = pivot_df.iloc[0]
        index_df = (pivot_df / base_prices) * 100
        market_df = get_market_data(start, end)

        if not market_df.empty:
            base_gold = market_df['gold_usd'].iloc[0]
            base_usd = market_df['usd_try'].iloc[0]
            market_df['gold_idx'] = (market_df['gold_usd'] / base_gold) * 100
            market_df['usd_idx'] = (market_df['usd_try'] / base_usd) * 100

        result = []
        fund_list = [f.strip() for f in funds.split(",")] if funds else []

        for date, row in index_df.iterrows():
            tefas_val = row.mean()
            valid_funds = [
                f for f in fund_list if f in row.index and not pd.isna(row[f])]
            port_val = row[valid_funds].mean() if valid_funds else 100.0

            # Ham verileri ve indeksleri çekiyoruz
            has_market = not market_df.empty and date in market_df.index
            gold_val = float(market_df.loc[date, 'gold_idx']) if has_market else (
                result[-1]["gold"] if result else 100.0)
            usd_val = float(market_df.loc[date, 'usd_idx']) if has_market else (
                result[-1]["usd"] if result else 100.0)

            # Hover'da görünecek ham fiyatlar
            raw_gold = float(
                market_df.loc[date, 'gold_usd']) if has_market else 0
            raw_usd = float(
                market_df.loc[date, 'usd_try']) if has_market else 0

            result.append({
                "date": date.strftime('%Y-%m-%d'),
                "portfolio": round(port_val, 2),
                "tefas": round(tefas_val, 2),
                "gold": round(gold_val, 2),
                "usd": round(usd_val, 2),
                "raw": {
                    "gold": round(raw_gold, 2),
                    "usd": round(raw_usd, 2)
                }
            })

        return result
    except Exception as e:
        print("Chart Error:", e)
        return []


# ==========================================
# 📊 RISK & RETURN ANALYTICS ENDPOINTS
# ==========================================

def _basket_for(current_user: User, db: Session) -> list[str]:
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).first()
    if not portfolio:
        return []
    items = db.query(PortfolioItem).filter(PortfolioItem.portfolio_id == portfolio.id).all()
    return [i.fund_code for i in items]


@app.get("/api/risk/sharpe")
def api_sharpe(funds: str = "", start: str = "", end: str = "",
               rf: float = rm.DEFAULT_RF_ANNUAL):
    """Sharpe + Sortino for either an explicit basket or each fund individually."""
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return {"funds": [], "portfolio": None}
    prices = rm._pivot_prices(f_df)
    codes = [c.strip() for c in funds.split(",") if c.strip()] if funds else []

    per_fund = []
    for c in (codes if codes else prices.columns[:50]):
        if c not in prices.columns:
            continue
        r = prices[c].pct_change().dropna()
        per_fund.append({
            "code": c,
            "sharpe": rm.sharpe_ratio(r, rf),
            "sortino": rm.sortino_ratio(r, rf),
            "volatility": float(r.std(ddof=1) * np.sqrt(rm.TRADING_DAYS)) if not r.empty else None,
        })

    portfolio_block = None
    if codes:
        port_returns = rm.portfolio_returns(prices, codes)
        portfolio_block = {
            "sharpe": rm.sharpe_ratio(port_returns, rf),
            "sortino": rm.sortino_ratio(port_returns, rf),
            "volatility": float(port_returns.std(ddof=1) * np.sqrt(rm.TRADING_DAYS)) if not port_returns.empty else None,
        }

    # JSON-safe NaN
    def _clean(v):
        if v is None: return None
        try:
            return None if pd.isna(v) else round(float(v), 4)
        except Exception:
            return v
    for row in per_fund:
        row["sharpe"] = _clean(row["sharpe"])
        row["sortino"] = _clean(row["sortino"])
        row["volatility"] = _clean(row["volatility"])
    if portfolio_block:
        portfolio_block = {k: _clean(v) for k, v in portfolio_block.items()}

    return {"funds": per_fund, "portfolio": portfolio_block, "rf": rf}


@app.get("/api/risk/real-return")
def api_real_return(funds: str = "", start: str = "", end: str = ""):
    """Base-100 nominal vs CPI-deflated (real) portfolio index."""
    f_df = get_filtered_df(start, end)
    if f_df.empty or _cpi.empty:
        return {"series": [], "summary": {}}
    prices = rm._pivot_prices(f_df)
    codes = [c.strip() for c in funds.split(",") if c.strip()]
    cols = [c for c in codes if c in prices.columns] or list(prices.columns)
    base = prices[cols].iloc[0]
    nominal = (prices[cols] / base * 100).mean(axis=1)
    real = rm.real_return_series(nominal, _cpi)

    series = []
    for date in nominal.index:
        series.append({
            "date": date.strftime("%Y-%m-%d"),
            "nominal": round(float(nominal.loc[date]), 2),
            "real": round(float(real.loc[date]), 2) if date in real.index and not pd.isna(real.loc[date]) else None,
        })
    summary = {
        "nominal_return": round(float(nominal.iloc[-1] / 100 - 1), 4) if not nominal.empty else None,
        "real_return": round(float(real.iloc[-1] / 100 - 1), 4) if not real.empty else None,
    }
    return {"series": series, "summary": summary}


@app.get("/api/risk/drawdown")
def api_drawdown(funds: str = "", start: str = "", end: str = ""):
    """Maximum peak-to-trough decline for the basket and an underwater curve."""
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return {"mdd": 0, "underwater": []}
    prices = rm._pivot_prices(f_df)
    codes = [c.strip() for c in funds.split(",") if c.strip()]
    cols = [c for c in codes if c in prices.columns] or list(prices.columns)
    base = prices[cols].iloc[0]
    index = (prices[cols] / base * 100).mean(axis=1)

    summary = rm.max_drawdown(index)
    running_peak = index.cummax()
    underwater = ((index - running_peak) / running_peak).fillna(0)
    return {
        **summary,
        "underwater": [
            {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
            for d, v in underwater.items()
        ],
    }


@app.get("/api/risk/correlation")
def api_correlation(funds: str = "", start: str = "", end: str = ""):
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return {"matrix": [], "score": None, "warnings": []}
    prices = rm._pivot_prices(f_df)
    codes = [c.strip() for c in funds.split(",") if c.strip()]
    if len(codes) < 2:
        return {"matrix": [], "score": None, "warnings": [], "avg_correlation": None}
    corr = rm.correlation_matrix(prices, codes)
    if corr.empty:
        return {"matrix": [], "score": None, "warnings": []}

    matrix = [
        {"row": r, "col": c, "value": round(float(corr.at[r, c]), 3)}
        for r in corr.index for c in corr.columns
    ]
    diagnostic = rm.diversification_score(corr)
    return {"matrix": matrix, "codes": list(corr.columns), **diagnostic}


@app.get("/api/risk/tax-impact")
def api_tax_impact(funds: str = "", start: str = "", end: str = ""):
    """For each fund: gross return, withholding rate, net-of-tax return."""
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return []
    codes = [c.strip() for c in funds.split(",") if c.strip()]
    if not codes:
        codes = list(f_df["FONKODU"].drop_duplicates().head(50))

    out = []
    for code in codes:
        sub = f_df[f_df["FONKODU"] == code].sort_values("tarih")
        if sub.empty:
            continue
        first = float(sub["FIYAT"].iloc[0])
        last = float(sub["FIYAT"].iloc[-1])
        gross = (last - first) / first if first else 0.0
        category = sub["ana_kategori"].iloc[0] if "ana_kategori" in sub.columns else None
        rate = rm.stopaj_rate(category)
        net = rm.net_of_tax_return(gross, category)
        out.append({
            "code": code,
            "category": category,
            "gross_return": round(gross, 4),
            "stopaj_rate": rate,
            "net_return": round(net, 4) if net == net else None,
        })
    out.sort(key=lambda r: r["net_return"] or 0, reverse=True)
    return out


@app.get("/api/sentiment/crowded")
def api_sentiment_crowded(start: str = "", end: str = "", window: int = 60):
    """Mean-reversion / crowded-trade indicator on category-level inflows."""
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return []
    z = rm.category_flow_zscore(f_df[["tarih", "ana_kategori", "net_giris_tl"]], window=window)
    return z.replace({np.nan: None}).to_dict(orient="records")


# ==========================================
# 🔐 AUTHENTICATION ENDPOINTS
# ==========================================

@app.post("/api/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=400, detail="Bu email adresi zaten kayıtlı.")

    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email,
                    hashed_password=hashed_password, full_name=user.full_name)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Kullanıcı oluşunca otomatik boş bir portföy de açalım
    new_portfolio = Portfolio(user_id=new_user.id, name="Ana Sepetim")
    db.add(new_portfolio)
    db.commit()

    return new_user


@app.post("/api/auth/login", response_model=Token)
def login(req: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=401, detail="Hatalı e-posta veya şifre.")

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "name": user.full_name}


@app.get("/api/auth/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    # React açıldığında "Ben kimim, oturumum açık mı?" diye buraya soracak
    return current_user


# ==========================================
# 💼 PORTFOLIO (SEPET) ENDPOINTS
# ==========================================

@app.get("/api/portfolio/basket")
def get_my_basket(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Kullanıcının sepetini bul
    portfolio = db.query(Portfolio).filter(
        Portfolio.user_id == current_user.id).first()
    if not portfolio:
        return {"funds": []}

    items = db.query(PortfolioItem).filter(
        PortfolioItem.portfolio_id == portfolio.id).all()
    fund_codes = [item.fund_code for item in items]
    return {"funds": fund_codes}


@app.post("/api/portfolio/basket")
def update_my_basket(basket: BasketUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Kullanıcının sepetini bul
    portfolio = db.query(Portfolio).filter(
        Portfolio.user_id == current_user.id).first()

    # 2. Eski sepetin içini tamamen temizle
    db.query(PortfolioItem).filter(
        PortfolioItem.portfolio_id == portfolio.id).delete()

    # 3. Frontend'den gelen yeni listeyi veritabanına yaz
    for code in basket.funds:
        new_item = PortfolioItem(portfolio_id=portfolio.id, fund_code=code)
        db.add(new_item)

    db.commit()
    return {"status": "success", "message": "Sepet başarıyla güncellendi", "funds": basket.funds}
