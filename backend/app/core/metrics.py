"""Forecast evaluation metrics for wind power forecasting.

Core Assumptions & Conventions:
- Error & Bias Sign Convention:
    error_i = forecast_i - actual_i
    Bias = mean(forecast - actual)
  A positive bias indicates over-forecasting (the model predicted more wind than actually occurred).
  A negative bias indicates under-forecasting (the model predicted less wind than actually occurred).
- MAE: Mean Absolute Error = mean(|forecast - actual|).
- RMSE: Root Mean Square Error = sqrt(mean((forecast - actual)^2)).
- MAPE: Mean Absolute Percentage Error = mean(|forecast - actual| / actual) * 100%.
  Safe for Zero Actuals: When actual == 0, division by zero is undefined. By default
  (zero_handling='filter'), zero-actual instances are safely excluded from the MAPE
  denominator. If no non-zero actuals exist, returns NaN.
- Error Percentiles: P10, P50 (median), and P90 of the signed error distribution
  (forecast - actual), characterizing tail forecast errors.
"""

from typing import Dict, Union, Tuple, Optional
import numpy as np
import pandas as pd


def _clean_arrays(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert inputs to 1D float numpy arrays and drop non-finite or paired NaN values."""
    act_arr = np.asarray(actual, dtype=float)
    fc_arr = np.asarray(forecast, dtype=float)

    if act_arr.shape != fc_arr.shape:
        raise ValueError(
            f"Shape mismatch: actual shape {act_arr.shape} != forecast shape {fc_arr.shape}"
        )

    valid_mask = np.isfinite(act_arr) & np.isfinite(fc_arr)
    return act_arr[valid_mask], fc_arr[valid_mask]


def calculate_bias(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
) -> float:
    """Calculate mean forecast bias = mean(forecast - actual).

    Sign convention:
    - Positive: Over-forecasting (forecast > actual).
    - Negative: Under-forecasting (forecast < actual).
    """
    act, fc = _clean_arrays(actual, forecast)
    if len(act) == 0:
        return float(np.nan)
    return float(np.mean(fc - act))


def calculate_mae(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
) -> float:
    """Calculate Mean Absolute Error = mean(|forecast - actual|)."""
    act, fc = _clean_arrays(actual, forecast)
    if len(act) == 0:
        return float(np.nan)
    return float(np.mean(np.abs(fc - act)))


def calculate_rmse(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
) -> float:
    """Calculate Root Mean Square Error = sqrt(mean((forecast - actual)^2))."""
    act, fc = _clean_arrays(actual, forecast)
    if len(act) == 0:
        return float(np.nan)
    return float(np.sqrt(np.mean((fc - act) ** 2)))


def calculate_mape(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
    zero_handling: str = "filter",
    eps: float = 1e-5,
) -> float:
    """Calculate Mean Absolute Percentage Error (%) safely for zero actuals.

    Parameters:
        actual: Ground-truth actual values.
        forecast: Forecast values.
        zero_handling:
            - 'filter' (default): Exclude rows where actual == 0. Returns NaN if all actuals are 0.
            - 'eps': Add epsilon to denominator: |fc - act| / max(|act|, eps).

    Returns:
        MAPE as percentage (e.g. 12.5 for 12.5%).
    """
    act, fc = _clean_arrays(actual, forecast)
    if len(act) == 0:
        return float(np.nan)

    if zero_handling == "filter":
        non_zero = act != 0
        if not np.any(non_zero):
            return float(np.nan)
        return float(np.mean(np.abs((fc[non_zero] - act[non_zero]) / act[non_zero])) * 100.0)
    elif zero_handling == "eps":
        denom = np.maximum(np.abs(act), eps)
        return float(np.mean(np.abs((fc - act) / denom)) * 100.0)
    else:
        raise ValueError(f"Unknown zero_handling mode: {zero_handling}. Use 'filter' or 'eps'.")


def calculate_error_percentiles(
    actual: Union[np.ndarray, pd.Series, list],
    forecast: Union[np.ndarray, pd.Series, list],
    percentiles: Tuple[float, float, float] = (10.0, 50.0, 90.0),
) -> Dict[str, float]:
    """Calculate percentiles of signed error (forecast - actual).

    Parameters:
        actual: Ground-truth actual values.
        forecast: Forecast values.
        percentiles: Tuple of percentiles to compute (default P10, P50/median, P90).

    Returns:
        Dict with keys like 'p10', 'p50', 'p90'.
    """
    act, fc = _clean_arrays(actual, forecast)
    if len(act) == 0:
        return {f"p{int(p)}": float(np.nan) for p in percentiles}

    errors = fc - act
    pct_values = np.percentile(errors, percentiles)
    return {f"p{int(p)}": float(val) for p, val in zip(percentiles, pct_values)}


def calculate_metrics(
    joined_df: pd.DataFrame,
    actual_col: str = "actual",
    forecast_col: str = "forecast",
    zero_handling: str = "filter",
) -> Dict[str, float]:
    """Compute all evaluation metrics on a joined DataFrame of actual vs forecast.

    Returns:
        Dictionary with:
        - count: Number of evaluated hourly records.
        - mae: Mean Absolute Error (MW).
        - rmse: Root Mean Square Error (MW).
        - mape: Mean Absolute Percentage Error (%).
        - bias: Mean Error (MW), where positive indicates over-forecasting.
        - p10: 10th percentile of error (MW).
        - p50: 50th percentile (median) of error (MW).
        - p90: 90th percentile of error (MW).
    """
    if joined_df.empty or actual_col not in joined_df.columns or forecast_col not in joined_df.columns:
        return {
            "count": 0,
            "mae": float(np.nan),
            "rmse": float(np.nan),
            "mape": float(np.nan),
            "bias": float(np.nan),
            "p10": float(np.nan),
            "p50": float(np.nan),
            "p90": float(np.nan),
        }

    act, fc = _clean_arrays(joined_df[actual_col], joined_df[forecast_col])
    n = len(act)
    if n == 0:
        return {
            "count": 0,
            "mae": float(np.nan),
            "rmse": float(np.nan),
            "mape": float(np.nan),
            "bias": float(np.nan),
            "p10": float(np.nan),
            "p50": float(np.nan),
            "p90": float(np.nan),
        }

    pcts = calculate_error_percentiles(act, fc, (10.0, 50.0, 90.0))

    return {
        "count": n,
        "mae": calculate_mae(act, fc),
        "rmse": calculate_rmse(act, fc),
        "mape": calculate_mape(act, fc, zero_handling=zero_handling),
        "bias": calculate_bias(act, fc),
        "p10": pcts.get("p10", float(np.nan)),
        "p50": pcts.get("p50", float(np.nan)),
        "p90": pcts.get("p90", float(np.nan)),
    }
