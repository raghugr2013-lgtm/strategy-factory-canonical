/*
 * orchestratorAdapter — thin read-only wrapper around /api/orchestrator/*.
 * refs docs/FE_B_PROPOSAL.md §2 · Backend Feature Freeze v1.1.0-stage4.
 *
 * Every hook here consumes an endpoint that already exists on the backend
 * and is documented in docs/CAPABILITY_INVENTORY.md §C (Autonomous
 * Orchestration, v1.2.0-alpha2 Phase B.2). This adapter adds NO new API
 * surface, NO writes, NO fixture data. It is a straight, refresh-safe
 * projection of the orchestrator state onto React Query.
 */
import { useQuery } from '@tanstack/react-query';
import { apiFetch, isLiveMode } from './apiClient';

const REFRESH_MS = 15_000;      // 15 s polling — matches StatusRail cadence.
const HISTORY_LIMIT = 20;

const safeFetch = async (path) => {
  if (!isLiveMode()) return null;
  try {
    return await apiFetch(path);
  } catch {
    return null;
  }
};

export const useOrchestratorStatus = () => useQuery({
  queryKey: ['orchestrator', 'status'],
  queryFn: () => safeFetch('/api/orchestrator/status'),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
  staleTime: 5_000,
});

export const useOrchestratorDecisions = (limit = HISTORY_LIMIT) => useQuery({
  queryKey: ['orchestrator', 'decisions', limit],
  queryFn: () => safeFetch(`/api/orchestrator/decisions?limit=${limit}`),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
});

export const useOrchestratorHistory = (limit = HISTORY_LIMIT) => useQuery({
  queryKey: ['orchestrator', 'history', limit],
  queryFn: () => safeFetch(`/api/orchestrator/history?limit=${limit}`),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
});

/**
 * Cross-source health inputs used by the operator-focused summary panel.
 * Each source is optional — a missing endpoint degrades gracefully to
 * `null` and the panel renders a `deferred` signal state.
 */
export const useOrchestratorHealthInputs = () => {
  const provider = useQuery({
    queryKey: ['orchestrator', 'ai-workforce-health'],
    queryFn: () => safeFetch('/api/ai-workforce/health'),
    refetchInterval: REFRESH_MS,
  });
  const factoryEval = useQuery({
    queryKey: ['orchestrator', 'factory-eval-config'],
    queryFn: () => safeFetch('/api/factory-eval/config'),
    refetchInterval: REFRESH_MS,
  });
  const metaLearning = useQuery({
    queryKey: ['orchestrator', 'meta-learning-config'],
    queryFn: () => safeFetch('/api/meta-learning/config'),
    refetchInterval: REFRESH_MS,
  });
  return { provider: provider.data, factoryEval: factoryEval.data, metaLearning: metaLearning.data };
};
