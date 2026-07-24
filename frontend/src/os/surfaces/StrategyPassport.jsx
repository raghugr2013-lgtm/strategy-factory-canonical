/*
 * Strategy Passport — canonical §10 surface.
 * refs docs/ARCHITECTURE.md §10 · Strategy Passport architecture
 * refs docs/ARCHITECTURE.md §4 · End-to-end strategy lifecycle
 * refs docs/ARCHITECTURE.md §9 · Workspace context model
 *
 * The Passport is the primary noun of the AI Factory. Every other surface
 * is a lens onto Passports. This file implements the canonical detail view
 * at /c/strategies/:id with the four §10.2 tabs:
 *
 *   evidence   (default) · identity + provenance + guardrails + evidence bundle
 *   lineage    · ordered state transitions
 *   neighbours · top-k nearest historical strategies (POST /api/knowledge/nearest)
 *   deployments· active broker connections (DEFERRED · §15 execution workspace)
 *
 * §10.3 Passport is the ONLY surface that can promote a strategy. The
 * PROMOTE CTA opens the shell-mounted Approvals modal (§12) pre-filled
 * with the exact §13 event name it will emit. Under Backend Feature
 * Freeze v1.1.0-stage4 the executor is a client-side no-op — the modal
 * writes §13 events to the timelineShim only; the Lineage tab below reads
 * them back via `useTimelineEvents({ objectId })`.
 *
 * Data path — live, no synthetic fallbacks:
 *   GET  /api/strategies/{id}         · identity + status + tags + timestamps
 *   POST /api/knowledge/nearest       · historical neighbours (tab 3)
 *
 * Workspace context (§9) — the URL param drives the workspace context.
 * Landing on this route sets sid=<id>; Pipeline highlights the same row.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, ArrowRight, ClipboardCheck, FileWarning, GitBranch,
  Rocket, ScrollText, ShieldAlert, Sparkles, Users,
} from 'lucide-react';
import { apiFetch, isLiveMode } from '../adapters/apiClient';
import { findNearestStrategies, listStrategies } from '../adapters/strategyLabAdapter';
import { SignalStateBadge, FreezeCaption } from './engineering/LivenessBadge';
import { useWorkspaceContext } from '../hooks/useWorkspaceContext';
import { openApproval } from '../shell/ApprovalsModal';
import { useTimelineEvents } from '../adapters/timelineShim';
import { useNavigationStore } from '../workspace-state/navigationStore';

const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};

// §4.1 state ladder — used by the Lineage tab and the promotion CTAs.
const STATE_LADDER = [
  { id: 'draft',       label: 'Draft',       accent: 'var(--sig-info)'     },
  { id: 'backtested',  label: 'Backtested',  accent: 'var(--sig-advisory)' },
  { id: 'champion',    label: 'Champion',    accent: 'var(--accent-gold)'  },
  { id: 'deployed',    label: 'Deployed',    accent: 'var(--sig-ok)'       },
  { id: 'retired',     label: 'Retired',     accent: 'var(--sig-dormant)'  },
];

const STATE_ID_OF = (status) => {
  const v = (status || '').toString().toLowerCase();
  if (['backtested', 'tested', 'validated'].includes(v)) return 'backtested';
  if (['deployed', 'live', 'active'].includes(v)) return 'deployed';
  if (['champion'].includes(v)) return 'champion';
  if (['retired', 'archived'].includes(v)) return 'retired';
  return 'draft';
};

// §4.2 next-state action — used to label the CTA + drive the Approvals
// modal (§12) with the exact §13 event name it will emit. Consequences
// bullets mirror the anatomy in §12.1. Under Backend Feature Freeze
// v1.1.0-stage4 the executor is a no-op — the modal writes §13 events to
// the client-side timelineShim only; no backend mutation occurs.
const NEXT_TRANSITION = {
  draft: {
    label: 'Promote to Backtested',
    cite: '§4 · draft → backtested',
    event_name: 'operator_strategy_promoted_to_backtested',
    action_label: 'promote to backtested',
    consequences: [
      'transition state draft → backtested',
      'write timeline event (§13)',
      'no broker connection is touched (backend freeze)',
    ],
  },
  backtested: {
    label: 'Promote to Champion',
    cite: '§4 · backtested → champion',
    event_name: 'operator_strategy_promoted_to_champion',
    action_label: 'promote to champion',
    consequences: [
      'transition state backtested → champion',
      'strategy becomes eligible for a Passport gate',
      'write timeline event (§13)',
    ],
  },
  champion: {
    label: 'Deploy to Paper',
    cite: '§22 · READY → PAPER TRADING',
    event_name: 'operator_strategy_deployed_to_paper',
    action_label: 'deploy to paper',
    consequences: [
      'request paper deployment (execution workspace · §15)',
      'no money is at risk — paper broker only',
      'write timeline event (§13)',
    ],
  },
  deployed: {
    label: 'Retire strategy',
    cite: '§4 · retire',
    event_name: 'operator_strategy_retired',
    action_label: 'retire strategy',
    consequences: [
      'transition state deployed → retired',
      'strategy loses deploy eligibility',
      'write timeline event (§13)',
    ],
  },
  retired: {
    label: 'Reinstate as draft',
    cite: '§4 · retired → draft',
    event_name: 'operator_strategy_reinstated_as_draft',
    action_label: 'reinstate as draft',
    consequences: [
      'transition state retired → draft',
      'strategy re-enters the composition ladder',
      'write timeline event (§13)',
    ],
  },
};

const fetchStrategyLive = async (id) => {
  if (!isLiveMode()) return { liveness: 'gated', reason: 'REACT_APP_BACKEND_URL not configured', payload: null };
  try {
    const payload = await apiFetch(`/api/strategies/${encodeURIComponent(id)}`);
    return { liveness: 'live', reason: null, payload };
  } catch (err) {
    if (err.status === 404) return { liveness: 'error', reason: 'strategy not found', payload: null };
    if (err.status === 401) return { liveness: 'error', reason: 'unauthorized', payload: null };
    return { liveness: 'error', reason: err.message || 'network error', payload: null };
  }
};

export const StrategyPassport = () => {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'evidence';
  const { context, setContext } = useWorkspaceContext();

  // Return-crumb consumer (Rule of Predictable Return · E5 §4.5).
  // Consumers such as StrategyExplorer / TimelineExplorer / ApprovalCenter
  // stamp a crumb via navigationStore.setCrumb before navigating here.
  // We read it (but do not consume it eagerly — the operator may want the
  // back button to remain until they actually click it) and clear it on
  // click via consumeCrumb().
  const returnCrumb = useNavigationStore((s) => s.crumb);
  const consumeCrumb = useNavigationStore((s) => s.consumeCrumb);

  const [strategyState, setStrategyState] = useState({ status: 'loading', liveness: 'partial', reason: null, payload: null });
  const [neighbourState, setNeighbourState] = useState({ status: 'idle', liveness: 'partial', reason: null, matches: [], total: 0 });
  const [siblingState, setSiblingState] = useState({ status: 'loading', liveness: 'partial', list: [] });

  const load = useCallback(async () => {
    setStrategyState((s) => ({ ...s, status: 'loading' }));
    const [strat, siblings] = await Promise.all([
      fetchStrategyLive(id),
      listStrategies(),
    ]);
    setStrategyState({ status: 'ready', ...strat });
    setSiblingState({ status: 'ready', liveness: siblings.liveness, list: siblings.payload || [] });
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // §9 — landing here binds the strategy id into the workspace context so
  // Pipeline / Coverage / Datasets highlight or filter accordingly.
  useEffect(() => {
    if (id) setContext({ strategy: id });
  }, [id, setContext]);

  const strategy = strategyState.payload;
  const currentStateId = STATE_ID_OF(strategy?.status);
  const currentStateEntry = STATE_LADDER.find((s) => s.id === currentStateId);
  const nextTransition = NEXT_TRANSITION[currentStateId];

  // On landing on the Neighbours tab, run the search once against the
  // strategy's own name+description as the query text.
  useEffect(() => {
    if (activeTab !== 'neighbours' || !strategy || neighbourState.status !== 'idle') return;
    (async () => {
      setNeighbourState((s) => ({ ...s, status: 'loading' }));
      const query = [strategy.name, strategy.description].filter(Boolean).join(' · ');
      const res = await findNearestStrategies({
        strategy_text: query,
        pair: strategy.symbol,
        timeframe: strategy.timeframe,
        top_k: 5,
      });
      setNeighbourState({
        status: 'ready',
        liveness: res.liveness,
        reason: res.reason,
        matches: res.payload?.matches || [],
        total: res.payload?.total_corpus || 0,
      });
    })();
  }, [activeTab, strategy, neighbourState.status]);

  const setTab = (t) => setSearchParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set('tab', t);
    return next;
  }, { replace: true });

  const aggregate = useMemo(() => {
    if (strategyState.status === 'loading') return { liveness: 'partial', reason: 'loading passport …' };
    if (strategyState.liveness === 'error') return { liveness: 'error', reason: strategyState.reason };
    if (!strategy) return { liveness: 'empty', reason: 'no strategy record returned' };
    return { liveness: 'live', reason: null };
  }, [strategyState, strategy]);

  // ── RENDER ─────────────────────────────────────────────────────────────

  if (strategyState.status === 'ready' && strategyState.liveness === 'error') {
    return (
      <section data-testid="engineering-surface-passport"
               style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1000 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
          {returnCrumb ? (
            <Link data-testid="passport-back"
                  to={returnCrumb.path}
                  onClick={() => consumeCrumb()}
                  style={backLink}>
              <ArrowLeft size={12} /> {returnCrumb.label}
            </Link>
          ) : (
            <Link data-testid="passport-back" to="/c/strategies" style={backLink}>
              <ArrowLeft size={12} /> Passports
            </Link>
          )}
          <span style={{ marginLeft: 'auto' }}>
            <SignalStateBadge state="error" reason={strategyState.reason} testId="passport-liveness" />
          </span>
        </div>
        <div data-testid="passport-error"
             style={{ ...panel, padding: 'var(--space-5)', borderLeft: '3px solid var(--sig-crit)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'var(--sig-crit)', marginBottom: 'var(--space-2)' }}>
            <FileWarning size={14} strokeWidth={1.75} />
            <span style={{ ...eyebrow, color: 'var(--sig-crit)' }}>Passport unavailable</span>
          </div>
          <div style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)' }}>
            Strategy id <code className="mono-num" style={{ color: 'var(--content-hi)' }}>{id}</code>
            {' '}could not be fetched · {strategyState.reason}. The interface is live — verify the id or open
            <Link to="/c/strategies" data-testid="passport-error-cta" style={{ color: 'var(--sig-info)', marginLeft: 4 }}>Strategy Passports ↗</Link>.
          </div>
        </div>
      </section>
    );
  }

  return (
    <section data-testid="engineering-surface-passport"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        {returnCrumb ? (
          <Link data-testid="passport-back"
                to={returnCrumb.path}
                onClick={() => consumeCrumb()}
                style={backLink}>
            <ArrowLeft size={12} /> {returnCrumb.label}
          </Link>
        ) : (
          <Link data-testid="passport-back" to="/c/strategies" style={backLink}>
            <ArrowLeft size={12} /> Passports
          </Link>
        )}
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }} data-testid="passport-id">
          {id}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          <SignalStateBadge state={aggregate.liveness} reason={aggregate.reason} testId="passport-liveness" />
        </span>
      </div>

      {/* IDENTITY */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="passport-name"
              style={{ margin: 0, fontSize: 'var(--font-h1)', fontWeight: 400, letterSpacing: '-0.015em', color: 'var(--content-hi)' }}>
            <ClipboardCheck size={22} strokeWidth={1.5} color="var(--accent-gold)" style={{ verticalAlign: '-3px', marginRight: 10 }} />
            {strategy?.name || 'Strategy · loading'}
          </h1>
          <p data-testid="passport-description"
             style={{ margin: 'var(--space-2) 0 var(--space-3) 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 900 }}>
            {strategy?.description || 'The primary noun of the AI Factory. Identity · provenance · evidence · lineage · guardrails · neighbours · deployments.'}
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <StateChip stateId={currentStateId} testId="passport-state-chip" />
            {(strategy?.tags || []).map((t, i) => (
              <span key={t} data-testid={`passport-tag-${i}`} style={tagChip}>{t}</span>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <div data-testid="passport-symbol-timeframe" style={{ ...eyebrow, color: 'var(--content-hi)' }}>
            {(strategy?.symbol || '—')} · {(strategy?.timeframe || '—')}
          </div>
          <div style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {iso(strategy?.updated_at)}
          </div>
        </div>
      </div>

      {/* PROMOTION BAR (§10.3 · Approvals pattern via §12 · ApprovalsModal) */}
      <div data-testid="passport-promotion-bar"
           style={{
             ...panel,
             padding: 'var(--space-3) var(--space-4)',
             marginBottom: 'var(--space-5)',
             display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap',
           }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 240 }}>
          <span style={eyebrow}>Governance</span>
          <span style={{ color: 'var(--content-hi)', fontSize: 'var(--font-body-sm)' }}>
            Only this surface can transition the strategy state
            <span style={{ color: 'var(--content-lo)', marginLeft: 6 }}>· §10.3 promotion boundary</span>
          </span>
        </div>
        {nextTransition && currentStateId !== 'retired' && strategy && (
          <button type="button"
                  data-testid="passport-promote-cta"
                  onClick={() => openApproval({
                    action_label: nextTransition.action_label,
                    event_name: nextTransition.event_name,
                    target: {
                      type: 'strategy',
                      id: strategy.strategy_id || strategy.id || id,
                      name: strategy.name || '(unnamed strategy)',
                    },
                    context: {
                      pair: strategy.symbol || context.pair || null,
                      timeframe: strategy.timeframe || context.timeframe || null,
                      cycle_id: context.cycle || null,
                    },
                    consequences: nextTransition.consequences,
                    // Backend freeze v1.1.0-stage4 — no mutation. The modal
                    // emits the §13 events; the Lineage tab reads them back.
                    executor: null,
                  })}
                  style={promoteBtn}>
            <Rocket size={12} strokeWidth={1.75} />
            <span>{nextTransition.label}</span>
          </button>
        )}
        <SignalStateBadge state={strategy ? 'live' : 'partial'}
                          reason={strategy
                            ? `${nextTransition?.cite || 'no transition available'} · Approvals modal ready (§12).`
                            : 'loading strategy …'}
                          testId="passport-approvals-liveness" />
      </div>

      {/* TAB BAR */}
      <div data-testid="passport-tab-bar"
           style={{ display: 'flex', gap: 'var(--space-1)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 'var(--space-4)' }}>
        {[
          { id: 'evidence',    label: 'Evidence',    icon: ShieldAlert   },
          { id: 'lineage',     label: 'Lineage',     icon: GitBranch     },
          { id: 'neighbours',  label: 'Neighbours',  icon: Users         },
          { id: 'deployments', label: 'Deployments', icon: Rocket        },
        ].map((t) => (
          <button key={t.id}
                  type="button"
                  data-testid={`passport-tab-${t.id}`}
                  onClick={() => setTab(t.id)}
                  style={{
                    ...tabBtn,
                    color: activeTab === t.id ? 'var(--content-hi)' : 'var(--content-md)',
                    borderBottom: activeTab === t.id ? '2px solid var(--accent-gold)' : '2px solid transparent',
                  }}>
            <t.icon size={12} strokeWidth={1.75} />
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* TAB CONTENT */}
      {activeTab === 'evidence'    && <EvidenceTab strategy={strategy} loading={strategyState.status === 'loading'} />}
      {activeTab === 'lineage'     && <LineageTab strategy={strategy} currentStateId={currentStateId} />}
      {activeTab === 'neighbours'  && <NeighboursTab state={neighbourState} strategy={strategy} />}
      {activeTab === 'deployments' && <DeploymentsTab />}

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)', marginTop: 'var(--space-5)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <FooterPill to="/c/engineering/strategy-pipeline" label="Strategy Pipeline"   testId="passport-related-pipeline" />
          <FooterPill to="/c/engineering/strategy-lab"      label="Strategy Lab"        testId="passport-related-lab" />
          <FooterPill to="/c/engineering/validation"        label="Validation"          testId="passport-related-validation" />
        </div>
      </div>
    </section>
  );
};

// ── TAB · EVIDENCE ────────────────────────────────────────────────────────

const EvidenceTab = ({ strategy, loading }) => {
  const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');
  return (
    <div data-testid="passport-tab-content-evidence">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        <MetricTile testId="passport-metric-status"   label="Current state"    value={(strategy?.status || '—').toUpperCase()} tone="info" />
        <MetricTile testId="passport-metric-symbol"   label="Symbol"           value={strategy?.symbol    || '—'} />
        <MetricTile testId="passport-metric-tf"       label="Timeframe"        value={strategy?.timeframe || '—'} />
        <MetricTile testId="passport-metric-tag-count" label="Tags"            value={nf((strategy?.tags || []).length)} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        {/* Provenance · §10.1 */}
        <div data-testid="passport-provenance-panel" style={panelBox}>
          <div style={panelHeaderInline}>Provenance · §10.1</div>
          <KV k="Strategy id" v={<code className="mono-num" style={{ color: 'var(--content-hi)' }}>{strategy?.strategy_id || '—'}</code>} />
          <KV k="Origin"      v={(strategy?.tags || []).includes('lab') ? 'Strategy Lab · CNL' : (strategy?.description || '').startsWith('KB') ? 'KB · import' : 'live · /api/strategies'} />
          <KV k="Created by"  v={<code className="mono-num" style={{ color: 'var(--content-hi)' }}>{strategy?.created_by || '—'}</code>} />
          <KV k="Created"     v={iso(strategy?.created_at)} />
          <KV k="Framework"   v="v1.1.0-stage4" last />
        </div>
        {/* Guardrails · §10.1 */}
        <div data-testid="passport-guardrails-panel" style={panelBox}>
          <div style={panelHeaderInline}>Guardrails · §10.1</div>
          <KV k="Learning only"       v={<GuardrailChip on={(strategy?.tags || []).some((t) => /kb|import|learning/i.test(t))} testId="passport-guardrail-learning" />} />
          <KV k="Deploy eligible"     v={<GuardrailChip on={false} inverse testId="passport-guardrail-deploy" />} />
          <KV k="Framework version"   v="v1.1.0-stage4" />
          <KV k="Two-person rule"     v={<span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>required · §12 (Slice γ)</span>} last />
        </div>
      </div>
      {/* Evidence bundle placeholder — §4.2 · backtests collection is post-freeze */}
      <div data-testid="passport-evidence-bundle" style={{ ...panelBox, marginBottom: 'var(--space-4)' }}>
        <div style={{ ...panelHeaderInline, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Evidence bundle · §4.2</span>
          <SignalStateBadge state="deferred" reason="`backtests` collection is post-freeze · §4.2" testId="passport-evidence-liveness" />
        </div>
        <div style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, padding: 'var(--space-2) 0' }}>
          Per §4.2 each state has an immutable evidence artefact. The
          <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>backtests</code>
          collection is scheduled for post-freeze; when it lands, this panel will surface the replay hash + p&amp;l series + validation verdict for the current state without any Passport UI change.
        </div>
      </div>
      {loading && (
        <div data-testid="passport-loading" style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>
          Loading …
        </div>
      )}
    </div>
  );
};

// ── TAB · LINEAGE ─────────────────────────────────────────────────────────

const LineageTab = ({ strategy, currentStateId }) => {
  const currentIdx = STATE_LADDER.findIndex((s) => s.id === currentStateId);
  // §13 · Timeline event query — reads client-side shim; when the backend
  // exposes a real Timeline endpoint the shim swaps with no UI change.
  const objectId = strategy?.strategy_id || strategy?.id || null;
  const events = useTimelineEvents({ objectId });
  return (
    <div data-testid="passport-tab-content-lineage">
      <div data-testid="passport-lineage-ladder" style={{ ...panelBox, marginBottom: 'var(--space-4)' }}>
        <div style={panelHeaderInline}>State ladder · §4.1</div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${STATE_LADDER.length}, minmax(0, 1fr))`, gap: 'var(--space-2)' }}>
          {STATE_LADDER.map((s, i) => {
            const passed = i < currentIdx;
            const current = i === currentIdx;
            return (
              <div key={s.id}
                   data-testid={`passport-lineage-stage-${s.id}`}
                   data-active={current ? 'true' : undefined}
                   style={{
                     borderRadius: 'var(--radius-2)',
                     padding: 'var(--space-3)',
                     background: current ? 'color-mix(in oklab, var(--accent-gold) 8%, transparent)' : 'var(--surface-2)',
                     border: `1px solid ${current ? 'var(--accent-gold)' : 'var(--stroke-1)'}`,
                     borderLeft: `3px solid ${s.accent}`,
                     opacity: passed ? 1 : current ? 1 : 0.55,
                   }}>
                <div style={{ ...eyebrow, color: passed || current ? 'var(--content-hi)' : 'var(--content-lo)' }}>
                  Stage {i + 1}
                </div>
                <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', marginTop: 4 }}>
                  {s.label}
                </div>
                {current && <div style={{ marginTop: 4, ...eyebrow, color: 'var(--accent-gold)' }}>Current</div>}
              </div>
            );
          })}
        </div>
      </div>
      <div data-testid="passport-lineage-events" style={panelBox}>
        <div style={{ ...panelHeaderInline, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>State transitions</span>
          <SignalStateBadge state={events.length > 0 ? 'partial' : 'deferred'}
                            reason={events.length > 0
                              ? `${events.length} shim event(s) · backend Timeline endpoint post-freeze (§13)`
                              : 'Timeline endpoint post-freeze · shim empty (§13)'}
                            testId="passport-lineage-events-liveness" />
        </div>
        {events.length === 0 ? (
          <div data-testid="passport-lineage-events-empty" style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, padding: 'var(--space-2) 0' }}>
            Per §13, every state transition writes to Timeline as an event with actor · reason · timestamp. Under Backend Feature Freeze v1.1.0-stage4 the emitter is a client-side shim — approve a promotion above and the request/approval events for this strategy will appear here. The ladder above reflects the live
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>strategy.status</code>
            from <code style={{ color: 'var(--sig-info)' }}>GET /api/strategies/{'{'}id{'}'}</code>.
          </div>
        ) : (
          <div data-testid="passport-lineage-events-list" role="table" aria-label="Timeline events for this strategy">
            <div role="row" style={eventRowHead}>
              <span>Event</span>
              <span>Actor</span>
              <span>Reason</span>
              <span style={{ textAlign: 'right' }}>Timestamp</span>
            </div>
            {events.map((e, i) => (
              <div key={e.event_id} role="row" data-testid={`passport-lineage-event-row-${i}`} style={eventRowBody}>
                <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-caption)' }}>{e.event_name}</span>
                <span style={{ color: 'var(--content-md)', fontSize: 'var(--font-caption)' }}>
                  {e.actor?.email || 'anonymous'}
                  <span style={{ color: 'var(--content-lo)', marginLeft: 4 }}>· {e.actor?.role || '—'}</span>
                </span>
                <span style={{ color: 'var(--content-md)', fontSize: 'var(--font-caption)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={e.reason || ''}>
                  {e.reason || <span style={{ color: 'var(--content-lo)' }}>—</span>}
                </span>
                <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-md)', fontSize: 'var(--font-caption)' }}>{iso(e.ts)}</span>
              </div>
            ))}
          </div>
        )}
        <div style={{ padding: 'var(--space-3) 0 0 0', display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-body-sm)', borderTop: '1px solid var(--stroke-1)', marginTop: 'var(--space-2)' }}>
          <span style={{ color: 'var(--content-lo)' }}>Latest known transition</span>
          <span className="mono-num" style={{ color: 'var(--content-hi)' }}>
            {iso(strategy?.updated_at)} · <span style={{ color: 'var(--content-md)' }}>{(strategy?.status || '—').toUpperCase()}</span>
          </span>
        </div>
      </div>
    </div>
  );
};

// ── TAB · NEIGHBOURS ──────────────────────────────────────────────────────

const NeighboursTab = ({ state, strategy }) => {
  return (
    <div data-testid="passport-tab-content-neighbours">
      <div data-testid="passport-neighbours-panel"
           style={{ ...panel, padding: 0, overflow: 'hidden' }}>
        <div style={{ ...panelHeaderRow, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Historical neighbours · POST /api/knowledge/nearest</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <SignalStateBadge state={state.status === 'ready' ? state.liveness : 'partial'}
                              reason={state.reason || (state.status === 'loading' ? 'searching …' : null)}
                              testId="passport-neighbours-liveness" />
            <span className="mono-num" data-testid="passport-neighbours-count" style={{ color: 'var(--content-lo)' }}>
              {state.matches.length} / {state.total || 0} corpus
            </span>
          </div>
        </div>
        {state.matches.length === 0 ? (
          <div data-testid="passport-neighbours-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              Corpus · {state.total || 0} strategies
            </div>
            {state.status === 'loading'
              ? 'Searching the historical KB with the strategy\u2019s own name and description …'
              : `No historical neighbours found for ${strategy?.symbol || '—'} · ${strategy?.timeframe || '—'}. The interface is live — as soon as the KB is populated (deferred pending compatibility review), matches will appear here.`}
          </div>
        ) : (
          <div role="table" aria-label="Historical neighbours">
            <div role="row" style={rowHead}>
              <span>Strategy id</span>
              <span>Pair · TF</span>
              <span>Type</span>
              <span style={{ textAlign: 'right' }}>Score</span>
              <span style={{ textAlign: 'right' }}>Verdict</span>
            </div>
            {state.matches.map((m, i) => (
              <div key={m.strategy_id || i} role="row" data-testid={`passport-neighbour-row-${i}`} style={rowBody}>
                <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-caption)' }}>{m.strategy_id}</span>
                <span>{[m.pair, m.timeframe].filter(Boolean).join(' · ') || '—'}</span>
                <span style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>{m.strategy_type || '—'}</span>
                <span className="mono-num" style={{ textAlign: 'right' }}>{typeof m.similarity_score === 'number' ? m.similarity_score.toFixed(3) : '—'}</span>
                <span style={{ textAlign: 'right', color: 'var(--sig-warn)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  {m.learning_only !== false ? 'learning only' : 'eligible'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ── TAB · DEPLOYMENTS ─────────────────────────────────────────────────────

const DeploymentsTab = () => (
  <div data-testid="passport-tab-content-deployments">
    <div data-testid="passport-deployments-panel" style={panelBox}>
      <div style={{ ...panelHeaderInline, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Active broker connections · §15</span>
        <SignalStateBadge state="deferred" reason="Execution workspace is post-freeze · §15" testId="passport-deployments-liveness" />
      </div>
      <div style={{ color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, padding: 'var(--space-2) 0' }}>
        Deployments (paper and live) are surfaced from the Execution workspace
        (§15) which is deliberately isolated from Engineering by group and by
        banner. Post-freeze, this tab will list every active broker connection
        carrying this strategy, its envelope, and its fill history, without any
        Passport UI change. Kill switch remains reachable in ≤ 3 seconds from
        every state.
      </div>
    </div>
  </div>
);

// ── VISUAL PRIMITIVES ─────────────────────────────────────────────────────

const StateChip = ({ stateId, testId }) => {
  const s = STATE_LADDER.find((x) => x.id === stateId) || STATE_LADDER[0];
  return (
    <span data-testid={testId}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '3px 10px',
            borderRadius: 999,
            background: `color-mix(in oklab, ${s.accent} 12%, transparent)`,
            border: `1px solid color-mix(in oklab, ${s.accent} 40%, transparent)`,
            color: s.accent,
            fontSize: 'var(--font-caption)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            fontWeight: 500,
          }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
      {s.label}
    </span>
  );
};

const GuardrailChip = ({ on, inverse, testId }) => {
  // "learning only" is a positive guardrail when on. "deploy eligible" is
  // a positive property when on (inverse). Both tint accordingly.
  const active = inverse ? !on : on;
  const accent = active ? 'var(--sig-warn)' : 'var(--sig-ok)';
  const label = inverse
    ? (on ? 'ELIGIBLE' : 'NOT ELIGIBLE')
    : (on ? 'LEARNING ONLY' : 'NOT SET');
  return (
    <span data-testid={testId}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '2px 8px', borderRadius: 999,
            background: `color-mix(in oklab, ${accent} 12%, transparent)`,
            border: `1px solid color-mix(in oklab, ${accent} 32%, transparent)`,
            color: accent,
            fontSize: 'var(--font-caption)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
      <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor' }} />
      {label}
    </span>
  );
};

const MetricTile = ({ testId, label, value, tone = 'info' }) => {
  const accent = {
    ok: 'var(--sig-ok)', info: 'var(--sig-info)', warn: 'var(--sig-warn)',
    crit: 'var(--sig-crit)', dormant: 'var(--sig-dormant)',
  }[tone] || 'var(--sig-info)';
  return (
    <div data-testid={testId}
         style={{
           background: 'var(--surface-1)',
           border: '1px solid var(--stroke-1)',
           borderLeft: `2px solid ${accent}`,
           borderRadius: 'var(--radius-3)',
           padding: 'var(--space-4)',
           display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
         }}>
      <span style={eyebrow}>{label}</span>
      <span className="mono-num"
            style={{ fontSize: 'var(--font-h2)', color: 'var(--content-hi)', fontWeight: 500, lineHeight: 1 }}>
        {value}
      </span>
    </div>
  );
};

const KV = ({ k, v, last }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)', padding: 'var(--space-2) 0', borderBottom: last ? 'none' : '1px solid var(--stroke-1)', alignItems: 'center' }}>
    <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-body-sm)' }}>{k}</span>
    <span style={{ color: 'var(--content-hi)', fontSize: 'var(--font-body-sm)' }}>{v}</span>
  </div>
);

const FooterPill = ({ to, label, testId }) => (
  <Link to={to} data-testid={testId} style={pill}>
    <span>{label}</span>
    <ArrowRight size={11} strokeWidth={1.75} />
  </Link>
);

// ── STYLES ────────────────────────────────────────────────────────────────

const eyebrow = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
};

const panel = {
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-1)',
  borderRadius: 'var(--radius-3)',
};

const panelBox = {
  ...panel,
  padding: 'var(--space-4)',
};

const panelHeaderInline = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 'var(--space-3)',
  paddingBottom: 'var(--space-3)',
  borderBottom: '1px solid var(--stroke-1)',
};

const panelHeaderRow = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  padding: 'var(--space-3) var(--space-4)',
  borderBottom: '1px solid var(--stroke-1)',
};

const backLink = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  color: 'var(--content-md)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  textDecoration: 'none',
};

const tabBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: 'var(--space-2) var(--space-3)',
  background: 'transparent',
  border: 'none',
  borderBottom: '2px solid transparent',
  fontSize: 'var(--font-body-sm)',
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};

const promoteBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: 'var(--space-2) var(--space-4)',
  background: 'color-mix(in oklab, var(--accent-gold) 12%, var(--surface-2))',
  color: 'var(--accent-gold)',
  border: '1px solid color-mix(in oklab, var(--accent-gold) 45%, var(--stroke-2))',
  borderRadius: 'var(--radius-2)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};

const tagChip = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '2px 8px', borderRadius: 999,
  background: 'var(--surface-2)',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
};

const rowHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 1.2fr 1fr 1.2fr',
  padding: '8px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  background: 'var(--surface-2)',
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const rowBody = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 1.2fr 1fr 1.2fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
  alignItems: 'center',
};

// Timeline event ledger rows (§13) — narrower grid than neighbours table.
const eventRowHead = {
  display: 'grid',
  gridTemplateColumns: '2.2fr 1.4fr 2fr 1.4fr',
  padding: '8px 12px',
  borderBottom: '1px solid var(--stroke-1)',
  background: 'var(--surface-2)',
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  borderRadius: 'var(--radius-2) var(--radius-2) 0 0',
};

const eventRowBody = {
  display: 'grid',
  gridTemplateColumns: '2.2fr 1.4fr 2fr 1.4fr',
  padding: '8px 12px',
  borderBottom: '1px solid var(--stroke-1)',
  alignItems: 'center',
  gap: 'var(--space-2)',
};

const pill = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '5px 12px',
  borderRadius: 999,
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  textDecoration: 'none',
};
