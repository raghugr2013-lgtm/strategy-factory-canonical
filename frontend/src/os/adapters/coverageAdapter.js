/*
 * coverageAdapter — Sprint 3 Phase-2 live adapter.
 * refs Backend Feature Freeze v1.1.0-stage4 · engines.coverage_router
 *
 * Reads the locked Coverage contract at GET /api/data/coverage. Never writes,
 * never triggers a backfill. Returns the raw payload plus a synthesised
 * `liveness` verdict so surfaces can decide between LIVE / PARTIAL LIVE /
 * ERROR without re-inspecting the shape.
 *
 *   liveness = 'live'         when summary.symbol_count > 0 AND cts_health_score >= 60
 *   liveness = 'partial-live' when the endpoint responded 200 but datasets are sparse
 *   liveness = 'gated'        when the flag COE_COVERAGE_REPORT_ENABLED is off (503)
 *   liveness = 'error'        network / unexpected status
 */
import { isLiveMode, apiFetch } from './apiClient';

const EMPTY_COVERAGE = {
  ts: null,
  canonical_mode: 'm1',
  summary: {
    symbol_count: 0,
    m1_row_count_total: 0,
    cache_bucket_count: 0,
    cache_bucket_stale_count: 0,
    coverage_completeness_pct: null,
    gap_count: 0,
    provider_sync_lag_seconds: null,
    cts_health_score: null,
  },
  symbols: [],
  gaps: [],
  cache: {
    bucket_count: 0,
    bucket_fresh_count: 0,
    bucket_stale_count: 0,
    hit_ratio_last_hour: 0,
    hit_ratio_last_day: 0,
    aggregation_ms_p50: null,
    aggregation_ms_p95: null,
    aggregation_ms_p99: null,
  },
  provider: { sources: [], verification_status: {} },
  health: { subsystem: 'cts', health_score: null, state: 'unknown' },
};

const classify = (payload) => {
  const summary = payload?.summary || {};
  const health = payload?.health || {};
  const score = typeof health.health_score === 'number' ? health.health_score : summary.cts_health_score;
  if ((summary.symbol_count || 0) > 0 && (score ?? 0) >= 60) return 'live';
  return 'partial-live';
};

export const fetchCoverage = async ({ include = 'all', symbol, timeframe } = {}) => {
  if (!isLiveMode()) {
    return { liveness: 'gated', reason: 'REACT_APP_BACKEND_URL not configured', payload: EMPTY_COVERAGE };
  }
  const qs = new URLSearchParams();
  if (include) qs.set('include', include);
  if (symbol) qs.set('symbol', symbol);
  if (timeframe) qs.set('timeframe', timeframe);
  const path = `/api/data/coverage${qs.toString() ? `?${qs.toString()}` : ''}`;
  try {
    const payload = await apiFetch(path);
    return { liveness: classify(payload), reason: null, payload };
  } catch (err) {
    if (err.status === 503) {
      return { liveness: 'gated', reason: 'COE_COVERAGE_REPORT_ENABLED is off', payload: EMPTY_COVERAGE };
    }
    if (err.status === 401) {
      return { liveness: 'error', reason: 'unauthorized · sign in required', payload: EMPTY_COVERAGE };
    }
    return { liveness: 'error', reason: err.message || 'network error', payload: EMPTY_COVERAGE };
  }
};

/**
 * fetchProviderRoster — Phase-2 pull for Market Data adjacency.
 * Uses /api/admin/providers under Backend Feature Freeze v1.1.0-stage4.
 * Requires admin role; returns { available: [], gated: true } on 403.
 */
export const fetchProviderRoster = async () => {
  if (!isLiveMode()) {
    return { liveness: 'gated', reason: 'REACT_APP_BACKEND_URL not configured', payload: [] };
  }
  try {
    const payload = await apiFetch('/api/admin/providers');
    return { liveness: 'live', reason: null, payload };
  } catch (err) {
    if (err.status === 403) {
      return { liveness: 'gated', reason: 'admin role required', payload: [] };
    }
    if (err.status === 401) {
      return { liveness: 'error', reason: 'unauthorized · sign in required', payload: [] };
    }
    return { liveness: 'error', reason: err.message || 'network error', payload: [] };
  }
};
