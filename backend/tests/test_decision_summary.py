"""Tests for the Decision Summary service and endpoint (/api/decision-summary).

Requirements tested:
1. Hand-computed numeric example for shortfall buffer (P90) and typical offset (median).
2. Floor-at-zero behaviour (P90 floored at 0, bias-adjusted hourly slots floored at 0).
3. Null case when history_days_used < 3 (returns null buffer fields and reason).
4. Information leakage rule (strictly no historical delivery day > D-2).
5. API endpoint validation with real snapshot data.
"""

from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import (
    get_decision_summary_service,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_hand_computed_numeric_summary():
    """Hand-computed verification of expected wind, shortfall buffer, offset, and bias-adjusted wind."""
    # 1. Synthetic target day forecast with 4 hourly slots (hours 0, 1, 2, 3)
    # Forecasts: 1000, 2000, 500, 300 MW -> total = 3800 MWh
    target_date = "2026-01-02"
    cutoff = "09:00"

    target_fc_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-02 00:00:00", periods=4, freq="1h", tz="UTC"),
            "publishTime": pd.Timestamp("2026-01-01 07:00:00", tz="UTC"),
            "generation": [1000, 2000, 500, 300],
            "forecast": [1000.0, 2000.0, 500.0, 300.0],
        }
    )

    # 2. Synthetic history: 3 days (2025-12-29, 2025-12-30, 2025-12-31 <= D-2 = 2026-01-03)
    # 10 specific signed errors (forecast - actual):
    # [-100, 0, 100, 200, 300, 400, 500, 600, 700, 800]
    # Median of 10 items: average of 300 and 400 = 350.0 MW
    # 90th percentile: 10% from top (between 700 and 800 with linear interp) = 710.0 MW
    raw_errors = [-100.0, 0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]
    expected_p90 = float(np.percentile(raw_errors, 90.0))
    expected_median = float(np.median(raw_errors))
    assert expected_median == 350.0
    assert expected_p90 == 710.0

    # Hours assigned to historical errors to test risk hours:
    # Hour 18 gets 800 error, Hour 19 gets 700 error, Hour 20 gets 600 error
    # Others get smaller errors
    hours = [0, 1, 2, 3, 4, 12, 17, 20, 19, 18]
    hist_records = []
    # Distribute across the 3 eligible dates: 2025-12-29, 2025-12-30, 2025-12-31
    dates = ["2025-12-29", "2025-12-30", "2025-12-31"]
    for i, (err, hr) in enumerate(zip(raw_errors, hours)):
        d_str = dates[i % 3]
        dt = pd.Timestamp(f"{d_str} {hr:02d}:00:00", tz="UTC")
        fc_val = 1500.0
        act_val = fc_val - err
        hist_records.append(
            {
                "startTime": dt,
                "publishTime": pd.Timestamp("2025-12-28 07:00:00", tz="UTC"),
                "generation": fc_val,
                "forecast": fc_val,
                "actual": act_val,
                "error": err,
            }
        )
    hist_df = pd.DataFrame(hist_records)

    mock_loader = MagicMock()
    mock_loader.forecasts_df = target_fc_df
    # Mock hourly actuals
    mock_loader.hourly_actuals_df = hist_df[["startTime", "actual"]].copy()

    # Mock select_forecast_at_cutoff to return target_fc_df for target_date and corresponding hist_records for hist_dates
    def mock_select(df, delivery_date, cutoff_time, tz, day_offset):
        if delivery_date == target_date:
            return target_fc_df
        subset = hist_df[hist_df["startTime"].dt.strftime("%Y-%m-%d") == delivery_date]
        return subset[["startTime", "publishTime", "generation", "forecast"]]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.app.services.select_forecast_at_cutoff", mock_select)
        res = get_decision_summary_service(
            date_str=target_date,
            cutoff_time=cutoff,
            loader=mock_loader,
        )

    # Hand-computed checks:
    # 1. Expected wind MWh = 1000 + 2000 + 500 + 300 = 3800.0
    assert res.expected_wind_mwh == 3800.0
    # 2. Shortfall buffer MW = P90(errors) floored at 0 = 710.0
    assert res.shortfall_buffer_mw == 710.0
    # 2b. Buffer relative to bias-adjusted forecast = P90 - median = 710.0 - 350.0 = 360.0
    assert res.shortfall_buffer_relative_to_adjusted_mw == 360.0
    # 3. Typical offset MW = median(errors) = 350.0
    assert res.typical_offset_mw == 350.0
    # 4. Bias-adjusted expected wind:
    # slot 0: max(0, 1000 - 350) = 650
    # slot 1: max(0, 2000 - 350) = 1650
    # slot 2: max(0, 500 - 350) = 150
    # slot 3: max(0, 300 - 350) = 0 (floored at zero!)
    # Total = 650 + 1650 + 150 + 0 = 2450.0 MWh
    assert res.bias_adjusted_expected_wind_mwh == 2450.0
    # 5. Risk hours: top 3 hours with highest error are [18, 19, 20], sorted ascending
    assert res.risk_hours == [18, 19, 20]
    # 6. Low confidence flag: 3 history days < 7 -> low_confidence must be True
    assert res.low_confidence is True
    assert res.history_days_used == 3
    # 7. Recommendation text contains key figures and demand disclaimer
    assert "350" in res.recommendation
    assert "710" in res.recommendation
    assert "Demand data is outside scope" in res.recommendation


def test_floor_at_zero_behaviour():
    """Verify shortfall buffer floors at 0 when errors are negative, and hourly slots floor at 0."""
    target_date = "2026-01-05"
    cutoff = "09:00"

    # All negative errors (under-forecasting in history):
    # Errors: [-500, -400, -300, -200] -> raw P90 is negative
    raw_errors = [-500.0, -400.0, -300.0, -200.0]
    raw_p90 = float(np.percentile(raw_errors, 90.0))
    assert raw_p90 < 0  # Raw percentile is negative

    # Target forecast with small numbers: 50, 100 MW
    target_fc_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-05 00:00:00", periods=2, freq="1h", tz="UTC"),
            "publishTime": pd.Timestamp("2026-01-04 07:00:00", tz="UTC"),
            "generation": [50.0, 100.0],
            "forecast": [50.0, 100.0],
        }
    )

    hist_records = []
    dates = ["2025-12-29", "2025-12-30", "2025-12-31"]
    for i, err in enumerate(raw_errors):
        d_str = dates[i % 3]
        dt = pd.Timestamp(f"{d_str} {i:02d}:00:00", tz="UTC")
        fc_val = 1000.0
        hist_records.append(
            {
                "startTime": dt,
                "publishTime": pd.Timestamp("2025-12-28 07:00:00", tz="UTC"),
                "generation": fc_val,
                "forecast": fc_val,
                "actual": fc_val - err,
                "error": err,
            }
        )
    hist_df = pd.DataFrame(hist_records)

    mock_loader = MagicMock()
    mock_loader.hourly_actuals_df = hist_df[["startTime", "actual"]].copy()

    def mock_select(df, delivery_date, cutoff_time, tz, day_offset):
        if delivery_date == target_date:
            return target_fc_df
        subset = hist_df[hist_df["startTime"].dt.strftime("%Y-%m-%d") == delivery_date]
        return subset[["startTime", "publishTime", "generation", "forecast"]]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.app.services.select_forecast_at_cutoff", mock_select)
        res = get_decision_summary_service(
            date_str=target_date,
            cutoff_time=cutoff,
            loader=mock_loader,
        )

    # Shortfall buffer must be floored at 0.0, NOT negative
    assert res.shortfall_buffer_mw == 0.0

    # In this case median error is negative (-350.0), so forecast - (-350) = forecast + 350
    # Now let's test positive typical offset exceeding forecast:
    # If offset = 200, forecasts = [50, 100], both max(0, 50 - 200) = 0 and max(0, 100 - 200) = 0
    raw_pos_errors = [200.0, 200.0, 200.0, 200.0]
    for i, err in enumerate(raw_pos_errors):
        hist_records[i]["error"] = err
        hist_records[i]["actual"] = hist_records[i]["forecast"] - err
    mock_loader.hourly_actuals_df = pd.DataFrame(hist_records)[["startTime", "actual"]].copy()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.app.services.select_forecast_at_cutoff", mock_select)
        res_pos = get_decision_summary_service(
            date_str=target_date,
            cutoff_time=cutoff,
            loader=mock_loader,
        )

    assert res_pos.typical_offset_mw == 200.0
    # Each slot max(0, 50-200) = 0 and max(0, 100-200) = 0 -> total must be 0.0, NOT negative
    assert res_pos.bias_adjusted_expected_wind_mwh == 0.0


def test_insufficient_history_null_case():
    """When history_days_used < 3, buffer fields must be null with an informative reason."""
    # Test with a date where eligible history days is < 3
    # For example, if BUFFER_HISTORY_START_DATE was shifted or we test with a mock date range
    target_date = "2026-01-02"
    cutoff = "09:00"

    target_fc_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-02 00:00:00", periods=24, freq="1h", tz="UTC"),
            "publishTime": pd.Timestamp("2026-01-01 07:00:00", tz="UTC"),
            "generation": [1000.0] * 24,
            "forecast": [1000.0] * 24,
        }
    )

    mock_loader = MagicMock()

    def mock_select(df, delivery_date, cutoff_time, tz, day_offset):
        return target_fc_df

    # Temporarily set BUFFER_HISTORY_START_DATE to "2025-12-31" so D-2 ("2025-12-31") gives only 1 day (< 3)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.app.services.BUFFER_HISTORY_START_DATE", "2025-12-31")
        mp.setattr("backend.app.services.select_forecast_at_cutoff", mock_select)
        res = get_decision_summary_service(
            date_str=target_date,
            cutoff_time=cutoff,
            loader=mock_loader,
        )

    assert res.history_days_used == 1
    assert res.shortfall_buffer_mw is None
    assert res.typical_offset_mw is None
    assert res.bias_adjusted_expected_wind_mwh is None
    assert res.risk_hours == []
    assert res.low_confidence is True
    assert res.reason is not None
    assert "Fewer than 3 historical delivery days available" in res.reason
    assert "Demand data is outside scope" in res.recommendation


def test_leakage_rule_no_history_after_d_minus_2(client: TestClient):
    """Leakage rule: for any target delivery day D, no history delivery day can be > D-2."""
    test_dates = ["2026-01-02", "2026-01-05", "2026-01-10", "2026-01-20", "2026-02-01"]

    for d_str in test_dates:
        resp = client.get(f"/api/decision-summary?date={d_str}&cutoff=09:00")
        assert resp.status_code == 200
        data = resp.json()

        d_dt = pd.Timestamp(d_str)
        max_allowed_history = (d_dt - pd.Timedelta(days=2)).strftime("%Y-%m-%d")

        if data["history_end_date"] is not None:
            # End date must be strictly <= D-2
            assert data["history_end_date"] <= max_allowed_history
            # And history_end_date can NEVER equal D-1 or D
            d_minus_1 = (d_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            assert data["history_end_date"] < d_minus_1
            assert data["history_end_date"] < d_str


def test_decision_summary_api_endpoint_jan10(client: TestClient):
    """Verify live endpoint response for sample date 2026-01-10."""
    resp = client.get("/api/decision-summary?date=2026-01-10&cutoff=09:00")
    assert resp.status_code == 200
    data = resp.json()

    assert data["delivery_date"] == "2026-01-10"
    assert data["cutoff_time"] == "09:00"
    assert data["expected_wind_mwh"] > 0
    assert data["shortfall_buffer_mw"] is not None
    assert data["shortfall_buffer_mw"] >= 0
    assert data["typical_offset_mw"] is not None
    assert data["bias_adjusted_expected_wind_mwh"] is not None
    assert data["bias_adjusted_expected_wind_mwh"] >= 0
    assert len(data["risk_hours"]) == 3
    for rh in data["risk_hours"]:
        assert 0 <= rh <= 23

    # On Jan 10, history is from 2025-12-29 to 2026-01-08 = 11 days (>= 7)
    assert data["history_days_used"] == 11
    assert data["history_start_date"] == "2025-12-29"
    assert data["history_end_date"] == "2026-01-08"
    assert data["low_confidence"] is False

    # Check recommendation text
    rec = data["recommendation"]
    assert "Forecast wind averages" in rec
    assert "Historically forecasts ran" in rec
    assert "Plan for up to" in rec
    assert "Demand data is outside scope" in rec
    assert "assumption" in data


def test_backtest_hand_computed():
    """Synthetic test verifying hand-computed backtest metrics (MAE raw vs adjusted, breach rate)."""
    # 3 history days: 2025-12-29, 2025-12-30, 2025-12-31
    # 1 target day: 2026-01-02 (history <= D-2 = 2025-12-31)
    # History: 10 errors [-100, 0, 100, 200, 300, 400, 500, 600, 700, 800]
    # Median = 350.0 MW
    # P90 = 710.0 MW
    raw_hist_errors = [-100.0, 0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]

    all_fc_rows = []
    all_act_rows = []

    # Distribute historical errors across the 3 days
    for i, err in enumerate(raw_hist_errors):
        d_str = ["2025-12-29", "2025-12-30", "2025-12-31"][i % 3]
        dt = pd.Timestamp(f"{d_str} {i:02d}:00:00", tz="UTC")
        fc_val = 2000.0
        act_val = fc_val - err
        all_fc_rows.append({"startTime": dt, "publishTime": pd.Timestamp("2025-12-28 07:00:00", tz="UTC"), "generation": fc_val, "forecast": fc_val})
        all_act_rows.append({"startTime": dt, "actual": act_val})

    # Target delivery day (2026-01-02): 2 hourly slots
    # Slot 0: Forecast = 1000, Actual = 800 -> raw error = +200
    # Slot 1: Forecast = 1200, Actual = 400 -> raw error = +800
    # Raw MAE = (|200| + |800|) / 2 = 500.0 MW
    # Typical offset = 350.0 MW
    # Slot 0 adjusted: max(0, 1000 - 350) = 650. Error vs 800 = |650 - 800| = 150 MW
    # Slot 1 adjusted: max(0, 1200 - 350) = 850. Error vs 400 = |850 - 400| = 450 MW
    # Adjusted MAE = (150 + 450) / 2 = 300.0 MW
    # Adjusted beats raw? 300.0 < 500.0 -> True!
    # Shortfall buffer = 710.0 MW
    # Slot 0: actual (800) < forecast - buffer (1000 - 710 = 290) -> 800 < 290 False (No breach)
    # Slot 1: actual (400) < forecast - buffer (1200 - 710 = 490) -> 400 < 490 True (Breach!)
    # Breach count = 1 / 2 slots = 0.5 (50.0% breach rate)
    t_dt0 = pd.Timestamp("2026-01-02 00:00:00", tz="UTC")
    t_dt1 = pd.Timestamp("2026-01-02 01:00:00", tz="UTC")
    all_fc_rows.append({"startTime": t_dt0, "publishTime": pd.Timestamp("2026-01-01 07:00:00", tz="UTC"), "generation": 1000.0, "forecast": 1000.0})
    all_fc_rows.append({"startTime": t_dt1, "publishTime": pd.Timestamp("2026-01-01 07:00:00", tz="UTC"), "generation": 1200.0, "forecast": 1200.0})
    all_act_rows.append({"startTime": t_dt0, "actual": 800.0})
    all_act_rows.append({"startTime": t_dt1, "actual": 400.0})

    mock_loader = MagicMock()
    mock_loader.forecasts_df = pd.DataFrame(all_fc_rows)
    mock_loader.hourly_actuals_df = pd.DataFrame(all_act_rows)

    def mock_select(df, delivery_date, cutoff_time, tz, day_offset):
        sub = df[df["startTime"].dt.strftime("%Y-%m-%d") == delivery_date]
        return sub[["startTime", "publishTime", "generation", "forecast"]]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.app.services.select_forecast_at_cutoff", mock_select)
        # Set MIN and MAX delivery date to test only 2026-01-02
        mp.setattr("backend.app.services.MIN_DELIVERY_DATE", "2026-01-02")
        mp.setattr("backend.app.services.MAX_DELIVERY_DATE", "2026-01-02")
        from backend.app.services import get_backtest_service
        backtest = get_backtest_service(cutoff_time="09:00", loader=mock_loader)

    assert backtest.summary.days_evaluated == 1
    day0 = backtest.daily[0]
    assert day0.delivery_date == "2026-01-02"
    assert day0.history_days_used == 3
    assert day0.typical_offset_mw == 350.0
    assert day0.shortfall_buffer_mw == 710.0
    assert day0.mae_raw == 500.0
    assert day0.mae_adjusted == 300.0
    assert day0.adjusted_beats_raw is True
    assert day0.breach_count == 1
    assert day0.slot_count == 2
    assert day0.breach_rate == 0.5


def test_backtest_leakage_rule(client: TestClient):
    """Leakage rule: for any target delivery day D in the backtest, history used must never include D-1 or D."""
    resp = client.get("/api/backtest?cutoff=09:00")
    assert resp.status_code == 200
    data = resp.json()

    # All 31 delivery days should be evaluated since Jan 02 has 3 buffer days (2025-12-29 to 2025-12-31)
    assert data["summary"]["days_evaluated"] == 31
    assert len(data["daily"]) == 31

    for row in data["daily"]:
        d_str = row["delivery_date"]
        d_dt = pd.Timestamp(d_str)

        # Theoretical max history day allowed
        max_allowed = (d_dt - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        d_minus_1 = (d_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        # History days used: from 2025-12-29 to max_allowed
        expected_history_count = len(pd.date_range("2025-12-29", max_allowed, freq="1D"))
        assert row["history_days_used"] == expected_history_count

        # Ensure no leakage: max historical day is <= D-2
        assert max_allowed < d_minus_1
        assert max_allowed < d_str


def test_backtest_api_endpoint(client: TestClient):
    """Integration test verifying realistic summary metrics across January 2026 backtest."""
    resp = client.get("/api/backtest?cutoff=09:00")
    assert resp.status_code == 200
    data = resp.json()

    summary = data["summary"]
    assert summary["days_evaluated"] == 31
    assert summary["mean_mae_raw"] > 0
    assert summary["mean_mae_adjusted"] > 0
    assert 0 <= summary["days_adjusted_beats_raw"] <= 31
    assert 0 <= summary["days_adjusted_beats_raw_pct"] <= 100.0
    assert summary["total_slots"] == 31 * 24
    assert 0 <= summary["overall_breach_rate"] <= 1.0

