from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import os
from datetime import timedelta
from src.config import MASTER_DATA_PATH
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from src.db import get_db, User, Portfolio, PortfolioItem, UserCreate, UserLogin, UserResponse, Token, BasketUpdate
from src.auth import get_password_hash, verify_password, create_access_token, get_current_user
from src.market_data import get_market_data
from src.portfolio_routes import register_portfolio_routes

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


def get_filtered_df(start: str = "", end: str = "", categories: str = ""):
    f_df = df.copy()
    if f_df.empty:
        return f_df
    if categories:
        cat_list = [c.strip() for c in categories.split(",")]
        f_df = f_df[f_df["ana_kategori"].isin(cat_list)]
    if start and start != "undefined":
        f_df = f_df[f_df["tarih"] >= pd.to_datetime(start)]
    if end and end != "undefined":
        f_df = f_df[f_df["tarih"] <= pd.to_datetime(end)]
    return f_df


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


@app.get("/api/macro/trend")
def get_macro_trend(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []
    trend = f_df.groupby("tarih")["net_giris_tl"].sum().reset_index()
    trend = trend.sort_values("tarih")
    trend["tarih"] = trend["tarih"].dt.strftime('%Y-%m-%d')
    trend["kumulatif_giris"] = trend["net_giris_tl"].cumsum()
    return trend.to_dict(orient="records")


@app.get("/api/macro/top10")
def get_macro_top10(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []
    top = f_df.groupby(["FONKODU", "FONUNVAN"])["net_giris_tl"].sum().reset_index()
    top = top.sort_values("net_giris_tl", ascending=False).head(10)
    return top.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "net_giris_tl": "netInflow"}).to_dict(orient="records")


@app.get("/api/macro/universe")
def get_macro_universe(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return []
    grouped = f_df.groupby(["FONKODU", "FONUNVAN", "ana_kategori"], dropna=False).agg(
        netInflow=('net_giris_tl', 'sum'),
        first_price=('FIYAT', 'first'),
        last_price=('FIYAT', 'last'),
    ).reset_index()
    grouped['perfYTD'] = (grouped['last_price'] - grouped['first_price']) / grouped['first_price']
    grouped['perfYTD'] = grouped['perfYTD'].replace([np.inf, -np.inf], np.nan).fillna(0)
    grouped['ana_kategori'] = grouped['ana_kategori'].fillna("Diğer")
    grouped = grouped.sort_values("netInflow", ascending=False).head(25)
    return grouped.rename(columns={"FONKODU": "code", "FONUNVAN": "name", "ana_kategori": "category"}).to_dict(orient="records")


@app.get("/api/fund/list")
def get_fund_list(q: str = "", page: int = 1, page_size: int = 50):
    if df.empty:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    funds = df[["FONKODU", "FONUNVAN"]].drop_duplicates().dropna()
    if q:
        ql = q.strip().lower()
        mask = (funds["FONKODU"].str.lower().str.contains(ql, na=False) |
                funds["FONUNVAN"].str.lower().str.contains(ql, na=False))
        funds = funds[mask]
    total = int(len(funds))
    page = max(1, page); page_size = max(1, min(500, page_size))
    start = (page - 1) * page_size; end = start + page_size
    return {
        "items": funds.iloc[start:end].rename(columns={"FONKODU": "code", "FONUNVAN": "name"}).to_dict(orient="records"),
        "total": total, "page": page, "page_size": page_size,
    }


@app.get("/api/fund/{fund_code}")
def get_fund_details(fund_code: str, start: str = "", end: str = ""):
    f_df = df[df["FONKODU"] == fund_code].sort_values("tarih")
    if f_df.empty:
        return {"error": "Fon bulunamadı"}
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
        "chart": chart_data.rename(columns={"tarih": "date", "FIYAT": "price", "net_giris_tl": "flow"}).to_dict(orient="records"),
    }


@app.get("/api/macro/flow")
def get_macro_flow(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}
    flow_df = f_df.groupby(["ana_kategori", "FONKODU"])["net_giris_tl"].sum().reset_index()
    flow_df = flow_df[flow_df["net_giris_tl"] > 0]
    flow_df = flow_df.sort_values("net_giris_tl", ascending=False).head(20)
    all_names = pd.concat([flow_df["ana_kategori"], flow_df["FONKODU"]]).unique().tolist()
    nodes = [{"name": name} for name in all_names]
    name_to_idx = {name: i for i, name in enumerate(all_names)}
    links = [{"source": name_to_idx[r["ana_kategori"]], "target": name_to_idx[r["FONKODU"]],
              "value": round(float(r["net_giris_tl"]), 2)} for _, r in flow_df.iterrows()]
    return {"nodes": nodes, "links": links}


@app.get("/api/macro/flow-sankey")
def get_macro_flow_sankey(start: str = "", end: str = "", categories: str = ""):
    f_df = get_filtered_df(start, end, categories)
    if f_df.empty:
        return {"nodes": [], "links": []}
    flow_df = f_df.groupby("ana_kategori")["net_giris_tl"].sum().reset_index()
    flow_df = flow_df[flow_df["net_giris_tl"].abs() > 1000]
    if flow_df.empty:
        return {"nodes": [], "links": []}
    end_dt = pd.to_datetime(end) if end and end != "undefined" else df["tarih"].max()
    cat_list = flow_df["ana_kategori"].tolist()
    aum_df = df[(df["ana_kategori"].isin(cat_list)) & (df["tarih"] <= end_dt)]
    aum_dict = aum_df.groupby("ana_kategori")["net_giris_tl"].sum().to_dict()
    INFLOW_NODE = "Sermaye Girişi"; OUTFLOW_NODE = "Sermaye Çıkışı"
    all_names = [INFLOW_NODE, OUTFLOW_NODE] + cat_list
    nodes = [{"name": n, "aum": aum_dict.get(n, 0)} for n in all_names]
    name_to_idx = {n: i for i, n in enumerate(all_names)}
    links = []
    for _, row in flow_df.iterrows():
        val = float(row["net_giris_tl"]); cat = row["ana_kategori"]
        cat_aum = float(aum_dict.get(cat, 0))
        if val > 0:
            links.append({"source": name_to_idx[INFLOW_NODE], "target": name_to_idx[cat],
                          "value": val, "type": "inflow", "cat_aum": cat_aum})
        elif val < 0:
            links.append({"source": name_to_idx[cat], "target": name_to_idx[OUTFLOW_NODE],
                          "value": abs(val), "type": "outflow", "cat_aum": cat_aum})
    return {"nodes": nodes, "links": links}


@app.get("/api/portfolio/chart")
def get_portfolio_chart(funds: str = "", start: str = "", end: str = ""):
    f_df = get_filtered_df(start, end)
    if f_df.empty:
        return []
    try:
        pivot_df = f_df.pivot_table(index="tarih", columns="FONKODU", values="FIYAT")
        pivot_df = pivot_df.ffill().dropna(axis=1, how='all')
        if pivot_df.empty:
            return []
        base_prices = pivot_df.iloc[0]
        index_df = (pivot_df / base_prices) * 100
        market_df = get_market_data(start, end)
        if not market_df.empty:
            base_gold = market_df['gold_usd'].iloc[0]; base_usd = market_df['usd_try'].iloc[0]
            market_df['gold_idx'] = (market_df['gold_usd'] / base_gold) * 100
            market_df['usd_idx'] = (market_df['usd_try'] / base_usd) * 100
        result = []
        fund_list = [f.strip() for f in funds.split(",")] if funds else []
        for date, row in index_df.iterrows():
            tefas_val = row.mean()
            valid = [f for f in fund_list if f in row.index and not pd.isna(row[f])]
            port_val = row[valid].mean() if valid else 100.0
            has_market = not market_df.empty and date in market_df.index
            gold_val = float(market_df.loc[date, 'gold_idx']) if has_market else (result[-1]["gold"] if result else 100.0)
            usd_val = float(market_df.loc[date, 'usd_idx']) if has_market else (result[-1]["usd"] if result else 100.0)
            raw_gold = float(market_df.loc[date, 'gold_usd']) if has_market else 0
            raw_usd = float(market_df.loc[date, 'usd_try']) if has_market else 0
            result.append({"date": date.strftime('%Y-%m-%d'), "portfolio": round(port_val, 2),
                           "tefas": round(tefas_val, 2), "gold": round(gold_val, 2), "usd": round(usd_val, 2),
                           "raw": {"gold": round(raw_gold, 2), "usd": round(raw_usd, 2)}})
        return result
    except Exception as e:
        print("Chart Error:", e)
        return []


# AUTH
@app.post("/api/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(400, "Bu email adresi zaten kayıtlı.")
    new_user = User(email=user.email, hashed_password=get_password_hash(user.password), full_name=user.full_name)
    db.add(new_user); db.commit(); db.refresh(new_user)
    db.add(Portfolio(user_id=new_user.id, name="Ana Sepetim")); db.commit()
    return new_user


@app.post("/api/auth/login", response_model=Token)
def login(req: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(401, "Hatalı e-posta veya şifre.")
    return {"access_token": create_access_token(data={"sub": user.email}),
            "token_type": "bearer", "name": user.full_name}


@app.get("/api/auth/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


# Multi-basket CRUD lives in src/portfolio_routes.py.
register_portfolio_routes(app)
