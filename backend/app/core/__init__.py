"""Core domain logic for wind-power forecast monitoring."""

from backend.app.core.forecast_selection import select_forecast_at_cutoff
from backend.app.core.actuals import aggregate_actuals_hourly
from backend.app.core.metrics import (
    calculate_mae,
    calculate_rmse,
    calculate_mape,
    calculate_bias,
    calculate_error_percentiles,
    calculate_metrics,
)
from backend.app.core.grouping import (
    compute_error_by_hour_of_day,
    compute_error_by_horizon_bucket,
)

__all__ = [
    "select_forecast_at_cutoff",
    "aggregate_actuals_hourly",
    "calculate_mae",
    "calculate_rmse",
    "calculate_mape",
    "calculate_bias",
    "calculate_error_percentiles",
    "calculate_metrics",
    "compute_error_by_hour_of_day",
    "compute_error_by_horizon_bucket",
]
