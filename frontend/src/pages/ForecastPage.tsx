import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Info,
  ShieldAlert,
} from 'lucide-react';
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiClient } from '../api/client.js';
import type { ErrorBandSlot } from '../types/api.js';
import { EmptyState } from '../components/EmptyState.js';
import { ErrorMessage } from '../components/ErrorMessage.js';
import { KpiCard } from '../components/KpiCard.js';
import { SkeletonLoader } from '../components/SkeletonLoader.js';
import {
  formatBias,
  formatBiasParts,
  formatDateLabel,
  formatHorizon,
  formatLondonTime,
  formatMW,
  formatMWParts,
  formatNumber,
} from '../utils/formatters.js';

const CUTOFF_PRESETS = ['09:00', '10:00', '11:00', '12:00'];

interface TooltipPayloadItem {
  name: string;
  value: number | [number, number] | null;
  color: string;
  payload: {
    time: string;
    isoTime: string;
    actual30m: number;
    actualHourly: number | null;
    forecast: number | null;
    error: number | null;
    publishTime: string | null;
    horizonHours: number | null;
    lowerBound: number | null;
    upperBound: number | null;
  };
}

const CustomChartTooltip: React.FC<{
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
  showErrorBand?: boolean;
}> = ({ active, payload, label, showErrorBand = true }) => {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  const isOver = (data.error ?? 0) > 0;

  return (
    <div className="custom-tooltip">
      <div className="tooltip-time">Slot: {label} Europe/London</div>
      <div className="tooltip-row">
        <span className="tooltip-label">
          <span className="tooltip-dot" style={{ backgroundColor: 'var(--cyan-accent)' }} />
          Day-Ahead Forecast:
        </span>
        <span className="tabular-nums" style={{ fontWeight: 600, color: 'var(--cyan-accent)' }}>
          {formatMW(data.forecast)}
        </span>
      </div>
      <div className="tooltip-row">
        <span className="tooltip-label">
          <span className="tooltip-dot" style={{ backgroundColor: 'var(--emerald-actual)' }} />
          Outturn (30-min):
        </span>
        <span className="tabular-nums" style={{ fontWeight: 600, color: 'var(--emerald-actual)' }}>
          {formatMW(data.actual30m)}
        </span>
      </div>
      {data.actualHourly !== null && (
        <div className="tooltip-row">
          <span className="tooltip-label" style={{ fontSize: '0.6875rem', paddingLeft: '12px' }}>
            Hourly Aggregated:
          </span>
          <span className="tabular-nums" style={{ fontSize: '0.6875rem', color: 'var(--text-secondary)' }}>
            {formatMW(data.actualHourly)}
          </span>
        </div>
      )}
      {data.error !== null && (
        <div
          className="tooltip-row"
          style={{
            marginTop: '4px',
            paddingTop: '4px',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          <span className="tooltip-label">Signed Error:</span>
          <span
            className="tabular-nums"
            style={{
              fontWeight: 600,
              color: isOver ? 'var(--amber-over)' : 'var(--rose-under)',
            }}
          >
            {formatBias(data.error)} ({isOver ? 'Over' : 'Under'})
          </span>
        </div>
      )}
      {showErrorBand && data.lowerBound !== null && data.upperBound !== null && (
        <div className="tooltip-row" style={{ marginTop: '3px' }}>
          <span className="tooltip-label">
            <span className="tooltip-dot" style={{ backgroundColor: 'var(--indigo-band)' }} />
            80% Error Band:
          </span>
          <span className="tabular-nums" style={{ fontSize: '0.6875rem', color: 'var(--indigo-band)' }}>
            [{formatMW(data.lowerBound)} – {formatMW(data.upperBound)}]
          </span>
        </div>
      )}
      <div className="tooltip-meta">
        <div>Run: {formatLondonTime(data.publishTime, 'datetime')}</div>
        <div>Lead time: {formatHorizon(data.horizonHours)}</div>
      </div>
    </div>
  );
};

export const ForecastPage: React.FC = () => {
  // Metadata for delivery bounds
  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: apiClient.getMeta,
  });

  const minDate = meta?.valid_start_date || '2026-01-02';
  const maxDate = meta?.valid_end_date || '2026-02-01';

  // Selected State
  const [selectedDate, setSelectedDate] = useState<string>('2026-01-05');
  const [cutoffTime, setCutoffTime] = useState<string>('09:00');
  const [showErrorBand, setShowErrorBand] = useState<boolean>(true);
  const [showTable, setShowTable] = useState<boolean>(false);

  // Queries
  const {
    data: forecastData,
    isLoading: isForecastLoading,
    isError: isForecastError,
    error: forecastError,
    refetch: refetchForecast,
  } = useQuery({
    queryKey: ['forecast', selectedDate, cutoffTime],
    queryFn: () => apiClient.getForecast(selectedDate, cutoffTime),
  });

  const { data: errorBandData, isLoading: isBandLoading } = useQuery({
    queryKey: ['error-band', selectedDate, cutoffTime],
    queryFn: () => apiClient.getErrorBand(selectedDate, cutoffTime),
    enabled: showErrorBand,
  });

  // Date Navigation handlers
  const handlePrevDay = () => {
    const cur = new Date(`${selectedDate}T00:00:00Z`);
    cur.setUTCDate(cur.getUTCDate() - 1);
    const prevStr = cur.toISOString().split('T')[0];
    if (prevStr >= minDate) {
      setSelectedDate(prevStr);
    }
  };

  const handleNextDay = () => {
    const cur = new Date(`${selectedDate}T00:00:00Z`);
    cur.setUTCDate(cur.getUTCDate() + 1);
    const nextStr = cur.toISOString().split('T')[0];
    if (nextStr <= maxDate) {
      setSelectedDate(nextStr);
    }
  };

  // Peak Absolute Error Calculation
  const peakErrorMetric = useMemo(() => {
    if (!forecastData?.hourly || forecastData.hourly.length === 0) return null;
    let maxErr = -1;
    let maxHour = -1;
    forecastData.hourly.forEach((slot, idx) => {
      if (slot.error !== null && slot.error !== undefined) {
        const absErr = Math.abs(slot.error);
        if (absErr > maxErr) {
          maxErr = absErr;
          maxHour = idx;
        }
      }
    });
    return {
      peakMW: maxErr >= 0 ? maxErr : null,
      hour: maxHour >= 0 ? `${String(maxHour).padStart(2, '0')}:00` : '',
    };
  }, [forecastData]);

  // Combine 30-min actuals, hourly forecasts, and error bands for the unified chart
  const chartData = useMemo(() => {
    if (!forecastData) return [];

    // Map hourly forecast by HH:00 timestamp
    const hourlyMap = new Map<string, (typeof forecastData.hourly)[0]>();
    forecastData.hourly.forEach((slot) => {
      const timeKey = formatLondonTime(slot.startTime, 'time');
      hourlyMap.set(timeKey, slot);
    });

    // Map error band by HH:00 timestamp
    const bandMap = new Map<string, ErrorBandSlot>();
    if (errorBandData?.band) {
      errorBandData.band.forEach((slot) => {
        const timeKey = formatLondonTime(slot.startTime, 'time');
        bandMap.set(timeKey, slot);
      });
    }

    // Iterate through all 30-minute settlement periods
    return forecastData.raw_actuals_30min.map((actual30) => {
      const timeLabel = formatLondonTime(actual30.startTime, 'time');
      const hourPrefix = timeLabel.split(':')[0] + ':00';
      const hourlySlot = hourlyMap.get(hourPrefix);
      const bandSlot = bandMap.get(hourPrefix);

      const forecastVal = hourlySlot?.forecast ?? null;
      const lowerVal = bandSlot ? bandSlot.lower_bound : null;
      const upperVal = bandSlot ? bandSlot.upper_bound : null;

      return {
        time: timeLabel,
        isoTime: actual30.startTime,
        actual30m: actual30.generation,
        actualHourly: hourlySlot?.actual ?? null,
        forecast: forecastVal,
        error: hourlySlot?.error ?? null,
        publishTime: hourlySlot?.publishTime ?? null,
        horizonHours: hourlySlot?.horizon_hours ?? null,
        lowerBound: lowerVal,
        upperBound: upperVal,
        bandRange: lowerVal !== null && upperVal !== null ? [lowerVal, upperVal] : null,
      };
    });
  }, [forecastData, errorBandData]);

  // Formatted KPI parts with small muted units
  const maeParts = formatMWParts(forecastData?.summary_metrics.mae, 1);
  const biasParts = formatBiasParts(forecastData?.summary_metrics.bias, 1);
  const peakErrParts = formatMWParts(peakErrorMetric?.peakMW, 1);
  const isOver = (forecastData?.summary_metrics.bias ?? 0) >= 0;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div className="page-title-row">
          <div>
            <h1 className="page-title">Day-Ahead Forecast & Outturn</h1>
            <p className="page-description">
              Compare D-1 cutoff-selected hourly wind forecasts against settlement actuals with
              leakage-free error bands.
            </p>
          </div>
        </div>

        {/* Control Bar */}
        <div className="control-bar" role="toolbar" aria-label="Forecast Controls">
          {/* Date Picker */}
          <div className="control-group">
            <label htmlFor="delivery-date-input" className="control-label">
              Delivery Date
            </label>
            <div className="control-input-wrapper">
              <button
                type="button"
                className="btn-icon"
                onClick={handlePrevDay}
                disabled={selectedDate <= minDate}
                aria-label="Previous day"
                title="Previous Day"
              >
                <ChevronLeft size={14} />
              </button>
              <input
                id="delivery-date-input"
                type="date"
                className="control-input tabular-nums"
                min={minDate}
                max={maxDate}
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
              <button
                type="button"
                className="btn-icon"
                onClick={handleNextDay}
                disabled={selectedDate >= maxDate}
                aria-label="Next day"
                title="Next Day"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>

          {/* Quick Presets */}
          <div className="control-group">
            <span className="control-label">Quick Dates</span>
            <div className="preset-pills">
              <button
                type="button"
                className={`preset-pill ${selectedDate === '2026-01-02' ? 'active' : ''}`}
                onClick={() => setSelectedDate('2026-01-02')}
              >
                Jan 02 (Start)
              </button>
              <button
                type="button"
                className={`preset-pill ${selectedDate === '2026-01-10' ? 'active' : ''}`}
                onClick={() => setSelectedDate('2026-01-10')}
              >
                Jan 10 (Sample)
              </button>
              <button
                type="button"
                className={`preset-pill ${selectedDate === '2026-01-20' ? 'active' : ''}`}
                onClick={() => setSelectedDate('2026-01-20')}
              >
                Jan 20 (Mid)
              </button>
              <button
                type="button"
                className={`preset-pill ${selectedDate === '2026-02-01' ? 'active' : ''}`}
                onClick={() => setSelectedDate('2026-02-01')}
              >
                Feb 01 (End)
              </button>
            </div>
          </div>

          {/* Cutoff Time Control */}
          <div className="control-group">
            <label htmlFor="cutoff-time-select" className="control-label">
              D-1 Cutoff Time
            </label>
            <div className="control-input-wrapper">
              <select
                id="cutoff-time-select"
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

          {/* Error Band Toggle */}
          <div className="control-group" style={{ marginLeft: 'auto' }}>
            <span className="control-label">Historical Error Band</span>
            <label className="toggle-label">
              <input
                type="checkbox"
                className="toggle-checkbox"
                checked={showErrorBand}
                onChange={(e) => setShowErrorBand(e.target.checked)}
              />
              <span>P10–P90 Band</span>
            </label>
          </div>
        </div>
      </div>

      {/* Error Band Status Banner (Plain text "up to D-2" per Requirement 3) */}
      {showErrorBand && (
        <>
          {isBandLoading ? (
            <div className="info-banner purple">
              <Clock size={14} />
              <span>Loading historical error band statistics...</span>
            </div>
          ) : errorBandData?.band ? (
            <div className="info-banner purple">
              <Info size={14} />
              <div>
                <strong>Historical 80% Confidence Band Active:</strong> Derived from{' '}
                <strong>{errorBandData.history_days_used} complete delivery days</strong> (
                {errorBandData.history_start_date} to {errorBandData.history_end_date}). Strictly
                uses historical error percentiles up to D-2 to avoid information leakage.
              </div>
            </div>
          ) : (
            <div className="info-banner warning">
              <ShieldAlert size={14} />
              <div>
                <strong>Error Band Unavailable:</strong>{' '}
                {errorBandData?.reason ||
                  'Requires at least 3 historical delivery days before decision day D-1.'}
              </div>
            </div>
          )}
        </>
      )}

      {/* Loading Skeleton */}
      {isForecastLoading && <SkeletonLoader cardsCount={4} showChart={true} />}

      {/* Error Message */}
      {isForecastError && (
        <ErrorMessage
          title="Could not load forecast"
          message={forecastError instanceof Error ? forecastError.message : 'Unknown error'}
          onRetry={() => refetchForecast()}
        />
      )}

      {/* Empty State */}
      {!isForecastLoading && !isForecastError && (!forecastData || forecastData.hourly.length === 0) && (
        <EmptyState
          title="No forecast data available"
          message={`No forecasts were returned for delivery date ${selectedDate} with cutoff ${cutoffTime}.`}
          actionText="Reset to Jan 02"
          onAction={() => setSelectedDate('2026-01-02')}
        />
      )}

      {/* Main Content Area */}
      {forecastData && forecastData.hourly.length > 0 && (
        <>
          {/* KPI Cards: solid flat cards, 1px subtle border, 8px radius, small caps label, status dot */}
          <div className="kpi-grid">
            <KpiCard
              title="Daily MAE"
              value={maeParts.value}
              unit={maeParts.unit}
              subtitle="Mean absolute error across 24 hourly slots"
              statusDot="cyan"
            />
            <KpiCard
              title="Mean Bias"
              value={biasParts.value}
              unit={biasParts.unit}
              subtitle="Positive bias = forecast above actual = risk of buying too little backup power."
              statusDot={isOver ? 'amber' : 'rose'}
            />
            <KpiCard
              title="Peak Absolute Error"
              value={peakErrParts.value}
              unit={peakErrParts.unit}
              subtitle={
                peakErrorMetric?.hour
                  ? `Max single-slot error recorded at ${peakErrorMetric.hour}`
                  : 'Across 24h slots'
              }
              statusDot="amber"
            />
            <KpiCard
              title="Mean MAPE"
              value={formatNumber(forecastData.summary_metrics.mape, 1)}
              unit="%"
              subtitle={`Daily RMSE: ${formatMW(forecastData.summary_metrics.rmse, 1)}`}
              statusDot="emerald"
            />
          </div>

          {/* Interactive Chart */}
          <div className="chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <h2 className="chart-title">Generation Profile: {formatDateLabel(selectedDate)}</h2>
                <span className="chart-subtitle">
                  Raw 30-min settlement actuals vs. D-1 {cutoffTime} hourly step-forecast
                </span>
              </div>
              <div className="chart-legend-custom">
                <div className="legend-item">
                  <span className="legend-swatch actual" />
                  <span>Actual (30-min FUELHH)</span>
                </div>
                <div className="legend-item">
                  <span className="legend-swatch forecast" />
                  <span>Forecast Step (Hourly WINDFOR)</span>
                </div>
                {showErrorBand && errorBandData?.band && (
                  <div className="legend-item">
                    <span className="legend-swatch band" />
                    <span>80% Error Band (P10–P90)</span>
                  </div>
                )}
              </div>
            </div>

            <div style={{ width: '100%', height: 400 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{ top: 8, right: 16, left: 8, bottom: 16 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--chart-grid)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="time"
                    stroke="var(--text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    interval={3}
                  />
                  <YAxis
                    stroke="var(--text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={80}
                    tickFormatter={(val: number) => `${val.toLocaleString()} MW`}
                    domain={[0, 'auto']}
                  />
                  <Tooltip
                    content={<CustomChartTooltip showErrorBand={showErrorBand} />}
                  />

                  {/* Shaded Area between lower and upper error bounds */}
                  {showErrorBand && errorBandData?.band && (
                    <Area
                      type="stepAfter"
                      dataKey="bandRange"
                      stroke="var(--indigo-band)"
                      strokeDasharray="3 3"
                      strokeWidth={1}
                      fill="var(--indigo-band-fill)"
                      name="80% Error Band"
                      isAnimationActive={false}
                    />
                  )}

                  {/* Raw 30-minute actual line: thinner line (1.5px) */}
                  <Line
                    type="monotone"
                    dataKey="actual30m"
                    stroke="var(--emerald-actual)"
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 4, fill: 'var(--emerald-actual)', stroke: '#fff' }}
                    name="Actual (30-min)"
                    isAnimationActive={false}
                  />

                  {/* Hourly forecast as a step line: 2px (per Requirement 10) */}
                  <Line
                    type="stepAfter"
                    dataKey="forecast"
                    stroke="var(--cyan-accent)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 5, fill: 'var(--cyan-accent)', stroke: '#fff' }}
                    name="Forecast (Hourly)"
                    isAnimationActive={false}
                  />

                  {/* Interactive brush / zoom */}
                  <Brush
                    dataKey="time"
                    height={26}
                    stroke="var(--border-subtle)"
                    fill="var(--bg-surface-subtle)"
                    tickFormatter={(val: string) => val}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Hourly Slots Table Toggle */}
          <div style={{ marginBottom: '8px', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="preset-pill"
              onClick={() => setShowTable((prev) => !prev)}
            >
              {showTable ? 'Hide Hourly Breakdown Table' : 'Show Hourly Breakdown Table (24 Slots)'}
            </button>
          </div>

          {/* Hourly Table */}
          {showTable && (
            <div className="chart-card">
              <h3 className="chart-title" style={{ marginBottom: '8px' }}>
                Settlement Slots Detail ({selectedDate})
              </h3>
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Hour</th>
                      <th>Forecast</th>
                      <th>Actual</th>
                      <th>Signed Error</th>
                      <th>Direction</th>
                      <th>Publication Used</th>
                      <th>Lead Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecastData.hourly.map((slot) => {
                      const isSlotOver = (slot.error ?? 0) > 0;
                      return (
                        <tr key={slot.startTime}>
                          <td className="tabular-nums" style={{ fontWeight: 600 }}>
                            {formatLondonTime(slot.startTime, 'time')}
                          </td>
                          <td className="tabular-nums" style={{ color: 'var(--cyan-accent)' }}>
                            {formatMW(slot.forecast)}
                          </td>
                          <td className="tabular-nums" style={{ color: 'var(--emerald-actual)' }}>
                            {formatMW(slot.actual)}
                          </td>
                          <td
                            className="tabular-nums"
                            style={{
                              fontWeight: 600,
                              color: isSlotOver ? 'var(--amber-over)' : 'var(--rose-under)',
                            }}
                          >
                            {formatBias(slot.error)}
                          </td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                color: isSlotOver ? 'var(--amber-over)' : 'var(--rose-under)',
                                borderColor: isSlotOver ? 'var(--amber-over)' : 'var(--rose-under)',
                              }}
                            >
                              {isSlotOver ? 'Over' : 'Under'}
                            </span>
                          </td>
                          <td
                            className="tabular-nums"
                            style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}
                          >
                            {formatLondonTime(slot.publishTime, 'datetime')}
                          </td>
                          <td className="tabular-nums" style={{ color: 'var(--text-muted)' }}>
                            {formatHorizon(slot.horizon_hours)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
