"""Unit tests for vectorized evaluation metrics, bias convention, and zero actual handling."""

import numpy as np
import pandas as pd
import pytest

from backend.app.core.metrics import (
    calculate_bias,
    calculate_error_percentiles,
    calculate_mae,
    calculate_mape,
    calculate_metrics,
    calculate_rmse,
)


def test_bias_sign_convention():
    """Verify bias sign convention: forecast - actual.

    Positive bias indicates over-forecasting (forecast > actual).
    Negative bias indicates under-forecasting (forecast < actual).
    """
    actual = np.array([100.0, 100.0])
    forecast_over = np.array([120.0, 110.0])
    forecast_under = np.array([80.0, 90.0])

    bias_over = calculate_bias(actual, forecast_over)
    bias_under = calculate_bias(actual, forecast_under)

    assert bias_over == +15.0  # mean([+20, +10])
    assert bias_under == -15.0  # mean([-20, -10])


def test_mae_and_rmse():
    """Verify vectorized MAE and RMSE on known numerical series."""
    actual = np.array([100.0, 200.0, 300.0])
    # Errors: [-10, +20, -30] -> Absolute: [10, 20, 30] -> Squared: [100, 400, 900]
    forecast = np.array([90.0, 220.0, 270.0])

    mae = calculate_mae(actual, forecast)
    rmse = calculate_rmse(actual, forecast)

    assert pytest.approx(mae) == 20.0  # (10 + 20 + 30) / 3
    assert pytest.approx(rmse) == np.sqrt(1400.0 / 3.0)


def test_mape_standard():
    """Verify MAPE calculates mean(|fc - act| / act) * 100."""
    actual = np.array([100.0, 200.0])
    forecast = np.array([110.0, 180.0])  # errors: +10 (10%), -20 (10%)

    mape = calculate_mape(actual, forecast)
    assert pytest.approx(mape) == 10.0


def test_mape_safe_zero_actuals():
    """Verify MAPE zero handling prevents ZeroDivisionError and handles all-zero actuals."""
    # Mixed: one non-zero (100 -> error 10 = 10%), two zeros
    actual = np.array([0.0, 100.0, 0.0])
    forecast = np.array([50.0, 110.0, 20.0])

    # Default 'filter' mode filters out the zeros and computes on non-zero elements
    mape_filtered = calculate_mape(actual, forecast, zero_handling="filter")
    assert pytest.approx(mape_filtered) == 10.0

    # 'eps' mode avoids division by zero using small epsilon
    mape_eps = calculate_mape(actual, forecast, zero_handling="eps")
    assert np.isfinite(mape_eps)

    # All zeros: returns NaN instead of crashing
    all_zero_act = np.array([0.0, 0.0])
    all_zero_fc = np.array([10.0, 20.0])
    assert np.isnan(calculate_mape(all_zero_act, all_zero_fc, zero_handling="filter"))


def test_error_percentiles():
    """Verify P10, P50 (median), and P90 of signed error distribution."""
    # 10 errors from -50 to +40 in steps of 10
    actual = np.zeros(10)
    forecast = np.array([-50.0, -40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0])

    pcts = calculate_error_percentiles(actual, forecast)
    assert "p10" in pcts and "p50" in pcts and "p90" in pcts
    assert pcts["p10"] < pcts["p50"] < pcts["p90"]
    assert pytest.approx(pcts["p50"]) == -5.0


def test_calculate_metrics_joined_dataframe():
    """Verify calculate_metrics on a joined DataFrame."""
    joined = pd.DataFrame({
        "startTime": pd.date_range("2026-01-01 00:00", periods=4, freq="1h", tz="UTC"),
        "actual": [100.0, 200.0, 300.0, np.nan],  # includes one NaN
        "forecast": [110.0, 190.0, 330.0, 400.0],
    })

    metrics = calculate_metrics(joined)
    assert metrics["count"] == 3
    assert pytest.approx(metrics["mae"]) == (10 + 10 + 30) / 3
    assert pytest.approx(metrics["bias"]) == (10 - 10 + 30) / 3  # +10.0


def test_calculate_metrics_empty():
    """Verify calculate_metrics on an empty DataFrame returns zero count and NaNs."""
    metrics = calculate_metrics(pd.DataFrame(columns=["actual", "forecast"]))
    assert metrics["count"] == 0
    assert np.isnan(metrics["mae"])
    assert np.isnan(metrics["mae_debiased"])
    assert np.isnan(metrics["rmse"])
    assert np.isnan(metrics["bias"])


def test_mae_debiased():
    """Verify MAE after removing mean bias on known constant and variable errors."""
    from backend.app.core.metrics import calculate_mae_debiased

    # Case 1: Pure constant offset (+100 MW bias everywhere)
    # Errors: [+100, +100, +100] -> Mean bias: +100 -> Debiased errors: [0, 0, 0] -> MAE debiased = 0.0
    actual = np.array([200.0, 300.0, 400.0])
    forecast_constant_bias = np.array([300.0, 400.0, 500.0])
    assert pytest.approx(calculate_mae(actual, forecast_constant_bias)) == 100.0
    assert pytest.approx(calculate_mae_debiased(actual, forecast_constant_bias)) == 0.0

    # Case 2: Mean bias = +50, errors = [0, +50, +100] -> debiased = [-50, 0, +50] -> MAE debiased = 33.33
    fc_var = np.array([200.0, 350.0, 500.0])
    assert pytest.approx(calculate_mae(actual, fc_var)) == 50.0  # (0 + 50 + 100)/3
    assert pytest.approx(calculate_mae_debiased(actual, fc_var)) == 100.0 / 3.0

