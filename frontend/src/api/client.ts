/**
 * Typed API client for the BMRS Wind-Power Forecast Monitoring API.
 */

import type {
  AccuracyResponse,
  BacktestResponse,
  DecisionSummaryResponse,
  ErrorBandResponse,
  ForecastResponse,
  HealthResponse,
  MetaResponse,
} from '../types/api.js';

export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && typeof envUrl === 'string') {
    // Strip trailing slashes
    return envUrl.replace(/\/+$/, '');
  }
  return '';
}

async function request<T>(endpoint: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = new URL(`${baseUrl}${endpoint}`, window.location.origin);

  if (params) {
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        url.searchParams.append(key, String(val));
      }
    });
  }

  const response = await fetch(url.toString(), {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson && typeof errorJson === 'object' && 'detail' in errorJson) {
        errorDetail = Array.isArray(errorJson.detail)
          ? errorJson.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(', ')
          : String(errorJson.detail);
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  getHealth: () => request<HealthResponse>('/health'),

  getMeta: () => request<MetaResponse>('/api/meta'),

  getForecast: (date: string, cutoff: string = '09:00') =>
    request<ForecastResponse>('/api/forecast', { date, cutoff }),

  getAccuracy: (start?: string, end?: string, cutoff: string = '09:00') =>
    request<AccuracyResponse>('/api/accuracy', { start, end, cutoff }),

  getErrorBand: (date: string, cutoff: string = '09:00') =>
    request<ErrorBandResponse>('/api/error-band', { date, cutoff }),

  getDecisionSummary: (date: string, cutoff: string = '09:00') =>
    request<DecisionSummaryResponse>('/api/decision-summary', { date, cutoff }),

  getBacktest: (cutoff: string = '09:00') =>
    request<BacktestResponse>('/api/backtest', { cutoff }),
};
