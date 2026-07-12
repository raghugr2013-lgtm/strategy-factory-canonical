import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Play, Stop, Spinner, Shield, Warning, ChartLineUp,
  TrendUp, TrendDown, ArrowsHorizontal, Pulse, Lightning, Target,
} from '@phosphor-icons/react';
import {
  startPaperExecution, stopPaperExecution, getPaperExecutionStatus,
  listPaperExecutionRuns, getPortfolioBuilderRecent,
} from '../services/api';
import { AsfKpiTile, AsfEmptyState, VerdictChip } from './ui-asf';

/**
 * Phase Safe-Execution — Paper Execution tab.
 *
 * Replays historical BID/BI5 bars through a portfolio-approved set of
 * strategies and simulates trades. Tracks:
 *   • Running equity curve
 *   • Expected-vs-actual entry deviation (per trade)
 *   • Running PF vs backtest PF (per strategy)
 *
 * Hard DD halts are enforced — this is a SAFE step before real execution.
 */

// ───────── Helpers ─────────
function fmt(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return typeof n === 'number' ? n.toFixed(d) : String(n);
}
function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

// ───────── Sparkline ─────────
function EquitySparkline({ points, height = 90, accent = 'emerald' }) {
  if (!points || points.length < 2) {
    return (
      <div
        data-testid="paper-exec-equity-empty"
        className="flex items-center justify-center rounded border border-zinc-800 bg-[#0E131A] text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-600"
        style={{ height }}
      >
        waiting for ticks…
      </div>
    );
  }
  const xs = points.map((_, i) => i);
  const ys = points.map((p) => p.equity);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const w = 600, h = height, pad = 6;
  const sx = (x) => pad + ((x - xMin) / Math.max(1, xMax - xMin)) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - yMin) / Math.max(1e-6, yMax - yMin)) * (h - 2 * pad);
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(i).toFixed(1)} ${sy(p.equity).toFixed(1)}`)
    .join(' ');
  const area = `${d} L ${sx(xs[xs.length - 1]).toFixed(1)} ${h - pad} L ${sx(xs[0]).toFixed(1)} ${h - pad} Z`;
  const strokeColor = accent === 'emerald' ? '#34d399' : '#f87171';
  const fillColor = accent === 'emerald' ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)';
  return (
    <svg
      data-testid="paper-exec-equity-curve"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="w-full rounded border border-zinc-800 bg-[#0E131A]"
      style={{ height }}
    >
      <path d={area} fill={fillColor} />
      <path d={d} stroke={strokeColor} strokeWidth="1.6" fill="none" />
    </svg>
  );
}

// ───────── Status pill (U-2 — VerdictChip-backed) ─────────
function StatusPill({ status, reason }) {
  const verdict =
    status === 'running' ? 'success' :
    status === 'halted'  ? 'danger'  :
    status === 'errored' ? 'warn'    :
    status === 'stopped' ? 'neutral' :
    'neutral';
  const label = `${status || 'idle'}${reason ? ` · ${reason}` : ''}`;
  return (
    <VerdictChip
      testId="paper-exec-status-pill"
      verdict={verdict}
      label={label}
    />
  );
}

function MetricCard({ label, value, accent = 'zinc', suffix = '', testId }) {
  const cls = {
    zinc: 'text-zinc-100', primary: 'text-accent-primary',
    emerald: 'text-emerald-300', yellow: 'text-yellow-300', red: 'text-red-300',
  }[accent] || 'text-zinc-100';
  return (
    <div data-testid={testId} className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</p>
      <p className={`text-xl font-bold mt-1 tabular-nums ${cls}`}>
        {value}{suffix && <span className="text-xs font-mono text-zinc-500 ml-1">{suffix}</span>}
      </p>
    </div>
  );
}

function DDBar({ pct, limit, color = 'red' }) {
  const p = clamp((pct / Math.max(0.01, limit)) * 100, 0, 100);
  const bg = color === 'red' ? 'bg-red-400' : 'bg-yellow-400';
  return (
    <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
      <div className={`h-full ${bg}`} style={{ width: `${p}%` }} />
    </div>
  );
}

// ─────────────────── Main component ───────────────────
export default function PaperExecution() {
  const [runId, setRunId] = useState(null);
  const [run, setRun] = useState(null);
  const [trades, setTrades] = useState([]);
  const [equityCurve, setEquityCurve] = useState([]);
  const [portfolios, setPortfolios] = useState([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState('');
  const [accountBalance, setAccountBalance] = useState(10000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [dailyLimit, setDailyLimit] = useState(5.0);
  const [totalLimit, setTotalLimit] = useState(10.0);
  const [tickMs, setTickMs] = useState(100);
  const [barsLimit, setBarsLimit] = useState(2000);
  const [source, setSource] = useState('bid_1m');
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [recent, setRecent] = useState([]);
  const pollRef = useRef(null);

  const pushToast = (msg, kind = 'ok') => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  const loadPortfolios = useCallback(async () => {
    try {
      const res = await getPortfolioBuilderRecent(20);
      setPortfolios(res.portfolios || []);
      if ((res.portfolios || []).length && !selectedPortfolioId) {
        setSelectedPortfolioId(res.portfolios[0].portfolio_id);
      }
    } catch { /* non-blocking */ }
  }, [selectedPortfolioId]);

  const loadRecentRuns = useCallback(async () => {
    try {
      const res = await listPaperExecutionRuns(5);
      setRecent(res.runs || []);
    } catch { /* non-blocking */ }
  }, []);

  const refreshStatus = useCallback(async (id) => {
    try {
      const s = await getPaperExecutionStatus(id, 25);
      setRun(s.active);
      setTrades(s.trades || []);
      setEquityCurve(s.equity_curve || []);
      if (s.active && s.active.run_id) setRunId(s.active.run_id);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadPortfolios();
    loadRecentRuns();
    refreshStatus();
  }, [loadPortfolios, loadRecentRuns, refreshStatus]);

  // Polling while run is active
  useEffect(() => {
    const activeStatus = run?.status;
    if (activeStatus === 'running' && runId) {
      pollRef.current = setInterval(() => { refreshStatus(runId); }, 1000);
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [run?.status, runId, refreshStatus]);

  const start = async () => {
    setLoading('start'); setError(null);
    try {
      const payload = {
        portfolio_id: selectedPortfolioId || undefined,
        account_balance: Number(accountBalance),
        risk_pct: Number(riskPct),
        daily_loss_limit_pct: Number(dailyLimit),
        total_loss_limit_pct: Number(totalLimit),
        tick_ms: Number(tickMs),
        bars_limit: Number(barsLimit),
        source,
      };
      const res = await startPaperExecution(payload);
      setRunId(res.run.run_id);
      setRun(res.run);
      setTrades([]);
      setEquityCurve([]);
      pushToast(`Run started: ${res.run.run_id}`, 'ok');
      setTimeout(() => refreshStatus(res.run.run_id), 400);
      loadRecentRuns();
    } catch (e) {
      setError(e.message || 'Start failed');
    } finally {
      setLoading(null);
    }
  };

  const stop = async () => {
    if (!runId) return;
    setLoading('stop'); setError(null);
    try {
      const res = await stopPaperExecution(runId);
      setRun(res.run);
      pushToast('Run stopped', 'ok');
      await loadRecentRuns();
    } catch (e) {
      setError(e.message || 'Stop failed');
    } finally {
      setLoading(null);
    }
  };

  const status = run?.status || 'idle';
  const canStart = !runId || status === 'stopped' || status === 'halted' || status === 'errored';
  const equity = run?.equity ?? accountBalance;
  const pnl = run?.pnl ?? 0;
  const winRate = run && run.trades_count
    ? ((run.strategies || []).reduce((acc, s) => acc + (s.wins || 0), 0) / run.trades_count) * 100
    : null;
  const dailyLimitPct = run?.limits?.daily_loss_limit_pct ?? dailyLimit;
  const totalLimitPct = run?.limits?.total_loss_limit_pct ?? totalLimit;

  // Format PF deviation nicely (clamp extreme values)
  const fmtDev = (v) => {
    if (v === null || v === undefined) return '—';
    if (v > 999) return '+999%+';
    if (v < -999) return '−999%+';
    return `${v >= 0 ? '+' : ''}${fmt(v, 1)}%`;
  };
  const devAccent = (v) => {
    if (v === null || v === undefined) return 'text-zinc-400';
    if (v >= 0) return 'text-emerald-300';
    if (v >= -25) return 'text-yellow-300';
    return 'text-red-300';
  };

  return (
    <div className="asf-section asf-u2-panel" data-testid="paper-execution">
      {/* Header (legacy title hidden when wrapped). */}
      <div className="asf-section__hd">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <Lightning size={20} className="text-accent-primary" weight="bold" />
            Paper Execution
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            Safe historical-replay runner. Uses portfolio-approved strategies against
            BID/BI5 bars with SL/TP enforcement, running PF vs backtest PF comparison,
            and per-trade entry-deviation tracking. Hard-halts on DD breach.
          </p>
        </div>
        <StatusPill status={status} reason={run?.halted_reason} />
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button
            data-testid="paper-exec-start-btn"
            onClick={start}
            disabled={!canStart || loading === 'start'}
            className="text-xs font-semibold px-4 py-2 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-40 flex items-center gap-2"
          >
            {loading === 'start' ? <Spinner size={14} className="animate-spin" /> : <Play size={14} weight="fill" />}
            Start
          </button>
          <button
            data-testid="paper-exec-stop-btn"
            onClick={stop}
            disabled={!runId || status !== 'running' || loading === 'stop'}
            className="text-xs font-semibold px-3 py-2 rounded border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300 disabled:opacity-40 flex items-center gap-2"
          >
            {loading === 'stop' ? <Spinner size={14} className="animate-spin" /> : <Stop size={14} weight="fill" />}
            Stop
          </button>
        </div>
      </div>

      {/* Config panel */}
      <div
        className="rounded-md border border-zinc-800 bg-[#121821] p-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-8 gap-3"
        data-testid="paper-exec-config"
      >
        <label className="flex flex-col gap-1 col-span-2">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Portfolio</span>
          <select
            data-testid="paper-exec-portfolio-select"
            value={selectedPortfolioId}
            onChange={(e) => setSelectedPortfolioId(e.target.value)}
            disabled={!canStart}
            className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-accent-primary/40 disabled:opacity-50"
          >
            <option value="">— latest saved —</option>
            {portfolios.map((p) => {
              const strat = p.meta?.selected_count ?? p.meta?.strategies?.length ?? '?';
              return (
                <option key={p.portfolio_id} value={p.portfolio_id}>
                  {new Date(p.saved_at).toLocaleString()} · {strat} strat
                </option>
              );
            })}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Source</span>
          <select
            data-testid="paper-exec-source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            disabled={!canStart}
            className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-accent-primary/40 disabled:opacity-50"
          >
            <option value="bid_1m">BID 1m</option>
            <option value="bi5">BI5 tick</option>
          </select>
        </label>
        {[
          ['accountBalance', 'Balance $', 100, 100, 10_000_000, accountBalance, setAccountBalance],
          ['riskPct', 'Risk %', 0.1, 0.1, 10, riskPct, setRiskPct],
          ['dailyLimit', 'Daily DD %', 0.5, 0.5, 100, dailyLimit, setDailyLimit],
          ['totalLimit', 'Total DD %', 0.5, 0.5, 100, totalLimit, setTotalLimit],
          ['tickMs', 'Tick ms', 5, 5, 10000, tickMs, setTickMs],
          ['barsLimit', 'Bars', 100, 100, 20000, barsLimit, setBarsLimit],
        ].map(([key, label, step, mn, mx, val, setter]) => (
          <label key={key} className="flex flex-col gap-1">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
            <input
              data-testid={`paper-exec-${key}`}
              type="number"
              step={step}
              min={mn}
              max={mx}
              value={val}
              onChange={(e) => setter(Number(e.target.value))}
              disabled={!canStart}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 tabular-nums focus:outline-none focus:border-accent-primary/40 disabled:opacity-50"
            />
          </label>
        ))}
      </div>

      {error && (
        <AsfEmptyState
          slug="paper-exec-error"
          testId="paper-exec-error"
          title="Paper execution error"
          body={error}
          action={{ label: 'Dismiss', onClick: () => setError(null), testId: 'paper-exec-error-dismiss' }}
        />
      )}

      {/* Equity + metrics (U-2 AsfKpiTile). */}
      <div className="asf-kpi-grid" data-testid="paper-exec-metrics">
        <AsfKpiTile
          label="Equity"
          value={`$${fmt(equity)}`}
          verdict={pnl >= 0 ? 'success' : 'danger'}
          testId="pe-metric-equity"
        />
        <AsfKpiTile
          label="PnL"
          value={`${pnl >= 0 ? '+' : ''}$${fmt(pnl)}`}
          verdict={pnl >= 0 ? 'success' : 'danger'}
          testId="pe-metric-pnl"
        />
        <AsfKpiTile
          label="Trades"
          value={run?.trades_count ?? 0}
          verdict="info"
          testId="pe-metric-trades"
        />
        <AsfKpiTile
          label="Win Rate"
          value={winRate !== null ? `${fmt(winRate, 1)}%` : '—'}
          verdict={winRate !== null && winRate >= 50 ? 'success' : 'warn'}
          testId="pe-metric-winrate"
        />
        <AsfKpiTile
          label="Max DD"
          value={`${fmt(run?.max_drawdown_pct || 0, 2)}%`}
          verdict={(run?.max_drawdown_pct || 0) >= totalLimitPct * 0.8 ? 'danger' : 'warn'}
          testId="pe-metric-maxdd"
        />
      </div>

      {/* Equity curve */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] p-3" data-testid="paper-exec-equity-panel">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 flex items-center gap-1">
            <ChartLineUp size={11} className="text-accent-primary" />
            Equity Curve ({equityCurve.length} ticks)
          </span>
          <span className="text-[10px] font-mono tabular-nums text-zinc-400">
            {equityCurve.length > 0
              ? `$${fmt(equityCurve[0].equity)} → $${fmt(equityCurve[equityCurve.length - 1].equity)}`
              : '—'}
          </span>
        </div>
        <EquitySparkline points={equityCurve} accent={pnl >= 0 ? 'emerald' : 'red'} />
      </div>

      {/* DD bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="paper-exec-dd-bars">
        <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <Warning size={10} className="inline mr-1 text-yellow-400" /> Daily Loss
            </span>
            <span className="text-[11px] font-mono tabular-nums text-zinc-300">
              {fmt(run?.daily_loss_pct || 0, 2)}% / {fmt(dailyLimitPct)}%
            </span>
          </div>
          <DDBar pct={run?.daily_loss_pct || 0} limit={dailyLimitPct} color="yellow" />
        </div>
        <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <Shield size={10} className="inline mr-1 text-red-400" /> Total Loss
            </span>
            <span className="text-[11px] font-mono tabular-nums text-zinc-300">
              {fmt(run?.total_loss_pct || 0, 2)}% / {fmt(totalLimitPct)}%
            </span>
          </div>
          <DDBar pct={run?.total_loss_pct || 0} limit={totalLimitPct} color="red" />
        </div>
      </div>

      {/* Strategies table */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden" data-testid="paper-exec-strategies">
        <div className="px-3 py-2 bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 flex items-center justify-between">
          <span>Strategies ({(run?.strategies || []).length})</span>
          <span className="text-zinc-600">
            <Target size={10} className="inline mr-1" /> running PF vs backtest PF
          </span>
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">Pair</th>
              <th className="text-right px-3 py-2">Risk</th>
              <th className="text-right px-3 py-2">Trades</th>
              <th className="text-right px-3 py-2">W / L</th>
              <th className="text-right px-3 py-2">PnL</th>
              <th className="text-right px-3 py-2">Run PF</th>
              <th className="text-right px-3 py-2">BT PF</th>
              <th className="text-right px-3 py-2">PF Dev</th>
              <th className="text-right px-3 py-2">Avg Entry Dev</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {!run && (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-zinc-500 font-mono text-xs" data-testid="paper-exec-empty">
                  Click <strong>Start</strong> to load an approved portfolio and begin paper execution.
                </td>
              </tr>
            )}
            {(run?.strategies || []).map((s) => (
              <tr
                key={s.strategy_hash}
                data-testid={`paper-exec-strategy-${s.strategy_hash}`}
                className="hover:bg-zinc-900/40 transition-colors"
              >
                <td className="px-3 py-2">
                  <p className="font-medium text-zinc-200">{s.strategy_name || '—'}</p>
                  <p className="text-[9px] font-mono text-zinc-500">{s.style}</p>
                </td>
                <td className="px-3 py-2 font-mono text-xs text-zinc-200">
                  {s.pair} · {s.timeframe}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-accent-primary">
                  {fmt(s.risk_pct, 2)}%
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-200">{s.trades}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  <span className="text-emerald-400">{s.wins}</span>
                  <span className="text-zinc-600 mx-0.5">/</span>
                  <span className="text-red-400">{s.losses}</span>
                </td>
                <td className={`px-3 py-2 text-right font-mono tabular-nums ${s.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                  {s.pnl >= 0 ? '+' : ''}${fmt(s.pnl, 2)}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">
                  {fmt(s.running_pf, 2)}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-400">
                  {fmt(s.backtest_pf, 2)}
                </td>
                <td className={`px-3 py-2 text-right font-mono tabular-nums ${devAccent(s.pf_deviation_pct)}`}>
                  {fmtDev(s.pf_deviation_pct)}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">
                  <ArrowsHorizontal size={9} className="inline text-zinc-500 mr-0.5" />
                  {fmt(s.avg_entry_deviation_pips, 2)} p
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Trade ticker */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden" data-testid="paper-exec-trades">
        <div className="px-3 py-2 bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          <Pulse size={10} className="inline mr-1 text-accent-primary" />
          Recent Trades ({trades.length})
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Strategy · Pair</th>
              <th className="text-left px-3 py-2">Dir</th>
              <th className="text-right px-3 py-2">Exp Entry</th>
              <th className="text-right px-3 py-2">Act Entry</th>
              <th className="text-right px-3 py-2">Dev (p)</th>
              <th className="text-right px-3 py-2">SL / TP</th>
              <th className="text-right px-3 py-2">Exit</th>
              <th className="text-right px-3 py-2">PnL</th>
              <th className="text-right px-3 py-2">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {trades.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-6 text-center text-zinc-500 font-mono text-xs">
                  No trades yet. Start the runner to generate simulated fills.
                </td>
              </tr>
            )}
            {trades.map((t, i) => (
              <tr key={`${t.executed_at}-${i}`} className="hover:bg-zinc-900/40 transition-colors">
                <td className="px-3 py-2">
                  <p className="font-medium text-zinc-200">{t.strategy_name || '—'}</p>
                  <p className="text-[9px] font-mono text-zinc-500">{t.pair} · {t.timeframe}</p>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] font-mono font-bold ${t.direction === 'BUY' ? 'text-emerald-300' : 'text-red-300'}`}>
                    {t.direction === 'BUY' ? <TrendUp size={10} className="inline mr-0.5" /> : <TrendDown size={10} className="inline mr-0.5" />}
                    {t.direction}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-400">
                  {fmt(t.expected_entry, 5)}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-200">
                  {fmt(t.actual_entry, 5)}
                </td>
                <td className={`px-3 py-2 text-right font-mono tabular-nums ${
                  Math.abs(t.deviation_pips || 0) <= 1 ? 'text-zinc-400' : 'text-yellow-300'
                }`}>
                  {(t.deviation_pips || 0) >= 0 ? '+' : ''}{fmt(t.deviation_pips, 2)}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-[10px]">
                  <span className="text-red-400">{fmt(t.sl_price, 5)}</span>
                  <span className="text-zinc-600 mx-0.5">/</span>
                  <span className="text-emerald-400">{fmt(t.tp_price, 5)}</span>
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300 text-[10px]">
                  {fmt(t.exit_price, 5)}
                  <span className="text-zinc-600 ml-1">({t.exit_reason})</span>
                </td>
                <td className={`px-3 py-2 text-right font-mono tabular-nums ${t.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                  {t.pnl >= 0 ? '+' : ''}${fmt(t.pnl, 2)}
                </td>
                <td className="px-3 py-2 text-right">
                  <span className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${
                    t.result === 'WIN'
                      ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                      : t.result === 'LOSS'
                        ? 'bg-red-500/10 border-red-500/40 text-red-300'
                        : 'bg-zinc-500/10 border-zinc-600/40 text-zinc-300'
                  }`}>
                    {t.result}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Run history */}
      {recent.length > 0 && (
        <div className="rounded-md border border-zinc-800 bg-[#121821] p-3" data-testid="paper-exec-recent">
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2">
            Recent runs
          </p>
          <ul className="space-y-1 text-[11px] font-mono text-zinc-400">
            {recent.map((r) => (
              <li
                key={r.run_id}
                data-testid={`paper-exec-recent-${r.run_id}`}
                className="flex items-center justify-between px-2 py-1 rounded bg-zinc-900/40 cursor-pointer hover:bg-zinc-900/70"
                onClick={() => { setRunId(r.run_id); refreshStatus(r.run_id); }}
              >
                <span className="flex items-center gap-2">
                  <StatusPill status={r.status} reason={r.halted_reason} />
                  <span className="text-zinc-500">
                    {new Date(r.started_at).toLocaleString()}
                  </span>
                </span>
                <span>
                  eq <span className="text-zinc-200">${fmt(r.equity)}</span> ·
                  pnl <span className={r.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}>
                    {r.pnl >= 0 ? '+' : ''}${fmt(r.pnl)}
                  </span> ·
                  trades <span className="text-zinc-200">{r.trades_count}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {toast && (
        <div
          data-testid="paper-exec-toast"
          className={`fixed bottom-4 right-4 z-50 text-xs font-medium px-3 py-2 rounded border shadow-lg max-w-sm ${
            toast.kind === 'err'
              ? 'bg-red-500/10 border-red-500/30 text-red-300'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          }`}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
