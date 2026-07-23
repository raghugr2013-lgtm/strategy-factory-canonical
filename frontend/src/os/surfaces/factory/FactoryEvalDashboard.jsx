/*
 * FactoryEvalDashboard — FE-B Slice 3.
 * refs docs/FE_B_PROPOSAL.md · docs/CAPABILITY_INVENTORY.md
 *
 * Read-only surface. Consumes pre-existing endpoints only:
 *   • GET /api/factory-eval/status
 *   • GET /api/factory-eval/config
 *   • GET /api/factory-eval/health
 *   • GET /api/factory-eval/kpis
 *   • GET /api/factory-eval/reports/latest
 *   • GET /api/factory-eval/insights
 *   • GET /api/factory-eval/recommendations
 *   • GET /api/factory-eval/pending
 *   • GET /api/factory-eval/coverage-gaps
 */
import React, { useMemo } from 'react';
import { Gauge, Lightbulb, ListChecks, Target, ClipboardCheck } from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge } from '../engineering/LivenessBadge';
import {
  useFactoryEvalStatus, useFactoryEvalConfig, useFactoryEvalHealth,
  useFactoryEvalKpis, useFactoryEvalLatestReport,
  useFactoryEvalInsights, useFactoryEvalRecommendations, useFactoryEvalPending,
  useFactoryEvalCoverageGaps,
} from '../../adapters/factoryEvalAdapter';
import {
  SummaryPanel, SectionHeader, sectionPanel, eyebrowLabel, cell, cellHead,
  fmtISO, fmtRel, asArray, modeToTone, deriveHealth,
} from './factoryPrimitives';

const decisionTone = (d) => {
  const s = String(d || '').toLowerCase();
  if (s === 'approved' || s === 'applied' || s === 'accepted' || s === 'green' || s === 'pass') return 'ok';
  if (s === 'rejected' || s === 'reverted' || s === 'failed' || s === 'red' || s === 'fail') return 'crit';
  if (s === 'pending' || s === 'waiting' || s === 'proposed' || s === 'amber' || s === 'warn') return 'warn';
  return 'info';
};

const InsightsTable = ({ rows }) => {
  if (!rows || rows.length === 0) return (
    <StateTemplate variant="empty" code="fe-insights-empty" icon={Lightbulb} tone="dormant"
                   headline="No insights yet."
                   purpose="Factory Evaluation has not surfaced new insights in the current window." />
  );
  return (
    <div data-testid="fe-insights-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>ID</th>
            <th style={cellHead}>Kind</th>
            <th style={cellHead}>Headline</th>
            <th style={cellHead}>Severity</th>
            <th style={cellHead}>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((r, i) => (
            <tr key={r.id || r.insight_id || i} data-testid={`fe-insight-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(r.id || r.insight_id || i).slice(0, 12)}</span></td>
              <td style={cell}><span className="mono-num">{r.kind || r.category || r.type || '—'}</span></td>
              <td style={cell} title={r.headline || r.summary || ''}>{String(r.headline || r.summary || r.message || '—').slice(0, 100)}</td>
              <td style={cell}><Chip tone={decisionTone(r.severity || r.tone || r.level)} label={String(r.severity || r.tone || r.level || 'info').toUpperCase()} /></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(r.ts || r.timestamp || r.created_at)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const KpiGrid = ({ kpis }) => {
  const entries = useMemo(() => {
    if (!kpis) return [];
    if (Array.isArray(kpis)) return kpis;
    if (typeof kpis !== 'object') return [];
    if (Array.isArray(kpis.kpis)) return kpis.kpis;
    if (Array.isArray(kpis.metrics)) return kpis.metrics;
    // convert plain map into entries
    return Object.entries(kpis)
      .filter(([, v]) => v !== null && v !== undefined && (typeof v !== 'object' || Array.isArray(v) === false))
      .map(([k, v]) => ({ name: k, value: v }));
  }, [kpis]);

  if (entries.length === 0) return (
    <StateTemplate variant="empty" code="fe-kpi-empty" icon={Gauge} tone="dormant"
                   headline="No KPIs available."
                   purpose="The evaluator has not published a KPI snapshot in the current window." />
  );

  return (
    <div data-testid="fe-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-3)' }}>
      {entries.slice(0, 16).map((e, i) => {
        const label = (e.name || e.label || `kpi-${i}`).toString();
        const raw = e.value ?? e.metric ?? e.score ?? '—';
        const value = (typeof raw === 'object' && raw !== null) ? (raw.value ?? raw.score ?? JSON.stringify(raw).slice(0, 20)) : String(raw);
        return (
          <div key={label + i} data-testid={`fe-kpi-${i}`} style={{
            display: 'flex', flexDirection: 'column', gap: 'var(--space-1)',
            padding: 'var(--space-3)', background: 'var(--surface-1)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)',
          }}>
            <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--content-lo)' }}>{label}</span>
            <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-body-md)' }}>{value}</span>
          </div>
        );
      })}
    </div>
  );
};

export const FactoryEvalDashboard = () => {
  const statusQ  = useFactoryEvalStatus();
  const configQ  = useFactoryEvalConfig();
  const healthQ  = useFactoryEvalHealth();
  const kpisQ    = useFactoryEvalKpis();
  const reportQ  = useFactoryEvalLatestReport();
  const insQ     = useFactoryEvalInsights(20);
  const recsQ    = useFactoryEvalRecommendations(20);
  const pendQ    = useFactoryEvalPending();
  const gapsQ    = useFactoryEvalCoverageGaps();

  const status = statusQ.data;
  const config = configQ.data;
  const health = healthQ.data;
  const kpis   = kpisQ.data;
  const report = reportQ.data;

  const insights        = asArray(insQ.data, 'insights');
  const recommendations = asArray(recsQ.data, 'recommendations');
  const pending         = asArray(pendQ.data, 'pending');
  const gaps            = asArray(gapsQ.data, 'gaps');

  const mode = (config?.mode || status?.mode || 'unknown');
  const h = deriveHealth(health);
  const reportTs = report?.ts || report?.timestamp || report?.created_at || null;
  const overall = report?.overall || report?.verdict || report?.grade || report?.status || null;

  const cells = useMemo(() => ([
    { label: 'Mode',                tone: modeToTone(mode),                       value: String(mode).toUpperCase(),        sub: 'factory-eval', testId: 'fe-cell-mode' },
    { label: 'Health',              tone: h.tone,                                  value: h.label,                            sub: '/api/factory-eval/health', testId: 'fe-cell-health' },
    { label: 'Latest Verdict',      tone: overall ? decisionTone(overall) : 'dormant', value: overall ? String(overall).toUpperCase() : 'NONE',       sub: reportTs ? fmtRel(reportTs) : 'no reports', testId: 'fe-cell-verdict' },
    { label: 'Insights',            tone: insights.length > 0 ? 'info' : 'dormant', value: `${insights.length}`, sub: 'current window', testId: 'fe-cell-insights' },
    { label: 'Recommendations',     tone: recommendations.length > 0 ? 'info' : 'dormant', value: `${recommendations.length}`, sub: 'current window', testId: 'fe-cell-recommendations' },
    { label: 'Pending Approvals',   tone: pending.length > 0 ? 'warn' : 'ok', value: `${pending.length}`, sub: pending.length > 0 ? 'operator action' : 'none pending', testId: 'fe-cell-pending' },
    { label: 'Coverage Gaps',       tone: gaps.length > 0 ? 'warn' : 'ok', value: `${gaps.length}`, sub: 'evaluator-flagged', testId: 'fe-cell-gaps' },
    { label: 'Window',              tone: 'info', value: config?.window || config?.evaluation_window || '—', sub: 'evaluation window', testId: 'fe-cell-window' },
  ]), [mode, h, overall, reportTs, insights, recommendations, pending, gaps, config]);

  return (
    <section data-testid="factory-eval-dashboard" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Evaluation &amp; KPI</span>
        <SignalStateBadge state={statusQ.isLoading ? 'partial' : (status || config || kpis) ? 'live' : 'error'}
                          reason={(status || config || kpis) ? '/api/factory-eval/*' : 'unreachable'}
                          testId="fe-header-signal" />
      </div>

      <h1 data-testid="fe-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Factory Evaluation · {String(mode).toUpperCase()}
      </h1>
      <p data-testid="fe-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        The Factory Evaluator grades the autonomous stack — data pipeline · generation · validation · execution — and
        publishes KPIs, insights, and change proposals. Under OBSERVE mode nothing is applied without operator approval.
      </p>

      <SummaryPanel testId="factory-eval-summary-panel"
                    signalState={(status || config || kpis) ? 'live' : 'deferred'}
                    signalReason={(status || config || kpis) ? '/api/factory-eval/*' : 'endpoint unreachable'}
                    cells={cells} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
           data-testid="fe-metric-row">
        <MetricBlock variant="B" eyebrow="INSIGHTS" value={insights.length}
                     deltaLabel="WINDOW" deltaTone="info"
                     state={insQ.isLoading ? 'loading' : 'happy'} testId="metric-fe-insights" />
        <MetricBlock variant="A" eyebrow="RECOMMENDATIONS" value={recommendations.length}
                     deltaLabel="WINDOW" deltaTone="info"
                     state={recsQ.isLoading ? 'loading' : 'happy'} testId="metric-fe-recommendations" />
        <MetricBlock variant="A" eyebrow="PENDING" value={pending.length}
                     deltaLabel={pending.length > 0 ? 'ACTION' : 'CLEAR'} deltaTone={pending.length > 0 ? 'warn' : 'ok'}
                     state={pendQ.isLoading ? 'loading' : 'happy'} testId="metric-fe-pending" />
        <MetricBlock variant="A" eyebrow="COVERAGE GAPS" value={gaps.length}
                     deltaLabel={gaps.length > 0 ? 'ATTENTION' : 'CLEAR'} deltaTone={gaps.length > 0 ? 'warn' : 'ok'}
                     state={gapsQ.isLoading ? 'loading' : 'happy'} testId="metric-fe-gaps" />
      </div>

      <SectionHeader icon={Gauge} title="KPI Snapshot" testId="fe-kpi-header" />
      <div style={sectionPanel} data-testid="fe-kpi-panel">
        {kpisQ.isLoading
          ? <StateTemplate variant="loading" code="fe-kpi-loading" icon={Gauge} tone="info" headline="Loading KPIs…" purpose="/api/factory-eval/kpis" />
          : <KpiGrid kpis={kpis} />}
      </div>

      <div style={{ marginTop: 'var(--space-6)' }}>
        <SectionHeader icon={Lightbulb} title="Insights (recent)" testId="fe-insights-header" />
        <div style={sectionPanel} data-testid="fe-insights-panel">
          {insQ.isLoading
            ? <StateTemplate variant="loading" code="fe-insights-loading" icon={Lightbulb} tone="info" headline="Loading insights…" purpose="/api/factory-eval/insights" />
            : <InsightsTable rows={insights} />}
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="fe-refresh-hint">Auto-refresh: 15s · Focus revalidates instantly</span>
        <span style={{ margin: '0 var(--space-3)', color: 'var(--content-lo)' }}>·</span>
        <span>Sources: <span className="mono-num">/api/factory-eval/{'{status,config,health,kpis,reports/latest,insights,recommendations,pending,coverage-gaps}'}</span></span>
      </div>
    </section>
  );
};

export default FactoryEvalDashboard;
