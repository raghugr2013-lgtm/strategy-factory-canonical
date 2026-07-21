/*
 * Mission Control aggregator — Sprint 2 N4.
 * refs SPRINT_2_PLANNING.md §2 N4 (Promise.all partial-failure closure)
 *
 * Change vs. Sprint 1: `Promise.all` was replaced with `Promise.allSettled`
 * so a single failing adapter (network, freeze, 500) no longer nukes the
 * entire Mission Control bundle. Each slot falls back to a documented
 * safe default and records a per-slot error breadcrumb on `partial`.
 */
import { fetchTimeline } from './timelineAdapter';
import { fetchApprovals } from './approvalsAdapter';
import { fetchWorkers, fetchPipeline } from './factoryAdapter';
import { MISSION_METRICS_FIXTURE } from './fixtures';

const settle = (result, fallback, label) => {
  if (result.status === 'fulfilled') return { value: result.value, error: null, label };
  console.warn(`[missionAggregator] ${label} failed:`, result.reason?.message ?? result.reason);
  return { value: fallback, error: result.reason?.message ?? String(result.reason), label };
};

export const aggregateMission = async () => {
  const [timelineRes, approvalsRes, workersRes, pipelineRes] = await Promise.allSettled([
    fetchTimeline(),
    fetchApprovals(),
    fetchWorkers(),
    fetchPipeline(),
  ]);

  const timeline = settle(timelineRes, [], 'timeline');
  const approvals = settle(approvalsRes, [], 'approvals');
  const workers = settle(workersRes, [], 'workers');
  const pipeline = settle(pipelineRes, [], 'pipeline');

  const partial = [timeline, approvals, workers, pipeline]
    .filter((s) => s.error)
    .map((s) => ({ slot: s.label, error: s.error }));

  return {
    metrics: MISSION_METRICS_FIXTURE,
    timeline: (timeline.value || []).slice(0, 4),
    approvals: approvals.value,
    workers: workers.value,
    pipeline: pipeline.value,
    partial,
  };
};
