import React, { useState } from 'react';
import { ShieldCheck, CircleNotch, Warning, Database, HardDrives, Shuffle, TrendUp, TrendDown } from '@phosphor-icons/react';
import { validateStrategy } from '../services/api';
import { AsfEmptyState } from './ui-asf';

function MiniMetric({ label, value, color, testId }) {
  return (
    <div data-testid={testId} className="bg-zinc-950 border border-zinc-800 rounded-md p-2 text-center">
      <p className={`text-base font-bold font-mono tracking-tight ${color || 'text-white'}`}>{value}</p>
      <p className="text-[9px] text-zinc-500 uppercase tracking-wider">{label}</p>
    </div>
  );
}

function CIBar({ lower, upper, label }) {
  const range = upper - lower;
  const midpoint = (lower + upper) / 2;
  const isPositive = midpoint > 0;
  return (
    <div className="flex items-center gap-2 text-[10px] font-mono">
      <span className="text-zinc-500 w-12 shrink-0">{label}</span>
      <div className="flex-1 h-4 bg-zinc-950 border border-zinc-800 rounded relative overflow-hidden">
        <div className="absolute inset-y-0 left-1/2 w-px bg-zinc-700" />
        {range > 0 && (
          <div
            className={`absolute inset-y-0 rounded-sm ${isPositive ? 'bg-emerald-500/30 border-emerald-500/40' : 'bg-red-500/30 border-red-500/40'} border`}
            style={{
              left: `${Math.max(0, Math.min(100, 50 + lower * 1.5))}%`,
              width: `${Math.max(2, Math.min(100, range * 1.5))}%`,
            }}
          />
        )}
      </div>
      <span className={`w-20 text-right ${lower >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
        {lower >= 0 ? '+' : ''}{lower}%
      </span>
      <span className="text-zinc-600">to</span>
      <span className={`w-20 ${upper >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
        {upper >= 0 ? '+' : ''}{upper}%
      </span>
    </div>
  );
}

export default function ValidationPanel({ strategy, pair, timeframe }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleValidate = async () => {
    if (!strategy) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await validateStrategy(strategy, pair, timeframe);
      const v = data.validation;
      if (v.success === false) setError(v.error || 'Validation failed');
      else setResult(v);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const stab = result?.stability;
  const segments = result?.segments || [];
  const tt = result?.train_test;
  const mc = result?.monte_carlo;
  const safety = result?.safety;
  const profitColor = (v) => v >= 0 ? 'text-emerald-500' : 'text-red-500';

  return (
    <div data-testid="validation-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
        <div className="asf-legacy-title flex items-center gap-2">
          <ShieldCheck size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">Validator</h2>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button data-testid="validate-strategy-btn" onClick={handleValidate} disabled={!strategy || loading}
            className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-3 py-1.5 text-xs transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
            {loading ? <><CircleNotch size={12} className="animate-spin" /> Validating...</> : <><ShieldCheck size={12} /> Validate</>}
          </button>
        </div>
      </div>

      <div className="p-4">
        {!strategy && !result && (
          <p className="text-sm text-zinc-600 text-center py-6">Generate a strategy first</p>
        )}
        {strategy && !result && !loading && !error && (
          <p className="text-sm text-zinc-600 text-center py-6">Click Validate to test robustness</p>
        )}
        {error && (
          <AsfEmptyState
            slug="validation-error"
            testId="validation-error"
            title="Validation failed"
            body={error}
          />
        )}

        {result && (
          <div className="flex flex-col gap-3">
            {/* Summary */}
            <div data-testid="validation-summary" className="flex items-center gap-3 flex-wrap text-xs font-mono">
              <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded border ${
                result.data_source === 'real'
                  ? 'text-emerald-500 border-emerald-500/20 bg-emerald-500/5'
                  : 'text-zinc-400 border-zinc-800 bg-zinc-800/50'
              }`}>
                {result.data_source === 'real' ? <Database size={10} /> : <HardDrives size={10} />}
                <span className="ml-0.5">{result.total_candles} candles</span>
              </span>
              <span className="text-zinc-500"><strong className="text-white">{result.num_segments}</strong> segments</span>
              {mc?.success && (
                <span className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-violet-500/20 bg-violet-500/5 text-violet-400">
                  <Shuffle size={10} />
                  <span>{mc.num_simulations} MC sims</span>
                </span>
              )}
              {safety && (
                <span data-testid="validation-safety-badge" className={`flex items-center gap-1 px-1.5 py-0.5 rounded border ${
                  safety.is_safe
                    ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-500'
                    : 'border-red-500/20 bg-red-500/5 text-red-500'
                }`}>
                  <ShieldCheck size={10} />
                  <span>{safety.is_safe ? 'Safe' : 'Unsafe'} {safety.grade}</span>
                </span>
              )}
            </div>

            {/* Stability Score */}
            {stab && (
              <div data-testid="stability-score-card" className={`rounded-md p-3 relative border ${
                stab.score >= 60 ? 'border-emerald-500/30 bg-emerald-500/5' :
                stab.score >= 40 ? 'border-yellow-500/30 bg-yellow-500/5' :
                'border-red-500/30 bg-red-500/5'
              }`}>
                <div className={`absolute -top-2 left-3 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                  stab.score >= 60 ? 'bg-emerald-500 text-zinc-900' :
                  stab.score >= 40 ? 'bg-yellow-500 text-zinc-900' :
                  'bg-red-500 text-white'
                }`}>
                  Walk-Forward {stab.grade}
                </div>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  <MiniMetric label="Stability" value={`${stab.score}/100`}
                    color={stab.score >= 60 ? 'text-emerald-500' : stab.score >= 40 ? 'text-yellow-500' : 'text-red-500'} />
                  <MiniMetric label="Consistency" value={`${stab.consistency_pct}%`}
                    color={stab.consistency_pct >= 66 ? 'text-emerald-500' : stab.consistency_pct >= 50 ? 'text-yellow-500' : 'text-red-500'} />
                  <MiniMetric label="Profitable" value={`${stab.profitable_segments}/${stab.total_segments}`}
                    color={stab.profitable_segments > stab.total_segments / 2 ? 'text-emerald-500' : 'text-red-500'} />
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[9px] font-mono text-zinc-500">
                  <span>Ret: <strong className="text-zinc-300">{stab.breakdown.return_stability}/25</strong></span>
                  <span>DD: <strong className="text-zinc-300">{stab.breakdown.drawdown_stability}/25</strong></span>
                  <span>WR: <strong className="text-zinc-300">{stab.breakdown.win_rate_consistency}/20</strong></span>
                </div>
              </div>
            )}

            {/* ═══ SAFETY SECTION ═══ */}
            {safety && (
              <div data-testid="validation-safety-section" className={`rounded-md p-3 relative border ${
                safety.safety_score >= 65 ? 'border-emerald-500/30 bg-emerald-500/5' :
                safety.safety_score >= 40 ? 'border-yellow-500/30 bg-yellow-500/5' :
                'border-red-500/30 bg-red-500/5'
              }`}>
                <div className={`absolute -top-2 left-3 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase flex items-center gap-1 ${
                  safety.safety_score >= 65 ? 'bg-emerald-500 text-zinc-900' :
                  safety.safety_score >= 40 ? 'bg-yellow-500 text-zinc-900' :
                  'bg-red-500 text-white'
                }`}>
                  <ShieldCheck size={9} weight="bold" /> Safety {safety.grade}
                </div>
                <div className="grid grid-cols-4 gap-2 mt-1 mb-2">
                  <div className="text-center">
                    <p data-testid="val-safety-score" className={`text-sm font-bold font-mono ${
                      safety.safety_score >= 65 ? 'text-emerald-500' : safety.safety_score >= 40 ? 'text-yellow-500' : 'text-red-500'
                    }`}>{safety.safety_score}/100</p>
                    <p className="text-[8px] text-zinc-500">Safety</p>
                  </div>
                  <div className="text-center">
                    <p data-testid="val-trades-per-day" className={`text-sm font-bold font-mono ${
                      safety.metrics?.overtrading ? 'text-red-500' : 'text-white'
                    }`}>{safety.metrics?.trades_per_day}/d</p>
                    <p className="text-[8px] text-zinc-500">Frequency</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-bold font-mono text-yellow-500">{safety.metrics?.max_drawdown_pct?.toFixed(1)}%</p>
                    <p className="text-[8px] text-zinc-500">Max DD</p>
                  </div>
                  <div className="text-center">
                    <p className={`text-sm font-bold font-mono ${safety.metrics?.consecutive_losses > 5 ? 'text-red-500' : 'text-white'}`}>
                      {safety.metrics?.consecutive_losses}
                    </p>
                    <p className="text-[8px] text-zinc-500">Consec Loss</p>
                  </div>
                </div>
                {safety.flags && safety.flags.length > 0 && (
                  <div className="flex flex-col gap-1 mb-1">
                    {safety.flags.map((f, i) => (
                      <div key={i} data-testid={`val-safety-flag-${i}`} className="flex items-center gap-1.5 text-[9px] font-mono text-red-400">
                        <Warning size={10} weight="bold" className="text-red-500 flex-shrink-0" />
                        {f}
                      </div>
                    ))}
                  </div>
                )}
                {safety.warnings && safety.warnings.length > 0 && (
                  <div className="flex flex-col gap-1">
                    {safety.warnings.map((w, i) => (
                      <div key={i} className="text-[9px] font-mono text-yellow-500">{w}</div>
                    ))}
                  </div>
                )}
                <div className="mt-2 pt-2 border-t border-zinc-800/50 flex flex-wrap gap-2 text-[9px] font-mono text-zinc-500">
                  <span>DD: <strong className="text-zinc-300">{safety.score_breakdown?.drawdown_control}/30</strong></span>
                  <span>Freq: <strong className="text-zinc-300">{safety.score_breakdown?.trade_frequency}/25</strong></span>
                  <span>Risk: <strong className="text-zinc-300">{safety.score_breakdown?.risk_exposure}/25</strong></span>
                  <span>Consec: <strong className="text-zinc-300">{safety.score_breakdown?.consecutive_loss}/20</strong></span>
                </div>
              </div>
            )}

            {/* ═══ MONTE CARLO SECTION ═══ */}
            {mc?.success && (
              <div data-testid="monte-carlo-section" className={`rounded-md p-3 relative border ${
                mc.score >= 60 ? 'border-violet-500/30 bg-violet-500/5' :
                mc.score >= 40 ? 'border-yellow-500/30 bg-yellow-500/5' :
                'border-red-500/30 bg-red-500/5'
              }`}>
                <div className={`absolute -top-2 left-3 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase flex items-center gap-1 ${
                  mc.score >= 60 ? 'bg-violet-500 text-white' :
                  mc.score >= 40 ? 'bg-yellow-500 text-zinc-900' :
                  'bg-red-500 text-white'
                }`}>
                  <Shuffle size={9} weight="bold" /> Monte Carlo {mc.grade}
                </div>

                {/* Top metrics */}
                <div className="grid grid-cols-4 gap-2 mt-1">
                  <MiniMetric testId="mc-score" label="MC Score" value={`${mc.score}/100`}
                    color={mc.score >= 60 ? 'text-violet-400' : mc.score >= 40 ? 'text-yellow-500' : 'text-red-500'} />
                  <MiniMetric testId="mc-prob-profit" label="Profit Prob" value={`${mc.statistics.prob_profit}%`}
                    color={mc.statistics.prob_profit >= 70 ? 'text-emerald-500' : mc.statistics.prob_profit >= 50 ? 'text-yellow-500' : 'text-red-500'} />
                  <MiniMetric testId="mc-mean-return" label="Avg Return" value={`${mc.statistics.mean_return >= 0 ? '+' : ''}${mc.statistics.mean_return}%`}
                    color={profitColor(mc.statistics.mean_return)} />
                  <MiniMetric testId="mc-worst-dd" label="Worst DD" value={`${mc.statistics.worst_drawdown}%`}
                    color="text-yellow-500" />
                </div>

                {/* 95% Confidence interval */}
                <div className="mt-3 flex flex-col gap-1.5">
                  <span className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider">95% Confidence Interval</span>
                  <CIBar lower={mc.confidence_95.return_lower} upper={mc.confidence_95.return_upper} label="Return" />
                  <CIBar lower={mc.confidence_95.drawdown_lower} upper={mc.confidence_95.drawdown_upper} label="Max DD" />
                </div>

                {/* Distribution percentiles */}
                {mc.distribution && (
                  <div className="mt-2 flex items-center gap-1 text-[9px] font-mono text-zinc-500">
                    <span className="text-zinc-600">P5:</span>
                    <span className={profitColor(mc.distribution.p5)}>{mc.distribution.p5}%</span>
                    <span className="text-zinc-700 mx-0.5">|</span>
                    <span className="text-zinc-600">P25:</span>
                    <span className={profitColor(mc.distribution.p25)}>{mc.distribution.p25}%</span>
                    <span className="text-zinc-700 mx-0.5">|</span>
                    <span className="text-zinc-600">P50:</span>
                    <span className={profitColor(mc.distribution.p50)}>{mc.distribution.p50}%</span>
                    <span className="text-zinc-700 mx-0.5">|</span>
                    <span className="text-zinc-600">P75:</span>
                    <span className={profitColor(mc.distribution.p75)}>{mc.distribution.p75}%</span>
                    <span className="text-zinc-700 mx-0.5">|</span>
                    <span className="text-zinc-600">P95:</span>
                    <span className={profitColor(mc.distribution.p95)}>{mc.distribution.p95}%</span>
                  </div>
                )}

                {/* Score breakdown */}
                <div className="mt-2 flex flex-wrap gap-2 text-[9px] font-mono text-zinc-500">
                  <span>Consist: <strong className="text-zinc-300">{mc.score_breakdown.consistency}/30</strong></span>
                  <span>Stable: <strong className="text-zinc-300">{mc.score_breakdown.return_stability}/25</strong></span>
                  <span>DD Ctrl: <strong className="text-zinc-300">{mc.score_breakdown.drawdown_control}/25</strong></span>
                  <span>Conf: <strong className="text-zinc-300">{mc.score_breakdown.confidence}/20</strong></span>
                </div>
              </div>
            )}

            {mc && !mc.success && mc.error && (
              <div data-testid="mc-insufficient" className="flex items-center gap-2 bg-zinc-800/50 border border-zinc-800 rounded-md p-2.5">
                <Shuffle size={14} className="text-zinc-500 flex-shrink-0" />
                <span className="text-[11px] font-mono text-zinc-500">{mc.error}</span>
              </div>
            )}

            {/* Overfit Warning */}
            {result.overfit_warning && (
              <div data-testid="overfit-warning" className="flex items-center gap-2 bg-red-500/5 border border-red-500/20 rounded-md p-2.5">
                <Warning size={14} weight="bold" className="text-red-500 flex-shrink-0" />
                <span className="text-[11px] font-mono text-red-400">{result.overfit_warning}</span>
              </div>
            )}

            {/* Segments Table */}
            {segments.length > 0 && (
              <div data-testid="segments-table" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                <div className="px-3 py-2 border-b border-zinc-800">
                  <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Walk-Forward</span>
                </div>
                <table className="w-full text-[11px] font-mono">
                  <thead>
                    <tr className="text-zinc-500 border-b border-zinc-800">
                      <th className="text-left px-3 py-1.5">Seg</th>
                      <th className="text-right px-2 py-1.5">Candles</th>
                      <th className="text-right px-2 py-1.5">Return</th>
                      <th className="text-right px-2 py-1.5">WR</th>
                      <th className="text-right px-2 py-1.5">DD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {segments.map((s) => (
                      <tr key={s.segment} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                        <td className="px-3 py-1.5 text-zinc-600">#{s.segment}</td>
                        <td className="text-right px-2 py-1.5 text-zinc-400">{s.candles}</td>
                        <td className={`text-right px-2 py-1.5 font-semibold ${profitColor(s.total_return_pct)}`}>
                          {s.total_return_pct >= 0 ? '+' : ''}{s.total_return_pct.toFixed(2)}%
                        </td>
                        <td className={`text-right px-2 py-1.5 ${s.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{s.win_rate}%</td>
                        <td className="text-right px-2 py-1.5 text-yellow-500">{s.max_drawdown_pct.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-3 py-2 border-t border-zinc-800/50">
                  <div className="flex items-end gap-1 h-10">
                    {segments.map((s) => {
                      const maxAbs = Math.max(...segments.map(sg => Math.abs(sg.total_return_pct)), 0.1);
                      const pct = (Math.abs(s.total_return_pct) / maxAbs) * 100;
                      return (
                        <div key={s.segment} className="flex-1 flex flex-col items-center justify-end h-full">
                          <div className={`w-full min-h-[2px] rounded-sm ${s.total_return_pct >= 0 ? 'bg-emerald-500/60' : 'bg-red-500/60'}`}
                            style={{ height: `${Math.max(pct, 4)}%` }} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Train / Test */}
            {tt && (tt.train || tt.test) && (
              <div data-testid="train-test-comparison" className="grid grid-cols-2 gap-3">
                {tt.train && (
                  <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                    <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Train (70%) &middot; {tt.train.candles}</p>
                    <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                      <span className={profitColor(tt.train.total_return_pct)}>{tt.train.total_return_pct >= 0 ? '+' : ''}{tt.train.total_return_pct.toFixed(2)}%</span>
                      <span className="text-zinc-500">WR: <strong className="text-white">{tt.train.win_rate}%</strong></span>
                    </div>
                  </div>
                )}
                {tt.test && (
                  <div className={`rounded-md p-3 border ${tt.test.net_profit >= 0 ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-red-500/20 bg-red-500/5'}`}>
                    <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Test (30%) &middot; {tt.test.candles}</p>
                    <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                      <span className={profitColor(tt.test.total_return_pct)}>{tt.test.total_return_pct >= 0 ? '+' : ''}{tt.test.total_return_pct.toFixed(2)}%</span>
                      <span className="text-zinc-500">WR: <strong className="text-white">{tt.test.win_rate}%</strong></span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
