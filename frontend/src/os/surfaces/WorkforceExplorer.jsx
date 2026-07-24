/*
 * WorkforceExplorer — Phase F: prototype-polished workforce surface.
 *
 * Merges the visual language of prototype/src/surfaces/MasterBot.tsx with
 * the production wiring of the sibling Workforce.jsx and MasterBot.jsx:
 *
 *   • Visual language (prototype):
 *     - SurfaceHeader anatomy (eyebrow · headline · briefing · mono trailer)
 *     - SignatureFrame · gold · Master Bot identity strip
 *     - Kill-posture SignatureFrame (crit) rendered when armed
 *     - Three-view toggle: org · purpose · status
 *     - View choice persists in navigationStore surface memory
 *     - State-count chips (active/idle/error/blocked/dormant)
 *
 *   • Production wiring (kept from Workforce.jsx / MasterBot.jsx):
 *     - Real API via `fetchWorkers()` (factoryAdapter — same as legacy
 *       Workforce · fixture-fallback with unavailableBreadcrumb)
 *     - Real API via `aggregateMasterBot()` (masterBotAdapter — same
 *       as legacy MasterBot · identity + current plan for the identity
 *       strip)
 *     - Kill-posture pulled from `useWorkspaceStore.killPostureArmed`
 *     - Icon inference (Cpu / Sparkles / Landmark / Bot) matches legacy
 *
 * Coexistence contract:
 *   /c/workforce            → legacy Workforce surface (unchanged)
 *   /c/masterbot            → legacy MasterBot surface (unchanged)
 *   /c/workforce/explorer   → this new surface
 * The existing surfaces are untouched. Rollback = revert this commit.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bot, Cpu, Sparkles, Landmark, LayoutGrid, Flag, ListChecks } from 'lucide-react';
import { SurfaceHeader } from '../primitives/SurfaceHeader';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { WorkerCard } from '../primitives/WorkerCard';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchWorkers } from '../adapters/factoryAdapter';
import { aggregateMasterBot } from '../adapters/masterBotAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

// ─── constants ───────────────────────────────────────────────────────────
const STATE_TONE = {
  active:  'ok',
  idle:    'info',
  error:   'crit',
  blocked: 'warn',
  dormant: 'dormant',
};

// Order matters — states most in need of operator attention first.
const STATE_ORDER = { error: 0, blocked: 1, active: 2, idle: 3, dormant: 4 };

const VIEWS = [
  { key: 'org',     label: 'org chart', icon: LayoutGrid, help: 'Grid of workers with purpose + state.' },
  { key: 'purpose', label: 'purpose',   icon: Flag,       help: 'Purpose-first list. State is intentionally muted.' },
  { key: 'status',  label: 'status',    icon: ListChecks, help: 'Status-first table. Purpose is intentionally muted.' },
];

// Icon inference — matches legacy Workforce.
const NAME_ICON = {
  ingestion:    Cpu,
  signal:       Sparkles,
  feature:      Sparkles,
  gov:          Landmark,
  candle:       Cpu,
  'master-bot': Bot,
};
const iconFor = (name = '') => {
  const key = Object.keys(NAME_ICON).find((k) => name.includes(k));
  return NAME_ICON[key] ?? Cpu;
};

// ─── component ───────────────────────────────────────────────────────────
export const WorkforceExplorer = () => {
  const loc = useLocation();

  const saveSurface  = useNavigationStore((s) => s.saveSurface);
  const killArmed    = useWorkspaceStore((s) => s.killPostureArmed);

  const [workers, setWorkers] = useState(null);
  const [masterBot, setMasterBot] = useState(null);
  // View memory: hydrate synchronously from navigationStore on mount to
  // avoid a mount-time race with the save effect below (found by testing
  // agent iteration_13).
  const [view, setView] = useState(() => {
    const mem = useNavigationStore.getState().memory?.[loc.pathname];
    return mem?.view && VIEWS.some((v) => v.key === mem.view) ? mem.view : 'org';
  });

  // Skip the very first save effect so the hydrated value is not stomped
  // by a redundant write with the same shape.
  const hydratedRef = useRef(false);

  // Persist view into surface memory (after the first render).
  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      return;
    }
    saveSurface(loc.pathname, { view });
  }, [view, loc.pathname, saveSurface]);

  // Fetch workers + Master Bot identity in parallel.
  useEffect(() => {
    let live = true;
    fetchWorkers().then((w) => { if (live) setWorkers(w); });
    aggregateMasterBot().then((mb) => { if (live) setMasterBot(mb); });
    return () => { live = false; };
  }, []);

  const isLoading = workers === null;
  const isEmpty = Array.isArray(workers) && workers.length === 0;

  // Roll up per-state counts.
  const byState = useMemo(() => {
    if (!Array.isArray(workers)) return {};
    return workers.reduce((acc, w) => {
      acc[w.state] = (acc[w.state] ?? 0) + 1;
      return acc;
    }, {});
  }, [workers]);

  // Header trailer.
  const trailer = isLoading
    ? 'loading…'
    : `${workers.length} worker${workers.length === 1 ? '' : 's'}`;

  const purpose = masterBot?.identity?.role
    ? `${masterBot.identity.codename} · ${masterBot.identity.role}`
    : 'Coordinates every research plan across ingest, feature, signal, backtest.';

  const currentPlanLine = masterBot?.currentPlan?.planId
    ? `plan ${masterBot.currentPlan.planId} · ${masterBot.currentPlan.ambition ?? ''}`.trim()
    : 'purpose before status';

  return (
    <section
      data-testid="workforce-explorer"
      style={{
        padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
        display: 'flex', flexDirection: 'column', gap: 'var(--space-6)',
      }}
    >
      <SurfaceHeader
        eyebrow="Workforce Explorer · Master Bot"
        headline="Every worker declares its purpose first."
        briefing="Toggle the view to shift the emphasis without losing the underlying truth (Decision Identity, D6 §8.1a). The org grid is default; purpose foregrounds intent; status foregrounds state."
        status={trailer}
        testId="workforce-explorer-header"
      />

      {/* Kill-posture ribbon — first-class when armed. */}
      {killArmed && (
        <SignatureFrame
          tone="crit"
          caption="Kill posture · armed"
          icon={Bot}
          testId="workforce-explorer-kill-posture"
        >
          <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', lineHeight: 1.5 }}>
            The workforce is operating under an intentional freeze. New signals
            will not be promoted until the posture is released by an operator.
          </div>
        </SignatureFrame>
      )}

      {/* Master Bot identity strip (Signature Frame · gold). */}
      <SignatureFrame
        tone="gold"
        icon={Bot}
        caption="Master Bot · orchestrator"
        testId="workforce-explorer-identity"
      >
        <DivisionCaption
          eyebrow="Orchestrator"
          purpose={purpose}
          icon={Bot}
          status={currentPlanLine}
        />
        {!isLoading && (
          <div
            data-testid="workforce-explorer-state-counts"
            style={{
              display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)',
              marginTop: 'var(--space-3)',
            }}
          >
            {Object.entries(byState).map(([state, count]) => (
              <Chip
                key={state}
                tone={STATE_TONE[state] ?? 'dormant'}
                label={`${count} ${state}`}
                showGlyph={false}
                testId={`workforce-explorer-count-${state}`}
              />
            ))}
          </div>
        )}
      </SignatureFrame>

      {/* View toggle. */}
      <div
        data-testid="workforce-explorer-view-toggle"
        role="tablist"
        aria-label="Workforce view"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span style={legend}>view ·</span>
        {VIEWS.map((v) => {
          const I = v.icon;
          const active = view === v.key;
          return (
            <button
              key={v.key}
              type="button"
              data-testid={`workforce-explorer-view-${v.key}`}
              role="tab"
              aria-selected={active}
              title={v.help}
              onClick={() => setView(v.key)}
              style={viewBtn(active)}
            >
              <I size={12} /> {v.label}
            </button>
          );
        })}
        <span
          data-testid="workforce-explorer-view-hint"
          style={{ ...legend, marginLeft: 'auto' }}
        >
          identity invariant · {isLoading ? '—' : workers.length} workers
        </span>
      </div>

      {/* Views. */}
      {isLoading ? (
        <div style={{ color: 'var(--content-lo)' }}>Loading workforce…</div>
      ) : isEmpty ? (
        <StateTemplate
          variant="dormant"
          code="workforce-explorer-empty"
          icon={Cpu}
          tone="dormant"
          headline="No workers currently registered."
          purpose="The Factory is idle."
        />
      ) : view === 'org' ? (
        <section
          data-testid="workforce-explorer-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 'var(--space-4)',
          }}
        >
          {workers.map((w) => (
            <WorkerCard
              key={w.id}
              name={w.name}
              purpose={w.purpose}
              subject={w.subject}
              state={w.state}
              icon={iconFor(w.name)}
              testId={`workforce-explorer-worker-${w.id}`}
            />
          ))}
        </section>
      ) : view === 'purpose' ? (
        <section
          data-testid="workforce-explorer-purpose-list"
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        >
          {[...workers]
            .sort((a, b) => a.purpose.localeCompare(b.purpose))
            .map((w) => (
              <div
                key={w.id}
                data-testid={`workforce-explorer-purpose-${w.id}`}
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
                <Chip tone={STATE_TONE[w.state] ?? 'dormant'} label={w.state} showGlyph={false} />
              </div>
            ))}
        </section>
      ) : (
        <section
          data-testid="workforce-explorer-status-table"
          role="table"
          aria-label="Workers ordered by state"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--stroke-1)',
            borderRadius: 'var(--radius-2)',
            overflow: 'hidden',
          }}
        >
          <div
            role="row"
            data-testid="workforce-explorer-status-header"
            style={{
              display: 'grid', gridTemplateColumns: '120px 200px 1fr 220px',
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
          {[...workers]
            .sort(
              (a, b) =>
                (STATE_ORDER[a.state] ?? 99) - (STATE_ORDER[b.state] ?? 99),
            )
            .map((w) => (
              <div
                key={w.id}
                role="row"
                data-testid={`workforce-explorer-status-${w.id}`}
                style={{
                  display: 'grid', gridTemplateColumns: '120px 200px 1fr 220px',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-2) var(--space-4)',
                  borderTop: '1px solid var(--stroke-1)',
                  alignItems: 'center',
                }}
              >
                <Chip
                  tone={STATE_TONE[w.state] ?? 'dormant'}
                  label={w.state}
                  showGlyph={false}
                  testId={`workforce-explorer-status-${w.id}-chip`}
                />
                <span
                  className="mono-num"
                  style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)' }}
                >
                  {w.name}
                </span>
                <span
                  className="mono-num"
                  style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}
                >
                  {w.subject ?? '—'}
                </span>
                <span
                  style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', lineHeight: 1.3 }}
                >
                  {w.purpose}
                </span>
              </div>
            ))}
        </section>
      )}
    </section>
  );
};

// ─── styles ──────────────────────────────────────────────────────────────
const legend = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const viewBtn = (active) => ({
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
});

export default WorkforceExplorer;
