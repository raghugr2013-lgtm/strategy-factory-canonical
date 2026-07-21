/*
 * PrimitiveGallery — Sprint 1 M2 verification surface.
 * refs DESIGN_FREEZE_v1.0.md §1.3 · Kickoff Plan M2 exit gate
 *
 * This gallery satisfies the intent of Storybook without shipping the full
 * Storybook infrastructure — every primitive is exercised in its canonical
 * states so QA and design review can validate visually.
 *
 * Access: authenticated route `/c/gallery`. Not part of the frozen operator
 * surface set; retained under Freeze §2 as an internal debug affordance.
 */
import React, { useState } from 'react';
import { Sparkles, Bot, Activity, Cpu, Landmark, ShieldAlert } from 'lucide-react';
import { Chip } from '../primitives/Chip';
import { MetricBlock } from '../primitives/MetricBlock';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { KeyboardShortcut, KeyboardShortcutHUD } from '../primitives/KeyboardShortcutHUD';
import { ProvenanceTriple } from '../primitives/ProvenanceTriple';
import { StateTemplate } from '../primitives/StateTemplate';
import { ChartTile } from '../primitives/ChartTile';
import { TableTile } from '../primitives/TableTile';
import { PipelineStageBar } from '../primitives/PipelineStageBar';
import { ActivityRow } from '../primitives/ActivityRow';
import { WorkerCard } from '../primitives/WorkerCard';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { LineageBar } from '../primitives/LineageBar';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';

const Section = ({ id, title, children }) => (
  <section id={id} data-testid={`gallery-section-${id}`}
           style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
                    padding: 'var(--space-5) 0', borderBottom: '1px solid var(--stroke-1)' }}>
    <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                  textTransform: 'uppercase', letterSpacing: '0.1em' }}>
      Primitive · {title}
    </div>
    {children}
  </section>
);

const Row = ({ children }) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 'var(--space-4)' }}>{children}</div>
);

const SAMPLE_POINTS = [12, 15, 14, 18, 22, 20, 26, 24, 28, 30, 27, 32, 34, 30, 36];

export const PrimitiveGallery = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <div style={{ padding: 'var(--space-5)', maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                       letterSpacing: '0.1em', textTransform: 'uppercase' }}>Gallery</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ color: 'var(--sig-info)', fontSize: 'var(--font-caption)',
                       letterSpacing: '0.1em', textTransform: 'uppercase' }}>Sprint 1 · M2</span>
      </div>
      <h1 style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                   fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Every primitive. Every canonical state. One visual contract.
      </h1>
      <p style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 720,
                  fontSize: 'var(--font-body-md)', lineHeight: 1.55, color: 'var(--content-md)' }}>
        M2 ships 15 primitives against the frozen Design contract. Toggle Advanced Lens in the header
        to reveal decision-identity footnotes; press <code>?</code> to open the Keyboard Shortcut HUD.
      </p>

      <Section id="chip" title="Chip · Bible §7.1">
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <Chip tone="ok" label="passing" />
          <Chip tone="info" label="working" />
          <Chip tone="warn" label="attention" />
          <Chip tone="crit" label="failed" />
          <Chip tone="advisory" label="advisory" />
          <Chip tone="dormant" label="idle" />
          <Chip tone="info" label="paper" showGlyph={false} />
          <Chip tone="ok" label="live" showGlyph={false} />
        </div>
      </Section>

      <Section id="metric" title="MetricBlock · Bible §7.11.1">
        <Row>
          <MetricBlock variant="A" eyebrow="Strategies live" value="12" deltaLabel="+2 today" deltaTone="ok"
                       footnote="hash 91a2b · plan #47 · signal-forge@v2" />
          <MetricBlock variant="B" eyebrow="Signals in queue" value="34" unit="jobs" deltaLabel="steady" deltaTone="info"
                       footnote="scheduler@v11" />
          <MetricBlock variant="C" eyebrow="AUM" value="$2.4M" deltaLabel="+3.2% wk" deltaTone="ok"
                       footnote="rebase 2026-07-14" />
          <MetricBlock variant="A" eyebrow="Loading state" value="—" state="loading" />
          <MetricBlock variant="A" eyebrow="Empty state" value="—" state="empty" />
          <MetricBlock variant="A" eyebrow="Error state" value="—" state="error" />
          <MetricBlock variant="A" eyebrow="Dormant state" value="12" deltaLabel="paused" deltaTone="dormant" state="dormant" />
        </Row>
      </Section>

      <Section id="division-caption" title="DivisionCaption · D4">
        <DivisionCaption eyebrow="Master Bot · Workforce" icon={Bot} status="v55 · plan #47 · 3/7"
                         purpose="Coordinates every research plan across ingest, feature, signal, backtest." />
      </Section>

      <Section id="signature-frame" title="SignatureFrame · D5">
        <Row>
          <SignatureFrame tone="info" icon={Activity} caption="Signature · info tone">
            <div style={{ color: 'var(--content-md)' }}>Frames chart tiles + editorial cards.</div>
          </SignatureFrame>
          <SignatureFrame tone="gold" icon={Sparkles} caption="Signature · gold accent">
            <div style={{ color: 'var(--content-md)' }}>Executive tone highlight.</div>
          </SignatureFrame>
          <SignatureFrame tone="warn" caption="Signature · attention">
            <div style={{ color: 'var(--content-md)' }}>Warn tone for advisory.</div>
          </SignatureFrame>
        </Row>
      </Section>

      <Section id="kbd" title="KeyboardShortcut · Bible §7.10">
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <KeyboardShortcut chord="⌘K" label="find anything" />
          <KeyboardShortcut chord="⌘/" label="advanced lens" />
          <KeyboardShortcut chord="Esc" label="close overlay" />
          <KeyboardShortcut chord="?" label="show shortcut HUD (press ?)" />
        </div>
        <KeyboardShortcutHUD />
      </Section>

      <Section id="provenance" title="ProvenanceTriple · Bible §10.2">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <ProvenanceTriple source="ingestion@v22" transform="candles@v3" attested="gov-warden" />
          <ProvenanceTriple source="ingestion@v22" transform="candles@v3" />
          <ProvenanceTriple />
        </div>
      </Section>

      <Section id="state-template" title="StateTemplate · D7">
        <Row>
          <StateTemplate variant="empty" code="mc-empty" icon={Sparkles} tone="dormant"
                         headline="Nothing to see here — yet."
                         purpose="Ingestion begins at 09:00Z. Come back then, or open the Timeline." />
          <StateTemplate variant="error" code="mc-error" icon={ShieldAlert} tone="crit"
                         headline="One worker is offline."
                         purpose="signal-forge@v2 stopped responding. Retrying in 45s."
                         primaryAction={{ label: 'view worker', onClick: () => {} }} />
          <StateTemplate variant="dormant" code="mc-dormant" icon={Landmark} tone="dormant"
                         headline="Kill posture engaged."
                         purpose="No new artefacts will be created until the operator disarms." />
        </Row>
      </Section>

      <Section id="chart" title="ChartTile · Bible §7.11.2">
        <Row>
          <ChartTile caption="AUM · 24h" points={SAMPLE_POINTS} tone="info" />
          <ChartTile caption="Sharpe rolling" points={SAMPLE_POINTS} tone="ok" />
          <ChartTile caption="Drawdown" points={SAMPLE_POINTS.slice().reverse()} tone="warn" />
          <ChartTile caption="Loading" points={[]} state="loading" />
          <ChartTile caption="Empty" points={[]} state="empty" />
          <ChartTile caption="Error" points={[]} state="error" />
        </Row>
      </Section>

      <Section id="table" title="TableTile · Bible §7.11.3">
        <TableTile caption="Strategies · flat"
                   columns={[
                     { key: 'id', label: 'id', sortable: true },
                     { key: 'name', label: 'name', sortable: true },
                     { key: 'status', label: 'status', sortable: true, render: (r) => <Chip tone={r.status === 'live' ? 'ok' : r.status === 'paper' ? 'info' : 'dormant'} label={r.status} /> },
                     { key: 'sharpe', label: 'sharpe', align: 'right', sortable: true },
                   ]}
                   rows={[
                     { id: 'strat-014', name: 'flagship-momentum', status: 'live', sharpe: 1.62 },
                     { id: 'strat-030', name: 'vol-carry', status: 'paper', sharpe: 0.94 },
                     { id: 'strat-041', name: 'mean-revert-eu', status: 'paper', sharpe: 1.11 },
                     { id: 'strat-052', name: 'archived-trend', status: 'archived', sharpe: 0.42 },
                   ]}
                   onRowActivate={() => {}} />
      </Section>

      <Section id="pipeline" title="PipelineStageBar · Bible §7.3">
        <PipelineStageBar />
      </Section>

      <Section id="activity" title="ActivityRow · Bible §7.4 · D2">
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', overflow: 'hidden' }}>
          <ActivityRow timestamp="12:34:02" actor={{ kind: 'governance', icon: Landmark }}
                       verb="held" subject="strat-014-schema-v3"
                       outcome={{ tone: 'warn', label: 'review' }}
                       trailer="policy v2.1 §8.4" onOpen={() => {}} />
          <ActivityRow timestamp="12:14:11" actor={{ kind: 'master-bot', icon: Bot }}
                       verb="deployed" subject="signal-forge@v2 → plan #47"
                       outcome={{ tone: 'ok', label: 'success' }} onOpen={() => {}} />
          <ActivityRow timestamp="11:58:44" actor={{ kind: 'llm', icon: Sparkles }}
                       verb="proposed" subject="feature-mill@v6"
                       outcome={{ tone: 'info', label: 'draft' }} onOpen={() => {}} />
          <ActivityRow timestamp="11:52:03" actor={{ kind: 'ingestion', icon: Cpu }}
                       verb="failed" subject="candles-gap 08:00–09:00"
                       outcome={{ tone: 'crit', label: 'failed' }} />
        </div>
      </Section>

      <Section id="worker" title="WorkerCard · Bible §7.6">
        <Row>
          <WorkerCard name="ingestion@v22" purpose="Streams bar candles from primary + fallback feeds."
                      subject="candles@v3 · window 24h" state="active" icon={Cpu} onOpen={() => {}} />
          <WorkerCard name="signal-forge@v2" purpose="Trains candidate signals from the feature store."
                      subject="plan #47 · epoch 4/6" state="active" icon={Sparkles} onOpen={() => {}} />
          <WorkerCard name="feature-mill@v6" purpose="Assembles feature vectors from candles + external factors."
                      subject="strat-014 · batch 5/5" state="idle" onOpen={() => {}} />
          <WorkerCard name="gov-warden" purpose="Attests schema, policy, and governance holds."
                      state="blocked" onOpen={() => {}} />
          <WorkerCard name="archived-scanner" purpose="Rehydrates archived strategies for replay."
                      state="dormant" />
          <WorkerCard name="candle-mill@v3" purpose="Fell over. Attempting reconnect."
                      state="error" />
        </Row>
      </Section>

      <Section id="approval" title="ApprovalCard · Bible §7.5 · D3">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <ApprovalCard title="Promote strat-014 flagship-momentum from paper to live."
                        origin="strategy" risk="moderate"
                        summary="Sharpe 1.62 over 42 days. Guardrails passing. Governance advisory: matches historical crowded-trade signature at v1.3."
                        provenance={{ source: 'flagship-momentum-worker@v2', transform: 'plan #47 · step 1', attested: 'gov-warden' }}
                        decisionIdentity="plan #47 · signal-forge@v2 · sha 91a2b3c"
                        ageMinutes={44} onApprove={() => {}} onDefer={() => {}} onBlock={() => {}} />
          <ApprovalCard title="Approve schema change · strat-014-schema-v3."
                        origin="schema-change" risk="high"
                        summary="Column added to signal envelope. Downstream models require re-fit within 24h."
                        provenance={{ source: 'schema-registry', transform: 'gov-warden', attested: 'gov-warden' }}
                        decisionIdentity="plan #47 · step 2 · sha 8c1d0"
                        ageMinutes={82} onApprove={() => {}} onDefer={() => {}} onBlock={() => {}} />
        </div>
      </Section>

      <Section id="lineage" title="LineageBar · Bible §10.1">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <LineageBar self={{ id: 'strat-014', label: 'STRAT-014', kind: 'strategy' }}
                      ancestors={[
                        { id: 'plan-47', label: 'PLAN #47', kind: 'plan' },
                        { id: 'signal-forge-v2', label: 'SIGNAL-FORGE@V2', kind: 'worker' },
                      ]}
                      descendants={[
                        { id: 'backtest-891', label: 'BACKTEST-891', kind: 'backtest' },
                      ]}
                      onOpen={() => {}} />
          <LineageBar self={{ id: 'plan-47', label: 'PLAN #47', kind: 'plan' }} />
          <LineageBar self={{ id: 'strat-014-v0', label: 'STRAT-014 · REPLAY', kind: 'strategy' }} replayEmpty />
        </div>
      </Section>

      <Section id="evidence" title="EvidenceDrawer · Bible §10">
        <button data-testid="gallery-open-evidence" onClick={() => setDrawerOpen(true)}
                style={{ background: 'var(--sig-info)', color: 'var(--surface-0)',
                         border: 'none', borderRadius: 'var(--radius-1)',
                         padding: '8px 14px', fontSize: 'var(--font-body-sm)',
                         fontFamily: 'inherit', cursor: 'pointer' }}>
          Open evidence drawer
        </button>
        <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}
                        title="held · strat-014-schema-v3" subtitle="12:34:02Z · gov-warden"
                        provenance={{ source: 'governance', transform: 'plan #47', attested: 'gov-warden' }}
                        lineage={{ self: { id: 'strat-014', label: 'STRAT-014', kind: 'strategy' },
                                   ancestors: [{ id: 'plan-47', label: 'PLAN #47', kind: 'plan' }] }}
                        sections={[
                          { heading: 'Trailer', body: 'policy v2.1 §8.4 — schema hash mismatch requires human attestation before the strategy graduates from paper.' },
                          { heading: 'Outcome', body: 'review (warn) · queued into Approval Center.' },
                          { heading: 'Decision identity', body: 'This event references strategy strat-014. Opening the passport preserves your position — the timeline will restore this row on return.' },
                        ]}
                        footerAction={{ label: 'open passport · strat-014', onClick: () => setDrawerOpen(false), testId: 'evidence-open-passport' }} />
      </Section>
    </div>
  );
};
