/*
 * StrategyPipeline — Sprint 3 Phase-2 live Engineering surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * Composes a 5-stage pipeline view from three live endpoints:
 *   GET /api/strategies              — draft/tested/live/retired inventory
 *   GET /api/knowledge/champions      — canonical champion families by pair
 *   GET /api/knowledge/statistics     — corpus size + pair distribution
 *
 * Stages are derived from the strategy `status` field on the live rows:
 *   draft       → Stage 1 · Drafts
 *   backtested  → Stage 2 · Backtested (also matches `tested`, `validated`)
 *   champion    → Stage 3 · Champions (fed by KB champions.categories)
 *   deployed    → Stage 4 · Deployed (also matches `live`, `active`)
 *   retired     → Stage 5 · Retired  (also matches `archived`)
 *
 * No synthetic data. Empty datasets render the live interface with a
 * PARTIAL LIVE badge and operator-legible reason.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, GitBranch, RefreshCw, Trophy } from 'lucide-react';
import {
  listStrategies,
  fetchKnowledgeChampions,
  fetchKnowledgeStatistics,
} from '../../adapters/strategyLabAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';
import { useWorkspaceContext, matchesContext } from '../../hooks/useWorkspaceContext';

const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};
const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');

// Stage taxonomy — order matters for the horizontal lineage bar.
const STAGES = [
  { id: 'drafts',      label: 'Drafts',      accent: 'var(--sig-info)',     match: ['draft'] },
  { id: 'backtested',  label: 'Backtested',  accent: 'var(--sig-advisory)', match: ['backtested', 'tested', 'validated'] },
  { id: 'champions',   label: 'Champions',   accent: 'var(--accent-gold)',  match: ['champion'] },
  { id: 'deployed',    label: 'Deployed',    accent: 'var(--sig-ok)',       match: ['deployed', 'live', 'active'] },
  { id: 'retired',     label: 'Retired',     accent: 'var(--sig-dormant)',  match: ['retired', 'archived'] },
];

const stageOf = (status) => {
  const v = (status || '').toString().toLowerCase();
  for (const s of STAGES) if (s.match.includes(v)) return s.id;
  return 'drafts';
};

export const StrategyPipeline = () => {
  const { context, isActive } = useWorkspaceContext();
  const [strategyState, setStrategyState] = useState({ status: 'loading', liveness: 'partial', reason: null, list: [] });
  const [championState, setChampionState] = useState({ status: 'loading', liveness: 'partial', reason: null, categories: {} });
  const [statsState, setStatsState] = useState({ status: 'loading', liveness: 'partial', reason: null, stats: {} });
  const [updatedAt, setUpdatedAt] = useState(null);
  const [activeStage, setActiveStage] = useState('drafts');

  const load = useCallback(async () => {
    setStrategyState((s) => ({ ...s, status: 'loading' }));
    setChampionState((s) => ({ ...s, status: 'loading' }));
    setStatsState((s) => ({ ...s, status: 'loading' }));
    const [strat, champ, stats] = await Promise.all([
      listStrategies(),
      fetchKnowledgeChampions(),
      fetchKnowledgeStatistics(),
    ]);
    setStrategyState({ status: 'ready', liveness: strat.liveness, reason: strat.reason, list: strat.payload || [] });
    setChampionState({ status: 'ready', liveness: champ.liveness, reason: champ.reason, categories: champ.payload?.categories || {} });
    setStatsState({ status: 'ready', liveness: stats.liveness, reason: stats.reason, stats: stats.payload || {} });
    setUpdatedAt(new Date());
  }, []);

  useEffect(() => { load(); }, [load]);

  // Bucket the live strategy inventory by stage. Context (§9) narrows
  // the inventory by pair / timeframe / strategy id when active.
  const buckets = useMemo(() => {
    const filtered = isActive ? strategyState.list.filter((s) => matchesContext(s, context)) : strategyState.list;
    const b = Object.fromEntries(STAGES.map((s) => [s.id, []]));
    for (const s of filtered) b[stageOf(s.status)].push(s);
    return b;
  }, [strategyState.list, context, isActive]);

  // Champion families flattened for the champions stage — these come from
  // the historical KB (`strategy_kb_champions`), not the live strategies
  // collection, so we merge them into the champions bucket for display.
  const championRows = useMemo(() => {
    const rows = [];
    for (const [category, families] of Object.entries(championState.categories || {})) {
      if (Array.isArray(families)) {
        for (const f of families) {
          rows.push({
            strategy_id: f.strategy_id || f.canonical_hash || '—',
            name: f.name || f.strategy_id || category,
            status: 'champion',
            symbol: f.pair || f.symbol || category,
            timeframe: f.timeframe || '—',
            _source: 'kb-champions',
            _category: category,
          });
        }
      }
    }
    return rows;
  }, [championState.categories]);

  const aggregate = useMemo(() => {
    if (strategyState.liveness === 'error' && championState.liveness === 'error') {
      return { liveness: 'error', reason: strategyState.reason || championState.reason };
    }
    const totalStrategies = strategyState.list.length + championRows.length;
    if (totalStrategies > 0) return { liveness: 'live', reason: null };
    return {
      liveness: 'partial',
      reason: 'Live strategies and champions collections both empty · pipeline shell rendered live.',
    };
  }, [strategyState, championState, championRows.length]);

  const stageCount = (id) => (id === 'champions'
    ? buckets.champions.length + championRows.length
    : buckets[id].length);

  const activeRows = activeStage === 'champions'
    ? [...buckets.champions, ...championRows]
    : buckets[activeStage] || [];

  return (
    <section data-testid="engineering-surface-strategy-pipeline"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Strategy Pipeline</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="strategy-pipeline-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="strategy-pipeline-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <GitBranch size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            Where every strategy sits · drafts → champions → deployments.
          </h1>
          <p data-testid="strategy-pipeline-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 900 }}>
            Composed under Backend Feature Freeze v1.1.0-stage4 from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/strategies</code>,
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/knowledge/champions</code>, and
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/knowledge/statistics</code>.
            Historical champions from the isolated KB corpus are surfaced alongside the live drafts collection — but never eligible for deploy without earning a fresh Passport.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="strategy-pipeline-refresh"
                  onClick={load}
                  disabled={strategyState.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} />
            <span>Refresh</span>
          </button>
          <div data-testid="strategy-pipeline-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {updatedAt ? updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* METRIC ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <MetricTile testId="strategy-pipeline-metric-strategies"
                    label="Live strategies"
                    value={nf(strategyState.list.length)}
                    footnote={`GET /api/strategies · ${strategyState.liveness}`} />
        <MetricTile testId="strategy-pipeline-metric-champions"
                    label="Champion families"
                    value={nf(statsState.stats?.canonical_families)}
                    tone={(statsState.stats?.canonical_families || 0) > 0 ? 'ok' : 'dormant'}
                    footnote={`${nf(championRows.length)} champion rows · ${nf(Object.keys(championState.categories || {}).length)} KB categories`} />
        <MetricTile testId="strategy-pipeline-metric-corpus"
                    label="Historical KB size"
                    value={nf(statsState.stats?.total_strategies)}
                    footnote={`Canonical families · ${nf(statsState.stats?.canonical_families)}`} />
        <MetricTile testId="strategy-pipeline-metric-pairs"
                    label="Pairs in corpus"
                    value={nf(Object.keys(statsState.stats?.pair_distribution || {}).length)}
                    footnote={`Multi-member · ${nf(statsState.stats?.multi_member_families)}`} />
      </div>

      {/* STAGE BAR */}
      <div data-testid="strategy-pipeline-stage-bar"
           style={{ display: 'grid', gridTemplateColumns: `repeat(${STAGES.length}, minmax(0, 1fr))`, gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
        {STAGES.map((s, idx) => {
          const active = activeStage === s.id;
          const count = stageCount(s.id);
          return (
            <button type="button"
                    key={s.id}
                    data-testid={`strategy-pipeline-stage-${s.id}`}
                    onClick={() => setActiveStage(s.id)}
                    style={{
                      textAlign: 'left',
                      background: active ? 'var(--surface-2)' : 'var(--surface-1)',
                      border: `1px solid ${active ? s.accent : 'var(--stroke-1)'}`,
                      borderLeft: `3px solid ${s.accent}`,
                      borderRadius: 'var(--radius-2)',
                      padding: 'var(--space-3) var(--space-4)',
                      color: 'var(--content-hi)',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      transition: 'background var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
                    }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                <span style={{ ...eyebrow, color: 'var(--content-lo)' }}>
                  Stage {idx + 1}
                </span>
                {s.id === 'champions' && <Trophy size={12} strokeWidth={1.75} color="var(--accent-gold)" />}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
                <span style={{ fontSize: 'var(--font-body)', color: 'var(--content-hi)', fontWeight: 500 }}>{s.label}</span>
                <span className="mono-num" style={{ fontSize: 'var(--font-h3)', color: s.accent, fontWeight: 500, lineHeight: 1 }}>
                  {nf(count)}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* PARTIAL LIVE ribbon */}
      {aggregate.liveness === 'partial' && (
        <div data-testid="strategy-pipeline-partial-reason"
             style={{
               padding: 'var(--space-3) var(--space-4)',
               border: '1px solid color-mix(in oklab, var(--sig-warn) 40%, transparent)',
               background: 'color-mix(in oklab, var(--sig-warn) 6%, transparent)',
               borderRadius: 'var(--radius-2)',
               color: 'var(--content-md)',
               fontSize: 'var(--font-body-sm)',
               marginBottom: 'var(--space-4)',
               display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
             }}>
          <span style={{ color: 'var(--sig-warn)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 'var(--font-caption)' }}>
            Awaiting inventory
          </span>
          <span>{aggregate.reason}</span>
          <Link data-testid="strategy-pipeline-empty-cta"
                to="/c/engineering/strategy-lab"
                style={{ marginLeft: 'auto', color: 'var(--sig-info)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Open Strategy Lab <ArrowRight size={11} />
          </Link>
        </div>
      )}

      {/* ACTIVE STAGE INVENTORY */}
      <div data-testid={`strategy-pipeline-inventory-${activeStage}`}
           style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{STAGES.find((s) => s.id === activeStage)?.label} · inventory</span>
          <span className="mono-num" data-testid="strategy-pipeline-active-count" style={{ color: 'var(--content-lo)' }}>
            {activeRows.length} rows
          </span>
        </div>
        {activeRows.length === 0 ? (
          <div data-testid="strategy-pipeline-active-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              {STAGES.find((s) => s.id === activeStage)?.label} · empty
            </div>
            No strategies at this stage yet. The interface is live — as soon as a strategy&apos;s status transitions into
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>{STAGES.find((s) => s.id === activeStage)?.match.join(' | ')}</code>,
            it will appear here on next refresh.
          </div>
        ) : (
          <div role="table" aria-label={`Strategies at ${activeStage}`}>
            <div role="row" style={rowHead}>
              <span>Name</span>
              <span>Strategy id</span>
              <span>Symbol · TF</span>
              <span>Source</span>
              <span>Updated</span>
              <span></span>
            </div>
            {activeRows.map((s, i) => {
              const highlighted = context.strategy && s.strategy_id === context.strategy;
              return (
              <div key={s.strategy_id || i} role="row" data-testid={`strategy-pipeline-row-${activeStage}-${i}`}
                   data-context-focus={highlighted ? 'true' : undefined}
                   style={{
                     ...rowBody,
                     background: highlighted ? 'color-mix(in oklab, var(--sig-info) 6%, transparent)' : undefined,
                     borderLeft: highlighted ? '2px solid var(--sig-info)' : rowBody.borderLeft,
                   }}>
                <span style={{ color: 'var(--content-hi)' }}>{s.name}</span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
                  {s.strategy_id}
                </span>
                <span>{[s.symbol, s.timeframe].filter((v) => v && v !== '—').join(' · ') || '—'}</span>
                <span style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  {s._source || 'live'}
                </span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
                  {iso(s.updated_at)}
                </span>
                <span style={{ textAlign: 'right' }}>
                  {s._source === 'kb-champions' ? (
                    <span style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                      learning only
                    </span>
                  ) : (
                    <Link to={`/c/strategies/${encodeURIComponent(s.strategy_id)}`}
                          data-testid={`strategy-pipeline-row-link-${i}`}
                          style={{ color: 'var(--sig-info)', textDecoration: 'none', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Passport <ArrowRight size={11} />
                    </Link>
                  )}
                </span>
              </div>
            );
            })}
          </div>
        )}
      </div>

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/strategy-lab" label="Compose draft"      testId="strategy-pipeline-related-lab" />
          <RelatedPill to="/c/engineering/optimization" label="Optimization"       testId="strategy-pipeline-related-optimization" />
          <RelatedPill to="/c/engineering/validation"   label="Validation"         testId="strategy-pipeline-related-validation" />
          <RelatedPill to="/c/strategies"               label="Strategy Passports" testId="strategy-pipeline-related-passports" />
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

const panelHeader = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
};

const rowHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.5fr 1.2fr 1fr 1.5fr 1fr',
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
  gridTemplateColumns: '2fr 1.5fr 1.2fr 1fr 1.5fr 1fr',
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
