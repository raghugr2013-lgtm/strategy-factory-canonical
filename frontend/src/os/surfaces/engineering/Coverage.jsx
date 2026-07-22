/*
 * Coverage — Sprint 3 Phase-2 live surface.
 * refs UX-Review-2026-07-22 · engines.coverage_router · COVERAGE_API_CONTRACT_PREVIEW.md
 *
 * Reads GET /api/data/coverage under Backend Feature Freeze v1.1.0-stage4.
 * No writes, no backfill triggers, no synthetic data. When the payload is
 * empty (fresh install, ingestion not yet run) we still render the full
 * interface with a PARTIAL LIVE indicator instead of a placeholder.
 *
 * Layout:
 *   HEADER — Engineering / Coverage · liveness badge · refresh · updated-at
 *   METRIC ROW (4) — symbol_count · m1_row_count_total · cache_bucket_count ·
 *                    cts_health_score
 *   PROVIDER PANEL — verification tiers (BID/BI5, HTF diff)
 *   CACHE PANEL   — hit ratio / aggregation percentiles
 *   SYMBOL MATRIX — per-symbol row (provider · first_ts · last_ts · rows · gaps)
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, RefreshCw, Waves } from 'lucide-react';
import { fetchCoverage } from '../../adapters/coverageAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';
import { useWorkspaceContext, matchesContext } from '../../hooks/useWorkspaceContext';

const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');
const pct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—');
const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};

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

export const Coverage = () => {
  const { context, isActive } = useWorkspaceContext();
  const [state, setState] = useState({ status: 'loading', liveness: 'partial', reason: null, payload: null, updatedAt: null });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading' }));
    const res = await fetchCoverage({ include: 'summary,symbols,gaps,cache,provider,health' });
    setState({ status: 'ready', liveness: res.liveness, reason: res.reason, payload: res.payload, updatedAt: new Date() });
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = state.payload?.summary || {};
  const symbolsRaw = state.payload?.symbols || [];
  const symbols = useMemo(
    () => (isActive ? symbolsRaw.filter((s) => matchesContext(s, context)) : symbolsRaw),
    [symbolsRaw, context, isActive]
  );
  const gaps    = state.payload?.gaps || [];
  const cache   = state.payload?.cache || {};
  const provider = state.payload?.provider || {};
  const health  = state.payload?.health || {};

  const reason = state.liveness === 'partial'
    ? (symbols.length === 0
        ? 'Endpoint responded 200 but no symbols have been ingested yet.'
        : `Health score ${summary.cts_health_score ?? '—'} · awaiting steady-state signal.`)
    : state.reason;

  return (
    <section data-testid="engineering-surface-coverage"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Coverage</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={state.liveness} reason={reason} testId="coverage-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="coverage-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <Waves size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            Which markets, timeframes, and history depths the Factory can trust.
          </h1>
          <p data-testid="coverage-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 780 }}>
            Read-only capability map of every (symbol × timeframe × history-window) tuple the Factory can serve.
            Sourced from <code style={{ color: 'var(--sig-info)' }}>GET /api/data/coverage</code>.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="coverage-refresh"
                  onClick={load}
                  disabled={state.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} style={{ animation: state.status === 'loading' ? 'sf-skeleton 1.2s linear infinite' : 'none' }} />
            <span>Refresh</span>
          </button>
          <div data-testid="coverage-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {state.updatedAt ? state.updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* PARTIAL LIVE reason ribbon */}
      {(state.liveness === 'partial' || state.liveness === 'gated' || state.liveness === 'error') && (
        <div data-testid="coverage-partial-reason"
             style={{
               padding: 'var(--space-3) var(--space-4)',
               border: `1px solid color-mix(in oklab, ${state.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)'} 40%, transparent)`,
               background: `color-mix(in oklab, ${state.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)'} 6%, transparent)`,
               borderRadius: 'var(--radius-2)',
               color: 'var(--content-md)',
               fontSize: 'var(--font-body-sm)',
               marginBottom: 'var(--space-5)',
               display: 'flex',
               gap: 'var(--space-3)',
               alignItems: 'center',
             }}>
          <span style={{ color: state.liveness === 'error' ? 'var(--sig-crit)' : 'var(--sig-warn)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 'var(--font-caption)' }}>
            {state.liveness === 'error' ? 'Live fetch failed' : state.liveness === 'gated' ? 'Endpoint gated' : 'Awaiting data'}
          </span>
          <span>{reason}</span>
        </div>
      )}

      {/* METRIC ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <MetricTile testId="coverage-metric-symbol-count"
                    label="Symbols tracked"
                    value={nf(summary.symbol_count)}
                    footnote={`Canonical mode · ${state.payload?.canonical_mode || 'm1'}`}
                    loading={state.status === 'loading'} />
        <MetricTile testId="coverage-metric-m1-rows"
                    label="M1 rows total"
                    value={nf(summary.m1_row_count_total)}
                    footnote={`Gaps · ${nf(summary.gap_count)}`}
                    loading={state.status === 'loading'} />
        <MetricTile testId="coverage-metric-cache-buckets"
                    label="Cache buckets"
                    value={nf(summary.cache_bucket_count)}
                    footnote={`Stale · ${nf(summary.cache_bucket_stale_count)}`}
                    loading={state.status === 'loading'} />
        <MetricTile testId="coverage-metric-health"
                    label="CTS health"
                    value={summary.cts_health_score == null ? '—' : `${summary.cts_health_score}`}
                    footnote={`State · ${health.state || 'unknown'}`}
                    tone={
                      typeof summary.cts_health_score === 'number'
                        ? summary.cts_health_score >= 80 ? 'ok' : summary.cts_health_score >= 60 ? 'warn' : 'crit'
                        : 'dormant'
                    }
                    loading={state.status === 'loading'} />
      </div>

      {/* PROVIDER + CACHE PANELS */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        {/* Provider verification */}
        <div data-testid="coverage-provider-panel" style={panel}>
          <div style={panelHeader}>Provider verification</div>
          <KV k="Sources registered"       v={nf((provider.sources || []).length)} />
          <KV k="BID/BI5 last diff"        v={iso(provider.verification_status?.last_bid_bi5_diff_at)} />
          <KV k="BID/BI5 tier"             v={provider.verification_status?.last_bid_bi5_diff_tier || '—'} />
          <KV k="HTF diff last run"        v={iso(provider.verification_status?.last_htf_diff_at)} />
          <KV k="HTF diff tier"            v={provider.verification_status?.last_htf_diff_tier || '—'} />
          <KV k="Provider sync lag (s)"    v={summary.provider_sync_lag_seconds == null ? '—' : nf(summary.provider_sync_lag_seconds)} last />
        </div>

        {/* Cache */}
        <div data-testid="coverage-cache-panel" style={panel}>
          <div style={panelHeader}>Cache</div>
          <KV k="Buckets fresh / stale"   v={`${nf(cache.bucket_fresh_count)} · ${nf(cache.bucket_stale_count)}`} />
          <KV k="Hit ratio · last hour"   v={pct(cache.hit_ratio_last_hour)} />
          <KV k="Hit ratio · last day"    v={pct(cache.hit_ratio_last_day)} />
          <KV k="Aggregation p50 (ms)"    v={cache.aggregation_ms_p50 ?? '—'} />
          <KV k="Aggregation p95 (ms)"    v={cache.aggregation_ms_p95 ?? '—'} />
          <KV k="Aggregation p99 (ms)"    v={cache.aggregation_ms_p99 ?? '—'} last />
        </div>
      </div>

      {/* SYMBOL MATRIX */}
      <div data-testid="coverage-symbols-panel" style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Symbol matrix</span>
          <span className="mono-num" data-testid="coverage-symbol-count" style={{ color: 'var(--content-lo)' }}>
            {symbols.length}{isActive && symbolsRaw.length !== symbols.length ? ` / ${symbolsRaw.length}` : ''} rows
          </span>
        </div>
        {symbols.length === 0 ? (
          <div data-testid="coverage-symbols-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>Awaiting first ingestion tick</div>
            No symbols have been persisted into <code style={{ color: 'var(--sig-info)' }}>market_data</code> yet.
            The interface is live — as soon as the ingestion engine writes its first
            <code style={{ color: 'var(--sig-info)' }}> bid_1m</code> row, this matrix will populate on next refresh.
          </div>
        ) : (
          <div role="table" aria-label="Symbol coverage matrix">
            <div role="row" style={rowHead}>
              <span>Symbol</span>
              <span>Provider</span>
              <span>First timestamp</span>
              <span>Last timestamp</span>
              <span style={{ textAlign: 'right' }}>M1 rows</span>
              <span style={{ textAlign: 'right' }}>Gaps</span>
            </div>
            {symbols.map((s, i) => (
              <div key={s.symbol || i} role="row" data-testid={`coverage-symbol-row-${i}`} style={rowBody}>
                <span style={{ color: 'var(--content-hi)' }}>{s.symbol}</span>
                <span>{s.provider || '—'}</span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)' }}>{iso(s.m1_first_ts)}</span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)' }}>{iso(s.m1_last_ts)}</span>
                <span className="mono-num" style={{ textAlign: 'right' }}>{nf(s.m1_row_count)}</span>
                <span className="mono-num" style={{ textAlign: 'right', color: (s.gap_count || 0) > 0 ? 'var(--sig-warn)' : 'var(--content-md)' }}>{nf(s.gap_count)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* GAPS */}
      {gaps.length > 0 && (
        <div data-testid="coverage-gaps-panel" style={{ ...panel, marginBottom: 'var(--space-5)' }}>
          <div style={panelHeader}>Gap enumeration</div>
          {gaps.slice(0, 20).map((g, i) => (
            <div key={i} data-testid={`coverage-gap-${i}`}
                 style={{ display: 'flex', justifyContent: 'space-between', padding: 'var(--space-2) 0', borderTop: i === 0 ? 'none' : '1px solid var(--stroke-1)', fontSize: 'var(--font-body-sm)' }}>
              <span style={{ color: 'var(--content-hi)' }}>{g.symbol}</span>
              <span className="mono-num" style={{ color: 'var(--content-md)' }}>{iso(g.from_ts)} → {iso(g.to_ts)}</span>
              <span style={{ color: 'var(--sig-warn)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)' }}>{g.severity || '—'}</span>
            </div>
          ))}
        </div>
      )}

      {/* FOOTER — related routes */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/market-data" label="Market Data" testId="coverage-related-market-data" />
          <RelatedPill to="/c/engineering/datasets"    label="Datasets"     testId="coverage-related-datasets" />
          <RelatedPill to="/c/timeline?actor=INGESTION" label="Timeline · Ingestion" testId="coverage-related-timeline" />
        </div>
      </div>
    </section>
  );
};

const MetricTile = ({ testId, label, value, footnote, tone = 'info', loading }) => {
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
        {loading ? '·' : value}
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

const rowHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.5fr 2fr 2fr 1fr 1fr',
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
  gridTemplateColumns: '2fr 1.5fr 2fr 2fr 1fr 1fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
};

const panelHeader = {
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
