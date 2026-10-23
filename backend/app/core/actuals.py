"""Actuals processing and hourly aggregation.

Core Assumption & Definition:
- Resolution Alignment (Option A): FUELHH actuals arrive in 30-minute settlement
  periods starting at :00 and :30. To align with hourly WINDFOR forecasts, actuals
  are aggregated to hourly intervals starting at HH:00 by computing the arithmetic mean
  of the two constituent 30-minute periods:
      Actual_hourly(H) = (Actual(H:00) + Actual(H:30)) / 2
- Incomplete Hours: If an hour contains only one half-hour settlement period, it is
  dropped by default (drop_incomplete=True) to avoid comparing partial-hour energy/power
  against full-hour forecasts. Alternatively, setting drop_incomplete=False retains the
  record with an `is_complete=False` boolean flag.
"""

import pandas as pd


def aggregate_actuals_hourly(
    actuals_df: pd.DataFrame,
    drop_incomplete: bool = True,
) -> pd.DataFrame:
    """Aggregate half-hourly actuals to hourly resolution.

    Parameters:
        actuals_df: DataFrame with 'startTime' (UTC) and 'generation' (or 'actual').
        drop_incomplete: If True, drop hours where either :00 or :30 is missing.
                         If False, compute mean over available periods and add 'is_complete'.

    Returns:
        DataFrame with:
        - startTime: UTC Timestamp at the start of the hour (:00).
        - actual: Aggregated generation in MW (float).
        - generation: Alias for actual (float).
        - (optional) is_complete: Boolean indicating whether both :00 and :30 were present.
    """
    if actuals_df.empty:
        cols = ["startTime", "actual", "generation"]
        if not drop_incomplete:
            cols.append("is_complete")
        return pd.DataFrame(columns=cols)

    df = actuals_df.copy()

    # Ensure UTC-aware timestamp
    if df["startTime"].dt.tz is None:
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    elif str(df["startTime"].dt.tz) != "UTC":
        df["startTime"] = df["startTime"].dt.tz_convert("UTC")

    val_col = "actual" if "actual" in df.columns else "generation"

    # Deduplicate exact duplicate settlement timestamps if any exist
    df = df.drop_duplicates(subset=["startTime"]).sort_values(by="startTime")

    # Map each settlement period to its hourly start slot
    df["hour_start"] = df["startTime"].dt.floor("1h")

    # Group by hourly slot and inspect completeness
    def process_hour_group(group: pd.DataFrame) -> pd.Series:
        minutes = set(group["startTime"].dt.minute)
        has_both_half_hours = (len(group) == 2) and (minutes == {0, 30})
        mean_val = group[val_col].mean()
        return pd.Series({
            "actual": float(mean_val),
            "generation": float(mean_val),
            "is_complete": bool(has_both_half_hours),
        })

    aggregated = df.groupby("hour_start", as_index=False).apply(
        process_hour_group,
        include_groups=False,
    )
    aggregated = aggregated.rename(columns={"hour_start": "startTime"})

    if drop_incomplete:
        aggregated = aggregated[aggregated["is_complete"]].drop(columns=["is_complete"])
    
    aggregated = aggregated.sort_values(by="startTime").reset_index(drop=True)
    return aggregated
