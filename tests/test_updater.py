"""Tests for src.updater.

The TEFAS-fetching part is out of scope (network + third-party client).
The pure logic — figuring out which sessions we already have on disk and
which business days are missing — is what we test here.
"""
import os
from datetime import date

from src.updater import _existing_dates, _missing_business_days


# ────────────────────────────────────────────────────────────────────────
# _existing_dates
# ────────────────────────────────────────────────────────────────────────

def test_existing_dates_parses_wellformed_filenames(tmp_data_dirs):
    raw = tmp_data_dirs["raw"]
    # Touch three valid snapshot files.
    for date_str in ("01.01.2024", "15.06.2024", "31.12.2024"):
        with open(os.path.join(raw, f"tefas_data_{date_str}.parquet"), "wb") as f:
            f.write(b"")
    seen = _existing_dates()
    assert seen == {date(2024, 1, 1), date(2024, 6, 15), date(2024, 12, 31)}


def test_existing_dates_skips_garbage_filenames(tmp_data_dirs):
    raw = tmp_data_dirs["raw"]
    # One valid + several invalid filenames.
    for name in (
        "tefas_data_01.01.2024.parquet",
        "tefas_data_garbage.parquet",
        "tefas_data_2024-01-01.parquet",   # wrong delimiter
        "other_file.parquet",                # different prefix
    ):
        with open(os.path.join(raw, name), "wb") as f:
            f.write(b"")
    seen = _existing_dates()
    # Only the well-formed one survives.
    assert seen == {date(2024, 1, 1)}


def test_existing_dates_empty_when_dir_has_no_parquets(tmp_data_dirs):
    assert _existing_dates() == set()


# ────────────────────────────────────────────────────────────────────────
# _missing_business_days
# ────────────────────────────────────────────────────────────────────────

def test_missing_business_days_returns_empty_when_all_seen(monkeypatch):
    """If every business day from TEFAS_EPOCH through today is already
    on disk, the missing set is empty."""
    import pandas as pd
    from src import updater

    today = date(2024, 1, 10)
    monkeypatch.setattr(updater, "date", _FrozenDate(today))
    seen = set(pd.bdate_range(start=updater.TEFAS_EPOCH, end=today).date)
    assert _missing_business_days(seen) == []


def test_missing_business_days_finds_gaps(monkeypatch):
    """Drop a known business day from the seen set; it must come back as missing."""
    import pandas as pd
    from src import updater

    today = date(2024, 1, 10)
    monkeypatch.setattr(updater, "date", _FrozenDate(today))
    all_bdays = set(pd.bdate_range(start=updater.TEFAS_EPOCH, end=today).date)
    gap_day = date(2024, 1, 8)  # Monday — a business day in the range
    assert gap_day in all_bdays  # sanity
    seen = all_bdays - {gap_day}
    missing = _missing_business_days(seen)
    assert missing == [gap_day]


def test_missing_business_days_returns_sorted(monkeypatch):
    """Output is sorted ascending so the scrape walks history chronologically."""
    import pandas as pd
    from src import updater

    today = date(2024, 1, 10)
    monkeypatch.setattr(updater, "date", _FrozenDate(today))
    all_bdays = sorted(pd.bdate_range(start=updater.TEFAS_EPOCH, end=today).date)
    # Pretend we have only the first session; everything else is missing.
    seen = {all_bdays[0]}
    missing = _missing_business_days(seen)
    assert missing == sorted(missing)


# ────────────────────────────────────────────────────────────────────────
# Test helpers
# ────────────────────────────────────────────────────────────────────────

class _FrozenDate:
    """Stand-in for `datetime.date` that returns a fixed `today()`."""
    def __init__(self, today_value: date):
        self._today = today_value

    def today(self) -> date:
        return self._today

    # Forward any other attribute access (date.fromisoformat, etc.) to the real class.
    def __getattr__(self, name):
        return getattr(date, name)
