/*
 * curatedLibraryAdapter — read-only view of the Historical KB curated candidates.
 * refs docs/HKB_MIGRATION_REPORT.md · Backend Feature Freeze v1.1.0-stage4.
 *
 * Consumes pre-existing endpoints only:
 *   • GET /api/knowledge/champions   — categorised champion families
 *   • GET /api/knowledge/statistics  — corpus totals
 *   • GET /api/knowledge/health      — corpus liveness
 *
 * The champions endpoint is populated by the post-import pipeline
 * (`hkb/scripts/build_kb_views.py`) from `curated_strategy_library`.
 */
import { useQuery } from '@tanstack/react-query';
import { apiFetch, isLiveMode } from './apiClient';

const REFRESH_MS = 30_000;

const safeFetch = async (path) => {
  if (!isLiveMode()) return null;
  try {
    return await apiFetch(path);
  } catch {
    return null;
  }
};

export const useKBHealth = () => useQuery({
  queryKey: ['knowledge', 'health'],
  queryFn: () => safeFetch('/api/knowledge/health'),
  refetchInterval: REFRESH_MS,
});

export const useKBStatistics = () => useQuery({
  queryKey: ['knowledge', 'statistics'],
  queryFn: () => safeFetch('/api/knowledge/statistics'),
  refetchInterval: REFRESH_MS,
});

export const useKBChampions = () => useQuery({
  queryKey: ['knowledge', 'champions'],
  queryFn: () => safeFetch('/api/knowledge/champions'),
  refetchInterval: REFRESH_MS,
});
