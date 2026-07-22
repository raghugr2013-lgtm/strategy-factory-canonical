/*
 * Optimization — Sprint 3 Phase-2+ PARTIAL LIVE Engineering surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * A dedicated /api/optimize/* router is scheduled for post-freeze. Under
 * the current freeze we render a read-only "optimization queue" view
 * composed from two pre-existing endpoints:
 *
 *   GET /api/strategies            — the current inventory (buckets that
 *                                    would feed a sweep launcher)
 *   GET /api/knowledge/statistics  — corpus counters + PF>1 winner rate,
 *                                    a signal for how much sweep budget
 *                                    has historically produced winners
 *
 * No synthetic data — when both are empty we render the real interface
 * with a PARTIAL LIVE badge and operator-legible reason.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, RefreshCw, SlidersHorizontal, Rocket } from 'lucide-react';
import {
  listStrategies,
  fetchKnowledgeStatistics,
} from '../../adapters/strategyLabAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';

const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};
const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');

// A strategy is "sweep-eligible" if it's a draft or backtested candidate.
const isEligible = (s) => {
  const v = (s?.status || '').toString().toLowerCase();
  return ['draft', 'backtested', 'tested', 'validated'].includes(v);
};

const stageOf = (s) => {
  const v = (s?.status || '').toString().toLowerCase();
  if (v === 'draft') return 'draft';
  if (['backtested', 'tested', 'validated'].includes(v)) return 'backtested';
  if (v === 'champion') return 'champion';
  if (['deployed', 'live', 'active'].includes(v)) return 'deployed';
  return 'other';
};

// Group by (symbol × timeframe) — the natural sweep bucket.
const groupBySweepBucket = (list) => {
  const map = new Map();
  for (const s of list) {
    const key = `${s.symbol || '—'}·${s.timeframe || '—'}`;
    if (!map.has(key)) map.set(key, { symbol: s.symbol, timeframe: s.timeframe, members: [], eligible: 0 });
    const b = map.get(key);
    b.members.push(s);
    if (isEligible(s)) b.eligible += 1;
  }
  return [...map.values()].sort((a, b) => b.eligible - a.eligible || b.members.length - a.members.length);
};

export const Optimization = () => {
  const [strategyState, setStrategyState] = useState({ status: 'loading', liveness: 'partial', reason: null, list: [] });
  const [statsState, setStatsState] = useState({ status: 'loading', liveness: 'partial', reason: null, stats: {} });
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(async () => {
    setStrategyState((s) => ({ ...s, status: 'loading' }));
    setStatsState((s) => ({ ...s, status: 'loading' }));
    const [strat, stats] = await Promise.all([
      listStrategies(),
      fetchKnowledgeStatistics(),
    ]);
    setStrategyState({ status: 'ready', liveness: strat.liveness, reason: strat.reason, list: strat.payload || [] });
    setStatsState({ status: 'ready', liveness: stats.liveness, reason: stats.reason, stats: stats.payload || {} });
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => { load(); }, [load]);

  const strategies = strategyState.list;
  const stats = statsState.stats;

  const stageCounts = useMemo(() => {
    const c = { draft: 0, backtested: 0, champion: 0, deployed: 0, other: 0 };
    for (const s of strategies) c[stageOf(s)] += 1;
    return c;
  }, [strategies]);

  const eligible = useMemo(() => strategies.filter(isEligible), [strategies]);
  const buckets  = useMemo(() => groupBySweepBucket(strategies), [strategies]);

  const winnerRate = useMemo(() => {
    const total = stats.total_strategies || 0;
    const winners = stats.positive_return_pf_gt_1 || 0;
    if (!total) return null;
    return winners / total;
  }, [stats.total_strategies, stats.positive_return_pf_gt_1]);

  const aggregate = useMemo(() => {
    // Under freeze, /api/optimize/* does not exist. Even a fully populated
    // strategies list can never make this surface "LIVE" for the sweep
    // launcher — the launcher itself is post-freeze. We still promote to
    // LIVE when we can meaningfully brief an operator (inventory + KB).
    if (strategyState.liveness === 'error' && statsState.liveness === 'error') {
      return { liveness: 'error', reason: strategyState.reason || statsState.reason };
    }
    if (strategies.length > 0 || (stats.total_strategies || 0) > 0) {
      return {
        liveness: 'deferred',
        reason: 'Read-only queue view. /api/optimize/* launcher scheduled post-freeze.',
      };
    }
    return {
      liveness: 'partial',
      reason: 'Strategies and KB corpus both empty · queue rendered live.',
    };
  }, [strategyState, statsState, strategies.length, stats.total_strategies]);

  return (
    <section data-testid="engineering-surface-optimization"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Optimization</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="optimization-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="optimization-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <SlidersHorizontal size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            What&apos;s queued for parameter sweeps and what history says about them.
          </h1>
          <p data-testid="optimization-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 900 }}>
            Read-only view under Backend Feature Freeze v1.1.0-stage4 · composed from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/strategies</code>
            (sweep-eligible inventory) and
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/knowledge/statistics</code>
            (historical PF&gt;1 winner rate). The
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>/api/optimize/*</code>
            launcher and cycle-history endpoints are scheduled for post-freeze — this surface will graduate to LIVE once they land.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="optimization-refresh"
                  onClick={load}
                  disabled={strategyState.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} />
            <span>Refresh</span>
          </button>
          <div data-testid="optimization-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {updatedAt ? updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* PARTIAL LIVE ribbon */}
      {aggregate.liveness !== 'live' && (
        <div data-testid="optimization-partial-reason"
             style={{
               padding: 'var(--space-3) var(--space-4)',
               border: `1px solid color-mix(in oklab, ${aggregate.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)'} 40%, transparent)`,
               background: `color-mix(in oklab, ${aggregate.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)'} 6%, transparent)`,
               borderRadius: 'var(--radius-2)',
               color: 'var(--content-md)',
               fontSize: 'var(--font-body-sm)',
               marginBottom: 'var(--space-5)',
               display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
             }}>
          <span style={{ color: aggregate.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 'var(--font-caption)' }}>
            {aggregate.liveness === 'error' ? 'Live fetch failed' : 'Launcher deferred'}
          </span>
          <span>{aggregate.reason}</span>
        </div>
      )}

      {/* METRIC ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <MetricTile testId="optimization-metric-eligible"
                    label="Sweep-eligible"
                    value={nf(eligible.length)}
                    footnote={`Drafts · ${nf(stageCounts.draft)} · Backtested · ${nf(stageCounts.backtested)}`}
                    tone={eligible.length > 0 ? 'info' : 'dormant'} />
        <MetricTile testId="optimization-metric-buckets"
                    label="Sweep buckets"
                    value={nf(buckets.length)}
                    footnote="Grouped by symbol × timeframe" />
        <MetricTile testId="optimization-metric-corpus"
                    label="Historical corpus"
                    value={nf(stats.total_strategies)}
                    footnote={`Canonical families · ${nf(stats.canonical_families)}`} />
        <MetricTile testId="optimization-metric-winrate"
                    label="Historical PF > 1"
                    value={winnerRate == null ? '—' : `${(winnerRate * 100).toFixed(1)}%`}
                    footnote={`${nf(stats.positive_return_pf_gt_1)} / ${nf(stats.total_strategies)}`}
                    tone={winnerRate == null ? 'dormant' : winnerRate >= 0.3 ? 'ok' : winnerRate >= 0.1 ? 'warn' : 'crit'} />
      </div>

      {/* SWEEP BUCKETS */}
      <div data-testid="optimization-buckets-panel"
           style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeaderRow, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Sweep buckets · symbol × timeframe</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <span data-testid="optimization-launcher-badge" style={launcherPill}>
              <Rocket size={11} strokeWidth={1.75} />
              Launcher · post-freeze
            </span>
            <span className="mono-num" data-testid="optimization-bucket-count" style={{ color: 'var(--content-lo)' }}>
              {buckets.length} buckets
            </span>
          </div>
        </div>
        {buckets.length === 0 ? (
          <div data-testid="optimization-buckets-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              No sweep buckets
            </div>
            The live strategies collection has no entries yet — nothing to sweep. Draft a candidate in
            <Link to="/c/engineering/strategy-lab" data-testid="optimization-buckets-empty-cta" style={{ color: 'var(--sig-info)', textDecoration: 'none', marginLeft: 4 }}>
              Strategy Lab ↗
            </Link>
            {' '}and it will appear here as its own sweep bucket.
          </div>
        ) : (
          <div role="table" aria-label="Sweep buckets">
            <div role="row" style={rowHead}>
              <span>Symbol · TF</span>
              <span style={{ textAlign: 'right' }}>Members</span>
              <span style={{ textAlign: 'right' }}>Eligible</span>
              <span>Stage breakdown</span>
              <span></span>
            </div>
            {buckets.map((b, i) => {
              const stagesInBucket = b.members.reduce((acc, m) => {
                const st = stageOf(m);
                acc[st] = (acc[st] || 0) + 1;
                return acc;
              }, {});
              return (
                <div key={`${b.symbol}-${b.timeframe}-${i}`} role="row" data-testid={`optimization-bucket-row-${i}`} style={rowBody}>
                  <span style={{ color: 'var(--content-hi)' }}>
                    {b.symbol || '—'} · {b.timeframe || '—'}
                  </span>
                  <span className="mono-num" style={{ textAlign: 'right' }}>{nf(b.members.length)}</span>
                  <span className="mono-num" style={{ textAlign: 'right', color: b.eligible > 0 ? 'var(--sig-info)' : 'var(--content-md)' }}>
                    {nf(b.eligible)}
                  </span>
                  <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {Object.entries(stagesInBucket).map(([st, n]) => (
                      <StageChip key={st} stage={st} count={n} />
                    ))}
                  </span>
                  <span style={{ textAlign: 'right' }}>
                    <span data-testid={`optimization-bucket-cta-${i}`} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      color: 'var(--content-lo)',
                      fontSize: 'var(--font-caption)',
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                    }} title="Sweep launcher scheduled for post-freeze.">
                      Sweep · deferred
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* KB SIGNAL PANEL */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div data-testid="optimization-kb-panel" style={panelBox}>
          <div style={panelHeaderInline}>Historical KB signal</div>
          <KV k="Total strategies"       v={nf(stats.total_strategies)} />
          <KV k="Canonical families"     v={nf(stats.canonical_families)} />
          <KV k="Multi-member families"  v={nf(stats.multi_member_families)} />
          <KV k="Positive-return PF > 1" v={nf(stats.positive_return_pf_gt_1)} />
          <KV k="Backend · rule-based"   v={stats.backend_available?.rule_based ? 'available' : 'off'} />
          <KV k="Backend · embedding"    v={stats.backend_available?.embedding ? 'available' : 'off'} last />
        </div>
        <div data-testid="optimization-inventory-panel" style={panelBox}>
          <div style={panelHeaderInline}>Live inventory (by stage)</div>
          <KV k="Draft"        v={nf(stageCounts.draft)} />
          <KV k="Backtested"   v={nf(stageCounts.backtested)} />
          <KV k="Champion"     v={nf(stageCounts.champion)} />
          <KV k="Deployed"     v={nf(stageCounts.deployed)} />
          <KV k="Other"        v={nf(stageCounts.other)} />
          <KV k="Total live"   v={nf(strategies.length)} last />
        </div>
      </div>

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/strategy-lab"      label="Compose draft"      testId="optimization-related-lab" />
          <RelatedPill to="/c/engineering/strategy-pipeline" label="Strategy Pipeline"  testId="optimization-related-pipeline" />
          <RelatedPill to="/c/engineering/validation"        label="Validation"         testId="optimization-related-validation" />
        </div>
      </div>
    </section>
  );
};

const STAGE_TONE = {
  draft:      'var(--sig-info)',
  backtested: 'var(--sig-advisory)',
  champion:   'var(--accent-gold)',
  deployed:   'var(--sig-ok)',
  other:      'var(--content-lo)',
};

const StageChip = ({ stage, count }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '2px 8px',
    borderRadius: 999,
    background: `color-mix(in oklab, ${STAGE_TONE[stage] || 'var(--content-lo)'} 10%, transparent)`,
    border: `1px solid color-mix(in oklab, ${STAGE_TONE[stage] || 'var(--content-lo)'} 32%, transparent)`,
    color: STAGE_TONE[stage] || 'var(--content-lo)',
    fontSize: 'var(--font-caption)',
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  }}>
    {stage} · {count}
  </span>
);

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
  gridTemplateColumns: '1.4fr 0.9fr 0.9fr 2fr 1fr',
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
  gridTemplateColumns: '1.4fr 0.9fr 0.9fr 2fr 1fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
  alignItems: 'center',
};

const launcherPill = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '3px 10px',
  borderRadius: 999,
  background: 'color-mix(in oklab, var(--sig-warn) 8%, transparent)',
  border: '1px solid color-mix(in oklab, var(--sig-warn) 32%, transparent)',
  color: 'var(--sig-warn)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
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
