/*
 * dataGovernanceAdapter — thin read-only wrapper around
 * /api/data/maintenance/* and /api/governance/*.
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

/* ── data maintenance ─────────────────────────────────────────────── */

export const useDataMaintenanceStatus = () => useQuery({
  queryKey: ['data-maintenance', 'status'],
  queryFn: () => safeFetch('/api/data/maintenance/status'),
  refetchInterval: REFRESH_MS,
  refetchOnWindowFocus: true,
});

export const useDataMaintenanceConfig = () => useQuery({
  queryKey: ['data-maintenance', 'config'],
  queryFn: () => safeFetch('/api/data/maintenance/config'),
  refetchInterval: REFRESH_MS,
});

export const useDataMaintenanceRecentRuns = (limit = LIMIT) => useQuery({
  queryKey: ['data-maintenance', 'recent-runs', limit],
  queryFn: () => safeFetch(`/api/data/maintenance/recent-runs?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useDataHealth = () => useQuery({
  queryKey: ['data', 'health'],
  queryFn: () => safeFetch('/api/data/health'),
  refetchInterval: REFRESH_MS,
});

export const useDataCoverage = () => useQuery({
  queryKey: ['data', 'coverage'],
  queryFn: () => safeFetch('/api/data/coverage'),
  refetchInterval: REFRESH_MS,
});

/* ── governance ───────────────────────────────────────────────────── */

export const useGovernanceEcosystemMaturity = () => useQuery({
  queryKey: ['governance', 'ecosystem-maturity'],
  queryFn: () => safeFetch('/api/governance/ecosystem-maturity'),
  refetchInterval: REFRESH_MS,
});

export const useGovernanceBi5Maturity = () => useQuery({
  queryKey: ['governance', 'bi5-maturity'],
  queryFn: () => safeFetch('/api/governance/bi5-maturity'),
  refetchInterval: REFRESH_MS,
});

export const useGovernancePromotionLedger = (limit = LIMIT) => useQuery({
  queryKey: ['governance', 'promotion-ledger', limit],
  queryFn: () => safeFetch(`/api/governance/promotion-ledger?limit=${limit}`),
  refetchInterval: REFRESH_MS,
});

export const useGovernanceSurvivorRegistry = () => useQuery({
  queryKey: ['governance', 'survivor-registry'],
  queryFn: () => safeFetch('/api/governance/survivor-registry'),
  refetchInterval: REFRESH_MS,
});

export const useGovernanceReplacementCandidates = () => useQuery({
  queryKey: ['governance', 'replacement-candidates'],
  queryFn: () => safeFetch('/api/governance/replacement-candidates'),
  refetchInterval: REFRESH_MS,
});

export const useGovernanceUniverse = () => useQuery({
  queryKey: ['governance', 'universe'],
  queryFn: () => safeFetch('/api/governance/universe'),
  refetchInterval: REFRESH_MS,
});

/* ── COE queue (shared between Cockpit + this dashboard) ───────────── */

export const useCoeState = () => useQuery({
  queryKey: ['coe', 'state'],
  queryFn: () => safeFetch('/api/coe/state'),
  refetchInterval: REFRESH_MS,
});

export const useCoeMetrics = () => useQuery({
  queryKey: ['coe', 'metrics'],
  queryFn: () => safeFetch('/api/coe/metrics'),
  refetchInterval: REFRESH_MS,
});

export const useCoeDeadLetterDepth = () => useQuery({
  queryKey: ['coe', 'dead-letter-depth'],
  queryFn: () => safeFetch('/api/coe/dead-letter/depth'),
  refetchInterval: REFRESH_MS,
});
