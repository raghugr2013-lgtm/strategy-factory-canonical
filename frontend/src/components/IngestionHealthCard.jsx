import React, { useEffect, useState } from 'react';
import {
  Database,
  CircleNotch,
  Warning,
  Heartbeat,
  ChartLineDown,
  Clock,
  CaretRight,
  CaretDown,
} from '@phosphor-icons/react';
import { AsfKpiTile, AsfEmptyState, VerdictBadge } from './ui-asf';
import { API_URL } from '../services/api';

const VERDICT_VARIANT = {
  HEALTHY:    'success',
  LAGGING:    'warn',
  DEGRADED:   'warn',
  STALE:      'warn',
  BLOCKED:    'danger',
  EMPTY:      'neutral',
  UNCERTAIN:  'neutral',
};

// Pass 14 — Ingestion Health Card (read-only, advisory-only).
//
// Operator constraint:
//   • Minimal · institutional · read-only-first · advisory-only.
//   • Single read endpoint: GET /api/latent/ingestion-aggregate.
//   • Surfaces:
//     - Verdict + rationale (HEALTHY / LAGGING / DEGRADED / STALE
//       / BLOCKED / EMPTY / UNCERTAIN)
//     - Per-band counts (healthy / stale / degraded / blocked)
//     - Heartbeat (band + age + last event kind)
//     - Multi-window degradation indicator (rows_last_24h vs prior)
//     - Drill-down: blocked + stale pair lists (collapsed by default)
//     - Source health visibility (per-row sample)
//   • EMPTY collapse to keep the dashboard clean before ingestion.
//   • No controls. No buttons that mutate. Operator authority remains
//     ingestion runner / supervisor / .env — this card is purely a
//     diagnostic window into the existing state.


const VERDICT_TONE = {
  HEALTHY:    { dot: 'bg-emerald-400', text: 'text-emerald-300', label: 'HEALTHY' },
  LAGGING:    { dot: 'bg-amber-400',   text: 'text-amber-300',   label: 'LAGGING' },
  DEGRADED:   { dot: 'bg-orange-400',  text: 'text-orange-300',  label: 'DEGRADED' },
  STALE:      { dot: 'bg-amber-500',   text: 'text-amber-400',   label: 'STALE' },
  BLOCKED:    { dot: 'bg-rose-500',    text: 'text-rose-300',    label: 'BLOCKED' },
  EMPTY:      { dot: 'bg-zinc-500',    text: 'text-zinc-400',    label: 'EMPTY' },
  UNCERTAIN:  { dot: 'bg-zinc-600',    text: 'text-zinc-400',    label: 'UNCERTAIN' },
};

const HB_TONE = {
  fresh:   'text-emerald-300',
  aged:    'text-amber-300',
  stale:   'text-rose-300',
  missing: 'text-zinc-500',
};

const DEG_TONE = {
  stable:                 'text-emerald-300',
  degrading:              'text-amber-300',
  collapsing:             'text-rose-300',
  insufficient_baseline:  'text-zinc-500',
  'n/a':                  'text-zinc-500',
};

async function fetchJson(path) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail || '';
    } catch { /* ignore */ }
    throw new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
  }
  return res.json();
}

function Pill({ label, value, color = 'text-zinc-100', testId, hint }) {
  return (
    <div data-testid={testId} className="flex flex-col" title={hint}>
      <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">
        {label}
      </span>
      <span className={`font-mono ${color} text-base font-semibold`}>
        {value ?? '—'}
      </span>
    </div>
  );
}

function ageString(iso) {
  if (!iso) return '—';
  try {
    const t = new Date(iso).getTime();
    const now = Date.now();
    const minutes = Math.max(0, Math.round((now - t) / 60000));
    if (minutes < 60) return `${minutes}m ago`;
    if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h ago`;
    return `${Math.round(minutes / 1440)}d ago`;
  } catch {
    return '—';
  }
}

export default function IngestionHealthCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);

  const [showBlocked, setShowBlocked] = useState(false);
  const [showStale, setShowStale] = useState(false);
  const [showAnyway, setShowAnyway] = useState(false);

  const refresh = async () => {
    setError(null);
    try {
      const out = await fetchJson('/api/latent/ingestion-aggregate');
      setData(out);
      setRefreshedAt(new Date().toISOString());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // Light polling (60s) — ingestion runs are not frequent enough
    // to justify a tighter cadence, but operators do scan often.
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, []);

  // EMPTY auto-collapse (matches the parity-cert card discipline).
  const isEmpty = !loading && !error && data?.verdict === 'EMPTY';
  if (isEmpty && !showAnyway) {
    return (
      <div
        data-testid="ingestion-health-card-empty"
        className="card-premium p-2 border border-zinc-800/60 bg-zinc-950/30 mb-4 flex items-center justify-between text-[10px] font-mono text-zinc-500"
      >
        <span className="flex items-center gap-2">
          <Database size={11} weight="bold" />
          ingestion-health · empty · no coverage rows or ingestion events
        </span>
        <button
          data-testid="ingestion-health-show-anyway"
          onClick={() => setShowAnyway(true)}
          className="text-cyan-400 hover:text-cyan-300 underline decoration-dotted underline-offset-2"
        >
          show anyway
        </button>
      </div>
    );
  }

  const verdict = data?.verdict || 'UNCERTAIN';
  const tone = VERDICT_TONE[verdict] || VERDICT_TONE.UNCERTAIN;
  const perBand = data?.per_band || {};
  const heartbeat = data?.heartbeat || {};
  const degradation = data?.degradation || {};
  const thresholds = data?.thresholds || {};
  const blockedPairs = data?.blocked_pairs || [];
  const stalePairs = data?.stale_pairs || [];
  const sample = data?.coverage_row_sample || [];

  return (
    <div
      data-testid="ingestion-health-card"
      className="asf-section asf-u2-panel card-premium p-4 border border-zinc-800/80 bg-zinc-950/40 mb-4"
    >
      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="asf-section__hd flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="asf-legacy-title flex items-center gap-2">
          <Database size={14} weight="fill" className="text-cyan-400" />
          <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-300">
            Ingestion Health · Pass 14
          </h3>
          <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
            read-only · advisory-only
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          {loading && <CircleNotch size={11} className="animate-spin" />}
          {refreshedAt && !loading && (
            <span
              data-testid="ingestion-health-refreshed"
              className="flex items-center gap-1"
            >
              <Clock size={10} />
              {new Date(refreshedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            data-testid="ingestion-health-refresh"
            onClick={refresh}
            className="px-2 py-0.5 border border-zinc-700/60 rounded hover:border-zinc-500 hover:text-zinc-300 transition-colors"
            title="Refresh now"
          >
            refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3">
          <AsfEmptyState
            slug="ingestion-health-error"
            testId="ingestion-health-error"
            title="Ingestion health failed to load"
            body={error}
            action={{ label: 'Retry', onClick: refresh, testId: 'ingestion-health-error-retry' }}
          />
        </div>
      )}

      {/* ── Verdict ──────────────────────────────────────────────── */}
      <div className="mb-3 flex items-center gap-2 flex-wrap" data-testid="ingestion-health-verdict-row">
        <VerdictBadge verdict={VERDICT_VARIANT[verdict] || 'neutral'} testId="ingestion-health-verdict">
          {tone.label}
        </VerdictBadge>
        <span
          data-testid="ingestion-health-rationale"
          className="text-[10px] font-mono text-zinc-400"
        >
          {data?.rationale || '—'}
        </span>
      </div>

      {/* ── KPI strip ─────────────────────────────────────────── */}
      <div className="asf-kpi-grid mb-3">
        <AsfKpiTile
          testId="ingestion-health-pill-healthy"
          label="Healthy"
          value={perBand.healthy ?? 0}
          verdict={perBand.healthy > 0 ? 'success' : 'neutral'}
          title={`Rows with lag ≤ ${thresholds.healthy_max_lag_bars} bars, completeness ≥ ${thresholds.healthy_min_completeness}, no gaps`}
        />
        <AsfKpiTile
          testId="ingestion-health-pill-stale"
          label="Stale"
          value={perBand.stale ?? 0}
          verdict={perBand.stale > 0 ? 'warn' : 'neutral'}
          title={`Rows with lag > ${thresholds.healthy_max_lag_bars} bars (data exists but lags)`}
        />
        <AsfKpiTile
          testId="ingestion-health-pill-degraded"
          label="Degraded"
          value={perBand.degraded ?? 0}
          verdict={perBand.degraded > 0 ? 'warn' : 'neutral'}
          title="Rows with gaps or completeness below SLA"
        />
        <AsfKpiTile
          testId="ingestion-health-pill-blocked"
          label="Blocked"
          value={perBand.blocked ?? 0}
          verdict={perBand.blocked > 0 ? 'danger' : 'neutral'}
          title="Rows producing zero data — runner likely down or broker connectivity broken"
        />
        <AsfKpiTile
          testId="ingestion-health-pill-rows"
          label="Coverage Rows"
          value={data?.row_count ?? 0}
          verdict="info"
          title="Total (symbol, timeframe, source) tuples observed in data_coverage"
        />
      </div>

      {/* ── Heartbeat + degradation row ─────────────────────── */}
      <div
        data-testid="ingestion-health-heartbeat-row"
        className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3 pt-2 border-t border-zinc-800/60"
      >
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <Heartbeat size={12} weight="bold" className={HB_TONE[heartbeat.band] || HB_TONE.missing} />
          <span className="text-zinc-500 uppercase tracking-wider">heartbeat:</span>
          <span
            data-testid="ingestion-health-heartbeat-band"
            className={HB_TONE[heartbeat.band] || HB_TONE.missing}
          >
            {heartbeat.band || 'missing'}
          </span>
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-400">{ageString(heartbeat.last_event_at)}</span>
          {heartbeat.last_event_kind && (
            <>
              <span className="text-zinc-600">·</span>
              <span className="text-zinc-500">{heartbeat.last_event_kind}</span>
            </>
          )}
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-400">
            <span className="text-zinc-200">{heartbeat.events_24h ?? 0}</span> events / 24h
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] font-mono">
          <ChartLineDown size={12} weight="bold" className={DEG_TONE[degradation.indicator] || DEG_TONE['n/a']} />
          <span className="text-zinc-500 uppercase tracking-wider">degradation:</span>
          <span
            data-testid="ingestion-health-degradation-indicator"
            className={DEG_TONE[degradation.indicator] || DEG_TONE['n/a']}
          >
            {degradation.indicator || 'n/a'}
          </span>
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-400">
            <span className="text-zinc-200">{degradation.rows_last_24h ?? 0}</span> / 24h
          </span>
          <span className="text-zinc-600">·</span>
          <span className="text-zinc-400">
            prior <span className="text-zinc-200">{degradation.rows_prior_24h ?? 0}</span>
          </span>
          {degradation.delta_pct != null && (
            <>
              <span className="text-zinc-600">·</span>
              <span className={degradation.delta_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}>
                {degradation.delta_pct > 0 ? '+' : ''}{degradation.delta_pct}%
              </span>
            </>
          )}
        </div>
      </div>

      {/* ── Blocked pairs drill-down (only when present) ───────── */}
      {blockedPairs.length > 0 && (
        <div className="mb-2 pt-2 border-t border-rose-900/40">
          <button
            data-testid="ingestion-health-toggle-blocked"
            onClick={() => setShowBlocked(!showBlocked)}
            className="flex items-center gap-1.5 text-[10px] font-mono text-rose-300 hover:text-rose-200"
          >
            {showBlocked
              ? <CaretDown size={10} weight="bold" />
              : <CaretRight size={10} weight="bold" />}
            <span className="uppercase tracking-wider">
              blocked pairs ({blockedPairs.length})
            </span>
          </button>
          {showBlocked && (
            <div data-testid="ingestion-health-blocked-list" className="mt-2 space-y-1">
              {blockedPairs.map((p, i) => (
                <div
                  key={`${p.symbol}-${p.timeframe}-${p.source}-${i}`}
                  className="text-[10px] font-mono text-zinc-400 flex items-center gap-2"
                >
                  <span className="text-rose-400">●</span>
                  <span className="text-zinc-200">{p.symbol}</span>
                  <span className="text-zinc-600">·</span>
                  <span>{p.timeframe}</span>
                  <span className="text-zinc-600">·</span>
                  <span className="text-zinc-500">{p.source}</span>
                  <span className="text-zinc-600">·</span>
                  <span>rows={p.rows}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Stale pairs drill-down (only when present) ─────────── */}
      {stalePairs.length > 0 && (
        <div className="mb-2 pt-2 border-t border-amber-900/40">
          <button
            data-testid="ingestion-health-toggle-stale"
            onClick={() => setShowStale(!showStale)}
            className="flex items-center gap-1.5 text-[10px] font-mono text-amber-300 hover:text-amber-200"
          >
            {showStale
              ? <CaretDown size={10} weight="bold" />
              : <CaretRight size={10} weight="bold" />}
            <span className="uppercase tracking-wider">
              stale / degraded rows ({stalePairs.length})
            </span>
          </button>
          {showStale && (
            <div data-testid="ingestion-health-stale-list" className="mt-2 space-y-1">
              {stalePairs.map((p, i) => (
                <div
                  key={`${p.symbol}-${p.timeframe}-${p.source}-${i}`}
                  className="text-[10px] font-mono text-zinc-400 flex items-center gap-2"
                >
                  <span className={p.band === 'degraded' ? 'text-orange-400' : 'text-amber-400'}>●</span>
                  <span className="text-zinc-200">{p.symbol}</span>
                  <span className="text-zinc-600">·</span>
                  <span>{p.timeframe}</span>
                  <span className="text-zinc-600">·</span>
                  <span className="text-zinc-500">{p.source}</span>
                  <span className="text-zinc-600">·</span>
                  <span>lag={p.lag_bars}b</span>
                  {p.has_gaps && (
                    <>
                      <span className="text-zinc-600">·</span>
                      <span className="text-orange-300">gaps</span>
                    </>
                  )}
                  {p.completeness != null && (
                    <>
                      <span className="text-zinc-600">·</span>
                      <span>comp={(p.completeness * 100).toFixed(1)}%</span>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Source health visibility (sample, when present) ────── */}
      {sample.length > 0 && (
        <div
          data-testid="ingestion-health-source-list"
          className="pt-2 border-t border-zinc-800/40 flex items-center gap-3 flex-wrap text-[10px] font-mono text-zinc-500"
        >
          <span className="text-zinc-600 uppercase tracking-wider">sources:</span>
          {Array.from(new Set(sample.map((s) => s.source).filter(Boolean))).map((src) => (
            <span key={src} className="text-zinc-300">{src}</span>
          ))}
        </div>
      )}

      {/* ── Footer: thresholds-at-read-time ────────────────────── */}
      <div
        data-testid="ingestion-health-thresholds-footer"
        className="pt-2 border-t border-zinc-800/40 flex items-center gap-3 flex-wrap text-[9px] font-mono text-zinc-600 mt-2"
      >
        <span className="uppercase tracking-wider">thresholds:</span>
        <span>max-lag={thresholds.healthy_max_lag_bars}b</span>
        <span className="text-zinc-700">·</span>
        <span>min-completeness={thresholds.healthy_min_completeness}</span>
        <span className="text-zinc-700">·</span>
        <span>heartbeat-fresh≤{thresholds.heartbeat_fresh_minutes}m</span>
        <span className="text-zinc-700">·</span>
        <span>heartbeat-stale&gt;{thresholds.heartbeat_stale_minutes}m</span>
      </div>
    </div>
  );
}
