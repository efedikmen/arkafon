"""Daily scraper + pipeline orchestrator.

Pipeline stage 1 of 4 (**updater** -> data_loader -> market_data -> export_json).

Walks every business day since TEFAS opened (2020-08-24), figures out
which dates are missing on disk, fetches them from TEFAS, and writes one
parquet per session under ``data/raw/``. After scraping, if any new days
landed, runs the rest of the pipeline in-process.

Why in-process and not subprocess: the prior version shelled out to
``python -m src.data_loader`` and ``python -m src.export_json`` via
``subprocess.run``. That added startup latency, hid exception tracebacks
behind a wall of stdout, and made error handling brittle. Direct
imports give us a real traceback and let the GitHub Actions log
surface the exact failure line.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from glob import glob
from typing import List

import pandas as pd
from tefas_client import Tefas

from src.config import RAW_DATA_DIR

log = logging.getLogger(__name__)

# TEFAS' public history starts here. Backfilling earlier dates returns nothing.
TEFAS_EPOCH = date(2020, 8, 24)

# Seconds to sleep between consecutive TEFAS fetches; we are a polite client.
FETCH_SLEEP = 3


def _existing_dates() -> set[date]:
    """Set of trade dates already scraped to disk."""
    seen: set[date] = set()
    for path in glob(os.path.join(RAW_DATA_DIR, "tefas_data_*.parquet")):
        name = os.path.basename(path)
        date_str = name.removeprefix("tefas_data_").removesuffix(".parquet")
        try:
            seen.add(datetime.strptime(date_str, "%d.%m.%Y").date())
        except ValueError:
            log.warning("Skipping un-parseable filename: %s", name)
    return seen


def _missing_business_days(seen: set[date]) -> List[date]:
    expected = set(pd.bdate_range(start=TEFAS_EPOCH, end=date.today()).date)
    return sorted(expected - seen)


def fetch_daily_data() -> bool:
    """Scrape every business day we don't yet have. Returns True if anything new."""
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    log.info("Arkafon updater started at %s", datetime.now().isoformat(timespec="seconds"))

    missing = _missing_business_days(_existing_dates())
    if not missing:
        log.info("All sessions present, nothing to fetch.")
        return False

    log.info("Missing sessions: %d", len(missing))

    with Tefas() as tefas:
        for target in missing:
            date_str = target.strftime("%d.%m.%Y")
            out = os.path.join(RAW_DATA_DIR, f"tefas_data_{date_str}.parquet")
            log.info("Fetching %s ...", date_str)
            try:
                data = tefas.fetch(start_date=target, end_date=target)
            except Exception as exc:  # noqa: BLE001 — tefas-client raises broad types
                log.error("Fetch failed for %s: %s: %s", date_str, type(exc).__name__, exc)
                time.sleep(FETCH_SLEEP)
                continue

            if data:
                rows = [
                    {
                        "FONKODU": code,
                        "FONUNVAN": fund.title,
                        "FIYAT": h.price,
                        "TEDPAYSAYISI": h.number_of_shares,
                    }
                    for code, fund in data.items()
                    for h in fund.history
                ]
                if rows:
                    pd.DataFrame(rows).to_parquet(out)
                    log.info("  wrote %d rows to %s", len(rows), os.path.basename(out))
            else:
                # Holiday — write a sentinel empty file so we don't retry forever.
                pd.DataFrame(columns=["FONKODU", "FONUNVAN", "FIYAT", "TEDPAYSAYISI"]).to_parquet(out)
                log.info("  %s returned no rows (holiday?); wrote sentinel", date_str)

            time.sleep(FETCH_SLEEP)

    return True


def run_pipeline() -> None:
    """Run data_loader -> market_data -> export_json in-process."""
    # Local imports keep heavy modules (pandas, yfinance) off the path
    # when the updater is invoked just to scrape.
    from src import data_loader, export_json, market_data

    log.info("Running data_loader...")
    data_loader.build_master_data()

    log.info("Running market_data...")
    market_data.main()

    log.info("Running export_json...")
    export_json.build_static_matrices("../arkafon-fe/public/data/")

    log.info("Pipeline complete; static payloads refreshed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if fetch_daily_data():
        run_pipeline()
    else:
        log.info("Nothing to do; exiting cleanly.")
