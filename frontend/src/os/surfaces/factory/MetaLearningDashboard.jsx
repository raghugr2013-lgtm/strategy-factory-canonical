/*
 * MetaLearningDashboard — FE-B Slice 2.
 * refs docs/FE_B_PROPOSAL.md · docs/CAPABILITY_INVENTORY.md
 *
 * Read-only surface. Consumes pre-existing endpoints only:
 *   • GET /api/meta-learning/status
 *   • GET /api/meta-learning/config
 *   • GET /api/meta-learning/health
 *   • GET /api/meta-learning/evaluations
 *   • GET /api/meta-learning/recommendations
 *   • GET /api/meta-learning/pending
 *   • GET /api/meta-learning/applications
 *   • GET /api/meta-learning/overrides
 *
 * Reuses MetricBlock · Chip · StateTemplate · SignalStateBadge · FreezeCaption.
 */
import React, { useMemo } from 'react';
import { Brain, Sparkles, ListChecks, Layers, ClipboardCheck } from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge } from '../engineering/LivenessBadge';
import {
  useMetaLearningStatus, useMetaLearningConfig, useMetaLearningHealth,
  useMetaLearningEvaluations, useMetaLearningRecommendations, useMetaLearningPending,
  useMetaLearningApplications, useMetaLearningOverrides,
} from '../../adapters/metaLearningAdapter';
import {
  SummaryPanel, SectionHeader, sectionPanel, eyebrowLabel, cell, cellHead,
  fmtISO, fmtRel, asArray, modeToTone, deriveHealth,
} from './factoryPrimitives';

const decisionTone = (d) => {
  const s = String(d || '').toLowerCase();
  if (s === 'approved' || s === 'applied' || s === 'accepted') return 'ok';
  if (s === 'rejected' || s === 'reverted' || s === 'failed') return 'crit';
  if (s === 'pending' || s === 'waiting' || s === 'proposed') return 'warn';
  return 'info';
};

const RecommendationsTable = ({ rows }) => {
  if (!rows || rows.length === 0) return (
    <StateTemplate variant="empty" code="ml-recs-empty" icon={Sparkles} tone="dormant"
                   headline="No recommendations yet."
                   purpose="Meta-Learning has not produced any recommendations in the current window." />
  );
  return (
    <div data-testid="ml-recommendations-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>ID</th>
            <th style={cellHead}>Target</th>
            <th style={cellHead}>Rationale</th>
            <th style={cellHead}>Status</th>
            <th style={cellHead}>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((r, i) => (
            <tr key={r.id || r.recommendation_id || i} data-testid={`ml-rec-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(r.id || r.recommendation_id || i).slice(0, 12)}</span></td>
              <td style={cell}><span className="mono-num">{r.target || r.target_scope || r.scope || '—'}</span></td>
              <td style={cell} title={r.rationale || r.reason || ''}>{String(r.rationale || r.reason || '—').slice(0, 80)}</td>
              <td style={cell}><Chip tone={decisionTone(r.status || r.decision)} label={String(r.status || r.decision || 'pending').toUpperCase()} /></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(r.created_at || r.ts || r.timestamp)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const EvaluationsTable = ({ rows }) => {
  if (!rows || rows.length === 0) return (
    <StateTemplate variant="empty" code="ml-evals-empty" icon={ClipboardCheck} tone="dormant"
                   headline="No evaluations yet."
                   purpose="Meta-Learning has not produced any evaluation runs in the current window." />
  );
  return (
    <div data-testid="ml-evaluations-table" style={{ overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
            <th style={cellHead}>ID</th>
            <th style={cellHead}>Kind</th>
            <th style={cellHead}>Result</th>
            <th style={cellHead}>When</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((e, i) => (
            <tr key={e.id || e.evaluation_id || i} data-testid={`ml-eval-row-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
              <td style={cell}><span className="mono-num">{String(e.id || e.evaluation_id || i).slice(0, 12)}</span></td>
              <td style={cell}><span className="mono-num">{e.kind || e.type || e.stage || '—'}</span></td>
              <td style={cell}><Chip tone={decisionTone(e.outcome || e.result || e.status)} label={String(e.outcome || e.result || e.status || 'unknown').toUpperCase()} /></td>
              <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{fmtRel(e.ts || e.timestamp || e.created_at)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const MetaLearningDashboard = () => {
  const statusQ = useMetaLearningStatus();
  const configQ = useMetaLearningConfig();
  const healthQ = useMetaLearningHealth();
  const evalsQ  = useMetaLearningEvaluations(20);
  const recsQ   = useMetaLearningRecommendations(20);
  const pendQ   = useMetaLearningPending();
  const appsQ   = useMetaLearningApplications(20);
  const ovrQ    = useMetaLearningOverrides();

  const status = statusQ.data;
  const config = configQ.data;
  const health = healthQ.data;

  const evaluations    = asArray(evalsQ.data, 'evaluations');
  const recommendations = asArray(recsQ.data, 'recommendations');
  const pending        = asArray(pendQ.data, 'pending');
  const applications   = asArray(appsQ.data, 'applications');
  const overrides      = asArray(ovrQ.data, 'overrides');

  const mode = (config?.mode || status?.mode || 'unknown');
  const h = deriveHealth(health);
  const lastEvalTs = evaluations[0]?.ts || evaluations[0]?.timestamp || evaluations[0]?.created_at || null;

  const cells = useMemo(() => ([
    { label: 'Mode',                tone: modeToTone(mode),          value: String(mode).toUpperCase(),        sub: 'meta-learning', testId: 'ml-cell-mode' },
    { label: 'Health',              tone: h.tone,                     value: h.label,                            sub: '/api/meta-learning/health', testId: 'ml-cell-health' },
    { label: 'Evaluations',         tone: evaluations.length > 0 ? 'info' : 'dormant', value: `${evaluations.length}`, sub: `last: ${fmtRel(lastEvalTs)}`, testId: 'ml-cell-evaluations' },
    { label: 'Recommendations',     tone: recommendations.length > 0 ? 'info' : 'dormant', value: `${recommendations.length}`, sub: 'in current window', testId: 'ml-cell-recommendations' },
    { label: 'Pending Approvals',   tone: pending.length > 0 ? 'warn' : 'ok', value: `${pending.length}`, sub: pending.length > 0 ? 'operator action' : 'none pending', testId: 'ml-cell-pending' },
    { label: 'Applied Changes',     tone: applications.length > 0 ? 'info' : 'dormant', value: `${applications.length}`, sub: 'in current window', testId: 'ml-cell-applications' },
    { label: 'Active Overrides',    tone: overrides.length > 0 ? 'warn' : 'ok', value: `${overrides.length}`, sub: 'operator-set', testId: 'ml-cell-overrides' },
    { label: 'Window',              tone: 'info', value: config?.window || config?.evaluation_window || '—', sub: 'evaluation window', testId: 'ml-cell-window' },
  ]), [mode, h, evaluations, recommendations, pending, applications, overrides, config, lastEvalTs]);

  return (
    <section data-testid="meta-learning-dashboard" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Meta-Learning</span>
        <SignalStateBadge state={statusQ.isLoading ? 'partial' : (status || config || health) ? 'live' : 'error'}
                          reason={(status || config || health) ? '/api/meta-learning/*' : 'unreachable'}
                          testId="ml-header-signal" />
      </div>

      <h1 data-testid="ml-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Meta-Learning · {String(mode).toUpperCase()}
      </h1>
      <p data-testid="ml-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        Meta-Learning observes the factory's outcomes and proposes parameter refinements. Under OBSERVE mode no
        recommendation is applied without operator approval. Every application is recorded in the applications ledger
        and every operator override lives in the overrides table.
      </p>

      <SummaryPanel testId="meta-learning-summary-panel"
                    signalState={(status || config || health) ? 'live' : 'deferred'}
                    signalReason={(status || config || health) ? '/api/meta-learning/*' : 'endpoint unreachable'}
                    cells={cells} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
           data-testid="ml-metric-row">
        <MetricBlock variant="B" eyebrow="EVALUATIONS" value={evaluations.length}
                     deltaLabel={lastEvalTs ? 'RECENT' : 'IDLE'} deltaTone={lastEvalTs ? 'info' : 'dormant'}
                     state={evalsQ.isLoading ? 'loading' : 'happy'} testId="metric-ml-evaluations" />
        <MetricBlock variant="A" eyebrow="RECOMMENDATIONS" value={recommendations.length}
                     deltaLabel="WINDOW" deltaTone="info"
                     state={recsQ.isLoading ? 'loading' : 'happy'} testId="metric-ml-recommendations" />
        <MetricBlock variant="A" eyebrow="PENDING" value={pending.length}
                     deltaLabel={pending.length > 0 ? 'ACTION' : 'CLEAR'} deltaTone={pending.length > 0 ? 'warn' : 'ok'}
                     state={pendQ.isLoading ? 'loading' : 'happy'} testId="metric-ml-pending" />
        <MetricBlock variant="A" eyebrow="APPLIED" value={applications.length}
                     deltaLabel={applications.length > 0 ? 'RECORDED' : 'NONE'} deltaTone={applications.length > 0 ? 'info' : 'dormant'}
                     state={appsQ.isLoading ? 'loading' : 'happy'} testId="metric-ml-applications" />
      </div>

      <SectionHeader icon={Sparkles} title="Recommendations (recent)" testId="ml-recommendations-header" />
      <div style={sectionPanel} data-testid="ml-recommendations-panel">
        {recsQ.isLoading
          ? <StateTemplate variant="loading" code="ml-recs-loading" icon={Sparkles} tone="info" headline="Loading recommendations…" purpose="/api/meta-learning/recommendations" />
          : <RecommendationsTable rows={recommendations} />}
      </div>

      <div style={{ marginTop: 'var(--space-6)' }}>
        <SectionHeader icon={ListChecks} title="Evaluations (recent)" testId="ml-evaluations-header" />
        <div style={sectionPanel} data-testid="ml-evaluations-panel">
          {evalsQ.isLoading
            ? <StateTemplate variant="loading" code="ml-evals-loading" icon={ListChecks} tone="info" headline="Loading evaluations…" purpose="/api/meta-learning/evaluations" />
            : <EvaluationsTable rows={evaluations} />}
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="ml-refresh-hint">Auto-refresh: 15s · Focus revalidates instantly</span>
        <span style={{ margin: '0 var(--space-3)', color: 'var(--content-lo)' }}>·</span>
        <span>Sources: <span className="mono-num">/api/meta-learning/{'{status,config,health,evaluations,recommendations,pending,applications,overrides}'}</span></span>
      </div>
    </section>
  );
};

export default MetaLearningDashboard;
