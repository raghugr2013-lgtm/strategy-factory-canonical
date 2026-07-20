/*
 * PrimitiveGallery — PROTOTYPE ONLY.
 * Single route showing all 13 primitives across 5 logical sections:
 *   Foundations · Data · Workflow · Decision · Evidence
 *
 * The Inspector panel drives representative states so we can validate the
 * full state grid (happy/loading/empty/error/dormant), density, mode,
 * advanced lens, reduced motion, and long-content examples without leaving
 * the page.
 */
import { useState } from 'react';
import {
  Activity, Bot, Cpu, GitBranch, ShieldCheck, Sparkles, Users, Zap,
} from 'lucide-react';
import { useInspectorStore } from '../workspace-state/inspectorStore';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { KeyboardShortcut, KeyboardShortcutHUD } from '../primitives/KeyboardShortcutHUD';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { MetricBlock } from '../primitives/MetricBlock';
import { ChartTile } from '../primitives/ChartTile';
import { TableTile, type TableColumn } from '../primitives/TableTile';
import { PipelineStageBar } from '../primitives/PipelineStageBar';
import { ActivityRow } from '../primitives/ActivityRow';
import { WorkerCard } from '../primitives/WorkerCard';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { LineageBar } from '../primitives/LineageBar';
import { ProvenanceTriple } from '../primitives/ProvenanceTriple';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';
import { artefactRows, priceSeries, spark, longText, type ArtefactRow } from './fixtures';

const Section: React.FC<{ code: string; title: string; blurb: string; children: React.ReactNode }> = ({
  code, title, blurb, children,
}) => (
  <section
    data-testid={`section-${code}`}
    style={{
      display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
      padding: 'var(--space-6) 0',
      borderTop: '1px solid var(--stroke-1)',
    }}
  >
    <header style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div
        style={{
          fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
          textTransform: 'uppercase', letterSpacing: '0.08em',
        }}
      >
        {code}
      </div>
      <h3 style={{ margin: 0, fontSize: 'var(--font-h3)', color: 'var(--content-hi)', fontWeight: 500 }}>
        {title}
      </h3>
      <p style={{ margin: 0, fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', maxWidth: '68ch' }}>
        {blurb}
      </p>
    </header>
    {children}
  </section>
);

export const PrimitiveGallery: React.FC = () => {
  const { canonicalState, longContent } = useInspectorStore();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const cols: TableColumn<ArtefactRow>[] = [
    { key: 'id',     label: 'artefact',  sortable: true  },
    { key: 'kind',   label: 'kind',      sortable: true  },
    { key: 'worker', label: 'worker',    sortable: true  },
    { key: 'status', label: 'status',    sortable: true  },
    { key: 'age',    label: 'age (h)',   sortable: true, align: 'right',
      render: (r) => r.age.toFixed(1) },
  ];

  const chartPoints = canonicalState === 'empty' ? [] : priceSeries;
  const tableRows   = canonicalState === 'empty' ? [] : artefactRows;

  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column',
        gap: 'var(--space-6)',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <header style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div
            style={{
              fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}
          >
            Prototype · Phase 2 · Primitive Gallery
          </div>
          <h1 style={{ margin: 0, fontSize: 'var(--font-h2)', color: 'var(--content-hi)', fontWeight: 500 }}>
            The reusable visual language of the Factory.
          </h1>
          <p style={{ margin: 0, fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', maxWidth: '72ch' }}>
            13 primitives grouped into five families — Foundations, Data, Workflow,
            Decision, Evidence. Every element uses the design tokens, honours the
            four canonical states, exposes <span className="mono-num">data-testid</span> attributes,
            and respects the operator's reduced-motion preference. Use the
            Inspector sheet (◆ PROTO in the header) to drive state permutations.
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
            <Chip tone="info" label="tokens only" />
            <Chip tone="ok" label="a11y focus" />
            <Chip tone="advisory" label="prototype" />
            <span style={{ marginLeft: 'auto' }}>
              <KeyboardShortcut chord="?" label="shortcuts" />
            </span>
          </div>
        </header>

        {/* ─── Foundations ─────────────────────────────────────────────── */}
        <Section
          code="F · foundations"
          title="Chrome, framing, captions, keyboard."
          blurb="Elements that give every surface consistent structure and rhythm."
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <SignatureFrame tone="info" icon={Sparkles} caption="Signature frame · info">
              <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
                A gallery card for charts and G-graphics. Never carries a decorative shadow.
              </div>
            </SignatureFrame>
            <SignatureFrame tone="gold" icon={Sparkles} caption="Signature frame · executive">
              <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
                Concept C variant — subtle gold rail for Executive mode narrative surfaces.
              </div>
            </SignatureFrame>
            <SignatureFrame tone="crit" caption="Signature frame · critical">
              <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
                Critical tone — used for kill-posture and governance freezes.
              </div>
            </SignatureFrame>
          </div>

          <DivisionCaption
            eyebrow="Master Bot · workforce"
            purpose="Coordinates every research plan across ingest, feature, signal, backtest."
            icon={Bot}
            status="v55 · plan #47 · 3/7"
          />

          <div
            style={{
              display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)',
              alignItems: 'center',
              background: 'var(--surface-1)',
              border: '1px solid var(--stroke-1)',
              borderRadius: 'var(--radius-2)',
              padding: 'var(--space-4)',
            }}
          >
            <span
              style={{
                fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                textTransform: 'uppercase', letterSpacing: '0.08em',
              }}
            >
              Keyboard shortcuts
            </span>
            <KeyboardShortcut chord="⌘K" label="find" />
            <KeyboardShortcut chord="⌘/" label="advanced lens" />
            <KeyboardShortcut chord="g m" label="mission" />
            <KeyboardShortcut chord="?" label="open HUD" />
          </div>

          <div
            style={{
              display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)',
              alignItems: 'center',
            }}
          >
            <span
              style={{
                fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                textTransform: 'uppercase', letterSpacing: '0.08em',
              }}
            >
              Chips ·
            </span>
            <Chip tone="ok"       label="passing"  />
            <Chip tone="info"     label="active"   />
            <Chip tone="warn"     label="warning"  />
            <Chip tone="crit"     label="failing"  />
            <Chip tone="advisory" label="advisory" />
            <Chip tone="dormant"  label="dormant"  />
          </div>
        </Section>

        {/* ─── Data ─────────────────────────────────────────────────────── */}
        <Section
          code="D · data"
          title="Metrics, charts, tables."
          blurb="The Widget Trichotomy — every dashboard tile is exactly one of these three primitives."
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <MetricBlock
              variant="A" eyebrow="strategies live" value="18" unit="of 22"
              deltaLabel="+2 vs yesterday" deltaTone="ok"
              footnote="24h window · 5m refresh · owner: ops"
              state={canonicalState}
              testId="metric-live"
            />
            <MetricBlock
              variant="B" eyebrow="signals in queue" value="47"
              deltaLabel="+11 last hour" deltaTone="info"
              footnote="scheduler@v9 · queue depth healthy"
              state={canonicalState}
              testId="metric-queue"
            />
            <MetricBlock
              variant="C" eyebrow="approval SLA" value="14m"
              deltaLabel="under target 30m" deltaTone="ok"
              footnote="p95 · aged approvals highlighted"
              state={canonicalState}
              testId="metric-sla"
            />
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <ChartTile
              caption="factory throughput"
              points={chartPoints}
              tone="info"
              timeWindow="last 24h"
              state={canonicalState}
              onDrill={() => {}}
              testId="chart-throughput"
            />
            <ChartTile
              caption="ingestion latency"
              points={chartPoints.map((p) => p * 0.7 + 20)}
              tone="warn"
              timeWindow="last 6h"
              unit="ms"
              state={canonicalState}
              testId="chart-latency"
            />
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                textTransform: 'uppercase', letterSpacing: '0.08em',
              }}
            >
              Sparklines ·
            </span>
            <ChartTile caption="strat 001" points={spark} variant="sparkline" tone="ok" state={canonicalState} />
            <ChartTile caption="strat 002" points={spark.map((p) => p * 0.6)} variant="sparkline" tone="crit" state={canonicalState} />
            <ChartTile caption="strat 003" points={spark.map((p) => p * 1.2)} variant="sparkline" tone="advisory" state={canonicalState} />
          </div>

          <TableTile
            caption="recent artefacts"
            columns={cols}
            rows={tableRows}
            state={canonicalState}
            onRowActivate={() => setDrawerOpen(true)}
            testId="table-artefacts"
          />
        </Section>

        {/* ─── Workflow ─────────────────────────────────────────────────── */}
        <Section
          code="W · workflow"
          title="Pipeline, activity, workforce."
          blurb="The rhythm of the Factory. Every stage tells you where work lives right now."
        >
          <PipelineStageBar />

          <SignatureFrame tone="info" caption="AI activity · last 60 minutes">
            <div role="list" style={{ display: 'flex', flexDirection: 'column' }}>
              <ActivityRow
                timestamp="15:04:12" actor={{ kind: 'master-bot', icon: Bot }}
                verb="dispatched" subject="plan #47 · step 3"
                outcome={{ tone: 'info', label: 'active' }}
                trailer="sha 91a2ce…"
                onOpen={() => setDrawerOpen(true)}
              />
              <ActivityRow
                timestamp="15:03:41" actor={{ kind: 'worker', icon: Cpu, name: 'signal-forge@v2' }}
                verb="generated" subject="sig-8f2"
                outcome={{ tone: 'ok', label: 'passing' }}
                trailer="epoch 4/6"
              />
              <ActivityRow
                timestamp="15:02:58" actor={{ kind: 'ingestion', icon: Activity }}
                verb="closed candle" subject="AAPL 15:00Z"
                outcome={{ tone: 'ok', label: 'passing' }}
              />
              <ActivityRow
                timestamp="15:01:12" actor={{ kind: 'governance', icon: ShieldCheck }}
                verb="held" subject="strat-014-schema-v3"
                outcome={{ tone: 'warn', label: 'review' }}
                trailer="policy v2.1 §8.4"
              />
              <ActivityRow
                timestamp="14:59:33" actor={{ kind: 'llm', icon: Zap }}
                verb="drafted" subject="brief · daily 2026-02-04"
                outcome={{ tone: 'info', label: 'draft' }}
              />
            </div>
          </SignatureFrame>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <WorkerCard
              name="signal-forge@v2"
              purpose={longContent
                ? longText
                : "Generates candidate signals from the feature store; hands off to the backtest suite."}
              subject="sig-8f2"
              state={canonicalState === 'happy' ? 'active' : canonicalState === 'error' ? 'error' : canonicalState === 'empty' ? 'idle' : canonicalState === 'dormant' ? 'dormant' : 'blocked'}
              icon={Cpu}
              onOpen={() => setDrawerOpen(true)}
            />
            <WorkerCard
              name="candle-pipe@v3"
              purpose="Assembles OHLCV candles from raw tick streams."
              subject="cdl-90d"
              state="active"
              icon={Activity}
            />
            <WorkerCard
              name="backtest-suite@v4"
              purpose="Evaluates candidate signals against the shadowed book."
              subject="bt-19a"
              state="idle"
              icon={Users}
            />
            <WorkerCard
              name="governance-warden@v1"
              purpose="Holds any artefact that violates a policy contract."
              subject="strat-014-schema-v3"
              state="blocked"
              icon={ShieldCheck}
            />
          </div>
        </Section>

        {/* ─── Decision ─────────────────────────────────────────────────── */}
        <Section
          code="X · decision"
          title="Approvals — the human gate."
          blurb="Every approval opens with purpose, exposes provenance, and never asks for a click without receipts."
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <ApprovalCard
              title="Promote signal sig-8f2 into paper trading."
              origin="strategy"
              risk="low"
              summary={longContent ? longText : "Backtest passed 12 of 13 checks. Sharpe 1.42, drawdown 4.1%. Shadow book agreement 96%."}
              provenance={{ source: 'signal-forge@v2', transform: 'plan #47 · step 3', attested: 'gov-warden' }}
              decisionIdentity="plan #47 · worker signal-forge@v2 · sha 91a2ce…"
              ageMinutes={14}
              onApprove={() => {}} onDefer={() => {}} onBlock={() => {}}
            />
            <ApprovalCard
              title="Rotate schema for feature store to v4."
              origin="schema-change"
              risk="moderate"
              summary="Adds five new columns; drops one. Reversible via migration 07-b."
              provenance={{ source: 'feature-mill@v6', transform: 'plan #48 · step 1', attested: 'gov-warden' }}
              decisionIdentity="plan #48 · sha 5da0ff… · reversible"
              ageMinutes={62}
              onApprove={() => {}} onDefer={() => {}} onBlock={() => {}}
            />
            <ApprovalCard
              title="Raise compute quota for backtest suite by 40%."
              origin="compute-quota"
              risk="high"
              summary="Estimated $184/day incremental cost. Impacts other tenants."
              provenance={{ source: 'ops-operator', transform: 'manual request', attested: undefined }}
              decisionIdentity="request #113 · unattested"
              ageMinutes={9}
              onApprove={() => {}} onDefer={() => {}} onBlock={() => {}}
            />
          </div>
        </Section>

        {/* ─── Evidence ─────────────────────────────────────────────────── */}
        <Section
          code="E · evidence"
          title="Provenance, lineage, evidence drawer."
          blurb="The receipts. Every operator claim can be inspected in place; nothing is asserted without a trail."
        >
          <ProvenanceTriple source="signal-forge@v2" transform="plan #47 · step 3" attested="gov-warden" />
          <ProvenanceTriple source="operator@ops" attested="gov-warden" />
          <LineageBar
            self={{ id: 'sig-8f2', label: 'sig-8f2', kind: 'signal' }}
            ancestors={[
              { id: 'ftr-77c', label: 'ftr-77c', kind: 'feature' },
              { id: 'cdl-90d', label: 'cdl-90d', kind: 'candle' },
            ]}
            descendants={[
              { id: 'bt-19a', label: 'bt-19a', kind: 'backtest' },
            ]}
            onOpen={() => setDrawerOpen(true)}
          />
          <LineageBar self={{ id: 'cdl-90d', label: 'cdl-90d', kind: 'candle' }} />

          <div
            style={{
              background: 'var(--surface-1)',
              border: '1px solid var(--stroke-1)',
              borderRadius: 'var(--radius-3)',
              padding: 'var(--space-5)',
              display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
            }}
          >
            <div style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)' }}>
              Open the evidence drawer
            </div>
            <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
              The drawer preserves the operator's context on the base surface.
              Press <KeyboardShortcut chord="Esc" /> to close, or click outside.
            </div>
            <div>
              <button
                data-testid="open-evidence-drawer"
                onClick={() => setDrawerOpen(true)}
                style={{
                  background: 'var(--sig-info)',
                  color: 'var(--surface-0)',
                  border: 'none',
                  borderRadius: 'var(--radius-1)',
                  padding: '8px 14px',
                  fontFamily: 'inherit',
                  fontSize: 'var(--font-body-sm)',
                  cursor: 'pointer',
                  marginTop: 'var(--space-2)',
                }}
              >
                Open drawer →
              </button>
            </div>
          </div>
        </Section>

        {/* ─── States showcase ─────────────────────────────────────────── */}
        <Section
          code="S · states"
          title="Canonical states."
          blurb="Every non-happy state renders through StateTemplate — six-slot anatomy, tone-driven icon, code identifier for regression."
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            <StateTemplate
              variant="empty" code="demo-empty" icon={GitBranch} tone="ok"
              headline="You are all caught up."
              purpose="No approvals require your attention."
              advancedFootnote="master-bot@v55 · plan #47"
            />
            <StateTemplate
              variant="dormant" code="demo-dormant" icon={GitBranch} tone="dormant"
              headline="This workspace is paused."
              purpose="Resume from the ⌘K palette."
            />
            <StateTemplate
              variant="error" code="demo-error" icon={GitBranch} tone="crit"
              headline="Something interrupted the last plan."
              purpose="Governance held plan #46 pending review."
              primaryAction={{ label: 'open governance queue', onClick: () => {} }}
              advancedFootnote="policy v2.1 §8.4"
            />
          </div>
        </Section>
      </div>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Signal sig-8f2"
        subtitle="plan #47 · step 3 · worker signal-forge@v2"
        provenance={{ source: 'signal-forge@v2', transform: 'plan #47 · step 3', attested: 'gov-warden' }}
        lineage={{
          self: { id: 'sig-8f2', label: 'sig-8f2', kind: 'signal' },
          ancestors: [
            { id: 'ftr-77c', label: 'ftr-77c', kind: 'feature' },
            { id: 'cdl-90d', label: 'cdl-90d', kind: 'candle' },
          ],
          descendants: [
            { id: 'bt-19a', label: 'bt-19a', kind: 'backtest' },
          ],
        }}
        sections={canonicalState === 'happy' ? [
          { heading: 'metrics',      body: 'Sharpe 1.42 · drawdown 4.1% · hit-rate 58%.' },
          { heading: 'shadow book',  body: 'Agreement 96% over the past 24h.' },
          { heading: 'operator notes', body: longContent ? longText : 'Promoted after the second-pass review.' },
        ] : []}
        state={canonicalState === 'dormant' ? 'happy' : canonicalState}
      />

      <KeyboardShortcutHUD />
    </div>
  );
};
