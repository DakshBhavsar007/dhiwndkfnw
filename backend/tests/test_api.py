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


def test_error_band_leakage_and_minimum_history(client: TestClient):
    """Verify error-band strict leakage prevention: only delivery days <= D-2 are used.

    - 2026-01-02: D-2 = 2025-12-31 (0 history days in scope < 3) -> band is null.
    - 2026-01-04: D-2 = 2026-01-02 (1 history day in scope < 3) -> band is null.
    - 2026-01-05: D-2 = 2026-01-03 (2 history days in scope < 3) -> band is null.
    - 2026-01-06: D-2 = 2026-01-04 (3 history days in scope: Jan 2, 3, 4 >= 3) -> band is generated.
    """
    # 1. Delivery day Jan 2: 0 days history
    resp_jan2 = client.get("/api/error-band?date=2026-01-02")
    assert resp_jan2.status_code == 200
    data_jan2 = resp_jan2.json()
    assert data_jan2["history_days_used"] == 0
    assert data_jan2["band"] is None
    assert "Fewer than 3 historical delivery days" in data_jan2["reason"]

    # 2. Delivery day Jan 4: 1 day history (2026-01-02)
    resp_jan4 = client.get("/api/error-band?date=2026-01-04")
    assert resp_jan4.status_code == 200
    data_jan4 = resp_jan4.json()
    assert data_jan4["history_days_used"] == 1
    assert data_jan4["band"] is None
    assert "Fewer than 3 historical delivery days" in data_jan4["reason"]

    # 3. Delivery day Jan 5: 2 days history (2026-01-02 and 2026-01-03)
    resp_jan5 = client.get("/api/error-band?date=2026-01-05")
    assert resp_jan5.status_code == 200
    data_jan5 = resp_jan5.json()
    assert data_jan5["history_days_used"] == 2
    assert data_jan5["band"] is None

    # 4. Delivery day Jan 6: 3 days history (2026-01-02, 2026-01-03, 2026-01-04)
    # Strictly <= D-2! Notice Jan 5 (D-1) is NOT included.
    resp_jan6 = client.get("/api/error-band?date=2026-01-06")
    assert resp_jan6.status_code == 200
    data_jan6 = resp_jan6.json()
    assert data_jan6["history_days_used"] == 3
    assert data_jan6["history_start_date"] == "2026-01-02"
    assert data_jan6["history_end_date"] == "2026-01-04"  # Confirms D-2 boundary!
    assert data_jan6["reason"] is None
    assert data_jan6["band"] is not None
    assert len(data_jan6["band"]) == 24

    # Verify bands: lower_bound <= upper_bound and lower_bound >= 0
    for slot in data_jan6["band"]:
        assert slot["lower_bound"] >= 0.0
        assert slot["lower_bound"] <= slot["upper_bound"]
        assert "p10_error" in slot
        assert "p90_error" in slot


def test_error_band_validation(client: TestClient):
    """GET /api/error-band with invalid date returns 422."""
    resp = client.get("/api/error-band?date=2025-11-20")
    assert resp.status_code == 422
    assert "outside the supported range" in resp.json()["detail"]


def test_request_logging_header(client: TestClient):
    """Every response must return the X-Request-ID header."""
    resp = client.get("/health", headers={"X-Request-ID": "test-trace-123"})
    assert resp.headers.get("X-Request-ID") == "test-trace-123"
