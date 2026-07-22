/*
 * strategyLabAdapter — Sprint 3 Phase-2 live adapter for Strategy Lab.
 * refs Backend Feature Freeze v1.1.0-stage4 · app.api.strategies · knowledge.router
 *
 *   generateStrategy({ pair, timeframe, style })
 *     → POST /api/strategies/generate       — returns compressed CNL text
 *   saveStrategyDraft({ name, description, symbol, timeframe, tags })
 *     → POST /api/strategies (status=draft) — persisted with lineage
 *   listStrategies({ status })
 *     → GET  /api/strategies                — safety-repo filtered
 *   findNearestStrategies({ strategy_text, pair, timeframe, top_k })
 *     → POST /api/knowledge/nearest         — rule-based similarity
 *
 * No writes ever bypass an authenticated live call. If the endpoint is
 * gated (503) or the caller lacks the role, the adapter returns a
 * liveness verdict + reason string so the surface can render an
 * operator-legible interstitial without ever inventing data.
 */
import { isLiveMode, apiFetch } from './apiClient';

const wrap = async (path, opts, empty) => {
  if (!isLiveMode()) {
    return { liveness: 'gated', reason: 'REACT_APP_BACKEND_URL not configured', payload: empty };
  }
  try {
    const payload = await apiFetch(path, opts);
    return { liveness: 'live', reason: null, payload };
  } catch (err) {
    if (err.status === 503) return { liveness: 'gated',   reason: 'endpoint gated under Backend Feature Freeze v1.1.0-stage4', payload: empty };
    if (err.status === 401) return { liveness: 'error',   reason: 'unauthorized · sign in required', payload: empty };
    if (err.status === 403) return { liveness: 'gated',   reason: 'role insufficient', payload: empty };
    if (err.status === 404) return { liveness: 'partial', reason: 'not found', payload: empty };
    return { liveness: 'error', reason: err.message || 'network error', payload: empty };
  }
};

export const generateStrategy = async ({ pair, timeframe, style } = {}) => {
  return wrap('/api/strategies/generate', {
    method: 'POST',
    body: JSON.stringify({ pair, timeframe, style: style || '' }),
  }, { strategy: '' });
};

export const saveStrategyDraft = async ({ name, description, symbol, timeframe, tags = [] } = {}) => {
  return wrap('/api/strategies', {
    method: 'POST',
    body: JSON.stringify({ name, description, symbol, timeframe, tags }),
  }, null);
};

export const listStrategies = async () => {
  const res = await wrap('/api/strategies', { method: 'GET' }, []);
  const payload = Array.isArray(res.payload) ? res.payload : [];
  return { ...res, payload };
};

export const findNearestStrategies = async ({ strategy_text, pair, timeframe, top_k = 5 } = {}) => {
  return wrap('/api/knowledge/nearest', {
    method: 'POST',
    body: JSON.stringify({ strategy_text, pair, timeframe, top_k }),
  }, { matches: [], total_corpus: 0, guardrails: { learning_only: true, eligible_for_deploy: false } });
};

/** KB corpus statistics — powers pipeline aggregate counters + Strategy Lab hint chip. */
export const fetchKnowledgeStatistics = async () => {
  return wrap('/api/knowledge/statistics', { method: 'GET' }, { total_strategies: 0, canonical_families: 0 });
};

export const fetchKnowledgeChampions = async () => {
  return wrap('/api/knowledge/champions', { method: 'GET' }, { categories: {} });
};
