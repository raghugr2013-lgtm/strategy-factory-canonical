/**
 * COMMAND · Pilot Restoration Step 2 — DashboardComposite
 * ----------------------------------------------------------------------------
 * Restores the original 1-vCPU Mission Control experience (GATE 0 pilot,
 * per /app/memory/IMPLEMENTATION_SEQUENCE.md Step 2 and
 * UI_RESTORATION_MASTERPLAN.md §1.1):
 *
 *   MissionBriefing (kept — read-only synthesis, top of stack)
 *   → GovernanceCard → UniverseGovernancePanel → StrategyIngestionCard
 *   → AutoSchedulerControl → OrchestratorPanel → MultiCycleRunner
 *   → AutoMutationRunner → StrategyDashboard
 *
 * The 8 legacy panels are the exact components mounted elsewhere in the
 * shell (Governance / Diag / AI / Mutation homes are unchanged) — this is
 * a COMPOSITION, not a relocation. All 8 are lazy so the dashboard chunk
 * stays light; each renders behind its own Suspense skeleton + error
 * boundary so a single panel failure never takes down Mission Control.
 *
 * Posture contract (locked):
 *   • workstation — full stacked scroll (the 1-vCPU feel)
 *   • tablet      — MissionBriefing + the 8 panels folded into collapsed
 *                   accordions (operator expands on demand)
 *   • briefing    — MissionBriefing ONLY (read-only contract preserved)
 */
import React, { Suspense } from 'react';
import { usePosture } from '../usePosture';
import MissionBriefing from './MissionBriefing';

// Lazy panels — identical import targets to their canonical homes in
// modulesRegistry.js (governance/gov, governance/universe, diag/ingest-src,
// ai/sched, ai/orch, mutate/cycle, mutate/auto, + StrategyDashboard).
const GovernanceCard          = React.lazy(() => import('../../../components/GovernanceCard'));
const UniverseGovernancePanel = React.lazy(() => import('../../../components/UniverseGovernancePanel'));
const StrategyIngestionCard   = React.lazy(() => import('../../../components/StrategyIngestionCard'));
const AutoSchedulerControl    = React.lazy(() => import('../../../components/AutoSchedulerControl'));
const OrchestratorPanel       = React.lazy(() => import('../../../components/OrchestratorPanel'));
const MultiCycleRunner        = React.lazy(() => import('../../../components/MultiCycleRunner'));
const AutoMutationRunner      = React.lazy(() => import('../../../components/AutoMutationRunner'));
const StrategyDashboard       = React.lazy(() => import('../../../components/StrategyDashboard'));

// Locked 1-vCPU order (old App.js LL 306–317). Do not re-order.
const STACK = [
  { id: 'governance',     title: 'governance',          Component: GovernanceCard },
  { id: 'universe',       title: 'universe governance', Component: UniverseGovernancePanel },
  { id: 'ingestion',      title: 'strategy ingestion',  Component: StrategyIngestionCard },
  { id: 'scheduler',      title: 'auto-scheduler',      Component: AutoSchedulerControl },
  { id: 'orchestrator',   title: 'orchestrator',        Component: OrchestratorPanel },
  { id: 'multi-cycle',    title: 'multi-cycle runner',  Component: MultiCycleRunner },
  { id: 'auto-mutation',  title: 'auto mutation runner', Component: AutoMutationRunner },
  { id: 'strategy-dash',  title: 'strategy dashboard',  Component: StrategyDashboard },
];

function PanelSkeleton({ title }) {
  return (
    <div data-testid={`dashboard-stack-skeleton-${title}`} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      <span className="cmd-skel-line" style={{ width: '34%' }} />
      <span className="cmd-skel-line" style={{ width: '70%' }} />
      <span className="cmd-skel-line" style={{ width: '52%' }} />
    </div>
  );
}

// Per-panel error boundary — mirrors ModuleSurface's section boundary so a
// single legacy panel crash leaves the rest of Mission Control standing.
class PanelBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) {
    // eslint-disable-next-line no-console
    console.error(`[command:dashboard-stack:${this.props.name}]`, err, info);
  }
  render() {
    if (this.state.err) {
      return (
        <div data-testid={`dashboard-stack-error-${this.props.name}`} style={{ fontSize: 11, color: 'var(--cmd-red)', padding: 8 }}>
          panel failed · {this.props.name} — {String(this.state.err.message || this.state.err)}
        </div>
      );
    }
    return this.props.children;
  }
}

function StackPanel({ id, title, Component }) {
  return (
    <section className="panel" data-testid={`dashboard-stack-${id}`}>
      <div className="panel__hd">
        <span>· {title}</span>
      </div>
      <PanelBoundary name={id}>
        <Suspense fallback={<PanelSkeleton title={id} />}>
          <Component />
        </Suspense>
      </PanelBoundary>
    </section>
  );
}

// Tablet posture — same panels, folded into collapsed accordions.
function StackAccordion({ id, title, Component }) {
  return (
    <details className="panel" data-testid={`dashboard-stack-${id}`} style={{ padding: 0 }}>
      <summary
        className="panel__hd"
        data-testid={`dashboard-stack-toggle-${id}`}
        style={{ cursor: 'pointer', listStyle: 'none', padding: '10px 12px', margin: 0, userSelect: 'none' }}
      >
        <span>· {title}</span>
        <div className="panel__hd-spacer" />
        <span className="chip"><span className="chip__label">expand</span></span>
      </summary>
      <div style={{ padding: '0 12px 12px' }}>
        <PanelBoundary name={id}>
          <Suspense fallback={<PanelSkeleton title={id} />}>
            <Component />
          </Suspense>
        </PanelBoundary>
      </div>
    </details>
  );
}

export default function DashboardComposite() {
  const posture = usePosture();

  // Briefing posture keeps the read-only contract: synthesis only.
  if (posture === 'briefing') {
    return <MissionBriefing />;
  }

  const Renderer = posture === 'tablet' ? StackAccordion : StackPanel;

  return (
    <div data-testid="dashboard-composite" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 1 · Read-only synthesis stays first — best of both eras. */}
      <MissionBriefing />
      {/* 2–9 · The restored 1-vCPU operator workbench stack. */}
      {STACK.map((p) => (
        <Renderer key={p.id} id={p.id} title={p.title} Component={p.Component} />
      ))}
    </div>
  );
}
