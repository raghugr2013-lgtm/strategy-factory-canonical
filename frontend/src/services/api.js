// Phase G2 — single-flight + cooldown throttle for write helpers.
// See services/throttledPost.js for semantics.
import { throttledPost } from './throttledPost';

// ── Canonical backend URL resolution (A-2) — single source of truth ──
// Every frontend API request must resolve through this exported helper.
// Order (see docs/CONFIGURATION.md → "Frontend backend-URL resolution"):
//   1. REACT_APP_BACKEND_URL baked at build time, if set;
//   2. localhost / 127.0.0.1 → http://<hostname>:8001 (canonical dev port);
//   3. '' → same-origin relative /api (production behind Traefik).
export function resolveBackendUrl() {
  const fromEnv = (process.env.REACT_APP_BACKEND_URL || '').trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  if (typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
  )) {
    return `http://${window.location.hostname}:8001`;
  }
  return '';
}
export const API_URL = resolveBackendUrl();

// ── Timeout-aware fetch ───────────────────────────────────────────────
// Every API call goes through here so a slow/hung backend can never
// lock the browser tab. Long operations (backtest, auto-factory) get
// 120 s; everything else gets 30 s.
function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal })
    .catch((err) => {
      if (err.name === 'AbortError') {
        throw new Error(`Request timed out after ${timeoutMs / 1000}s — the backend may still be processing`);
      }
      throw err;
    })
    .finally(() => clearTimeout(timerId));
}
const LONG = 120000; // 120 s for slow operations
const STD  =  30000; //  30 s for normal operations

export async function generateStrategy(pair, timeframe, style) {
  const res = await fetchWithTimeout(`${API_URL}/api/generate-strategy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pair, timeframe, style }),
  }, LONG);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to generate strategy');
  return data;
}

export async function generateDashboardStrategies({
  pair = 'EURUSD',
  timeframe = 'H1',
  style = 'trend-following',
  firm = 'ftmo',
  count = 5,
  topN = 5,
  refineTop = 3,
  // Phase-3 — opt-in parameter optimisation + portfolio combiner.
  // Defaults match the dashboard contract (optimise top-2 strategies
  // and emit the portfolio block whenever ≥2 cards are available).
  optimizeTop = 2,
  optimizeVariants = 30,
  enablePortfolio = true,
  // P2 — optimiser choice: 'random_search' (default) or 'ga'
  optimizer = 'random_search',
  gaPopulation = 16,
  gaGenerations = 5,
  // P2 — Signal Quality Score filter (entry-quality gate). Defaults
  // OFF so existing callers see no behaviour change. UI can pass
  // qualityFilter=true + qualityThreshold=60 to enable it.
  qualityFilter = false,
  qualityThreshold = 60,
} = {}) {
  const body = JSON.stringify({
    pair, timeframe, style, firm,
    count, top_n: topN, refine_top: refineTop,
    optimize_top: optimizeTop,
    optimize_variants: optimizeVariants,
    enable_portfolio: enablePortfolio,
    optimizer,
    ga_population: gaPopulation,
    ga_generations: gaGenerations,
    quality_filter: qualityFilter,
    quality_threshold: qualityThreshold,
  });

  // Try primary endpoint, fall back on 404 only.
  let res = await fetchWithTimeout(`${API_URL}/api/dashboard/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  }, LONG);

  if (res.status === 404) {
    res = await fetchWithTimeout(`${API_URL}/api/run-pipeline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'dashboard',
        pair, timeframe, style, firm,
        count, top_n: topN, refine_top: refineTop,
      }),
    }, LONG);
  }

  // Read the body ONCE and store it — never call res.json() twice.
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON response */ }

  if (!res.ok) {
    const detail = data?.detail || data?.message || '';
    const label =
      res.status === 400 ? 'Pipeline input error' :
      res.status === 404 ? 'Pipeline endpoint not found' :
      res.status >= 500 ? 'Pipeline server error' :
      'Pipeline request failed';
    throw new Error(detail ? `${label}: ${detail}` : `${label} (HTTP ${res.status})`);
  }

  return data;
}

// ── P4 — Multi-asset portfolio rollout ────────────────────────────
export async function generateMultiAssetPortfolio({
  pairs,
  timeframe = 'H1',
  style = 'trend-following',
  firm = 'ftmo',
  count = 2,
  topNPerPair = 2,
  gateEnabled = true,
  gateThreshold = 1.10,
  gateMaxDdPct = 30.0,
  gateSeeds = [7, 42, 101, 314, 2718],
  gatePopulation = 10,
  gateGenerations = 3,
  optimizeTop = 0,
  optimizer = 'random_search',
  qualityFilter = false,
  qualityThreshold = 60,
} = {}) {
  const body = JSON.stringify({
    pairs,
    timeframe,
    style,
    firm,
    count,
    top_n_per_pair: topNPerPair,
    gate_enabled: gateEnabled,
    gate_threshold: gateThreshold,
    gate_max_dd_pct: gateMaxDdPct,
    gate_seeds: gateSeeds,
    gate_population: gatePopulation,
    gate_generations: gateGenerations,
    optimize_top: optimizeTop,
    optimizer,
    quality_filter: qualityFilter,
    quality_threshold: qualityThreshold,
  });
  const res = await fetchWithTimeout(
    `${API_URL}/api/dashboard/generate-portfolio`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body },
    LONG,
  );
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = data?.detail?.message || data?.detail || data?.message || '';
    throw new Error(detail || `Multi-asset pipeline failed (HTTP ${res.status})`);
  }
  return data;
}


// ── P1 — Multi-asset portfolio persistence ─────────────────────────

export async function savePortfolio({ name, portfolioResult, requestEcho } = {}) {
  const body = JSON.stringify({
    name: name || '',
    portfolio_result: portfolioResult || {},
    request_echo: requestEcho || {},
  });
  const res = await fetchWithTimeout(
    `${API_URL}/api/dashboard/portfolios/save`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body },
    STD,
  );
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    throw new Error(data?.detail || data?.error || `Save failed (HTTP ${res.status})`);
  }
  return data;
}


export async function listSavedPortfolios({ limit = 100 } = {}) {
  const res = await fetchWithTimeout(
    `${API_URL}/api/dashboard/portfolios/list?limit=${limit}`,
    { method: 'GET', headers: { 'Content-Type': 'application/json' } },
    STD,
  );
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    throw new Error(data?.detail || `List failed (HTTP ${res.status})`);
  }
  return data;
}


export async function loadSavedPortfolio(portfolioId) {
  const res = await fetchWithTimeout(
    `${API_URL}/api/dashboard/portfolios/${encodeURIComponent(portfolioId)}`,
    { method: 'GET', headers: { 'Content-Type': 'application/json' } },
    STD,
  );
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    throw new Error(data?.detail || `Load failed (HTTP ${res.status})`);
  }
  return data;
}


export async function deleteSavedPortfolio(portfolioId) {
  const res = await fetchWithTimeout(
    `${API_URL}/api/dashboard/portfolios/${encodeURIComponent(portfolioId)}`,
    { method: 'DELETE', headers: { 'Content-Type': 'application/json' } },
    STD,
  );
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    throw new Error(data?.detail || `Delete failed (HTTP ${res.status})`);
  }
  return data;
}


// ── P2 — Dataset inventory (dynamic pair/timeframe discovery) ──────
export async function fetchDatasets() {
  const res = await fetchWithTimeout(`${API_URL}/api/dashboard/datasets`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  }, STD);
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    throw new Error(
      (typeof data?.detail === 'string' && data.detail) ||
      data?.detail?.message ||
      `Dataset fetch failed (HTTP ${res.status})`,
    );
  }
  return data;
}

// ── P2 — One-click data ingestion (Dukascopy) ──────────────────────
// Wraps POST /api/download-data so the dashboard can kick off a live
// fetch when a (pair, timeframe) combination has insufficient data.
// Backend expects lower-case db-form timeframes (1m, 5m, ..., 1d).
const CANONICAL_TO_DB_TF = {
  M1: '1m', M5: '5m', M15: '15m', M30: '30m',
  H1: '1h', H4: '4h', D1: '1d',
};

export async function loadMarketData({
  pair, timeframe,
  // Default: fetch the trailing 2 years of data so there are enough
  // candles for a meaningful backtest even on H4 / D1.
  yearsBack = 2,
} = {}) {
  const dbTf = CANONICAL_TO_DB_TF[timeframe] || String(timeframe || '').toLowerCase();
  const today = new Date();
  const from = new Date(today);
  from.setFullYear(today.getFullYear() - yearsBack);
  const iso = (d) => d.toISOString().slice(0, 10);

  const res = await fetchWithTimeout(`${API_URL}/api/download-data`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: pair,
      timeframe: dbTf,
      date_from: iso(from),
      date_to: iso(today),
    }),
  }, LONG);

  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok || data?.success === false) {
    const msg =
      (typeof data?.detail === 'string' && data.detail) ||
      data?.detail?.message ||
      data?.error ||
      `Data download failed (HTTP ${res.status})`;
    throw new Error(msg);
  }
  return data;
}

// ── P2 — Quality Threshold Calibration ──────────────────────────────
export async function fetchQualityProfile({
  pair = 'EURUSD',
  timeframe = 'H1',
  style = 'trend-following',
  offset = 5,
} = {}) {
  const res = await fetchWithTimeout(`${API_URL}/api/dashboard/quality-profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pair, timeframe, style, offset }),
  }, LONG);

  let data = {};
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = data?.detail;
    // Prefer the backend's structured error message in all cases —
    // FastAPI wraps HTTPException(detail={...}) inside {"detail": {...}},
    // and the payload always carries a human-readable `message` field.
    const structured = (detail && typeof detail === 'object' && detail.message)
      ? detail.message
      : null;
    const stringDetail = (typeof detail === 'string' && detail) || null;
    // 422 is used by the calibration endpoint EXCLUSIVELY for the
    // "insufficient data for this pair / timeframe" case, so even if
    // the body failed to parse (CORS, interceptor, stream consumed
    // elsewhere, etc.) we can still produce a useful message.
    const statusFallback = res.status === 422
      ? `Not enough candles for ${pair}/${timeframe} — try a different pair or timeframe.`
      : `Calibration failed (HTTP ${res.status})`;
    const msg =
      structured ||
      stringDetail ||
      data?.message ||
      statusFallback;
    throw new Error(msg);
  }
  return data;
}

// ── Phase 11 — Strategy Library ──────────────────────────────────────

export async function saveStrategyToLibrary(strategy, { source = 'dashboard', force = false } = {}) {
  const res = await fetchWithTimeout(`${API_URL}/api/library/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy, source, force }),
  }, STD);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to save strategy');
  return data;
}

export async function autoSaveTopStrategies(topStrategies, { source = 'auto_save' } = {}) {
  const res = await fetchWithTimeout(`${API_URL}/api/library/auto-save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ top_strategies: topStrategies, source }),
  }, STD);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to auto-save');
  return data;
}

export async function listLibraryStrategies({ pair, timeframe, verdict, limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (pair) params.set('pair', pair);
  if (timeframe) params.set('timeframe', timeframe);
  if (verdict) params.set('verdict', verdict);
  params.set('limit', String(limit));
  const res = await fetch(`${API_URL}/api/library/list?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to list library');
  return res.json();
}

export async function runBacktest(strategyText, pair, timeframe, useUploadedData = false, dateFrom = null, dateTo = null, spreadPips = null, riskPercent = 1.0) {
  const body = {
    strategy_text: strategyText, pair, timeframe,
    use_uploaded_data: useUploadedData,
    risk_percent: riskPercent,
  };
  if (dateFrom) body.date_from = dateFrom;
  if (dateTo) body.date_to = dateTo;
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  const res = await fetchWithTimeout(`${API_URL}/api/run-backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, LONG);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to run backtest');
  return data;
}

export async function saveStrategy(strategyText, pair, timeframe, backtestResults, extra = {}) {
  const res = await fetch(`${API_URL}/api/save-strategy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_text: strategyText,
      pair,
      timeframe,
      backtest_results: backtestResults,
      strategy_type: extra.strategy_type || null,
      indicators: extra.indicators || null,
      safety: extra.safety || null,
      validation: extra.validation || null,
      monte_carlo: extra.monte_carlo || null,
      ranking: extra.ranking || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to save strategy');
  }
  return res.json();
}

export async function getStrategies(filters = {}) {
  const params = new URLSearchParams();
  if (filters.symbol) params.set('symbol', filters.symbol);
  if (filters.timeframe) params.set('timeframe', filters.timeframe);
  if (filters.min_score !== undefined) params.set('min_score', filters.min_score);
  if (filters.max_score !== undefined) params.set('max_score', filters.max_score);
  if (filters.status) params.set('status', filters.status);
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.sort_dir) params.set('sort_dir', filters.sort_dir);
  const qs = params.toString();
  const res = await fetch(`${API_URL}/api/strategies${qs ? '?' + qs : ''}`);
  if (!res.ok) throw new Error('Failed to fetch strategies');
  return res.json();
}

// ── Library (single source of truth = strategy_library via /auto-factory/saved) ──
//
// The legacy /api/strategies endpoint reads a separate "strategies"
// collection that Auto Factory does NOT write to. Every strategy actually
// produced by the pipeline lands in `strategy_library`, which is exposed
// via /api/auto-factory/saved. This helper reads from there and
// normalises the row shape into what <StrategyLibrary /> expects.
export async function getLibraryStrategies(filters = {}) {
  const res = await fetch(`${API_URL}/api/auto-factory/saved?limit=500`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to fetch library');
  const data = await res.json();
  const rows = (data.strategies || []).map((s) => ({
    id: s.strategy_id,
    pair: s.pair,
    timeframe: s.timeframe,
    strategy_type: s.style || s.strategy_type,
    strategy_text: s.strategy_text,
    parameters: s.parameters || {},
    score: s.score,
    status: s.verdict || s.prop_status || 'RISKY',
    metrics: {
      profit_factor: s.profit_factor,
      max_drawdown_pct: s.max_drawdown_pct,
      win_rate: s.win_rate,
      total_trades: s.total_trades,
      total_return_pct: s.total_return_pct,
      net_profit: null,
    },
    source: s.source,
    fingerprint: s.fingerprint,
    created_at: s.created_at,
  }));

  // Client-side filter + sort (mirrors the legacy server-side behaviour).
  let filtered = rows;
  if (filters.symbol) filtered = filtered.filter((r) => r.pair === filters.symbol);
  if (filters.timeframe) filtered = filtered.filter((r) => r.timeframe === filters.timeframe);
  if (filters.status) filtered = filtered.filter((r) => r.status === filters.status);
  if (filters.sort_by) {
    const dir = filters.sort_dir === 'asc' ? 1 : -1;
    const pick = (r) => {
      const m = r.metrics || {};
      switch (filters.sort_by) {
        case 'score':         return r.score ?? 0;
        case 'profit_factor': return m.profit_factor ?? 0;
        case 'drawdown':      return m.max_drawdown_pct ?? 0;
        case 'win_rate':      return m.win_rate ?? 0;
        case 'net_profit':    return m.total_return_pct ?? 0;
        default:              return 0;
      }
    };
    filtered = [...filtered].sort((a, b) => dir * ((pick(a) || 0) - (pick(b) || 0)));
  }
  return { strategies: filtered, count: filtered.length };
}

// Delete a strategy from strategy_library (source of truth for Library).
export async function deleteLibraryStrategy(id) {
  const res = await fetch(`${API_URL}/api/auto-factory/saved/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete strategy');
  return res.json();
}


export async function getStrategyDetail(id) {
  const res = await fetch(`${API_URL}/api/strategies/${id}`);
  if (!res.ok) throw new Error('Failed to fetch strategy');
  return res.json();
}

export async function deleteStrategy(id) {
  const res = await fetch(`${API_URL}/api/strategies/${id}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete');
  }
  return res.json();
}

export async function analyzePortfolio(strategyIds, allocations = null) {
  const body = { strategy_ids: strategyIds };
  if (allocations) body.allocations = allocations;
  const res = await fetch(`${API_URL}/api/portfolio-analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Portfolio analysis failed');
  }
  return res.json();
}

export async function autoBuildPortfolio(config = {}) {
  const res = await fetch(`${API_URL}/api/portfolio-auto-build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_size: config.target_size || 4,
      max_pair_corr: config.max_pair_corr ?? 0.6,
      min_score: config.min_score || 0,
      min_safety: config.min_safety || 0,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Auto portfolio build failed');
  }
  return res.json();
}

export async function getLiveAllocation(strategyIds, config = {}) {
  const res = await fetch(`${API_URL}/api/portfolio-live-allocation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_ids: strategyIds,
      alloc_rules: config.alloc_rules || null,
      use_safety_adjustment: config.use_safety_adjustment !== false,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Live allocation failed');
  }
  return res.json();
}

export async function getAllocationHistory(filters = {}) {
  const params = new URLSearchParams();
  if (filters.symbol) params.set('symbol', filters.symbol);
  if (filters.timeframe) params.set('timeframe', filters.timeframe);
  if (filters.strategy_id) params.set('strategy_id', filters.strategy_id);
  if (filters.limit) params.set('limit', filters.limit);
  const res = await fetch(`${API_URL}/api/allocation-history?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch allocation history');
  }
  return res.json();
}

export async function getRebalanceConfig() {
  const res = await fetch(`${API_URL}/api/rebalance/config`);
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed to fetch rebalance config'); }
  return res.json();
}

export async function saveRebalanceConfig(config) {
  const res = await fetch(`${API_URL}/api/rebalance/config`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
  });
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed to save config'); }
  return res.json();
}

export async function runRebalance(reason = 'manual') {
  const res = await fetch(`${API_URL}/api/rebalance/run?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Rebalance failed'); }
  return res.json();
}

export async function getRebalanceStatus() {
  const res = await fetch(`${API_URL}/api/rebalance/status`);
  if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'Failed to fetch status'); }
  return res.json();
}



export async function rankStrategies(strategies) {
  const res = await fetch(`${API_URL}/api/rank-strategies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategies }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to rank strategies');
  }
  return res.json();
}

export async function compareStrategies(strategyIds) {
  const res = await fetch(`${API_URL}/api/strategies/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_ids: strategyIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to compare strategies');
  }
  return res.json();
}


export async function analyzeStrategy(strategyText, backtestResults) {
  const res = await fetch(`${API_URL}/api/analyze-strategy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_text: strategyText,
      backtest_results: backtestResults,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to analyze strategy');
  }
  return res.json();
}

export async function extractParams(strategyText) {
  const res = await fetch(`${API_URL}/api/extract-params`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_text: strategyText }),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function uploadMarketData(file, symbol, timeframe, source = 'bid_1m') {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('symbol', symbol);
  formData.append('timeframe', timeframe);
  formData.append('source', source);

  let res;
  try {
    res = await fetch(`${API_URL}/api/upload-data`, {
      method: 'POST',
      body: formData,
    });
  } catch (networkErr) {
    // Connection dropped / CORS / offline — backend may still have committed.
    // Return a structured "unknown" marker; caller will reconcile against DB.
    console.warn('[uploadMarketData] network error (backend may still have committed)', networkErr);
    return { status: 'unknown', ok: false, http: 0, reason: networkErr.message, body: null };
  }

  // Read body once as text so we can log the raw payload AND parse JSON safely.
  const rawText = await res.text();
  let body = null;
  try {
    body = rawText ? JSON.parse(rawText) : null;
  } catch (jsonErr) {
    console.warn('[uploadMarketData] non-JSON response', { status: res.status, rawText });
  }

  console.info('[uploadMarketData]', { status: res.status, ok: res.ok, body });

  // 2xx → confirmed success. Backend returns { status: "success", ... }.
  if (res.ok) {
    return body || { status: 'success', rows_inserted: 0, note: 'empty response body' };
  }

  // 502 / 503 / 504 → gateway error while backend was processing. The merge
  // very likely committed (idempotent upsert by (symbol, timeframe, timestamp)).
  // Return "unknown" so UI can reconcile against /api/market-data.
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    return {
      status: 'unknown',
      ok: false,
      http: res.status,
      reason: `Gateway error (HTTP ${res.status}) — backend may still have committed the upload`,
      body,
    };
  }

  // Real 4xx / other 5xx → genuine failure. Surface backend detail if present.
  const detail = body?.detail || body?.message || body?.error;
  throw new Error(detail || `Upload failed (HTTP ${res.status})`);
}

export async function getMarketData() {
  const res = await fetch(`${API_URL}/api/market-data`);
  if (!res.ok) throw new Error('Failed to fetch market data');
  return res.json();
}

export async function downloadMarketData(symbol, timeframe, dateFrom, dateTo) {
  // Phase G2 — client-side single-flight + 3s cooldown per (symbol, tf).
  // Mirrors the server-side advisory lock so the UI surfaces a clean
  // "throttled" outcome instead of hammering the lock and getting 409s.
  const key = `download-data:${symbol}:${timeframe}`;
  const gate = await throttledPost(key, async () => {
    const res = await fetch(`${API_URL}/api/download-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        timeframe,
        date_from: dateFrom,
        date_to: dateTo,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      // Surface the server-side advisory_lock 409 distinctly so the UI
      // can show a helpful "another download is in flight" hint.
      if (res.status === 409) {
        const e = new Error('Another download for this dataset is already running.');
        e.throttled = true;
        e.serverLock = err.detail || err;
        throw e;
      }
      throw new Error(err.detail || 'Failed to download market data');
    }
    const data = await res.json();
    if (data.success === false) {
      throw new Error(data.error || 'Data not available or fetch failed');
    }
    return data;
  }, { minIntervalMs: 3000 });
  if (!gate.ok) {
    const e = new Error(`Throttled: ${gate.reason}. Please wait a moment.`);
    e.throttled = true;
    e.reason = gate.reason;
    throw e;
  }
  return gate.result;
}

export async function generateCbot(strategyText, pair, timeframe, backtestParams, simSettings, safetyRules = null, indicators = null, strategyType = null, extraction = null) {
  const res = await fetch(`${API_URL}/api/generate-cbot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_text: strategyText,
      pair,
      timeframe,
      backtest_params: backtestParams || null,
      sim_settings: simSettings || null,
      safety_rules: safetyRules || null,
      indicators: indicators || null,
      strategy_type: strategyType || null,
      extraction: extraction || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to generate cBot');
  }
  return res.json();
}

export async function runPipeline(pair, timeframe, count = 5, riskPercent = 1.0, spreadPips = null) {
  const body = { pair, timeframe, count, risk_percent: riskPercent };
  if (spreadPips !== null) body.spread_pips = spreadPips;
  const res = await fetch(`${API_URL}/api/run-pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Pipeline failed');
  }
  return res.json();
}

export async function runAutoFactory(config) {
  const res = await fetchWithTimeout(`${API_URL}/api/auto-factory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  }, LONG);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data?.detail === 'string'
      ? data.detail
      : (data?.detail?.message || 'Auto Factory failed');
    const e = new Error(msg);
    e.status = res.status;
    e.body = data;
    throw e;
  }
  return data;
}

export async function optimizeStrategy(strategyText, pair, timeframe, useUploadedData = false, spreadPips = null, riskPercent = 1.0) {
  const body = {
    strategy_text: strategyText,
    pair,
    timeframe,
    use_uploaded_data: useUploadedData,
    risk_percent: riskPercent,
  };
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  const res = await fetch(`${API_URL}/api/optimize-strategy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Optimization failed');
  }
  return res.json();
}

export async function optimizeRandom(strategyText, pair, timeframe, numVariants = 75, trainRatio = 0.70, spreadPips = null, riskPercent = 1.0) {
  const body = {
    strategy_text: strategyText,
    pair,
    timeframe,
    num_variants: numVariants,
    train_ratio: trainRatio,
    risk_percent: riskPercent,
  };
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  const res = await fetch(`${API_URL}/api/optimize-random`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Random optimization failed');
  }
  return res.json();
}

export async function checkDataGaps(symbol, timeframe) {
  const res = await fetch(`${API_URL}/api/check-gaps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, timeframe }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to check data gaps');
  }
  const data = await res.json();
  if (data.success === false) {
    throw new Error(data.error || 'Gap check failed');
  }
  return data;
}

export async function fixDataGaps(symbol, timeframe) {
  const res = await fetch(`${API_URL}/api/fix-gaps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, timeframe }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fix data gaps');
  }
  const data = await res.json();
  if (data.success === false) {
    throw new Error(data.error || 'Gap fix failed');
  }
  return data;
}

export async function validateStrategy(strategyText, pair, timeframe, spreadPips = null, riskPercent = 1.0) {
  const body = {
    strategy_text: strategyText,
    pair,
    timeframe,
    risk_percent: riskPercent,
  };
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  const res = await fetch(`${API_URL}/api/validate-strategy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Validation failed');
  }
  return res.json();
}

export async function runSafetyCheck(strategyText, pair, timeframe, spreadPips = null, riskPercent = 1.0, thresholds = null) {
  const body = {
    strategy_text: strategyText,
    pair,
    timeframe,
    risk_percent: riskPercent,
  };
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  if (thresholds) body.thresholds = thresholds;
  const res = await fetch(`${API_URL}/api/safety-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Safety check failed');
  }
  return res.json();
}

export async function runMonteCarlo(strategyText, pair, timeframe, numSimulations = 100, spreadPips = null, riskPercent = 1.0) {
  const body = {
    strategy_text: strategyText,
    pair,
    timeframe,
    num_simulations: numSimulations,
    risk_percent: riskPercent,
  };
  if (spreadPips !== null && spreadPips !== '') body.spread_pips = parseFloat(spreadPips);
  const res = await fetch(`${API_URL}/api/monte-carlo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Monte Carlo failed');
  }
  return res.json();
}


export async function getServerFiles() {
  const res = await fetch(`${API_URL}/api/server-files`);
  if (!res.ok) throw new Error('Failed to fetch server files');
  return res.json();
}

export async function importServerFile(filename, symbol, timeframe) {
  const res = await fetch(`${API_URL}/api/import-server-file`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, symbol, timeframe }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Import failed');
  }
  const data = await res.json();
  if (data.success === false) {
    throw new Error(data.error || 'Import failed');
  }
  return data;
}


// ── Live Tracking API ──

export async function startLiveTracking(strategyId, config = {}) {
  const res = await fetch(`${API_URL}/api/live/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_id: strategyId,
      failure_threshold: config.failure_threshold || 3,
      auto_disable: config.auto_disable !== false,
    }),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
  return res.json();
}

export async function stopLiveTracking(strategyId) {
  const res = await fetch(`${API_URL}/api/live/stop`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_id: strategyId }),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
  return res.json();
}

export async function getTrackedStrategies() {
  const res = await fetch(`${API_URL}/api/live/strategies`);
  if (!res.ok) throw new Error('Failed to fetch tracked strategies');
  return res.json();
}

export async function updateLiveTracking(strategyId) {
  const res = await fetch(`${API_URL}/api/live/update/${strategyId}`, { method: 'POST' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Update failed'); }
  return res.json();
}

export async function updateAllLiveTracking() {
  const res = await fetch(`${API_URL}/api/live/update-all`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to update all');
  return res.json();
}

export async function refreshMarketData(symbol, timeframe, daysBack = 1) {
  // Phase G2 — client-side single-flight + 3s cooldown per (symbol, tf).
  const key = `live-refresh-data:${symbol}:${timeframe}`;
  const gate = await throttledPost(key, async () => {
    const res = await fetch(`${API_URL}/api/live/refresh-data`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, timeframe, days_back: daysBack }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      if (res.status === 409) {
        const err = new Error('Another refresh for this dataset is already running.');
        err.throttled = true; err.serverLock = e.detail || e;
        throw err;
      }
      throw new Error(e.detail || 'Refresh failed');
    }
    return res.json();
  }, { minIntervalMs: 3000 });
  if (!gate.ok) {
    const e = new Error(`Throttled: ${gate.reason}. Please wait a moment.`);
    e.throttled = true; e.reason = gate.reason;
    throw e;
  }
  return gate.result;
}

export async function removeLiveTracking(strategyId) {
  const res = await fetch(`${API_URL}/api/live/${strategyId}`, { method: 'DELETE' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Remove failed'); }
  return res.json();
}

// ──────────────────────────────────────────────────────────────────────────
// Data coverage (per-source) + auto-maintenance
// ──────────────────────────────────────────────────────────────────────────

export async function getDataCoverage(symbol, source = 'bid_1m', timeframe) {
  const qs = new URLSearchParams({ symbol, source });
  if (timeframe) qs.set('timeframe', timeframe);
  const res = await fetch(`${API_URL}/api/data-coverage?${qs.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch coverage');
  }
  return res.json();
}

export async function getAutoMaintenanceStatus() {
  const res = await fetch(`${API_URL}/api/auto-maintenance/status`);
  if (!res.ok) throw new Error('Failed to fetch auto-maintenance status');
  return res.json();
}

export async function toggleAutoMaintenance(enabled) {
  const res = await fetch(`${API_URL}/api/auto-maintenance/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to toggle auto-maintenance');
  }
  return res.json();
}

export async function runAutoMaintenanceNow() {
  const res = await fetch(`${API_URL}/api/auto-maintenance/run-now`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to run maintenance');
  }
  return res.json();
}

// ── Phase 2 — Prop Firm Config System ────────────────────────────────

export async function listPropFirms() {
  const res = await fetch(`${API_URL}/api/prop-firms/list`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to list prop firms');
  }
  return res.json();
}

export async function listChallengeFirms() {
  const res = await fetch(`${API_URL}/api/challenge-firms`);
  if (!res.ok) throw new Error('Failed to list challenge firms');
  return res.json();
}

export async function extractPropFirm({ firm_name, challenge_size, website_url, pdf }) {
  const fd = new FormData();
  fd.append('firm_name', firm_name);
  fd.append('challenge_size', String(challenge_size));
  if (website_url) fd.append('website_url', website_url);
  if (pdf) fd.append('pdf', pdf);
  const res = await fetch(`${API_URL}/api/prop-firms/extract`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Extraction failed');
  }
  return res.json();
}

export async function savePropFirm(payload) {
  const res = await fetch(`${API_URL}/api/prop-firms/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Save failed');
  }
  return res.json();
}

export async function deletePropFirm(firmSlug) {
  const res = await fetch(`${API_URL}/api/prop-firms/${encodeURIComponent(firmSlug)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Delete failed');
  }
  return res.json();
}

// ── Phase 3 — Prop Firm Intelligence Layer ───────────────────────────

export async function discoverChallenges({ firm_name, website_url, pdf }) {
  const fd = new FormData();
  fd.append('firm_name', firm_name);
  if (website_url) fd.append('website_url', website_url);
  if (pdf) fd.append('pdf', pdf);
  const res = await fetch(`${API_URL}/api/prop-firms/discover-challenges`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Discovery failed');
  }
  return res.json();
}

export async function saveChallenges(payload) {
  const res = await fetch(`${API_URL}/api/prop-firms/save-challenges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Save challenges failed');
  }
  return res.json();
}

export async function listFirmIntelligence() {
  const res = await fetch(`${API_URL}/api/prop-firms/intelligence/list`);
  if (!res.ok) throw new Error('Failed to list intelligence');
  return res.json();
}

export async function deleteFirmIntelligence(firmSlug) {
  const res = await fetch(`${API_URL}/api/prop-firms/intelligence/${encodeURIComponent(firmSlug)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Delete failed');
  }
  return res.json();
}


// ═══ Phase 4 — Strategy ↔ Prop Firm Matching ═══════════════════════════
/**
 * Call the Phase-4 matcher. Accepts any ONE of:
 *   - { strategyId }                          — loads trades from DB
 *   - { trades, initialBalance }              — raw trade list
 *   - { strategyText, pair, timeframe }       — ad-hoc backtest first
 * Returns { matching: { ranked_matches, rejected, profile_summary, ... } }.
 *
 * Tries /api/phase4/match-firms first; on 404/502/504 falls back to the
 * allow-listed piggy-back route /api/match-firms-phase4.
 */
export async function matchFirmsPhase4({
  strategyId,
  trades,
  strategyText,
  pair,
  timeframe,
  initialBalance = 10000,
  nSimulations = 30,
  relaxedMode = false,
} = {}) {
  const body = {
    initial_balance: initialBalance,
    n_simulations: nSimulations,
    relaxed_mode: !!relaxedMode,
  };
  if (strategyId) body.strategy_id = strategyId;
  if (trades) body.strategy_trades = trades;
  if (strategyText) {
    body.strategy_text = strategyText;
    body.pair = pair;
    body.timeframe = timeframe;
  }

  const paths = ['/api/match-firms-phase4', '/api/phase4/match-firms'];
  let lastErr = null;
  for (const path of paths) {
    try {
      const res = await fetch(`${API_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) return res.json();
      if ([404, 502, 503, 504].includes(res.status)) {
        lastErr = new Error(`Firm match failed (HTTP ${res.status})`);
        continue; // try next path
      }
      const err = await res.json().catch(() => ({}));
      // Phase 19 — backend may return detail as a string OR an object
      // {reason, diagnostics}. Surface the reason string + 422 hint.
      let msg;
      if (err && typeof err.detail === 'string') {
        msg = err.detail;
      } else if (err && err.detail && typeof err.detail === 'object') {
        msg = err.detail.reason || JSON.stringify(err.detail);
      } else if (Array.isArray(err?.detail) && err.detail[0]?.msg) {
        msg = err.detail.map((d) => d.msg).join('; ');
      } else {
        msg = `Firm match failed (HTTP ${res.status})`;
      }
      const error = new Error(msg);
      error.diagnostics = err?.detail?.diagnostics || null;
      error.status = res.status;
      throw error;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('Firm match failed');
}



// ── Phase 14.4 — Pipeline Logs ──────────────────────────────────────

export async function getPipelineLogs({ limit = 100, run_id, stage, level } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (run_id) params.set('run_id', run_id);
  if (stage)  params.set('stage', stage);
  if (level)  params.set('level', level);
  const res = await fetch(`${API_URL}/api/logs?${params.toString()}`);
  if (!res.ok) throw new Error(`Pipeline logs fetch failed (HTTP ${res.status})`);
  return res.json();
}


// ── Phase 16 — Mutation (additive; calls existing /api/mutation/mutate) ──
export async function mutateStrategy({ strategy_text, pair, timeframe, style, max_variants = 5 }) {
  const res = await fetch(`${API_URL}/api/mutation/mutate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      strategy_text, pair, timeframe, style: style || null, max_variants,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Mutation failed (HTTP ${res.status})`);
  }
  return res.json();
}

// ── Strategy Description (additive, read-only enrichment) ──
export async function describeStrategy({ strategy_text, pair, timeframe, style, backtest, force = false }) {
  const res = await fetch(`${API_URL}/api/strategy/describe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_text, pair, timeframe, style, backtest, force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Describe failed (HTTP ${res.status})`);
  }
  return res.json();
}


// ─────────────────────────────────────────────────────────────────────
// Strategy Memory + Explorer (Phase 16)
// ─────────────────────────────────────────────────────────────────────

export async function getExplorer(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    q.append(k, String(v));
  });
  const res = await fetch(`${API_URL}/api/strategies/explorer?${q.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Explorer fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getStrategyHistory(strategyHash, limit = 500) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/history?limit=${limit}`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `History fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function reRunStrategyByHash(strategyHash, { max_variants = 10, auto_save = true, firm = 'ftmo' } = {}) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/re-run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_variants, auto_save, firm }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Re-run failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function exportStrategyByHash(strategyHash) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/export`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Export failed (HTTP ${res.status})`);
  }
  return res.json();
}

// Phase 24 — Strategy Explorer details drawer (cached only, no recompute).
export async function getStrategyDetails(strategyId) {
  const res = await fetch(
    `${API_URL}/api/strategies/library/${encodeURIComponent(strategyId)}/details`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Details failed (HTTP ${res.status})`);
  }
  return res.json();
}

// Phase 26 / G1 — Research lineage queries.
export async function getResearchRunsForStrategy(strategyHash, { limit = 10 } = {}) {
  const res = await fetch(
    `${API_URL}/api/research-runs/by-strategy/${encodeURIComponent(strategyHash)}?limit=${limit}`,
  );
  if (!res.ok) return { count: 0, runs: [] };
  return res.json();
}

export async function getResearchRun(researchRunId) {
  const res = await fetch(
    `${API_URL}/api/research-runs/${encodeURIComponent(researchRunId)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export async function listResearchRuns({ limit = 50, triggerType, status } = {}) {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (triggerType) qs.set('trigger_type', triggerType);
  if (status) qs.set('status', status);
  const res = await fetch(`${API_URL}/api/research-runs?${qs.toString()}`);
  if (!res.ok) return { count: 0, runs: [] };
  return res.json();
}

export async function downloadStrategyCbotByHash(strategyHash, name) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/export/cbot`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `cBot export failed (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const safeName = (name || 'Strategy').replace(/[^A-Za-z0-9_-]+/g, '_');
  a.href = url;
  a.download = `${safeName}_${strategyHash.slice(0, 8)}.cs`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return true;
}

export async function toggleStrategyFavorite(strategyHash, isFavorite) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/favorite`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_favorite: !!isFavorite }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Favorite failed (HTTP ${res.status})`);
  }
  return res.json();
}


// ─────────────────────────────────────────────────────────────────────
// Strategy Market Intelligence (Phase 17)
// ─────────────────────────────────────────────────────────────────────

export async function scanStrategyMarket(strategyHash, { pairs, timeframes, force = false } = {}) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/market-scan`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pairs, timeframes, force }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Market scan failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getStrategyMarketProfile(strategyHash) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/market-profile`,
  );
  if (!res.ok) {
    if (res.status === 404) return null;
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Profile fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function scanMarketEligible({ limit = 3, pairs, timeframes, force = false } = {}) {
  const res = await fetch(`${API_URL}/api/market-intelligence/scan-eligible`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit, pairs, timeframes, force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Eligible scan failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getMarketIntelligenceRankings(limit = 100) {
  const res = await fetch(`${API_URL}/api/market-intelligence/rankings?limit=${limit}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Rankings fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getMarketIntelligenceConfig() {
  const res = await fetch(`${API_URL}/api/market-intelligence/config`);
  if (!res.ok) throw new Error(`Config fetch failed (HTTP ${res.status})`);
  return res.json();
}


// ─────────────────────────────────────────────────────────────────────
// Prop Firm Rule Engine + Challenge Simulator (Phase 18)
// ─────────────────────────────────────────────────────────────────────

export async function listPropFirmRules() {
  const res = await fetch(`${API_URL}/api/prop-firm-analysis/rules`);
  if (!res.ok) throw new Error(`Rules fetch failed (HTTP ${res.status})`);
  return res.json();
}

export async function analyzeStrategyProp(strategyHash, firmSlug = 'ftmo') {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/prop-analysis`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ firm_slug: firmSlug }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Prop analysis failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getStrategyPropAnalysis(strategyHash, firmSlug = 'ftmo') {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/prop-analysis?firm_slug=${firmSlug}`,
  );
  if (!res.ok) {
    if (res.status === 404) return null;
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Prop analysis fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function batchAnalyzeProp({ firm_slug = 'ftmo', limit = 50, min_runs = 1, force = false } = {}) {
  const res = await fetch(`${API_URL}/api/prop-firm-analysis/batch-analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firm_slug, limit, min_runs, force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Batch prop analysis failed (HTTP ${res.status})`);
  }
  return res.json();
}


// ─────────────────────────────────────────────────────────────────────
// Challenge Type Matching (Phase 2)
// ─────────────────────────────────────────────────────────────────────

export async function listChallengeTypesByFirm() {
  const res = await fetch(`${API_URL}/api/challenge-matching/challenge-types/by-firm`);
  if (!res.ok) throw new Error(`Challenge types fetch failed (HTTP ${res.status})`);
  return res.json();
}

export async function matchStrategyChallenges(strategyHash, force = false) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/match-challenges`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Match failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getStrategyChallengeMatch(strategyHash) {
  const res = await fetch(
    `${API_URL}/api/strategies/${encodeURIComponent(strategyHash)}/challenge-match`,
  );
  if (!res.ok) {
    if (res.status === 404) return null;
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Match fetch failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function runEligibleChallengeMatch({ limit = 3, force = false } = {}) {
  const res = await fetch(`${API_URL}/api/challenge-matching/run-eligible`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit, force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Batch match failed (HTTP ${res.status})`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────
// Prop Firm Rules Review & Approval (Phase 20)
// ─────────────────────────────────────────────────────────────────────

export async function listPropFirmReviewRules() {
  const res = await fetch(`${API_URL}/api/prop-firm-rules`);
  if (!res.ok) throw new Error(`List failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPropFirmReviewRule(firmSlug) {
  const res = await fetch(`${API_URL}/api/prop-firm-rules/${encodeURIComponent(firmSlug)}`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`Get failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function approvePropFirmRules(firmSlug, approvedRules) {
  const res = await fetch(
    `${API_URL}/api/prop-firm-rules/${encodeURIComponent(firmSlug)}/approve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved_rules: approvedRules }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Approve failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function rejectPropFirmRules(firmSlug) {
  const res = await fetch(
    `${API_URL}/api/prop-firm-rules/${encodeURIComponent(firmSlug)}/reject`,
    { method: 'POST' },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Reject failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function resetPropFirmRules(firmSlug) {
  const res = await fetch(
    `${API_URL}/api/prop-firm-rules/${encodeURIComponent(firmSlug)}/reset`,
    { method: 'POST' },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Reset failed (HTTP ${res.status})`);
  }
  return res.json();
}



// ─────────────────────────────────────────────────────────────────────
// Auto Selection (Phase 3)
// ─────────────────────────────────────────────────────────────────────

export async function runAutoSelection(filters = {}) {
  const res = await fetch(`${API_URL}/api/auto-select/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Auto-select failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getAutoSelectionRecent(limit = 10) {
  const res = await fetch(`${API_URL}/api/auto-select/recent?limit=${limit}`);
  if (!res.ok) throw new Error(`Recent fetch failed (HTTP ${res.status})`);
  return res.json();
}

export async function getAutoSelectionConfig() {
  const res = await fetch(`${API_URL}/api/auto-select/config`);
  if (!res.ok) throw new Error(`Config fetch failed (HTTP ${res.status})`);
  return res.json();
}



// ─────────────────────────────────────────────────────────────────────
// Portfolio Builder (Phase 4)
// ─────────────────────────────────────────────────────────────────────

export async function buildPortfolioBuilder(filters = {}) {
  const res = await fetch(`${API_URL}/api/portfolio-builder/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Portfolio build failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function savePortfolioBuilder(portfolio) {
  const res = await fetch(`${API_URL}/api/portfolio-builder/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(portfolio),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Portfolio save failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getPortfolioBuilderRecent(limit = 10) {
  const res = await fetch(`${API_URL}/api/portfolio-builder/recent?limit=${limit}`);
  if (!res.ok) throw new Error(`Recent portfolios failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPortfolioBuilderConfig() {
  const res = await fetch(`${API_URL}/api/portfolio-builder/config`);
  if (!res.ok) throw new Error(`Portfolio config failed (HTTP ${res.status})`);
  return res.json();
}


// ─────────────────────────────────────────────────────────────────────
// Trade Runner (Phase 5 — paper execution)
// ─────────────────────────────────────────────────────────────────────

export async function startTradeRunner(payload = {}) {
  const res = await fetch(`${API_URL}/api/trade-runner/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Start failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function stepTradeRunner(runId, steps = 1) {
  const res = await fetch(`${API_URL}/api/trade-runner/step/${runId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ steps }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Step failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function stopTradeRunner(runId) {
  const res = await fetch(`${API_URL}/api/trade-runner/stop/${runId}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Stop failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getTradeRunnerStatus(runId, tradeLimit = 25) {
  const res = await fetch(
    `${API_URL}/api/trade-runner/status/${runId}?trade_limit=${tradeLimit}`,
  );
  if (!res.ok) throw new Error(`Status failed (HTTP ${res.status})`);
  return res.json();
}

export async function listTradeRunnerRuns(limit = 10) {
  const res = await fetch(`${API_URL}/api/trade-runner/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`List runs failed (HTTP ${res.status})`);
  return res.json();
}



// ─────────────────────────────────────────────────────────────────────
// Phase 5.2 — Data Maintenance & Backup
// ─────────────────────────────────────────────────────────────────────

export async function getDataMaintenanceStatus() {
  const res = await fetch(`${API_URL}/api/data/maintenance/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Status failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function toggleDataMaintenance(enabled) {
  const res = await fetch(`${API_URL}/api/data/maintenance/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Toggle failed');
  }
  return res.json();
}

export async function runDataMaintenance(payload = {}) {
  const res = await fetch(`${API_URL}/api/data/maintenance/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Run failed');
  }
  return res.json();
}

export async function getDataMaintenanceConfig() {
  const res = await fetch(`${API_URL}/api/data/maintenance/config`);
  if (!res.ok) throw new Error(`Config failed (HTTP ${res.status})`);
  return res.json();
}

export async function saveDataMaintenanceConfig(payload) {
  const res = await fetch(`${API_URL}/api/data/maintenance/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Save config failed');
  }
  return res.json();
}

export async function getDataMaintenanceCoverage() {
  const res = await fetch(`${API_URL}/api/data/maintenance/coverage`);
  if (!res.ok) throw new Error(`Coverage failed (HTTP ${res.status})`);
  return res.json();
}

export async function backfillDataMaintenance(payload = {}) {
  const res = await fetch(`${API_URL}/api/data/maintenance/backfill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Backfill failed (HTTP ${res.status})`);
  }
  return res.json();
}

export function dataExportAllUrl() {
  return `${API_URL}/api/data/backup/export-all`;
}

export function dataExportSingleUrl({ symbol, timeframe = '1h', source = 'bid_1m' }) {
  const qs = new URLSearchParams({ symbol, timeframe, source });
  return `${API_URL}/api/data/backup/export?${qs.toString()}`;
}

export async function importDataBackup(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`${API_URL}/api/data/backup/import`, {
    method: 'POST',
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Import failed');
  }
  return res.json();
}


// ─── Market-Data Export (POST /api/data/export — streamed ZIP) ─────────
//
// Builds a portable ZIP of every BID + BI5 dataset plus a rich manifest
// (`market_data_manifest.json`). The blob is downloaded directly to the
// user's machine so they can import it into another Emergent account via
// the existing "Import ZIP" workflow.
//
// Returns: { filename, totalRows, totalDatasets }
export async function exportMarketData(payload = {}) {
  const res = await fetch(`${API_URL}/api/data/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    let detail = `Export failed (HTTP ${res.status})`;
    try {
      const err = await res.json();
      if (err && err.detail) detail = err.detail;
    } catch (_) { /* non-JSON body */ }
    throw new Error(detail);
  }

  const blob = await res.blob();
  const headerFilename = res.headers.get('X-Export-Filename');
  const cd = res.headers.get('Content-Disposition') || '';
  const cdMatch = cd.match(/filename="?([^";]+)"?/i);
  const filename = headerFilename || (cdMatch && cdMatch[1])
    || `market_data_export_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);

  return {
    filename,
    totalRows: Number(res.headers.get('X-Export-Total-Rows') || 0),
    totalDatasets: Number(res.headers.get('X-Export-Total-Datasets') || 0),
  };
}


// ─── Phase 7 — Portfolio Intelligence Upgrade ────────────────────────
export async function buildPortfolioIntelligence(config = {}) {
  const res = await fetch(`${API_URL}/api/portfolio-intelligence/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Portfolio intelligence build failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getPortfolioIntelligenceCurrent() {
  const res = await fetch(`${API_URL}/api/portfolio-intelligence/current`);
  if (!res.ok) throw new Error(`Current portfolio failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPortfolioIntelligenceHistory(limit = 20) {
  const res = await fetch(`${API_URL}/api/portfolio-intelligence/history?limit=${limit}`);
  if (!res.ok) throw new Error(`Portfolio history failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPortfolioIntelligenceDefaults() {
  const res = await fetch(`${API_URL}/api/portfolio-intelligence/config`);
  if (!res.ok) throw new Error(`Portfolio config failed (HTTP ${res.status})`);
  return res.json();
}

// ─── Phase 8 — Optimization (Strategy Refinement) ────────────────────
export async function runOptimization(config = {}) {
  const res = await fetch(`${API_URL}/api/optimization/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Optimization failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getOptimizationHistory(limit = 20) {
  const res = await fetch(`${API_URL}/api/optimization/history?limit=${limit}`);
  if (!res.ok) throw new Error(`History failed (HTTP ${res.status})`);
  return res.json();
}

export async function getOptimizationBest(limit = 10) {
  const res = await fetch(`${API_URL}/api/optimization/best?limit=${limit}`);
  if (!res.ok) throw new Error(`Best failed (HTTP ${res.status})`);
  return res.json();
}

export async function getOptimizationConfig() {
  const res = await fetch(`${API_URL}/api/optimization/config`);
  if (!res.ok) throw new Error(`Config failed (HTTP ${res.status})`);
  return res.json();
}

export async function getOptimizationPortfolioActions(limit = 20) {
  const res = await fetch(`${API_URL}/api/optimization/portfolio-actions?limit=${limit}`);
  if (!res.ok) throw new Error(`Actions failed (HTTP ${res.status})`);
  return res.json();
}

// ═══════════════════════════════════════════════════════════════════
// Paper Execution (Safe historical-replay)
// ═══════════════════════════════════════════════════════════════════

export async function startPaperExecution(payload) {
  const res = await fetch(`${API_URL}/api/execution/paper/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Start failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function stopPaperExecution(runId) {
  const res = await fetch(`${API_URL}/api/execution/paper/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Stop failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function getPaperExecutionStatus(runId, tradeLimit = 25) {
  const qs = new URLSearchParams();
  if (runId) qs.set('run_id', runId);
  qs.set('trade_limit', String(tradeLimit));
  const res = await fetch(`${API_URL}/api/execution/paper/status?${qs}`);
  if (!res.ok) throw new Error(`Status failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPaperExecutionTrades(runId, limit = 100) {
  const qs = new URLSearchParams();
  if (runId) qs.set('run_id', runId);
  qs.set('limit', String(limit));
  const res = await fetch(`${API_URL}/api/execution/paper/trades?${qs}`);
  if (!res.ok) throw new Error(`Trades failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPaperExecutionEquity(runId, limit = 1000) {
  const res = await fetch(
    `${API_URL}/api/execution/paper/equity?run_id=${encodeURIComponent(runId)}&limit=${limit}`,
  );
  if (!res.ok) throw new Error(`Equity failed (HTTP ${res.status})`);
  return res.json();
}

export async function listPaperExecutionRuns(limit = 10) {
  const res = await fetch(`${API_URL}/api/execution/paper/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`Runs failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPaperDeviationHistory(strategyHash, limit = 100) {
  const res = await fetch(
    `${API_URL}/api/execution/paper/deviation/${encodeURIComponent(strategyHash)}?limit=${limit}`,
  );
  if (!res.ok) throw new Error(`Deviation failed (HTTP ${res.status})`);
  return res.json();
}

export async function getPaperExecutionConfig() {
  const res = await fetch(`${API_URL}/api/execution/paper/config`);
  if (!res.ok) throw new Error(`Config failed (HTTP ${res.status})`);
  return res.json();
}


// ── Master Bot (MB-1 + MB-2 + MB-3) ─────────────────────────────────
async function _json(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export async function listMasterBots({ includeDeleted = false, limit = 100 } = {}) {
  const qs = new URLSearchParams();
  if (includeDeleted) qs.set('include_deleted', 'true');
  qs.set('limit', String(limit));
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot?${qs}`, {}, STD));
}

export async function createMasterBot({ name, description }) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description: description || '' }),
  }, STD));
}

export async function getMasterBot(id) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/${encodeURIComponent(id)}`, {}, STD));
}

export async function renameMasterBot(id, { name, description }) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/${encodeURIComponent(id)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  }, STD));
}

export async function deleteMasterBot(id, { hard = false } = {}) {
  const qs = hard ? '?hard=true' : '';
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/${encodeURIComponent(id)}${qs}`, {
    method: 'DELETE',
  }, STD));
}

export async function getMasterBotCandidates(limit = 30) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/candidates?limit=${limit}`, {}, STD));
}

export async function getMasterBotRankerConfig() {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/ranker/config`, {}, STD));
}

export async function setMasterBotRankerConfig(weights) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/ranker/config`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(weights || {}),
  }, STD));
}

export async function addMasterBotMember(id, body) {
  return _json(await fetchWithTimeout(`${API_URL}/api/master-bot/${encodeURIComponent(id)}/members`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }, STD));
}

export async function removeMasterBotMember(id, hash) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/members/${encodeURIComponent(hash)}`,
    { method: 'DELETE' }, STD,
  ));
}

export async function setMasterBotMemberEnabled(id, hash, enabled) {
  const action = enabled ? 'enable' : 'disable';
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/members/${encodeURIComponent(hash)}/${action}`,
    { method: 'POST' }, STD,
  ));
}

export async function promoteMasterBotMember(id, hash) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/members/${encodeURIComponent(hash)}/promote`,
    { method: 'POST' }, STD,
  ));
}

export async function demoteMasterBotMember(id, hash) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/members/${encodeURIComponent(hash)}/demote`,
    { method: 'POST' }, STD,
  ));
}

export async function moveMasterBotMemberToTier(id, hash, tier) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/members/${encodeURIComponent(hash)}/move-to`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }) }, STD,
  ));
}

export async function reorderMasterBotTier(id, tier, orderedHashes) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/tiers/${encodeURIComponent(tier)}/reorder`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ordered_hashes: orderedHashes || [] }) }, STD,
  ));
}

export async function autoFillMasterBot(id, body) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/auto-fill`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }, LONG,
  ));
}



// ── Master Bot — MB-4 / MB-7 / MB-8 / Diff ─────────────────────────
export async function compileMasterBot(id, body) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/compile`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }, LONG,
  ));
}

export async function listMasterBotDefinitions(id, limit = 50) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/definitions?limit=${limit}`,
    {}, STD,
  ));
}

export async function getMasterBotDefinitionLatest(id) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/definitions/latest`,
    {}, STD,
  ));
}

export async function getMasterBotDefinitionByRev(id, rev) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/definitions/${encodeURIComponent(rev)}`,
    {}, STD,
  ));
}

export async function exportMasterBotCs(id, body) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/export`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }, LONG,
  ));
}

export async function listMasterBotExports(id, limit = 50) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/exports?limit=${limit}`,
    {}, STD,
  ));
}

export function downloadMasterBotExportUrl(exportId, kind = 'cs') {
  return `${API_URL}/api/master-bot/exports/${encodeURIComponent(exportId)}/download/${encodeURIComponent(kind)}`;
}

export async function buildMasterBotPack(id, body) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/pack`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }, LONG,
  ));
}

export async function listMasterBotPacks(id, limit = 50) {
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/packs?limit=${limit}`,
    {}, STD,
  ));
}

export function downloadMasterBotPackUrl(packId) {
  return `${API_URL}/api/master-bot/packs/${encodeURIComponent(packId)}/download`;
}

export async function diffMasterBotRevisions(id, { fromRev, toRev } = {}) {
  const qs = new URLSearchParams();
  if (fromRev !== undefined && fromRev !== null) qs.set('from_rev', String(fromRev));
  if (toRev   !== undefined && toRev   !== null) qs.set('to_rev',   String(toRev));
  return _json(await fetchWithTimeout(
    `${API_URL}/api/master-bot/${encodeURIComponent(id)}/diff?${qs}`,
    {}, STD,
  ));
}
