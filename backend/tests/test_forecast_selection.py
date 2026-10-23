"""Unit tests for forecast selection logic, cutoff filtering, and DST handling."""

import datetime
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from backend.app.core.forecast_selection import select_forecast_at_cutoff


def test_forecast_selection_standard_day():
    """Verify standard delivery day produces 24 hourly slots with latest publishTime <= cutoff."""
    # Decision for 2026-01-02 at 09:00 on 2026-01-01
    publish_times = [
        pd.Timestamp("2026-01-01 05:30:00+00:00"),
        pd.Timestamp("2026-01-01 07:30:00+00:00"),
    ]
    slots = pd.date_range("2026-01-02 00:00:00+00:00", "2026-01-02 23:00:00+00:00", freq="1h")

    records = []
    for pub in publish_times:
        gen_base = 10000 if pub.hour == 5 else 12000
        for slot in slots:
            records.append({
                "startTime": slot,
                "publishTime": pub,
                "generation": gen_base,
            })
    df = pd.DataFrame(records)

    selected = select_forecast_at_cutoff(df, "2026-01-02", cutoff_time="09:00", day_offset=1)

    assert len(selected) == 24
    assert list(selected["startTime"]) == list(slots)
    # Latest publishTime (07:30) must be chosen for all slots
    assert (selected["publishTime"] == pd.Timestamp("2026-01-01 07:30:00+00:00")).all()
    assert (selected["forecast"] == 12000.0).all()
    assert selected["horizon_hours"].min() == 16.5  # 00:00 - 07:30 D-1
    assert selected["horizon_hours"].max() == 39.5  # 23:00 - 07:30 D-1


def test_cutoff_exact_match_included():
    """A forecast published exactly at the cutoff (e.g. 09:00:00) must be included."""
    cutoff_ts = pd.Timestamp("2026-01-01 09:00:00+00:00")
    earlier_ts = pd.Timestamp("2026-01-01 07:30:00+00:00")
    slot = pd.Timestamp("2026-01-02 12:00:00+00:00")

    df = pd.DataFrame([
        {"startTime": slot, "publishTime": earlier_ts, "generation": 10000},
        {"startTime": slot, "publishTime": cutoff_ts, "generation": 15000},
    ])

    selected = select_forecast_at_cutoff(df, "2026-01-02", cutoff_time="09:00", day_offset=1)
    row_12 = selected[selected["startTime"] == slot].iloc[0]

    assert row_12["publishTime"] == cutoff_ts
    assert row_12["forecast"] == 15000.0


def test_publish_time_after_cutoff_excluded():
    """A forecast published 1 minute after cutoff (e.g. 09:01:00) MUST be excluded."""
    cutoff_ts = pd.Timestamp("2026-01-01 09:00:00+00:00")
    one_min_after = pd.Timestamp("2026-01-01 09:01:00+00:00")
    earlier_ts = pd.Timestamp("2026-01-01 07:30:00+00:00")
    slot = pd.Timestamp("2026-01-02 12:00:00+00:00")

    df = pd.DataFrame([
        {"startTime": slot, "publishTime": earlier_ts, "generation": 10000},
        {"startTime": slot, "publishTime": one_min_after, "generation": 99999},
    ])

    selected = select_forecast_at_cutoff(df, "2026-01-02", cutoff_time="09:00", day_offset=1)
    row_12 = selected[selected["startTime"] == slot].iloc[0]

    # The run at 09:01:00 must NOT be selected; must fall back to 07:30:00
    assert row_12["publishTime"] == earlier_ts
    assert row_12["forecast"] == 10000.0


def test_some_slots_missing_forecast():
    """If some slots lack an eligible forecast, they must appear with NaN/NaT."""
    pub_ts = pd.Timestamp("2026-01-01 07:30:00+00:00")
    # Only hours 00:00 to 05:00 have forecasts
    partial_slots = pd.date_range("2026-01-02 00:00:00+00:00", "2026-01-02 05:00:00+00:00", freq="1h")
    records = [{"startTime": s, "publishTime": pub_ts, "generation": 11000} for s in partial_slots]
    df = pd.DataFrame(records)

    selected = select_forecast_at_cutoff(df, "2026-01-02", cutoff_time="09:00", day_offset=1)

    assert len(selected) == 24
    # First 6 slots have values
    assert selected.iloc[:6]["forecast"].notna().all()
    # Remaining 18 slots are NaN
    assert selected.iloc[6:]["forecast"].isna().all()
    assert selected.iloc[6:]["publishTime"].isna().all()
    assert selected.iloc[6:]["horizon_hours"].isna().all()


def test_empty_day_and_empty_dataframe():
    """An empty DataFrame or empty day should still return the full set of local hourly slots with NaNs."""
    selected_empty_df = select_forecast_at_cutoff(pd.DataFrame(), "2026-01-02")
    assert len(selected_empty_df) == 24
    assert selected_empty_df["forecast"].isna().all()
    assert selected_empty_df["publishTime"].isna().all()
    assert selected_empty_df["horizon_hours"].isna().all()

    # DataFrame with forecasts only for another day
    other_day_df = pd.DataFrame([{
        "startTime": pd.Timestamp("2026-02-15 00:00:00+00:00"),
        "publishTime": pd.Timestamp("2026-02-14 07:30:00+00:00"),
        "generation": 5000,
    }])
    selected_no_match = select_forecast_at_cutoff(other_day_df, "2026-01-02")
    assert len(selected_no_match) == 24
    assert selected_no_match["forecast"].isna().all()


def test_dst_spring_forward_23_hours():
    """Europe/London spring forward (2026-03-29): clock jumps 01:00 -> 02:00, producing exactly 23 local hours."""
    # Cutoff 09:00 on 2026-03-28 (D-1)
    pub_ts = pd.Timestamp("2026-03-28 07:30:00+00:00")
    # In Europe/London on 2026-03-29, 00:00 GMT, 02:00 BST (01:00 UTC), ... 23:00 BST (22:00 UTC) = 23 slots
    tz = "Europe/London"
    start_local = pd.Timestamp("2026-03-29").tz_localize(tz)
    end_local = start_local + pd.DateOffset(days=1)
    expected_local_slots = pd.date_range(start_local, end_local, freq="1h", inclusive="left")
    expected_utc_slots = expected_local_slots.tz_convert("UTC")

    assert len(expected_utc_slots) == 23

    records = [{"startTime": s, "publishTime": pub_ts, "generation": 14000} for s in expected_utc_slots]
    df = pd.DataFrame(records)

    selected = select_forecast_at_cutoff(df, "2026-03-29", tz="Europe/London")
    assert len(selected) == 23
    assert list(selected["startTime"]) == list(expected_utc_slots)
    assert selected["forecast"].notna().all()


def test_dst_fall_back_25_hours():
    """Europe/London fall back (2026-10-25): clock jumps 02:00 -> 01:00, producing exactly 25 local hours."""
    pub_ts = pd.Timestamp("2026-10-24 07:30:00+00:00")
    tz = "Europe/London"
    start_local = pd.Timestamp("2026-10-25").tz_localize(tz)
    end_local = start_local + pd.DateOffset(days=1)
    expected_local_slots = pd.date_range(start_local, end_local, freq="1h", inclusive="left")
    expected_utc_slots = expected_local_slots.tz_convert("UTC")

    assert len(expected_utc_slots) == 25

    records = [{"startTime": s, "publishTime": pub_ts, "generation": 16000} for s in expected_utc_slots]
    df = pd.DataFrame(records)

    selected = select_forecast_at_cutoff(df, "2026-10-25", tz="Europe/London")
    assert len(selected) == 25
    assert list(selected["startTime"]) == list(expected_utc_slots)
    assert selected["forecast"].notna().all()


def test_real_snapshot_delivery_day():
    """Validate on the real snapshot forecasts.parquet for delivery day 2026-01-02."""
    p = Path("backend/data/forecasts.parquet")
    if not p.exists():
        pytest.skip("forecasts.parquet not found")

    df_fc = pd.read_parquet(p)
    selected = select_forecast_at_cutoff(df_fc, "2026-01-02", cutoff_time="09:00", tz="Europe/London")

    assert len(selected) == 24
    assert selected["forecast"].notna().all()
    # Confirm exactly the 07:30 publish run is chosen
    assert (selected["publishTime"] == pd.Timestamp("2026-01-01 07:30:00+00:00")).all()
    assert selected["horizon_hours"].min() == 16.5
    assert selected["horizon_hours"].max() == 39.5
