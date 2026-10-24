/**
 * TypeScript type definitions mirroring backend FastAPI Pydantic schemas.
 */

export interface HealthResponse {
  status: string;
  version: string;
  data_loaded: boolean;
}

export interface MetaResponse {
  valid_start_date: string;
  valid_end_date: string;
  total_delivery_days: number;
  default_cutoff_time: string;
  timezone: string;
  actuals_resolution: string;
  forecast_resolution: string;
  alignment_rule: string;
  bias_convention: string;
}

export interface HourlyForecastSlot {
  startTime: string; // UTC ISO string
  startTime_local: string; // Europe/London ISO string
  forecast: number | null; // Forecast in MW
  actual: number | null; // Hourly aggregated actual in MW
  error: number | null; // forecast - actual in MW
  publishTime: string | null;
  horizon_hours: number | null;
}

export interface RawActual30Min {
  startTime: string; // UTC ISO string
  startTime_local: string;
  generation: number; // Raw 30-min settlement actual in MW
}

export interface DailySummaryMetrics {
  count: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  bias: number | null; // Positive = over-forecast, Negative = under-forecast
  mae_debiased?: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface ForecastResponse {
  delivery_date: string;
  cutoff_time: string;
  decision_time_utc: string;
  hourly: HourlyForecastSlot[];
  raw_actuals_30min: RawActual30Min[];
  summary_metrics: DailySummaryMetrics;
}

export interface HeadlineAccuracyMetrics {
  count: number;
  mae: number | null;
  mae_debiased: number | null;
  rmse: number | null;
  mape: number | null;
  bias: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface ErrorHistogramBin {
  bin_start: number;
  bin_end: number;
  bin_label: string;
  count: number;
}

export interface HourOfDayBreakdownItem {
  hour_of_day: number; // 0..23 in Europe/London
  count: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  bias: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface HorizonBreakdownItem {
  horizon_bucket: string; // e.g. "12-18h", "18-24h", "24-30h", "30-36h", "36-42h"
  count: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  bias: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface AccuracyResponse {
  start_date: string;
  end_date: string;
  cutoff_time: string;
  headline_metrics: HeadlineAccuracyMetrics;
  by_hour_of_day: HourOfDayBreakdownItem[];
  by_horizon: HorizonBreakdownItem[];
  error_histogram: ErrorHistogramBin[];
}

export interface ErrorBandSlot {
  startTime: string;
  startTime_local: string;
  forecast: number;
  lower_bound: number; // Clamped to >= 0
  upper_bound: number; // Clamped to >= 0
  p10_error: number;
  p90_error: number;
}

export interface ErrorBandResponse {
  delivery_date: string;
  cutoff_time: string;
  history_days_used: number;
  history_start_date: string | null;
  history_end_date: string | null;
  band: ErrorBandSlot[] | null;
  reason: string | null;
}

export interface DecisionSummaryResponse {
  delivery_date: string;
  cutoff_time: string;
  expected_wind_mwh: number;
  shortfall_buffer_mw: number | null;
  shortfall_buffer_relative_to_adjusted_mw: number | null;
  typical_offset_mw: number | null;
  bias_adjusted_expected_wind_mwh: number | null;
  risk_hours: number[];
  low_confidence: boolean;
  history_days_used: number;
  history_start_date: string | null;
  history_end_date: string | null;
  recommendation: string;
  assumption: string;
  reason: string | null;
}

export interface BacktestDailyItem {
  delivery_date: string;
  history_days_used: number;
  typical_offset_mw: number;
  shortfall_buffer_mw: number;
  mae_raw: number;
  mae_adjusted: number;
  adjusted_beats_raw: boolean;
  breach_count: number;
  slot_count: number;
  breach_rate: number;
}

export interface BacktestSummary {
  days_evaluated: number;
  mean_mae_raw: number;
  mean_mae_adjusted: number;
  days_adjusted_beats_raw: number;
  days_adjusted_beats_raw_pct: number;
  total_breaches: number;
  total_slots: number;
  overall_breach_rate: number;
}

export interface BacktestResponse {
  cutoff_time: string;
  summary: BacktestSummary;
  daily: BacktestDailyItem[];
}


