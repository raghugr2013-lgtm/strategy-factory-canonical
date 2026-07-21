/*
 * Factory adapter — F6.
 * Pipeline stages + worker roster + strategy inventory.
 */
import { fixtureOrLive } from './apiClient';
import { WORKERS_FIXTURE, PIPELINE_FIXTURE, STRATEGIES_FIXTURE } from './fixtures';

export const fetchWorkers = async () => {
  const data = await fixtureOrLive('/api/ai-workforce/workers', WORKERS_FIXTURE);
  return Array.isArray(data) ? data : WORKERS_FIXTURE;
};

export const fetchPipeline = async () => {
  const data = await fixtureOrLive('/api/coe/state', PIPELINE_FIXTURE);
  return Array.isArray(data) ? data : PIPELINE_FIXTURE;
};

export const fetchStrategies = async ({ status = 'all' } = {}) => {
  const data = await fixtureOrLive('/api/factory-eval/strategies', STRATEGIES_FIXTURE);
  const items = Array.isArray(data) ? data : STRATEGIES_FIXTURE;
  if (!status || status === 'all') return items;
  return items.filter((s) => s.status === status);
};
