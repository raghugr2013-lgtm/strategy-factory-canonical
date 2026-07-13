import React, { useEffect, useRef, useState, useCallback } from 'react';
import { API_URL, generateCbot } from '../services/api';


async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

const POLL_MS = 4000;

/**
 * Multi-Cycle Optimisation Runner.
 *
 * Drives N sequential discovery cycles via existing engines (no new
 * orchestration logic on the frontend). Shows:
 *   • "Run 5 Cycles" button (one-click default).
 *   • Cycle progress (1/5 .. 5/5) with a bar.
 *   • PF improvement trend — sparkline of best avg_pf per cycle.
 *   • Per-cycle scan summary (pair × timeframe results).
 *
 * Backend endpoints:
 *   POST /api/auto/multi-cycle/start   { cycles, batch_size, ... }
 *   POST /api/auto/multi-cycle/stop
 *   GET  /api/auto/multi-cycle/status
 */
export default function MultiCycleRunner({ onPromote = null } = {}) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // Phase 21 — history & best-strategy state.
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState(null);          // {count, runs[]}
  const [historyLoading, setHistoryLoading] = useState(false);
  const [bestByRun, setBestByRun] = useState({});        // run_id → best dict
  const [bestLoading, setBestLoading] = useState({});    // run_id → bool
  const [actionMsg, setActionMsg] = useState(null);
  const lastSeenRunRef = useRef(null);

  // ── HTTP helpers ──────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/auto/multi-cycle/status`);
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e.message || 'status fetch failed');
    }
  }, []);

  const startRun = useCallback(async (cycles = 5) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/auto/multi-cycle/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cycles, batch_size: 3 }),
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setStatus(data);
    } catch (e) {
      setError(e.message || 'start failed');
    } finally {
      setBusy(false);
    }
  }, []);

  const stopRun = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/auto/multi-cycle/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'stop failed');
    } finally {
      setBusy(false);
    }
  }, [fetchStatus]);

  // ── Phase 21 — history & best-of-run helpers ─────────────────────
  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auto/multi-cycle/history?limit=10`);
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setHistory(data);
    } catch (e) {
      setError(e.message || 'history fetch failed');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const fetchBestForRun = useCallback(async (runId) => {
    if (!runId || bestByRun[runId] || bestLoading[runId]) return;
    setBestLoading((s) => ({ ...s, [runId]: true }));
    try {
      const res = await fetch(
        `${API_URL}/api/auto/multi-cycle/runs/${encodeURIComponent(runId)}/best`,
      );
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setBestByRun((s) => ({ ...s, [runId]: data }));
    } catch (e) {
      setBestByRun((s) => ({
        ...s,
        [runId]: { error: e.message || 'fetch failed', best: null },
      }));
    } finally {
      setBestLoading((s) => ({ ...s, [runId]: false }));
    }
  }, [bestByRun, bestLoading]);

  // ── Action: Promote a strategy to the dashboard ──────────────────
  const onPromoteClick = useCallback((strat) => {
    setActionMsg(null);
    if (typeof onPromote === 'function') {
      try {
        onPromote(strat);
        setActionMsg(`Promoted to dashboard: ${strat?.pair}/${strat?.timeframe}`);
      } catch (e) {
        setActionMsg(`Promote failed: ${e?.message || 'unknown'}`);
      }
    } else {
      setActionMsg('Dashboard handler not wired (onPromote prop missing)');
    }
  }, [onPromote]);

  // ── Action: Generate cBot for the best strategy ──────────────────
  const onGenerateCbotClick = useCallback(async (strat) => {
    if (!strat?.strategy_text) {
      setActionMsg('No strategy_text on this entry — cannot generate cBot');
      return;
    }
    setActionMsg('Generating cBot…');
    try {
      const res = await generateCbot(
        strat.strategy_text,
        strat.pair || 'EURUSD',
        strat.timeframe || 'H1',
        strat.parameters || {},
        {},
        null,
        strat.indicators || null,
        strat.strategy_type || null,
      );
      const ok = res?.code || res?.success;
      setActionMsg(
        ok
          ? `cBot generated (${(res?.code || '').length} chars). Open the cBot tab to copy.`
          : `cBot returned: ${JSON.stringify(res).slice(0, 120)}`,
      );
    } catch (e) {
      setActionMsg(`cBot failed: ${e?.message || 'unknown'}`);
    }
  }, []);

  // ── Polling lifecycle ─────────────────────────────────────────────
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchStatus]);

  // ── Phase 21 — when a run COMPLETES, auto-fetch its best strategy ─
  useEffect(() => {
    const s = status?.status;
    const rid = status?.run_id;
    if (!rid) return;
    if ((s === 'completed' || s === 'stopped') && lastSeenRunRef.current !== rid) {
      lastSeenRunRef.current = rid;
      fetchBestForRun(rid);
      // Also refresh history so the just-finished run shows up.
      if (historyOpen) fetchHistory();
    }
  }, [status?.status, status?.run_id, fetchBestForRun, fetchHistory, historyOpen]);

  const running       = status?.status === 'running';
  const completed     = status?.status === 'completed';
  const stopped       = status?.status === 'stopped';
  const errored       = status?.status === 'error';
  const currentCycle  = status?.current_cycle || 0;
  const totalCycles   = status?.total_cycles  || 0;
  const cycles        = status?.cycles        || [];
  const pfTrend       = status?.pf_trend      || [];
  const stopRequested = !!status?.stop_requested;

  const progressPct = totalCycles > 0
    ? Math.min(100, Math.round((currentCycle / totalCycles) * 100))
    : 0;

  // ── Trend-arrow heuristic: compare first reported PF to last ──────
  const firstPf = pfTrend.find((p) => typeof p === 'number');
  const lastPf  = [...pfTrend].reverse().find((p) => typeof p === 'number');
  let trendArrow = '·';
  let trendTone = 'text-zinc-400';
  if (typeof firstPf === 'number' && typeof lastPf === 'number') {
    if (lastPf - firstPf > 0.05)       { trendArrow = '▲'; trendTone = 'text-emerald-300'; }
    else if (lastPf - firstPf < -0.05) { trendArrow = '▼'; trendTone = 'text-red-300'; }
    else                                { trendArrow = '→'; trendTone = 'text-zinc-300'; }
  }

  return (
    <div
      data-testid="multi-cycle-card"
      className="asf-section asf-u2-panel border border-zinc-700/50 rounded-lg bg-zinc-900/40 p-4 mb-4"
    >
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="asf-section__hd asf-legacy-title flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={
              'w-2 h-2 rounded-full ' +
              (running ? 'bg-amber-400 animate-pulse' :
               completed ? 'bg-emerald-400' :
               errored   ? 'bg-red-400' : 'bg-zinc-600')
            }
          />
          <h3 className="text-sm font-mono font-semibold text-zinc-200 truncate">
            Multi-Cycle Optimisation
          </h3>
          <span
            data-testid="multi-cycle-state-label"
            className={
              'text-[10px] font-mono px-2 py-0.5 rounded-full border ' +
              (running ? 'border-amber-500/40 text-amber-300 bg-amber-500/10' :
               completed ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' :
               stopped ? 'border-zinc-500/40 text-zinc-300 bg-zinc-500/10' :
               errored ? 'border-red-500/40 text-red-300 bg-red-500/10' :
               'border-zinc-600 text-zinc-400 bg-zinc-800/40')
            }
          >
            {(status?.status || 'idle').toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {!running ? (
            <button
              type="button"
              data-testid="multi-cycle-run-5"
              onClick={() => startRun(5)}
              disabled={busy}
              className={
                'text-[11px] font-mono px-3 py-1.5 rounded ' +
                'bg-accent-primary/20 hover:bg-accent-primary/30 ' +
                'border border-accent-primary/40 text-accent-primary ' +
                'transition-colors ' + (busy ? 'opacity-60 cursor-wait' : '')
              }
            >
              {busy ? '…' : 'Run 5 Cycles'}
            </button>
          ) : (
            <button
              type="button"
              data-testid="multi-cycle-stop"
              onClick={stopRun}
              disabled={busy || stopRequested}
              className={
                'text-[11px] font-mono px-3 py-1.5 rounded border ' +
                'border-red-500/40 text-red-300 hover:bg-red-500/10 ' +
                'transition-colors ' +
                ((busy || stopRequested) ? 'opacity-60 cursor-wait' : '')
              }
            >
              {stopRequested ? 'Stopping…' : 'Stop'}
            </button>
          )}
        </div>
      </div>

      {/* ── Progress bar ─────────────────────────────────────────── */}
      {totalCycles > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400 mb-1">
            <span data-testid="multi-cycle-progress-label">
              Cycle {currentCycle} / {totalCycles}
            </span>
            <span>{progressPct}%</span>
          </div>
          <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
            <div
              data-testid="multi-cycle-progress-bar"
              className={
                'h-full transition-all duration-500 ' +
                (running ? 'bg-amber-400' :
                 completed ? 'bg-emerald-400' :
                 errored ? 'bg-red-400' : 'bg-zinc-500')
              }
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {/* ── PF trend sparkline + arrow ─────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div className="flex flex-col">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
            PF trend
          </span>
          <div className="flex items-center gap-2">
            <Sparkline values={pfTrend} />
            <span data-testid="multi-cycle-trend-arrow" className={`text-sm font-mono ${trendTone}`}>
              {trendArrow}
            </span>
          </div>
        </div>
        <div className="flex flex-col">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
            First → last PF
          </span>
          <span data-testid="multi-cycle-pf-delta" className="text-[12px] font-mono text-zinc-200">
            {typeof firstPf === 'number'
              ? firstPf.toFixed(2)
              : '—'}
            {' → '}
            {typeof lastPf === 'number'
              ? lastPf.toFixed(2)
              : '—'}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
            Saved (cumulative)
          </span>
          <span data-testid="multi-cycle-saved-cum" className="text-[12px] font-mono text-zinc-200">
            {cycles.reduce((s, c) => s + (c.strategies_saved || 0), 0)}
          </span>
        </div>
      </div>

      {/* ── Per-cycle table ──────────────────────────────────────── */}
      {cycles.length > 0 && (
        <div className="border-t border-zinc-700/40 pt-2">
          <table
            data-testid="multi-cycle-cycle-table"
            className="w-full text-[10px] font-mono text-zinc-300"
          >
            <thead className="text-zinc-500">
              <tr>
                <th className="text-left py-1">#</th>
                <th className="text-left">Best PF</th>
                <th className="text-left">Avg PF</th>
                <th className="text-left">Generated</th>
                <th className="text-left">Saved</th>
                <th className="text-left">Scan</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((c, i) => (
                <tr
                  key={i}
                  data-testid={`multi-cycle-row-${c.cycle_index}`}
                  className="border-t border-zinc-800/60"
                >
                  <td className="py-1 text-zinc-400">{c.cycle_index}</td>
                  <td className="text-emerald-300">
                    {typeof c.best_pf === 'number' ? c.best_pf.toFixed(2) : '—'}
                  </td>
                  <td>{typeof c.avg_pf === 'number' ? c.avg_pf.toFixed(2) : '—'}</td>
                  <td>{c.strategies_generated ?? 0}</td>
                  <td className="text-emerald-300">{c.strategies_saved ?? 0}</td>
                  <td className="text-zinc-500 truncate">
                    {(c.scan || []).map((s) => `${s.pair}/${s.timeframe}`).join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Phase 21 — Best of Run highlight (current run) ─────── */}
      {status?.run_id && (completed || stopped) && (
        <BestStrategyHighlight
          runId={status.run_id}
          best={bestByRun[status.run_id]}
          loading={!!bestLoading[status.run_id]}
          onPromote={onPromoteClick}
          onGenerateCbot={onGenerateCbotClick}
          testIdPrefix="multi-cycle-current-best"
        />
      )}

      {/* ── Phase 21 — View Previous Runs drawer ─────────────────── */}
      <div className="border-t border-zinc-700/40 pt-2 mt-2">
        <button
          type="button"
          data-testid="multi-cycle-history-toggle"
          onClick={() => {
            const next = !historyOpen;
            setHistoryOpen(next);
            if (next && !history) fetchHistory();
          }}
          className="text-[11px] font-mono text-zinc-400 hover:text-accent-primary transition-colors"
        >
          {historyOpen ? '▼ Hide previous runs' : '▶ View previous runs'}
          {history?.count > 0 && (
            <span className="ml-2 text-zinc-600">({history.count})</span>
          )}
        </button>

        {historyOpen && (
          <div data-testid="multi-cycle-history-panel" className="mt-2">
            {historyLoading && (
              <div className="text-[10px] font-mono text-zinc-500 py-2">Loading…</div>
            )}
            {!historyLoading && history?.runs?.length === 0 && (
              <div className="text-[10px] font-mono text-zinc-500 py-2">
                No previous runs yet — completed runs will appear here.
              </div>
            )}
            {!historyLoading && history?.runs?.map((r) => (
              <HistoryRunRow
                key={r.run_id}
                run={r}
                best={bestByRun[r.run_id]}
                bestLoading={!!bestLoading[r.run_id]}
                onExpand={() => fetchBestForRun(r.run_id)}
                onPromote={onPromoteClick}
                onGenerateCbot={onGenerateCbotClick}
              />
            ))}
          </div>
        )}
      </div>

      {actionMsg && (
        <div
          data-testid="multi-cycle-action-msg"
          className="text-[11px] font-mono text-emerald-300 border-t border-zinc-700/40 pt-2 mt-2"
        >
          {actionMsg}
        </div>
      )}

      {error && (
        <div
          data-testid="multi-cycle-error"
          className="text-[11px] font-mono text-red-300 border-t border-zinc-700/40 pt-2 mt-2"
        >
          {error}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Tiny sparkline — pure SVG, no chart lib. Plots best avg_pf per cycle.
// ─────────────────────────────────────────────────────────────────────
function Sparkline({ values = [], width = 120, height = 24 }) {
  const series = (values || []).map((v) => (typeof v === 'number' ? v : null));
  const valid = series.filter((v) => v !== null);
  if (valid.length === 0) {
    return (
      <svg width={width} height={height} className="opacity-50">
        <line x1="0" y1={height / 2} x2={width} y2={height / 2}
              stroke="rgb(82,82,91)" strokeWidth="1" strokeDasharray="2 3" />
      </svg>
    );
  }
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const stepX = series.length > 1 ? width / (series.length - 1) : width;

  const pts = series.map((v, i) => {
    if (v === null) return null;
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y];
  }).filter(Boolean);

  const path = pts.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(' ');
  return (
    <svg
      width={width}
      height={height}
      data-testid="multi-cycle-sparkline"
      className="overflow-visible"
    >
      <path d={path} fill="none" stroke="rgb(52,211,153)" strokeWidth="1.5" />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="1.7" fill="rgb(52,211,153)" />
      ))}
    </svg>
  );
}


// ─────────────────────────────────────────────────────────────────────
// Phase 21 — Best-strategy highlight box.
// ─────────────────────────────────────────────────────────────────────
function BestStrategyHighlight({
  runId, best, loading, onPromote, onGenerateCbot, testIdPrefix,
}) {
  if (loading) {
    return (
      <div
        data-testid={`${testIdPrefix}-loading`}
        className="border-t border-zinc-700/40 pt-2 mt-2 text-[10px] font-mono text-zinc-500"
      >
        Loading best strategy for run {runId.slice(0, 8)}…
      </div>
    );
  }
  if (!best) return null;
  if (best.error) {
    return (
      <div className="border-t border-zinc-700/40 pt-2 mt-2 text-[10px] font-mono text-red-300">
        {best.error}
      </div>
    );
  }
  const s = best.best;
  if (!s) {
    return (
      <div
        data-testid={`${testIdPrefix}-empty`}
        className="border-t border-zinc-700/40 pt-2 mt-2 text-[10px] font-mono text-zinc-500"
      >
        No strategies were saved during run {runId.slice(0, 8)} — try
        lowering the eligibility threshold or running more cycles.
      </div>
    );
  }
  const score = typeof s.score === 'number' ? s.score.toFixed(1) : '—';
  const pp = typeof s.pass_probability === 'number' ? `${s.pass_probability.toFixed(0)}%` : '—';
  const stab = typeof s.stability_score === 'number' ? s.stability_score.toFixed(0) : '—';
  return (
    <div
      data-testid={testIdPrefix}
      className="border border-emerald-600/30 bg-emerald-500/5 rounded p-3 mt-3"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="text-[9px] font-mono uppercase tracking-wider text-emerald-400">
            Best of run · {runId.slice(0, 8)}
          </div>
          <div
            data-testid={`${testIdPrefix}-headline`}
            className="text-[12px] font-mono text-zinc-100 truncate"
            title={s.strategy_text}
          >
            {(s.strategy_type || 'strategy').toUpperCase()} ·{' '}
            {s.pair}/{s.timeframe}
            {s.style ? ` · ${s.style}` : ''}
          </div>
          <div className="text-[10px] font-mono text-zinc-400 mt-1">
            score {score} · pass-prob {pp} · stability {stab} ·{' '}
            <span className="text-zinc-500">{s.verdict || s.prop_status || '—'}</span>
            {best.candidates_considered > 1 && (
              <span className="text-zinc-600"> · {best.candidates_considered} candidates</span>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-1.5 shrink-0">
          <button
            type="button"
            data-testid={`${testIdPrefix}-promote`}
            onClick={() => onPromote(s)}
            className="text-[10px] font-mono px-2.5 py-1 rounded bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-300 transition-colors"
          >
            Promote to Dashboard
          </button>
          <button
            type="button"
            data-testid={`${testIdPrefix}-cbot`}
            onClick={() => onGenerateCbot(s)}
            className="text-[10px] font-mono px-2.5 py-1 rounded bg-zinc-800 hover:bg-accent-primary/15 border border-zinc-600 hover:border-accent-primary/50 text-zinc-200 hover:text-accent-primary transition-colors"
          >
            Generate cBot
          </button>
        </div>
      </div>
      {s.strategy_text && (
        <pre className="text-[10px] font-mono text-zinc-300 bg-zinc-950/60 rounded p-2 mt-1 overflow-x-auto whitespace-pre-wrap max-h-32">
          {s.strategy_text.length > 480 ? `${s.strategy_text.slice(0, 480)}…` : s.strategy_text}
        </pre>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────
// Phase 21 — One row in the "View Previous Runs" panel.
// ─────────────────────────────────────────────────────────────────────
function HistoryRunRow({ run, best, bestLoading, onExpand, onPromote, onGenerateCbot }) {
  const [open, setOpen] = useState(false);
  const totalSaved = (run.cycles || []).reduce(
    (acc, c) => acc + (c.strategies_saved || 0), 0,
  );
  const validPfs = (run.pf_trend || []).filter((p) => typeof p === 'number');
  const peakPf = validPfs.length ? Math.max(...validPfs).toFixed(2) : '—';
  const startedShort = (run.started_at || '').replace('T', ' ').slice(0, 19);

  const expand = () => {
    const next = !open;
    setOpen(next);
    if (next) onExpand();
  };

  return (
    <div
      data-testid={`multi-cycle-history-row-${run.run_id}`}
      className="border border-zinc-800 rounded mt-1 px-3 py-2 hover:border-zinc-700 transition-colors"
    >
      <button
        type="button"
        onClick={expand}
        className="w-full flex items-center justify-between gap-3 text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <Sparkline values={run.pf_trend || []} width={60} height={18} />
          <div className="text-[10px] font-mono text-zinc-300 truncate">
            <span className="text-zinc-500">{startedShort}</span>{' '}
            <span
              className={
                'ml-1 px-1.5 py-0.5 rounded text-[9px] ' +
                (run.status === 'completed'
                  ? 'bg-emerald-500/10 text-emerald-300'
                  : run.status === 'stopped'
                  ? 'bg-zinc-700 text-zinc-300'
                  : 'bg-red-500/10 text-red-300')
              }
            >
              {run.status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono shrink-0">
          <span className="text-emerald-300">peak {peakPf}</span>
          <span className="text-zinc-300">saved {totalSaved}</span>
          <span className="text-zinc-500">{open ? '▼' : '▶'}</span>
        </div>
      </button>

      {open && (
        <div className="mt-2 pt-2 border-t border-zinc-800">
          <BestStrategyHighlight
            runId={run.run_id}
            best={best}
            loading={bestLoading}
            onPromote={onPromote}
            onGenerateCbot={onGenerateCbot}
            testIdPrefix={`multi-cycle-history-best-${run.run_id}`}
          />
        </div>
      )}
    </div>
  );
}
