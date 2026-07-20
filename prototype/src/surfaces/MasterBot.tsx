/*
 * MasterBot — Bible §7.6, D4.
 * The workforce org chart surface. Sprint 1: grid view only. The Master Bot
 * caption opens with purpose (not with a name); each subordinate worker is
 * a `WorkerCard`. Kill posture, when armed, gets a first-class notice.
 */
import { Bot, Cpu } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { WorkerCard } from '../primitives/WorkerCard';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { Chip } from '../primitives/Chip';
import { useScenarioFixture } from '../gallery/scenarioFixtures';
import { useWorkspaceStore } from '../workspace-state/store';

const stateTone = { active: 'ok', idle: 'info', error: 'crit', blocked: 'warn', dormant: 'dormant' } as const;

export const MasterBot: React.FC = () => {
  const fx = useScenarioFixture();
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);

  const byState = fx.workers.reduce<Record<string, number>>((acc, w) => {
    acc[w.state] = (acc[w.state] ?? 0) + 1; return acc;
  }, {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Master Bot · workforce"
        headline={fx.workforcePurpose}
        briefing="Every worker declares its purpose first. Colour is not the only channel of state — every card carries a labelled chip."
        status={fx.workforceStatus}
        testId="masterbot-header"
      />

      {killArmed && (
        <SignatureFrame tone="crit" caption="Kill posture" icon={Bot}>
          <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', lineHeight: 1.5 }}>
            The workforce is operating under an intentional freeze. New signals
            will not be promoted until the posture is released by an operator.
          </div>
        </SignatureFrame>
      )}

      <SignatureFrame tone="gold" icon={Bot} caption="Master Bot">
        <DivisionCaption
          eyebrow="Orchestrator"
          purpose={fx.workforcePurpose}
          icon={Bot}
          status={fx.workforceStatus}
        />
        <div
          style={{
            display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)',
            marginTop: 'var(--space-3)',
          }}
        >
          {Object.entries(byState).map(([state, count]) => (
            <Chip
              key={state}
              tone={stateTone[state as keyof typeof stateTone]}
              label={`${count} ${state}`}
              showGlyph={false}
              testId={`workforce-count-${state}`}
            />
          ))}
        </div>
      </SignatureFrame>

      <section
        data-testid="workforce-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        {fx.workers.map((w) => (
          <WorkerCard
            key={w.id}
            name={w.name}
            purpose={w.purpose}
            subject={w.subject}
            state={w.state}
            icon={Cpu}
            testId={`worker-${w.id}`}
          />
        ))}
      </section>
    </div>
  );
};
