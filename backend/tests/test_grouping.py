"""Unit tests for group-by analysis utilities (hour-of-day and horizon buckets)."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from backend.app.core.actuals import aggregate_actuals_hourly
from backend.app.core.forecast_selection import select_forecast_at_cutoff
from backend.app.core.grouping import (
    compute_error_by_horizon_bucket,
    compute_error_by_hour_of_day,
)


def test_compute_error_by_hour_of_day():
    """Verify metrics grouped by local hour of day (0-23)."""
    # 48 hours of synthetic data (2 days)
    slots = pd.date_range("2026-01-01 00:00:00+00:00", periods=48, freq="1h")
    actuals = np.full(48, 1000.0)
    # Hour 0 has error +100, Hour 1 has error +200, etc.
    forecasts = actuals + np.tile(np.arange(24) * 10.0, 2)

    df = pd.DataFrame({
        "startTime": slots,
        "actual": actuals,
        "forecast": forecasts,
    })

    result = compute_error_by_hour_of_day(df, tz="Europe/London")

    assert len(result) == 24
    assert list(result["hour_of_day"]) == list(range(24))
    assert (result["count"] == 2).all()
    # Check hour 5: error should be 50.0
    row_5 = result[result["hour_of_day"] == 5].iloc[0]
    assert pytest.approx(row_5["mae"]) == 50.0
    assert pytest.approx(row_5["bias"]) == 50.0


def test_compute_error_by_horizon_bucket():
    """Verify metrics grouped by horizon lead-time bucket."""
    horizons = np.array([5.0, 10.0, 18.0, 22.0, 30.0, 42.0])
    actual = np.full(6, 100.0)
    forecast = np.array([110.0, 110.0, 120.0, 120.0, 130.0, 140.0])

    df = pd.DataFrame({
        "horizon_hours": horizons,
        "actual": actual,
        "forecast": forecast,
    })

    result = compute_error_by_horizon_bucket(df)

    assert "horizon_bucket" in result.columns
    # Buckets: '0-12h' (2 items), '12-24h' (2 items), '24-36h' (1 item), '36-48h' (1 item), '48-72h' (0 items)
    b_0_12 = result[result["horizon_bucket"] == "0-12h"].iloc[0]
    assert b_0_12["count"] == 2
    assert pytest.approx(b_0_12["mae"]) == 10.0

    b_12_24 = result[result["horizon_bucket"] == "12-24h"].iloc[0]
    assert b_12_24["count"] == 2
    assert pytest.approx(b_12_24["mae"]) == 20.0

    b_48_72 = result[result["horizon_bucket"] == "48-72h"].iloc[0]
    assert b_48_72["count"] == 0
    assert np.isnan(b_48_72["mae"])


def test_end_to_end_delivery_day_pipeline():
    """End-to-end integration test: select forecast, aggregate actuals, join, and compute groupings."""
    actuals_file = Path("backend/data/actuals.parquet")
    forecasts_file = Path("backend/data/forecasts.parquet")
    if not (actuals_file.exists() and forecasts_file.exists()):
        pytest.skip("Snapshots not available")

    df_act_raw = pd.read_parquet(actuals_file)
    df_fc_raw = pd.read_parquet(forecasts_file)

    # 1. Aggregate actuals
    hourly_actuals = aggregate_actuals_hourly(df_act_raw)

    # 2. Select forecast at 09:00 on D-1 for delivery day 2026-01-02
    selected_fc = select_forecast_at_cutoff(df_fc_raw, "2026-01-02", cutoff_time="09:00")
    assert len(selected_fc) == 24

    # 3. Join on hourly startTime
    joined = pd.merge(hourly_actuals, selected_fc, on="startTime", how="inner")
    assert len(joined) == 24
    assert joined["actual"].notna().all()
    assert joined["forecast"].notna().all()

    # 4. Group by hour of day
    by_hour = compute_error_by_hour_of_day(joined)
    assert len(by_hour) == 24
    assert (by_hour["count"] == 1).all()
    assert by_hour["mae"].notna().all()

    # 5. Group by horizon bucket
    by_horizon = compute_error_by_horizon_bucket(joined)
    assert len(by_horizon) > 0
    # On 2026-01-02, horizons range from 16.5h to 39.5h, falling in '12-24h' and '24-36h' and '36-48h'
    populated = by_horizon[by_horizon["count"] > 0]
    assert set(populated["horizon_bucket"]) == {"12-24h", "24-36h", "36-48h"}
    assert populated["count"].sum() == 24
