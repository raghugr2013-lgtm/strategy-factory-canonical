/*
 * ApprovalCenter — Phase B: institutional approval-center surface.
 *
 * Merges the prototype's visual language with the production wiring of
 * the sibling Approvals surface:
 *
 *   • Visual language (prototype/src/surfaces/ApprovalCenter.tsx, D3/§7.5):
 *     - SurfaceHeader anatomy (eyebrow · headline · briefing · h/m/l trailer)
 *     - Priority sort (risk desc → age desc)
 *     - Resolved-strip with tone-coded chips
 *     - "Open passport" affordance on strategy-scoped approvals
 *     - Surface memory keyed by pathname (Predictable Return)
 *     - Shared risk-facet cascade via navigationStore
 *
 *   • Production wiring (kept from Approvals.jsx):
 *     - Real optimistic UI via `useOptimistic`
 *     - Real API commit via `commitApproval` (falls back to OBSERVE ack)
 *     - Poll-fallback stream via `useStream`
 *     - Palette-drop proposals via `PROPOSAL_EVENT`
 *
 * This surface DOES NOT delete or replace the existing Approvals surface —
 * both routes coexist until operator validation confirms feature parity
 * (see docs/FRONTEND_MIGRATION_PLAN.md §Phase B).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';
import { SurfaceHeader } from '../primitives/SurfaceHeader';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { useOptimistic } from '../adapters/optimistic';
import { fetchApprovals, commitApproval } from '../adapters/approvalsAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useStream } from '../features/useStream';
import { StreamPostmark } from '../features/StreamPostmark';
import { drainProposals, PROPOSAL_EVENT } from '../features/paletteProposals';

const RISK_FILTERS = [
  { key: 'all',      label: 'all' },
  { key: 'high',     label: 'high' },
  { key: 'moderate', label: 'moderate' },
  { key: 'low',      label: 'low' },
];

const RISK_WEIGHT = { high: 2, moderate: 1, low: 0 };

const sortByPriority = (a, b) => {
  const rd = (RISK_WEIGHT[b.risk] ?? 0) - (RISK_WEIGHT[a.risk] ?? 0);
  if (rd !== 0) return rd;
  return (b.ageMinutes ?? 0) - (a.ageMinutes ?? 0);
};

const findStrategyId = (a) => {
  const hay = `${a.title ?? ''} ${a.summary ?? ''} ${a.decisionIdentity ?? ''}`;
  const m = hay.match(/strat-\d+/);
  return m ? m[0] : null;
};

const applyLoad = (state, { list }) => ({ ...state, pending: list });

const applyResolve = (state, { id, verdict }) => {
  const match = state.pending?.find((a) => a.id === id);
  if (!match) return state;
  return {
    ...state,
    pending: state.pending.filter((a) => a.id !== id),
    resolved: [{ ...match, verdict, resolvedAt: Date.now() }, ...state.resolved],
    toast: null,
  };
};

const initialState = { pending: null, resolved: [], toast: null };

export const ApprovalCenter = () => {
  const nav = useNavigate();
  const loc = useLocation();
  const riskFacet    = useNavigationStore((s) => s.facets.risk);
  const setFacet     = useNavigationStore((s) => s.setFacet);
  const saveSurface  = useNavigationStore((s) => s.saveSurface);
  const readSurface  = useNavigationStore((s) => s.readSurface);
  const setCrumb     = useNavigationStore((s) => s.setCrumb);
  const selectStrategy = useWorkspaceStore((s) => s.selectStrategy);

  const [state, dispatch, setState] = useOptimistic(initialState, {
    apply: (s, payload) => (payload.kind === 'load' ? applyLoad(s, payload) : applyResolve(s, payload)),
    commit: async (payload) => {
      if (payload.kind === 'load') return;
      await commitApproval(payload.id, payload.verdict);
    },
    revert: (previous, payload) => ({ ...previous, toast: `${payload.verdict} failed — restored.` }),
  });

  // Restore surface memory (Predictable Return).
  const [restoredMemoryOnce, setRestoredMemoryOnce] = useState(false);
  useEffect(() => {
    if (restoredMemoryOnce) return;
    const mem = readSurface(loc.pathname);
    if (mem?.resolved?.length) setState((prev) => ({ ...prev, resolved: mem.resolved }));
    setRestoredMemoryOnce(true);
  }, [restoredMemoryOnce, readSurface, loc.pathname, setState]);

  // Persist resolved list to surface memory on change.
  useEffect(() => {
    if (state.resolved) saveSurface(loc.pathname, { resolved: state.resolved });
  }, [state.resolved, loc.pathname, saveSurface]);

  // Fetch on risk-facet change (facet cascade).
  useEffect(() => {
    let live = true;
    fetchApprovals({ risk: riskFacet }).then((list) => {
      if (!live) return;
      const buffered = drainProposals();
      dispatch({ kind: 'load', list: [...buffered, ...list] });
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskFacet]);

  // Palette-drop integration (kept from Approvals.jsx).
  useEffect(() => {
    const onProposalDropped = (e) => {
      const proposal = e.detail?.approval;
      if (!proposal) return;
      setState((prev) => ({ ...prev, pending: [proposal, ...(prev.pending ?? [])] }));
    };
    window.addEventListener(PROPOSAL_EVENT, onProposalDropped);
    return () => window.removeEventListener(PROPOSAL_EVENT, onProposalDropped);
  }, [setState]);

  // Stream polling (kept from Approvals.jsx).
  const streamStatus = useStream('approvals', {
    intervalMs: 15_000,
    onTick: (payload) => {
      if (payload.mode === 'initial') return;
      fetchApprovals({ risk: riskFacet }).then((list) => {
        setState((prev) => {
          const proposals = (prev.pending ?? []).filter((a) => a.id?.startsWith('proposal-'));
          return { ...prev, pending: [...proposals, ...list] };
        });
      });
    },
  });

  const pending = state.pending ?? [];
  const sorted = useMemo(() => [...pending].sort(sortByPriority), [pending]);
  const highCount = pending.filter((a) => a.risk === 'high').length;
  const modCount  = pending.filter((a) => a.risk === 'moderate').length;
  const lowCount  = pending.filter((a) => a.risk === 'low').length;

  const openPassport = (a) => {
    const id = findStrategyId(a);
    if (!id) return;
    selectStrategy(id);
    setCrumb({
      path: loc.pathname,
      label: 'back to approval center',
      origin: 'approvals',
      originId: a.id,
    });
    nav(`/c/strategies/${id}`);
  };

  const isLoading = state.pending === null;

  const headline = pending.length === 0
    ? riskFacet === 'all' ? 'You are all caught up.' : `No ${riskFacet}-risk approvals waiting.`
    : `${pending.length} approval${pending.length > 1 ? 's need' : ' needs'} a human decision.`;

  const briefing = pending.length === 0
    ? 'The Factory is running autonomously. New approvals will appear here in real time.'
    : 'Sorted by risk, then by age. Every card carries its receipts. Nothing is decided without provenance.';

  const status = pending.length
    ? `${highCount}h · ${modCount}m · ${lowCount}l`
    : 'clear';

  return (
    <section
      data-testid="approval-center"
      style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1180,
               display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}
    >
      <SurfaceHeader
        eyebrow="Approval Center · human gates"
        headline={headline}
        briefing={briefing}
        status={status}
        testId="approval-center-header"
        actions={<StreamPostmark status={streamStatus} testId="approval-center-stream-postmark" />}
      />

      <div
        data-testid="approval-center-facet-bar"
        role="tablist"
        aria-label="Filter approvals by risk"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span style={facetLegend}>risk ·</span>
        {RISK_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`approval-center-facet-${f.key}`}
            role="tab"
            aria-selected={riskFacet === f.key}
            onClick={() => setFacet('risk', f.key)}
            style={facetChip(riskFacet === f.key)}
          >
            {f.label}
          </button>
        ))}
        <span data-testid="approval-center-cascade-hint" style={{ ...facetLegend, marginLeft: 'auto' }}>
          cascade · risk {riskFacet}
        </span>
      </div>

      {state.toast && (
        <div data-testid="approval-center-toast" role="alert" style={toastStyle}>
          {state.toast}
        </div>
      )}

      {isLoading ? (
        <div style={{ padding: 'var(--space-4)', color: 'var(--content-lo)' }}>
          Loading approvals…
        </div>
      ) : sorted.length === 0 ? (
        <StateTemplate
          variant="empty"
          code={`approval-center-empty-${riskFacet}`}
          icon={CheckCircle2}
          tone="ok"
          headline={
            riskFacet === 'all'
              ? 'Nothing needs your attention.'
              : `No ${riskFacet}-risk approvals in this band.`
          }
          purpose={
            riskFacet === 'all'
              ? 'The Master Bot has cleared the queue.'
              : 'Widen the risk facet to see other decisions.'
          }
          advancedFootnote={`stream · ${streamStatus.mode ?? 'idle'}`}
        />
      ) : (
        <div
          data-testid="approval-center-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
            gap: 'var(--space-4)',
          }}
        >
          {sorted.map((a) => {
            const stratId = findStrategyId(a);
            return (
              <div key={a.id} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <ApprovalCard
                  testId={`approval-center-card-${a.id}`}
                  title={a.title}
                  origin={a.origin}
                  risk={a.risk}
                  summary={a.summary}
                  provenance={a.provenance}
                  decisionIdentity={a.decisionIdentity}
                  ageMinutes={a.ageMinutes}
                  onApprove={() => dispatch({ id: a.id, verdict: 'approve' })}
                  onDefer={() => dispatch({ id: a.id, verdict: 'defer' })}
                  onBlock={() => dispatch({ id: a.id, verdict: 'block' })}
                />
                {stratId && (
                  <button
                    data-testid={`approval-center-open-passport-${a.id}`}
                    onClick={() => openPassport(a)}
                    style={openPassportButton}
                  >
                    open passport · {stratId} →
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {state.resolved.length > 0 && (
        <section
          data-testid="approval-center-resolved-strip"
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
        >
          <div style={sectionLegend}>resolved · this session</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {state.resolved.map((r) => {
              const tone = r.verdict === 'approve' ? 'ok' : r.verdict === 'block' ? 'crit' : 'info';
              return (
                <span key={r.id} data-testid={`approval-center-resolved-${r.id}`}>
                  <Chip tone={tone} label={`${r.verdict} · ${r.id}`} showGlyph={false} />
                </span>
              );
            })}
          </div>
        </section>
      )}
    </section>
  );
};

// ─── styles ───────────────────────────────────────────────
const facetLegend = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const facetChip = (active) => ({
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

const toastStyle = {
  padding: 'var(--space-2) var(--space-3)',
  background: 'rgba(240,180,41,0.14)',
  color: 'var(--sig-warn)',
  borderRadius: 'var(--radius-1)',
  fontSize: 'var(--font-body-sm)',
};

const openPassportButton = {
  alignSelf: 'flex-end',
  background: 'transparent',
  color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '3px 8px',
  fontFamily: 'ui-monospace, monospace',
  fontSize: 'var(--font-caption)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
};

const sectionLegend = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

export default ApprovalCenter;
