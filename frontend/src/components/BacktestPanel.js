import React, { useState, useEffect, useCallback } from 'react';
import { ChartLine, FloppyDisk, CircleNotch, TrendUp, TrendDown, Warning, Database, HardDrives, Gear, ChartBar, Gauge } from '@phosphor-icons/react';
import { runBacktest, saveStrategy, getMarketData } from '../services/api';
import StrategyChartView from './StrategyChartView';
import StrategyDeepDivePanel from './StrategyDeepDivePanel';
import { AsfKpiTile, AsfEmptyState, VerdictBadge } from './ui-asf';

function _DeprecatedMetricCard({ label, value, color, testId }) {
  return (
    <div data-testid={testId} className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
      <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono tracking-tight ${color || 'text-white'}`}>{value}</p>
    </div>
  );
}

function SmallMetric({ label, value, color, testId }) {
  return (
    <div data-testid={testId} className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-bold font-mono tracking-tight ${color || 'text-white'}`}>{value}</p>
    </div>
  );
}

const TF_MAP = { 'M1': '1m', 'M5': '5m', 'M15': '15m', 'M30': '30m', 'H1': '1h', 'H4': '4h', 'D1': '1d' };

export default function BacktestPanel({ strategy, backtestResults, onBacktestRun, onStrategySaved, pair, timeframe }) {
  const [loadingBacktest, setLoadingBacktest] = useState(false);
  const [loadingSave, setLoadingSave] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [error, setError] = useState(null);
  const [showChart, setShowChart] = useState(false);
  const [showDeepDive, setShowDeepDive] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [availableData, setAvailableData] = useState([]);
  const [riskPercent, setRiskPercent] = useState('1.0');
  const [spreadPips, setSpreadPips] = useState('');

  const fetchAvailable = useCallback(async () => {
    try { const data = await getMarketData(); setAvailableData(data.datasets || []); } catch (e) { /* silent */ }
  }, []);
  useEffect(() => { fetchAvailable(); }, [fetchAvailable]);

  const dataTf = TF_MAP[timeframe] || timeframe?.toLowerCase();
  const matchingDataset = availableData.find((d) => d.symbol === pair && d.timeframe === dataTf);

  const handleBacktest = async () => {
    if (!strategy) return;
    setLoadingBacktest(true);
    setError(null);
    try {
      const data = await runBacktest(strategy, pair, timeframe, false, dateFrom || null, dateTo || null, spreadPips || null, parseFloat(riskPercent) || 1.0);
      onBacktestRun(data.results);
    } catch (e) { setError(e.message); }
    finally { setLoadingBacktest(false); }
  };

  const handleSave = async () => {
    if (!strategy) return;
    setLoadingSave(true);
    setSaveMsg(null);
    try {
      const extra = {
        strategy_type: backtestResults?.strategy_type || null,
        safety: backtestResults?.safety || null,
      };
      // Extract indicators from extraction data
      if (backtestResults?.extraction?.raw) {
        const raw = backtestResults.extraction.raw;
        const ind = {};
        if (raw.rsi_period) ind.rsi = { period: raw.rsi_period, buy: raw.rsi_buy_threshold, sell: raw.rsi_sell_threshold };
        if (raw.macd) ind.macd = raw.macd;
        if (raw.bollinger) ind.bollinger = raw.bollinger;
        if (Object.keys(ind).length > 0) extra.indicators = ind;
      }
      await saveStrategy(strategy, pair, timeframe, backtestResults, extra);
      setSaveMsg('Strategy saved to Library');
      onStrategySaved();
      setTimeout(() => setSaveMsg(null), 3000);
    } catch (e) { setError(e.message); }
    finally { setLoadingSave(false); }
  };

  const r = backtestResults;
  const inputClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none transition-colors";

  return (
    <div className="flex flex-col gap-4">
      {/* Strategy + Actions */}
      <div data-testid="strategy-text-display" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
        <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
          <h2 className="asf-legacy-title text-sm font-semibold text-white">Strategy Output</h2>
          <div className="asf-section__hd-spacer" />
          <div className="asf-section__hd-actions flex gap-2">
            <button data-testid="run-backtest-btn" onClick={handleBacktest} disabled={!strategy || loadingBacktest}
              className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
              {loadingBacktest ? <CircleNotch size={12} className="animate-spin" /> : <ChartLine size={12} />}
              {loadingBacktest ? 'Running...' : 'Run Backtest'}
            </button>
            <button data-testid="save-strategy-btn" onClick={handleSave} disabled={!strategy || loadingSave}
              className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
              {loadingSave ? <CircleNotch size={12} className="animate-spin" /> : <FloppyDisk size={12} />}
              {loadingSave ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>

        {/* Config Bar */}
        {strategy && (
          <div data-testid="data-source-controls" className="border-b border-zinc-800 px-4 py-3 flex flex-col gap-2.5 bg-zinc-900/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Gear size={12} className="text-zinc-500" />
                <span className="text-[11px] font-medium text-zinc-400">Configuration</span>
              </div>
              {matchingDataset ? (
                <span className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-500">
                  <Database size={10} /> Real data &middot; {matchingDataset.records.toLocaleString()} candles
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                  <HardDrives size={10} /> Sample data (50 pts)
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              {matchingDataset && (
                <>
                  <input data-testid="date-from-input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                    className={`${inputClass} w-32`} />
                  <span className="text-zinc-600 text-xs">to</span>
                  <input data-testid="date-to-input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                    className={`${inputClass} w-32`} />
                  {(dateFrom || dateTo) && (
                    <button data-testid="clear-dates-btn" onClick={() => { setDateFrom(''); setDateTo(''); }}
                      className="text-[10px] font-mono text-zinc-500 hover:text-white transition-colors">Clear</button>
                  )}
                  <span className="w-px h-4 bg-zinc-800" />
                </>
              )}
              <div className="flex items-center gap-1.5">
                <label className="text-[10px] font-mono text-zinc-500">Risk</label>
                <input data-testid="risk-percent-input" type="number" step="0.5" min="0.1" max="10" value={riskPercent}
                  onChange={(e) => setRiskPercent(e.target.value)} className={`${inputClass} w-14 text-center`} />
                <span className="text-[10px] font-mono text-zinc-600">%</span>
              </div>
              <div className="flex items-center gap-1.5">
                <label className="text-[10px] font-mono text-zinc-500">Spread</label>
                <input data-testid="spread-pips-input" type="number" step="0.1" min="0" value={spreadPips}
                  onChange={(e) => setSpreadPips(e.target.value)} placeholder="Auto"
                  className={`${inputClass} w-14 text-center placeholder:text-zinc-700`} />
              </div>
              <span className="text-[10px] font-mono text-zinc-600">$10K &middot; $7/lot comm</span>
            </div>
          </div>
        )}

        {/* Strategy Text */}
        <div className="p-4">
          {strategy ? (
            <pre className="text-sm font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-y-auto">
              {strategy}
            </pre>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
              <ChartLine size={40} weight="thin" className="mb-2 opacity-30" />
              <p className="text-sm">No strategy generated yet</p>
              <p className="text-xs text-zinc-700 mt-1">Use the generator panel to create one</p>
            </div>
          )}
          {saveMsg && <p data-testid="save-success-msg" className="text-emerald-500 text-xs font-mono mt-3">{saveMsg}</p>}
          {error && (
            <div className="mt-3">
              <AsfEmptyState
                slug="backtest-error"
                testId="backtest-error"
                title="Backtest failed"
                body={error}
              />
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {r && (
        <div data-testid="backtest-results-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
          <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
            <div className="asf-legacy-title flex items-center gap-2">
              <ChartLine size={14} weight="bold" className="text-emerald-500" />
              <h2 className="text-sm font-semibold text-white">Backtest Results</h2>
            </div>
            <span data-testid="data-source-badge" className={`ml-1 text-[10px] font-medium font-mono px-1.5 py-0.5 rounded border ${
              r.data_source === 'real' || r.data_source === 'uploaded'
                ? 'text-emerald-500 border-emerald-500/20 bg-emerald-500/5'
                : 'text-zinc-400 border-zinc-800 bg-zinc-800/50'
            }`}>
              {r.data_source === 'real' || r.data_source === 'uploaded' ? 'Real Data' : 'Sample'}
            </span>
            {r.data_points > 0 && <span className="text-[10px] font-mono text-zinc-500">{r.data_points} pts</span>}
            <span className="asf-section__hd-spacer" />
            <span className="text-xs font-mono text-zinc-500">{r.pair} &middot; {r.timeframe}</span>
            <div className="asf-section__hd-actions">
              {r.trades && r.trades.length > 0 && r.prices && r.prices.length > 0 && (
                <button
                  data-testid="view-chart-btn"
                  onClick={() => setShowChart(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/10 text-emerald-400 text-[11px] font-mono font-medium transition-colors"
                >
                  <ChartBar size={12} weight="bold" />
                  View Chart
                </button>
              )}
              {r.trades && r.trades.length > 0 && r.report && (
                <button
                  data-testid="deep-dive-btn"
                  onClick={() => setShowDeepDive(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 text-amber-400 text-[11px] font-mono font-medium transition-colors"
                >
                  <Gauge size={12} weight="bold" />
                  Deep Dive
                </button>
              )}
            </div>
          </div>

          <div className="p-4 flex flex-col gap-4">
            {/* Primary Metrics — AsfKpiTile (U-2). */}
            <div className="asf-kpi-grid">
              <AsfKpiTile
                testId="metric-net-profit"
                label="Net Profit"
                value={`$${r.net_profit >= 0 ? '+' : ''}${r.net_profit?.toLocaleString() ?? '0'}`}
                verdict={r.net_profit >= 0 ? 'success' : 'danger'}
              />
              <AsfKpiTile
                testId="metric-win-rate"
                label="Win Rate"
                value={`${r.win_rate}%`}
                verdict={r.win_rate >= 50 ? 'success' : 'danger'}
              />
              <AsfKpiTile
                testId="metric-max-dd-pct"
                label="Max Drawdown"
                value={`${r.max_drawdown_pct?.toFixed(1) ?? '0'}%`}
                verdict="warn"
              />
              <AsfKpiTile
                testId="metric-risk-adjusted"
                label="Risk-Adj Return"
                value={r.risk_adjusted_return ?? 0}
                verdict={(r.risk_adjusted_return ?? 0) >= 1 ? 'success' : 'danger'}
              />
            </div>

            {/* Secondary Metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              <SmallMetric testId="metric-total-pnl" label="Total P&L"
                value={`${r.total_pnl_pips > 0 ? '+' : ''}${r.total_pnl_pips} pips`}
                color={r.total_pnl_pips >= 0 ? 'text-emerald-500' : 'text-red-500'} />
              <SmallMetric testId="metric-total-trades" label="Trades" value={r.total_trades} />
              <SmallMetric testId="metric-profit-factor" label="Profit Factor"
                value={r.profit_factor} color={r.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'} />
              <SmallMetric testId="metric-avg-win" label="Avg Win" value={`$${r.avg_win_usd?.toFixed(0) ?? '0'}`} color="text-emerald-500" />
              <SmallMetric testId="metric-avg-loss" label="Avg Loss" value={`$${r.avg_loss_usd?.toFixed(0) ?? '0'}`} color="text-red-500" />
            </div>

            {/* Costs + Equity */}
            <div className="grid grid-cols-2 gap-3">
              <div data-testid="costs-panel" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Trading Costs</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-mono text-zinc-400">
                  <span>Commission: <strong className="text-red-400">${r.total_commission?.toFixed(2)}</strong></span>
                  <span>Spread: <strong className="text-red-400">${r.total_spread_cost?.toFixed(2)}</strong></span>
                  <span>Slippage: <strong className="text-red-400">${r.total_slippage_cost?.toFixed(2)}</strong></span>
                  <span>Total: <strong className="text-yellow-500">${r.total_costs?.toFixed(2)}</strong></span>
                </div>
              </div>
              <div data-testid="equity-panel" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Equity</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-mono text-zinc-400">
                  <span>Initial: <strong className="text-white">${r.initial_balance?.toLocaleString()}</strong></span>
                  <span>Final: <strong className={r.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}>${r.final_balance?.toLocaleString()}</strong></span>
                  <span>Return: <strong className={r.total_return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}>{r.total_return_pct >= 0 ? '+' : ''}{r.total_return_pct?.toFixed(2)}%</strong></span>
                </div>
              </div>
            </div>

            {/* Parameters & Extraction Debug */}
            {r.simulation && (
              <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Parameters Used in Backtest</p>
                  <div className="flex items-center gap-1.5">
                    {r.strategy_type && (
                      <span data-testid="strategy-type-badge" className="text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border bg-yellow-500/10 text-yellow-500 border-yellow-500/20">
                        {r.strategy_type.replace('_', ' ')}
                      </span>
                    )}
                    {r.parameters?.source && (
                      <span data-testid="param-source-badge" className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${
                        r.parameters.source === 'extracted'
                          ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                          : r.parameters.source === 'overrides'
                          ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                          : 'bg-zinc-800 text-zinc-500 border-zinc-700'
                      }`}>
                        {r.parameters.source === 'extracted' ? 'Extracted from strategy' : r.parameters.source === 'overrides' ? 'Manual override' : 'Seed default'}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3 text-xs font-mono text-zinc-400">
                  <span>Spread: <strong className="text-white">{r.simulation.spread_pips}p</strong></span>
                  <span>Risk: <strong className="text-white">{r.simulation.risk_percent}%</strong></span>
                  <span>Fast EMA: <strong className="text-white">{r.parameters.fast_sma}</strong></span>
                  <span>Slow EMA: <strong className="text-white">{r.parameters.slow_sma}</strong></span>
                  <span>SL: <strong className="text-red-400">{r.parameters.stop_loss_pips}p</strong></span>
                  <span>TP: <strong className="text-emerald-400">{r.parameters.take_profit_pips}p</strong></span>
                </div>
                {/* Active indicators */}
                {r.indicators_used && r.indicators_used.length > 0 && (
                  <div data-testid="indicators-used" className="mt-2 pt-2 border-t border-zinc-800/50 flex items-center gap-1.5 flex-wrap">
                    <span className="text-[9px] font-mono text-zinc-600">Indicators:</span>
                    {r.indicators_used.map((ind, idx) => (
                      <span key={idx} className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                        {ind}
                      </span>
                    ))}
                  </div>
                )}
                {r.extraction && r.extraction.confidence > 0 && (
                  <div data-testid="extraction-debug" className="mt-2 pt-2 border-t border-zinc-800/50">
                    <p className="text-[9px] font-mono text-zinc-600 mb-1">
                      Extracted {r.extraction.confidence} params from strategy text
                      {r.extraction.complete && <span className="text-emerald-500 ml-1">— full match</span>}
                    </p>
                    {r.extraction.raw && (
                      <div className="flex flex-wrap gap-2 text-[9px] font-mono text-zinc-500">
                        {r.extraction.raw.fast_ma != null && <span>Fast: {r.extraction.raw.fast_ma}</span>}
                        {r.extraction.raw.slow_ma != null && <span>Slow: {r.extraction.raw.slow_ma}</span>}
                        {r.extraction.raw.stop_loss != null && <span>SL: {r.extraction.raw.stop_loss}p</span>}
                        {r.extraction.raw.take_profit != null && <span>TP: {r.extraction.raw.take_profit}p</span>}
                        {r.extraction.raw.rsi_period != null && <span>RSI: {r.extraction.raw.rsi_period}</span>}
                        {r.extraction.raw.rsi_buy_threshold != null && <span>RSI Buy: {'>'}{r.extraction.raw.rsi_buy_threshold}</span>}
                        {r.extraction.raw.rsi_sell_threshold != null && <span>RSI Sell: {'<'}{r.extraction.raw.rsi_sell_threshold}</span>}
                        {r.extraction.raw.macd && <span>MACD: {r.extraction.raw.macd.fast}/{r.extraction.raw.macd.slow}/{r.extraction.raw.macd.signal}</span>}
                        {r.extraction.raw.bollinger && <span>BB: {r.extraction.raw.bollinger.period},{r.extraction.raw.bollinger.std_dev}</span>}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Safety Analysis */}
            {r.safety && (
              <div data-testid="safety-section" className={`bg-zinc-950 border rounded-md p-3 relative ${
                r.safety.is_safe ? 'border-emerald-500/20' : 'border-red-500/30'
              }`}>
                <div className="absolute -top-2 left-3">
                  <VerdictBadge
                    verdict={r.safety.safety_score >= 65 ? 'success' : r.safety.safety_score >= 40 ? 'warn' : 'danger'}
                  >
                    {r.safety.is_safe ? 'Safe' : 'Unsafe'} — {r.safety.grade}
                  </VerdictBadge>
                </div>
                <div className="grid grid-cols-4 gap-2 mt-1 mb-2">
                  <div className="text-center">
                    <p data-testid="safety-score" className={`text-sm font-bold font-mono ${
                      r.safety.safety_score >= 65 ? 'text-emerald-500' : r.safety.safety_score >= 40 ? 'text-yellow-500' : 'text-red-500'
                    }`}>{r.safety.safety_score}/100</p>
                    <p className="text-[8px] text-zinc-500">Safety</p>
                  </div>
                  <div className="text-center">
                    <p data-testid="trades-per-day" className={`text-sm font-bold font-mono ${
                      r.safety.metrics?.overtrading ? 'text-red-500' : 'text-white'
                    }`}>{r.safety.metrics?.trades_per_day}/d</p>
                    <p className="text-[8px] text-zinc-500">Frequency</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-bold font-mono text-yellow-500">{r.safety.metrics?.max_drawdown_pct?.toFixed(1)}%</p>
                    <p className="text-[8px] text-zinc-500">Max DD</p>
                  </div>
                  <div className="text-center">
                    <p className={`text-sm font-bold font-mono ${r.safety.metrics?.consecutive_losses > 5 ? 'text-red-500' : 'text-white'}`}>
                      {r.safety.metrics?.consecutive_losses}
                    </p>
                    <p className="text-[8px] text-zinc-500">Max Consec Loss</p>
                  </div>
                </div>
                {/* Flags */}
                {r.safety.flags && r.safety.flags.length > 0 && (
                  <div className="flex flex-col gap-1 mb-1">
                    {r.safety.flags.map((f, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-[9px] font-mono text-red-400">
                        <Warning size={10} weight="bold" className="text-red-500 flex-shrink-0" />
                        {f}
                      </div>
                    ))}
                  </div>
                )}
                {r.safety.warnings && r.safety.warnings.length > 0 && (
                  <div className="flex flex-col gap-1">
                    {r.safety.warnings.map((w, i) => (
                      <div key={i} className="text-[9px] font-mono text-yellow-500">{w}</div>
                    ))}
                  </div>
                )}
                {/* Score breakdown */}
                <div className="mt-2 pt-2 border-t border-zinc-800/50 flex flex-wrap gap-2 text-[9px] font-mono text-zinc-500">
                  <span>DD: <strong className="text-zinc-300">{r.safety.score_breakdown?.drawdown_control}/30</strong></span>
                  <span>Freq: <strong className="text-zinc-300">{r.safety.score_breakdown?.trade_frequency}/25</strong></span>
                  <span>Risk: <strong className="text-zinc-300">{r.safety.score_breakdown?.risk_exposure}/25</strong></span>
                  <span>Consec: <strong className="text-zinc-300">{r.safety.score_breakdown?.consecutive_loss}/20</strong></span>
                </div>
              </div>
            )}

            {/* Equity Curve */}
            {r.equity_curve && r.equity_curve.length > 1 && (
              <div data-testid="equity-curve" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Equity Curve</p>
                <div className="h-16 flex items-end gap-px">
                  {r.equity_curve.map((val, i) => {
                    const min = Math.min(...r.equity_curve);
                    const max = Math.max(...r.equity_curve);
                    const range = max - min || 1;
                    const pct = ((val - min) / range) * 100;
                    return (
                      <div key={i} className="flex-1 min-w-[2px]" style={{ height: `${Math.max(pct, 4)}%` }}>
                        <div className={`w-full h-full rounded-sm ${val >= r.initial_balance ? 'bg-emerald-500/50' : 'bg-red-500/50'}`} />
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between mt-1 text-[9px] font-mono text-zinc-600">
                  <span>${r.equity_curve[0]?.toLocaleString()}</span>
                  <span>${r.equity_curve[r.equity_curve.length - 1]?.toLocaleString()}</span>
                </div>
              </div>
            )}

            {/* Trade Log */}
            {r.trades && r.trades.length > 0 && (
              <div data-testid="trade-log" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                <div className="px-4 py-2.5 border-b border-zinc-800">
                  <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Trade Log</p>
                </div>
                <div className="max-h-[200px] overflow-y-auto">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left px-3 py-2">#</th>
                        <th className="text-left px-3 py-2">Dir</th>
                        <th className="text-right px-3 py-2">Lots</th>
                        <th className="text-right px-3 py-2">Entry</th>
                        <th className="text-right px-3 py-2">Exit</th>
                        <th className="text-right px-3 py-2">Pips</th>
                        <th className="text-right px-3 py-2">Net $</th>
                        <th className="text-right px-3 py-2">Balance</th>
                        <th className="text-right px-3 py-2">Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.trades.map((t, i) => (
                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                          <td className="px-3 py-1.5 text-zinc-600">{i + 1}</td>
                          <td className="px-3 py-1.5">
                            <span className="flex items-center gap-1">
                              {t.direction === 'BUY' ? <TrendUp size={10} className="text-emerald-500" /> : <TrendDown size={10} className="text-red-500" />}
                              <span className="text-zinc-300">{t.direction}</span>
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-right text-zinc-400">{t.lot_size}</td>
                          <td className="px-3 py-1.5 text-right text-zinc-400">{t.entry_price}</td>
                          <td className="px-3 py-1.5 text-right text-zinc-400">{t.exit_price}</td>
                          <td className={`px-3 py-1.5 text-right ${t.pnl_pips >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {t.pnl_pips > 0 ? '+' : ''}{t.pnl_pips}
                          </td>
                          <td className={`px-3 py-1.5 text-right font-semibold ${t.net_pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {t.net_pnl > 0 ? '+' : ''}${t.net_pnl?.toFixed(0)}
                          </td>
                          <td className="px-3 py-1.5 text-right text-zinc-500">${t.balance?.toLocaleString()}</td>
                          <td className="px-3 py-1.5 text-right">
                            <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${
                              t.result === 'TP' ? 'bg-emerald-500/10 text-emerald-500' :
                              t.result === 'SL' ? 'bg-red-500/10 text-red-500' :
                              'bg-zinc-800 text-zinc-400'
                            }`}>{t.result}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {r.trades && r.trades.length === 0 && (
              <div className="flex items-center gap-2 p-3 bg-zinc-950 border border-zinc-800 rounded-md text-zinc-500">
                <Warning size={14} />
                <span className="text-xs font-mono">No trades generated during the backtest period</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Phase 7.5 — Trade Visualization Modal */}
      {showChart && r && (
        <div
          data-testid="chart-modal"
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setShowChart(false); }}
        >
          <div className="w-[min(1400px,95vw)] h-[min(90vh,900px)] bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden shadow-2xl">
            <StrategyChartView
              report={r.report}
              prices={r.prices}
              onClose={() => setShowChart(false)}
            />
          </div>
        </div>
      )}

      {/* Phase 7.5 — Strategy Deep Dive Modal */}
      {showDeepDive && r && (
        <div
          data-testid="deep-dive-modal"
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setShowDeepDive(false); }}
        >
          <div className="w-[min(1500px,96vw)] h-[min(94vh,1000px)] bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden shadow-2xl">
            <StrategyDeepDivePanel
              result={r}
              onClose={() => setShowDeepDive(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
