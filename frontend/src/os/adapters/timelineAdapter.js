/*
 * Timeline adapter — Backend Integration edition.
 * refs SPRINT_1_COMPLETION_REPORT.md §6.1
 *
 * Expected `/api/llm-calls` does not exist in v1.1.0-stage4. `/api/research/history`
 * is a partial substitute (research plan events only), not a general activity
 * feed. Per operator directive, adapters stay in fixture mode when there is
 * no true equivalent — emit a breadcrumb.
 */
import { TIMELINE_FIXTURE } from './fixtures';
import { unavailableBreadcrumb } from './apiClient';

const facetFilter = (events, actor) => {
  if (!actor || actor === 'all') return events;
  return events.filter((e) => e.actorKind === actor);
};

export const fetchTimeline = async ({ actor = 'all' } = {}) => {
  unavailableBreadcrumb(
    'fetchTimeline',
    'GET /api/llm-calls',
    'endpoint not exposed in v1.1.0-stage4; /api/research/history is only a partial substitute (research plans only)'
  );
  return facetFilter(TIMELINE_FIXTURE, actor);
};
