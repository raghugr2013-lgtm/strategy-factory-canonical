/*
 * metaLearningAdapter — thin read-only wrapper around /api/meta-learning/*.
 * refs docs/FE_B_PROPOSAL.md · Backend Feature Freeze v1.1.0-stage4.
 *
 * All endpoints already exist under the backend Feature Freeze. This adapter
 * adds NO new API surface, NO writes, NO fixture data. It simply projects
 * meta-learning state onto React Query.
 */
import { useQuery } from '@tanstack/react-query';
import { apiFetch, isLiveMode } from './apiClient';

const REFRESH_MS = 15_000;
const LIMIT = 20;

const safeFetch = async (path) => {
  if (!isLiveMode()) return null;
  try {
    return await apiFetch(path);
  } catch {
    return null;
  }
};

export const useMetaLearningStatus = () => useQuery({
  queryKey: ['meta-learning', 'status'],
  queryFn: () => safeFetch('/api/meta-learning/status'),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
});

export const useMetaLearningConfig = () => useQuery({
  queryKey: ['meta-learning', 'config'],
  queryFn: () => safeFetch('/api/meta-learning/config'),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningHealth = () => useQuery({
  queryKey: ['meta-learning', 'health'],
  queryFn: () => safeFetch('/api/meta-learning/health'),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningEvaluations = (limit = LIMIT) => useQuery({
  queryKey: ['meta-learning', 'evaluations', limit],
  queryFn: () => safeFetch(`/api/meta-learning/evaluations?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningRecommendations = (limit = LIMIT) => useQuery({
  queryKey: ['meta-learning', 'recommendations', limit],
  queryFn: () => safeFetch(`/api/meta-learning/recommendations?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningPending = () => useQuery({
  queryKey: ['meta-learning', 'pending'],
  queryFn: () => safeFetch('/api/meta-learning/pending'),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningApplications = (limit = LIMIT) => useQuery({
  queryKey: ['meta-learning', 'applications', limit],
  queryFn: () => safeFetch(`/api/meta-learning/applications?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useMetaLearningOverrides = () => useQuery({
  queryKey: ['meta-learning', 'overrides'],
  queryFn: () => safeFetch('/api/meta-learning/overrides'),
  refetchInterval: REFRESH_MS,
});
