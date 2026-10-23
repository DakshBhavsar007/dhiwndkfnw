/**
 * Utility formatters for energy trading values, London time, and percentages.
 */

/**
 * Format a number in Megawatts (MW) with thousand separators.
 * Null/undefined/NaN is formatted as "—".
 */
export function formatMW(value: number | null | undefined, decimals: number = 0): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  const formatted = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

  return `${formatted} MW`;
}

/**
 * Format MW with value and unit separated for UI rendering with muted units.
 */
export function formatMWParts(value: number | null | undefined, decimals: number = 0): { value: string; unit: string } {
  if (value === null || value === undefined || isNaN(value)) {
    return { value: '—', unit: '' };
  }
  const formatted = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
  return { value: formatted, unit: 'MW' };
}

/**
 * Format signed bias with separated unit for UI rendering.
 */
export function formatBiasParts(value: number | null | undefined, decimals: number = 0): { value: string; unit: string } {
  if (value === null || value === undefined || isNaN(value)) {
    return { value: '—', unit: '' };
  }
  const sign = value > 0 ? '+' : '';
  const formatted = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
  return { value: `${sign}${formatted}`, unit: 'MW' };
}

/**
 * Format raw number with optional thousand separator without units.
 */
export function formatNumber(value: number | null | undefined, decimals: number = 1): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  return new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Format a percentage value.
 */
export function formatPercent(value: number | null | undefined, decimals: number = 1): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  const formatted = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

  return `${formatted}%`;
}

/**
 * Format signed bias: forecast - actual.
 * Positive = Over-forecast (+)
 * Negative = Under-forecast (-)
 */
export function formatBias(value: number | null | undefined, decimals: number = 0): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—';
  }
  const sign = value > 0 ? '+' : '';
  const formatted = new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

  return `${sign}${formatted} MW`;
}

/**
 * Format an ISO timestamp string into Europe/London time.
 * Mode:
 * - 'time': "HH:mm"
 * - 'datetime': "YYYY-MM-DD HH:mm"
 * - 'short': "DD MMM HH:mm"
 */
export function formatLondonTime(
  isoString: string | null | undefined,
  mode: 'time' | 'datetime' | 'short' = 'time'
): string {
  if (!isoString) return '—';

  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '—';

    const options: Intl.DateTimeFormatOptions = {
      timeZone: 'Europe/London',
      hour12: false,
    };

    if (mode === 'time') {
      options.hour = '2-digit';
      options.minute = '2-digit';
      return new Intl.DateTimeFormat('en-GB', options).format(date);
    }

    if (mode === 'short') {
      options.day = '2-digit';
      options.month = 'short';
      options.hour = '2-digit';
      options.minute = '2-digit';
      return new Intl.DateTimeFormat('en-GB', options).format(date);
    }

    options.year = 'numeric';
    options.month = '2-digit';
    options.day = '2-digit';
    options.hour = '2-digit';
    options.minute = '2-digit';
    return new Intl.DateTimeFormat('en-GB', options).format(date);
  } catch {
    return '—';
  }
}

/**
 * Format a delivery date string (YYYY-MM-DD) with human-readable weekday.
 */
export function formatDateLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    // Append T12:00:00Z to avoid timezone day shifts
    const d = new Date(`${dateStr}T12:00:00Z`);
    if (isNaN(d.getTime())) return dateStr;
    return new Intl.DateTimeFormat('en-GB', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      timeZone: 'Europe/London',
    }).format(d);
  } catch {
    return dateStr;
  }
}

/**
 * Format forecast horizon (lead time) in hours.
 */
export function formatHorizon(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || isNaN(hours)) {
    return '—';
  }
  return `${hours.toFixed(1)}h`;
}
