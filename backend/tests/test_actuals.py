"""Unit tests for actuals aggregation, missing half-hour handling, and data validation."""

import pandas as pd
import pytest
from pathlib import Path

from backend.app.core.actuals import aggregate_actuals_hourly


def test_standard_hourly_aggregation():
    """Verify mean of two consecutive half-hours is calculated correctly."""
    data = [
        {"startTime": pd.Timestamp("2026-01-01 00:00:00+00:00"), "generation": 10000},
        {"startTime": pd.Timestamp("2026-01-01 00:30:00+00:00"), "generation": 12000},
        {"startTime": pd.Timestamp("2026-01-01 01:00:00+00:00"), "generation": 8000},
        {"startTime": pd.Timestamp("2026-01-01 01:30:00+00:00"), "generation": 10000},
    ]
    df = pd.DataFrame(data)
    hourly = aggregate_actuals_hourly(df)

    assert len(hourly) == 2
    assert list(hourly["startTime"]) == [
        pd.Timestamp("2026-01-01 00:00:00+00:00"),
        pd.Timestamp("2026-01-01 01:00:00+00:00"),
    ]
    assert hourly.iloc[0]["actual"] == 11000.0  # (10000 + 12000) / 2
    assert hourly.iloc[1]["actual"] == 9000.0   # (8000 + 10000) / 2
    # Verify alias column 'generation' is identical to 'actual'
    assert hourly.iloc[0]["generation"] == 11000.0


def test_missing_half_hour_dropped_by_default():
    """An hour with only one half-hour present (e.g. only :00 or only :30) must be dropped by default."""
    data = [
        # Hour 00: complete
        {"startTime": pd.Timestamp("2026-01-01 00:00:00+00:00"), "generation": 10000},
        {"startTime": pd.Timestamp("2026-01-01 00:30:00+00:00"), "generation": 12000},
        # Hour 01: incomplete (only :00 present, :30 missing)
        {"startTime": pd.Timestamp("2026-01-01 01:00:00+00:00"), "generation": 8000},
        # Hour 02: incomplete (only :30 present, :00 missing)
        {"startTime": pd.Timestamp("2026-01-01 02:30:00+00:00"), "generation": 9000},
        # Hour 03: complete
        {"startTime": pd.Timestamp("2026-01-01 03:00:00+00:00"), "generation": 7000},
        {"startTime": pd.Timestamp("2026-01-01 03:30:00+00:00"), "generation": 7000},
    ]
    df = pd.DataFrame(data)
    hourly = aggregate_actuals_hourly(df, drop_incomplete=True)

    # Hours 01 and 02 must be dropped
    assert len(hourly) == 2
    assert list(hourly["startTime"]) == [
        pd.Timestamp("2026-01-01 00:00:00+00:00"),
        pd.Timestamp("2026-01-01 03:00:00+00:00"),
    ]


def test_missing_half_hour_flagged_when_retained():
    """When drop_incomplete=False, incomplete hours must be kept and flagged with is_complete=False."""
    data = [
        {"startTime": pd.Timestamp("2026-01-01 00:00:00+00:00"), "generation": 10000},
        {"startTime": pd.Timestamp("2026-01-01 00:30:00+00:00"), "generation": 12000},
        {"startTime": pd.Timestamp("2026-01-01 01:00:00+00:00"), "generation": 8000},
    ]
    df = pd.DataFrame(data)
    hourly = aggregate_actuals_hourly(df, drop_incomplete=False)

    assert len(hourly) == 2
    assert "is_complete" in hourly.columns
    assert hourly.iloc[0]["is_complete"] is True or hourly.iloc[0]["is_complete"] == True
    assert hourly.iloc[1]["is_complete"] is False or hourly.iloc[1]["is_complete"] == False
    assert hourly.iloc[1]["actual"] == 8000.0


def test_deduplicates_duplicate_timestamps():
    """Verify duplicate records for the same settlement timestamp are deduplicated before mean."""
    data = [
        {"startTime": pd.Timestamp("2026-01-01 00:00:00+00:00"), "generation": 10000},
        {"startTime": pd.Timestamp("2026-01-01 00:00:00+00:00"), "generation": 10000}, # duplicate
        {"startTime": pd.Timestamp("2026-01-01 00:30:00+00:00"), "generation": 12000},
    ]
    df = pd.DataFrame(data)
    hourly = aggregate_actuals_hourly(df)

    assert len(hourly) == 1
    assert hourly.iloc[0]["actual"] == 11000.0


def test_empty_actuals():
    """Verify empty DataFrame returns empty hourly DataFrame with correct schema."""
    hourly = aggregate_actuals_hourly(pd.DataFrame())
    assert hourly.empty
    assert "startTime" in hourly.columns
    assert "actual" in hourly.columns


def test_real_snapshot_actuals():
    """Verify aggregation on full real actuals.parquet snapshot (1,824 half-hours -> 912 hours)."""
    p = Path("backend/data/actuals.parquet")
    if not p.exists():
        pytest.skip("actuals.parquet not found")

    df_act = pd.read_parquet(p)
    assert len(df_act) == 1824

    hourly = aggregate_actuals_hourly(df_act, drop_incomplete=True)
    # Exactly 38 days * 24 hours = 912 hourly periods
    assert len(hourly) == 912
    assert hourly["actual"].isna().sum() == 0
    # Every delta between consecutive rows must be exactly 1 hour
    deltas = hourly["startTime"].diff().dropna()
    assert (deltas == pd.Timedelta(hours=1)).all()
