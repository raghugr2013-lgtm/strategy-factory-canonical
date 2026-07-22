/*
 * Datasets — Sprint 3 Phase-2+ live Engineering surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * Composed under the freeze from two live endpoints:
 *   GET /api/data/coverage    (symbols · cache · gaps · summary)
 *   GET /api/dashboard/summary (top-level counters)
 *
 * Datasets renders the shape and health of the raw market-data assets
 * the Factory can serve — per-symbol row counts, dataset span, gap
 * enumeration, cache freshness. No writes, no ingestion triggers.
 * Empty datasets render the real interface with a PARTIAL LIVE badge.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Database, RefreshCw, AlertTriangle } from 'lucide-react';
import { fetchCoverage } from '../../adapters/coverageAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';

const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};
const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');
const pct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—');

const spanDays = (a, b) => {
  if (!a || !b) return null;
  try {
    const ms = new Date(b).getTime() - new Date(a).getTime();
    if (Number.isNaN(ms) || ms < 0) return null;
    return Math.round(ms / 86_400_000);
  } catch { return null; }
};

const cacheTone = (v) => {
  if (!v) return 'dormant';
  const s = String(v).toLowerCase();
  if (['fresh', 'ok', 'hot'].includes(s)) return 'ok';
  if (['stale', 'warm', 'cold'].includes(s)) return 'warn';
  if (['missing', 'expired', 'evicted'].includes(s)) return 'crit';
  return 'info';
};

export const Datasets = () => {
  const [state, setState] = useState({ status: 'loading', liveness: 'partial-live', reason: null, payload: null, updatedAt: null });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading' }));
    const res = await fetchCoverage({ include: 'summary,symbols,cache,gaps,health' });
    setState({ status: 'ready', liveness: res.liveness, reason: res.reason, payload: res.payload, updatedAt: new Date() });
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = state.payload?.summary || {};
  const symbols = state.payload?.symbols || [];
  const cache   = state.payload?.cache || {};
  const gaps    = state.payload?.gaps || [];
  const health  = state.payload?.health || {};

  // Aggregate signals for the surface header.
  const aggregate = useMemo(() => {
    if (state.liveness === 'error') return { liveness: 'error', reason: state.reason };
    if (state.liveness === 'gated') return { liveness: 'gated', reason: state.reason };
    if (symbols.length > 0 && (summary.m1_row_count_total || 0) > 0) return { liveness: 'live', reason: null };
    const parts = [];
    if (symbols.length === 0) parts.push('0 symbols persisted');
    if ((summary.m1_row_count_total || 0) === 0) parts.push('0 m1 rows');
    return { liveness: 'partial-live', reason: parts.join(' · ') };
  }, [state.liveness, state.reason, symbols.length, summary.m1_row_count_total]);

  return (
    <section data-testid="engineering-surface-datasets"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Datasets</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="datasets-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="datasets-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <Database size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            The shape and health of the raw data the Factory can serve.
          </h1>
          <p data-testid="datasets-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 900 }}>
            Composed under Backend Feature Freeze v1.1.0-stage4 from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/data/coverage</code>.
            Read-only view of every persisted (symbol × timeframe × history-window) tuple, cache freshness percentiles, and gap enumeration.
            Dedicated <code style={{ color: 'var(--sig-info)' }}>/api/datasets/*</code> endpoints are scheduled for post-freeze.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="datasets-refresh"
                  onClick={load}
                  disabled={state.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} style={{ animation: state.status === 'loading' ? 'sf-skeleton 1.2s linear infinite' : 'none' }} />
            <span>Refresh</span>
          </button>
          <div data-testid="datasets-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {state.updatedAt ? state.updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* PARTIAL LIVE / ERROR ribbon */}
      {aggregate.liveness !== 'live' && (
        <div data-testid="datasets-partial-reason"
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
            {aggregate.liveness === 'error' ? 'Live fetch failed' : 'Awaiting first ingestion tick'}
          </span>
          <span>{aggregate.reason || 'The coverage endpoint responded 200 but no persisted rows exist yet.'}</span>
        </div>
      )}

      {/* METRIC ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <MetricTile testId="datasets-metric-symbols"
                    label="Datasets tracked"
                    value={nf(summary.symbol_count || symbols.length)}
                    footnote={`Canonical mode · ${state.payload?.canonical_mode || 'm1'}`} />
        <MetricTile testId="datasets-metric-rows"
                    label="Total M1 rows"
                    value={nf(summary.m1_row_count_total)}
                    footnote={`Canonical · ${nf(summary.canonical_symbol_count)} · native TF · ${nf(summary.native_tf_symbol_count)}`} />
        <MetricTile testId="datasets-metric-cache"
                    label="Cache hit ratio (1h)"
                    value={pct(cache.hit_ratio_last_hour)}
                    footnote={`Buckets · ${nf(cache.bucket_count)} · stale ${nf(cache.bucket_stale_count)}`}
                    tone={
                      typeof cache.hit_ratio_last_hour === 'number'
                        ? cache.hit_ratio_last_hour >= 0.9 ? 'ok' : cache.hit_ratio_last_hour >= 0.7 ? 'warn' : 'crit'
                        : 'dormant'
                    } />
        <MetricTile testId="datasets-metric-gaps"
                    label="Open gaps"
                    value={nf(summary.gap_count)}
                    footnote={summary.gap_severity_max ? `Max severity · ${summary.gap_severity_max}` : 'No severity reported'}
                    tone={(summary.gap_count || 0) === 0 ? 'ok' : (summary.gap_count || 0) < 10 ? 'warn' : 'crit'} />
      </div>

      {/* DATASET CARDS (per symbol) */}
      <div data-testid="datasets-cards-panel"
           style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Dataset inventory</span>
          <span className="mono-num" data-testid="datasets-card-count" style={{ color: 'var(--content-lo)' }}>
            {symbols.length} datasets
          </span>
        </div>
        {symbols.length === 0 ? (
          <div data-testid="datasets-cards-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              Empty inventory
            </div>
            No datasets have been persisted. The interface is live — as soon as an ingestion worker writes to
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>market_data</code>,
            each new (symbol × timeframe) tuple will appear as an individual card here.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 'var(--space-3)', padding: 'var(--space-4)' }}>
            {symbols.map((s, i) => {
              const span = spanDays(s.m1_first_ts, s.m1_last_ts);
              const tone = cacheTone(s.cache_status);
              return (
                <div key={s.symbol || i}
                     data-testid={`datasets-card-${i}`}
                     style={{
                       background: 'var(--surface-2)',
                       border: '1px solid var(--stroke-1)',
                       borderLeft: `3px solid ${(s.gap_count || 0) > 0 ? 'var(--sig-warn)' : 'var(--sig-ok)'}`,
                       borderRadius: 'var(--radius-3)',
                       padding: 'var(--space-4)',
                     }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--space-2)' }}>
                    <span style={{ color: 'var(--content-hi)', fontSize: 'var(--font-body)', fontWeight: 500 }}>
                      {s.symbol}
                    </span>
                    <span style={{ ...eyebrow, color: 'var(--content-lo)' }}>
                      {s.provider || 'unknown'}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', rowGap: 6, columnGap: 12, fontSize: 'var(--font-body-sm)' }}>
                    <span style={{ color: 'var(--content-lo)' }}>Rows</span>
                    <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-hi)' }}>{nf(s.m1_row_count)}</span>
                    <span style={{ color: 'var(--content-lo)' }}>Span (days)</span>
                    <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-hi)' }}>{span == null ? '—' : nf(span)}</span>
                    <span style={{ color: 'var(--content-lo)' }}>First</span>
                    <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-md)', fontSize: 'var(--font-caption)' }}>{iso(s.m1_first_ts)}</span>
                    <span style={{ color: 'var(--content-lo)' }}>Last</span>
                    <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-md)', fontSize: 'var(--font-caption)' }}>{iso(s.m1_last_ts)}</span>
                    <span style={{ color: 'var(--content-lo)' }}>Gaps</span>
                    <span className="mono-num" style={{ textAlign: 'right', color: (s.gap_count || 0) > 0 ? 'var(--sig-warn)' : 'var(--content-hi)' }}>
                      {nf(s.gap_count)}
                    </span>
                    <span style={{ color: 'var(--content-lo)' }}>Cache</span>
                    <span style={{ textAlign: 'right' }}>
                      <ToneChip tone={tone} label={s.cache_status || 'unknown'} testId={`datasets-card-cache-${i}`} />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* CACHE PERFORMANCE */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div data-testid="datasets-cache-panel" style={panel}>
          <div style={panelHeaderInline}>Cache performance</div>
          <KV k="Buckets total"                v={nf(cache.bucket_count)} />
          <KV k="Fresh / stale / missing"      v={`${nf(cache.bucket_fresh_count)} · ${nf(cache.bucket_stale_count)} · ${nf(cache.bucket_missing_count)}`} />
          <KV k="Hit ratio · last hour"        v={pct(cache.hit_ratio_last_hour)} />
          <KV k="Hit ratio · last day"         v={pct(cache.hit_ratio_last_day)} />
          <KV k="Aggregation p50 / p95 / p99"  v={`${cache.aggregation_ms_p50 ?? '—'} · ${cache.aggregation_ms_p95 ?? '—'} · ${cache.aggregation_ms_p99 ?? '—'}`} last />
        </div>
        <div data-testid="datasets-health-panel" style={panel}>
          <div style={panelHeaderInline}>Subsystem health</div>
          <KV k="Subsystem"          v={health.subsystem || '—'} />
          <KV k="Health score"       v={health.health_score == null ? '—' : nf(health.health_score)} />
          <KV k="State"              v={health.state || 'unknown'} />
          <KV k="CTS score (summary)" v={summary.cts_health_score == null ? '—' : nf(summary.cts_health_score)} />
          <KV k="Provider sync lag"   v={summary.provider_sync_lag_seconds == null ? '—' : `${nf(summary.provider_sync_lag_seconds)}s`} last />
        </div>
      </div>

      {/* GAPS */}
      {gaps.length > 0 && (
        <div data-testid="datasets-gaps-panel" style={{ ...panel, marginBottom: 'var(--space-5)' }}>
          <div style={panelHeaderInline}>
            <AlertTriangle size={13} strokeWidth={1.75} color="var(--sig-warn)" style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Gap enumeration ({gaps.length})
          </div>
          {gaps.slice(0, 20).map((g, i) => (
            <div key={i} data-testid={`datasets-gap-${i}`}
                 style={{ display: 'grid', gridTemplateColumns: '1fr 3fr 1fr', gap: 'var(--space-3)', padding: 'var(--space-2) 0', borderTop: i === 0 ? 'none' : '1px solid var(--stroke-1)', fontSize: 'var(--font-body-sm)' }}>
              <span style={{ color: 'var(--content-hi)' }}>{g.symbol}</span>
              <span className="mono-num" style={{ color: 'var(--content-md)', fontSize: 'var(--font-caption)' }}>
                {iso(g.from_ts)} → {iso(g.to_ts)}
              </span>
              <span style={{ textAlign: 'right', color: 'var(--sig-warn)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)' }}>
                {g.severity || '—'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* FOOTER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/coverage"     label="Coverage detail"     testId="datasets-related-coverage" />
          <RelatedPill to="/c/engineering/market-data"  label="Market Data feed"    testId="datasets-related-market-data" />
          <RelatedPill to="/c/timeline?actor=INGESTION" label="Ingestion timeline"  testId="datasets-related-timeline" />
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

const ToneChip = ({ tone = 'info', label, testId }) => {
  const accent = {
    ok:      'var(--sig-ok)',
    info:    'var(--sig-info)',
    warn:    'var(--sig-warn)',
    crit:    'var(--sig-crit)',
    dormant: 'var(--sig-dormant)',
  }[tone] || 'var(--sig-info)';
  return (
    <span data-testid={testId}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '2px 8px', borderRadius: 999,
            background: `color-mix(in oklab, ${accent} 12%, transparent)`,
            border: `1px solid color-mix(in oklab, ${accent} 35%, transparent)`,
            color: accent,
            fontSize: 'var(--font-caption)',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}>
      <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor' }} />
      {label}
    </span>
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
  padding: 'var(--space-4)',
};

const panelHeader = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
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
