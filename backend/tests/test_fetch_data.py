"""Unit tests for fetch_data script and data integrity."""

import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock

from backend.scripts.fetch_data import (
    fetch_fuelhh_actuals,
    fetch_windfor_forecasts,
)


def test_fetch_fuelhh_actuals_cleaning():
    """Verify FUELHH stream cleaning: parses UTC, filters columns, deduplicates, sorts."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T01:00:00Z",
            "startTime": "2026-01-01T00:30:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 2,
            "fuelType": "WIND",
            "generation": 12500,
        },
        # Duplicate with different or same settlementPeriod
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T01:00:00Z",
            "startTime": "2026-01-01T00:30:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 2,
            "fuelType": "WIND",
            "generation": 12500,
        },
        # Earlier period out of order
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T00:30:00Z",
            "startTime": "2026-01-01T00:00:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 1,
            "fuelType": "WIND",
            "generation": 12000,
        },
    ]
    mock_session.get.return_value = mock_response

    df = fetch_fuelhh_actuals(
        mock_session,
        start_date="2026-01-01",
        end_date="2026-01-01",
        chunk_days=1,
    )

    # Validate output schema
    assert list(df.columns) == ["startTime", "generation"]
    assert len(df) == 2  # deduplicated
    assert df["startTime"].dt.tz is not None  # timezone-aware UTC
    assert str(df["startTime"].dt.tz) == "UTC"
    # Validate sorting
    assert df.iloc[0]["startTime"] < df.iloc[1]["startTime"]
    assert df.iloc[0]["generation"] == 12000
    assert df.iloc[1]["generation"] == 12500


def test_fetch_windfor_forecasts_cleaning():
    """Verify WINDFOR stream cleaning: parses UTC, filters columns, deduplicates, sorts."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "dataset": "WINDFOR",
            "publishTime": "2026-01-01T02:30:00Z",
            "startTime": "2026-01-01T12:00:00Z",
            "generation": 15000,
        },
        # Duplicate row
        {
            "dataset": "WINDFOR",
            "publishTime": "2026-01-01T02:30:00Z",
            "startTime": "2026-01-01T12:00:00Z",
            "generation": 15000,
        },
        # Earlier forecast run
        {
            "dataset": "WINDFOR",
            "publishTime": "2025-12-31T22:30:00Z",
            "startTime": "2026-01-01T12:00:00Z",
            "generation": 14000,
        },
    ]
    mock_session.get.return_value = mock_response

    df = fetch_windfor_forecasts(
        mock_session,
        start_dt="2026-01-01T00:00:00Z",
        end_dt="2026-01-01T23:59:59Z",
        chunk_days=1,
    )

    # Validate output schema
    assert list(df.columns) == ["startTime", "publishTime", "generation"]
    assert len(df) == 2
    assert str(df["startTime"].dt.tz) == "UTC"
    assert str(df["publishTime"].dt.tz) == "UTC"
    # Sorting: by publishTime, then startTime
    assert df.iloc[0]["publishTime"] < df.iloc[1]["publishTime"]


def test_saved_parquet_snapshots_exist_and_valid():
    """Verify the downloaded parquet datasets in backend/data exist and are non-empty."""
    actuals_path = Path("backend/data/actuals.parquet")
    forecasts_path = Path("backend/data/forecasts.parquet")

    assert actuals_path.exists(), "actuals.parquet must exist"
    assert forecasts_path.exists(), "forecasts.parquet must exist"

    df_act = pd.read_parquet(actuals_path)
    df_fc = pd.read_parquet(forecasts_path)

    assert len(df_act) > 0
    assert len(df_fc) > 0
    assert set(df_act.columns) == {"startTime", "generation"}
    assert set(df_fc.columns) == {"startTime", "publishTime", "generation"}
    assert df_act["generation"].isna().sum() == 0
    assert df_fc["generation"].isna().sum() == 0
