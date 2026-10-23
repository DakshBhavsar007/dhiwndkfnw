"""Integration tests for FastAPI endpoints using TestClient."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with lifespan events executed so parquet data is loaded."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient):
    """GET /health must return status ok and confirm data is loaded in memory."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["data_loaded"] is True
    assert "X-Request-ID" in resp.headers


def test_meta_endpoint(client: TestClient):
    """GET /api/meta must return domain boundaries and document bias sign convention."""
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid_start_date"] == "2026-01-02"
    assert data["valid_end_date"] == "2026-02-01"
    assert data["total_delivery_days"] == 31
    assert data["default_cutoff_time"] == "09:00"
    assert data["timezone"] == "Europe/London"
    assert "forecast - actual" in data["bias_convention"]


def test_forecast_endpoint_valid_day(client: TestClient):
    """GET /api/forecast for a valid day returns hourly slots, 30-min actuals, and summary metrics."""
    resp = client.get("/api/forecast?date=2026-01-02&cutoff=09:00")
    assert resp.status_code == 200
    data = resp.json()

    assert data["delivery_date"] == "2026-01-02"
    assert data["cutoff_time"] == "09:00"
    # 24 hourly slots
    assert len(data["hourly"]) == 24
    slot0 = data["hourly"][0]
    assert "startTime" in slot0
    assert "startTime_local" in slot0
    assert slot0["forecast"] is not None
    assert slot0["actual"] is not None
    assert slot0["error"] == pytest.approx(slot0["forecast"] - slot0["actual"])
    assert "2026-01-01T07:30:00" in slot0["publishTime"]
    assert slot0["horizon_hours"] == 16.5

    # 48 raw 30-min actuals
    assert len(data["raw_actuals_30min"]) == 48

    # Summary metrics
    metrics = data["summary_metrics"]
    assert metrics["count"] == 24
    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0


def test_forecast_endpoint_date_validation(client: TestClient):
    """GET /api/forecast with date outside range or malformed date returns 422 with clear message."""
    # Date before valid range
    resp_early = client.get("/api/forecast?date=2025-12-31")
    assert resp_early.status_code == 422
    assert "outside the supported range" in resp_early.json()["detail"]

    # Date after valid range
    resp_late = client.get("/api/forecast?date=2026-02-15")
    assert resp_late.status_code == 422
    assert "outside the supported range" in resp_late.json()["detail"]

    # Malformed date string
    resp_bad = client.get("/api/forecast?date=invalid-date")
    assert resp_bad.status_code == 422
    assert "Invalid date format" in resp_bad.json()["detail"]


def test_accuracy_endpoint_valid_range(client: TestClient):
    """GET /api/accuracy returns headline metrics, hour-of-day breakdown, and all-publishTime horizon breakdown."""
    resp = client.get("/api/accuracy?start=2026-01-02&end=2026-01-10&cutoff=09:00")
    assert resp.status_code == 200
    data = resp.json()

    assert data["start_date"] == "2026-01-02"
    assert data["end_date"] == "2026-01-10"

    # Headline metrics for 9 days * 24 hours = 216 slots
    headline = data["headline_metrics"]
    assert headline["count"] == 9 * 24
    assert headline["mae"] > 0
    assert headline["rmse"] > 0

    # By-hour-of-day breakdown (24 hours)
    by_hour = data["by_hour_of_day"]
    assert len(by_hour) == 24
    assert [item["hour_of_day"] for item in by_hour] == list(range(24))
    assert all(item["count"] == 9 for item in by_hour)

    # By-horizon breakdown across ALL publish runs (12-18, 18-24, 24-30, 30-36, 36-42h)
    by_horizon = data["by_horizon"]
    assert len(by_horizon) == 5
    expected_buckets = ["12-18h", "18-24h", "24-30h", "30-36h", "36-42h"]
    assert [item["horizon_bucket"] for item in by_horizon] == expected_buckets
    # Each bucket must have evaluations from the rolling publication runs
    assert all(item["count"] > 0 for item in by_horizon)


def test_accuracy_endpoint_validation(client: TestClient):
    """GET /api/accuracy fails with 422 if start > end or dates are out of bounds."""
    resp_inverted = client.get("/api/accuracy?start=2026-01-15&end=2026-01-10")
    assert resp_inverted.status_code == 422
    assert "must be earlier than or equal to" in resp_inverted.json()["detail"]

    resp_out_of_bounds = client.get("/api/accuracy?start=2025-12-01&end=2026-01-10")
    assert resp_out_of_bounds.status_code == 422
    assert "outside the supported range" in resp_out_of_bounds.json()["detail"]


def test_error_band_numeric_hand_computed_example():
    """Hand-computed verification of the error band direction.

    Arithmetic:
    - Error definition: error = forecast - actual (positive = over-forecast, negative = under-forecast).
    - Actual generation: actual = forecast - error.
    - Given forecast = 1000.0 MW.
    - Given historical errors = [-200.0, -100.0, 0.0, 100.0, 200.0] MW.
      * P10(error) = -160.0 MW (severe under-forecast, where actual was 1160.0).
      * P90(error) = +160.0 MW (severe over-forecast, where actual was 840.0).
    - Band for ACTUAL generation:
      * lower = max(0.0, forecast - P90(error)) = max(0.0, 1000.0 - 160.0) = 840.0 MW.
      * upper = max(0.0, forecast - P10(error)) = max(0.0, 1000.0 - (-160.0)) = 1160.0 MW.
    - Result:
      * lower (840.0) <= upper (1160.0) is verified.
      * Over-forecasting (+160 error) pushes lower bound down to 840.
      * Under-forecasting (-160 error) pushes upper bound up to 1160.
    """
    import numpy as np

    forecast = 1000.0
    errors = np.array([-200.0, -100.0, 0.0, 100.0, 200.0])

    p10_error = float(np.percentile(errors, 10.0))
    p90_error = float(np.percentile(errors, 90.0))

    assert pytest.approx(p10_error) == -160.0
    assert pytest.approx(p90_error) == +160.0

    lower = max(0.0, forecast - p90_error)
    upper = max(0.0, forecast - p10_error)

    assert pytest.approx(lower) == 840.0
    assert pytest.approx(upper) == 1160.0
    assert lower <= upper


def test_error_band_jan2_has_3_history_days(client: TestClient):
    """2026-01-02 returns a band with history_days_used = 3 (Dec 29, 30, 31)."""
    resp = client.get("/api/error-band?date=2026-01-02")
    assert resp.status_code == 200
    data = resp.json()

    assert data["delivery_date"] == "2026-01-02"
    assert data["history_days_used"] == 3
    assert data["history_start_date"] == "2025-12-29"
    assert data["history_end_date"] == "2025-12-31"  # exactly D-2!
    assert data["reason"] is None
    assert data["band"] is not None
    assert len(data["band"]) == 24

    for slot in data["band"]:
        assert slot["lower_bound"] >= 0.0
        assert slot["lower_bound"] <= slot["upper_bound"]


def test_error_band_leakage_multiple_dates(client: TestClient):
    """Leakage test: for multiple delivery dates, assert no history day > D-2 is ever used."""
    import pandas as pd

    test_dates = ["2026-01-02", "2026-01-05", "2026-01-15", "2026-02-01"]

    for d_str in test_dates:
        resp = client.get(f"/api/error-band?date={d_str}")
        assert resp.status_code == 200
        data = resp.json()

        d_minus_2 = (pd.Timestamp(d_str) - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        assert data["history_end_date"] == d_minus_2
        assert data["history_end_date"] <= d_minus_2  # strictly <= D-2!
        assert data["history_days_used"] >= 3
        assert data["band"] is not None


def test_error_band_validation(client: TestClient):
    """GET /api/error-band with invalid date returns 422."""
    resp = client.get("/api/error-band?date=2025-11-20")
    assert resp.status_code == 422
    assert "outside the supported range" in resp.json()["detail"]


def test_request_logging_header(client: TestClient):
    """Every response must return the X-Request-ID header."""
    resp = client.get("/health", headers={"X-Request-ID": "test-trace-123"})
    assert resp.headers.get("X-Request-ID") == "test-trace-123"

