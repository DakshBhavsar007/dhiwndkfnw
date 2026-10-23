"""Group-by error analysis utilities: error by hour-of-day and by horizon bucket."""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from backend.app.core.metrics import calculate_metrics


def compute_error_by_hour_of_day(
    joined_df: pd.DataFrame,
    tz: str = "Europe/London",
    time_col: str = "startTime",
    actual_col: str = "actual",
    forecast_col: str = "forecast",
) -> pd.DataFrame:
    """Compute forecast evaluation metrics grouped by local hour of day (0-23).

    Parameters:
        joined_df: DataFrame containing at least `time_col`, `actual_col`, and `forecast_col`.
        tz: Timezone to determine the local hour of day (default 'Europe/London').
        time_col: Column name containing the UTC hourly timestamp.
        actual_col: Column name for actual outturn generation.
        forecast_col: Column name for forecasted generation.

    Returns:
        DataFrame indexed/sorted by `hour_of_day` (0 to 23) with evaluation metrics:
        ['hour_of_day', 'count', 'mae', 'rmse', 'mape', 'bias', 'p10', 'p50', 'p90']
    """
    if joined_df.empty:
        return pd.DataFrame(
            columns=["hour_of_day", "count", "mae", "rmse", "mape", "bias", "p10", "p50", "p90"]
        )

    df = joined_df.copy()

    # Convert timestamp to local timezone to extract hour of day
    if df[time_col].dt.tz is None:
        local_time = pd.to_datetime(df[time_col], utc=True).dt.tz_convert(tz)
    else:
        local_time = df[time_col].dt.tz_convert(tz)

    df["hour_of_day"] = local_time.dt.hour

    rows = []
    # Guarantee all 24 hours appear in output if data exists or iterate over unique groups
    for hour, grp in df.groupby("hour_of_day"):
        m = calculate_metrics(grp, actual_col=actual_col, forecast_col=forecast_col)
        m["hour_of_day"] = int(hour)
        rows.append(m)

    out_df = pd.DataFrame(rows)
    cols = ["hour_of_day", "count", "mae", "rmse", "mape", "bias", "p10", "p50", "p90"]
    out_df = out_df[[c for c in cols if c in out_df.columns]].sort_values(by="hour_of_day").reset_index(drop=True)
    return out_df


def compute_error_by_horizon_bucket(
    joined_df: pd.DataFrame,
    bins: Optional[List[float]] = None,
    labels: Optional[List[str]] = None,
    horizon_col: str = "horizon_hours",
    actual_col: str = "actual",
    forecast_col: str = "forecast",
) -> pd.DataFrame:
    """Compute forecast evaluation metrics grouped by lead time (forecast horizon) bucket.

    Parameters:
        joined_df: DataFrame containing `horizon_col`, `actual_col`, and `forecast_col`.
        bins: Bin edges for forecast horizons in hours (default: [0, 12, 24, 36, 48, 72]).
        labels: Names for the bins (default: ['0-12h', '12-24h', '24-36h', '36-48h', '48-72h']).
        horizon_col: Column name containing the forecast lead time in hours.
        actual_col: Column name for actual outturn generation.
        forecast_col: Column name for forecasted generation.

    Returns:
        DataFrame grouped by `horizon_bucket` with evaluation metrics:
        ['horizon_bucket', 'count', 'mae', 'rmse', 'mape', 'bias', 'p10', 'p50', 'p90']
    """
    if bins is None:
        bins = [0.0, 12.0, 24.0, 36.0, 48.0, 72.0]
    if labels is None:
        labels = ["0-12h", "12-24h", "24-36h", "36-48h", "48-72h"]

    if joined_df.empty or horizon_col not in joined_df.columns:
        return pd.DataFrame(
            columns=["horizon_bucket", "count", "mae", "rmse", "mape", "bias", "p10", "p50", "p90"]
        )

    df = joined_df.copy()
    df["horizon_bucket"] = pd.cut(df[horizon_col], bins=bins, labels=labels, right=False)

    rows = []
    for bucket in labels:
        grp = df[df["horizon_bucket"] == bucket]
        m = calculate_metrics(grp, actual_col=actual_col, forecast_col=forecast_col)
        m["horizon_bucket"] = str(bucket)
        rows.append(m)

    out_df = pd.DataFrame(rows)
    cols = ["horizon_bucket", "count", "mae", "rmse", "mape", "bias", "p10", "p50", "p90"]
    return out_df[cols].reset_index(drop=True)


def compute_error_histogram_bins(
    joined_df: pd.DataFrame,
    actual_col: str = "actual",
    forecast_col: str = "forecast",
    bin_width: float = 500.0,
) -> List[Dict[str, Any]]:
    """Compute fixed 500 MW bins of signed error (forecast - actual).

    Parameters:
        joined_df: DataFrame containing actual and forecast columns.
        actual_col: Column name for actual outturn.
        forecast_col: Column name for forecast.
        bin_width: Fixed bin width in MW (default 500.0).

    Returns:
        List of dicts with:
        ['bin_start', 'bin_end', 'bin_label', 'count']
    """
    if actual_col not in joined_df.columns and "generation" in joined_df.columns and forecast_col != "generation":
        actual_col = "generation"
    elif forecast_col not in joined_df.columns and "generation" in joined_df.columns and actual_col != "generation":
        forecast_col = "generation"

    if joined_df.empty or actual_col not in joined_df.columns or forecast_col not in joined_df.columns:
        return []

    act = pd.to_numeric(joined_df[actual_col], errors="coerce")
    fc = pd.to_numeric(joined_df[forecast_col], errors="coerce")
    valid = np.isfinite(act) & np.isfinite(fc)

    if not np.any(valid):
        return []

    errors = (fc[valid] - act[valid]).to_numpy()
    min_err = float(np.min(errors))
    max_err = float(np.max(errors))

    start = float(np.floor(min_err / bin_width) * bin_width)
    end = float(np.ceil(max_err / bin_width) * bin_width)
    if start == end:
        end += bin_width

    bin_edges = np.arange(start, end + bin_width, bin_width)
    counts, edges = np.histogram(errors, bins=bin_edges)

    out = []
    for i in range(len(counts)):
        b_start = float(edges[i])
        b_end = float(edges[i + 1])
        s_str = f"{int(b_start):+d}" if b_start != 0 else "0"
        e_str = f"{int(b_end):+d}" if b_end != 0 else "0"
        out.append({
            "bin_start": b_start,
            "bin_end": b_end,
            "bin_label": f"{s_str} to {e_str} MW",
            "count": int(counts[i]),
        })
    return out

