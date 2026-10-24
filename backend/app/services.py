"""Business logic and service layer for the wind forecast monitoring API."""

from datetime import datetime
from typing import List
import numpy as np
import pandas as pd
from fastapi import HTTPException

from backend.app.core.forecast_selection import select_forecast_at_cutoff
from backend.app.core.grouping import (
    compute_error_by_horizon_bucket,
    compute_error_by_hour_of_day,
    compute_error_histogram_bins,
)
from backend.app.core.metrics import (
    calculate_metrics,
)
from backend.app.data_loader import DataLoader
from backend.app.schemas import (
    AccuracyResponse,
    BacktestDailyItem,
    BacktestResponse,
    BacktestSummary,
    DailySummaryMetrics,
    DecisionSummaryResponse,
    ErrorBandResponse,
    ErrorBandSlot,
    ErrorHistogramBin,
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

    # Error distribution histogram (fixed 500 MW bins)
    histogram_bins = compute_error_histogram_bins(
        combined_df, actual_col="actual", forecast_col="forecast", bin_width=500.0
    )
    histogram_items = [ErrorHistogramBin(**b) for b in histogram_bins]

    return AccuracyResponse(
        start_date=start_valid,
        end_date=end_valid,
        cutoff_time=cutoff_time,
        headline_metrics=HeadlineAccuracyMetrics(**headline_metrics_dict),
        by_hour_of_day=by_hour_items,
        by_horizon=by_horizon_items,
        error_histogram=histogram_items,
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


def get_decision_summary_service(
    date_str: str,
    cutoff_time: str,
    loader: DataLoader,
    tz: str = DEFAULT_TIMEZONE,
) -> DecisionSummaryResponse:
    """Compute day-ahead decision summary, expected wind, shortfall buffer (P90), offset, and risk hours."""
    valid_date = validate_delivery_date(date_str)

    # 1. Select cutoff-aware forecast for the target delivery day
    target_fc = select_forecast_at_cutoff(
        loader.forecasts_df,
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        tz=tz,
        day_offset=1,
    )
    expected_wind_mwh = float(target_fc["forecast"].fillna(0.0).sum())
    slot_count = len(target_fc)
    avg_fc = (expected_wind_mwh / slot_count) if slot_count > 0 else 0.0

    # 2. Determine eligible history delivery days strictly <= D-2
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

    # If fewer than 3 historical days are available, return null buffer fields with reason
    if history_count < 3:
        reason = (
            f"Fewer than 3 historical delivery days available ({history_count} < 3). "
            f"At decision cutoff on D-1 {cutoff_time}, actuals are only complete through D-2 ({d_minus_2_str})."
        )
        recommendation = (
            f"Forecast wind averages {round(avg_fc):,} MW ({round(expected_wind_mwh):,} MWh total). "
            f"Fewer than 3 historical delivery days are available at D-1 {cutoff_time} cutoff to compute "
            f"historical shortfall buffer or typical offset. Demand data is outside scope so the actual procurement volume cannot be computed."
        )
        return DecisionSummaryResponse(
            delivery_date=valid_date,
            cutoff_time=cutoff_time,
            expected_wind_mwh=round(expected_wind_mwh, 1),
            shortfall_buffer_mw=None,
            typical_offset_mw=None,
            bias_adjusted_expected_wind_mwh=None,
            risk_hours=[],
            low_confidence=True,
            history_days_used=history_count,
            history_start_date=eligible_history_dates[0] if eligible_history_dates else None,
            history_end_date=eligible_history_dates[-1] if eligible_history_dates else None,
            recommendation=recommendation,
            reason=reason,
        )

    # 3. Gather historical forecast vs actual pairs strictly <= D-2
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

    # 4. Shortfall buffer: P90 of signed error (forecast - actual), floored at 0
    raw_p90 = float(np.percentile(valid_errors, 90.0))
    shortfall_buffer_mw = max(0.0, raw_p90)

    # 5. Typical offset: median of signed error (persistent bias)
    typical_offset_mw = float(np.median(valid_errors))

    # Buffer relative to bias-adjusted forecast = P90 - median
    shortfall_buffer_rel_adj = round(raw_p90 - typical_offset_mw, 1)

    # 6. Bias-adjusted expected wind: forecast minus typical_offset, floored at 0 per hour
    adjusted_slots = [
        max(0.0, float(fc_val) - typical_offset_mw)
        for fc_val in target_fc["forecast"].fillna(0.0)
    ]
    bias_adjusted_expected_wind_mwh = sum(adjusted_slots)

    # 7. Risk hours: top 3 local hours with highest historical hour-of-day mean over-forecast, sorted ascending
    if hist_df["startTime"].dt.tz is None:
        hist_local_times = pd.to_datetime(hist_df["startTime"], utc=True).dt.tz_convert(tz)
    else:
        hist_local_times = hist_df["startTime"].dt.tz_convert(tz)
    hist_df["local_hour"] = hist_local_times.dt.hour

    hour_means = hist_df.groupby("local_hour")["error"].mean()
    top_hours = hour_means.sort_values(ascending=False).head(3).index.tolist()
    risk_hours = sorted([int(h) for h in top_hours])

    # Confidence assessment: low confidence if fewer than 7 days
    low_confidence = history_count < 7

    # 8. Recommendation text
    offset_dir = "above" if typical_offset_mw >= 0 else "below"
    offset_abs = abs(round(typical_offset_mw))
    buffer_round = round(shortfall_buffer_mw)
    risk_hours_str = ", ".join(f"{h:02d}:00" for h in risk_hours) if risk_hours else "peak hours"

    recommendation = (
        f"Forecast wind averages {round(avg_fc):,} MW. "
        f"Historically forecasts ran {offset_abs:,} MW {offset_dir} actual (median, {history_count} days). "
        f"Plan for up to {buffer_round:,} MW less wind than forecast (P90); "
        f"consider covering that with thermal/other sources, especially around {risk_hours_str}. "
        f"Demand data is outside scope so the actual procurement volume cannot be computed."
    )

    return DecisionSummaryResponse(
        delivery_date=valid_date,
        cutoff_time=cutoff_time,
        expected_wind_mwh=round(expected_wind_mwh, 1),
        shortfall_buffer_mw=round(shortfall_buffer_mw, 1),
        shortfall_buffer_relative_to_adjusted_mw=shortfall_buffer_rel_adj,
        typical_offset_mw=round(typical_offset_mw, 1),
        bias_adjusted_expected_wind_mwh=round(bias_adjusted_expected_wind_mwh, 1),
        risk_hours=risk_hours,
        low_confidence=low_confidence,
        history_days_used=history_count,
        history_start_date=eligible_history_dates[0],
        history_end_date=eligible_history_dates[-1],
        recommendation=recommendation,
        reason=None,
    )


def get_backtest_service(
    cutoff_time: str = DEFAULT_CUTOFF,
    loader: DataLoader = None,
    tz: str = DEFAULT_TIMEZONE,
) -> BacktestResponse:
    """Run rolling, leakage-free backtest across delivery days 2026-01-02 to 2026-02-01.

    For each delivery day D with >= 3 history days (<= D-2, buffer allowed from 2025-12-29):
    1. Compute typical_offset (median) and shortfall_buffer (P90 floored at 0) from history <= D-2.
    2. Evaluate on day D:
       - MAE of raw forecast
       - MAE of bias-adjusted forecast (forecast - offset, floored at 0 per hour)
       - Buffer breach rate: fraction of hours on day D where actual < forecast - buffer.
    """
    if loader is None:
        raise ValueError("DataLoader instance must be provided.")

    # Dates to pre-extract: from buffer start (2025-12-29) through end of January (2026-02-01)
    all_dates = [
        d.strftime("%Y-%m-%d")
        for d in pd.date_range(BUFFER_HISTORY_START_DATE, MAX_DELIVERY_DATE, freq="1D")
    ]

    day_df_map = {}
    for d_str in all_dates:
        fc = select_forecast_at_cutoff(
            loader.forecasts_df,
            delivery_date=d_str,
            cutoff_time=cutoff_time,
            tz=tz,
            day_offset=1,
        )
        st_local = pd.Timestamp(d_str).tz_localize(tz)
        end_local = st_local + pd.DateOffset(days=1)
        st_utc = st_local.tz_convert("UTC")
        end_utc = end_local.tz_convert("UTC")

        act = loader.hourly_actuals_df[
            (loader.hourly_actuals_df["startTime"] >= st_utc)
            & (loader.hourly_actuals_df["startTime"] < end_utc)
        ]
        joined = pd.merge(fc, act[["startTime", "actual"]], on="startTime", how="inner")
        joined["error"] = joined["forecast"] - joined["actual"]
        day_df_map[d_str] = joined

    eval_dates = [
        d.strftime("%Y-%m-%d")
        for d in pd.date_range(MIN_DELIVERY_DATE, MAX_DELIVERY_DATE, freq="1D")
    ]

    daily_items: List[BacktestDailyItem] = []

    for d_str in eval_dates:
        target_dt = pd.Timestamp(d_str)
        d_minus_2_str = (target_dt - pd.Timedelta(days=2)).strftime("%Y-%m-%d")

        eligible_history = [d for d in all_dates if BUFFER_HISTORY_START_DATE <= d <= d_minus_2_str]
        if len(eligible_history) < 3:
            continue

        hist_dfs = [day_df_map[d] for d in eligible_history if d in day_df_map and not day_df_map[d].empty]
        if not hist_dfs:
            continue
        combined_hist = pd.concat(hist_dfs, ignore_index=True)
        hist_errors = combined_hist["error"].dropna().values
        if len(hist_errors) == 0:
            continue

        typical_offset = float(np.median(hist_errors))
        shortfall_buffer = max(0.0, float(np.percentile(hist_errors, 90.0)))

        target_df = day_df_map.get(d_str)
        if target_df is None or target_df.empty:
            continue

        raw_errors = (target_df["forecast"] - target_df["actual"]).dropna().values
        mae_raw = float(np.mean(np.abs(raw_errors)))

        adjusted_forecast = np.maximum(0.0, target_df["forecast"].values - typical_offset)
        adjusted_errors = adjusted_forecast - target_df["actual"].values
        mae_adjusted = float(np.mean(np.abs(adjusted_errors)))

        # Buffer breach: actual < forecast - buffer
        breaches = target_df["actual"].values < (target_df["forecast"].values - shortfall_buffer)
        breach_count = int(np.sum(breaches))
        slot_count = int(len(target_df))
        breach_rate = float(breach_count / slot_count) if slot_count > 0 else 0.0

        daily_items.append(
            BacktestDailyItem(
                delivery_date=d_str,
                history_days_used=len(eligible_history),
                typical_offset_mw=round(typical_offset, 1),
                shortfall_buffer_mw=round(shortfall_buffer, 1),
                mae_raw=round(mae_raw, 1),
                mae_adjusted=round(mae_adjusted, 1),
                adjusted_beats_raw=bool(mae_adjusted < mae_raw),
                breach_count=breach_count,
                slot_count=slot_count,
                breach_rate=round(breach_rate, 4),
            )
        )

    days_eval = len(daily_items)
    mean_raw = float(np.mean([d.mae_raw for d in daily_items])) if days_eval > 0 else 0.0
    mean_adj = float(np.mean([d.mae_adjusted for d in daily_items])) if days_eval > 0 else 0.0
    beats_count = sum(1 for d in daily_items if d.adjusted_beats_raw)
    beats_pct = (beats_count / days_eval * 100.0) if days_eval > 0 else 0.0
    tot_breaches = sum(d.breach_count for d in daily_items)
    tot_slots = sum(d.slot_count for d in daily_items)
    overall_breach_rate = (tot_breaches / tot_slots) if tot_slots > 0 else 0.0

    summary = BacktestSummary(
        days_evaluated=days_eval,
        mean_mae_raw=round(mean_raw, 1),
        mean_mae_adjusted=round(mean_adj, 1),
        days_adjusted_beats_raw=beats_count,
        days_adjusted_beats_raw_pct=round(beats_pct, 1),
        total_breaches=tot_breaches,
        total_slots=tot_slots,
        overall_breach_rate=round(overall_breach_rate, 4),
    )

    return BacktestResponse(
        cutoff_time=cutoff_time,
        summary=summary,
        daily=daily_items,
    )



