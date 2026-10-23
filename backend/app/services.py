"""Business logic and service layer for the wind forecast monitoring API."""

from datetime import datetime
from typing import List, Optional
import numpy as np
import pandas as pd
from fastapi import HTTPException

from backend.app.core.forecast_selection import select_forecast_at_cutoff
from backend.app.core.grouping import (
    compute_error_by_horizon_bucket,
    compute_error_by_hour_of_day,
)
from backend.app.core.metrics import (
    calculate_error_percentiles,
    calculate_metrics,
)
from backend.app.data_loader import DataLoader
from backend.app.schemas import (
    AccuracyResponse,
    DailySummaryMetrics,
    ErrorBandResponse,
    ErrorBandSlot,
    ForecastResponse,
    HeadlineAccuracyMetrics,
    HorizonBreakdownItem,
    HourOfDayBreakdownItem,
    HourlyForecastSlot,
    MetaResponse,
    RawActual30Min,
)

MIN_DELIVERY_DATE = "2026-01-02"
MAX_DELIVERY_DATE = "2026-02-01"
DEFAULT_TIMEZONE = "Europe/London"
DEFAULT_CUTOFF = "09:00"


def validate_delivery_date(date_str: str) -> str:
    """Validate that date_str is a valid ISO date within [MIN_DELIVERY_DATE, MAX_DELIVERY_DATE]."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.",
        )

    clean_str = dt.isoformat()
    if clean_str < MIN_DELIVERY_DATE or clean_str > MAX_DELIVERY_DATE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Delivery date '{clean_str}' is outside the supported range "
                f"[{MIN_DELIVERY_DATE}, {MAX_DELIVERY_DATE}]. Decisions were made in January 2026."
            ),
        )
    return clean_str


def get_all_valid_dates() -> List[str]:
    """Return all 31 valid delivery dates as ISO date strings."""
    return [
        d.strftime("%Y-%m-%d")
        for d in pd.date_range(MIN_DELIVERY_DATE, MAX_DELIVERY_DATE, freq="1D")
    ]


def get_meta_service() -> MetaResponse:
    """Return system metadata, valid date range, and resolution documentation."""
    return MetaResponse()


def get_forecast_service(
    date_str: str,
    cutoff_time: str,
    loader: DataLoader,
    tz: str = DEFAULT_TIMEZONE,
) -> ForecastResponse:
    """Retrieve cutoff-aware hourly forecast, hourly actuals, raw 30-min actuals, and summary metrics."""
    valid_date = validate_delivery_date(date_str)

    # 1. Select cutoff-aware forecast for the delivery day
    fc_df = select_forecast_at_cutoff(
        loader.forecasts_df,
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        tz=tz,
        day_offset=1,
    )

    # 2. Get local day boundary in UTC
    start_local = pd.Timestamp(valid_date).tz_localize(tz)
    end_local = start_local + pd.DateOffset(days=1)
    start_utc = start_local.tz_convert("UTC")
    end_utc = end_local.tz_convert("UTC")

    # 3. Filter hourly aggregated actuals
    hourly_actuals = loader.hourly_actuals_df[
        (loader.hourly_actuals_df["startTime"] >= start_utc)
        & (loader.hourly_actuals_df["startTime"] < end_utc)
    ]

    # 4. Filter raw 30-min actuals
    raw_actuals = loader.actuals_df[
        (loader.actuals_df["startTime"] >= start_utc)
        & (loader.actuals_df["startTime"] < end_utc)
    ].sort_values(by="startTime")

    # 5. Join hourly forecast and hourly actuals on startTime
    joined = pd.merge(fc_df, hourly_actuals[["startTime", "actual"]], on="startTime", how="left")
    joined["error"] = joined["forecast"] - joined["actual"]

    # 6. Compute summary metrics for the day
    metrics_dict = calculate_metrics(joined, actual_col="actual", forecast_col="forecast")

    # Build response hourly items
    hourly_items: List[HourlyForecastSlot] = []
    for _, row in joined.iterrows():
        st_utc = row["startTime"]
        st_local = st_utc.tz_convert(tz).isoformat()
        pub_iso = row["publishTime"].isoformat() if pd.notna(row["publishTime"]) else None
        fc_val = float(row["forecast"]) if pd.notna(row["forecast"]) else None
        act_val = float(row["actual"]) if pd.notna(row["actual"]) else None
        err_val = float(row["error"]) if pd.notna(row["error"]) else None
        hor_val = float(row["horizon_hours"]) if pd.notna(row["horizon_hours"]) else None

        hourly_items.append(
            HourlyForecastSlot(
                startTime=st_utc.isoformat(),
                startTime_local=st_local,
                forecast=fc_val,
                actual=act_val,
                error=err_val,
                publishTime=pub_iso,
                horizon_hours=hor_val,
            )
        )

    # Build raw 30-minute actuals items
    raw_items: List[RawActual30Min] = []
    for _, row in raw_actuals.iterrows():
        st_utc = row["startTime"]
        raw_items.append(
            RawActual30Min(
                startTime=st_utc.isoformat(),
                startTime_local=st_utc.tz_convert(tz).isoformat(),
                generation=float(row["generation"]),
            )
        )

    # Compute decision cutoff UTC timestamp for clarity
    decision_day_local = start_local - pd.DateOffset(days=1)
    parts = [int(p) for p in cutoff_time.split(":")[:2]]
    cutoff_local = decision_day_local + pd.Timedelta(hours=parts[0], minutes=parts[1])
    decision_time_utc = cutoff_local.tz_convert("UTC").isoformat()

    return ForecastResponse(
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        decision_time_utc=decision_time_utc,
        hourly=hourly_items,
        raw_actuals_30min=raw_items,
        summary_metrics=DailySummaryMetrics(**metrics_dict),
    )


def get_accuracy_service(
    start_str: str,
    end_str: str,
    cutoff_time: str,
    loader: DataLoader,
    tz: str = DEFAULT_TIMEZONE,
) -> AccuracyResponse:
    """Compute headline accuracy, hour-of-day breakdown, and all-publishTime horizon breakdown."""
    start_valid = validate_delivery_date(start_str)
    end_valid = validate_delivery_date(end_str)

    if start_valid > end_valid:
        raise HTTPException(
            status_code=422,
            detail=f"start_date '{start_valid}' must be earlier than or equal to end_date '{end_valid}'.",
        )

    date_range = [
        d.strftime("%Y-%m-%d")
        for d in pd.date_range(start_valid, end_valid, freq="1D")
    ]

    # --- Part A: Headline metrics and by-hour breakdown (cutoff-selected forecasts) ---
    all_joined_list: List[pd.DataFrame] = []
    for d_str in date_range:
        fc = select_forecast_at_cutoff(
            loader.forecasts_df,
            delivery_date=d_str,
            cutoff_time=cutoff_time,
            tz=tz,
            day_offset=1,
        )
        # Match with hourly actuals
        st_local = pd.Timestamp(d_str).tz_localize(tz)
        end_local = st_local + pd.DateOffset(days=1)
        st_utc = st_local.tz_convert("UTC")
        end_utc = end_local.tz_convert("UTC")

        act = loader.hourly_actuals_df[
            (loader.hourly_actuals_df["startTime"] >= st_utc)
            & (loader.hourly_actuals_df["startTime"] < end_utc)
        ]
        joined = pd.merge(fc, act[["startTime", "actual"]], on="startTime", how="inner")
        all_joined_list.append(joined)

    if all_joined_list:
        combined_df = pd.concat(all_joined_list, ignore_index=True)
    else:
        combined_df = pd.DataFrame()

    headline_metrics_dict = calculate_metrics(combined_df, actual_col="actual", forecast_col="forecast")

    # Hour of day breakdown
    by_hour_df = compute_error_by_hour_of_day(
        combined_df, tz=tz, actual_col="actual", forecast_col="forecast"
    )
    by_hour_items = [
        HourOfDayBreakdownItem(**row.to_dict()) for _, row in by_hour_df.iterrows()
    ]

    # --- Part B: By-horizon breakdown across ALL publishTime runs joined to actuals ---
    # Horizon buckets: 12-18, 18-24, 24-30, 30-36, 36-42h
    overall_start_utc = pd.Timestamp(start_valid).tz_localize(tz).tz_convert("UTC")
    overall_end_utc = (pd.Timestamp(end_valid).tz_localize(tz) + pd.DateOffset(days=1)).tz_convert("UTC")

    window_actuals = loader.hourly_actuals_df[
        (loader.hourly_actuals_df["startTime"] >= overall_start_utc)
        & (loader.hourly_actuals_df["startTime"] < overall_end_utc)
    ]

    fc_all = loader.forecasts_df[
        loader.forecasts_df["startTime"].isin(window_actuals["startTime"])
    ].copy()

    merged_all = pd.merge(
        fc_all, window_actuals[["startTime", "actual"]], on="startTime", how="inner"
    )
    merged_all["horizon_hours"] = (
        merged_all["startTime"] - merged_all["publishTime"]
    ).dt.total_seconds() / 3600.0

    bins = [12.0, 18.0, 24.0, 30.0, 36.0, 42.0]
    labels = ["12-18h", "18-24h", "24-30h", "30-36h", "36-42h"]

    by_horizon_df = compute_error_by_horizon_bucket(
        merged_all,
        bins=bins,
        labels=labels,
        horizon_col="horizon_hours",
        actual_col="actual",
        forecast_col="generation",
    )

    by_horizon_items = [
        HorizonBreakdownItem(**row.to_dict()) for _, row in by_horizon_df.iterrows()
    ]

    return AccuracyResponse(
        start_date=start_valid,
        end_date=end_valid,
        cutoff_time=cutoff_time,
        headline_metrics=HeadlineAccuracyMetrics(**headline_metrics_dict),
        by_hour_of_day=by_hour_items,
        by_horizon=by_horizon_items,
    )


BUFFER_HISTORY_START_DATE = "2025-12-29"


def get_error_band_service(
    date_str: str,
    cutoff_time: str,
    loader: DataLoader,
    tz: str = DEFAULT_TIMEZONE,
) -> ErrorBandResponse:
    """Compute forecast with historical error bounds adhering strictly to the D-2 leakage rule."""
    valid_date = validate_delivery_date(date_str)

    # Leakage Rule: At decision time on D-1 09:00, actuals of D-1 are incomplete.
    # Therefore, historical delivery days used must be strictly <= D-2.
    # We allow historical days from the fetched buffer: delivery days from 2025-12-29 onward.
    target_dt = pd.Timestamp(valid_date)
    d_minus_2_str = (target_dt - pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    if d_minus_2_str < BUFFER_HISTORY_START_DATE:
        eligible_history_dates = []
    else:
        eligible_history_dates = [
            d.strftime("%Y-%m-%d")
            for d in pd.date_range(BUFFER_HISTORY_START_DATE, d_minus_2_str, freq="1D")
        ]

    history_count = len(eligible_history_dates)

    if history_count < 3:
        return ErrorBandResponse(
            delivery_date=valid_date,
            cutoff_time=cutoff_time,
            history_days_used=history_count,
            history_start_date=eligible_history_dates[0] if eligible_history_dates else None,
            history_end_date=eligible_history_dates[-1] if eligible_history_dates else None,
            band=None,
            reason=(
                f"Fewer than 3 historical delivery days available ({history_count} < 3). "
                f"At decision cutoff on D-1 {cutoff_time}, actuals are only complete through D-2 ({d_minus_2_str})."
            ),
        )

    # 1. Gather historical error pairs from eligible days using the exact same cutoff rule
    hist_joined_list: List[pd.DataFrame] = []
    for h_date in eligible_history_dates:
        fc = select_forecast_at_cutoff(
            loader.forecasts_df,
            delivery_date=h_date,
            cutoff_time=cutoff_time,
            tz=tz,
            day_offset=1,
        )
        st_local = pd.Timestamp(h_date).tz_localize(tz)
        end_local = st_local + pd.DateOffset(days=1)
        st_utc = st_local.tz_convert("UTC")
        end_utc = end_local.tz_convert("UTC")

        act = loader.hourly_actuals_df[
            (loader.hourly_actuals_df["startTime"] >= st_utc)
            & (loader.hourly_actuals_df["startTime"] < end_utc)
        ]
        joined = pd.merge(fc, act[["startTime", "actual"]], on="startTime", how="inner")
        joined["error"] = joined["forecast"] - joined["actual"]
        hist_joined_list.append(joined)

    hist_df = pd.concat(hist_joined_list, ignore_index=True)
    valid_errors = hist_df["error"].dropna().values

    # Percentiles of signed error (error = forecast - actual, positive = over-forecast)
    p10_error = float(np.percentile(valid_errors, 10.0))
    p90_error = float(np.percentile(valid_errors, 90.0))

    # 2. Select forecast for the target delivery day
    target_fc = select_forecast_at_cutoff(
        loader.forecasts_df,
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        tz=tz,
        day_offset=1,
    )

    # 3. Construct error bands for ACTUAL generation:
    # error = forecast - actual  =>  actual = forecast - error
    # lower = forecast - P90(error), upper = forecast - P10(error), both clipped at 0
    band_slots: List[ErrorBandSlot] = []
    for _, row in target_fc.iterrows():
        fc_val = float(row["forecast"]) if pd.notna(row["forecast"]) else 0.0

        lower_bound = max(0.0, fc_val - p90_error)
        upper_bound = max(0.0, fc_val - p10_error)

        band_slots.append(
            ErrorBandSlot(
                startTime=row["startTime"].isoformat(),
                startTime_local=row["startTime"].tz_convert(tz).isoformat(),
                forecast=round(fc_val, 1),
                lower_bound=round(lower_bound, 1),
                upper_bound=round(upper_bound, 1),
                p10_error=round(p10_error, 1),
                p90_error=round(p90_error, 1),
            )
        )

    return ErrorBandResponse(
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        history_days_used=history_count,
        history_start_date=eligible_history_dates[0],
        history_end_date=eligible_history_dates[-1],
        band=band_slots,
        reason=None,
    )

