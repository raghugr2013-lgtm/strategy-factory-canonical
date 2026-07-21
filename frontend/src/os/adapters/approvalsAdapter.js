/*
 * Approvals adapter — F5.
 * Facets: risk (from navigationStore.facets.risk).
 * Actions (Sprint 1 · OBSERVE mode): approve/defer/block return 409 in live
 * mode by design — the UI acknowledges the action optimistically and shows a
 * "queued · pending backend enablement" toast copy path when a 409 arrives.
 */
import { apiFetch, fixtureOrLive } from './apiClient';
import { APPROVALS_FIXTURE } from './fixtures';

const facetFilter = (items, risk) => {
  if (!risk || risk === 'all') return items;
  return items.filter((a) => a.risk === risk);
};

export const fetchApprovals = async ({ risk = 'all' } = {}) => {
  const all = await fixtureOrLive('/api/meta-learning/recommendations?limit=20', APPROVALS_FIXTURE);
  const items = Array.isArray(all) ? all : APPROVALS_FIXTURE;
  return facetFilter(items, risk);
};

export const commitApproval = async (id, action /* 'approve' | 'defer' | 'block' */) => {
  try {
    return await apiFetch(`/api/meta-learning/recommendations/${id}/${action}`, { method: 'POST' });
  } catch (err) {
    if (err.status === 409) {
      // OBSERVE-mode acknowledgment per Sprint 1 M3 spec
      return { ok: true, mode: 'observe', ack: `${action} · queued · OBSERVE mode` };
    }
    throw err;
  }
};
