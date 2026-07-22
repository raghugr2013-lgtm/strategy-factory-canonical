/*
 * Validation — Sprint 3 Phase-2+ PARTIAL LIVE Engineering surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * Composed from four live endpoints under the freeze:
 *   GET /api/knowledge/health       — corpus status + readiness ceiling
 *   GET /api/knowledge/statistics   — total / canonical / multi-member /
 *                                     PF>1 counts + guardrails
 *   GET /api/knowledge/champions    — validated champion families
 *   GET /api/strategies             — live inventory buckets by status
 *
 * Validation is the "did the Factory earn trust yet?" ledger — every
 * indicator here is read-only under the freeze. No writes, no runs.
 * Empty corpus renders the live interface with a PARTIAL LIVE badge
 * and the guardrail chips visible (learning-only, not deploy-eligible).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ClipboardCheck, RefreshCw, ShieldCheck, ShieldAlert } from 'lucide-react';
import { apiFetch, isLiveMode } from '../../adapters/apiClient';
import {
  listStrategies,
  fetchKnowledgeStatistics,
  fetchKnowledgeChampions,
} from '../../adapters/strategyLabAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';

const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');

const HEALTH_TONE = {
  green:  { tone: 'ok',      label: 'GREEN'  },
  ready:  { tone: 'ok',      label: 'READY'  },
  ok:     { tone: 'ok',      label: 'OK'     },
  warm:   { tone: 'warn',    label: 'WARM'   },
  warn:   { tone: 'warn',    label: 'WARN'   },
  amber:  { tone: 'warn',    label: 'AMBER'  },
  empty:  { tone: 'dormant', label: 'EMPTY'  },
  cold:   { tone: 'dormant', label: 'COLD'   },
  red:    { tone: 'crit',    label: 'RED'    },
  error:  { tone: 'crit',    label: 'ERROR'  },
};

const fetchKnowledgeHealthDirect = async () => {
  // /api/knowledge/health is not proxied by strategyLabAdapter — dedicated
  // pull here so we can carry its distinct empty-state semantics.
  if (!isLiveMode()) return { liveness: 'gated', reason: 'REACT_APP_BACKEND_URL not configured', payload: null };
  try {
    const payload = await apiFetch('/api/knowledge/health');
    return { liveness: 'live', reason: null, payload };
  } catch (err) {
    if (err.status === 401) return { liveness: 'error', reason: 'unauthorized · sign in required', payload: null };
    return { liveness: 'error', reason: err.message || 'network error', payload: null };
  }
};

const statusOf = (s) => (s?.status || '').toString().toLowerCase();

export const Validation = () => {
  const [health, setHealth]       = useState({ status: 'loading', liveness: 'partial', reason: null, payload: null });
  const [stats, setStats]         = useState({ status: 'loading', liveness: 'partial', reason: null, stats: {} });
  const [champions, setChampions] = useState({ status: 'loading', liveness: 'partial', reason: null, categories: {} });
  const [inv, setInv]             = useState({ status: 'loading', liveness: 'partial', reason: null, list: [] });
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(async () => {
    setHealth((s) => ({ ...s, status: 'loading' }));
    setStats((s) => ({ ...s, status: 'loading' }));
    setChampions((s) => ({ ...s, status: 'loading' }));
    setInv((s) => ({ ...s, status: 'loading' }));
    const [h, st, ch, i] = await Promise.all([
      fetchKnowledgeHealthDirect(),
      fetchKnowledgeStatistics(),
      fetchKnowledgeChampions(),
      listStrategies(),
    ]);
    setHealth({ status: 'ready', liveness: h.liveness, reason: h.reason, payload: h.payload });
    setStats({ status: 'ready', liveness: st.liveness, reason: st.reason, stats: st.payload || {} });
    setChampions({ status: 'ready', liveness: ch.liveness, reason: ch.reason, categories: ch.payload?.categories || {} });
    setInv({ status: 'ready', liveness: i.liveness, reason: i.reason, list: i.payload || [] });
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = stats.stats || {};
  const inventory = inv.list || [];

  const validated  = useMemo(() => inventory.filter((r) => ['backtested', 'tested', 'validated'].includes(statusOf(r))), [inventory]);
  const champions_ = useMemo(() => inventory.filter((r) => statusOf(r) === 'champion'), [inventory]);
  const deployed   = useMemo(() => inventory.filter((r) => ['deployed', 'live', 'active'].includes(statusOf(r))), [inventory]);
  const drafts     = useMemo(() => inventory.filter((r) => statusOf(r) === 'draft'), [inventory]);

  const championFamilies = useMemo(() => {
    const rows = [];
    for (const [category, families] of Object.entries(champions.categories || {})) {
      if (Array.isArray(families)) {
        for (const f of families) rows.push({ category, ...f });
      }
    }
    return rows;
  }, [champions.categories]);

  const guardrails = s.guardrails || {};
  const backendAvail = s.backend_available || {};
  const readinessCeiling = health.payload?.readiness_ceiling || 'pending_validation';
  const corpusSize = health.payload?.corpus_size ?? s.total_strategies ?? 0;
  const backend = health.payload?.backend || (backendAvail.rule_based ? 'rule_based_v1' : 'unavailable');
  const healthStatus = HEALTH_TONE[(health.payload?.status || 'empty').toLowerCase()] || HEALTH_TONE.empty;

  const winnerRate = useMemo(() => {
    const total = s.total_strategies || 0;
    const wins  = s.positive_return_pf_gt_1 || 0;
    if (!total) return null;
    return wins / total;
  }, [s.total_strategies, s.positive_return_pf_gt_1]);

  const aggregate = useMemo(() => {
    if (health.liveness === 'error' && inv.liveness === 'error') {
      return { liveness: 'error', reason: health.reason || inv.reason };
    }
    if ((corpusSize > 0 && (s.canonical_families || 0) > 0) || champions_.length > 0 || validated.length > 0) {
      return { liveness: 'live', reason: null };
    }
    return {
      liveness: 'partial',
      reason: `Corpus is ${health.payload?.status || 'empty'} · readiness ceiling ${readinessCeiling}. Interface is live.`,
    };
  }, [health, inv, corpusSize, s.canonical_families, champions_.length, validated.length, readinessCeiling]);

  return (
    <section data-testid="engineering-surface-validation"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Validation</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="validation-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="validation-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <ClipboardCheck size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            Did the Factory earn trust yet? The evidence ledger.
          </h1>
          <p data-testid="validation-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 900 }}>
            Composed under Backend Feature Freeze v1.1.0-stage4 from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/knowledge/health</code>,
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>/statistics</code>,
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>/champions</code>, and
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/strategies</code>.
            Passport-level backtest artefacts and per-run validation reports are surfaced here as they become available — the interface itself is always live.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="validation-refresh"
                  onClick={load}
                  disabled={health.status === 'loading' || inv.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} />
            <span>Refresh</span>
          </button>
          <div data-testid="validation-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {updatedAt ? updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* GUARDRAILS ribbon (always visible when learning_only is on) */}
      {guardrails.learning_only && (
        <div data-testid="validation-guardrail-ribbon"
             style={{
               padding: 'var(--space-3) var(--space-4)',
               border: '1px solid color-mix(in oklab, var(--sig-warn) 40%, transparent)',
               background: 'color-mix(in oklab, var(--sig-warn) 6%, transparent)',
               borderRadius: 'var(--radius-2)',
               color: 'var(--content-md)',
               fontSize: 'var(--font-body-sm)',
               marginBottom: 'var(--space-5)',
               display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
             }}>
          <ShieldAlert size={14} strokeWidth={1.75} color="var(--sig-warn)" />
          <span style={{ color: 'var(--sig-warn)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 'var(--font-caption)' }}>
            Learning-only guardrail
          </span>
          <span>
            Historical KB is <code style={{ color: 'var(--sig-info)' }}>learning_only=true</code> ·
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>eligible_for_deploy={String(!!guardrails.eligible_for_deploy)}</code>.
            No historical strategy can be promoted to production. Every deploy candidate must earn a fresh Passport under current framework.
          </span>
        </div>
      )}

      {/* CORPUS HEALTH row */}
      <div data-testid="validation-health-panel"
           style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeaderRow, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Corpus health · <code style={{ color: 'var(--sig-info)' }}>/api/knowledge/health</code></span>
          <LivenessBadge liveness={health.liveness} reason={health.reason} testId="validation-health-liveness" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', padding: 'var(--space-4)' }}>
          <StatusTile testId="validation-metric-status"
                      label="Corpus status"
                      value={healthStatus.label}
                      tone={healthStatus.tone}
                      footnote={`Backend · ${backend}`} />
          <MetricTile testId="validation-metric-corpus"
                      label="Corpus size"
                      value={nf(corpusSize)}
                      tone={corpusSize > 0 ? 'ok' : 'dormant'}
                      footnote={`Canonical families · ${nf(s.canonical_families)}`} />
          <MetricTile testId="validation-metric-champions"
                      label="Champion families"
                      value={nf(championFamilies.length)}
                      tone={championFamilies.length > 0 ? 'info' : 'dormant'}
                      footnote={`Categories · ${nf(Object.keys(champions.categories || {}).length)}`} />
          <StatusTile testId="validation-metric-ceiling"
                      label="Readiness ceiling"
                      value={String(readinessCeiling).replace(/_/g, ' ').toUpperCase()}
                      tone={String(readinessCeiling).toLowerCase() === 'ready' ? 'ok' : 'warn'}
                      footnote={`Rule-based · ${backendAvail.rule_based ? 'available' : 'off'}`} />
        </div>
      </div>

      {/* EVIDENCE ROW — two-panel split */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        {/* Historical evidence */}
        <div data-testid="validation-history-panel" style={panelBox}>
          <div style={panelHeaderInline}>
            <ShieldCheck size={13} strokeWidth={1.75} color="var(--sig-info)" style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Historical evidence · KB corpus
          </div>
          <KV k="Total strategies"        v={nf(s.total_strategies)} />
          <KV k="Canonical families"      v={nf(s.canonical_families)} />
          <KV k="Multi-member families"   v={nf(s.multi_member_families)} />
          <KV k="Positive-return PF > 1"  v={nf(s.positive_return_pf_gt_1)} />
          <KV k="Winner rate"             v={winnerRate == null ? '—' : `${(winnerRate * 100).toFixed(1)}%`} />
          <KV k="Pair coverage"           v={nf(Object.keys(s.pair_distribution || {}).length)} last />
        </div>

        {/* Live evidence — inventory by validation state */}
        <div data-testid="validation-live-panel" style={panelBox}>
          <div style={panelHeaderInline}>
            <ClipboardCheck size={13} strokeWidth={1.75} color="var(--sig-info)" style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Live evidence · inventory by state
          </div>
          <KV k="Drafts (unvalidated)"    v={nf(drafts.length)} />
          <KV k="Backtested / validated"  v={nf(validated.length)} />
          <KV k="Champions"               v={nf(champions_.length)} />
          <KV k="Deployed"                v={nf(deployed.length)} />
          <KV k="Total live strategies"   v={nf(inventory.length)} />
          <KV k="Rule-based / embedding"  v={`${backendAvail.rule_based ? '✓' : '·'} / ${backendAvail.embedding ? '✓' : '·'}`} last />
        </div>
      </div>

      {/* CHAMPION FAMILIES */}
      <div data-testid="validation-champions-panel"
           style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeaderRow, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Validated champion families · KB</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <LivenessBadge liveness={champions.liveness}
                           reason={champions.reason || (championFamilies.length === 0 ? 'Corpus empty · no champions yet.' : null)}
                           testId="validation-champions-liveness" />
            <span className="mono-num" data-testid="validation-champions-count" style={{ color: 'var(--content-lo)' }}>
              {championFamilies.length} families
            </span>
          </div>
        </div>
        {championFamilies.length === 0 ? (
          <div data-testid="validation-champions-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              No champion families
            </div>
            The historical corpus is empty (or has not yet promoted any families). This surface is live — as soon as
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>/api/knowledge/champions</code>
            returns a non-empty categories map, each canonical hash will appear here with its category and metadata.
          </div>
        ) : (
          <div role="table" aria-label="Validated champion families">
            <div role="row" style={rowHead}>
              <span>Category</span>
              <span>Family / strategy id</span>
              <span>Pair · TF</span>
              <span style={{ textAlign: 'right' }}>Members</span>
              <span style={{ textAlign: 'right' }}>Verdict</span>
            </div>
            {championFamilies.map((f, i) => (
              <div key={f.canonical_hash || f.strategy_id || i}
                   role="row"
                   data-testid={`validation-champion-row-${i}`}
                   style={rowBody}>
                <span style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  {f.category || '—'}
                </span>
                <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-caption)' }}>
                  {f.strategy_id || f.canonical_hash || '—'}
                </span>
                <span>{[f.pair || f.symbol, f.timeframe].filter(Boolean).join(' · ') || '—'}</span>
                <span className="mono-num" style={{ textAlign: 'right' }}>{nf(f.member_count)}</span>
                <span style={{ textAlign: 'right', color: 'var(--sig-warn)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  learning only
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/strategy-pipeline" label="Strategy Pipeline"  testId="validation-related-pipeline" />
          <RelatedPill to="/c/engineering/optimization"      label="Optimization"       testId="validation-related-optimization" />
          <RelatedPill to="/c/strategies"                    label="Strategy Passports" testId="validation-related-passports" />
        </div>
      </div>
    </section>
  );
};

const MetricTile = ({ testId, label, value, footnote, tone = 'info' }) => {
  const accent = {
    ok:      'var(--sig-ok)',
    info:    'var(--sig-info)',
    warn:    'var(--sig-warn)',
    crit:    'var(--sig-crit)',
    dormant: 'var(--sig-dormant)',
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
      <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        {footnote}
      </span>
    </div>
  );
};

const StatusTile = ({ testId, label, value, tone, footnote }) => {
  const accent = {
    ok:      'var(--sig-ok)',
    info:    'var(--sig-info)',
    warn:    'var(--sig-warn)',
    crit:    'var(--sig-crit)',
    dormant: 'var(--sig-dormant)',
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
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 12px',
        borderRadius: 999,
        background: `color-mix(in oklab, ${accent} 12%, transparent)`,
        border: `1px solid color-mix(in oklab, ${accent} 40%, transparent)`,
        color: accent,
        fontSize: 'var(--font-caption)',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        fontWeight: 500,
        alignSelf: 'flex-start',
      }}>
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
        {value}
      </span>
      <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        {footnote}
      </span>
    </div>
  );
};

const KV = ({ k, v, last }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)', padding: 'var(--space-2) 0', borderBottom: last ? 'none' : '1px solid var(--stroke-1)' }}>
    <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-body-sm)' }}>{k}</span>
    <span className="mono-num" style={{ color: 'var(--content-hi)', fontSize: 'var(--font-body-sm)' }}>{v}</span>
  </div>
);

const RelatedPill = ({ to, label, testId }) => (
  <Link to={to} data-testid={testId} style={pill}>
    <span>{label}</span>
    <ArrowRight size={11} strokeWidth={1.75} />
  </Link>
);

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

const panelHeaderRow = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  padding: 'var(--space-3) var(--space-4)',
  borderBottom: '1px solid var(--stroke-1)',
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

const rowHead = {
  display: 'grid',
  gridTemplateColumns: '1.2fr 2fr 1.2fr 1fr 1.2fr',
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
  gridTemplateColumns: '1.2fr 2fr 1.2fr 1fr 1.2fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
  alignItems: 'center',
};

const refreshBtn = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px',
  background: 'var(--surface-1)',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  borderRadius: 'var(--radius-2)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  cursor: 'pointer',
  transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
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
  transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
};
