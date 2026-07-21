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
import { WORKERS_FIXTURE, PIPELINE_FIXTURE, STRATEGIES_FIXTURE } from './fixtures';

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

export const fetchPipeline = async () => {
  unavailableBreadcrumb('fetchPipeline', 'GET /api/coe/state', 'COE_GAMMA_ENABLED flag OFF under freeze');
  return PIPELINE_FIXTURE;
};
