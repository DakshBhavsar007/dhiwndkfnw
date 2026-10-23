"""Pydantic schemas and request/response models for the wind-forecast API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Server status")
    version: str = Field("1.0.0", description="API version")
    data_loaded: bool = Field(True, description="Whether data snapshots are successfully loaded into memory")


class MetaResponse(BaseModel):
    valid_start_date: str = Field("2026-01-02", description="Earliest valid delivery date (YYYY-MM-DD)")
    valid_end_date: str = Field("2026-02-01", description="Latest valid delivery date (YYYY-MM-DD)")
    total_delivery_days: int = Field(31, description="Total delivery days in scope")
    default_cutoff_time: str = Field("09:00", description="Default day-ahead decision cutoff time in Europe/London on D-1")
    timezone: str = Field("Europe/London", description="Market timezone")
    actuals_resolution: str = Field("Half-hourly (30-min settlement periods starting at :00 and :30, FUELHH stream)")
    forecast_resolution: str = Field("Hourly (starting at :00, 73 rows per run, WINDFOR stream)")
    alignment_rule: str = Field(
        "Option A: Actuals aggregated to hourly arithmetic mean of HH:00 and HH:30 for evaluation joins; raw 30-min actuals preserved for charts"
    )
    bias_convention: str = Field(
        "forecast - actual. Positive values indicate over-forecasting (forecast > actual); negative values indicate under-forecasting."
    )


class HourlyForecastSlot(BaseModel):
    startTime: str = Field(..., description="UTC ISO string of the hourly slot start")
    startTime_local: str = Field(..., description="Local Europe/London ISO string of the slot start")
    forecast: Optional[float] = Field(None, description="Selected forecasted wind generation in MW")
    actual: Optional[float] = Field(None, description="Hourly aggregated outturn wind generation in MW")
    error: Optional[float] = Field(None, description="Signed error = forecast - actual in MW (positive = over-forecast)")
    publishTime: Optional[str] = Field(None, description="UTC ISO string of the forecast publication run used")
    horizon_hours: Optional[float] = Field(None, description="Lead time in hours = (startTime - publishTime)")


class RawActual30Min(BaseModel):
    startTime: str = Field(..., description="UTC ISO string of the 30-minute settlement period start")
    startTime_local: str = Field(..., description="Local Europe/London ISO string")
    generation: float = Field(..., description="Outturn half-hourly wind generation in MW")


class DailySummaryMetrics(BaseModel):
    count: int = Field(..., description="Number of evaluated hourly slots")
    mae: Optional[float] = Field(None, description="Mean Absolute Error in MW")
    rmse: Optional[float] = Field(None, description="Root Mean Square Error in MW")
    mape: Optional[float] = Field(None, description="Mean Absolute Percentage Error (%)")
    bias: Optional[float] = Field(None, description="Mean Error = mean(forecast - actual) in MW")
    p10: Optional[float] = Field(None, description="10th percentile of signed error in MW")
    p50: Optional[float] = Field(None, description="50th percentile (median) of signed error in MW")
    p90: Optional[float] = Field(None, description="90th percentile of signed error in MW")


class ForecastResponse(BaseModel):
    delivery_date: str = Field(..., description="Delivery date (YYYY-MM-DD)")
    cutoff_time: str = Field(..., description="Decision cutoff time on D-1")
    decision_time_utc: str = Field(..., description="UTC timestamp of the decision cutoff threshold")
    hourly: List[HourlyForecastSlot] = Field(..., description="Per-hour forecast, actual, and error")
    raw_actuals_30min: List[RawActual30Min] = Field(..., description="Raw 30-minute actual settlement periods")
    summary_metrics: DailySummaryMetrics = Field(..., description="Summary accuracy metrics for the delivery day")


class HeadlineAccuracyMetrics(BaseModel):
    count: int = Field(..., description="Total evaluated hourly slots")
    mae: Optional[float] = Field(None, description="Mean Absolute Error (MW)")
    rmse: Optional[float] = Field(None, description="Root Mean Square Error (MW)")
    mape: Optional[float] = Field(None, description="Mean Absolute Percentage Error (%)")
    bias: Optional[float] = Field(None, description="Mean Error = mean(forecast - actual) (MW)")
    p10: Optional[float] = Field(None, description="10th percentile of signed error (MW)")
    p50: Optional[float] = Field(None, description="50th percentile (median) of signed error (MW)")
    p90: Optional[float] = Field(None, description="90th percentile of signed error (MW)")


class HourOfDayBreakdownItem(BaseModel):
    hour_of_day: int = Field(..., description="Hour of day (0-23) in Europe/London")
    count: int = Field(..., description="Number of evaluations")
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    bias: Optional[float] = None
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class HorizonBreakdownItem(BaseModel):
    horizon_bucket: str = Field(..., description="Lead time bucket (e.g. 12-18h, 18-24h)")
    count: int = Field(..., description="Number of evaluations")
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    bias: Optional[float] = None
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class AccuracyResponse(BaseModel):
    start_date: str = Field(..., description="Start delivery date evaluated (YYYY-MM-DD)")
    end_date: str = Field(..., description="End delivery date evaluated (YYYY-MM-DD)")
    cutoff_time: str = Field(..., description="Cutoff time used for headline selection")
    headline_metrics: HeadlineAccuracyMetrics = Field(..., description="Headline metrics for cutoff-selected forecasts")
    by_hour_of_day: List[HourOfDayBreakdownItem] = Field(..., description="Error breakdown by local hour of day")
    by_horizon: List[HorizonBreakdownItem] = Field(
        ...,
        description="Error breakdown by lead time bucket across ALL published forecast runs (12-18h, 18-24h, 24-30h, 30-36h, 36-42h)"
    )


class ErrorBandSlot(BaseModel):
    startTime: str = Field(..., description="UTC ISO string of the hourly slot start")
    startTime_local: str = Field(..., description="Local Europe/London ISO string")
    forecast: float = Field(..., description="Selected forecast in MW")
    lower_bound: float = Field(..., description="Lower confidence band in MW (clamped to >= 0)")
    upper_bound: float = Field(..., description="Upper confidence band in MW (clamped to >= 0)")
    p10_error: float = Field(..., description="10th percentile of historical signed error (forecast - actual)")
    p90_error: float = Field(..., description="90th percentile of historical signed error (forecast - actual)")


class ErrorBandResponse(BaseModel):
    delivery_date: str = Field(..., description="Target delivery date (YYYY-MM-DD)")
    cutoff_time: str = Field(..., description="Decision cutoff time on D-1")
    history_days_used: int = Field(..., description="Number of complete historical delivery days used (strictly <= D-2)")
    history_start_date: Optional[str] = Field(None, description="Earliest historical delivery day used")
    history_end_date: Optional[str] = Field(None, description="Latest historical delivery day used (<= D-2)")
    band: Optional[List[ErrorBandSlot]] = Field(None, description="Hourly forecast with lower and upper error bands")
    reason: Optional[str] = Field(None, description="Reason if band is null (e.g. fewer than 3 history days)")
