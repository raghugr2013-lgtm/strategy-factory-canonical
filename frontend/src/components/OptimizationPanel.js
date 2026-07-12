import React, { useState } from 'react';
import { Gauge, CircleNotch, Trophy, ArrowUp, Crown, Database, WarningCircle, Shuffle, ChartLineUp, ShieldCheck, Lightning } from '@phosphor-icons/react';
import { optimizeRandom } from '../services/api';
import { AsfEmptyState } from './ui-asf';

function ParamPill({ label, value, highlight }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${
      highlight ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' : 'border-zinc-800 bg-zinc-800/50 text-zinc-400'
    }`}>
      <span className="uppercase tracking-wider">{label}</span>
      <strong className="text-white">{value}</strong>
    </span>
  );
}

function ParamPills({ params, highlight }) {
  if (!params) return null;
  const pills = [];
  if (params.fast_period != null) pills.push({ l: 'EMA-F', v: params.fast_period });
  if (params.slow_period != null) pills.push({ l: 'EMA-S', v: params.slow_period });
  if (params.rsi_period != null) pills.push({ l: 'RSI', v: params.rsi_period });
  if (params.rsi_buy_threshold != null) pills.push({ l: 'RSI-B', v: params.rsi_buy_threshold });
  if (params.rsi_sell_threshold != null) pills.push({ l: 'RSI-S', v: params.rsi_sell_threshold });
  if (params.macd_fast != null) pills.push({ l: 'MACD', v: `${params.macd_fast}/${params.macd_slow}/${params.macd_signal}` });
  if (params.bb_period != null) pills.push({ l: 'BB', v: `${params.bb_period}/${params.bb_std_dev}` });
  if (params.sl_pips != null) pills.push({ l: 'SL', v: `${params.sl_pips}p` });
  if (params.tp_pips != null) pills.push({ l: 'TP', v: `${params.tp_pips}p` });
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {pills.map((p, i) => <ParamPill key={i} label={p.l} value={p.v} highlight={highlight} />)}
    </div>
  );
}

const TYPE_LABELS = {
  trend_following: 'Trend Following', mean_reversion: 'Mean Reversion',
  momentum: 'Momentum', breakout: 'Breakout', scalping: 'Scalping',
};

function MetricCell({ label, value, suffix, good }) {
  return (
    <div className="text-center">
      <p data-testid={`opt-metric-${label.toLowerCase().replace(/\s/g,'-')}`}
         className={`text-sm font-bold font-mono ${good === true ? 'text-emerald-500' : good === false ? 'text-red-500' : 'text-zinc-300'}`}>
        {value}{suffix}
      </p>
      <p className="text-[9px] text-zinc-500">{label}</p>
    </div>
  );
}

function OverfitBar({ score }) {
  const pct = Math.round(score * 100);
  const color = pct <= 25 ? 'bg-emerald-500' : pct <= 50 ? 'bg-yellow-500' : 'bg-red-500';
  const label = pct <= 25 ? 'Low risk' : pct <= 50 ? 'Moderate' : 'High risk';
  return (
    <div data-testid="overfit-indicator" className="flex items-center gap-2">
      <span className="text-[9px] text-zinc-500 w-14">Overfit</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.max(pct, 3)}%` }} />
      </div>
      <span className={`text-[9px] font-mono ${pct <= 25 ? 'text-emerald-500' : pct <= 50 ? 'text-yellow-500' : 'text-red-500'}`}>
        {pct}% {label}
      </span>
    </div>
  );
}

function FitnessBreakdown({ breakdown }) {
  if (!breakdown) return null;
  const bars = [
    { key: 'profit', label: 'Profit', max: 25, color: 'bg-emerald-500' },
    { key: 'sharpe', label: 'Sharpe', max: 30, color: 'bg-blue-500' },
    { key: 'drawdown', label: 'Drawdown', max: 25, color: 'bg-yellow-500' },
    { key: 'frequency', label: 'Frequency', max: 20, color: 'bg-purple-500' },
  ];
  return (
    <div data-testid="fitness-breakdown" className="flex flex-col gap-1">
      {bars.map(b => (
        <div key={b.key} className="flex items-center gap-2">
          <span className="text-[9px] text-zinc-500 w-16">{b.label}</span>
          <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div className={`h-full ${b.color} rounded-full`}
                 style={{ width: `${(breakdown[b.key] / b.max) * 100}%` }} />
          </div>
          <span className="text-[9px] font-mono text-zinc-400 w-10 text-right">
            {breakdown[b.key]?.toFixed(1)}/{b.max}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function OptimizationPanel({ strategy, pair, timeframe }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [numVariants, setNumVariants] = useState(75);
  const [trainRatio, setTrainRatio] = useState(70);

  const handleOptimize = async () => {
    if (!strategy) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await optimizeRandom(strategy, pair, timeframe, numVariants, trainRatio / 100);
      setResult(data.optimization);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const best = result?.best;
  const top10 = result?.top_10 || [];
  const stats = result?.population_stats;
  const split = result?.train_test_split;
  const warnings = result?.warnings || [];
  const stratType = result?.strategy_type;

  return (
    <div data-testid="optimization-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      {/* Header */}
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
        <div className="asf-legacy-title flex items-center gap-2">
          <Shuffle size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">Random Search Optimizer</h2>
          {stratType && result && (
            <span data-testid="opt-strategy-type" className="text-[9px] font-mono font-semibold bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded border border-zinc-700">
              {TYPE_LABELS[stratType] || stratType}
            </span>
          )}
          <span className="text-[8px] font-mono text-zinc-600 border border-zinc-800 px-1 py-0.5 rounded">Phase 1</span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button data-testid="optimize-random-btn" onClick={handleOptimize} disabled={!strategy || loading}
            className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-3 py-1.5 text-xs transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
            {loading ? <><CircleNotch size={12} className="animate-spin" /> Searching...</> : <><Shuffle size={12} /> Optimize</>}
          </button>
        </div>
      </div>

      <div className="p-4">
        {/* Empty states */}
        {!strategy && !result && (
          <p className="text-sm text-zinc-600 text-center py-6">Generate a strategy first</p>
        )}
        {strategy && !result && !loading && !error && (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-zinc-500 text-center">
              Random search generates {numVariants} parameter variants, evaluates each with execution costs on a train/test split, and selects the top 10.
            </p>
            <div className="flex items-center gap-4 justify-center">
              <label className="flex items-center gap-2 text-[10px] text-zinc-400">
                Variants
                <select data-testid="opt-variants-select" value={numVariants} onChange={e => setNumVariants(Number(e.target.value))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-white text-[10px] font-mono">
                  <option value={50}>50</option>
                  <option value={75}>75</option>
                  <option value={100}>100</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-[10px] text-zinc-400">
                Train
                <select data-testid="opt-train-ratio-select" value={trainRatio} onChange={e => setTrainRatio(Number(e.target.value))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-white text-[10px] font-mono">
                  <option value={60}>60%</option>
                  <option value={70}>70%</option>
                  <option value={80}>80%</option>
                </select>
              </label>
            </div>
          </div>
        )}
        {error && (
          <AsfEmptyState
            slug="optimization-error"
            testId="optimization-error"
            title="Optimization failed"
            body={error}
          />
        )}

        {result && result.success === false && (
          <AsfEmptyState
            slug="optimization-result-error"
            testId="optimization-error"
            title="Optimizer returned no result"
            body={result.error || 'Unknown error'}
          />
        )}

        {result && result.success && (
          <div className="flex flex-col gap-3">
            {/* Summary Bar */}
            <div data-testid="optimization-summary" className="flex items-center gap-3 flex-wrap text-xs font-mono">
              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded border text-emerald-500 border-emerald-500/20 bg-emerald-500/5">
                <Database size={10} />
                <span className="ml-0.5">{result.data_points} candles</span>
              </span>
              {split && (
                <span className="text-zinc-500">
                  Train <strong className="text-blue-400">{split.train_candles}</strong> / Test <strong className="text-orange-400">{split.test_candles}</strong>
                </span>
              )}
              <span className="text-zinc-500"><strong className="text-white">{result.num_variants}</strong> searched</span>
              {stats && (
                <span className="text-zinc-500">
                  <strong className="text-emerald-400">{stats.profitable_on_test}</strong>/{result.num_variants} profitable on test
                </span>
              )}
            </div>

            {/* Warnings */}
            {warnings.length > 0 && (
              <div data-testid="optimization-warnings" className="bg-yellow-500/5 border border-yellow-500/20 rounded-md p-2.5">
                {warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-[10px] text-yellow-500 font-mono">
                    <WarningCircle size={12} weight="bold" className="shrink-0 mt-0.5" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Best Result */}
            {best && (
              <div data-testid="best-configuration" className="border border-yellow-500/30 bg-yellow-500/5 rounded-md p-3 relative">
                <div className="absolute -top-2 left-3 flex items-center gap-1 bg-yellow-500 text-zinc-900 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase">
                  <Crown size={9} weight="bold" /> Best
                </div>
                <div className="flex items-start justify-between mt-1 mb-2">
                  <ParamPills params={best.parameters} highlight />
                  <span className="text-emerald-500 font-bold font-mono text-sm ml-2 shrink-0">{best.fitness}/100</span>
                </div>

                {/* Train vs Test comparison */}
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <div className="bg-blue-500/5 border border-blue-500/15 rounded p-2">
                    <p className="text-[9px] font-bold text-blue-400 uppercase tracking-wider mb-1 flex items-center gap-1">
                      <ChartLineUp size={9} /> Train
                    </p>
                    <div className="grid grid-cols-3 gap-1">
                      <MetricCell label="Profit" value={`$${best.train?.net_profit?.toFixed(0)}`} good={best.train?.net_profit > 0} />
                      <MetricCell label="Sharpe" value={best.train?.sharpe_ratio?.toFixed(2)} good={best.train?.sharpe_ratio > 0.5} />
                      <MetricCell label="DD" value={`${best.train?.max_drawdown_pct?.toFixed(1)}%`} good={best.train?.max_drawdown_pct < 15} />
                    </div>
                  </div>
                  <div className="bg-orange-500/5 border border-orange-500/15 rounded p-2">
                    <p className="text-[9px] font-bold text-orange-400 uppercase tracking-wider mb-1 flex items-center gap-1">
                      <ShieldCheck size={9} /> Test
                    </p>
                    <div className="grid grid-cols-3 gap-1">
                      <MetricCell label="Profit" value={`$${best.test?.net_profit?.toFixed(0)}`} good={best.test?.net_profit > 0} />
                      <MetricCell label="Sharpe" value={best.test?.sharpe_ratio?.toFixed(2)} good={best.test?.sharpe_ratio > 0.5} />
                      <MetricCell label="DD" value={`${best.test?.max_drawdown_pct?.toFixed(1)}%`} good={best.test?.max_drawdown_pct < 15} />
                    </div>
                  </div>
                </div>

                <OverfitBar score={best.overfit_score} />
                <div className="mt-2">
                  <FitnessBreakdown breakdown={best.fitness_breakdown} />
                </div>
              </div>
            )}

            {/* Top 10 Table */}
            {top10.length > 0 && (
              <div data-testid="optimization-results-table" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2">
                  <Trophy size={12} className="text-yellow-500" />
                  <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Top 10 Variants</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] font-mono">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left px-2 py-1.5">#</th>
                        <th className="text-right px-2 py-1.5">Fitness</th>
                        <th className="text-right px-2 py-1.5">Sharpe</th>
                        <th className="text-right px-2 py-1.5">Train $</th>
                        <th className="text-right px-2 py-1.5">Test $</th>
                        <th className="text-right px-2 py-1.5">WR</th>
                        <th className="text-right px-2 py-1.5">DD</th>
                        <th className="text-right px-2 py-1.5">Trades</th>
                        <th className="text-center px-2 py-1.5">Overfit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top10.map((v) => (
                        <tr key={v.rank} data-testid={`opt-variant-${v.rank}`}
                          className={`border-b border-zinc-800/50 transition-colors ${v.rank === 1 ? 'bg-yellow-500/5' : 'hover:bg-zinc-800/30'}`}>
                          <td className="px-2 py-1.5"><span className={v.rank === 1 ? 'text-yellow-500 font-bold' : 'text-zinc-600'}>#{v.rank}</span></td>
                          <td className={`text-right px-2 py-1.5 font-bold ${v.fitness >= 60 ? 'text-emerald-500' : v.fitness >= 40 ? 'text-yellow-500' : 'text-red-500'}`}>{v.fitness}</td>
                          <td className={`text-right px-2 py-1.5 ${v.sharpe_ratio > 0.5 ? 'text-blue-400' : v.sharpe_ratio > 0 ? 'text-zinc-400' : 'text-red-500'}`}>{v.sharpe_ratio?.toFixed(2)}</td>
                          <td className={`text-right px-2 py-1.5 ${v.train?.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${v.train?.net_profit?.toFixed(0)}</td>
                          <td className={`text-right px-2 py-1.5 ${v.test?.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${v.test?.net_profit?.toFixed(0)}</td>
                          <td className={`text-right px-2 py-1.5 ${v.train?.win_rate >= 50 ? 'text-emerald-500' : 'text-zinc-400'}`}>{v.train?.win_rate}%</td>
                          <td className={`text-right px-2 py-1.5 ${v.train?.max_drawdown_pct < 15 ? 'text-emerald-500' : 'text-yellow-500'}`}>{v.train?.max_drawdown_pct?.toFixed(1)}%</td>
                          <td className="text-right px-2 py-1.5 text-zinc-400">{v.train?.total_trades}</td>
                          <td className="text-center px-2 py-1.5">
                            <span className={`text-[9px] px-1 py-0.5 rounded ${
                              v.overfit_score <= 0.25 ? 'bg-emerald-500/10 text-emerald-400'
                              : v.overfit_score <= 0.5 ? 'bg-yellow-500/10 text-yellow-400'
                              : 'bg-red-500/10 text-red-400'
                            }`}>{Math.round(v.overfit_score * 100)}%</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Population Stats */}
            {stats && (
              <div data-testid="population-stats" className="grid grid-cols-4 gap-2">
                <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
                  <p className="text-sm font-bold font-mono text-white">{stats.mean_fitness}</p>
                  <p className="text-[9px] text-zinc-500">Avg Fitness</p>
                </div>
                <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
                  <p className="text-sm font-bold font-mono text-blue-400">{stats.mean_sharpe}</p>
                  <p className="text-[9px] text-zinc-500">Avg Sharpe</p>
                </div>
                <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
                  <p className="text-sm font-bold font-mono text-emerald-400">{stats.profitable_on_train}/{result.num_variants}</p>
                  <p className="text-[9px] text-zinc-500">Train +ve</p>
                </div>
                <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
                  <p className={`text-sm font-bold font-mono ${stats.avg_overfit_score <= 0.3 ? 'text-emerald-400' : 'text-yellow-400'}`}>
                    {(stats.avg_overfit_score * 100).toFixed(0)}%
                  </p>
                  <p className="text-[9px] text-zinc-500">Avg Overfit</p>
                </div>
              </div>
            )}

            {/* GA upgrade hint */}
            <div className="flex items-center gap-2 text-[9px] text-zinc-600 font-mono border-t border-zinc-800/50 pt-2">
              <Lightning size={10} className="text-zinc-700" />
              <span>Phase 1: Random Search  |  Phase 2: Genetic Algorithm (architecture ready)</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
