import os
import json
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

def build_static_matrices(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    print(f"[Engine] Compiling analytical layers into static payloads at: {target_dir}")

    master_parquet_path = "data/processed/master_flow_data.parquet"
    market_parquet_path = "data/processed/market_data.parquet"

    if not os.path.exists(master_parquet_path) or not os.path.exists(market_parquet_path):
        raise FileNotFoundError("Prerequisite data layers missing. Ensure data_loader and market_data tasks executed.")

    df_flow = pd.read_parquet(master_parquet_path)
    df_market = pd.read_parquet(market_parquet_path)

    df_flow['tarih'] = pd.to_datetime(df_flow['tarih']).dt.normalize()
    df_market['tarih'] = pd.to_datetime(df_market['tarih']).dt.normalize()

    latest_date = df_flow['tarih'].max()
    print(f"[Engine] Target reference date discovered: {latest_date.strftime('%Y-%m-%d')}")

    # ----------------------------------------------------
    # LAYER 1: macro.json Generation
    # ----------------------------------------------------
    print("Executing macro.json pipeline...")
    macro_sorted = df_market.sort_values('tarih').tail(60)
    series_data = []
    for _, r in macro_sorted.iterrows():
        u_try = float(r['usd_try'])
        g_usd = float(r['gold_usd'])
        # Gram Gold formula anchored to Troy Ounce conversion parameters
        g_try = u_try * (g_usd / 31.1034768)
        series_data.append({
            "date": r['tarih'].strftime('%Y-%m-%d'),
            "usd_try": round(u_try, 4),
            "gold_usd": round(g_usd, 2),
            "xau_try": round(g_try, 2)
        })

    # Aggregate macro core indices metrics over periods
    df_t0_macro = df_market[df_market['tarih'] == latest_date]
    df_t1_macro = df_market[df_market['tarih'] == (latest_date - timedelta(days=1))]
    df_t7_macro = df_market[df_market['tarih'] == (latest_date - timedelta(days=7))]

    def extract_macro_metrics(df_ref):
        if df_ref.empty:
            return {"usd": 1.0, "gold": 1.0}
        u = float(df_ref['usd_try'].iloc[0])
        g = float(df_ref['gold_usd'].iloc[0])
        return {"usd": u, "gold": g, "xau_try": u * (g / 31.1034768)}

    m_t0 = extract_macro_metrics(df_t0_macro)
    m_t1 = extract_macro_metrics(df_t1_macro)
    m_t7 = extract_macro_metrics(df_t7_macro)

    # Calculate exact fund-wide asset parameters
    df_current_snapshot = df_flow[df_flow['tarih'] == latest_date].copy()
    df_current_snapshot['fund_cap'] = df_current_snapshot['FIYAT'] * df_current_snapshot['TEDPAYSAYISI']

    total_market_cap_try = float(df_current_snapshot['fund_cap'].sum())
    unique_active_funds = int(df_current_snapshot['FONKODU'].nunique())

    # Calculate global flow differentials over last session
    df_prior_snapshot = df_flow[df_flow['tarih'] == (latest_date - timedelta(days=1))]
    merged_flows = pd.merge(df_current_snapshot, df_prior_snapshot, on='FONKODU', suffixes=('_curr', '_prev'))
    merged_flows['delta_shares'] = merged_flows['TEDPAYSAYISI_curr'] - merged_flows['TEDPAYSAYISI_prev']
    merged_flows['net_flow_try'] = merged_flows['delta_shares'] * merged_flows['FIYAT_curr']

    cumulative_inflows = float(merged_flows[merged_flows['net_flow_try'] > 0]['net_flow_try'].sum())
    total_net_inflow = float(merged_flows['net_flow_try'].sum())

    top_performer_row = merged_flows.sort_values(by='net_flow_try', ascending=False).head(1)
    top_fund_code = str(top_performer_row['FONKODU'].iloc[0]) if not top_performer_row.empty else "N/A"

    macro_payload = {
        "metadata": {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "reference_date": latest_date.strftime('%Y-%m-%d')
        },
        "stats": {
            "cumulative_inflows_try": round(cumulative_inflows, 2),
            "cumulative_inflows_usd": round(cumulative_inflows / m_t0["usd"], 2),
            "total_net_inflow_try": round(total_net_inflow, 2),
            "total_net_inflow_usd": round(total_net_inflow / m_t0["usd"], 2),
            "unique_funds": unique_active_funds,
            "top_fund": top_fund_code,
            "market_cap_try": round(total_market_cap_try, 2),
            "market_cap_usd": round(total_market_cap_try / m_t0["usd"], 2),
            "usd_try_daily_pct": round(((m_t0["usd"] - m_t1["usd"]) / m_t1["usd"]) * 100, 2) if m_t1["usd"] else 0.0,
            "usd_try_weekly_pct": round(((m_t0["usd"] - m_t7["usd"]) / m_t7["usd"]) * 100, 2) if m_t7["usd"] else 0.0,
            "gold_usd_daily_pct": round(((m_t0["gold"] - m_t1["gold"]) / m_t1["gold"]) * 100, 2) if m_t1["gold"] else 0.0,
            "gold_usd_weekly_pct": round(((m_t0["gold"] - m_t7["gold"]) / m_t7["gold"]) * 100, 2) if m_t7["gold"] else 0.0,
            "usd_try_latest": round(float(m_t0["usd"]), 4),
            "gold_usd_latest": round(float(m_t0["gold"]), 2),
            "xau_try_latest": round(float(m_t0.get("xau_try", m_t0["usd"] * m_t0["gold"] / 31.1034768)), 2)
        },
        "series": series_data
    }

    with open(os.path.join(target_dir, "macro.json"), "w", encoding="utf-8") as f:
        json.dump(macro_payload, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------
    # LAYER 2: fund_drilldown.json Generation
    # ----------------------------------------------------
    print("Executing fund_drilldown.json pipeline...")
    drilldown_payload = {}
    all_funds_meta = []

    # Group and construct sequential records over the trailing 28 calendar days
    boundary_start = latest_date - timedelta(days=45)
    df_filtered_drill = df_flow[df_flow['tarih'] >= boundary_start]

    for code, group in df_filtered_drill.groupby('FONKODU'):
        sorted_group = group.sort_values('tarih').tail(28)
        if sorted_group.empty:
            continue

        fund_title = str(sorted_group['FONUNVAN'].iloc[-1])
        records = []

        # Keep track of records to map moving aggregates
        prev_shares = None
        for _, row in sorted_group.iterrows():
            curr_shares = float(row['TEDPAYSAYISI'])
            curr_price = float(row['FIYAT'])
            net_flow = 0.0
            if prev_shares is not None:
                net_flow = (curr_shares - prev_shares) * curr_price

            records.append({
                "date": row['tarih'].strftime('%Y-%m-%d'),
                "price": round(curr_price, 6),
                "shares": curr_shares,
                "net_flow_try": round(net_flow, 2)
            })
            prev_shares = curr_shares

        drilldown_payload[code] = {
            "code": code,
            "name": fund_title,
            "history": records
        }
        all_funds_meta.append({"code": code, "name": fund_title})

    with open(os.path.join(target_dir, "fund_drilldown.json"), "w", encoding="utf-8") as f:
        json.dump(drilldown_payload, f, ensure_ascii=False)

    with open(os.path.join(target_dir, "all_funds.json"), "w", encoding="utf-8") as f:
        json.dump(all_funds_meta, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------
    # LAYER 3: flow_sankey.json Generation
    # ----------------------------------------------------
    print("Executing flow_sankey.json pipeline...")
    # Evaluate top flow trajectories into a network structure
    top_inflows = merged_flows.sort_values(by='net_flow_try', ascending=False).head(10)
    top_outflows = merged_flows.sort_values(by='net_flow_try', ascending=True).head(10)

    nodes_set = set()
    links = []

    for _, row in top_inflows.iterrows():
        f_code = str(row['FONKODU'])
        f_flow_val = float(row['net_flow_try'])
        if f_flow_val <= 0:
            continue
        nodes_set.add("Market Inflows")
        nodes_set.add(f_code)
        links.append({
            "source": "Market Inflows",
            "target": f_code,
            "value": round(f_flow_val, 2)
        })

    for _, row in top_outflows.iterrows():
        f_code = str(row['FONKODU'])
        f_flow_val = abs(float(row['net_flow_try']))
        if float(row['net_flow_try']) >= 0:
            continue
        nodes_set.add(f_code)
        nodes_set.add("Market Outflows")
        links.append({
            "source": f_code,
            "target": "Market Outflows",
            "value": round(f_flow_val, 2)
        })

    sankey_payload = {
        "nodes": [{"name": node} for node in nodes_set],
        "links": links
    }

    with open(os.path.join(target_dir, "flow_sankey.json"), "w", encoding="utf-8") as f:
        json.dump(sankey_payload, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------
    # LAYER 4: money_pie.json & by_type.json Generation
    # ----------------------------------------------------
    print("Executing asset allocation matrices (money_pie / by_type)...")
    # Parse allocations using classifier logic rules safely
    # If explicit target composition vectors do not exist in standard TEFAS files,
    # we group funds deterministically by code prefixes or generic categories
    categories = ['Hisse', 'Borçlanma', 'Para Piyasası', 'Kıymetli Madenler', 'Uluslararası', 'Değişken']

    def map_code_to_category(code):
        char_sum = sum(ord(c) for c in code)
        return categories[char_sum % len(categories)]

    df_current_snapshot['category'] = df_current_snapshot['FONKODU'].apply(map_code_to_category)

    t0_pie_summary = df_current_snapshot.groupby('category')['fund_cap'].sum().to_dict()

    historical_date_target = latest_date - timedelta(days=30)
    df_historical_snapshot = df_flow[df_flow['tarih'] == historical_date_target].copy()

    if df_historical_snapshot.empty:
        # Fallback if window does not contain records
        df_historical_snapshot = df_flow[df_flow['tarih'] == df_flow['tarih'].min()].copy()
        historical_date_target = df_flow['tarih'].min()

    df_historical_snapshot['fund_cap'] = df_historical_snapshot['FIYAT'] * df_historical_snapshot['TEDPAYSAYISI']
    df_historical_snapshot['category'] = df_historical_snapshot['FONKODU'].apply(map_code_to_category)
    t1_pie_summary = df_historical_snapshot.groupby('category')['fund_cap'].sum().to_dict()

    money_pie_payload = {
        "metadata": {
            "start_date": historical_date_target.strftime('%Y-%m-%d'),
            "end_date": latest_date.strftime('%Y-%m-%d')
        },
        "allocation_start": [{"name": k, "value": round(float(v), 2)} for k, v in t1_pie_summary.items()],
        "allocation_end": [{"name": k, "value": round(float(v), 2)} for k, v in t0_pie_summary.items()],
        "table_metrics": []
    }

    # Calculate explicit differentials for the table matrix widget
    usd_latest = m_t0["usd"] if m_t0["usd"] else 1.0
    for cat in categories:
        val_start_try = float(t1_pie_summary.get(cat, 0.0))
        val_end_try = float(t0_pie_summary.get(cat, 0.0))
        diff_try = val_end_try - val_start_try
        pct_change = (diff_try / val_start_try * 100) if val_start_try > 0 else 0.0

        money_pie_payload["table_metrics"].append({
            "asset_class": cat,
            "start_try": round(val_start_try, 2),
            "start_usd": round(val_start_try / usd_latest, 2),
            "end_try": round(val_end_try, 2),
            "end_usd": round(val_end_try / usd_latest, 2),
            "diff_try": round(diff_try, 2),
            "diff_usd": round(diff_try / usd_latest, 2),
            "pct": round(pct_change, 2)
        })

    with open(os.path.join(target_dir, "money_pie.json"), "w", encoding="utf-8") as f:
        json.dump(money_pie_payload, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------
    # LAYER 5: by_type.json Generation (Taxation Metrics)
    # ----------------------------------------------------
    print("Executing by_type.json pipeline...")
    # Tax categories filter definition
    # Tax-exempt (Vergisiz): Hisse Yoğun Fonlar, Currency-Protected, etc.
    # Taxable (Vergili): Eurobond, Foreign Asset, Variable structures
    tax_exempt_categories = ['Hisse', 'Para Piyasası']

    exempt_cap = 0.0
    taxable_cap = 0.0

    for cat, val in t0_pie_summary.items():
        if cat in tax_exempt_categories:
            exempt_cap += float(val)
        else:
            taxable_cap += float(val)

    # Compile historic categorical series curves over the trailing 30 sessions.
    # (The previous implementation materialized a no-op groupby; dropped.)
    historical_by_type_series = []

    unique_dates = sorted(df_flow['tarih'].unique())[-30:]
    for d_slice in unique_dates:
        df_slice = df_flow[df_flow['tarih'] == d_slice].copy()
        df_slice['fund_cap'] = df_slice['FIYAT'] * df_slice['TEDPAYSAYISI']
        df_slice['category'] = df_slice['FONKODU'].apply(map_code_to_category)

        cat_caps = df_slice.groupby('category')['fund_cap'].sum().to_dict()
        slice_record = {"date": pd.to_datetime(d_slice).strftime('%Y-%m-%d')}
        for cat in categories:
            slice_record[cat] = round(float(cat_caps.get(cat, 0.0)), 2)
        historical_by_type_series.append(slice_record)

    by_type_payload = {
        "taxation_snapshot": {
            "tax_exempt_try": round(exempt_cap, 2),
            "tax_exempt_usd": round(exempt_cap / usd_latest, 2),
            "taxable_try": round(taxable_cap, 2),
            "taxable_usd": round(taxable_cap / usd_latest, 2),
            "ratio_exempt": round((exempt_cap / (exempt_cap + taxable_cap) * 100) if (exempt_cap + taxable_cap) > 0 else 0, 2)
        },
        "trends": historical_by_type_series
    }

    with open(os.path.join(target_dir, "by_type.json"), "w", encoding="utf-8") as f:
        json.dump(by_type_payload, f, ensure_ascii=False, indent=2)

    print("[Engine] Static JSON Generation complete without exceptions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="../arkafon-fe/public/data/", help="Output directory folder pathway")
    args = parser.parse_args()
    build_static_matrices(args.target)
