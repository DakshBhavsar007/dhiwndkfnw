import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient, getApiBaseUrl } from '../api/client.js';

describe('apiClient', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('getApiBaseUrl returns empty string if VITE_API_BASE_URL is not set', () => {
    expect(getApiBaseUrl()).toBe('');
  });

  it('getForecast calls /api/forecast with date and cutoff parameters', async () => {
    const mockResponse = {
      delivery_date: '2026-01-05',
      cutoff_time: '09:00',
      hourly: [],
      raw_actuals_30min: [],
      summary_metrics: { count: 0 },
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    globalThis.fetch = fetchMock;

    const result = await apiClient.getForecast('2026-01-05', '09:00');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0];
    expect(calledUrl).toContain('/api/forecast');
    expect(calledUrl).toContain('date=2026-01-05');
    expect(calledUrl).toContain('cutoff=09%3A00');
    expect(result).toEqual(mockResponse);
  });

  it('getAccuracy calls /api/accuracy with start, end and cutoff', async () => {
    const mockResponse = {
      start_date: '2026-01-02',
      end_date: '2026-01-10',
      cutoff_time: '09:00',
      headline_metrics: { count: 216, mae: 1000.0, mae_debiased: 750.0 },
      by_hour_of_day: [],
      by_horizon: [],
      error_histogram: [],
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    globalThis.fetch = fetchMock;

    const result = await apiClient.getAccuracy('2026-01-02', '2026-01-10', '09:00');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0];
    expect(calledUrl).toContain('/api/accuracy');
    expect(calledUrl).toContain('start=2026-01-02');
    expect(calledUrl).toContain('end=2026-01-10');
    expect(result).toEqual(mockResponse);
  });

  it('getErrorBand calls /api/error-band with date and cutoff', async () => {
    const mockResponse = {
      delivery_date: '2026-01-06',
      cutoff_time: '09:00',
      history_days_used: 7,
      band: [],
      reason: null,
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    globalThis.fetch = fetchMock;

    const result = await apiClient.getErrorBand('2026-01-06', '09:00');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0];
    expect(calledUrl).toContain('/api/error-band');
    expect(calledUrl).toContain('date=2026-01-06');
    expect(result).toEqual(mockResponse);
  });

  it('handles HTTP error responses and extracts detail message', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({ detail: 'Delivery date before valid start date 2026-01-02' }),
    });
    globalThis.fetch = fetchMock;

    await expect(apiClient.getForecast('2025-12-01')).rejects.toThrow(
      'Delivery date before valid start date 2026-01-02'
    );
  });
});
