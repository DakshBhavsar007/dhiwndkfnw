import { describe, expect, it } from 'vitest';
import {
  formatBias,
  formatBiasParts,
  formatDateLabel,
  formatHorizon,
  formatLondonTime,
  formatMW,
  formatMWParts,
  formatNumber,
  formatPercent,
} from '../utils/formatters.js';

describe('formatMW', () => {
  it('formats positive MW numbers with thousand separator and units', () => {
    expect(formatMW(11542)).toBe('11,542 MW');
    expect(formatMW(11542.45, 1)).toBe('11,542.5 MW');
  });

  it('formats zero and small numbers', () => {
    expect(formatMW(0)).toBe('0 MW');
    expect(formatMW(50)).toBe('50 MW');
  });

  it('handles null, undefined and NaN gracefully', () => {
    expect(formatMW(null)).toBe('—');
    expect(formatMW(undefined)).toBe('—');
    expect(formatMW(NaN)).toBe('—');
  });
});

describe('formatMWParts & formatBiasParts', () => {
  it('splits value and MW unit', () => {
    expect(formatMWParts(11542)).toEqual({ value: '11,542', unit: 'MW' });
    expect(formatMWParts(null)).toEqual({ value: '—', unit: '' });
    expect(formatBiasParts(1240)).toEqual({ value: '+1,240', unit: 'MW' });
    expect(formatBiasParts(-850)).toEqual({ value: '-850', unit: 'MW' });
  });
});

describe('formatNumber', () => {
  it('formats numbers with decimal precision', () => {
    expect(formatNumber(1234.56, 1)).toBe('1,234.6');
    expect(formatNumber(0, 0)).toBe('0');
  });

  it('handles null and undefined', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
  });
});

describe('formatPercent', () => {
  it('formats percentage with percent sign', () => {
    expect(formatPercent(12.34)).toBe('12.3%');
    expect(formatPercent(0)).toBe('0.0%');
  });

  it('handles null and undefined', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(undefined)).toBe('—');
  });
});

describe('formatBias', () => {
  it('formats positive bias with plus sign (over-forecast)', () => {
    expect(formatBias(1240)).toBe('+1,240 MW');
    expect(formatBias(0.5, 1)).toBe('+0.5 MW');
  });

  it('formats negative bias with minus sign (under-forecast)', () => {
    expect(formatBias(-850)).toBe('-850 MW');
  });

  it('formats zero bias without duplicate sign', () => {
    expect(formatBias(0)).toBe('0 MW');
  });

  it('handles null and undefined', () => {
    expect(formatBias(null)).toBe('—');
    expect(formatBias(undefined)).toBe('—');
  });
});

describe('formatLondonTime', () => {
  it('formats UTC ISO timestamp into Europe/London time correctly', () => {
    // In January, Europe/London is UTC (GMT)
    const isoUtc = '2026-01-10T14:30:00Z';
    expect(formatLondonTime(isoUtc, 'time')).toBe('14:30');
    expect(formatLondonTime(isoUtc, 'datetime')).toBe('10/01/2026, 14:30');
  });

  it('handles invalid timestamps and nulls', () => {
    expect(formatLondonTime(null)).toBe('—');
    expect(formatLondonTime(undefined)).toBe('—');
    expect(formatLondonTime('invalid-date')).toBe('—');
  });
});

describe('formatDateLabel', () => {
  it('formats YYYY-MM-DD into a localized date string with day of week', () => {
    const label = formatDateLabel('2026-01-02');
    expect(label).toContain('2026');
    expect(label).toContain('Jan');
    expect(label).toContain('02');
  });

  it('handles null and undefined', () => {
    expect(formatDateLabel(null)).toBe('—');
    expect(formatDateLabel(undefined)).toBe('—');
  });
});

describe('formatHorizon', () => {
  it('formats lead time in hours', () => {
    expect(formatHorizon(23)).toBe('23.0h');
    expect(formatHorizon(15.5)).toBe('15.5h');
  });

  it('handles null and undefined', () => {
    expect(formatHorizon(null)).toBe('—');
    expect(formatHorizon(undefined)).toBe('—');
  });
});
