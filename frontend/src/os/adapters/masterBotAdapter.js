/*
 * Master Bot adapter — Sprint 2 N2.
 * refs SPRINT_2_PLANNING.md §2 N2 · Design Freeze §1.4 (D4)
 *
 * Endpoints (expected, not yet exposed under v1.1.0-stage4):
 *   GET /api/master-bot/identity      → identity strip
 *   GET /api/master-bot/current-plan  → current plan card
 *   GET /api/master-bot/decisions     → last N decisions
 *
 * All three fixtures fall back via `unavailableBreadcrumb` per the same
 * pattern established for factoryAdapter · timelineAdapter · approvalsAdapter.
 * When backend activation lands, the adapter is the single seam that swaps
 * to live traffic without any surface-side change.
 */
import { isLiveMode, apiFetch, unavailableBreadcrumb } from './apiClient';
import { MASTER_BOT_FIXTURE } from './fixtures';

const attemptLive = async (path) => {
  if (!isLiveMode()) throw new Error('fixture-mode');
  return apiFetch(path);
};

export const fetchIdentity = async () => {
  try {
    return await attemptLive('/api/master-bot/identity');
  } catch (e) {
    unavailableBreadcrumb('fetchIdentity', 'GET /api/master-bot/identity',
      'Master Bot router not exposed in v1.1.0-stage4');
    return MASTER_BOT_FIXTURE.identity;
  }
};

export const fetchCurrentPlan = async () => {
  try {
    return await attemptLive('/api/master-bot/current-plan');
  } catch (e) {
    unavailableBreadcrumb('fetchCurrentPlan', 'GET /api/master-bot/current-plan',
      'Master Bot router not exposed in v1.1.0-stage4');
    return MASTER_BOT_FIXTURE.currentPlan;
  }
};

export const fetchDecisions = async ({ limit = 5 } = {}) => {
  try {
    const raw = await attemptLive(`/api/master-bot/decisions?limit=${limit}`);
    return Array.isArray(raw) ? raw : MASTER_BOT_FIXTURE.lastDecisions.slice(0, limit);
  } catch (e) {
    unavailableBreadcrumb('fetchDecisions', 'GET /api/master-bot/decisions',
      'Master Bot router not exposed in v1.1.0-stage4');
    return MASTER_BOT_FIXTURE.lastDecisions.slice(0, limit);
  }
};

export const aggregateMasterBot = async () => {
  const [identity, currentPlan, decisions] = await Promise.all([
    fetchIdentity(),
    fetchCurrentPlan(),
    fetchDecisions({ limit: 5 }),
  ]);
  return { identity, currentPlan, decisions };
};
