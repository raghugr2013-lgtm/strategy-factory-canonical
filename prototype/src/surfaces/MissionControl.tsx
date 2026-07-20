/*
 * MissionControl — Bible §7.11, D1 §5.
 * The operator's opening surface. Anatomy:
 *   Header · KPI row (3 MetricBlocks) · Pipeline stage bar ·
 *   throughput chart · latest activity strip · quick approvals summary.
 *
 * Every element is driven by the current scenario fixture. No workflow
 * logic — the scenario picks the presentation.
 */
import { useNavigate } from 'react-router-dom';
import { Bot, Compass } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { MetricBlock } from '../primitives/MetricBlock';
import { PipelineStageBar } from '../primitives/PipelineStageBar';
import { ChartTile } from '../primitives/ChartTile';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { ActivityRow } from '../primitives/ActivityRow';
import { Chip } from '../primitives/Chip';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { StateTemplate } from '../primitives/StateTemplate';
import { useScenarioFixture } from '../gallery/scenarioFixtures';

export const MissionControl: React.FC = () => {
  const fx = useScenarioFixture();
  const nav = useNavigate();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow={fx.missionEyebrow}
        headline={fx.missionHeadline}
        briefing={fx.missionBriefing}
        status="v55 · plan #47"
        testId="mission-header"
      />

      <div
        data-testid="mission-kpi-row"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        {fx.missionMetrics.map((m, i) => (
          <MetricBlock
            key={i}
            variant={m.variant}
            eyebrow={m.eyebrow}
            value={m.value}
            unit={m.unit}
            deltaLabel={m.deltaLabel}
            deltaTone={m.deltaTone as any}
            footnote={m.footnote}
          />
        ))}
      </div>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption
          eyebrow="Factory pipeline"
          purpose="Where work lives right now."
          icon={Compass}
        />
        <PipelineStageBar stages={fx.pipelineStages} />
      </section>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)',
          gap: 'var(--space-4)',
          alignItems: 'flex-start',
        }}
      >
        <ChartTile
          caption="factory throughput"
          points={fx.missionSparkPoints}
          tone={fx.missionTone as any}
          timeWindow="last 24h"
          testId="mission-throughput"
        />

        <SignatureFrame tone="info" caption="Latest activity">
          <div role="list" style={{ display: 'flex', flexDirection: 'column' }}>
            {fx.timelineEvents.slice(0, 4).map((e, i) => (
              <ActivityRow
                key={i}
                timestamp={e.timestamp}
                actor={{ kind: e.actor.kind, name: e.actor.name }}
                verb={e.verb}
                subject={e.subject}
                outcome={e.outcome}
                trailer={e.trailer}
                onOpen={() => nav('/c/timeline')}
                testId={`mission-activity-${i}`}
              />
            ))}
          </div>
        </SignatureFrame>
      </div>

      <SignatureFrame tone={fx.approvals.length ? 'warn' : 'ok'} caption="Approvals summary">
        {fx.approvals.length === 0 ? (
          <StateTemplate
            variant="empty"
            code="mission-no-approvals"
            icon={Bot}
            tone="ok"
            headline="You are all caught up."
            purpose="No approvals require your attention."
            primaryAction={{ label: 'open Timeline', onClick: () => nav('/c/timeline') }}
            secondaryLink={{ label: "view yesterday's briefing", onClick: () => {} }}
            advancedFootnote="master-bot@v55 · plan #47"
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                fontSize: 'var(--font-body-sm)', color: 'var(--content-md)',
              }}
            >
              <Chip tone="warn" label={`${fx.approvals.length} pending`} />
              <span>
                {fx.approvals.filter((a) => a.risk === 'high').length} high-risk ·{' '}
                {fx.approvals.filter((a) => a.ageMinutes > 60).length} aged &gt; 60m
              </span>
              <button
                data-testid="mission-open-approvals"
                onClick={() => nav('/c/approvals')}
                style={{
                  marginLeft: 'auto',
                  background: 'var(--sig-info)',
                  color: 'var(--surface-0)',
                  border: 'none',
                  borderRadius: 'var(--radius-1)',
                  padding: '6px 12px',
                  fontFamily: 'inherit',
                  fontSize: 'var(--font-body-sm)',
                  cursor: 'pointer',
                }}
              >
                open Approval Center →
              </button>
            </div>
          </div>
        )}
      </SignatureFrame>
    </div>
  );
};
