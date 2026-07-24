/*
 * Mission Control — S1. Six operator questions in one glance.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · D1 · Bible §7.11
 */
import React, { useEffect, useState } from 'react';
import { Bot, Landmark, Cpu, Activity, Sparkles, GitBranch, ClipboardList, ClipboardCheck } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useWorkspaceStore } from '../workspace-state/store';
import { MetricBlock } from '../primitives/MetricBlock';
import { PipelineStageBar } from '../primitives/PipelineStageBar';
import { ChartTile } from '../primitives/ChartTile';
import { ActivityRow } from '../primitives/ActivityRow';
import { Chip } from '../primitives/Chip';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { StateTemplate } from '../primitives/StateTemplate';
import { aggregateMission } from '../adapters/missionAggregator';

const ACTOR_ICON = { governance: Landmark, 'master-bot': Bot, llm: Sparkles,
                     ingestion: Cpu, operator: ClipboardList, validator: Activity,
                     scheduler: GitBranch };

const HEADLINES = {
  operations: 'A busy shift. The Factory needs three human decisions.',
  executive:  'The Factory ran cleanly overnight. No decisions required.',
  research:   'Two research plans progressed. One backtest completed.',
  developer:  'Six services healthy. One worker recovering. Zero errors.',
};

const BRIEFINGS = {
  operations: 'The Factory advanced 12 strategies overnight. Three approvals are aged. One worker is degraded. Kill posture disarmed.',
  executive:  'AUM is up 3.2% week-over-week. Flagship strategy is passing all guardrails. Nothing needs you.',
  research:   'Plan #47 is on epoch 4/6. Backtest-891 attested. Two new proposals from the LLM await triage.',
  developer:  'Ingestion streaming · Scheduler paused (dev) · LLM warm · Governance nominal · Kill posture disarmed.',
};

export const MissionControl = () => {
  const location = useLocation();
  const mode = useWorkspaceStore((s) => s.mode);
  const [bundle, setBundle] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    setErr(null);
    aggregateMission()
      .then((b) => { if (live) setBundle(b); })
      .catch((e) => { if (live) setErr(e); });
    return () => { live = false; };
  }, []);

  if (err) {
    return (
      <div style={{ padding: 'var(--space-6) var(--space-5)' }}>
        <StateTemplate variant="error" code="mc-error" icon={Activity} tone="crit"
                       headline="Mission Control could not assemble the daily brief."
                       purpose="The mission aggregator failed. Retrying every 60s."
                       advancedFootnote={`aggregator@v1 · ${err.message}`} />
      </div>
    );
  }

  const isLoading = !bundle;
  const metrics = bundle?.metrics;
  const timeline = bundle?.timeline ?? [];
  const approvals = bundle?.approvals ?? [];
  const workers = bundle?.workers ?? [];
  const pipeline = bundle?.pipeline ?? [];

  const agedApprovals = approvals.filter((a) => a.ageMinutes >= 60).length;
  const degradedWorkers = workers.filter((w) => ['error', 'blocked'].includes(w.state)).length;

  return (
    <section data-testid="mission-control" data-mode={mode}
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
          <span data-testid="mc-eyebrow"
                style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                         letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Mission control · {mode}
          </span>
        </div>
        <h1 data-testid="mc-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
          {HEADLINES[mode] ?? HEADLINES.operations}
        </h1>
        <p data-testid="mc-briefing"
           style={{ margin: 0, maxWidth: 780, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          {BRIEFINGS[mode] ?? BRIEFINGS.operations}
        </p>
      </div>

      {/* Q1 · What is live · Q2 · What needs me · Q5 · What to watch · R1 · Portfolio equity */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
        <MetricBlock variant="A" eyebrow="Strategies live"
                     value={isLoading ? '—' : metrics.strategiesLive.value}
                     deltaLabel={metrics?.strategiesLive.delta} deltaTone={metrics?.strategiesLive.tone}
                     state={isLoading ? 'loading' : 'happy'}
                     footnote="sha 91a2b · plan #47 · signal-forge@v2" />
        <MetricBlock variant="B" eyebrow="Approvals pending"
                     value={isLoading ? '—' : String(approvals.length)}
                     deltaLabel={agedApprovals ? `${agedApprovals} aged` : 'fresh'} deltaTone={agedApprovals ? 'warn' : 'ok'}
                     state={isLoading ? 'loading' : 'happy'}
                     footnote="aging over 60m" />
        <MetricBlock variant="C" eyebrow="Signals in queue"
                     value={isLoading ? '—' : metrics.signalsInQueue.value}
                     unit={metrics?.signalsInQueue.unit}
                     deltaLabel={metrics?.signalsInQueue.delta} deltaTone={metrics?.signalsInQueue.tone}
                     state={isLoading ? 'loading' : 'happy'}
                     footnote="scheduler@v11" />
        <MetricBlock variant="B" eyebrow="Portfolio equity"
                     value={isLoading ? '—' : metrics.portfolioEquity.value}
                     deltaLabel={metrics?.portfolioEquity.delta} deltaTone={metrics?.portfolioEquity.tone}
                     state={isLoading ? 'loading' : 'happy'}
                     footnote={metrics?.portfolioEquity.drawdown}
                     testId="mc-portfolio-equity" />
      </div>

      {/* Q3 · Factory Pipeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption eyebrow="Factory pipeline" icon={GitBranch}
                         status={`${pipeline.filter((s) => s.status === 'done').length}/${pipeline.length} stages green`}
                         purpose="The Factory advances a strategy through eight canonical stages, from ingest to monitor." />
        <PipelineStageBar stages={pipeline} testId="mc-pipeline" />
      </div>

      {/* Q4 · Throughput chart */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-4)' }}>
        <ChartTile caption="Throughput · signals/hour · last 24h"
                   points={metrics?.throughput ?? []} tone="info"
                   timeWindow="last 24h"
                   state={isLoading ? 'loading' : 'happy'} />

        {/* Q5 · Approvals summary */}
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', padding: 'var(--space-4)',
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Approvals summary
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <Chip tone="ok" label={`low · ${approvals.filter((a) => a.risk === 'low').length}`} showGlyph={false} />
            <Chip tone="advisory" label={`moderate · ${approvals.filter((a) => a.risk === 'moderate').length}`} showGlyph={false} />
            <Chip tone="crit" label={`high · ${approvals.filter((a) => a.risk === 'high').length}`} showGlyph={false} />
          </div>
          <a href="/c/approvals"
             data-testid="mc-open-approvals"
             style={{ color: 'var(--sig-info)', textDecoration: 'none',
                      fontSize: 'var(--font-body-sm)', marginTop: 'auto' }}>
            → open approval center
          </a>
        </div>
      </div>

      {/* Q6 · Latest activity */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption eyebrow="Latest activity" icon={Activity}
                         status={`${timeline.length} recent events`}
                         purpose="A ranked feed of the last few decisions the Factory took." />
        <div data-testid="mc-timeline"
             role="list"
             aria-label="Latest factory activity"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', overflow: 'hidden' }}>
          {isLoading ? (
            <div style={{ padding: 'var(--space-4)', color: 'var(--content-lo)',
                          fontSize: 'var(--font-body-sm)' }}>Loading latest activity…</div>
          ) : (
            timeline.map((e) => (
              <ActivityRow key={e.id}
                           timestamp={e.timestamp}
                           actor={{ kind: e.actorKind, name: e.actorName, icon: ACTOR_ICON[e.actorKind] }}
                           verb={e.verb}
                           subject={e.subject}
                           outcome={e.outcome}
                           trailer={e.trailer} />
            ))
          )}
        </div>
      </div>

      {/* Evaluation Harness discovery affordance · Phase D1.
          Subtle link — mirrors the Phase B/C pattern. Read-only preview. */}
      <a
        href="/c/evaluation"
        data-testid="mc-open-evaluation"
        style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
          padding: 'var(--space-3) var(--space-4)',
          background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
          borderRadius: 'var(--radius-2)', textDecoration: 'none', color: 'inherit',
        }}
      >
        <ClipboardCheck size={14} color="var(--content-md)" aria-hidden />
        <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em',
                        textTransform: 'uppercase', color: 'var(--content-md)' }}>
          Interactive Prototype Gate
        </span>
        <Chip tone="info" label="D1 preview" showGlyph={false}
              testId="mc-open-evaluation-badge" />
        <span style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                        color: 'var(--content-lo)' }}>
          Open Evaluation Harness →
        </span>
      </a>

      {/* Partial-failure notice · Sprint 2 N4 · Promise.allSettled slots */}
      {bundle?.partial?.length > 0 && (
        <div data-testid="mc-partial-notice"
             role="status"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--sig-warn)',
                      borderRadius: 'var(--radius-3)', padding: 'var(--space-3) var(--space-4)',
                      fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--sig-warn)',
                        textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
            Partial — {bundle.partial.length} data slot{bundle.partial.length > 1 ? 's' : ''} unavailable
          </div>
          {bundle.partial.map((p) => (
            <span key={p.slot} data-testid={`mc-partial-${p.slot}`} className="mono-num"
                  style={{ marginRight: 12, color: 'var(--content-lo)' }}>
              {p.slot} · {p.error?.slice(0, 60)}
            </span>
          ))}
        </div>
      )}

      {/* System attention (degraded workers) */}
      {degradedWorkers > 0 && (
        <div data-testid="mc-attention"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--sig-warn)',
                      borderRadius: 'var(--radius-3)', padding: 'var(--space-4)',
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--sig-warn)',
                        textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Attention · {degradedWorkers} worker{degradedWorkers > 1 ? 's' : ''} degraded
          </div>
          <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
            {workers.filter((w) => ['error', 'blocked'].includes(w.state))
                    .map((w) => `${w.name} · ${w.state}`).join(' · ')}
          </div>
          <a href="/c/workforce" data-testid="mc-open-workforce"
             style={{ color: 'var(--sig-info)', textDecoration: 'none',
                                          fontSize: 'var(--font-body-sm)', marginTop: 'var(--space-1)' }}>
            → open AI workforce
          </a>
        </div>
      )}
    </section>
  );
};
