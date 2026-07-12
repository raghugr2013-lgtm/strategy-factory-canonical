import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Play, Stop, SkipForward, Spinner, CurrencyDollar, Shield,
  TrendUp, TrendDown, Warning, ChartLine, Globe,
} from '@phosphor-icons/react';
import {
  startTradeRunner, stepTradeRunner, stopTradeRunner,
  getTradeRunnerStatus, listTradeRunnerRuns,
  getPortfolioBuilderRecent,
} from '../services/api';
import { AsfKpiTile, AsfEmptyState, VerdictChip } from './ui-asf';

/**
 * Phase 5 — Trade Runner.
 *
 * Paper-execution layer for a saved Portfolio Builder snapshot.
 * Start / Step / Stop controls, equity + DD cards, per-strategy rollup,
 * and a live trade ticker. Isolated from the existing Execution tab.
 */

function fmt(n, d = 2) {
  if (n === null || n === undefined) return '—';
  return typeof n === 'number' ? n.toFixed(d) : String(n);
}

function StatusPill({ status, reason }) {
  const verdict =
    status === 'running' ? 'success' :
    status === 'halted'  ? 'danger'  :
    status === 'errored' ? 'warn'    :
    status === 'stopped' ? 'neutral' : 'neutral';
  const label = `${status || 'idle'}${reason ? ` · ${reason}` : ''}`;
  return (
    <VerdictChip
      testId="trade-runner-status-pill"
      verdict={verdict}
      label={label}
    />
  );
}

function MetricCard({ label, value, accent = 'zinc', suffix = '', testId }) {
  const cls = {
    zinc: 'text-zinc-100',
    primary: 'text-accent-primary',
    emerald: 'text-emerald-300',
    yellow: 'text-yellow-300',
    red: 'text-red-300',
  }[accent] || 'text-zinc-100';
  return (
    <div
      data-testid={testId}
      className="rounded border border-zinc-800 bg-[#121821] px-4 py-3"
    >
      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
        {label}
      </p>
      <p className={`text-xl font-bold mt-1 tabular-nums ${cls}`}>
        {value}
        {suffix && <span className="text-xs font-mono text-zinc-500 ml-1">{suffix}</span>}
      </p>
    </div>
  );
}

function DDBar({ pct, limit, color = 'red' }) {
  const p = Math.max(0, Math.min(100, (pct / limit) * 100));
  const bg = color === 'red' ? 'bg-red-400' : 'bg-yellow-400';
  return (
    <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
      <div className={`h-full ${bg}`} style={{ width: `${p}%` }} />
    </div>
  );
}

export default function TradeRunner() {
  const [runId, setRunId] = useState(null);
  const [run, setRun] = useState(null);
  const [trades, setTrades] = useState([]);
  const [portfolios, setPortfolios] = useState([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState('');
  const [accountBalance, setAccountBalance] = useState(10000);
  const [dailyLimit, setDailyLimit] = useState(5.0);
  const [totalLimit, setTotalLimit] = useState(10.0);
  const [rewardRatio, setRewardRatio] = useState(1.0);
  const [stepsPerTick, setStepsPerTick] = useState(5);
  const [auto, setAuto] = useState(false);
  const [loading, setLoading] = useState(null);   // 'start' | 'step' | 'stop'
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [recent, setRecent] = useState([]);
  const autoRef = useRef(null);

  const pushToast = (msg, kind = 'ok') => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  // Load saved portfolios for the selector
  const loadPortfolios = useCallback(async () => {
    try {
      const res = await getPortfolioBuilderRecent(20);
      setPortfolios(res.portfolios || []);
      if ((res.portfolios || []).length && !selectedPortfolioId) {
        setSelectedPortfolioId(res.portfolios[0].portfolio_id);
      }
    } catch {
      /* non-blocking */
    }
  }, [selectedPortfolioId]);

  const loadRecentRuns = useCallback(async () => {
    try {
      const res = await listTradeRunnerRuns(5);
      setRecent(res.runs || []);
    } catch {
      /* non-blocking */
    }
  }, []);

  useEffect(() => { loadPortfolios(); loadRecentRuns(); },
    [loadPortfolios, loadRecentRuns]);

  const refreshStatus = useCallback(async (id) => {
    if (!id) return;
    try {
      const s = await getTradeRunnerStatus(id, 25);
      setRun(s.run);
      setTrades(s.trades || []);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const start = async () => {
    setLoading('start'); setError(null);
    try {
      const payload = {
        portfolio_id: selectedPortfolioId || undefined,
        account_balance: Number(accountBalance),
        daily_loss_limit_pct: Number(dailyLimit),
        total_loss_limit_pct: Number(totalLimit),
        reward_ratio: Number(rewardRatio),
      };
      const res = await startTradeRunner(payload);
      setRunId(res.run.run_id);
      setRun(res.run);
      setTrades([]);
      pushToast(`Run started: ${res.run.run_id}`, 'ok');
    } catch (e) {
      setError(e.message || 'Start failed');
    } finally {
      setLoading(null);
    }
  };

  const step = useCallback(async () => {
    if (!runId) return;
    setLoading('step'); setError(null);
    try {
      const res = await stepTradeRunner(runId, Number(stepsPerTick));
      setRun(res.run);
      // Prepend newest trades (keep last 25 shown)
      setTrades((prev) => [...(res.executed || []).slice().reverse(), ...prev].slice(0, 25));
      if (res.run.status !== 'running') {
        setAuto(false);
        pushToast(`Run ${res.run.status}: ${res.run.halted_reason || 'user'}`, 'err');
      }
    } catch (e) {
      setError(e.message || 'Step failed');
      setAuto(false);
    } finally {
      setLoading(null);
    }
  }, [runId, stepsPerTick]);

  const stop = async () => {
    if (!runId) return;
    setLoading('stop'); setError(null);
    setAuto(false);
    try {
      const res = await stopTradeRunner(runId);
      setRun(res.run);
      pushToast('Run stopped', 'ok');
      await loadRecentRuns();
    } catch (e) {
      setError(e.message || 'Stop failed');
    } finally {
      setLoading(null);
    }
  };

  // Auto-step loop
  useEffect(() => {
    if (!auto || !runId || run?.status !== 'running') {
      if (autoRef.current) { clearInterval(autoRef.current); autoRef.current = null; }
      return undefined;
    }
    autoRef.current = setInterval(() => { step(); }, 1800);
    return () => { if (autoRef.current) clearInterval(autoRef.current); };
  }, [auto, runId, run?.status, step]);

  const status = run?.status || 'idle';
  const canStart = !runId || status === 'stopped' || status === 'halted';
  const canStep = runId && status === 'running';

  const equity = run?.equity ?? accountBalance;
  const pnl = run?.pnl ?? 0;
  const winRate = run && run.trades_count
    ? (run.wins_count / run.trades_count) * 100
    : null;

  const dailyLimitPct = run?.limits?.daily_loss_limit_pct ?? dailyLimit;
  const totalLimitPct = run?.limits?.total_loss_limit_pct ?? totalLimit;

  return (
    <div className="asf-section asf-u2-panel space-y-5" data-testid="trade-runner">
      {/* Header + controls */}
      <div className="asf-section__hd flex items-center justify-between flex-wrap gap-3">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <ChartLine size={20} className="text-accent-primary" weight="bold" />
            Trade Runner
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            Paper-execution runner for a saved Portfolio Builder snapshot.
            Uses SL-based sizing (<code className="text-zinc-300">risk_usd = balance × risk%</code>),
            enforces daily &amp; total DD limits, and halts on breach.
          </p>
        </div>
        <StatusPill status={status} reason={run?.halted_reason} />
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <button
            data-testid="trade-runner-start-btn"
            onClick={start}
            disabled={!canStart || loading === 'start'}
            className="text-xs font-semibold px-4 py-2 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-40 flex items-center gap-2"
          >
            {loading === 'start' ? <Spinner size={14} className="animate-spin" /> : <Play size={14} weight="fill" />}
            Start
          </button>
          <button
            data-testid="trade-runner-step-btn"
            onClick={step}
            disabled={!canStep || loading === 'step'}
            className="text-xs font-semibold px-3 py-2 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-40 flex items-center gap-2"
          >
            {loading === 'step' ? <Spinner size={14} className="animate-spin" /> : <SkipForward size={14} weight="fill" />}
            Step ×{stepsPerTick}
          </button>
          <label className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400 cursor-pointer">
            <input
              data-testid="trade-runner-auto-toggle"
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked && canStep)}
              disabled={!canStep}
              className="accent-accent-primary"
            />
            Auto
          </label>
          <button
            data-testid="trade-runner-stop-btn"
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
        className="rounded-md border border-zinc-800 bg-[#121821] p-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"
        data-testid="trade-runner-config"
      >
        <label className="flex flex-col gap-1 col-span-2">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Portfolio</span>
          <select
            data-testid="trade-runner-portfolio-select"
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
        {[
          ['accountBalance', 'Balance $', 100, 100, 10_000_000, accountBalance, setAccountBalance],
          ['dailyLimit', 'Daily DD %', 0.5, 0.5, 100, dailyLimit, setDailyLimit],
          ['totalLimit', 'Total DD %', 0.5, 0.5, 100, totalLimit, setTotalLimit],
          ['rewardRatio', 'R:R', 0.1, 0.1, 10, rewardRatio, setRewardRatio],
          ['stepsPerTick', 'Steps/Tick', 1, 1, 50, stepsPerTick, setStepsPerTick],
        ].map(([key, label, step, mn, mx, val, setter]) => (
          <label key={key} className="flex flex-col gap-1">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
            <input
              data-testid={`trade-runner-${key}`}
              type="number"
              step={step}
              min={mn}
              max={mx}
              value={val}
              onChange={(e) => setter(Number(e.target.value))}
              disabled={!canStart && ['accountBalance', 'dailyLimit', 'totalLimit', 'rewardRatio'].includes(key)}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 tabular-nums focus:outline-none focus:border-accent-primary/40 disabled:opacity-50"
            />
          </label>
        ))}
      </div>

      {error && (
        <AsfEmptyState
          slug="trade-runner-error"
          testId="trade-runner-error"
          title="Trade runner error"
          body={error}
          action={{ label: 'Dismiss', onClick: () => setError(null), testId: 'trade-runner-error-dismiss' }}
        />
      )}

      {/* Equity / DD metrics */}
      <div className="asf-kpi-grid" data-testid="trade-runner-metrics">
        <AsfKpiTile
          label="Equity"
          value={`$${fmt(equity)}`}
          verdict={pnl >= 0 ? 'success' : 'danger'}
          testId="metric-equity"
        />
        <AsfKpiTile
          label="PnL"
          value={`${pnl >= 0 ? '+' : ''}$${fmt(pnl)}`}
          verdict={pnl >= 0 ? 'success' : 'danger'}
          testId="metric-pnl"
        />
        <AsfKpiTile
          label="Trades"
          value={run?.trades_count ?? 0}
          verdict="info"
          testId="metric-trades"
        />
        <AsfKpiTile
          label="Win Rate"
          value={winRate !== null ? `${fmt(winRate, 1)}%` : '—'}
          verdict={winRate !== null && winRate >= 50 ? 'success' : 'warn'}
          testId="metric-winrate"
        />
        <AsfKpiTile
          label="Max DD"
          value={`${fmt(run?.max_drawdown_pct || 0, 2)}%`}
          verdict={(run?.max_drawdown_pct || 0) >= totalLimitPct * 0.8 ? 'danger' : 'warn'}
          testId="metric-maxdd"
        />
      </div>

      {/* DD progress bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="trade-runner-dd-bars">
        <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <Warning size={10} className="inline mr-1 text-yellow-400" />
              Daily Loss
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
              <Shield size={10} className="inline mr-1 text-red-400" />
              Total Loss
            </span>
            <span className="text-[11px] font-mono tabular-nums text-zinc-300">
              {fmt(run?.total_loss_pct || 0, 2)}% / {fmt(totalLimitPct)}%
            </span>
          </div>
          <DDBar pct={run?.total_loss_pct || 0} limit={totalLimitPct} color="red" />
        </div>
      </div>

      {/* Per-strategy status */}
      <div
        className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden"
        data-testid="trade-runner-strategies"
      >
        <div className="px-3 py-2 bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Strategies ({(run?.strategies || []).length})
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Name</th>
              <th className="text-left px-3 py-2">Env</th>
              <th className="text-right px-3 py-2">Risk</th>
              <th className="text-right px-3 py-2">WR (exp)</th>
              <th className="text-right px-3 py-2">Trades</th>
              <th className="text-right px-3 py-2">W / L</th>
              <th className="text-right px-3 py-2">PnL</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {!run && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-zinc-500 font-mono text-xs" data-testid="trade-runner-empty">
                  Click <strong>Start</strong> to load a portfolio and begin paper execution.
                </td>
              </tr>
            )}
            {(run?.strategies || []).map((s) => (
              <tr
                key={s.strategy_hash}
                data-testid={`trade-runner-strategy-${s.strategy_hash}`}
                className="hover:bg-zinc-900/40 transition-colors"
              >
                <td className="px-3 py-2">
                  <p className="font-medium text-zinc-200">{s.strategy_name || '—'}</p>
                  <p className="text-[9px] font-mono text-zinc-500">
                    {s.firm_slug || '—'} · PF {fmt(s.pf)}
                  </p>
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-zinc-200">
                    <Globe size={11} className="text-accent-primary" />
                    {s.pair} · {s.timeframe}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-accent-primary">
                  {fmt(s.risk_pct, 2)}%
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">
                  {fmt((s.win_rate || 0) * 100, 1)}%
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-200">
                  {s.trades}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  <span className="text-emerald-400">{s.wins}</span>
                  <span className="text-zinc-600 mx-0.5">/</span>
                  <span className="text-red-400">{s.losses}</span>
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono tabular-nums ${
                    s.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'
                  }`}
                >
                  {s.pnl >= 0 ? '+' : ''}${fmt(s.pnl, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recent trades ticker */}
      <div
        className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden"
        data-testid="trade-runner-trades"
      >
        <div className="px-3 py-2 bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Recent Trades ({trades.length})
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Time</th>
              <th className="text-left px-3 py-2">Strategy · Pair</th>
              <th className="text-left px-3 py-2">Dir</th>
              <th className="text-right px-3 py-2">Lot</th>
              <th className="text-right px-3 py-2">SL pips</th>
              <th className="text-right px-3 py-2">Risk $</th>
              <th className="text-right px-3 py-2">PnL</th>
              <th className="text-right px-3 py-2">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {trades.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-zinc-500 font-mono text-xs">
                  No trades yet. Step the runner to execute rounds.
                </td>
              </tr>
            )}
            {trades.map((t, i) => (
              <tr
                key={`${t.executed_at}-${i}`}
                className="hover:bg-zinc-900/40 transition-colors"
              >
                <td className="px-3 py-2 font-mono text-[10px] text-zinc-500 tabular-nums">
                  {new Date(t.executed_at).toLocaleTimeString()}
                </td>
                <td className="px-3 py-2">
                  <p className="font-medium text-zinc-200 text-xs">{t.strategy_name || '—'}</p>
                  <p className="text-[9px] font-mono text-zinc-500">{t.pair} · {t.timeframe}</p>
                </td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] font-mono font-bold ${
                    t.direction === 'BUY' ? 'text-emerald-300' : 'text-red-300'
                  }`}>
                    {t.direction === 'BUY'
                      ? <TrendUp size={10} className="inline mr-0.5" />
                      : <TrendDown size={10} className="inline mr-0.5" />}
                    {t.direction}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">{fmt(t.lot_size, 3)}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-400">{fmt(t.sl_pips, 0)}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-zinc-300">
                  <CurrencyDollar size={9} className="inline text-zinc-500" />{fmt(t.risk_usd, 2)}
                </td>
                <td className={`px-3 py-2 text-right font-mono tabular-nums ${
                  t.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'
                }`}>
                  {t.pnl >= 0 ? '+' : ''}${fmt(t.pnl, 2)}
                </td>
                <td className="px-3 py-2 text-right">
                  <span className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${
                    t.result === 'WIN'
                      ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                      : 'bg-red-500/10 border-red-500/40 text-red-300'
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
        <div
          className="rounded-md border border-zinc-800 bg-[#121821] p-3"
          data-testid="trade-runner-recent"
        >
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2">
            Recent runs
          </p>
          <ul className="space-y-1 text-[11px] font-mono text-zinc-400">
            {recent.map((r) => (
              <li
                key={r.run_id}
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
          data-testid="trade-runner-toast"
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
