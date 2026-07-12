import React, { useState, useMemo } from 'react';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts';
import { X, TrendUp, Gauge, ChartLine, Coins, Target } from '@phosphor-icons/react';
import StrategyChartView from './StrategyChartView';
import FirmMatchPanel from './FirmMatchPanel';

/**
 * Phase 7.5 — Strategy Deep Dive Panel
 *
 * Pure composition over the existing report + viz primitives.
 * All data comes from the backtest response — no recomputation of
 * trades, summary, equity, drawdown, or execution costs.
 *
 * Layout:
 *   Top   → Summary metrics   (from report.summary)
 *   Mid   → StrategyChartView (reused as-is)
 *   Bottom→ Tabs: Trades | Risk | Execution
 */
export default function StrategyDeepDivePanel({ result, onClose }) {
  const [tab, setTab] = useState('trades');

  const report = result?.report || {};
  const summary = report.summary || {};
  const trades = report.trades || [];
  const equityCurve = report.equity_curve || [];
  const drawdownCurve = report.drawdown_curve || [];
  const execution = result?.execution_summary || { enabled: false, total_spread_cost: 0, total_slippage_cost: 0, total_commission: 0, total_execution_cost: 0 };

  // Simple risk roll-up: avg drawdown over the drawdown curve
  // (drawdown_curve already contains non-negative peak-to-equity drops).
  const avgDrawdown = useMemo(() => {
    if (!drawdownCurve.length) return 0;
    const s = drawdownCurve.reduce((a, b) => a + Number(b || 0), 0);
    return s / drawdownCurve.length;
  }, [drawdownCurve]);

  return (
    <div data-testid="strategy-deep-dive-panel" className="flex flex-col h-full bg-zinc-950">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Gauge size={16} weight="bold" className="text-emerald-500" />
          <h3 className="text-sm font-semibold text-white">Strategy Deep Dive</h3>
          {result?.pair && (
            <span className="text-[11px] font-mono text-zinc-500">
              {result.pair} · {result.timeframe}
              {result?.data_points ? ` · ${result.data_points} bars` : ''}
            </span>
          )}
        </div>
        {onClose && (
          <button
            data-testid="deep-dive-close-btn"
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800"
          >
            <X size={16} weight="bold" />
          </button>
        )}
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-auto">
        {/* ── TOP: Summary metrics ─────────────────────────── */}
        <div className="p-4" data-testid="deep-dive-summary">
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <MetricTile
              testId="dd-metric-net-profit"
              label="Net Profit"
              value={`${summary.net_profit >= 0 ? '+' : ''}$${Number(summary.net_profit ?? 0).toFixed(2)}`}
              tone={summary.net_profit >= 0 ? 'good' : 'bad'}
            />
            <MetricTile
              testId="dd-metric-max-dd"
              label="Max Drawdown"
              value={`$${Number(summary.max_drawdown ?? 0).toFixed(2)}`}
              tone="bad"
            />
            <MetricTile
              testId="dd-metric-profit-factor"
              label="Profit Factor"
              value={summary.profit_factor == null ? 'n/a' : Number(summary.profit_factor).toFixed(2)}
              tone={summary.profit_factor && summary.profit_factor >= 1 ? 'good' : 'bad'}
            />
            <MetricTile
              testId="dd-metric-win-rate"
              label="Win Rate"
              value={`${Number(summary.win_rate ?? 0).toFixed(1)}%`}
              tone={summary.win_rate >= 50 ? 'good' : 'bad'}
            />
            <MetricTile
              testId="dd-metric-total-trades"
              label="Total Trades"
              value={String(summary.total_trades ?? 0)}
              tone="neutral"
            />
          </div>
        </div>

        {/* ── MIDDLE: Chart (reused) ───────────────────────── */}
        <div className="h-[560px] border-t border-zinc-800" data-testid="deep-dive-chart-slot">
          <StrategyChartView report={report} prices={result?.prices} />
        </div>

        {/* ── BOTTOM: Tabs ─────────────────────────────────── */}
        <div className="border-t border-zinc-800" data-testid="deep-dive-tabs">
          <div className="flex items-center gap-1 px-2 pt-2 border-b border-zinc-800">
            <TabButton active={tab === 'trades'} onClick={() => setTab('trades')}
              testId="tab-trades" icon={<ChartLine size={12} weight="bold" />}>Trades</TabButton>
            <TabButton active={tab === 'risk'} onClick={() => setTab('risk')}
              testId="tab-risk" icon={<TrendUp size={12} weight="bold" />}>Risk</TabButton>
            <TabButton active={tab === 'execution'} onClick={() => setTab('execution')}
              testId="tab-execution" icon={<Coins size={12} weight="bold" />}>Execution</TabButton>
            <TabButton active={tab === 'firm-match'} onClick={() => setTab('firm-match')}
              testId="tab-firm-match" icon={<Target size={12} weight="bold" />}>Firm Match</TabButton>
          </div>

          <div className="p-4">
            {tab === 'trades' && <TradesTab trades={trades} />}
            {tab === 'risk' && (
              <RiskTab
                summary={summary}
                avgDrawdown={avgDrawdown}
                equityCurve={equityCurve}
                drawdownCurve={drawdownCurve}
              />
            )}
            {tab === 'execution' && <ExecutionTab execution={execution} />}
            {tab === 'firm-match' && (
              <FirmMatchPanel
                variant="full"
                trades={trades}
                pair={result?.pair}
                timeframe={result?.timeframe}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════

function MetricTile({ label, value, tone, testId }) {
  const color =
    tone === 'good' ? 'text-emerald-400'
    : tone === 'bad' ? 'text-red-400'
    : 'text-white';
  const dotColor =
    tone === 'good' ? 'bg-emerald-500'
    : tone === 'bad' ? 'bg-red-500'
    : 'bg-zinc-500';
  return (
    <div data-testid={testId} className="bg-zinc-900 border border-zinc-800 rounded-md p-3">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`} />
        <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">{label}</p>
      </div>
      <p className={`text-xl font-bold font-mono tracking-tight ${color}`}>{value}</p>
    </div>
  );
}

function TabButton({ active, onClick, children, icon, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-2 text-[11px] font-mono font-medium border-b-2 transition-colors ${
        active
          ? 'border-emerald-500 text-emerald-400'
          : 'border-transparent text-zinc-400 hover:text-white'
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

// ── Tab: Trades ──────────────────────────────────────────────────
function TradesTab({ trades }) {
  if (!trades.length) {
    return <p className="text-[11px] font-mono text-zinc-500 p-2">No trades in report.</p>;
  }
  return (
    <div className="max-h-[360px] overflow-auto border border-zinc-800 rounded-md"
         data-testid="tab-trades-table">
      <table className="w-full text-[11px] font-mono">
        <thead className="bg-zinc-900 text-zinc-400 sticky top-0">
          <tr>
            <th className="text-left px-3 py-2 font-medium">#</th>
            <th className="text-left px-3 py-2 font-medium">Entry</th>
            <th className="text-left px-3 py-2 font-medium">Dir</th>
            <th className="text-right px-3 py-2 font-medium">Entry Px</th>
            <th className="text-right px-3 py-2 font-medium">Exit Px</th>
            <th className="text-left px-3 py-2 font-medium">Out</th>
            <th className="text-right px-3 py-2 font-medium">MAE (pips)</th>
            <th className="text-right px-3 py-2 font-medium">MFE (pips)</th>
            <th className="text-right px-3 py-2 font-medium">R</th>
            <th className="text-right px-3 py-2 font-medium">Net PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, idx) => {
            const dir = (t.direction || t.side || '').toUpperCase();
            const out = (t.outcome || t.result || '').toUpperCase();
            return (
              <tr key={idx} className="border-t border-zinc-900">
                <td className="px-3 py-1.5 text-zinc-500">{idx + 1}</td>
                <td className="px-3 py-1.5 text-zinc-300">{String(t.entry_time ?? '-')}</td>
                <td className={`px-3 py-1.5 font-semibold ${dir === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                  {dir || '-'}
                </td>
                <td className="px-3 py-1.5 text-right text-zinc-200">{Number(t.entry_price).toFixed(5)}</td>
                <td className="px-3 py-1.5 text-right text-zinc-200">{Number(t.exit_price).toFixed(5)}</td>
                <td className={`px-3 py-1.5 ${out === 'TP' ? 'text-emerald-400' : out === 'SL' ? 'text-red-400' : 'text-zinc-400'}`}>
                  {out || '-'}
                </td>
                <td className="px-3 py-1.5 text-right text-red-400">{Number(t.mae ?? 0).toFixed(1)}</td>
                <td className="px-3 py-1.5 text-right text-emerald-400">{Number(t.mfe ?? 0).toFixed(1)}</td>
                <td className={`px-3 py-1.5 text-right ${Number(t.r_multiple ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {Number(t.r_multiple ?? 0) >= 0 ? '+' : ''}{Number(t.r_multiple ?? 0).toFixed(2)}
                </td>
                <td className={`px-3 py-1.5 text-right ${t.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {t.net_pnl >= 0 ? '+' : ''}{Number(t.net_pnl).toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Tab: Risk ────────────────────────────────────────────────────
function RiskTab({ summary, avgDrawdown, equityCurve, drawdownCurve }) {
  const curveData = useMemo(() => equityCurve.map((v, i) => ({
    bar: i,
    equity: Number(v),
    drawdown: -Number(drawdownCurve[i] ?? 0),  // negative so it dips below
  })), [equityCurve, drawdownCurve]);

  return (
    <div className="flex flex-col gap-4" data-testid="tab-risk-content">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <MetricTile
          testId="risk-max-dd"
          label="Max Drawdown"
          value={`$${Number(summary.max_drawdown ?? 0).toFixed(2)}`}
          tone="bad"
        />
        <MetricTile
          testId="risk-avg-dd"
          label="Avg Drawdown"
          value={`$${Number(avgDrawdown).toFixed(2)}`}
          tone="neutral"
        />
        <MetricTile
          testId="risk-trade-count"
          label="Trade Count"
          value={String(summary.total_trades ?? 0)}
          tone="neutral"
        />
      </div>

      {curveData.length > 1 && (
        <div className="border border-zinc-800 rounded-md bg-zinc-900/50 p-3">
          <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-2">
            Equity Curve &amp; Drawdown
          </p>
          <div className="h-[200px]" data-testid="risk-equity-chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={curveData} margin={{ top: 5, right: 10, bottom: 5, left: 40 }}>
                <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
                <XAxis
                  dataKey="bar"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  stroke="#52525b"
                  tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#52525b"
                  tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }}
                  width={70}
                  tickFormatter={(v) => `$${Math.round(v)}`}
                />
                <Tooltip
                  contentStyle={{
                    background: '#18181b',
                    border: '1px solid #3f3f46',
                    borderRadius: 4,
                    fontSize: 11,
                    fontFamily: 'monospace',
                  }}
                  formatter={(v, n) => [`$${Number(v).toFixed(2)}`, n]}
                />
                <Area
                  type="monotone"
                  dataKey="drawdown"
                  fill="#ef4444"
                  fillOpacity={0.15}
                  stroke="#ef4444"
                  strokeWidth={1}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab: Execution ───────────────────────────────────────────────
function ExecutionTab({ execution }) {
  const enabled = !!execution?.enabled;
  return (
    <div className="flex flex-col gap-3" data-testid="tab-execution-content">
      <div className="flex items-center gap-2 text-[11px] font-mono">
        <span className={`inline-block w-2 h-2 rounded-full ${enabled ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
        <span className="text-zinc-400">
          Execution engine is <span className={enabled ? 'text-emerald-400' : 'text-zinc-300'}>
            {enabled ? 'ENABLED' : 'DISABLED'}
          </span>
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricTile
          testId="exec-spread"
          label="Total Spread Cost"
          value={`$${Number(execution?.total_spread_cost ?? 0).toFixed(2)}`}
          tone="bad"
        />
        <MetricTile
          testId="exec-slippage"
          label="Total Slippage Cost"
          value={`$${Number(execution?.total_slippage_cost ?? 0).toFixed(2)}`}
          tone="bad"
        />
        <MetricTile
          testId="exec-commission"
          label="Total Commission"
          value={`$${Number(execution?.total_commission ?? 0).toFixed(2)}`}
          tone="bad"
        />
        <MetricTile
          testId="exec-total"
          label="Total Execution Cost"
          value={`$${Number(execution?.total_execution_cost ?? 0).toFixed(2)}`}
          tone={Number(execution?.total_execution_cost ?? 0) > 0 ? 'bad' : 'neutral'}
        />
      </div>

      {!enabled && (
        <p className="text-[11px] font-mono text-zinc-500 pt-1">
          Execution realism was not enabled for this backtest. Enable it in the simulation config
          (<span className="text-zinc-300">execution.enabled = true</span>) to see realistic spread, slippage, and commission costs.
        </p>
      )}
    </div>
  );
}
