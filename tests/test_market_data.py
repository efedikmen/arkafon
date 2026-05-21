"""Tests for src.market_data.

We don't hit the network — fetch_markers and main are intentionally
out of scope. The high-value logic here is merge_and_write: it must
be idempotent under re-runs and must dedupe by date (keep last) so a
mid-day re-fetch doesn't double-count or stale-overwrite the parquet.
"""
import os

import pandas as pd
import pytest

from src.market_data import _series_from_history, merge_and_write


# ────────────────────────────────────────────────────────────────────────
# _series_from_history
# ────────────────────────────────────────────────────────────────────────

def test_series_from_history_normalizes_index():
    """yfinance returns timezone-aware DatetimeIndex; we strip tz and
    normalize to midnight so the dates line up with master_flow_data."""
    raw = pd.DataFrame(
        {"Close": [30.0, 30.5, 31.0]},
        index=pd.to_datetime(
            ["2024-01-01 10:00:00+00:00", "2024-01-02 10:00:00+00:00", "2024-01-03 10:00:00+00:00"],
            utc=True,
        ),
    )
    out = _series_from_history(raw)
    assert all(t.tzinfo is None for t in out.index)
    assert all(t == t.normalize() for t in out.index)
    assert out.iloc[0] == 30.0


def test_series_from_history_dedupes_intraday_to_last():
    raw = pd.DataFrame(
        {"Close": [30.0, 30.5]},
        index=pd.to_datetime(["2024-01-01 10:00:00", "2024-01-01 16:00:00"]),
    )
    out = _series_from_history(raw)
    # Two intraday rows for the same date collapse to the last one.
    assert len(out) == 1
    assert out.iloc[0] == 30.5


# ────────────────────────────────────────────────────────────────────────
# merge_and_write — idempotency + dedup behavior
# ────────────────────────────────────────────────────────────────────────

def _frame(dates, usd, gold):
    return pd.DataFrame({
        "tarih":   pd.to_datetime(dates),
        "usd_try": usd,
        "gold_usd": gold,
    })


def test_merge_and_write_creates_file_on_first_run(tmp_data_dirs):
    fresh = _frame(["2024-01-01", "2024-01-02"], [30.0, 30.5], [2000.0, 2050.0])
    out = merge_and_write(fresh, out_path=tmp_data_dirs["market"])
    assert os.path.exists(tmp_data_dirs["market"])
    assert len(out) == 2


def test_merge_and_write_is_idempotent_under_replay(tmp_data_dirs):
    """Running the same fetch twice must not duplicate rows."""
    fresh = _frame(["2024-01-01", "2024-01-02"], [30.0, 30.5], [2000.0, 2050.0])
    merge_and_write(fresh, out_path=tmp_data_dirs["market"])
    out = merge_and_write(fresh, out_path=tmp_data_dirs["market"])
    assert len(out) == 2


def test_merge_and_write_keeps_latest_value_on_date_collision(tmp_data_dirs):
    """Same date with a different rate: the new value wins. This matters
    when the cron runs twice on the same day and the second fetch has
    fresher data."""
    first = _frame(["2024-01-01"], [30.0], [2000.0])
    merge_and_write(first, out_path=tmp_data_dirs["market"])
    second = _frame(["2024-01-01"], [30.7], [2055.0])
    out = merge_and_write(second, out_path=tmp_data_dirs["market"])
    assert len(out) == 1
    assert out["usd_try"].iloc[0] == 30.7
    assert out["gold_usd"].iloc[0] == 2055.0


def test_merge_and_write_extends_history(tmp_data_dirs):
    """A second fetch with later dates appends rather than overwriting."""
    first = _frame(["2024-01-01", "2024-01-02"], [30.0, 30.5], [2000.0, 2050.0])
    merge_and_write(first, out_path=tmp_data_dirs["market"])
    second = _frame(["2024-01-03"], [31.0], [2100.0])
    out = merge_and_write(second, out_path=tmp_data_dirs["market"])
    assert len(out) == 3
    assert out["tarih"].iloc[-1] == pd.Timestamp("2024-01-03")
