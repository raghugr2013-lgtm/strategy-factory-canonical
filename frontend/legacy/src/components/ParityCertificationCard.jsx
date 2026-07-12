import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  CircleNotch,
  Warning,
  Gauge,
  ListChecks,
  Clock,
  Lock,
} from '@phosphor-icons/react';
import { AsfKpiTile, AsfEmptyState, VerdictBadge } from './ui-asf';

const VERDICT_VARIANT = {
  PROMOTABLE:          'success',
  NEEDS_MORE_EVIDENCE: 'warn',
  NOT_READY:           'danger',
  UNCERTIFIED:         'neutral',
};

// P1.5 · Pass 13 — Parity Certification Card (read-only, advisory-only).
//
// Operator constraint:
//   • Minimal · institutional · read-only-first · advisory-only.
//   • Surfaces the soak-evidence the operator needs to make the P1.5
//     hard-gate promotion decision DEFENSIBLE.
//   • Polls a single READ endpoint; no writes, no controls, no
//     activation buttons. Activation remains explicit operator
//     authority — this card produces the evidence, the operator
//     produces the decision.
//   • Card is HIDDEN automatically when the certifier returns row=0
//     AND verdict=UNCERTIFIED on the very first load — keeps the
//     dashboard clean until at least one sign-off has been written.
//     A small "show anyway" link allows the operator to override.
//
// Endpoint (read-only, auth-gated, advisory-only):
//   • GET /api/latent/parity-certification
//       ?window_days=&require_trade_parity=&require_htf_parity=
//       &min_samples=&min_pass_rate=&limit=

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

const VERDICT_TONE = {
  PROMOTABLE:           { dot: 'bg-emerald-400', text: 'text-emerald-300',
                          bar: 'bg-emerald-500/70',
                          label: 'PROMOTABLE' },
  NEEDS_MORE_EVIDENCE:  { dot: 'bg-amber-400',   text: 'text-amber-300',
                          bar: 'bg-amber-500/70',
                          label: 'NEEDS MORE EVIDENCE' },
  NOT_READY:            { dot: 'bg-rose-400',    text: 'text-rose-300',
                          bar: 'bg-rose-500/70',
                          label: 'NOT READY' },
  UNCERTIFIED:          { dot: 'bg-zinc-500',    text: 'text-zinc-400',
                          bar: 'bg-zinc-500/60',
                          label: 'UNCERTIFIED' },
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

function PassRateGauge({ rate, tolerance }) {
  // rate ∈ [0..1] | null. Tolerance is the configured min_pass_rate.
  const pct = rate == null ? null : Math.max(0, Math.min(1, rate)) * 100;
  const tolPct = tolerance == null ? null : Math.max(0, Math.min(1, tolerance)) * 100;
  const tone =
    pct == null ? 'bg-zinc-700' :
    tolPct != null && pct >= tolPct ? 'bg-emerald-500/80' :
    pct >= 80 ? 'bg-amber-500/80' :
    'bg-rose-500/80';
  return (
    <div
      data-testid="parity-cert-gauge"
      className="relative h-1.5 bg-zinc-800/80 rounded overflow-hidden"
    >
      {pct != null && (
        <div
          className={`absolute inset-y-0 left-0 ${tone} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      )}
      {tolPct != null && (
        <div
          className="absolute inset-y-0 w-px bg-zinc-300/70"
          style={{ left: `${tolPct}%` }}
          title={`threshold ${tolPct.toFixed(1)}%`}
        />
      )}
    </div>
  );
}

export default function ParityCertificationCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);

  const [windowDays, setWindowDays] = useState(30);
  const [requireTrade, setRequireTrade] = useState(true);
  const [requireHtf, setRequireHtf] = useState(true);
  const [showAnyway, setShowAnyway] = useState(false);

  const buildQuery = () => {
    const qs = new URLSearchParams();
    qs.set('window_days', String(windowDays));
    qs.set('require_trade_parity', String(requireTrade));
    qs.set('require_htf_parity', String(requireHtf));
    return qs.toString();
  };

  const refresh = async () => {
    setError(null);
    try {
      const out = await fetchJson(`/api/latent/parity-certification?${buildQuery()}`);
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
    // Light polling (90s). Sign-offs accumulate slowly; no urgency.
    const id = setInterval(refresh, 90_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowDays, requireTrade, requireHtf]);

  // Auto-hide path: pre-soak, the collection is empty and the card adds
  // noise without value. Keep the operator's dashboard clean unless they
  // ask to see it.
  const isPreSoak =
    !loading && !error && data?.row_count === 0
    && data?.verdict?.verdict === 'UNCERTIFIED';

  if (isPreSoak && !showAnyway) {
    return (
      <div
        data-testid="parity-cert-card-presoak"
        className="card-premium p-2 border border-zinc-800/60 bg-zinc-950/30 mb-4 flex items-center justify-between text-[10px] font-mono text-zinc-500"
      >
        <span className="flex items-center gap-2">
          <Lock size={11} weight="bold" />
          parity-certification · pre-soak · no sign-offs yet
        </span>
        <button
          data-testid="parity-cert-show-anyway"
          onClick={() => setShowAnyway(true)}
          className="text-cyan-400 hover:text-cyan-300 underline decoration-dotted underline-offset-2"
        >
          show anyway
        </button>
      </div>
    );
  }

  const verdict = data?.verdict?.verdict || 'UNCERTIFIED';
  const tone = VERDICT_TONE[verdict] || VERDICT_TONE.UNCERTIFIED;
  const rationale = data?.verdict?.rationale || '';
  const observedRate = data?.verdict?.observed_pass_rate;
  const minPassRate  = data?.verdict?.min_pass_rate;
  const minSamples   = data?.verdict?.min_samples;
  const summary      = data?.summary || {};
  const hardGate     = summary.hard_gate || {};
  const tradeParity  = summary.trade_parity || {};
  const htfParity    = summary.htf_parity || {};
  const htfVerdicts  = htfParity.verdicts || {};
  const flagsAtRead  = data?.flags_at_read_time || {};

  return (
    <div
      data-testid="parity-certification-card"
      className="asf-section asf-u2-panel card-premium p-4 border border-zinc-800/80 bg-zinc-950/40 mb-4"
    >
      <div className="asf-section__hd flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="asf-legacy-title flex items-center gap-2">
          <ShieldCheck size={14} weight="fill" className="text-cyan-400" />
          <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-300">
            Parity Certification · P1.5
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
              data-testid="parity-cert-refreshed"
              className="flex items-center gap-1"
            >
              <Clock size={10} />
              {new Date(refreshedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            data-testid="parity-cert-refresh"
            onClick={refresh}
            className="px-2 py-0.5 border border-zinc-700/60 rounded hover:border-zinc-500 hover:text-zinc-300 transition-colors"
            title="Refresh now"
          >
            refresh
          </button>
        </div>
      </div>

      {/* ── Controls ────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap mb-3 text-[10px] font-mono text-zinc-400">
        <label className="flex items-center gap-1.5">
          <span className="text-zinc-500 uppercase tracking-wider">window</span>
          <select
            data-testid="parity-cert-window-select"
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="bg-zinc-900/60 border border-zinc-700/60 rounded px-1.5 py-0.5 text-zinc-200"
          >
            <option value={7}>7d</option>
            <option value={14}>14d</option>
            <option value={30}>30d</option>
            <option value={90}>90d</option>
            <option value={365}>1y</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            data-testid="parity-cert-require-trade"
            type="checkbox"
            checked={requireTrade}
            onChange={(e) => setRequireTrade(e.target.checked)}
            className="accent-cyan-500"
          />
          <span>require trade-parity</span>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            data-testid="parity-cert-require-htf"
            type="checkbox"
            checked={requireHtf}
            onChange={(e) => setRequireHtf(e.target.checked)}
            className="accent-cyan-500"
          />
          <span>require HTF-parity</span>
        </label>
      </div>

      {error && (
        <div className="mb-3">
          <AsfEmptyState
            slug="parity-cert-error"
            testId="parity-cert-error"
            title="Parity certification failed to load"
            body={error}
            action={{ label: 'Retry', onClick: refresh, testId: 'parity-cert-error-retry' }}
          />
        </div>
      )}

      {/* ── Verdict + gauge ─────────────────────────────────────── */}
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-1.5" data-testid="parity-cert-verdict-row">
          <VerdictBadge verdict={VERDICT_VARIANT[verdict] || 'neutral'} testId="parity-cert-verdict">
            {tone.label}
          </VerdictBadge>
          <span className="text-[10px] font-mono text-zinc-500">
            {observedRate != null
              ? `${(observedRate * 100).toFixed(1)}% pass-rate`
              : 'no pass-rate yet'}
          </span>
        </div>
        <PassRateGauge rate={observedRate} tolerance={minPassRate} />
        <div className="mt-1 flex items-center justify-between text-[9px] font-mono text-zinc-600">
          <span>0%</span>
          <span data-testid="parity-cert-threshold">
            threshold {minPassRate != null ? `${(minPassRate * 100).toFixed(1)}%` : '—'}
          </span>
          <span>100%</span>
        </div>
      </div>

      {/* ── KPI strip ──────────────────────────────────────────── */}
      <div className="asf-kpi-grid mb-3">
        <AsfKpiTile
          testId="parity-cert-pill-rows"
          label="Signoffs (window)"
          value={data?.row_count ?? '—'}
          verdict="info"
          title={`Sign-offs in last ${windowDays} day(s)`}
        />
        <AsfKpiTile
          testId="parity-cert-pill-min-samples"
          label="Min Samples"
          value={minSamples ?? '—'}
          verdict={data?.row_count >= (minSamples || 0) ? 'success' : 'warn'}
          title="Operator-configurable evidence threshold (PARITY_CERTIFICATION_MIN_SAMPLES)"
        />
        <AsfKpiTile
          testId="parity-cert-pill-hardgate"
          label="Would-Pass Hard Gate"
          value={hardGate.rate != null ? `${(hardGate.rate * 100).toFixed(1)}%` : '—'}
          verdict={hardGate.rate != null && hardGate.rate >= (minPassRate || 0)
            ? 'success'
            : hardGate.rate != null ? 'warn' : 'neutral'}
          title="Fraction of sign-offs that would PASS the hardened gate (signal × trade × HTF)"
        />
        <AsfKpiTile
          testId="parity-cert-pill-trade-rate"
          label="Trade-Parity Rate"
          value={tradeParity.rate != null ? `${(tradeParity.rate * 100).toFixed(1)}%` : 'N/A'}
          verdict={tradeParity.rate == null ? 'neutral' :
            tradeParity.rate >= 0.95 ? 'success' : 'warn'}
          title={`P1.3 advisory · ${tradeParity.passed || 0}/${tradeParity.present || 0} present`}
        />
        <AsfKpiTile
          testId="parity-cert-pill-htf-rate"
          label="HTF-Parity Rate"
          value={htfParity.rate != null ? `${(htfParity.rate * 100).toFixed(1)}%` : 'N/A'}
          verdict={htfParity.rate == null ? 'neutral' :
            htfParity.rate >= 0.95 ? 'success' : 'warn'}
          title={`P1.4 advisory · ${htfParity.passing || 0}/${htfParity.present || 0} in passing band`}
        />
      </div>

      {/* ── HTF verdict mix (when present) ──────────────────────── */}
      {htfParity.present > 0 && (
        <div
          data-testid="parity-cert-htf-mix"
          className="mb-3 pt-2 border-t border-zinc-800/60 flex items-center gap-3 flex-wrap text-[10px] font-mono text-zinc-500"
        >
          <span className="flex items-center gap-1 text-zinc-600 uppercase tracking-wider">
            <Gauge size={11} weight="bold" />
            htf-mix:
          </span>
          {[
            ['EXACT',            'text-emerald-300'],
            ['WITHIN_TOLERANCE', 'text-emerald-400'],
            ['NOT_APPLICABLE',   'text-zinc-400'],
            ['DIVERGENT',        'text-rose-300'],
            ['ERROR',            'text-amber-300'],
          ].map(([k, c]) => (
            <span key={k} className="flex items-center gap-1">
              <span className={c}>{k}</span>
              <span className="text-zinc-200">{htfVerdicts[k] || 0}</span>
            </span>
          ))}
        </div>
      )}

      {/* ── Status counts (always show) ─────────────────────────── */}
      {summary.status_counts && Object.keys(summary.status_counts).length > 0 && (
        <div
          data-testid="parity-cert-status-counts"
          className="mb-3 pt-2 border-t border-zinc-800/60 flex items-center gap-3 flex-wrap text-[10px] font-mono text-zinc-500"
        >
          <span className="flex items-center gap-1 text-zinc-600 uppercase tracking-wider">
            <ListChecks size={11} weight="bold" />
            sign-off mix:
          </span>
          {Object.entries(summary.status_counts).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1">
              <span className={k === 'PASSED' ? 'text-emerald-300' : 'text-zinc-400'}>
                {k}
              </span>
              <span className="text-zinc-200">{v}</span>
            </span>
          ))}
        </div>
      )}

      {/* ── Rationale ───────────────────────────────────────────── */}
      {rationale && (
        <div
          data-testid="parity-cert-rationale"
          className="mb-2 p-2 text-[10px] font-mono leading-relaxed text-zinc-400 bg-zinc-900/40 border border-zinc-800/60 rounded"
        >
          {rationale}
        </div>
      )}

      {/* ── Flags-at-read-time footer ───────────────────────────── */}
      <div
        data-testid="parity-cert-flags-footer"
        className="pt-2 border-t border-zinc-800/40 flex items-center gap-3 flex-wrap text-[9px] font-mono text-zinc-600"
      >
        <span className="uppercase tracking-wider">activation flags:</span>
        <span className={flagsAtRead.ENABLE_TRADE_PARITY_HARD_GATE
          ? 'text-emerald-400' : 'text-zinc-500'}>
          trade-hard-gate {flagsAtRead.ENABLE_TRADE_PARITY_HARD_GATE ? 'ON' : 'OFF'}
        </span>
        <span className="text-zinc-700">·</span>
        <span className={flagsAtRead.ENABLE_HTF_PARITY_HARD_GATE
          ? 'text-emerald-400' : 'text-zinc-500'}>
          htf-hard-gate {flagsAtRead.ENABLE_HTF_PARITY_HARD_GATE ? 'ON' : 'OFF'}
        </span>
        <span className="text-zinc-700">·</span>
        <span>
          min_samples={flagsAtRead.PARITY_CERTIFICATION_MIN_SAMPLES ?? '—'}
        </span>
        <span className="text-zinc-700">·</span>
        <span>
          min_pass_rate={flagsAtRead.PARITY_CERTIFICATION_MIN_PASS_RATE ?? '—'}
        </span>
        {data?.dormant === true && (
          <span className="ml-auto flex items-center gap-1 text-zinc-500">
            <Lock size={10} weight="bold" /> dormant
          </span>
        )}
      </div>
    </div>
  );
}
