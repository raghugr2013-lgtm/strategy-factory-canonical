/*
 * FactoryCockpit — FE-B Slice 5 · unified operator landing page at /c/factory.
 * refs docs/FE_B_PROPOSAL.md — one-glance overview of the Autonomous Factory.
 *
 * Read-only. Reuses ALL existing Factory adapters (no new endpoints, no writes,
 * no fixtures). Every summary tile drills into its full dashboard.
 *
 * Sections (per user request):
 *   1. Overall Factory Health (aggregated traffic-light)
 *   2. Orchestrator Status
 *   3. Meta-Learning Status
 *   4. Factory Evaluation
 *   5. AI Provider Health
 *   6. Data Maintenance Status
 *   7. Governance Status
 *   8. Current Alerts
 *   9. Running Tasks
 *  10. Recent Decisions
 *  11. Queue Status (COE)
 */
import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity, Cpu, Brain, Gauge, Bot, Database, ShieldCheck, AlertTriangle,
  Zap, GitBranch, Layers,
} from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge, FreezeCaption } from '../engineering/LivenessBadge';
import {
  useOrchestratorStatus, useOrchestratorDecisions, useOrchestratorHealthInputs,
} from '../../adapters/orchestratorAdapter';
import {
  useMetaLearningStatus, useMetaLearningConfig, useMetaLearningHealth,
  useMetaLearningPending,
} from '../../adapters/metaLearningAdapter';
import {
  useFactoryEvalStatus, useFactoryEvalConfig, useFactoryEvalHealth,
  useFactoryEvalLatestReport, useFactoryEvalPending,
} from '../../adapters/factoryEvalAdapter';
import {
  useDataMaintenanceStatus, useDataHealth, useDataCoverage,
  useGovernanceEcosystemMaturity,
  useCoeState, useCoeDeadLetterDepth,
} from '../../adapters/dataGovernanceAdapter';
import {
  SectionHeader, sectionPanel, eyebrowLabel, cell, cellHead,
  fmtISO, fmtRel, asArray, modeToTone, deriveHealth,
} from './factoryPrimitives';

const bandToTone = (band) => (band === 'critical' ? 'crit' : band === 'warn' ? 'warn' : band === 'unknown' ? 'dormant' : 'ok');

const providerNormalised = (raw) => {
  if (!raw) return [];
  if (Array.isArray(raw.providers)) return raw.providers;
  if (raw.providers && typeof raw.providers === 'object') return Object.entries(raw.providers).map(([name, v]) => ({ name, ...(v || {}) }));
  if (Array.isArray(raw)) return raw;
  return [];
};

/* ─── overall traffic-light — worst signal wins ──────────────────── */
const aggregate = (signals) => {
  const priority = { crit: 4, warn: 3, info: 2, ok: 1, dormant: 0 };
  return signals.reduce((worst, s) => (priority[s] > priority[worst] ? s : worst), 'ok');
};

/* ─── section tile — one status pill + link to its own dashboard ──── */
const StatusTile = ({ icon: Icon, testId, label, tone, value, sub, to }) => (
  <Link to={to} data-testid={testId} style={{
    display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
    padding: 'var(--space-4)', minWidth: 200,
    background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
    borderRadius: 'var(--radius-2)', textDecoration: 'none', color: 'inherit',
    transition: 'border-color 120ms ease, background 120ms ease',
  }}
  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--sig-info)'; }}
  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--stroke-1)'; }}>
    <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--content-lo)' }}>
      {Icon && <Icon size={12} aria-hidden />}
      {label}
    </span>
    <Chip tone={tone} label={value} />
    {sub && <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>{sub}</span>}
  </Link>
);

export const FactoryCockpit = () => {
  /* Data pulls (all Read-only, all pre-existing endpoints) */
  const orchStatusQ = useOrchestratorStatus();
  const orchDecisionsQ = useOrchestratorDecisions(20);
  const orchHealth = useOrchestratorHealthInputs();

  const mlStatusQ = useMetaLearningStatus();
  const mlConfigQ = useMetaLearningConfig();
  const mlHealthQ = useMetaLearningHealth();
  const mlPendingQ = useMetaLearningPending();

  const feStatusQ = useFactoryEvalStatus();
  const feConfigQ = useFactoryEvalConfig();
  const feHealthQ = useFactoryEvalHealth();
  const feReportQ = useFactoryEvalLatestReport();
  const fePendingQ = useFactoryEvalPending();

  const dmStatusQ = useDataMaintenanceStatus();
  const dHealthQ  = useDataHealth();
  const covQ      = useDataCoverage();
  const ecoQ      = useGovernanceEcosystemMaturity();
  const coeStateQ = useCoeState();
  const dlqQ      = useCoeDeadLetterDepth();

  const orch = orchStatusQ.data;
  const decisions = asArray(orchDecisionsQ.data, 'decisions');
  const mlConfig = mlConfigQ.data;
  const mlHealth = mlHealthQ.data;
  const mlPending = asArray(mlPendingQ.data, 'pending');
  const feConfig = feConfigQ.data;
  const feHealth = feHealthQ.data;
  const feReport = feReportQ.data;
  const fePending = asArray(fePendingQ.data, 'pending');
  const dmStatus = dmStatusQ.data;
  const dHealth = dHealthQ.data;
  const cov = covQ.data;
  const eco = ecoQ.data;
  const coeState = coeStateQ.data;
  const dlq = dlqQ.data;

  /* Derived signals */
  const orchRunning = orch?.running === true;
  const orchTone = orch?.meta?.last_error ? 'crit' : !orchRunning ? 'dormant' : bandToTone(orch?.meta?.last_tick?.band);
  const orchLabel = orch?.meta?.last_error ? 'ERROR' : orchRunning ? `RUNNING · ${(orch?.meta?.last_tick?.band || 'nominal').toUpperCase()}` : 'HALTED';

  const inFlight = (orch?.in_flight || []);
  const dispatched = orch?.meta?.dispatched_total ?? 0;

  const providers = providerNormalised(orchHealth.provider);
  const providerConfigured = providers.filter((p) => p.configured || p.enabled || p.available).length;
  const providerCircuitOpen = providers.some((p) => p.circuit === 'open' || p.state === 'open');
  const providerTone = providerCircuitOpen ? 'crit' : providerConfigured === 0 ? 'dormant' : 'info';
  const providerLabel = providerCircuitOpen ? 'CIRCUIT OPEN' : providerConfigured === 0 ? 'NO PROVIDER' : `${providerConfigured} PROVIDER${providerConfigured === 1 ? '' : 'S'}`;

  const mlMode = mlConfig?.mode || 'unknown';
  const mlH = deriveHealth(mlHealth);
  const mlTone = mlH.tone === 'ok' ? modeToTone(mlMode) : mlH.tone;
  const mlLabel = mlH.tone === 'dormant' && mlH.label === 'DISABLED' ? `${String(mlMode).toUpperCase()} · DISABLED` : `${String(mlMode).toUpperCase()} · ${mlH.label}`;

  const feMode = feConfig?.mode || 'unknown';
  const feH = deriveHealth(feHealth);
  const feVerdict = feReport?.overall || feReport?.verdict || feReport?.grade || feReport?.status || null;
  const feTone = feH.tone === 'ok' ? modeToTone(feMode) : feH.tone;
  const feLabel = feVerdict
    ? `${String(feMode).toUpperCase()} · ${String(feVerdict).toUpperCase()}`
    : (feH.tone === 'dormant' && feH.label === 'DISABLED' ? `${String(feMode).toUpperCase()} · DISABLED` : `${String(feMode).toUpperCase()} · ${feH.label}`);

  const dmRunning = dmStatus?.enabled === true || dmStatus?.running === true;
  const dh = deriveHealth(dHealth);
  const dmTone = dh.tone === 'ok' ? 'ok' : dh.tone;
  const dmLabel = dh.label === 'HEALTHY' ? (dmRunning ? 'ACTIVE' : 'IDLE') : dh.label;
  const coverageGaps = cov?.gaps ?? cov?.total_gaps ?? 0;

  const ecoScore = eco?.score ?? eco?.maturity ?? eco?.overall ?? null;
  const govTone  = ecoScore != null ? (ecoScore >= 0.8 ? 'ok' : ecoScore >= 0.5 ? 'warn' : 'crit') : 'dormant';
  const govLabel = ecoScore != null ? `MATURITY ${Math.round(ecoScore * 100)}%` : '—';

  const dlqDepth = dlq?.depth ?? dlq?.count ?? (typeof dlq === 'number' ? dlq : 0);
  const coeH = deriveHealth(coeState);
  const coeMode = coeH.tone === 'dormant' && coeH.label === 'DISABLED'
    ? 'unknown'
    : (coeState?.mode || coeState?.state || (coeState?.paused ? 'paused' : 'active'));
  const coeTone = coeH.tone === 'dormant' && coeH.label === 'DISABLED'
    ? 'dormant'
    : (coeState?.paused === true ? 'warn' : dlqDepth > 0 ? 'warn' : 'ok');
  const coeLabel = coeH.tone === 'dormant' && coeH.label === 'DISABLED'
    ? 'DISABLED'
    : `${String(coeMode).toUpperCase()} · DLQ ${dlqDepth}`;

  /* Alerts aggregation */
  const alerts = useMemo(() => {
    const out = [];
    if (orch?.meta?.last_error) out.push({ tone: 'crit', headline: `Orchestrator error · ${String(orch.meta.last_error).slice(0, 80)}` });
    if (!orchRunning) out.push({ tone: 'warn', headline: 'Orchestrator is halted' });
    if (orch?.meta?.last_tick?.band === 'critical') out.push({ tone: 'crit', headline: 'Last tick band CRITICAL' });
    providers.filter((p) => p.circuit === 'open' || p.state === 'open')
      .forEach((p) => out.push({ tone: 'crit', headline: `Provider ${p.name || p.provider || 'unknown'} circuit open` }));
    if (mlPending.length > 0) out.push({ tone: 'warn', headline: `${mlPending.length} meta-learning approval${mlPending.length === 1 ? '' : 's'} pending` });
    if (fePending.length > 0) out.push({ tone: 'warn', headline: `${fePending.length} factory-eval approval${fePending.length === 1 ? '' : 's'} pending` });
    if (dlqDepth > 0) out.push({ tone: 'warn', headline: `${dlqDepth} item${dlqDepth === 1 ? '' : 's'} in COE dead-letter queue` });
    if (coeState?.paused) out.push({ tone: 'warn', headline: 'COE queue is paused' });
    if (coverageGaps > 0) out.push({ tone: 'warn', headline: `${coverageGaps} coverage gap${coverageGaps === 1 ? '' : 's'} across the universe` });
    return out;
  }, [orch, orchRunning, providers, mlPending, fePending, dlqDepth, coeState, coverageGaps]);

  /* Overall factory health (worst-signal wins) */
  const overall = aggregate([orchTone, mlTone, feTone, providerTone, dmTone, govTone, coeTone]);
  const overallLabel = overall === 'crit' ? 'CRITICAL' : overall === 'warn' ? 'ATTENTION' : overall === 'ok' ? 'HEALTHY' : overall === 'info' ? 'LIVE' : 'IDLE';

  const anyLoaded = orch || mlConfig || feConfig || dmStatus || eco;

  return (
    <section data-testid="factory-cockpit" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Cockpit</span>
        <SignalStateBadge state={anyLoaded ? 'live' : (orchStatusQ.isLoading ? 'partial' : 'error')}
                          reason={anyLoaded ? 'live poll · 15s' : 'endpoints unreachable'}
                          testId="cockpit-header-signal" />
        <span style={{ marginLeft: 'auto' }}><FreezeCaption /></span>
      </div>

      <h1 data-testid="cockpit-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Autonomous Factory Cockpit · {overallLabel}
      </h1>
      <p data-testid="cockpit-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        One-glance operator view of the Autonomous Research Factory. Each tile links to its own dashboard. The overall
        signal is worst-signal-wins across seven subsystems (Orchestrator · Meta-Learning · Evaluation · AI Provider ·
        Data Maintenance · Governance · Queue).
      </p>

      {/* Overall health block */}
      <div data-testid="cockpit-overall-panel" style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-4)',
        padding: 'var(--space-4)', marginBottom: 'var(--space-6)',
        background: 'var(--surface-2)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-3)',
      }}>
        <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-md)' }}>Overall Factory Health</span>
        <Chip tone={overall} label={overallLabel} testId="cockpit-overall-chip" />
        <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-body-sm)' }}>
          {alerts.length === 0 ? 'No open alerts.' : `${alerts.length} alert${alerts.length === 1 ? '' : 's'} · worst signal: ${overall.toUpperCase()}`}
        </span>
      </div>

      {/* Subsystem status tiles */}
      <SectionHeader icon={Layers} title="Subsystem Status" testId="cockpit-subsystems-header" />
      <div data-testid="cockpit-subsystems-grid"
           style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-6)' }}>
        <StatusTile icon={Cpu}         testId="tile-orchestrator"    label="Orchestrator"       tone={orchTone}     value={orchLabel}       sub={`${inFlight.length} in flight · ${dispatched} dispatched`} to="/c/factory/orchestrator" />
        <StatusTile icon={Brain}       testId="tile-meta-learning"   label="Meta-Learning"      tone={mlTone}       value={mlLabel}         sub={`${mlPending.length} pending`}                            to="/c/factory/meta-learning" />
        <StatusTile icon={Gauge}       testId="tile-factory-eval"    label="Factory Evaluation" tone={feTone}       value={feLabel}         sub={`${fePending.length} pending`}                            to="/c/factory/evaluation" />
        <StatusTile icon={Bot}         testId="tile-ai-provider"     label="AI Provider Health" tone={providerTone} value={providerLabel}   sub="/api/ai-workforce/health"                                to="/c/factory/orchestrator" />
        <StatusTile icon={Database}    testId="tile-data-maintenance" label="Data Maintenance"  tone={dmTone}       value={dmLabel}         sub={`${coverageGaps} coverage gaps`}                          to="/c/factory/data-governance" />
        <StatusTile icon={ShieldCheck} testId="tile-governance"      label="Governance"         tone={govTone}      value={govLabel}        sub="ecosystem maturity"                                       to="/c/factory/data-governance" />
        <StatusTile icon={GitBranch}   testId="tile-queue"           label="Queue (COE)"        tone={coeTone}      value={coeLabel}        sub="/api/coe/*"                                              to="/c/factory/data-governance" />
      </div>

      {/* Alerts + running tasks + recent decisions row */}
      <SectionHeader icon={AlertTriangle} title="Current Alerts" testId="cockpit-alerts-header" />
      <div style={sectionPanel} data-testid="cockpit-alerts-panel">
        {alerts.length === 0 ? (
          <StateTemplate variant="empty" code="cockpit-alerts-empty" icon={AlertTriangle} tone="ok"
                         headline="No open alerts."
                         purpose="Every subsystem reports green or dormant." />
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {alerts.map((a, i) => (
              <li key={i} data-testid={`cockpit-alert-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                <Chip tone={a.tone} label={a.tone.toUpperCase()} />
                <span style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)' }}>{a.headline}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', marginTop: 'var(--space-6)' }}>
        {/* Running tasks */}
        <div>
          <SectionHeader icon={Zap} title="Running Tasks" testId="cockpit-running-header" />
          <div style={sectionPanel} data-testid="cockpit-running-panel">
            {inFlight.length === 0 ? (
              <StateTemplate variant="empty" code="cockpit-running-empty" icon={Zap} tone="dormant"
                             headline="No tasks in flight."
                             purpose="The orchestrator has no active dispatch." />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }} data-testid="cockpit-running-table">
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
                    <th style={cellHead}>Task</th>
                    <th style={cellHead}>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {inFlight.slice(0, 10).map((t, i) => (
                    <tr key={t.task_name + i} data-testid={`cockpit-running-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
                      <td style={cell}><span className="mono-num">{t.task_name}</span></td>
                      <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(t.started_at || t.ts)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Recent decisions */}
        <div>
          <SectionHeader icon={GitBranch} title="Recent Decisions" testId="cockpit-decisions-header" />
          <div style={sectionPanel} data-testid="cockpit-decisions-panel">
            {decisions.length === 0 ? (
              <StateTemplate variant="empty" code="cockpit-decisions-empty" icon={GitBranch} tone="dormant"
                             headline="No recent decisions."
                             purpose="The orchestrator has not dispatched any ticks yet." />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }} data-testid="cockpit-decisions-table">
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
                    <th style={cellHead}>Tick</th>
                    <th style={cellHead}>Band</th>
                    <th style={cellHead}>Launched</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.slice(-10).reverse().map((d, i) => (
                    <tr key={d.tick_id || i} data-testid={`cockpit-decision-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
                      <td style={cell}><span className="mono-num">{String(d.tick_id || i).slice(0, 12)}</span></td>
                      <td style={cell}><Chip tone={bandToTone(d.band)} label={(d.band || 'nominal').toUpperCase()} /></td>
                      <td style={cell}><span className="mono-num" style={{ color: 'var(--content-md)' }}>{(d.launched || []).map((l) => l.task_name).join(', ') || '—'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Footnote */}
      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="cockpit-refresh-hint">Auto-refresh: 15s · Focus revalidates instantly · Zero writes · Feature Freeze preserved</span>
      </div>
    </section>
  );
};

export default FactoryCockpit;
