/**
 * ASF · RC1 Parity Closure — thin operator-panel wrappers for backend-only
 * surfaces. Each wrapper exposes a curated, design-system-consistent view
 * of a backend router so the operator no longer has to use curl.
 *
 * All wrappers re-use /app/frontend/src/components/OperatorEndpointPanel.jsx
 * which inherits asf-section / asf-u2-panel surfaces, light + dark theme
 * tokens, and U-4.1 a11y (aria-labels, sr-only labels, keyboard accessible).
 *
 * Backend paths are sourced from /app/backend/api/{router}.py — verified
 * 2026-02 during the FULL_PARITY closure.
 */

import React from 'react';
import OperatorEndpointPanel from './OperatorEndpointPanel';

const M = (method, path, description, extra = {}) => ({ method, path, description, ...extra });

/* ── GAP-P0-2 · Factory Supervisor ──────────────────────────────────────── */
export function FactorySupervisorPanel() {
  return (
    <OperatorEndpointPanel
      title="Factory Supervisor"
      subtitle="Fleet · heartbeats · submissions · defer-queue · workers · transport"
      surfaceTestid="operator-factory-supervisor-panel"
      endpoints={[
        M('GET', '/api/factory-supervisor/status',              'Current supervisor status snapshot', { group: 'Status', runOnMount: true }),
        M('GET', '/api/factory-supervisor/fleet',               'Registered runner fleet', { group: 'Status' }),
        M('GET', '/api/factory-supervisor/lock',                'Current lock holder', { group: 'Status' }),
        M('GET', '/api/factory-supervisor/heartbeat-status',    'Last-seen heartbeat per runner', { group: 'Status' }),
        M('GET', '/api/factory-supervisor/heartbeats',          'Raw heartbeat stream (recent)', { group: 'Status' }),
        M('GET', '/api/factory-supervisor/events',              'Supervisor event log', { group: 'Events' }),
        M('GET', '/api/factory-supervisor/events/stats',        'Event-rate stats', { group: 'Events' }),
        M('POST','/api/factory-supervisor/lock/release',        'Force-release the supervisor lock (dangerous)', { group: 'Control' }),
        M('POST','/api/factory-supervisor/submit',              'Submit a new job to the supervisor', { group: 'Submissions', samplePayload: { strategy_id: '', priority: 0 } }),
        M('GET', '/api/factory-supervisor/submissions',         'Submission log', { group: 'Submissions' }),
        M('GET', '/api/factory-supervisor/submissions/stats',   'Submission throughput stats', { group: 'Submissions' }),
        M('GET', '/api/factory-supervisor/routing-policy',      'Active routing policy', { group: 'Routing' }),
        M('GET', '/api/factory-supervisor/defer-queue',         'Defer queue contents', { group: 'Defer Queue' }),
        M('GET', '/api/factory-supervisor/defer-queue/stats',   'Defer queue stats', { group: 'Defer Queue' }),
        M('POST','/api/factory-supervisor/defer-queue/cancel',  'Cancel a queued item', { group: 'Defer Queue', samplePayload: { row_id: '' } }),
        M('POST','/api/factory-supervisor/defer-queue/expire-overdue', 'Expire overdue queue items', { group: 'Defer Queue' }),
        M('GET', '/api/factory-supervisor/workers',             'Worker fleet status', { group: 'Workers' }),
        M('POST','/api/factory-supervisor/workers/tick',        'Force a worker tick', { group: 'Workers' }),
        M('GET', '/api/factory-supervisor/remote-transport',    'Remote transport state', { group: 'Transport' }),
      ]}
    />
  );
}

/* ── GAP-P0-3 · Scaling controls ────────────────────────────────────────── */
export function ScalingPanel() {
  return (
    <OperatorEndpointPanel
      title="Scaling Controls (12-vCPU readiness)"
      subtitle="Heartbeat · nodes · concurrency · admission · pressure · architect"
      surfaceTestid="operator-scaling-panel"
      endpoints={[
        M('POST','/api/scaling/heartbeat',                'Post heartbeat from this node', { group: 'Heartbeat' }),
        M('GET', '/api/scaling/nodes',                    'Known scaling nodes', { group: 'Topology', runOnMount: true }),
        M('GET', '/api/scaling/route',                    'Current scaling route table', { group: 'Topology' }),
        M('GET', '/api/scaling/concurrency',              'Concurrency limits per node', { group: 'Limits' }),
        M('GET', '/api/scaling/admission',                'Current admission policy', { group: 'Limits' }),
        M('GET', '/api/scaling/pressure',                 'Pressure signal (LCP, queue)', { group: 'Signals' }),
        M('GET', '/api/scaling/events',                   'Scaling event log', { group: 'Events' }),
        M('GET', '/api/scaling/events/stats',             'Event stats', { group: 'Events' }),
        M('GET', '/api/scaling/admission/journal-stats',  'Admission journal stats', { group: 'Limits' }),
        M('GET', '/api/scaling/architect/snapshot',       'Architect snapshot (read-only)', { group: 'Architect' }),
      ]}
    />
  );
}

/* ── GAP-P1-6 · Phase 12 tuning ─────────────────────────────────────────── */
export function Phase12TuningPanel() {
  return (
    <OperatorEndpointPanel
      title="Phase 12 Tuning"
      subtitle="Tuning settings · slot stats · performance · events"
      surfaceTestid="operator-phase12-tuning-panel"
      endpoints={[
        M('GET', '/api/tuning/settings',             'Current Phase-12 tuning settings', { group: 'Settings', runOnMount: true }),
        M('POST','/api/tuning/settings',             'Update tuning settings', { group: 'Settings', samplePayload: {} }),
        M('POST','/api/tuning/settings/reset',       'Reset tuning to defaults', { group: 'Settings' }),
        M('GET', '/api/tuning/slot-stats',           'Slot allocation stats', { group: 'Slots' }),
        M('GET', '/api/tuning/slot-stats/recommend', 'Recommended slot config', { group: 'Slots' }),
        M('GET', '/api/tuning/performance',          'Performance snapshot history', { group: 'Performance' }),
        M('POST','/api/tuning/performance/snapshot', 'Take a new performance snapshot', { group: 'Performance' }),
        M('GET', '/api/tuning/events',               'Tuning event log', { group: 'Events' }),
        M('GET', '/api/tuning/overview',             'Tuning overview', { group: 'Overview' }),
      ]}
    />
  );
}

/* ── GAP-P1-7 · GEM Factory ─────────────────────────────────────────────── */
export function GemFactoryPanel() {
  return (
    <OperatorEndpointPanel
      title="GEM Factory"
      subtitle="Run · status · sweep-degradation"
      surfaceTestid="operator-gem-factory-panel"
      endpoints={[
        M('GET', '/api/gem-factory/status',             'GEM factory status', { group: 'Status', runOnMount: true }),
        M('POST','/api/gem-factory/run',                'Trigger a GEM factory run', { group: 'Run', samplePayload: {} }),
        M('POST','/api/gem-factory/sweep-degradation',  'Sweep degraded GEMs', { group: 'Maintenance' }),
      ]}
    />
  );
}

/* ── GAP-P1-5 · Auto-Selection wrapper (delegates to existing component) ─ */
export { default as AutoSelectionWrapper } from './AutoSelection';

/* ── GAP-P2-10 · Admin Flag Governance ──────────────────────────────────── */
export function AdminFlagGovernancePanel() {
  return (
    <OperatorEndpointPanel
      title="Admin · Flag Governance"
      subtitle="Feature-flag lifecycle · widening proposals"
      surfaceTestid="operator-admin-flag-gov-panel"
      endpoints={[
        M('GET', '/api/admin/flag',                                    'Current flags', { group: 'Flags', runOnMount: true }),
        M('GET', '/api/admin/flag/history',                            'Flag change history', { group: 'Flags' }),
        M('POST','/api/admin/flag',                                    'Add or update a flag', { group: 'Flags', samplePayload: { flag_name: '', value: '', reason: '' } }),
        M('DELETE','/api/admin/flag/{flag_name}',                      'Delete a flag — replace {flag_name} first', { group: 'Flags' }),
        M('GET', '/api/admin/widening-proposals',                      'Pending widening proposals', { group: 'Proposals' }),
        M('POST','/api/admin/widening-proposals',                      'Submit a widening proposal', { group: 'Proposals', samplePayload: {} }),
        M('POST','/api/admin/widening-proposals/{proposal_id}/approve','Approve a proposal — replace {proposal_id} first', { group: 'Proposals' }),
        M('POST','/api/admin/widening-proposals/{proposal_id}/reject', 'Reject a proposal — replace {proposal_id} first', { group: 'Proposals' }),
      ]}
    />
  );
}

/* ── GAP-P2-11 · Admin Execution Realism ────────────────────────────────── */
export function AdminExecutionRealismPanel() {
  return (
    <OperatorEndpointPanel
      title="Admin · Execution Realism"
      subtitle="Realism gate defaults (set / unset)"
      surfaceTestid="operator-admin-exec-realism-panel"
      endpoints={[
        M('POST','/api/admin/execution-realism-defaults',   'Set realism defaults', { samplePayload: {} }),
        M('DELETE','/api/admin/execution-realism-defaults', 'Clear realism defaults'),
      ]}
    />
  );
}

/* ── GAP-P2-12 · Data backup (extra section under diag) ─────────────────── */
export function DataBackupPanel() {
  return (
    <OperatorEndpointPanel
      title="Data Backup"
      subtitle="Backup / coverage / import-backup"
      surfaceTestid="operator-data-backup-panel"
      endpoints={[
        M('GET', '/api/data/maintenance/coverage',       'Data coverage snapshot', { runOnMount: true }),
        M('POST','/api/data/maintenance/import-backup',  'Import a previously-exported backup', { samplePayload: { archive_path: '' } }),
        M('POST','/api/data/maintenance/backfill',       'Backfill missing windows', { samplePayload: {} }),
      ]}
    />
  );
}

/* ── GAP-P2-13 · Soak Diagnostics ──────────────────────────────────────── */
export function SoakDiagnosticsPanel() {
  return (
    <OperatorEndpointPanel
      title="Soak Diagnostics"
      subtitle="Hourly soak snapshot — used by Phase-2 soak coverage assessment"
      surfaceTestid="operator-soak-diag-panel"
      endpoints={[
        M('GET', '/api/diagnostics/soak-snapshot', 'Current soak snapshot', { runOnMount: true }),
      ]}
    />
  );
}

/* ── GAP-P2-14 · CPU pool state ────────────────────────────────────────── */
export function CpuPoolStatePanel() {
  return (
    <OperatorEndpointPanel
      title="CPU Pool State"
      subtitle="Pool sizing and utilisation"
      surfaceTestid="operator-cpu-pool-panel"
      endpoints={[
        M('GET', '/api/cpu-pool/state', 'Current CPU pool state', { runOnMount: true }),
      ]}
    />
  );
}

/* ── GAP-P1-9 · Challenge Matching ─────────────────────────────────────── */
export function ChallengeMatchingPanel() {
  return (
    <OperatorEndpointPanel
      title="Challenge Matching"
      subtitle="Status · decision · cooldown · control"
      surfaceTestid="operator-challenge-matching-panel"
      endpoints={[
        M('GET', '/api/challenge/status',           'Challenge matching status', { runOnMount: true }),
        M('POST','/api/challenge/decision',         'Submit a matching decision', { samplePayload: {} }),
        M('POST','/api/challenge/clear-cooldown',   'Clear matching cooldown'),
        M('POST','/api/challenge/control',          'Issue a control directive', { samplePayload: {} }),
      ]}
    />
  );
}

/* ── GAP-P0-1 wrap helper · existing MasterBotDashboard (full UI on disk) */
export { default as MasterBotDashboardWrapper } from './MasterBotDashboard';

/* ── GAP-P0-4 wrap helper · existing AdminUsers (full UI on disk) ──────── */
export { default as AdminUsersWrapper } from './AdminUsers';

/* ── GAP-P1-8 wrap helper · existing StrategyComparison (full UI on disk) */
export { default as StrategyComparisonWrapper } from './StrategyComparison';
