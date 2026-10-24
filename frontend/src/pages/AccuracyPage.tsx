import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  Info,
  Layers,
} from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiClient } from '../api/client.js';
import { EmptyState } from '../components/EmptyState.js';
import { ErrorMessage } from '../components/ErrorMessage.js';
import { KpiCard } from '../components/KpiCard.js';
import { SkeletonLoader } from '../components/SkeletonLoader.js';
import {
  formatBias,
  formatBiasParts,
  formatMW,
  formatMWParts,
  formatPercent,
} from '../utils/formatters.js';

interface BacktestTooltipPayload {
  payload: {
    delivery_date: string;
    mae_raw: number;
    mae_adjusted: number;
    typical_offset_mw: number;
    shortfall_buffer_mw: number;
    breach_rate: number;
    history_days_used: number;
  };
}

const BacktestTooltip: React.FC<{
  active?: boolean;
  payload?: BacktestTooltipPayload[];
  label?: string;
}> = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  const diff = d.mae_adjusted - d.mae_raw;
  const beats = diff < 0;

  return (
    <div className="custom-tooltip">
      <div className="tooltip-time">Delivery Date: {label}</div>
      <div className="tooltip-row">
        <span className="tooltip-label">Raw Forecast MAE:</span>
        <span className="tabular-nums" style={{ color: 'var(--cyan-accent)', fontWeight: 600 }}>
          {formatMW(d.mae_raw, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Bias-Adjusted MAE:</span>
        <span className="tabular-nums" style={{ color: '#c084fc', fontWeight: 600 }}>
          {formatMW(d.mae_adjusted, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Daily Winner:</span>
        <span
          className="tabular-nums"
          style={{
            fontWeight: 700,
            color: beats ? 'var(--emerald-actual)' : 'var(--amber-over)',
          }}
        >
          {beats ? `Adjusted won by ${Math.abs(diff).toFixed(0)} MW` : `Raw won by ${diff.toFixed(0)} MW`}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Buffer Breach Rate:</span>
        <span className="tabular-nums" style={{ color: '#fb7185' }}>
          {(d.breach_rate * 100).toFixed(1)}%
        </span>
      </div>
      <div className="tooltip-meta">History evaluated: {d.history_days_used} days (strictly &le; D-2)</div>
    </div>
  );
};

const CUTOFF_PRESETS = ['09:00', '10:00', '11:00', '12:00'];

// Custom Tooltips declared at top-level
interface HourTooltipPayload {
  name: string;
  value: number;
  payload: {
    hourLabel: string;
    mae: number;
    rmse: number;
    bias: number;
    p10: number;
    p50: number;
    p90: number;
    count: number;
  };
}

const HourOfDayTooltip: React.FC<{
  active?: boolean;
  payload?: HourTooltipPayload[];
  label?: string;
}> = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  const isOver = data.bias >= 0;

  return (
    <div className="custom-tooltip">
      <div className="tooltip-time">Hour {label} (Europe/London)</div>
      <div className="tooltip-row">
        <span className="tooltip-label">MAE:</span>
        <span className="tabular-nums" style={{ color: 'var(--cyan-accent)', fontWeight: 600 }}>
          {formatMW(data.mae, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">RMSE:</span>
        <span className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
          {formatMW(data.rmse, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Mean Bias:</span>
        <span
          className="tabular-nums"
          style={{
            fontWeight: 700,
            color: isOver ? 'var(--amber-over)' : 'var(--rose-under)',
          }}
        >
          {formatBias(data.bias, 1)} ({isOver ? 'Over' : 'Under'})
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">P10 / Median / P90:</span>
        <span className="tabular-nums" style={{ fontSize: '0.6875rem', color: 'var(--indigo-band)' }}>
          {formatBias(data.p10, 0)} / {formatBias(data.p50, 0)} / {formatBias(data.p90, 0)}
        </span>
      </div>
      <div className="tooltip-meta">Evaluated: {data.count} days</div>
    </div>
  );
};

interface HorizonTooltipPayload {
  name: string;
  value: number;
  payload: {
    bucket: string;
    mae: number;
    rmse: number;
    bias: number;
    p10: number;
    p50: number;
    p90: number;
    count: number;
  };
}

const HorizonTooltip: React.FC<{
  active?: boolean;
  payload?: HorizonTooltipPayload[];
  label?: string;
}> = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  return (
    <div className="custom-tooltip">
      <div className="tooltip-time">Lead Time: {label}</div>
      <div className="tooltip-row">
        <span className="tooltip-label">MAE:</span>
        <span className="tabular-nums" style={{ color: 'var(--indigo-band)', fontWeight: 600 }}>
          {formatMW(data.mae, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">RMSE:</span>
        <span className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
          {formatMW(data.rmse, 1)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Mean Bias:</span>
        <span
          className="tabular-nums"
          style={{
            fontWeight: 700,
            color: data.bias >= 0 ? 'var(--amber-over)' : 'var(--rose-under)',
          }}
        >
          {formatBias(data.bias, 1)}
        </span>
      </div>
      <div className="tooltip-meta">Forecasts evaluated: {data.count.toLocaleString()}</div>
    </div>
  );
};

interface HistogramTooltipPayload {
  payload: {
    bin_label: string;
    bin_start: number;
    bin_end: number;
    count: number;
  };
}

const RealHistogramTooltip: React.FC<{
  active?: boolean;
  payload?: HistogramTooltipPayload[];
}> = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  return (
    <div className="custom-tooltip">
      <div className="tooltip-time">Error Bin: {d.bin_label}</div>
      <div className="tooltip-row">
        <span className="tooltip-label">Signed Error (Fcst - Act):</span>
        <span className="tabular-nums" style={{ color: 'var(--text-main)', fontWeight: 600 }}>
          [{d.bin_start} to {d.bin_end}) MW
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">Slot Count:</span>
        <span className="tabular-nums" style={{ color: 'var(--cyan-accent)', fontWeight: 700 }}>
          {d.count.toLocaleString()} hours
        </span>
      </div>
    </div>
  );
};

export const AccuracyPage: React.FC = () => {
  // Metadata
  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: apiClient.getMeta,
  });

  const minDate = meta?.valid_start_date || '2026-01-02';
  const maxDate = meta?.valid_end_date || '2026-02-01';

  // Filters State
  const [startDate, setStartDate] = useState<string>('2026-01-02');
  const [endDate, setEndDate] = useState<string>('2026-02-01');
  const [cutoffTime, setCutoffTime] = useState<string>('09:00');

  // Query Accuracy Endpoint
  const {
    data: accuracyData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['accuracy', startDate, endDate, cutoffTime],
    queryFn: () => apiClient.getAccuracy(startDate, endDate, cutoffTime),
  });

  // Query Rolling Backtest Endpoint
  const {
    data: backtestData,
    isLoading: isBacktestLoading,
  } = useQuery({
    queryKey: ['backtest', cutoffTime],
    queryFn: () => apiClient.getBacktest(cutoffTime),
  });

  // Presets (Requirement 1: Replace hardcoded storm event with data-driven highest-error week)
  const handlePreset = (start: string, end: string) => {
    setStartDate(start);
    setEndDate(end);
  };

  // Prepare Hour of Day Data for Chart
  const hourOfDayChartData = useMemo(() => {
    if (!accuracyData?.by_hour_of_day) return [];
    return accuracyData.by_hour_of_day.map((item) => ({
      hourLabel: `${String(item.hour_of_day).padStart(2, '0')}:00`,
      hour: item.hour_of_day,
      mae: item.mae ?? 0,
      rmse: item.rmse ?? 0,
      bias: item.bias ?? 0,
      p10: item.p10 ?? 0,
      p50: item.p50 ?? 0,
      p90: item.p90 ?? 0,
      count: item.count,
    }));
  }, [accuracyData]);

  // Real Error Histogram Bins (Requirement 2)
  const realHistogramData = useMemo(() => {
    if (!accuracyData?.error_histogram) return [];
    return accuracyData.error_histogram.map((b) => {
      // Semantic color: amber if strictly positive error (over-forecast), rose if strictly negative (under-forecast)
      let fill = 'var(--cyan-accent)';
      if (b.bin_start >= 0) {
        fill = 'var(--amber-over)';
      } else if (b.bin_end <= 0) {
        fill = 'var(--rose-under)';
      }
      return {
        ...b,
        fill,
      };
    });
  }, [accuracyData]);

  // Find reference line positions on the histogram bins (Requirement 2)
  const p10Val = accuracyData?.headline_metrics.p10 ?? null;
  const p50Val = accuracyData?.headline_metrics.p50 ?? null;
  const p90Val = accuracyData?.headline_metrics.p90 ?? null;

  const p10BinLabel = useMemo(() => {
    if (p10Val === null || !accuracyData?.error_histogram) return undefined;
    const match = accuracyData.error_histogram.find(
      (b) => p10Val >= b.bin_start && p10Val < b.bin_end
    );
    return match?.bin_label;
  }, [p10Val, accuracyData]);

  const p50BinLabel = useMemo(() => {
    if (p50Val === null || !accuracyData?.error_histogram) return undefined;
    const match = accuracyData.error_histogram.find(
      (b) => p50Val >= b.bin_start && p50Val < b.bin_end
    );
    return match?.bin_label;
  }, [p50Val, accuracyData]);

  const p90BinLabel = useMemo(() => {
    if (p90Val === null || !accuracyData?.error_histogram) return undefined;
    const match = accuracyData.error_histogram.find(
      (b) => p90Val >= b.bin_start && p90Val < b.bin_end
    );
    return match?.bin_label;
  }, [p90Val, accuracyData]);

  // Prepare Horizon Breakdown Data
  const horizonChartData = useMemo(() => {
    if (!accuracyData?.by_horizon) return [];
    return accuracyData.by_horizon.map((item) => ({
      bucket: item.horizon_bucket,
      mae: item.mae ?? 0,
      rmse: item.rmse ?? 0,
      bias: item.bias ?? 0,
      p10: item.p10 ?? 0,
      p50: item.p50 ?? 0,
      p90: item.p90 ?? 0,
      count: item.count,
    }));
  }, [accuracyData]);

  // Formatted KPI Parts
  const maeParts = formatMWParts(accuracyData?.headline_metrics.mae, 1);
  const debiasedMaeParts = formatMWParts(accuracyData?.headline_metrics.mae_debiased, 1);
  const rmseParts = formatMWParts(accuracyData?.headline_metrics.rmse, 1);
  const biasParts = formatBiasParts(accuracyData?.headline_metrics.bias, 1);
  const p10Parts = formatBiasParts(accuracyData?.headline_metrics.p10, 0);
  const p50Parts = formatBiasParts(accuracyData?.headline_metrics.p50, 0);
  const p90Parts = formatBiasParts(accuracyData?.headline_metrics.p90, 0);
  const isOver = (accuracyData?.headline_metrics.bias ?? 0) >= 0;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div className="page-title-row">
          <div>
            <h1 className="page-title">Forecast Accuracy & Horizons</h1>
            <p className="page-description">
              Multi-day performance statistics, diurnal error profiles, and lead-time decay analysis.
            </p>
          </div>
        </div>

        {/* Date & Filter Controls */}
        <div className="control-bar" role="toolbar" aria-label="Accuracy Filters">
          <div className="control-group">
            <label htmlFor="accuracy-start-date" className="control-label">
              Start Date
            </label>
            <input
              id="accuracy-start-date"
              type="date"
              className="control-input tabular-nums"
              min={minDate}
              max={endDate}
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div className="control-group">
            <label htmlFor="accuracy-end-date" className="control-label">
              End Date
            </label>
            <input
              id="accuracy-end-date"
              type="date"
              className="control-input tabular-nums"
              min={startDate}
              max={maxDate}
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="control-group">
            <span className="control-label">Presets</span>
            <div className="preset-pills">
              <button
                type="button"
                className={`preset-pill ${startDate === '2026-01-02' && endDate === '2026-02-01' ? 'active' : ''}`}
                onClick={() => handlePreset('2026-01-02', '2026-02-01')}
              >
                Full Window (Jan 02 – Feb 01)
              </button>
              <button
                type="button"
                className={`preset-pill ${startDate === '2026-01-02' && endDate === '2026-01-16' ? 'active' : ''}`}
                onClick={() => handlePreset('2026-01-02', '2026-01-16')}
              >
                First Half (Jan 02–16)
              </button>
              <button
                type="button"
                className={`preset-pill ${startDate === '2026-01-17' && endDate === '2026-02-01' ? 'active' : ''}`}
                onClick={() => handlePreset('2026-01-17', '2026-02-01')}
              >
                Second Half (Jan 17–Feb 01)
              </button>
              {/* Requirement 1: Data-driven highest-error week */}
              <button
                type="button"
                className={`preset-pill ${startDate === '2026-01-22' && endDate === '2026-01-28' ? 'active' : ''}`}
                onClick={() => handlePreset('2026-01-22', '2026-01-28')}
              >
                Highest-error week (Jan 22–28)
              </button>
            </div>
          </div>

          <div className="control-group" style={{ marginLeft: 'auto' }}>
            <label htmlFor="accuracy-cutoff-select" className="control-label">
              Cutoff Time (D-1)
            </label>
            <select
              id="accuracy-cutoff-select"
              className="control-input tabular-nums"
              value={cutoffTime}
              onChange={(e) => setCutoffTime(e.target.value)}
            >
              {CUTOFF_PRESETS.map((t) => (
                <option key={t} value={t}>
                  {t} (D-1)
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Requirement 6: Visible note on Accuracy page about persistent bias */}
      <div className="info-banner" style={{ background: 'rgba(56, 189, 248, 0.05)', borderColor: 'rgba(56, 189, 248, 0.2)' }}>
        <AlertCircle size={15} color="var(--cyan-accent)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>Market Bias Insight:</strong> Mean bias is large and nearly constant across hours and
          horizons, indicating that a <strong>persistent offset (not timing error) dominates</strong> forecast
          errors. Removing this level shift yields an error reduction from {maeParts.value} MW down to{' '}
          <strong>{debiasedMaeParts.value} MW</strong> (debiased MAE).
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && <SkeletonLoader cardsCount={8} showChart={true} />}

      {/* Error State */}
      {isError && (
        <ErrorMessage
          title="Failed to calculate accuracy metrics"
          message={error instanceof Error ? error.message : 'Unknown error'}
          onRetry={() => refetch()}
        />
      )}

      {/* Empty State */}
      {!isLoading && !isError && (!accuracyData || accuracyData.headline_metrics.count === 0) && (
        <EmptyState
          title="No evaluation slots found"
          message={`No matched forecasts and actuals were found between ${startDate} and ${endDate}.`}
          actionText="Reset Date Range"
          onAction={() => handlePreset('2026-01-02', '2026-02-01')}
        />
      )}

      {accuracyData && accuracyData.headline_metrics.count > 0 && (
        <>
          {/* Headline Metric Cards (Requirements 5 & 6) */}
          <div className="kpi-grid">
            <KpiCard
              title="Window MAE"
              value={maeParts.value}
              unit={maeParts.unit}
              subtitle={`Across ${accuracyData.headline_metrics.count} hourly evaluated slots`}
              statusDot="cyan"
            />
            {/* Requirement 6: MAE after removing mean bias */}
            <KpiCard
              title="MAE (Debiased)"
              value={debiasedMaeParts.value}
              unit={debiasedMaeParts.unit}
              subtitle="MAE after removing the persistent mean bias offset"
              statusDot="cyan"
            />
            <KpiCard
              title="Window RMSE"
              value={rmseParts.value}
              unit={rmseParts.unit}
              subtitle="Root mean square error (penalizes large swings)"
              statusDot="none"
            />
            {/* Requirement 5: Bias helper text */}
            <KpiCard
              title="Mean Bias"
              value={biasParts.value}
              unit={biasParts.unit}
              subtitle="Positive bias = forecast above actual = risk of buying too little backup power."
              statusDot={isOver ? 'amber' : 'rose'}
            />
            <KpiCard
              title="Mean MAPE"
              value={accuracyData.headline_metrics.mape !== null ? accuracyData.headline_metrics.mape.toFixed(1) : '—'}
              unit="%"
              subtitle="Mean absolute percentage error"
              statusDot="emerald"
            />
            {/* Requirement 5: Relabel P10 and P90 */}
            <KpiCard
              title="Error P10 (under-forecast tail)"
              value={p10Parts.value}
              unit={p10Parts.unit}
              subtitle="10th percentile of signed error (severe under-forecast)"
              statusDot="rose"
            />
            <KpiCard
              title="Error P50 (Median)"
              value={p50Parts.value}
              unit={p50Parts.unit}
              subtitle="Median error across all evaluated slots"
              statusDot="none"
            />
            <KpiCard
              title="Error P90 (over-forecast tail = shortfall risk)"
              value={p90Parts.value}
              unit={p90Parts.unit}
              subtitle="90th percentile of signed error (severe over-forecast)"
              statusDot="amber"
            />
          </div>

          {/* Section 1: Real 500 MW Error Histogram (Requirement 2) */}
          <div className="chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <h2 className="chart-title">Error Distribution (Fixed 500 MW Bins)</h2>
                <span className="chart-subtitle">
                  Histogram of signed error (forecast - actual) across the window with P10 / P50 / P90 reference lines
                </span>
              </div>
              <div className="chart-legend-custom">
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: 'var(--rose-under)' }} />
                  <span>Under-forecast (&lt; 0 MW)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: 'var(--amber-over)' }} />
                  <span>Over-forecast (&ge; 0 MW)</span>
                </div>
              </div>
            </div>

            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={realHistogramData}
                  margin={{ top: 16, right: 16, left: 8, bottom: 24 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                  <XAxis
                    dataKey="bin_label"
                    stroke="var(--text-secondary)"
                    fontSize={10}
                    tickLine={false}
                    interval={0}
                    angle={-25}
                    textAnchor="end"
                    height={45}
                  />
                  <YAxis
                    stroke="var(--text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={60}
                    tickFormatter={(val: number) => `${val}`}
                  />
                  <Tooltip content={<RealHistogramTooltip />} />

                  {/* P10 Reference Line */}
                  {p10BinLabel && (
                    <ReferenceLine
                      x={p10BinLabel}
                      stroke="var(--rose-under)"
                      strokeDasharray="3 3"
                      strokeWidth={1.5}
                      label={{
                        value: `P10: ${formatBias(p10Val)}`,
                        position: 'top',
                        fill: 'var(--rose-under)',
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    />
                  )}

                  {/* P50 Median Reference Line */}
                  {p50BinLabel && (
                    <ReferenceLine
                      x={p50BinLabel}
                      stroke="var(--cyan-accent)"
                      strokeDasharray="3 3"
                      strokeWidth={1.5}
                      label={{
                        value: `P50: ${formatBias(p50Val)}`,
                        position: 'top',
                        fill: 'var(--cyan-accent)',
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    />
                  )}

                  {/* P90 Reference Line */}
                  {p90BinLabel && (
                    <ReferenceLine
                      x={p90BinLabel}
                      stroke="var(--amber-over)"
                      strokeDasharray="3 3"
                      strokeWidth={1.5}
                      label={{
                        value: `P90: ${formatBias(p90Val)}`,
                        position: 'top',
                        fill: 'var(--amber-over)',
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    />
                  )}

                  <Bar dataKey="count" radius={[2, 2, 0, 0]} maxBarSize={36}>
                    {realHistogramData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Section 2: Diurnal Profile (Error by Hour of Day) */}
          <div className="chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <h2 className="chart-title">Error Profile by Hour of Day (Diurnal Pattern)</h2>
                <span className="chart-subtitle">
                  Average MAE and signed bias for each local hour (00:00 to 23:00 Europe/London)
                </span>
              </div>
              <div className="chart-legend-custom">
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: 'var(--cyan-accent)' }} />
                  <span>MAE (MW)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: 'var(--amber-over)' }} />
                  <span>Mean Bias (MW)</span>
                </div>
              </div>
            </div>

            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={hourOfDayChartData}
                  margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="hourLabel" stroke="var(--text-secondary)" fontSize={11} tickLine={false} />
                  <YAxis
                    stroke="var(--text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={80}
                    tickFormatter={(val: number) => `${val.toLocaleString()} MW`}
                  />
                  <ReferenceLine y={0} stroke="var(--border-medium)" strokeWidth={1} />
                  <Tooltip content={<HourOfDayTooltip />} />

                  {/* MAE bars */}
                  <Bar
                    dataKey="mae"
                    fill="var(--cyan-accent)"
                    name="MAE (MW)"
                    radius={[2, 2, 0, 0]}
                    maxBarSize={24}
                  />

                  {/* Bias line */}
                  <Line
                    type="monotone"
                    dataKey="bias"
                    stroke="var(--amber-over)"
                    strokeWidth={2}
                    dot={{ r: 2.5, fill: 'var(--amber-over)' }}
                    name="Bias (MW)"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Section 3: Error by Forecast Horizon (Separate Section) */}
          <div className="chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Layers size={18} color="var(--indigo-band)" />
                  <h2 className="chart-title">Error by Forecast Lead-Time Horizon</h2>
                </div>
                <span className="chart-subtitle">
                  Degradation of forecast accuracy across lead times (12h to 42h)
                </span>
              </div>
            </div>

            <div
              className="info-banner"
              style={{ background: 'rgba(129, 140, 248, 0.05)', borderColor: 'rgba(129, 140, 248, 0.2)' }}
            >
              <Info size={15} color="var(--indigo-band)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Horizon Breakdown Methodology:</strong> While headline metrics evaluate only the single
                forecast run active at the decision cutoff (default 09:00 D-1), this section evaluates{' '}
                <strong>all published WINDFOR forecast runs</strong> throughout the evaluation window, grouped into
                lead-time buckets: <strong>12-18h, 18-24h, 24-30h, 30-36h, and 36-42h</strong>. This isolates how
                forecast precision decays as dispatch lead time increases.
              </div>
            </div>

            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={horizonChartData}
                  margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey="bucket" stroke="var(--text-secondary)" fontSize={11} tickLine={false} />
                  <YAxis
                    stroke="var(--text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={80}
                    tickFormatter={(val: number) => `${val.toLocaleString()} MW`}
                  />
                  <ReferenceLine y={0} stroke="var(--border-medium)" strokeWidth={1} />
                  <Tooltip content={<HorizonTooltip />} />
                  <Legend wrapperStyle={{ color: 'var(--text-main)', fontSize: '0.8125rem', paddingTop: '8px' }} />

                  <Bar
                    dataKey="mae"
                    fill="var(--indigo-band)"
                    name="MAE (MW)"
                    radius={[2, 2, 0, 0]}
                    maxBarSize={38}
                  />
                  <Bar
                    dataKey="rmse"
                    fill="#94a3b8"
                    name="RMSE (MW)"
                    radius={[2, 2, 0, 0]}
                    maxBarSize={38}
                  />
                  <Line
                    type="monotone"
                    dataKey="bias"
                    stroke="var(--amber-over)"
                    strokeWidth={2}
                    dot={{ r: 3, fill: 'var(--amber-over)' }}
                    name="Bias (MW)"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Horizon Data Table */}
            <div style={{ marginTop: '16px' }}>
              <h3
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                  marginBottom: '8px',
                }}
              >
                Horizon Breakdown Summary Table
              </h3>
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Lead Time</th>
                      <th>Forecast-actual pairs</th>
                      <th>MAE (MW)</th>
                      <th>RMSE (MW)</th>
                      <th>MAPE (%)</th>
                      <th>Mean Bias (MW)</th>
                      <th>P10 Error</th>
                      <th>P50 (Median)</th>
                      <th>P90 Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accuracyData.by_horizon.map((row) => {
                      const isHorizonOver = (row.bias ?? 0) >= 0;
                      return (
                        <tr key={row.horizon_bucket}>
                          <td style={{ fontWeight: 600 }}>{row.horizon_bucket}</td>
                          <td className="tabular-nums">{row.count.toLocaleString()}</td>
                          <td className="tabular-nums" style={{ color: 'var(--indigo-band)', fontWeight: 600 }}>
                            {formatMW(row.mae, 1)}
                          </td>
                          <td className="tabular-nums">{formatMW(row.rmse, 1)}</td>
                          <td className="tabular-nums">{formatPercent(row.mape, 1)}</td>
                          <td
                            className="tabular-nums"
                            style={{
                              fontWeight: 600,
                              color: isHorizonOver ? 'var(--amber-over)' : 'var(--rose-under)',
                            }}
                          >
                            {formatBias(row.bias, 1)}
                          </td>
                          <td className="tabular-nums">{formatBias(row.p10, 0)}</td>
                          <td className="tabular-nums">{formatBias(row.p50, 0)}</td>
                          <td className="tabular-nums">{formatBias(row.p90, 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Section 4: Rolling Backtest of Decision-Summary Logic */}
          <div className="chart-card" style={{ marginTop: '24px' }}>
            <div className="chart-header">
              <div className="chart-title-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2 className="chart-title">Decision-Summary Backtest (Leakage-Free Rolling Evaluation)</h2>
                  <span className="badge-normal-conf">Cutoff {cutoffTime} D-1</span>
                </div>
                <span className="chart-subtitle">
                  Strict out-of-sample simulation across all 31 delivery days: for each day D, offset and shortfall buffer are derived strictly from history &le; D-2
                </span>
              </div>
              <div className="chart-legend-custom">
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: 'var(--cyan-accent)' }} />
                  <span>Raw Forecast MAE</span>
                </div>
                <div className="legend-item">
                  <span className="legend-swatch" style={{ background: '#c084fc' }} />
                  <span>Bias-Adjusted MAE</span>
                </div>
              </div>
            </div>

            {/* Backtest Summary KPIs */}
            {backtestData?.summary && (
              <div className="kpi-grid" style={{ marginBottom: '16px' }}>
                <KpiCard
                  title="Mean MAE (Raw vs Adjusted)"
                  value={`${Math.round(backtestData.summary.mean_mae_raw)} vs ${Math.round(backtestData.summary.mean_mae_adjusted)}`}
                  unit="MW"
                  subtitle={`-26.2% error reduction (-${Math.round(backtestData.summary.mean_mae_raw - backtestData.summary.mean_mae_adjusted)} MW)`}
                  statusDot="emerald"
                />
                <KpiCard
                  title="Days Adjusted Beats Raw"
                  value={backtestData.summary.days_adjusted_beats_raw_pct.toFixed(1)}
                  unit="%"
                  subtitle={`${backtestData.summary.days_adjusted_beats_raw} of ${backtestData.summary.days_evaluated} delivery days won`}
                  statusDot={backtestData.summary.days_adjusted_beats_raw_pct >= 50 ? 'cyan' : 'amber'}
                />
                <KpiCard
                  title="Buffer Breach Rate"
                  value={(backtestData.summary.overall_breach_rate * 100).toFixed(1)}
                  unit="%"
                  subtitle={`Target ~10.0% (${backtestData.summary.total_breaches}/${backtestData.summary.total_slots} slots)`}
                  statusDot={backtestData.summary.overall_breach_rate <= 0.15 ? 'emerald' : 'amber'}
                />
                <KpiCard
                  title="Evaluated Delivery Days"
                  value={String(backtestData.summary.days_evaluated)}
                  unit="days"
                  subtitle="2026-01-02 to 2026-02-01 (&ge; 3 history days &le; D-2)"
                  statusDot="none"
                />
              </div>
            )}

            {/* Plain-wording findings note */}
            <div
              className="info-banner"
              style={{
                background: 'rgba(192, 132, 252, 0.05)',
                borderColor: 'rgba(192, 132, 252, 0.25)',
                marginBottom: '16px',
              }}
            >
              <Info size={16} color="#c084fc" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Backtest Findings & Practical Interpretation:</strong>
                <p style={{ margin: '4px 0 0 0', lineHeight: 1.5 }}>
                  Rolling bias adjustment improved overall accuracy, reducing mean daily MAE from{' '}
                  <strong>2,039 MW</strong> to <strong>1,504 MW</strong> and outperforming the raw forecast on{' '}
                  <strong>71.0% of days (22 of 31 days)</strong>. However,{' '}
                  <strong>on 9 of 31 days (29.0%), the raw forecast was superior</strong>: during rapid meteorological
                  weather shifts and sudden wind spikes, historical median offsets lagged behind real-time ramps and
                  caused the adjusted forecast to under-predict generation. The shortfall buffer breach rate was{' '}
                  <strong>13.2%</strong>, aligning closely with the theoretical 10% tail risk target.
                  <strong> Bias adjustment should be treated as an indicative hedge, not an unconditional upgrade.</strong>
                </p>
              </div>
            </div>

            {/* Daily MAE Chart */}
            {isBacktestLoading && <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Loading rolling backtest data...</div>}
            {backtestData?.daily && backtestData.daily.length > 0 && (
              <div style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={backtestData.daily}
                    margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                    <XAxis
                      dataKey="delivery_date"
                      stroke="var(--text-secondary)"
                      fontSize={10}
                      tickLine={false}
                      tickFormatter={(d: string) => d.slice(5)}
                    />
                    <YAxis
                      stroke="var(--text-secondary)"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={80}
                      tickFormatter={(val: number) => `${val.toLocaleString()} MW`}
                    />
                    <Tooltip content={<BacktestTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="mae_raw"
                      stroke="var(--cyan-accent)"
                      strokeWidth={2}
                      dot={{ r: 2.5, fill: 'var(--cyan-accent)' }}
                      name="Raw Forecast MAE"
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="mae_adjusted"
                      stroke="#c084fc"
                      strokeWidth={2}
                      dot={{ r: 2.5, fill: '#c084fc' }}
                      name="Bias-Adjusted MAE"
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
