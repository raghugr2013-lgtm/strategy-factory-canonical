/*
 * OrchestratorDashboard — FE-B Slice 1 · the primary operational view of the
 * Autonomous Research Factory.
 * refs docs/FE_B_PROPOSAL.md §3 · docs/CAPABILITY_INVENTORY.md §C
 *
 * Read-only. Consumes the following pre-existing backend endpoints (all under
 * Backend Feature Freeze v1.1.0-stage4):
 *   • GET /api/orchestrator/status
 *   • GET /api/orchestrator/decisions?limit=20
 *   • GET /api/orchestrator/history?limit=20
 *   • GET /api/ai-workforce/health         (LLM provider health)
 *   • GET /api/factory-eval/config         (Factory Eval mode)
 *   • GET /api/meta-learning/config        (Meta-Learning mode)
 *
 * Reuses these existing primitives verbatim — no new components:
 *   • MetricBlock       (4-card metric row + summary strip)
 *   • Chip              (tone-glyph badges)
 *   • SignalStateBadge  (canonical LIVE/PARTIAL/DEFERRED/GATED/ERROR)
 *   • StateTemplate     (loading / error / empty flows)
 */
import React, { useMemo } from 'react';
import { Bot, GitBranch, Sparkles, Zap, Clock, Activity } from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge, FreezeCaption } from '../engineering/LivenessBadge';
import {
  useOrchestratorStatus,
  useOrchestratorDecisions,
  useOrchestratorHistory,
  useOrchestratorHealthInputs,
} from '../../adapters/orchestratorAdapter';

/* ── projections ─────────────────────────────────────────────────────── */

const fmtISO = (iso) => (iso ? String(iso).replace('T', ' ').replace('Z', 'Z').slice(5, 22) : '—');
const fmtRel = (iso) => {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return '—';
  const dSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (dSec < 60) return `${dSec}s ago`;
  if (dSec < 3600) return `${Math.floor(dSec / 60)}m ago`;
  if (dSec < 86_400) return `${Math.floor(dSec / 3600)}h ago`;
  return `${Math.floor(dSec / 86_400)}d ago`;
};

const bandToTone = (band) => (band === 'critical' ? 'crit' : band === 'warn' ? 'warn' : band === 'unknown' ? 'dormant' : 'ok');
const factoryState = (status) => {
  if (!status) return { tone: 'dormant', label: 'Unknown' };
  if (status.meta?.last_error) return { tone: 'crit', label: 'Error' };
  if (!status.running) return { tone: 'dormant', label: 'Halted' };
  return { tone: bandToTone(status.meta?.last_tick?.band), label: (status.meta?.last_tick?.band || 'nominal').toUpperCase() };
};

/* ── summary panel (operator "at-a-glance") ──────────────────────────── */

const SummaryPanel = ({ status, provider, factoryEval, metaLearning, lastGoodTick, alerts }) => {
  const state = factoryState(status);
  const running = status?.running === true;

  const orchTone = state.tone;
  const orchLabel = running ? `RUNNING · ${state.label}` : `${state.label.toUpperCase()}`;

  const inFlight = (status?.in_flight || []).length;
  const dispatched = status?.meta?.dispatched_total ?? 0;
  const runsFail = Object.values(status?.counters?.runs_fail || {}).reduce((a, b) => a + b, 0);

  const providersArr = Array.isArray(provider?.providers)
    ? provider.providers
    : (provider?.providers && typeof provider.providers === 'object')
      ? Object.entries(provider.providers).map(([name, v]) => ({ name, ...(v || {}) }))
      : [];
  const providerConfigured = providersArr.filter((p) => p.configured || p.enabled || p.available).length;
  const providerCircuitOpen = providersArr.some((p) => p.circuit === 'open' || p.state === 'open');
  const providerTone = providerCircuitOpen ? 'crit' : providerConfigured === 0 ? 'dormant' : 'info';
  const providerLabel = providerCircuitOpen ? 'CIRCUIT OPEN' : providerConfigured === 0 ? 'NO PROVIDER' : `${providerConfigured} PROVIDER${providerConfigured === 1 ? '' : 'S'}`;

  const feMode = factoryEval?.mode || 'unknown';
  const mlMode = metaLearning?.mode || 'unknown';

  const cell = (label, tone, value, sub) => (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
      padding: 'var(--space-4)', minWidth: 180,
      background: 'var(--surface-1)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)',
    }}>
      <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--content-lo)' }}>{label}</span>
      <Chip tone={tone} label={value} />
      {sub && <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>{sub}</span>}
    </div>
  );

  return (
    <div data-testid="orchestrator-summary-panel"
         style={{
           padding: 'var(--space-4)',
           background: 'var(--surface-2)',
           border: '1px solid var(--stroke-1)',
           borderRadius: 'var(--radius-3)',
           marginBottom: 'var(--space-6)',
         }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-md)' }}>Operator Summary</span>
        <SignalStateBadge state={status ? 'live' : 'deferred'} reason={status ? '/api/orchestrator/status' : 'endpoint unreachable'} testId="orchestrator-summary-signal" />
        <span style={{ marginLeft: 'auto' }}>
          <FreezeCaption />
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-3)' }}>
        {cell('Factory State',       orchTone,    orchLabel,                                `${inFlight} in flight`)}
        {cell('Orchestrator Status', orchTone,    running ? 'RUNNING' : 'HALTED',           `${status?.meta?.tick_count ?? 0} ticks`)}
        {cell('Active Tasks',        inFlight > 0 ? 'info' : 'dormant', `${inFlight}`,       `${dispatched} dispatched`)}
        {cell('Scheduler Health',    running ? 'ok' : 'dormant',        running ? 'ACTIVE' : 'SUBORDINATED', 'orchestrator owns cadence')}
        {cell('AI Provider Health',  providerTone, providerLabel,                             provider ? '/api/ai-workforce/health' : '—')}
        {cell('Last Successful Cycle', lastGoodTick ? 'ok' : 'dormant', fmtRel(lastGoodTick),  fmtISO(lastGoodTick))}
        {cell('Current Alerts',      alerts.length > 0 ? 'warn' : 'ok', `${alerts.length}`,   alerts[0]?.headline || 'None')}
        {cell('Mode',                (feMode === 'observe' && mlMode === 'observe') ? 'ok' : 'warn',
                                     `OBSERVE · OBSERVE`,
                                     `factory-eval · meta-learning`)}
      </div>
    </div>
  );
};

/* ── decisions table (compact) ───────────────────────────────────────── */

const DecisionsTable = ({ rows }) => {
  if (!Array.isArray(rows) || rows.length === 0) return (
    <StateTemplate variant="empty" code="orch-decisions-empty" icon={GitBranch} tone="dormant"
                   headline="No orchestrator decisions yet."
                   purpose="Once the orchestrator starts dispatching tasks, each tick's decision lands here." />
  );
  return (
    <div data-testid="orchestrator-decisions-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>Tick</th>
            <th style={cellHead}>Band</th>
            <th style={cellHead}>In flight</th>
            <th style={cellHead}>Launched</th>
            <th style={cellHead}>Skipped reasons (top)</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(-20).reverse().map((d, i) => (
            <tr key={d.tick_id || i} data-testid={`decision-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(d.tick_id || i).slice(0, 14)}</span></td>
              <td style={cell}><Chip tone={bandToTone(d.band)} label={(d.band || 'nominal').toUpperCase()} /></td>
              <td style={cell}><span className="mono-num">{d.in_flight ?? 0}</span></td>
              <td style={cell}><span className="mono-num">{(d.launched || []).map((l) => l.task_name).join(', ') || '—'}</span></td>
              <td style={cell}>
                {(() => {
                  const skipped = (d.candidates || []).filter((c) => !c.eligible).slice(0, 3);
                  if (skipped.length === 0) return '—';
                  return (
                    <span style={{ color: 'var(--content-md)' }}>
                      {skipped.map((c, k) => (
                        <span key={k} style={{ marginRight: 8 }}>
                          <span style={{ color: 'var(--content-lo)' }}>{c.task_name}:</span> {String(c.reason || '?').slice(0, 40)}
                        </span>
                      ))}
                    </span>
                  );
                })()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

/* ── task registry table ─────────────────────────────────────────────── */

const TaskRegistryTable = ({ status }) => {
  const names = status?.task_names || [];
  const runsOk = status?.counters?.runs_ok || {};
  const runsFail = status?.counters?.runs_fail || {};
  const runsTotal = status?.counters?.runs_total || {};
  const inFlight = new Set((status?.in_flight || []).map((t) => t.task_name));

  if (names.length === 0) return (
    <StateTemplate variant="empty" code="orch-registry-empty" icon={Zap} tone="dormant"
                   headline="No tasks registered."
                   purpose="The orchestrator has not yet reported its task registry." />
  );

  return (
    <div data-testid="orchestrator-registry-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>Task</th>
            <th style={cellHead}>Status</th>
            <th style={cellHead}>Runs</th>
            <th style={cellHead}>OK</th>
            <th style={cellHead}>Fail</th>
            <th style={cellHead}>Fail rate</th>
          </tr>
        </thead>
        <tbody>
          {[...names].sort().map((name) => {
            const ok = runsOk[name] || 0;
            const fail = runsFail[name] || 0;
            const total = runsTotal[name] || (ok + fail);
            const rate = total > 0 ? (fail / total) : 0;
            const rateTone = rate === 0 ? 'ok' : rate < 0.1 ? 'info' : rate < 0.3 ? 'warn' : 'crit';
            const running = inFlight.has(name);
            return (
              <tr key={name} data-testid={`task-row-${name}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
                <td style={cell}><span className="mono-num">{name}</span></td>
                <td style={cell}><Chip tone={running ? 'info' : total > 0 ? 'ok' : 'dormant'} label={running ? 'RUNNING' : total > 0 ? 'IDLE' : 'DORMANT'} /></td>
                <td style={cell}><span className="mono-num">{total}</span></td>
                <td style={cell}><span className="mono-num" style={{ color: 'var(--sig-ok)' }}>{ok}</span></td>
                <td style={cell}><span className="mono-num" style={{ color: fail > 0 ? 'var(--sig-crit)' : 'var(--content-lo)' }}>{fail}</span></td>
                <td style={cell}><Chip tone={rateTone} label={`${(rate * 100).toFixed(1)}%`} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const cellHead = { padding: 'var(--space-3) var(--space-2)', fontWeight: 500 };
const cell     = { padding: 'var(--space-3) var(--space-2)', verticalAlign: 'top' };

/* ── main surface ────────────────────────────────────────────────────── */

export const OrchestratorDashboard = () => {
  const statusQ    = useOrchestratorStatus();
  const decisionsQ = useOrchestratorDecisions(20);
  const historyQ   = useOrchestratorHistory(20);
  const health     = useOrchestratorHealthInputs();

  const status    = statusQ.data;
  const decisions = decisionsQ.data;
  const history   = historyQ.data;

  const alerts = useMemo(() => {
    const out = [];
    if (status?.meta?.last_error) out.push({ tone: 'crit', headline: `Orchestrator error · ${String(status.meta.last_error).slice(0, 80)}` });
    if (!status?.running)         out.push({ tone: 'warn', headline: 'Orchestrator is halted' });
    if (status?.meta?.last_tick?.band === 'critical') out.push({ tone: 'crit', headline: 'Last tick band CRITICAL' });
    const raw = health.provider?.providers;
    const provArr = Array.isArray(raw)
      ? raw
      : (raw && typeof raw === 'object')
        ? Object.entries(raw).map(([name, v]) => ({ name, ...(v || {}) }))
        : [];
    provArr
      .filter((p) => p.circuit === 'open' || p.state === 'open')
      .forEach((p) => out.push({ tone: 'crit', headline: `Provider ${p.name || p.provider || 'unknown'} circuit open` }));
    return out;
  }, [status, health.provider]);

  const lastGoodTick = useMemo(() => {
    if (!Array.isArray(history)) return null;
    const good = [...history].reverse().find((h) => h.ok === true || h.status === 'ok');
    return good?.ts || good?.completed_at || null;
  }, [history]);

  const state = factoryState(status);
  const running = status?.running === true;

  return (
    <section data-testid="orchestrator-dashboard" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      {/* Eyebrow */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Orchestrator</span>
        <SignalStateBadge state={statusQ.isLoading ? 'partial' : status ? 'live' : 'error'}
                          reason={status ? '/api/orchestrator/status · 15s poll' : (statusQ.error ? 'unreachable' : 'loading')}
                          testId="orchestrator-header-signal" />
      </div>

      <h1 data-testid="orchestrator-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Autonomous Research Factory · {state.label}
      </h1>
      <p data-testid="orchestrator-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        Unified Autonomous Orchestration Engine (Phase B.2). {status?.task_names?.length ?? 0} tasks registered.
        {' '}Every mutating decision below is recorded via <span className="mono-num">outcome_events</span> and — under OBSERVE mode — never applied to production strategy state without operator approval.
      </p>

      <SummaryPanel status={status}
                    provider={health.provider}
                    factoryEval={health.factoryEval}
                    metaLearning={health.metaLearning}
                    lastGoodTick={lastGoodTick}
                    alerts={alerts} />

      {/* Metric row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
           data-testid="orchestrator-metric-row">
        <MetricBlock variant="B" eyebrow="TICKS" value={status?.meta?.tick_count ?? 0}
                     deltaLabel={running ? 'LIVE' : 'HALTED'} deltaTone={running ? 'ok' : 'dormant'}
                     state={statusQ.isLoading ? 'loading' : 'happy'}
                     testId="metric-orch-ticks" />
        <MetricBlock variant="A" eyebrow="DISPATCHED" value={status?.meta?.dispatched_total ?? 0}
                     deltaLabel="TOTAL" deltaTone="info"
                     state={statusQ.isLoading ? 'loading' : 'happy'}
                     testId="metric-orch-dispatched" />
        <MetricBlock variant="A" eyebrow="IN FLIGHT" value={(status?.in_flight || []).length}
                     deltaLabel={(status?.in_flight || []).length > 0 ? 'ACTIVE' : 'IDLE'}
                     deltaTone={(status?.in_flight || []).length > 0 ? 'info' : 'dormant'}
                     state={statusQ.isLoading ? 'loading' : 'happy'}
                     testId="metric-orch-in-flight" />
        <MetricBlock variant={alerts.length > 0 ? 'A' : 'A'}
                     eyebrow="ALERTS" value={alerts.length}
                     deltaLabel={alerts.length > 0 ? 'ATTENTION' : 'CLEAR'}
                     deltaTone={alerts.length > 0 ? 'warn' : 'ok'}
                     state={statusQ.isLoading ? 'loading' : 'happy'}
                     testId="metric-orch-alerts" />
      </div>

      {/* Decisions */}
      <SectionHeader icon={GitBranch} title="Recent Decisions (last 20 ticks)" testId="orch-decisions-header" />
      <div style={sectionPanel} data-testid="orchestrator-decisions-panel">
        {decisionsQ.isLoading
          ? <StateTemplate variant="loading" code="orch-decisions-loading" icon={GitBranch} tone="info" headline="Loading decisions…" purpose="/api/orchestrator/decisions" />
          : <DecisionsTable rows={decisions} />}
      </div>

      {/* Registry */}
      <div style={{ marginTop: 'var(--space-6)' }}>
        <SectionHeader icon={Zap} title="Task Registry" testId="orch-registry-header" />
        <div style={sectionPanel} data-testid="orchestrator-registry-panel">
          {statusQ.isLoading
            ? <StateTemplate variant="loading" code="orch-registry-loading" icon={Zap} tone="info" headline="Loading registry…" purpose="/api/orchestrator/status.task_names" />
            : <TaskRegistryTable status={status} />}
        </div>
      </div>

      {/* Footnote */}
      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="orch-refresh-hint">Auto-refresh: 15s · Focus revalidates instantly</span>
        <span style={{ margin: '0 var(--space-3)', color: 'var(--content-lo)' }}>·</span>
        <span>Sources: <span className="mono-num">/api/orchestrator/status</span> · <span className="mono-num">/decisions</span> · <span className="mono-num">/history</span> · <span className="mono-num">/api/ai-workforce/health</span> · <span className="mono-num">/api/factory-eval/config</span> · <span className="mono-num">/api/meta-learning/config</span></span>
      </div>
    </section>
  );
};

const SectionHeader = ({ icon: Icon, title, testId }) => (
  <div data-testid={testId} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
    <Icon size={14} color="var(--content-md)" aria-hidden />
    <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--content-md)' }}>{title}</span>
  </div>
);

const eyebrowLabel = {
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'var(--content-md)',
};

const sectionPanel = {
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-1)',
  borderRadius: 'var(--radius-3)',
  padding: 'var(--space-4)',
};

export default OrchestratorDashboard;
