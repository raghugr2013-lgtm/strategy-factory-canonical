/*
 * Factory adapter — Backend Integration edition.
 * refs SPRINT_1_COMPLETION_REPORT.md §6.1
 *
 * Remap decisions (adapter layer is the compatibility boundary):
 *   fetchStrategies   → GET /api/strategies (LIVE · v1.1.0-stage4 ships this)
 *                       Response transformation: StrategyOut → adapter shape.
 *   fetchWorkers      → NO EQUIVALENT · fixture only (breadcrumb).
 *   fetchPipeline     → /api/coe/state is 503 under freeze (COE_GAMMA_ENABLED
 *                       flag OFF) · fixture only (breadcrumb).
 */
import { isLiveMode, fixtureOrLive, unavailableBreadcrumb } from './apiClient';
import { WORKERS_FIXTURE, PIPELINE_FIXTURE, STRATEGIES_FIXTURE, STRATEGY_PASSPORT_FIXTURE, STRATEGY_PASSPORT_FALLBACK } from './fixtures';

// StrategyOut (backend) → Strategy Explorer row (frontend)
const transformStrategy = (s) => ({
  id: s.strategy_id ?? s.id,
  name: s.name,
  status: s.status ?? 'draft',
  // Sharpe / drawdown not present on StrategyOut — leave undefined; TableTile
  // renders `undefined.toFixed()` safely if we substitute.
  sharpe: typeof s.sharpe === 'number' ? s.sharpe : 0,
  drawdown: typeof s.drawdown === 'number' ? s.drawdown : 0,
});

export const fetchStrategies = async ({ status = 'all' } = {}) => {
  let items;
  if (isLiveMode()) {
    try {
      const raw = await (await import('./apiClient')).apiFetch('/api/strategies');
      items = Array.isArray(raw) ? raw.map(transformStrategy) : STRATEGIES_FIXTURE;
    } catch (e) {
      // 401 (no auth token yet) or network → transparent fixture fallback.
      if (e.status !== 401) {
        console.warn('[adapter] fetchStrategies live failed, falling back:', e.message);
      }
      items = STRATEGIES_FIXTURE;
    }
  } else {
    items = STRATEGIES_FIXTURE;
  }
  if (!status || status === 'all') return items;
  return items.filter((s) => s.status === status);
};

export const fetchWorkers = async () => {
  unavailableBreadcrumb('fetchWorkers', 'GET /api/ai-workforce/workers', 'router not exposed in v1.1.0-stage4');
  return WORKERS_FIXTURE;
};

// Sprint 2 N5 · Strategy Passport (D5).
// Tries live `GET /api/strategies/{id}` first. If backend serves a record
// we hydrate the passport shell with any missing fields from the fixture
// (backend does not yet surface guardrails / equity curve / lineage).
// Falls back to fixture-only or a generic shell when 404 / freeze.
const hydrate = (id, backendRow, fixture) => {
  const base = fixture || STRATEGY_PASSPORT_FALLBACK(id);
  if (!backendRow) return base;
  return {
    ...base,
    id: backendRow.strategy_id ?? backendRow.id ?? id,
    name: backendRow.name ?? base.name,
    status: backendRow.status ?? base.status,
    codeSha: backendRow.code_sha ?? base.codeSha,
    version: backendRow.version ?? base.version,
    ambition: backendRow.ambition ?? base.ambition,
    _source: 'live+hydrated',
  };
};

export const fetchStrategy = async (id) => {
  const fixture = STRATEGY_PASSPORT_FIXTURE[id];
  if (isLiveMode()) {
    try {
      const raw = await (await import('./apiClient')).apiFetch(`/api/strategies/${encodeURIComponent(id)}`);
      return hydrate(id, raw, fixture);
    } catch (e) {
      if (e.status !== 401 && e.status !== 404) {
        console.warn('[adapter] fetchStrategy live failed, falling back:', e.message);
      }
      if (e.status === 404) {
        unavailableBreadcrumb(`fetchStrategy:${id}`,
          `GET /api/strategies/${id}`,
          'strategy not present in backend store (freeze · unseeded db)');
      }
      return fixture ? { ...fixture, _source: 'fixture' } : STRATEGY_PASSPORT_FALLBACK(id);
    }
  }
  return fixture ? { ...fixture, _source: 'fixture' } : STRATEGY_PASSPORT_FALLBACK(id);
};

export const fetchPipeline = async () => {
  unavailableBreadcrumb('fetchPipeline', 'GET /api/coe/state', 'COE_GAMMA_ENABLED flag OFF under freeze');
  return PIPELINE_FIXTURE;
};
