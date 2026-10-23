"""Forecast selection logic for day-ahead wind power market decisions.

Core Assumption & Definition:
- Local Day Definition: A delivery day is defined by its calendar date in the specified
  local timezone (default 'Europe/London'). On standard days, this comprises 24 hourly
  slots starting at 00:00 local time. On DST transition days, this comprises 23 slots
  (spring forward, 1 hour skipped) or 25 slots (fall back, 1 hour repeated).
- Cutoff Rule: For a delivery day D, the decision is taken at `cutoff_time` on day
  D - day_offset in the local timezone. Any forecast published strictly after the cutoff
  (publishTime > cutoff) is excluded to prevent future leakage. A forecast published exactly
  at cutoff (publishTime == cutoff) is eligible.
- Slot Selection: For each hourly slot of day D, the eligible forecast with the latest
  publishTime is selected.
- Horizon: Calculated as (startTime - publishTime) in decimal hours.
"""

from datetime import date, datetime
from typing import Union
import numpy as np
import pandas as pd


def select_forecast_at_cutoff(
    forecasts_df: pd.DataFrame,
    delivery_date: Union[str, date, datetime, pd.Timestamp],
    cutoff_time: str = "09:00",
    tz: str = "Europe/London",
    day_offset: int = 1,
) -> pd.DataFrame:
    """Select the latest available forecast at or before the decision cutoff.

    Parameters:
        forecasts_df: DataFrame containing at least ['startTime', 'publishTime', 'generation' (or 'forecast')].
        delivery_date: Delivery date as ISO string (YYYY-MM-DD), date, or datetime.
        cutoff_time: Local cutoff time string (e.g. '09:00' or '09:00:00').
        tz: Local timezone string (default 'Europe/London').
        day_offset: Number of days prior to delivery day when decision is made (default 1 for day-ahead).

    Returns:
        DataFrame with one row per hourly startTime of the local delivery day, containing:
        - startTime: UTC Timestamp of each hourly slot start.
        - forecast: Forecasted generation in MW (float, NaN if missing).
        - generation: Alias for forecast (float, NaN if missing).
        - publishTime: Timestamp when the selected forecast was published (NaT if missing).
        - horizon_hours: Lead time in hours between publishTime and startTime (NaN if missing).
    """
    if isinstance(delivery_date, (date, datetime, pd.Timestamp)):
        delivery_date_str = delivery_date.strftime("%Y-%m-%d")
    else:
        delivery_date_str = str(delivery_date).split("T")[0].strip()

    # Define the local day boundaries in tz
    start_local = pd.Timestamp(delivery_date_str).tz_localize(tz)
    end_local = start_local + pd.DateOffset(days=1)

    # Hourly slots for the local delivery day (24 on normal days, 23 on spring forward, 25 on fall back)
    slots_local = pd.date_range(start=start_local, end=end_local, freq="1h", inclusive="left")
    slots_utc = slots_local.tz_convert("UTC")

    # Decision cutoff in tz converted to UTC
    decision_day_local = start_local - pd.DateOffset(days=day_offset)
    parts = [int(p) for p in cutoff_time.split(":")[:3]]
    h = parts[0]
    m = parts[1] if len(parts) > 1 else 0
    s = parts[2] if len(parts) > 2 else 0
    cutoff_local = decision_day_local + pd.Timedelta(hours=h, minutes=m, seconds=s)
    cutoff_utc = cutoff_local.tz_convert("UTC")

    # Base dataframe guaranteeing all expected slots are present
    base_df = pd.DataFrame({"startTime": slots_utc})

    if forecasts_df.empty:
        base_df["forecast"] = np.nan
        base_df["generation"] = np.nan
        base_df["publishTime"] = pd.NaT
        base_df["horizon_hours"] = np.nan
        return base_df

    df = forecasts_df.copy()

    # Ensure UTC-aware timestamps
    if df["startTime"].dt.tz is None:
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    elif str(df["startTime"].dt.tz) != "UTC":
        df["startTime"] = df["startTime"].dt.tz_convert("UTC")

    if df["publishTime"].dt.tz is None:
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    elif str(df["publishTime"].dt.tz) != "UTC":
        df["publishTime"] = df["publishTime"].dt.tz_convert("UTC")

    # Filter: strictly published at or before cutoff, and matches a delivery day slot
    mask = (df["publishTime"] <= cutoff_utc) & (df["startTime"].isin(slots_utc))
    eligible = df[mask]

    if eligible.empty:
        base_df["forecast"] = np.nan
        base_df["generation"] = np.nan
        base_df["publishTime"] = pd.NaT
        base_df["horizon_hours"] = np.nan
        return base_df

    val_col = "forecast" if "forecast" in eligible.columns else "generation"

    # For each startTime slot, pick the row with the latest publishTime
    eligible = eligible.sort_values(by=["startTime", "publishTime"])
    latest_per_slot = eligible.drop_duplicates(subset=["startTime"], keep="last").copy()

    latest_per_slot["forecast"] = latest_per_slot[val_col].astype(float)
    latest_per_slot["generation"] = latest_per_slot["forecast"]
    latest_per_slot["horizon_hours"] = (
        latest_per_slot["startTime"] - latest_per_slot["publishTime"]
    ).dt.total_seconds() / 3600.0

    keep_cols = ["startTime", "forecast", "generation", "publishTime", "horizon_hours"]
    merged = pd.merge(base_df, latest_per_slot[keep_cols], on="startTime", how="left")
    merged = merged.sort_values(by="startTime").reset_index(drop=True)

    return merged
