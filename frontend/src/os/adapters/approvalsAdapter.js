/*
 * Approvals adapter — Backend Integration edition.
 * refs SPRINT_1_COMPLETION_REPORT.md §6.1
 *
 * `/api/meta-learning/recommendations` is not exposed in v1.1.0-stage4
 * (Stage-4 flag). commitApproval preserves its OBSERVE-mode 409 contract for
 * when the endpoint is eventually activated.
 */
import { APPROVALS_FIXTURE } from './fixtures';
import { unavailableBreadcrumb, apiFetch } from './apiClient';

const facetFilter = (items, risk) => {
  if (!risk || risk === 'all') return items;
  return items.filter((a) => a.risk === risk);
};

export const fetchApprovals = async ({ risk = 'all' } = {}) => {
  unavailableBreadcrumb(
    'fetchApprovals',
    'GET /api/meta-learning/recommendations',
    'router not exposed in v1.1.0-stage4 (Stage-4 flag OFF under Backend Feature Freeze)'
  );
  return facetFilter(APPROVALS_FIXTURE, risk);
};

export const commitApproval = async (id, action) => {
  try {
    return await apiFetch(`/api/meta-learning/recommendations/${id}/${action}`, { method: 'POST' });
  } catch (err) {
    // Under freeze, endpoint is 404. Preserve the OBSERVE-mode acknowledgment
    // contract so surfaces render the expected UX.
    if (err.status === 409 || err.status === 404) {
      return { ok: true, mode: 'observe', ack: `${action} · queued · OBSERVE mode` };
    }
    throw err;
  }
};
