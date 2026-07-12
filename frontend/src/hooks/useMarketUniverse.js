/**
 * R4 — useMarketUniverse hook
 *
 * Single source of truth for symbol pickers across the dashboard.
 * Backed by `GET /api/latent/market-universe`. Falls back to the
 * legacy 7-pair list when the API is unavailable, empty, or times
 * out — so dropdowns never render blank.
 *
 * Public surface:
 *
 *   const {
 *     all,              // string[] — every enabled symbol the registry lists
 *     ingestion,        // string[] — eligibility.ingestion_enabled subset
 *     discovery,        // string[]
 *     mutation,         // string[]
 *     validation,       // string[]
 *     certification,    // string[]
 *     portfolio,        // string[]
 *     live_trading,     // string[]
 *     tier1,            // string[] — tier === 'active' (or legacy fallback)
 *     loading,          // boolean — first load in flight
 *     error,            // string | null
 *     fromFallback,     // true when the legacy fallback is being served
 *     reload,           // () => Promise<void>
 *   } = useMarketUniverse({ eligibility: 'discovery' });
 *
 * The hook accepts an optional `{ eligibility }` filter; when supplied,
 * `useMarketUniverse(...).options` is a convenience accessor returning
 * the appropriate slice already filtered.
 *
 * Discipline
 * ----------
 * - Always-safe defaults: even before the network call resolves, the
 *   hook returns the legacy 7-pair list so dropdowns render immediately.
 * - 5-second hard timeout per request. Exceeding it triggers the
 *   legacy fallback (no UI lockup, no blank selectors).
 * - Session-level singleton: only one in-flight request at a time
 *   even when multiple components call the hook simultaneously.
 * - Refetches when the window regains focus (5-minute stale window).
 *
 * R5 will not touch this file — the hook already consults the same
 * GET endpoint regardless of the backend flag state.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

// ─── Legacy fallback — mirrors the backend authority ───────────────
// Kept here so the hook can render dropdowns even when the API is
// unreachable on first mount.
export const LEGACY_PAIRS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US100', 'BTCUSD', 'ETHUSD',
];

const LEGACY_DISCOVERY     = ['EURUSD', 'GBPUSD', 'XAUUSD'];
const LEGACY_MUTATION      = ['EURUSD', 'GBPUSD', 'XAUUSD'];
const LEGACY_PORTFOLIO     = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'];
const LEGACY_CERTIFICATION = ['EURUSD', 'GBPUSD', 'XAUUSD'];
const LEGACY_TIER1         = ['EURUSD', 'GBPUSD'];

const FETCH_TIMEOUT_MS = 5000;
const STALE_MS         = 5 * 60 * 1000;

// Process-level cache so multiple components share one fetch.
let _cache = null;          // { ts: number, rows: Row[] | null, error: string | null }
let _inflight = null;       // Promise<void> | null
const _listeners = new Set();

function _notify() {
  for (const fn of _listeners) {
    try { fn(); } catch (_) { /* noop */ }
  }
}

function _baseURL() {
  // Same source of truth used by services/api.js across this codebase.
  return process.env.REACT_APP_BACKEND_URL || '';
}

async function _refresh() {
  if (_inflight) return _inflight;
  _inflight = (async () => {
    const url = `${_baseURL()}/api/latent/market-universe?limit=200`;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const rows = Array.isArray(data?.rows) ? data.rows : [];
      _cache = { ts: Date.now(), rows, error: null };
    } catch (e) {
      _cache = {
        ts: Date.now(),
        rows: null,
        error: (e && e.message) || 'fetch_failed',
      };
    } finally {
      _inflight = null;
      _notify();
    }
  })();
  return _inflight;
}

function _isStale() {
  return !_cache || (Date.now() - _cache.ts) > STALE_MS;
}

function _filterEligibility(rows, key) {
  return rows
    .filter((r) =>
      r && r.enabled !== false
      && (r.eligibility || {})[key] === true,
    )
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    .map((r) => r.symbol)
    .filter(Boolean);
}

function _allSymbols(rows) {
  return rows
    .filter((r) => r && r.enabled !== false)
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    .map((r) => r.symbol)
    .filter(Boolean);
}

function _tier1FromRows(rows) {
  const active = rows
    .filter((r) => r && r.enabled !== false && (r.tier || '').toLowerCase() === 'active')
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    .map((r) => r.symbol)
    .filter(Boolean);
  return active.length ? active : LEGACY_TIER1;
}

export function useMarketUniverse(opts = {}) {
  const { eligibility } = opts;
  const [, setVersion] = useState(0);

  useEffect(() => {
    const onChange = () => setVersion((v) => v + 1);
    _listeners.add(onChange);
    if (_isStale() && !_inflight) {
      _refresh();
    }
    const onFocus = () => {
      if (_isStale() && !_inflight) _refresh();
    };
    window.addEventListener('focus', onFocus);
    return () => {
      _listeners.delete(onChange);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const view = useMemo(() => {
    const rows = (_cache && _cache.rows) || null;
    const fromFallback = !rows;
    if (!rows) {
      const fbAll = LEGACY_PAIRS.slice();
      return {
        all:           fbAll,
        ingestion:     fbAll,
        discovery:     LEGACY_DISCOVERY.slice(),
        mutation:      LEGACY_MUTATION.slice(),
        validation:    fbAll,
        certification: LEGACY_CERTIFICATION.slice(),
        portfolio:     LEGACY_PORTFOLIO.slice(),
        live_trading:  [],
        tier1:         LEGACY_TIER1.slice(),
        fromFallback,
      };
    }
    return {
      all:           _allSymbols(rows),
      ingestion:     _filterEligibility(rows, 'ingestion_enabled'),
      discovery:     _filterEligibility(rows, 'discovery_enabled'),
      mutation:      _filterEligibility(rows, 'mutation_enabled'),
      validation:    _filterEligibility(rows, 'validation_enabled'),
      certification: _filterEligibility(rows, 'certification_enabled'),
      portfolio:     _filterEligibility(rows, 'portfolio_enabled'),
      live_trading:  _filterEligibility(rows, 'live_trading_enabled'),
      tier1:         _tier1FromRows(rows),
      fromFallback,
    };
  }, [_cache?.ts]);

  const reload = useCallback(async () => { await _refresh(); }, []);
  const loading = !!_inflight && !_cache;
  const error = _cache?.error || null;

  // Convenience: when `eligibility` is supplied, expose `.options` as
  // the appropriate slice. Always non-empty (falls back to all).
  let options;
  if (eligibility && Object.prototype.hasOwnProperty.call(view, eligibility)) {
    const slice = view[eligibility];
    options = (slice && slice.length) ? slice : view.all;
  } else {
    options = view.all;
  }
  // Safety net — never return an empty array to the dropdown.
  if (!options || !options.length) {
    options = LEGACY_PAIRS.slice();
  }

  return {
    ...view,
    options,
    loading,
    error,
    reload,
  };
}

// Test/inspection helpers (not part of the public API).
export function __resetUseMarketUniverseCache_TESTONLY() {
  _cache = null;
  _inflight = null;
}

export default useMarketUniverse;
