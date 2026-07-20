/*
 * MasterBot — Bible §7.6, D4. Phase 5-wired:
 *   • Three-view toggle:
 *       Org      — grid of WorkerCards (default; original view)
 *       Purpose  — same workforce ordered by purpose, showing only
 *                   the purpose statements — reinforces D4 §5.1.1
 *                   "Purpose Before Status".
 *       Status   — status-first tabular view (state, subject, name).
 *   • Selection choice persists in navigation surface memory so
 *     returning to /c/workforce restores the last view.
 *   • Kill posture, when armed, still gets a first-class notice.
 */
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bot, Cpu, LayoutGrid, Flag, ListChecks } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { WorkerCard } from '../primitives/WorkerCard';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { Chip } from '../primitives/Chip';
import { useScenarioFixture } from '../gallery/scenarioFixtures';
import { useWorkspaceStore } from '../workspace-state/store';
import { useNavigationStore } from '../workspace-state/navigationStore';

type WorkforceView = 'org' | 'purpose' | 'status';

const stateTone = { active: 'ok', idle: 'info', error: 'crit', blocked: 'warn', dormant: 'dormant' } as const;

const VIEWS: Array<{ key: WorkforceView; label: string; icon: typeof Bot; help: string }> = [
  { key: 'org',      label: 'org chart',   icon: LayoutGrid,  help: 'Grid of workers with purpose + state.' },
  { key: 'purpose',  label: 'purpose',     icon: Flag,        help: 'Purpose-first list. State is intentionally muted.' },
  { key: 'status',   label: 'status',      icon: ListChecks,  help: 'Status-first table. Purpose is intentionally muted.' },
];

export const MasterBot: React.FC = () => {
  const fx = useScenarioFixture();
  const loc = useLocation();
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const saveSurface = useNavigationStore((s) => s.saveSurface);
  const readSurface = useNavigationStore((s) => s.readSurface);

  const [view, setView] = useState<WorkforceView>(() => {
    const mem = readSurface<{ view: WorkforceView }>(loc.pathname);
    return mem?.view ?? 'org';
  });

  useEffect(() => {
    saveSurface(loc.pathname, { view });
  }, [view, loc.pathname, saveSurface]);

  const byState = fx.workers.reduce<Record<string, number>>((acc, w) => {
    acc[w.state] = (acc[w.state] ?? 0) + 1; return acc;
  }, {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Master Bot · workforce"
        headline={fx.workforcePurpose}
        briefing="Every worker declares its purpose first. Toggle the view to shift the emphasis without losing the underlying truth (Decision Identity, D6 §8.1a)."
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

      {/* View toggle */}
      <div
        data-testid="workforce-view-toggle"
        role="tablist"
        aria-label="Workforce view"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span
          style={{
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          view ·
        </span>
        {VIEWS.map((v) => {
          const I = v.icon;
          const active = view === v.key;
          return (
            <button
              key={v.key}
              data-testid={`workforce-view-${v.key}`}
              role="tab"
              aria-selected={active}
              title={v.help}
              onClick={() => setView(v.key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: active ? 'var(--sig-info)' : 'var(--surface-2)',
                color: active ? 'var(--surface-0)' : 'var(--content-md)',
                border: '1px solid var(--stroke-2)',
                borderRadius: 'var(--radius-1)',
                padding: '4px 10px',
                fontFamily: 'ui-monospace, monospace',
                fontSize: 'var(--font-caption)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                cursor: 'pointer',
              }}
            >
              <I size={12} /> {v.label}
            </button>
          );
        })}
        <span
          data-testid="workforce-view-hint"
          style={{
            marginLeft: 'auto', fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          identity invariant · {fx.workers.length} workers
        </span>
      </div>

      {view === 'org' && (
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
      )}

      {view === 'purpose' && (
        <section
          data-testid="workforce-purpose-list"
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        >
          {[...fx.workers]
            .sort((a, b) => a.purpose.localeCompare(b.purpose))
            .map((w) => (
              <div
                key={w.id}
                data-testid={`worker-purpose-${w.id}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '160px 1fr auto',
                  gap: 'var(--space-3)',
                  alignItems: 'baseline',
                  padding: 'var(--space-3) var(--space-4)',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--stroke-1)',
                  borderRadius: 'var(--radius-2)',
                }}
              >
                <span
                  className="mono-num"
                  style={{
                    fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}
                >
                  {w.name}
                </span>
                <span style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)', lineHeight: 1.5 }}>
                  {w.purpose}
                </span>
                <Chip tone={stateTone[w.state]} label={w.state} showGlyph={false} />
              </div>
            ))}
        </section>
      )}

      {view === 'status' && (
        <section
          data-testid="workforce-status-table"
          role="table"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--stroke-1)',
            borderRadius: 'var(--radius-2)',
            overflow: 'hidden',
          }}
        >
          <div
            role="row"
            style={{
              display: 'grid', gridTemplateColumns: '120px 200px 1fr 200px',
              gap: 'var(--space-3)',
              padding: 'var(--space-2) var(--space-4)',
              background: 'var(--surface-2)',
              fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}
          >
            <span>state</span>
            <span>worker</span>
            <span>subject</span>
            <span>purpose (muted)</span>
          </div>
          {[...fx.workers]
            .sort((a, b) =>
              a.state === b.state ? 0
              : a.state === 'error' ? -1 : b.state === 'error' ? 1
              : a.state === 'blocked' ? -1 : b.state === 'blocked' ? 1
              : a.state === 'active' ? -1 : b.state === 'active' ? 1 : 0)
            .map((w) => (
              <div
                key={w.id}
                role="row"
                data-testid={`worker-status-${w.id}`}
                style={{
                  display: 'grid', gridTemplateColumns: '120px 200px 1fr 200px',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-2) var(--space-4)',
                  borderTop: '1px solid var(--stroke-1)',
                  alignItems: 'center',
                }}
              >
                <Chip tone={stateTone[w.state]} label={w.state} showGlyph={false} testId={`worker-status-${w.id}-chip`} />
                <span className="mono-num" style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)' }}>
                  {w.name}
                </span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
                  {w.subject ?? '—'}
                </span>
                <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', lineHeight: 1.3 }}>
                  {w.purpose}
                </span>
              </div>
            ))}
        </section>
      )}
    </div>
  );
};
