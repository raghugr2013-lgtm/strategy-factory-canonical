/*
 * Timeline adapter — F4.
 * Facets: actor kind (from navigationStore.facets.actor).
 */
import { fixtureOrLive } from './apiClient';
import { TIMELINE_FIXTURE } from './fixtures';

const facetFilter = (events, actor) => {
  if (!actor || actor === 'all') return events;
  return events.filter((e) => e.actorKind === actor);
};

export const fetchTimeline = async ({ actor = 'all', window: _win = 'last-24h' } = {}) => {
  const all = await fixtureOrLive('/api/llm-calls?limit=50', TIMELINE_FIXTURE);
  // In live mode the shape may differ; fall back to fixture semantics if it does.
  const events = Array.isArray(all) ? all : TIMELINE_FIXTURE;
  return facetFilter(events, actor);
};
