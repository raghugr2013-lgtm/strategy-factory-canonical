/*
 * Mission Control aggregator — F7.
 * Composes Timeline + Approvals + Factory into a single Mission Control view.
 */
import { fetchTimeline } from './timelineAdapter';
import { fetchApprovals } from './approvalsAdapter';
import { fetchWorkers, fetchPipeline } from './factoryAdapter';
import { MISSION_METRICS_FIXTURE } from './fixtures';

export const aggregateMission = async () => {
  const [timeline, approvals, workers, pipeline] = await Promise.all([
    fetchTimeline(),
    fetchApprovals(),
    fetchWorkers(),
    fetchPipeline(),
  ]);
  return {
    metrics: MISSION_METRICS_FIXTURE,
    timeline: timeline.slice(0, 4),
    approvals,
    workers,
    pipeline,
  };
};
