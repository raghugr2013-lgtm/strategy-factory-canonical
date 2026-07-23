/*
 * DataGovernanceDashboard — FE-B Slice 4.
 * Data Maintenance + Governance observability, side by side.
 * refs docs/FE_B_PROPOSAL.md · docs/CAPABILITY_INVENTORY.md
 *
 * Read-only. Consumes pre-existing endpoints only:
 *   Data Maintenance
 *     • GET /api/data/maintenance/status
 *     • GET /api/data/maintenance/config
 *     • GET /api/data/maintenance/recent-runs
 *     • GET /api/data/health
 *     • GET /api/data/coverage
 *   Governance
 *     • GET /api/governance/ecosystem-maturity
 *     • GET /api/governance/bi5-maturity
 *     • GET /api/governance/promotion-ledger
 *     • GET /api/governance/survivor-registry
 *     • GET /api/governance/replacement-candidates
 *     • GET /api/governance/universe
 *   COE
 *     • GET /api/coe/state
 *     • GET /api/coe/metrics
 *     • GET /api/coe/dead-letter/depth
 */
import React, { useMemo } from 'react';
import { Database, ShieldCheck, GitBranch, Waves, PackageCheck } from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge } from '../engineering/LivenessBadge';
import {
  useDataMaintenanceStatus, useDataMaintenanceConfig, useDataMaintenanceRecentRuns,
  useDataHealth, useDataCoverage,
  useGovernanceEcosystemMaturity, useGovernanceBi5Maturity, useGovernancePromotionLedger,
  useGovernanceSurvivorRegistry, useGovernanceReplacementCandidates, useGovernanceUniverse,
  useCoeState, useCoeMetrics, useCoeDeadLetterDepth,
} from '../../adapters/dataGovernanceAdapter';
import {
  SummaryPanel, SectionHeader, sectionPanel, eyebrowLabel, cell, cellHead,
  fmtISO, fmtRel, asArray, modeToTone, deriveHealth,
} from './factoryPrimitives';

const runTone = (s) => {
  const v = String(s || '').toLowerCase();
  if (v === 'ok' || v === 'success' || v === 'complete' || v === 'completed') return 'ok';
  if (v === 'failed' || v === 'error') return 'crit';
  if (v === 'running' || v === 'in-progress' || v === 'in_progress') return 'info';
  return 'dormant';
};

const RunsTable = ({ rows }) => {
  if (!rows || rows.length === 0) return (
    <StateTemplate variant="empty" code="dm-runs-empty" icon={Database} tone="dormant"
                   headline="No recent runs."
                   purpose="Data-maintenance has not executed a run in the current window." />
  );
  return (
    <div data-testid="dm-runs-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>ID</th>
            <th style={cellHead}>Kind</th>
            <th style={cellHead}>Status</th>
            <th style={cellHead}>Started</th>
            <th style={cellHead}>Duration</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((r, i) => (
            <tr key={r.id || r.run_id || i} data-testid={`dm-run-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(r.id || r.run_id || i).slice(0, 12)}</span></td>
              <td style={cell}><span className="mono-num">{r.kind || r.type || r.name || '—'}</span></td>
              <td style={cell}><Chip tone={runTone(r.status || r.state)} label={String(r.status || r.state || 'unknown').toUpperCase()} /></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(r.started_at || r.ts || r.timestamp)}</span></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{r.duration_s ? `${r.duration_s}s` : '—'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const PromotionsTable = ({ rows }) => {
  if (!rows || rows.length === 0) return (
    <StateTemplate variant="empty" code="gov-prom-empty" icon={GitBranch} tone="dormant"
                   headline="No promotions logged."
                   purpose="No strategy promotions in the current governance ledger window." />
  );
  return (
    <div data-testid="gov-promotions-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>Strategy</th>
            <th style={cellHead}>From → To</th>
            <th style={cellHead}>Actor</th>
            <th style={cellHead}>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((r, i) => (
            <tr key={r.id || i} data-testid={`gov-prom-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(r.strategy_id || r.strategy || r.hash || '—').slice(0, 22)}</span></td>
              <td style={cell}><span className="mono-num">{`${r.from_stage || r.from || '—'} → ${r.to_stage || r.to || '—'}`}</span></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-md)' }}>{r.actor || r.by || 'system'}</span></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(r.ts || r.timestamp || r.at)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const DataGovernanceDashboard = () => {
  const dmStatusQ  = useDataMaintenanceStatus();
  const dmConfigQ  = useDataMaintenanceConfig();
  const dmRunsQ    = useDataMaintenanceRecentRuns(20);
  const dhealthQ   = useDataHealth();
  const covQ       = useDataCoverage();
  const ecoQ       = useGovernanceEcosystemMaturity();
  const bi5Q       = useGovernanceBi5Maturity();
  const promQ      = useGovernancePromotionLedger(20);
  const survQ      = useGovernanceSurvivorRegistry();
  const replQ      = useGovernanceReplacementCandidates();
  const univQ      = useGovernanceUniverse();
  const coeStateQ  = useCoeState();
  const coeMetQ    = useCoeMetrics();
  const dlqDepthQ  = useCoeDeadLetterDepth();

  const dmStatus = dmStatusQ.data;
  const dmConfig = dmConfigQ.data;
  const dhealth  = dhealthQ.data;
  const coverage = covQ.data;
  const eco      = ecoQ.data;
  const bi5      = bi5Q.data;
  const surv     = survQ.data;
  const univ     = univQ.data;
  const coeState = coeStateQ.data;
  const coeMet   = coeMetQ.data;
  const dlq      = dlqDepthQ.data;

  const runs        = asArray(dmRunsQ.data, 'runs', 'recent_runs');
  const promotions  = asArray(promQ.data, 'promotions', 'ledger', 'entries');
  const survivors   = asArray(surv, 'survivors', 'entries');
  const candidates  = asArray(replQ.data, 'candidates');

  const dmMode      = dmStatus?.mode || dmConfig?.mode || (dmStatus?.enabled === false ? 'disabled' : 'unknown');
  const dmEnabled   = dmStatus?.enabled === true || dmStatus?.running === true;
  const dh          = deriveHealth(dhealth);
  const coverageOk  = coverage?.ok === true || coverage?.healthy === true || (coverage?.gaps !== undefined ? coverage.gaps === 0 : (coverage ? true : false));
  const coverageGaps = coverage?.gaps ?? coverage?.total_gaps ?? 0;

  const ecoScore = eco?.score ?? eco?.maturity ?? eco?.overall ?? null;
  const ecoTone  = ecoScore != null ? (ecoScore >= 0.8 ? 'ok' : ecoScore >= 0.5 ? 'warn' : 'crit') : 'dormant';

  const universeSize = univ?.count ?? univ?.size ?? (Array.isArray(univ?.symbols) ? univ.symbols.length : (Array.isArray(univ) ? univ.length : 0));

  const dlqDepth = dlq?.depth ?? dlq?.count ?? (typeof dlq === 'number' ? dlq : 0);
  const coeH = deriveHealth(coeState);
  const coeMode = coeH.tone === 'dormant' && coeH.label === 'DISABLED'
    ? 'unknown'
    : (coeState?.mode || coeState?.state || (coeState?.paused ? 'paused' : 'active'));

  const cells = useMemo(() => ([
    { label: 'Maintenance Mode',    tone: modeToTone(dmMode),                     value: String(dmMode).toUpperCase(),        sub: '/api/data/maintenance', testId: 'dm-cell-mode' },
    { label: 'Maintenance Active',  tone: dmEnabled ? 'info' : 'dormant',         value: dmEnabled ? 'RUNNING' : 'IDLE',      sub: `${runs.length} recent runs`, testId: 'dm-cell-active' },
    { label: 'Data Health',         tone: dh.tone, value: dh.label, sub: '/api/data/health', testId: 'dm-cell-health' },
    { label: 'Coverage Gaps',       tone: coverageGaps > 0 ? 'warn' : 'ok',       value: `${coverageGaps}`,                    sub: 'total across universe', testId: 'dm-cell-cov-gaps' },
    { label: 'Ecosystem Maturity',  tone: ecoTone,                                value: ecoScore != null ? `${Math.round(ecoScore * 100)}%` : '—', sub: '/api/governance/ecosystem-maturity', testId: 'gov-cell-eco' },
    { label: 'Universe Size',       tone: universeSize > 0 ? 'info' : 'dormant',  value: `${universeSize}`,                    sub: 'governance-approved', testId: 'gov-cell-universe' },
    { label: 'Survivors',           tone: survivors.length > 0 ? 'info' : 'dormant', value: `${survivors.length}`,             sub: 'survivor registry', testId: 'gov-cell-survivors' },
    { label: 'Queue · DLQ',         tone: dlqDepth > 0 ? 'warn' : 'ok',           value: `${dlqDepth}`,                        sub: `queue · ${String(coeMode).toUpperCase()}`, testId: 'coe-cell-dlq' },
  ]), [dmMode, dmEnabled, dh, coverageGaps, ecoScore, ecoTone, universeSize, survivors, dlqDepth, coeMode, runs.length]);

  return (
    <section data-testid="data-governance-dashboard" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Data Maintenance &amp; Governance</span>
        <SignalStateBadge state={(dmStatus || dhealth || eco) ? 'live' : 'error'}
                          reason={(dmStatus || dhealth || eco) ? '/api/data/maintenance/* · /api/governance/*' : 'unreachable'}
                          testId="dg-header-signal" />
      </div>

      <h1 data-testid="dg-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Data Maintenance &amp; Governance
      </h1>
      <p data-testid="dg-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        Data-maintenance keeps the coverage matrix honest — ingest, gap-fill, health probe. Governance keeps the strategy
        universe honest — promotion ledger, survivor registry, replacement candidates, ecosystem maturity. The COE queue
        gates every mutating operation.
      </p>

      <SummaryPanel testId="data-governance-summary-panel"
                    signalState={(dmStatus || dhealth || eco) ? 'live' : 'deferred'}
                    signalReason={(dmStatus || dhealth || eco) ? '/api/data/maintenance/* · /api/governance/*' : 'endpoint unreachable'}
                    cells={cells} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
           data-testid="dg-metric-row">
        <MetricBlock variant="B" eyebrow="RECENT RUNS" value={runs.length}
                     deltaLabel={dmEnabled ? 'ACTIVE' : 'IDLE'} deltaTone={dmEnabled ? 'info' : 'dormant'}
                     state={dmRunsQ.isLoading ? 'loading' : 'happy'} testId="metric-dg-runs" />
        <MetricBlock variant="A" eyebrow="COVERAGE GAPS" value={coverageGaps}
                     deltaLabel={coverageGaps > 0 ? 'ATTENTION' : 'CLEAR'} deltaTone={coverageGaps > 0 ? 'warn' : 'ok'}
                     state={covQ.isLoading ? 'loading' : 'happy'} testId="metric-dg-gaps" />
        <MetricBlock variant="A" eyebrow="PROMOTIONS" value={promotions.length}
                     deltaLabel="LEDGER" deltaTone="info"
                     state={promQ.isLoading ? 'loading' : 'happy'} testId="metric-dg-promotions" />
        <MetricBlock variant="A" eyebrow="DLQ DEPTH" value={dlqDepth}
                     deltaLabel={dlqDepth > 0 ? 'ATTENTION' : 'CLEAR'} deltaTone={dlqDepth > 0 ? 'warn' : 'ok'}
                     state={dlqDepthQ.isLoading ? 'loading' : 'happy'} testId="metric-dg-dlq" />
      </div>

      <SectionHeader icon={Database} title="Data-Maintenance · Recent Runs" testId="dg-runs-header" />
      <div style={sectionPanel} data-testid="dg-runs-panel">
        {dmRunsQ.isLoading
          ? <StateTemplate variant="loading" code="dm-runs-loading" icon={Database} tone="info" headline="Loading recent runs…" purpose="/api/data/maintenance/recent-runs" />
          : <RunsTable rows={runs} />}
      </div>

      <div style={{ marginTop: 'var(--space-6)' }}>
        <SectionHeader icon={GitBranch} title="Governance · Promotion Ledger" testId="dg-promotions-header" />
        <div style={sectionPanel} data-testid="dg-promotions-panel">
          {promQ.isLoading
            ? <StateTemplate variant="loading" code="gov-prom-loading" icon={GitBranch} tone="info" headline="Loading promotion ledger…" purpose="/api/governance/promotion-ledger" />
            : <PromotionsTable rows={promotions} />}
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="dg-refresh-hint">Auto-refresh: 15s · Focus revalidates instantly</span>
        <span style={{ margin: '0 var(--space-3)', color: 'var(--content-lo)' }}>·</span>
        <span>Sources: <span className="mono-num">/api/data/maintenance/*</span> · <span className="mono-num">/api/data/health</span> · <span className="mono-num">/api/governance/*</span> · <span className="mono-num">/api/coe/*</span></span>
      </div>
    </section>
  );
};

export default DataGovernanceDashboard;
