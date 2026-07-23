/*
 * factoryEvalAdapter — thin read-only wrapper around /api/factory-eval/*.
 * refs docs/FE_B_PROPOSAL.md · Backend Feature Freeze v1.1.0-stage4.
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

export const useFactoryEvalStatus = () => useQuery({
  queryKey: ['factory-eval', 'status'],
  queryFn: () => safeFetch('/api/factory-eval/status'),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
});

export const useFactoryEvalConfig = () => useQuery({
  queryKey: ['factory-eval', 'config'],
  queryFn: () => safeFetch('/api/factory-eval/config'),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalHealth = () => useQuery({
  queryKey: ['factory-eval', 'health'],
  queryFn: () => safeFetch('/api/factory-eval/health'),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalKpis = () => useQuery({
  queryKey: ['factory-eval', 'kpis'],
  queryFn: () => safeFetch('/api/factory-eval/kpis'),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalLatestReport = () => useQuery({
  queryKey: ['factory-eval', 'reports', 'latest'],
  queryFn: () => safeFetch('/api/factory-eval/reports/latest'),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalReports = (limit = LIMIT) => useQuery({
  queryKey: ['factory-eval', 'reports', limit],
  queryFn: () => safeFetch(`/api/factory-eval/reports?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalInsights = (limit = LIMIT) => useQuery({
  queryKey: ['factory-eval', 'insights', limit],
  queryFn: () => safeFetch(`/api/factory-eval/insights?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalRecommendations = (limit = LIMIT) => useQuery({
  queryKey: ['factory-eval', 'recommendations', limit],
  queryFn: () => safeFetch(`/api/factory-eval/recommendations?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalPending = () => useQuery({
  queryKey: ['factory-eval', 'pending'],
  queryFn: () => safeFetch('/api/factory-eval/pending'),
  refetchInterval: REFRESH_MS,
});

export const useFactoryEvalCoverageGaps = () => useQuery({
  queryKey: ['factory-eval', 'coverage-gaps'],
  queryFn: () => safeFetch('/api/factory-eval/coverage-gaps'),
  refetchInterval: REFRESH_MS,
});
