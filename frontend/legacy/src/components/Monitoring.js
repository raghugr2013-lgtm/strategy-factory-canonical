import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AsfEmptyState } from './ui-asf';

// ════════════════════════════════════════════════════════════════════
// Phase 6 — Monitoring & Control Layer.
// Observes Trade Runner data, reports system state, breaches, and
// lets the operator pause / resume / reset via /api/monitoring/*.
// ════════════════════════════════════════════════════════════════════

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8001`
  : process.env.REACT_APP_BACKEND_URL;

const M = `${API_URL}/api/monitoring`;

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, { cache: 'no-store', ...opts });
  const t = await r.text();
  let body;
  try { body = t ? JSON.parse(t) : {}; } catch { body = { raw: t }; }
  if (!r.ok) throw new Error(body?.detail || `HTTP ${r.status}`);
  return body;
}
const api = {
  status: () => fetchJson(`${M}/status`),
  runNow: () => fetchJson(`${M}/run`, { method: 'POST' }),
  reset: () => fetchJson(`${M}/reset`, { method: 'POST' }),
  pauseAll: () => fetchJson(`${M}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ global_stop: true }),
  }),
  pauseStrategy: (sid) => fetchJson(`${M}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_id: sid }),
  }),
  resumeAll: () => fetchJson(`${M}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }),
  resumeStrategy: (sid) => fetchJson(`${M}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy_id: sid }),
  }),
  scheduler: (enabled, interval_seconds) => fetchJson(`${M}/scheduler`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, interval_seconds }),
  }),
  thresholds: (patch) => fetchJson(`${M}/thresholds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }),
  equity: (limit = 200) => fetchJson(`${M}/equity-curve?limit=${limit}`),
};

// ─── Small UI atoms ────────────────────────────────────────────────
function Section({ title, children, action }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-card p-4 md:p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-heading text-sm font-semibold text-zinc-100 uppercase tracking-wider">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

const STATE_STYLES = {
  RUNNING:        { bg: 'bg-emerald-500/10',   text: 'text-emerald-400', border: 'border-emerald-500/30' },
  PAUSED_DAILY:   { bg: 'bg-yellow-500/10',    text: 'text-yellow-400',  border: 'border-yellow-500/30' },
  STOPPED:        { bg: 'bg-red-500/10',       text: 'text-red-400',     border: 'border-red-500/30' },
  RECOVERY_MODE:  { bg: 'bg-sky-500/10',       text: 'text-sky-400',     border: 'border-sky-500/30' },
};
const STRAT_STYLES = {
  ACTIVE:         { bg: 'bg-emerald-500/10',  text: 'text-emerald-400', border: 'border-emerald-500/30' },
  UNDER_REVIEW:   { bg: 'bg-yellow-500/10',   text: 'text-yellow-400',  border: 'border-yellow-500/30' },
  PAUSED_STREAK:  { bg: 'bg-orange-500/10',   text: 'text-orange-400',  border: 'border-orange-500/30' },
  PAUSED_MANUAL:  { bg: 'bg-red-500/10',      text: 'text-red-400',     border: 'border-red-500/30' },
};
function Pill({ value, styleMap }) {
  const s = styleMap[value] || { bg: 'bg-surface-elevated', text: 'text-zinc-300', border: 'border-border-subtle' };
  return (
    <span className={`text-[10px] font-mono font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${s.bg} ${s.text} ${s.border}`}>
      {value || '—'}
    </span>
  );
}

function Stat({ label, value, valueClass = '', testid }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className={`text-sm font-mono text-zinc-100 ${valueClass}`} data-testid={testid}>{value}</span>
    </div>
  );
}

function fmtPct(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return `${n.toFixed(2)}%`;
}
function fmtMoney(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Minimal SVG sparkline for the equity curve (no lib, keeps deps lean)
function EquitySparkline({ points }) {
  if (!points || points.length < 2) {
    return <div className="h-24 flex items-center justify-center text-xs text-zinc-500 italic">Not enough data yet</div>;
  }
  const W = 640, H = 120, PAD = 4;
  const ys = points.map(p => Number(p.equity) || 0);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const range = (max - min) || 1;
  const step = (W - PAD * 2) / (points.length - 1);
  const path = points.map((p, i) => {
    const x = PAD + i * step;
    const y = H - PAD - ((Number(p.equity) - min) / range) * (H - PAD * 2);
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28" data-testid="mon-equity-spark">
      <defs>
        <linearGradient id="eqgrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#00E0B8" stopOpacity="0.35"/>
          <stop offset="100%" stopColor="#00E0B8" stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={`${path} L${(W - PAD).toFixed(1)},${H - PAD} L${PAD},${H - PAD} Z`} fill="url(#eqgrad)" />
      <path d={path} fill="none" stroke="#00E0B8" strokeWidth="1.5" />
    </svg>
  );
}

// ─── Main component ────────────────────────────────────────────────
export default function Monitoring() {
  const [st, setSt] = useState(null);
  const [equity, setEquity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [thresholdDraft, setThresholdDraft] = useState(null);
  const [schedIval, setSchedIval] = useState(60);
  const pollingRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [status, eq] = await Promise.all([api.status(), api.equity(200)]);
      setSt(status);
      setEquity(eq.points || []);
      if (!thresholdDraft) setThresholdDraft(status.config);
      setSchedIval(status.scheduler?.interval_seconds || 60);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [thresholdDraft]);

  useEffect(() => {
    refresh();
    pollingRef.current = setInterval(refresh, 5000);
    return () => pollingRef.current && clearInterval(pollingRef.current);
  }, [refresh]);

  const wrap = async (fn) => {
    try { setBusy(true); setError(null); await fn(); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const handleRunNow = () => wrap(api.runNow);
  const handleReset = () => wrap(api.reset);
  const handlePauseAll = () => wrap(api.pauseAll);
  const handleResumeAll = () => wrap(api.resumeAll);

  const toggleScheduler = (enabled) => wrap(() => api.scheduler(enabled, Number(schedIval) || 60));

  const saveThresholds = () => wrap(async () => {
    if (!thresholdDraft) return;
    await api.thresholds({
      daily_dd_threshold_pct: Number(thresholdDraft.daily_dd_threshold_pct),
      total_dd_threshold_pct: Number(thresholdDraft.total_dd_threshold_pct),
      underperform_pf_threshold: Number(thresholdDraft.underperform_pf_threshold),
      underperform_window: Number(thresholdDraft.underperform_window),
      loss_streak_threshold: Number(thresholdDraft.loss_streak_threshold),
    });
  });

  if (loading) return <div className="p-6 text-sm text-zinc-400" data-testid="monitoring-loading">Loading monitoring…</div>;
  const metrics = st?.metrics || {};
  const strategies = st?.strategies || [];
  const breaches = st?.breaches || [];
  const state = st?.state || 'RUNNING';
  const cfg = st?.config || {};

  return (
    <div className="asf-section asf-u2-panel space-y-5" data-testid="monitoring-root">
      {/* ── Header ── */}
      <div className="asf-section__hd flex items-start justify-between flex-wrap gap-4">
        <div className="asf-legacy-title">
          <div className="text-[10px] font-mono text-accent-primary/80 tracking-widest uppercase">Phase 6</div>
          <h2 className="font-heading text-2xl font-bold text-zinc-100">Monitoring &amp; Control</h2>
          <p className="text-xs text-zinc-400 mt-1 max-w-2xl">
            Real-time risk layer. Observes Trade Runner, enforces drawdown limits,
            pauses under-performing strategies — all via existing APIs. Monitoring
            failures never block the trading system.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <Pill value={state} styleMap={STATE_STYLES} />
          <button
            data-testid="mon-run-btn"
            onClick={handleRunNow}
            disabled={busy}
            className="px-3 py-1.5 rounded text-xs border border-accent-primary/30 text-accent-primary bg-accent-primary-soft hover:bg-accent-primary/20 disabled:opacity-50"
          >
            Run now
          </button>
          <button
            data-testid="mon-reset-btn"
            onClick={handleReset}
            disabled={busy}
            className="px-3 py-1.5 rounded text-xs text-zinc-300 border border-border-subtle hover:bg-surface-elevated disabled:opacity-50"
          >
            Reset
          </button>
        </div>
      </div>

      {error && (
        <AsfEmptyState
          slug="mon-error"
          testId="mon-error"
          title="Monitoring error"
          body={error}
        />
      )}

      {/* ── Control strip ── */}
      <Section
        title="Control"
        action={
          <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
            Last updated {st?.updated_at ? new Date(st.updated_at).toLocaleTimeString() : '—'}
          </span>
        }
      >
        <div className="flex items-center gap-2 flex-wrap">
          <button
            data-testid="mon-pause-all"
            onClick={handlePauseAll}
            disabled={busy || state === 'STOPPED'}
            className="px-3 py-1.5 rounded text-xs border border-red-500/30 text-red-400 bg-red-500/5 hover:bg-red-500/10 disabled:opacity-50"
          >
            Stop all trading
          </button>
          <button
            data-testid="mon-resume-all"
            onClick={handleResumeAll}
            disabled={busy || state === 'RUNNING'}
            className="px-3 py-1.5 rounded text-xs border border-emerald-500/30 text-emerald-400 bg-emerald-500/5 hover:bg-emerald-500/10 disabled:opacity-50"
          >
            Resume trading
          </button>
          <span className="mx-2 text-zinc-600">·</span>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            Interval (s)
            <input
              type="number" min="5" max="3600" step="5"
              value={schedIval}
              data-testid="mon-sched-interval"
              onChange={(e) => setSchedIval(Number(e.target.value))}
              className="w-20 bg-surface-elevated border border-border-subtle rounded px-2 py-1 text-sm text-zinc-100"
            />
          </label>
          <button
            data-testid="mon-sched-on"
            onClick={() => toggleScheduler(true)}
            disabled={busy}
            className="px-3 py-1.5 rounded text-xs border border-accent-primary/30 text-accent-primary bg-accent-primary-soft hover:bg-accent-primary/20 disabled:opacity-50"
          >
            Scheduler ON
          </button>
          <button
            data-testid="mon-sched-off"
            onClick={() => toggleScheduler(false)}
            disabled={busy}
            className="px-3 py-1.5 rounded text-xs border border-border-subtle text-zinc-300 hover:bg-surface-elevated disabled:opacity-50"
          >
            OFF
          </button>
          <span
            data-testid="mon-sched-status"
            className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              st?.scheduler?.enabled
                ? 'border-accent-primary/40 text-accent-primary bg-accent-primary-soft'
                : 'border-border-subtle text-zinc-500 bg-surface-elevated'
            }`}
          >
            {st?.scheduler?.enabled ? 'ON' : 'OFF'}
          </span>
        </div>
      </Section>

      {/* ── Metrics + equity curve ── */}
      <div className="grid grid-cols-1 md:grid-cols-[3fr,2fr] gap-4">
        <Section title="Portfolio equity">
          <EquitySparkline points={equity} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            <Stat label="Equity"           value={fmtMoney(metrics.portfolio_current_equity)} testid="mon-equity" />
            <Stat label="Peak"             value={fmtMoney(metrics.portfolio_peak_equity)}    testid="mon-peak" />
            <Stat label="Total DD"         value={fmtPct(metrics.portfolio_total_dd_pct)}
                  valueClass={metrics.portfolio_total_dd_pct >= (cfg.total_dd_threshold_pct || 10) ? 'text-red-400' : ''}
                  testid="mon-total-dd" />
            <Stat label="Daily DD"         value={fmtPct(metrics.portfolio_daily_dd_pct)}
                  valueClass={metrics.portfolio_daily_dd_pct >= (cfg.daily_dd_threshold_pct || 5) ? 'text-yellow-400' : ''}
                  testid="mon-daily-dd" />
          </div>
        </Section>

        <Section title="Fleet">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Active runs"      value={metrics.active_runs ?? 0}        testid="mon-active-runs" />
            <Stat label="Active strategies" value={metrics.active_strategies ?? 0} testid="mon-active-strats" />
            <Stat label="Under review"     value={metrics.under_review ?? 0}       testid="mon-under-review" />
            <Stat label="Paused"           value={metrics.paused_strategies ?? 0}  testid="mon-paused" />
          </div>
          <div className="mt-4 border-t border-border-subtle pt-3">
            <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-2">Thresholds</div>
            {thresholdDraft && (
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['daily_dd_threshold_pct', 'Daily DD %'],
                  ['total_dd_threshold_pct', 'Total DD %'],
                  ['underperform_pf_threshold', 'Underperf PF'],
                  ['underperform_window', 'PF window N'],
                  ['loss_streak_threshold', 'Loss streak'],
                ].map(([k, lbl]) => (
                  <label key={k} className="flex flex-col text-xs">
                    <span className="text-zinc-500 mb-0.5">{lbl}</span>
                    <input
                      type="number" step="0.1"
                      value={thresholdDraft[k] ?? ''}
                      data-testid={`mon-thr-${k}`}
                      onChange={(e) => setThresholdDraft({ ...thresholdDraft, [k]: e.target.value === '' ? '' : Number(e.target.value) })}
                      className="bg-surface-elevated border border-border-subtle rounded px-2 py-1 text-sm text-zinc-100"
                    />
                  </label>
                ))}
              </div>
            )}
            <button
              data-testid="mon-save-thresholds"
              onClick={saveThresholds}
              disabled={busy}
              className="mt-3 px-3 py-1.5 rounded text-xs bg-accent-primary text-[#061812] font-semibold hover:bg-accent-primary-dim disabled:opacity-50"
            >
              Save thresholds
            </button>
          </div>
        </Section>
      </div>

      {/* ── Strategies table ── */}
      <Section
        title={`Strategies (${strategies.length})`}
        action={<span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">observe · pause · resume</span>}
      >
        {strategies.length === 0 ? (
          <div className="text-xs text-zinc-500 italic" data-testid="mon-no-strategies">
            No strategies tracked yet. Start a Trade Runner run and click "Run now" to populate this view.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="mon-strategies-table">
              <thead>
                <tr className="text-zinc-500 border-b border-border-subtle">
                  <th className="text-left py-2 px-2">Strategy</th>
                  <th className="text-left py-2 px-2">Run / Pair · TF</th>
                  <th className="text-left py-2 px-2">State</th>
                  <th className="text-right py-2 px-2">Equity</th>
                  <th className="text-right py-2 px-2">Total DD</th>
                  <th className="text-right py-2 px-2">Daily DD</th>
                  <th className="text-right py-2 px-2">PF (last N)</th>
                  <th className="text-right py-2 px-2">Loss streak</th>
                  <th className="text-right py-2 px-2">Trades today</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((s) => {
                  const m = s.metrics || {};
                  const sid = s.strategy_id || s.run_id;
                  return (
                    <tr key={sid} data-testid={`mon-strat-row-${sid}`} className="border-b border-border-subtle/50 hover:bg-surface-elevated/40">
                      <td className="py-1.5 px-2 font-mono text-zinc-200">{(sid || '').slice(0, 14)}</td>
                      <td className="py-1.5 px-2 text-zinc-400">
                        <span className="font-mono">{(s.run_id || '').slice(0, 8)}</span>
                        <span className="mx-1 text-zinc-600">·</span>
                        <span>{s.pair || '—'} {s.timeframe || ''}</span>
                      </td>
                      <td className="py-1.5 px-2"><Pill value={s.state} styleMap={STRAT_STYLES} /></td>
                      <td className="py-1.5 px-2 text-right text-zinc-200">{fmtMoney(m.equity)}</td>
                      <td className={`py-1.5 px-2 text-right ${Number(m.total_dd_pct) >= (cfg.total_dd_threshold_pct || 10) ? 'text-red-400' : 'text-zinc-200'}`}>
                        {fmtPct(m.total_dd_pct)}
                      </td>
                      <td className={`py-1.5 px-2 text-right ${Number(m.daily_dd_pct) >= (cfg.daily_dd_threshold_pct || 5) ? 'text-yellow-400' : 'text-zinc-200'}`}>
                        {fmtPct(m.daily_dd_pct)}
                      </td>
                      <td className={`py-1.5 px-2 text-right ${Number(m.pf_last_n) < Number(cfg.underperform_pf_threshold || 1) && Number(m.recent_trades) >= Number(cfg.underperform_window || 20) ? 'text-yellow-400' : 'text-zinc-200'}`}>
                        {m.pf_last_n != null ? Number(m.pf_last_n).toFixed(2) : '—'}
                      </td>
                      <td className={`py-1.5 px-2 text-right ${Number(m.loss_streak) >= Number(cfg.loss_streak_threshold || 5) ? 'text-orange-400' : 'text-zinc-200'}`}>
                        {m.loss_streak ?? 0}
                      </td>
                      <td className="py-1.5 px-2 text-right text-zinc-300">{m.trades_today ?? 0}</td>
                      <td className="py-1.5 px-2 text-right space-x-2">
                        {s.state === 'PAUSED_MANUAL' ? (
                          <button
                            data-testid={`mon-resume-${sid}`}
                            onClick={() => wrap(() => api.resumeStrategy(sid))}
                            disabled={busy}
                            className="text-[11px] text-emerald-400 hover:underline"
                          >
                            Resume
                          </button>
                        ) : (
                          <button
                            data-testid={`mon-pause-${sid}`}
                            onClick={() => wrap(() => api.pauseStrategy(sid))}
                            disabled={busy}
                            className="text-[11px] text-red-400 hover:underline"
                          >
                            Pause
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── Breaches ── */}
      <Section title={`Breach log (${breaches.length})`}>
        {breaches.length === 0 ? (
          <div className="text-xs text-zinc-500 italic" data-testid="mon-no-breaches">No breaches recorded. 🫶</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="mon-breach-table">
              <thead>
                <tr className="text-zinc-500 border-b border-border-subtle">
                  <th className="text-left py-2 px-2">When</th>
                  <th className="text-left py-2 px-2">Kind</th>
                  <th className="text-left py-2 px-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {breaches.map((b, i) => (
                  <tr key={i} className="border-b border-border-subtle/50">
                    <td className="py-1.5 px-2 text-zinc-400 font-mono">{b.at ? new Date(b.at).toLocaleString() : '—'}</td>
                    <td className="py-1.5 px-2 font-mono text-zinc-200">{b.kind}</td>
                    <td className="py-1.5 px-2 text-zinc-300">
                      {b.details ? JSON.stringify(b.details) : (b.reason || '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
