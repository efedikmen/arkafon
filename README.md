# Arkafon Backend

> **Static matrix compiler for the ArkaFon Jamstack pipeline.** Reads TEFAS parquet snapshots and currency markers, emits versioned JSON payloads consumed by the frontend at the edge. Zero servers at runtime.

## Architecture

ArkaFon runs as a fully serverless Jamstack stack. The backend is a build-time
compiler, not a service. There is no API process, no SQLite database, no
authentication layer, and no portfolio routing — those subsystems have been
removed.

The daily execution loop:

1. A scheduled GitHub Actions workflow wakes at **19:15 UTC**.
2. `src/updater.py` scrapes the latest TEFAS `.parquet` files into `data/raw/`.
3. `src/data_loader.py` compiles them into a monolithic
   `data/processed/master_flow_data.parquet`.
4. `src/market_data.py` refreshes the USD/TRY and XAU/USD markers into
   `data/processed/market_data.parquet`.
5. `src/export_json.py` rolls everything up into five static JSON payloads and
   writes them directly into the frontend repo at
   `../arkafon-fe/public/data/*.json`.
6. The frontend repo is committed and pushed; Vercel detects the change and
   redeploys the static site to its edge.

## Static payloads

`src/export_json.py --target <dir>` writes the following files into `<dir>`:

| File | Purpose |
| --- | --- |
| `macro.json` | KPI stats (cumulative inflows, net inflow, top fund, market cap) and a trailing 60-day USD/TRY + Gram Gold (TRY/g) series. |
| `fund_drilldown.json` | Per-fund 28-day ledger: NAV price, circulating shares, net capital handoff (Δshares × price). |
| `all_funds.json` | Flat lookup index `{code, name}` for the search box. |
| `flow_sankey.json` | Top 10 inflow + top 10 outflow links for the flow map. |
| `money_pie.json` | Categorical allocation snapshots (T0 vs. T-30) plus a TRY/USD diff table. |
| `by_type.json` | Taxation split (`tax_exempt` vs `taxable`) and a 30-day stacked category trend. |

Asset categories are deterministically assigned from `FONKODU` via the
classifier in `export_json.py` (`Hisse`, `Borçlanma`, `Para Piyasası`,
`Kıymetli Madenler`, `Uluslararası`, `Değişken`). `Hisse` and `Para Piyasası`
are treated as tax-exempt (`%0 Stopaj`); the rest fall under the taxable
framework.

## Layout

```text
arkafon-be/
├── data/
│   ├── raw/                 # TEFAS .parquet snapshots (git-ignored)
│   └── processed/           # master_flow_data.parquet, market_data.parquet
├── src/
│   ├── updater.py           # TEFAS scraper
│   ├── data_loader.py       # ETL into master_flow_data.parquet
│   ├── market_data.py       # USD/TRY + Gold ingest
│   ├── classifier.py        # category mapping helpers
│   ├── config.py            # paths & env loading
│   └── export_json.py       # static JSON compiler (entry point of the build)
├── tests/
├── requirements.txt
└── README.md
```

## Running the pipeline locally

```bash
python3 -m venv .arkafon_env
source .arkafon_env/bin/activate
pip install -r requirements.txt

# 1. Pull fresh TEFAS data (skip if data/raw/ is already populated)
python -m src.updater

# 2. Compile master parquet + market data
python -m src.data_loader
python -m src.market_data

# 3. Emit static payloads into the FE repo
python -m src.export_json --target ../arkafon-fe/public/data/
```

`export_json.py` is idempotent: every run fully overwrites the target JSON
files from the current parquet state. Diff the FE repo, commit, push — Vercel
takes it from there.

## Tests

```bash
pytest -q
```

## Configuration

There is no runtime configuration. The build expects two parquet files to exist
under `data/processed/`:

- `master_flow_data.parquet` — columns: `tarih`, `FONKODU`, `FONUNVAN`,
  `FIYAT`, `TEDPAYSAYISI`.
- `market_data.parquet` — columns: `tarih`, `usd_try`, `gold_usd`.

If either is missing, `export_json.py` raises `FileNotFoundError` and the GitHub
Actions run fails loudly. The currency conversion uses the Troy-ounce constant
(31.1034768 g/oz) to derive Gram Gold from `usd_try × gold_usd / 31.1034768`.

## License

MIT.
