/*
 * Approval Center — S3. Unified queue with FacetBar (risk) + optimistic UI.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · D3 · Bible §7.5
 */
import React, { useEffect } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { FacetBar } from '../features/FacetBar';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { StateTemplate } from '../primitives/StateTemplate';
import { Chip } from '../primitives/Chip';
import { useOptimistic } from '../adapters/optimistic';
import { fetchApprovals, commitApproval } from '../adapters/approvalsAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';

const RISK_OPTIONS = [
  { key: 'all', label: 'All' },
  { key: 'low', label: 'Low' },
  { key: 'moderate', label: 'Moderate' },
  { key: 'high', label: 'High' },
];

const initialState = { pending: null, resolved: [], toast: null };

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

const applyLoad = (state, { list }) => ({ ...state, pending: list });

export const Approvals = () => {
  const riskFacet = useNavigationStore((s) => s.facets.risk);
  const [state, dispatch, setState] = useOptimistic(initialState, {
    apply: (s, payload) => {
      if (payload.kind === 'load') return applyLoad(s, payload);
      return applyResolve(s, payload);
    },
    commit: async (payload) => {
      if (payload.kind === 'load') return;
      await commitApproval(payload.id, payload.verdict);
    },
    revert: (previous, payload) => ({ ...previous, toast: `${payload.verdict} failed — restored.` }),
  });

  useEffect(() => {
    let live = true;
    fetchApprovals({ risk: riskFacet }).then((list) => { if (live) dispatch({ kind: 'load', list }); });
    return () => { live = false; };
  }, [riskFacet, dispatch]);

  const pending = state.pending ?? [];
  const highCount = pending.filter((a) => a.risk === 'high').length;
  const modCount = pending.filter((a) => a.risk === 'moderate').length;
  const lowCount = pending.filter((a) => a.risk === 'low').length;
  const agedCount = pending.filter((a) => a.ageMinutes >= 60).length;

  const headline = pending.length === 0
    ? 'Nothing needs a human decision right now.'
    : `${pending.length} approval${pending.length > 1 ? 's need' : ' needs'} a human decision.`;

  return (
    <section data-testid="approvals"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1000,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                      letterSpacing: '0.1em', textTransform: 'uppercase',
                      marginBottom: 'var(--space-2)' }}>Approvals</div>
        <h1 data-testid="approvals-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
          {headline}
        </h1>
        <p data-testid="approvals-briefing"
           style={{ margin: 0, maxWidth: 720, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          Approvals arrive with the full evidence bundle already attached. Approve, defer, or block —
          the queue updates optimistically. In Sprint 1 the backend is in OBSERVE mode; verdicts are
          acknowledged locally and queued for commit when the freeze lifts.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}>
        <FacetBar axis="risk" options={RISK_OPTIONS} testIdPrefix="approvals-facet" />
        <span data-testid="approvals-cascade-hint"
              style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                       textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          cascade · risk {riskFacet}
        </span>
        <span data-testid="approvals-facet-counts" className="mono-num"
              style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                       color: 'var(--content-lo)', textTransform: 'uppercase',
                       letterSpacing: '0.06em' }}>
          {highCount}H · {modCount}M · {lowCount}L · aged {agedCount}
        </span>
      </div>

      {state.toast && (
        <div data-testid="approvals-toast" role="alert"
             style={{ padding: 'var(--space-2) var(--space-3)',
                      background: 'rgba(240,180,41,0.14)', color: 'var(--sig-warn)',
                      borderRadius: 'var(--radius-1)', fontSize: 'var(--font-body-sm)' }}>
          {state.toast}
        </div>
      )}

      {state.pending === null ? (
        <div style={{ padding: 'var(--space-4)', color: 'var(--content-lo)' }}>Loading approvals…</div>
      ) : pending.length === 0 ? (
        <StateTemplate variant="empty" code="approvals-empty" icon={CheckCircle2} tone="ok"
                       headline="No approvals in this risk band."
                       purpose="Clear the facet or check back after the next scheduled run." />
      ) : (
        <div data-testid="approvals-grid"
             style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {pending.map((a) => (
            <ApprovalCard key={a.id}
                          testId={`approval-${a.id}`}
                          title={a.title}
                          origin={a.origin}
                          risk={a.risk}
                          summary={a.summary}
                          provenance={a.provenance}
                          decisionIdentity={a.decisionIdentity}
                          ageMinutes={a.ageMinutes}
                          onApprove={() => dispatch({ id: a.id, verdict: 'approve' })}
                          onDefer={() => dispatch({ id: a.id, verdict: 'defer' })}
                          onBlock={() => dispatch({ id: a.id, verdict: 'block' })} />
          ))}
        </div>
      )}

      {state.resolved.length > 0 && (
        <div data-testid="approvals-resolved-strip"
             style={{ marginTop: 'var(--space-4)', paddingTop: 'var(--space-4)',
                      borderTop: '1px solid var(--stroke-1)',
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Resolved · this session
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {state.resolved.map((r) => (
              <span key={r.id} data-testid={`approvals-resolved-${r.id}`}>
                <Chip tone={r.verdict === 'approve' ? 'ok' : r.verdict === 'block' ? 'crit' : 'info'}
                      label={`${r.verdict} · ${r.id}`}
                      showGlyph={false} />
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
