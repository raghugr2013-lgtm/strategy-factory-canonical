/*
 * MarketData — Sprint 3 Phase-2 PARTIAL LIVE surface.
 * refs UX-Review-2026-07-22 · Backend Feature Freeze v1.1.0-stage4
 *
 * There is no dedicated /api/market-data/* router under the freeze. This
 * surface is composed entirely from the single live endpoint that
 * describes market-data venues today:
 *
 *   GET /api/data/coverage
 *     · payload.provider.sources             — market-data venue roster
 *     · payload.provider.verification_status — BID/BI5 + HTF diff tiers
 *     · payload.symbols                      — per-symbol last-tick roster
 *     · payload.summary                      — global counters
 *
 * Nothing is fabricated. When the payload is empty (fresh install, no
 * ingestion yet) we still render the full live interface with PARTIAL
 * LIVE badges and operator-legible reasons.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Radio, RefreshCw } from 'lucide-react';
import { fetchCoverage } from '../../adapters/coverageAdapter';
import { LivenessBadge, FreezeCaption } from './LivenessBadge';

const iso = (v) => {
  if (!v) return '—';
  try { return new Date(v).toISOString().replace('T', ' ').replace(/\.\d+Z$/, 'Z'); }
  catch { return String(v); }
};
const nf = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');
const ageSince = (v) => {
  if (!v) return null;
  try {
    const ms = Date.now() - new Date(v).getTime();
    if (Number.isNaN(ms)) return null;
    if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
    if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
    if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h ago`;
    return `${Math.round(ms / 86_400_000)}d ago`;
  } catch { return null; }
};

export const MarketData = () => {
  const [state, setState] = useState({ status: 'loading', liveness: 'partial-live', reason: null, payload: null, updatedAt: null });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading' }));
    const res = await fetchCoverage({ include: 'summary,symbols,provider,health' });
    setState({ status: 'ready', liveness: res.liveness, reason: res.reason, payload: res.payload, updatedAt: new Date() });
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = state.payload?.summary || {};
  const symbols = state.payload?.symbols || [];
  const providerBlock = state.payload?.provider || {};
  const providerSources = providerBlock.sources || [];
  const providerVerification = providerBlock.verification_status || {};
  const health = state.payload?.health || {};

  const aggregate = useMemo(() => {
    if (state.liveness === 'error') return { liveness: 'error', reason: state.reason };
    if (state.liveness === 'gated') return { liveness: 'gated', reason: state.reason };
    if (symbols.length > 0 && providerSources.length > 0) return { liveness: 'live', reason: null };
    const parts = [];
    if (providerSources.length === 0) parts.push('venue roster · empty');
    if (symbols.length === 0) parts.push('symbol feed · 0 rows');
    return { liveness: 'partial-live', reason: parts.join(' · ') };
  }, [state.liveness, state.reason, symbols.length, providerSources.length]);

  return (
    <section data-testid="engineering-surface-market-data"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>

      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrow}>Engineering</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrow, color: 'var(--content-hi)' }}>Market Data</span>
        <span style={{ marginLeft: 'auto' }}>
          <LivenessBadge liveness={aggregate.liveness} reason={aggregate.reason} testId="market-data-liveness" />
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <div style={{ flex: 1 }}>
          <h1 data-testid="market-data-headline"
              style={{ margin: 0, fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
            <Radio size={20} strokeWidth={1.5} color="var(--sig-info)" style={{ verticalAlign: '-3px', marginRight: 8 }} />
            Which venues the Factory hears from right now.
          </h1>
          <p data-testid="market-data-subhead"
             style={{ margin: 'var(--space-2) 0 0 0', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6, maxWidth: 780 }}>
            Composed under Backend Feature Freeze v1.1.0-stage4 from
            <code style={{ color: 'var(--sig-info)', margin: '0 4px' }}>GET /api/data/coverage</code>.
            Venue roster, verification tiers, and last-tick feed are all read from the same locked contract; a dedicated
            streaming <code style={{ color: 'var(--sig-info)' }}>/api/market-data/*</code> API is scheduled for post-freeze.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button"
                  data-testid="market-data-refresh"
                  onClick={load}
                  disabled={state.status === 'loading'}
                  style={refreshBtn}>
            <RefreshCw size={12} strokeWidth={1.75} />
            <span>Refresh</span>
          </button>
          <div data-testid="market-data-updated-at" style={{ ...eyebrow, color: 'var(--content-lo)' }}>
            Updated · {state.updatedAt ? state.updatedAt.toUTCString().slice(17, 25) + 'Z' : '—'}
          </div>
        </div>
      </div>

      {/* Aggregate reason ribbon */}
      {aggregate.liveness !== 'live' && (
        <div data-testid="market-data-partial-reason"
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
            {aggregate.liveness === 'error' ? 'Live fetch failed' : 'Awaiting steady state'}
          </span>
          <span>
            {aggregate.reason || 'Coverage endpoint responded 200 but the venue roster and symbol feed are still populating.'}
          </span>
        </div>
      )}

      {/* METRIC ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <MetricTile testId="market-data-metric-symbols"
                    label="Symbols streaming"
                    value={nf(summary.symbol_count || symbols.length)}
                    footnote={`Canonical mode · ${state.payload?.canonical_mode || 'm1'}`} />
        <MetricTile testId="market-data-metric-venues"
                    label="Venues registered"
                    value={nf(providerSources.length)}
                    footnote={providerSources.length === 0 ? 'No venue writes yet' : 'Sources · from coverage payload'} />
        <MetricTile testId="market-data-metric-sync-lag"
                    label="Provider sync lag (s)"
                    value={summary.provider_sync_lag_seconds == null ? '—' : nf(summary.provider_sync_lag_seconds)}
                    footnote={providerVerification.last_bid_bi5_diff_at ? `BID/BI5 · ${ageSince(providerVerification.last_bid_bi5_diff_at) || iso(providerVerification.last_bid_bi5_diff_at)}` : 'BID/BI5 · never'}
                    tone={
                      typeof summary.provider_sync_lag_seconds === 'number'
                        ? summary.provider_sync_lag_seconds < 60 ? 'ok' : summary.provider_sync_lag_seconds < 600 ? 'warn' : 'crit'
                        : 'dormant'
                    } />
        <MetricTile testId="market-data-metric-htf"
                    label="HTF diff tier"
                    value={providerVerification.last_htf_diff_tier || '—'}
                    footnote={providerVerification.last_htf_diff_at ? ageSince(providerVerification.last_htf_diff_at) || iso(providerVerification.last_htf_diff_at) : 'never run'} />
      </div>

      {/* VENUE ROSTER */}
      <div data-testid="market-data-venues-panel" style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Venue roster</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <LivenessBadge liveness={providerSources.length > 0 ? 'live' : 'partial-live'}
                           reason={providerSources.length === 0 ? 'coverage.provider.sources is empty' : null}
                           testId="market-data-venues-liveness" />
            <span className="mono-num" data-testid="market-data-venue-count" style={{ color: 'var(--content-lo)' }}>
              {providerSources.length} venues
            </span>
          </div>
        </div>
        {providerSources.length === 0 ? (
          <div data-testid="market-data-venues-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>
              Venue registry · empty
            </div>
            No venues have written to the coverage provider block yet. As soon as an ingestion worker registers a venue
            (via <code style={{ color: 'var(--sig-info)' }}>market_data</code> writes), it will appear here.
            Meanwhile, verification tiers below are pulled from the same live payload.
          </div>
        ) : (
          <div role="table" aria-label="Venue roster">
            <div role="row" style={venueHead}>
              <span>Venue</span>
              <span>Kind</span>
              <span>Last verified</span>
              <span style={{ textAlign: 'right' }}>Symbols</span>
            </div>
            {providerSources.map((v, i) => (
              <div key={v.name || v.id || i} role="row" data-testid={`market-data-venue-row-${i}`} style={venueBody}>
                <span style={{ color: 'var(--content-hi)' }}>{v.name || v.id || '—'}</span>
                <span style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 'var(--font-caption)' }}>
                  {v.kind || v.category || '—'}
                </span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)' }}>
                  {v.last_verified_at ? (ageSince(v.last_verified_at) || iso(v.last_verified_at)) : '—'}
                </span>
                <span className="mono-num" style={{ textAlign: 'right' }}>
                  {typeof v.symbol_count === 'number' ? nf(v.symbol_count) : '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* SYMBOL FEED */}
      <div data-testid="market-data-symbols-panel" style={{ ...panel, padding: 0, overflow: 'hidden', marginBottom: 'var(--space-5)' }}>
        <div style={{ ...panelHeader, padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--stroke-1)', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Symbol feed</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <LivenessBadge liveness={symbols.length > 0 ? 'live' : 'partial-live'}
                           reason={symbols.length === 0 ? 'coverage.symbols is empty' : null}
                           testId="market-data-feed-liveness" />
            <span className="mono-num" data-testid="market-data-symbol-count" style={{ color: 'var(--content-lo)' }}>
              {symbols.length} symbols
            </span>
          </div>
        </div>
        {symbols.length === 0 ? (
          <div data-testid="market-data-symbols-empty"
               style={{ padding: 'var(--space-5) var(--space-4)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 'var(--font-caption)', marginBottom: 'var(--space-2)' }}>Awaiting first ingestion tick</div>
            No symbols in <code style={{ color: 'var(--sig-info)' }}>market_data</code>. As soon as an ingestion worker writes its first
            <code style={{ color: 'var(--sig-info)' }}> bid_1m</code> row, this feed will populate on next refresh.
            CTS health remains reported at <span className="mono-num" style={{ color: 'var(--content-hi)' }}>{health.health_score ?? '—'}</span>.
          </div>
        ) : (
          <div role="table" aria-label="Symbol feed">
            <div role="row" style={symbolHead}>
              <span>Symbol</span>
              <span>Provider</span>
              <span>Last tick</span>
              <span style={{ textAlign: 'right' }}>Rows</span>
              <span style={{ textAlign: 'right' }}>Age</span>
            </div>
            {symbols.slice(0, 40).map((s, i) => (
              <div key={s.symbol || i} role="row" data-testid={`market-data-symbol-row-${i}`} style={symbolBody}>
                <span style={{ color: 'var(--content-hi)' }}>{s.symbol}</span>
                <span>{s.provider || '—'}</span>
                <span className="mono-num" style={{ fontSize: 'var(--font-caption)' }}>{iso(s.m1_last_ts)}</span>
                <span className="mono-num" style={{ textAlign: 'right' }}>{nf(s.m1_row_count)}</span>
                <span className="mono-num" style={{ textAlign: 'right', color: 'var(--content-md)' }}>
                  {s.m1_last_ts ? (ageSince(s.m1_last_ts) || '—') : '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* FOOTER — related routes */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <FreezeCaption />
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <RelatedPill to="/c/engineering/coverage"     label="Coverage detail"     testId="market-data-related-coverage" />
          <RelatedPill to="/c/engineering/datasets"     label="Datasets"            testId="market-data-related-datasets" />
          <RelatedPill to="/c/timeline?actor=INGESTION" label="Ingestion timeline"  testId="market-data-related-timeline" />
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

const venueHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 2fr 1fr',
  padding: '8px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  background: 'var(--surface-2)',
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const venueBody = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.2fr 2fr 1fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
};

const symbolHead = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.5fr 2fr 1fr 1fr',
  padding: '8px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  background: 'var(--surface-2)',
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const symbolBody = {
  display: 'grid',
  gridTemplateColumns: '2fr 1.5fr 2fr 1fr 1fr',
  padding: '10px 16px',
  borderBottom: '1px solid var(--stroke-1)',
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-md)',
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
