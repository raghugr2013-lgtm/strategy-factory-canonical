import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ChartPieSlice, CircleNotch, CheckCircle, Warning,
  ArrowRight, Lightning, Sliders, CaretDown, Pulse, TrendUp, TrendDown,
  ClockCounterClockwise, Funnel, X, Repeat, Play, Power
} from '@phosphor-icons/react';
import { getStrategies, analyzePortfolio, autoBuildPortfolio, getLiveAllocation, getAllocationHistory, getRebalanceConfig, saveRebalanceConfig, runRebalance, getRebalanceStatus } from '../services/api';
import PortfolioIntelligence from './PortfolioIntelligence';
import { useMarketUniverse } from '../hooks/useMarketUniverse';

function RiskGradeBadge({ grade, score }) {
  const cfg = {
    A: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20' },
    B: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
    C: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20' },
    D: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/20' },
    F: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20' },
  };
  const c = cfg[grade] || cfg.C;
  return (
    <div data-testid="portfolio-risk-grade" className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border ${c.bg} ${c.text} ${c.border}`}>
      <span className="text-lg font-bold font-mono">{grade}</span>
      <span className="text-[9px] font-mono opacity-75">Risk {score}/100</span>
    </div>
  );
}

function CorrCell({ value }) {
  const abs = Math.abs(value);
  const color = abs > 0.7 ? 'text-red-500' : abs > 0.4 ? 'text-yellow-500' : 'text-emerald-500';
  const bg = abs > 0.7 ? 'bg-red-500/10' : abs > 0.4 ? 'bg-yellow-500/5' : '';
  return <td className={`px-2 py-1.5 text-center text-[10px] font-mono font-bold ${color} ${bg}`}>{value.toFixed(2)}</td>;
}

function StatusBadge({ status }) {
  const cfg = {
    READY: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20' },
    MODERATE: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20' },
    RISKY: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20' },
  };
  const c = cfg[status] || cfg.RISKY;
  return <span className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>{status}</span>;
}

/* ── Shared portfolio results display ── */
function PortfolioResults({ r }) {
  if (!r) return null;
  const cm = r.combined_metrics || {};
  const ss = r.strategies_summary || [];
  const corr = r.correlation_matrix || [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <RiskGradeBadge grade={r.diversification_grade} score={r.portfolio_risk_score} />
        <div>
          <p className="text-[10px] font-mono text-zinc-500">{r.num_strategies} strategies, avg corr: {r.avg_correlation}</p>
        </div>
      </div>

      <div data-testid="portfolio-combined-metrics" className="grid grid-cols-4 gap-2">
        <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
          <p className={`text-sm font-bold font-mono ${cm.total_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${cm.total_profit?.toFixed(0)}</p>
          <p className="text-[7px] text-zinc-500 uppercase">Profit</p>
        </div>
        <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
          <p className={`text-sm font-bold font-mono ${cm.total_return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{cm.total_return_pct?.toFixed(1)}%</p>
          <p className="text-[7px] text-zinc-500 uppercase">Return</p>
        </div>
        <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
          <p className="text-sm font-bold font-mono text-yellow-500">{cm.max_drawdown_pct?.toFixed(1)}%</p>
          <p className="text-[7px] text-zinc-500 uppercase">Max DD</p>
        </div>
        <div className="bg-zinc-950 border border-zinc-800 rounded p-2 text-center">
          <p className="text-sm font-bold font-mono text-zinc-300">{cm.volatility}</p>
          <p className="text-[7px] text-zinc-500 uppercase">Volatility</p>
        </div>
      </div>

      <div className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5">
        <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Risk Breakdown</p>
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <span className="text-zinc-500">Corr: <strong className="text-zinc-300">{r.risk_breakdown?.correlation_penalty}/40</strong></span>
          <span className="text-zinc-500">DD: <strong className="text-zinc-300">{r.risk_breakdown?.drawdown_penalty}/40</strong></span>
          <span className="text-zinc-500">Vol: <strong className="text-zinc-300">{r.risk_breakdown?.volatility_penalty}/20</strong></span>
        </div>
      </div>

      {r.combined_equity && r.combined_equity.length > 1 && (
        <div data-testid="portfolio-equity-curve" className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5">
          <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Combined Equity</p>
          <div className="h-14 flex items-end gap-px">
            {r.combined_equity.map((val, i) => {
              const mn = Math.min(...r.combined_equity);
              const mx = Math.max(...r.combined_equity);
              const range = mx - mn || 1;
              const pct = ((val - mn) / range) * 100;
              return (
                <div key={i} className="flex-1 min-w-[1px]" style={{ height: `${Math.max(pct, 3)}%` }}>
                  <div className={`w-full h-full rounded-sm ${val >= r.combined_equity[0] ? 'bg-emerald-500/50' : 'bg-red-500/50'}`} />
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-1 text-[8px] font-mono text-zinc-600">
            <span>${r.combined_equity[0]?.toLocaleString()}</span>
            <span>${r.combined_equity[r.combined_equity.length - 1]?.toLocaleString()}</span>
          </div>
        </div>
      )}

      {corr.length > 1 && (
        <div data-testid="portfolio-correlation" className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5 overflow-x-auto">
          <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Correlation Matrix</p>
          <table className="w-full text-[10px] font-mono">
            <thead><tr>
              <th className="px-2 py-1 text-zinc-600"></th>
              {ss.map((s, i) => <th key={i} className="px-2 py-1 text-zinc-500 text-center">{s.pair}<br /><span className="text-[8px] text-zinc-600">{s.timeframe}</span></th>)}
            </tr></thead>
            <tbody>
              {corr.map((row, i) => (
                <tr key={i}>
                  <td className="px-2 py-1.5 text-zinc-500 text-[9px]">{ss[i]?.pair}/{ss[i]?.timeframe}</td>
                  {row.map((val, j) => i === j ? (
                    <td key={j} className="px-2 py-1.5 text-center text-[10px] font-mono text-zinc-700">1.00</td>
                  ) : <CorrCell key={j} value={val} />)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div data-testid="portfolio-allocations" className="bg-zinc-950 border border-zinc-800 rounded-md p-2.5">
        <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Allocation</p>
        <div className="flex flex-col gap-1">
          {ss.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
              <span className="text-zinc-400 w-24 truncate">{s.pair}/{s.timeframe}</span>
              <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-yellow-500/60 rounded-full" style={{ width: `${(s.allocation || 0) * 100}%` }} />
              </div>
              <span className="text-zinc-300 w-10 text-right">{((s.allocation || 0) * 100).toFixed(0)}%</span>
              {s.suggested_allocation !== s.allocation && (
                <span className="text-[8px] text-zinc-600"><ArrowRight size={7} className="inline" /> {((s.suggested_allocation || 0) * 100).toFixed(0)}%</span>
              )}
            </div>
          ))}
        </div>
        <p className="text-[8px] font-mono text-zinc-600 mt-1">Suggested: inverse-DD weighting</p>
      </div>

      {r.warnings && r.warnings.length > 0 && (
        <div data-testid="portfolio-warnings" className="flex flex-col gap-1">
          {r.warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-1.5 text-[9px] font-mono text-yellow-500">
              <Warning size={10} weight="bold" className="flex-shrink-0" /> {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PortfolioPanel() {
  // R4 — registry-backed portfolio pair list.
  const { options: PORTFOLIO_PAIRS } = useMarketUniverse({ eligibility: 'portfolio' });
  const [mode, setMode] = useState('manual'); // 'manual' | 'auto' | 'live'
  const [strategies, setStrategies] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [listLoading, setListLoading] = useState(false);

  // Auto-build state
  const [abLoading, setAbLoading] = useState(false);
  const [abResult, setAbResult] = useState(null);
  const [abError, setAbError] = useState(null);
  const [abSize, setAbSize] = useState(4);
  const [abMaxCorr, setAbMaxCorr] = useState(0.6);
  const [abMinScore, setAbMinScore] = useState(0);
  const [abMinSafety, setAbMinSafety] = useState(0);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Live allocation state
  const [laLoading, setLaLoading] = useState(false);
  const [laResult, setLaResult] = useState(null);
  const [laError, setLaError] = useState(null);
  const [laSelected, setLaSelected] = useState([]);
  const [laSafetyAdj, setLaSafetyAdj] = useState(true);
  const [laStableW, setLaStableW] = useState(100);
  const [laWarningW, setLaWarningW] = useState(50);
  const [laFailingW, setLaFailingW] = useState(0);
  const [laAutoRefresh, setLaAutoRefresh] = useState(true);
  const laIntervalRef = useRef(null);

  // Allocation History state
  const [liveSubTab, setLiveSubTab] = useState('allocate'); // 'allocate' | 'history' | 'rebalance'
  const [histData, setHistData] = useState(null);
  const [histLoading, setHistLoading] = useState(false);
  const [histError, setHistError] = useState(null);
  const [histFilterSymbol, setHistFilterSymbol] = useState('');
  const [histFilterTf, setHistFilterTf] = useState('');
  const [histFilterStrategy, setHistFilterStrategy] = useState('');

  // Rebalance state
  const [rbConfig, setRbConfig] = useState(null);
  const [rbStatus, setRbStatus] = useState(null);
  const [rbLoading, setRbLoading] = useState(false);
  const [rbRunning, setRbRunning] = useState(false);
  const [rbError, setRbError] = useState(null);
  const [rbLastResult, setRbLastResult] = useState(null);
  const rbIntervalRef = useRef(null);
  const fetchHistory = useCallback(async () => {
    setHistLoading(true); setHistError(null);
    try {
      const filters = {};
      if (histFilterSymbol) filters.symbol = histFilterSymbol;
      if (histFilterTf) filters.timeframe = histFilterTf;
      if (histFilterStrategy) filters.strategy_id = histFilterStrategy;
      filters.limit = 50;
      const data = await getAllocationHistory(filters);
      setHistData(data);
    } catch (e) { setHistError(e.message); }
    finally { setHistLoading(false); }
  }, [histFilterSymbol, histFilterTf, histFilterStrategy]);

  const fetchRbData = useCallback(async () => {
    setRbLoading(true); setRbError(null);
    try {
      const [cfg, st] = await Promise.all([getRebalanceConfig(), getRebalanceStatus()]);
      setRbConfig(cfg);
      setRbStatus(st);
    } catch (e) { setRbError(e.message); }
    finally { setRbLoading(false); }
  }, []);

  const handleSaveRbConfig = async (updates) => {
    try {
      const newCfg = { ...rbConfig, ...updates };
      await saveRebalanceConfig(newCfg);
      setRbConfig(newCfg);
    } catch (e) { setRbError(e.message); }
  };

  const handleRunRebalance = async (reason = 'manual') => {
    setRbRunning(true); setRbError(null); setRbLastResult(null);
    try {
      const result = await runRebalance(reason);
      setRbLastResult(result);
      await fetchRbData();
    } catch (e) { setRbError(e.message); }
    finally { setRbRunning(false); }
  };

  const fetchStrategies = useCallback(async () => {
    setListLoading(true);
    try {
      const data = await getStrategies({ sort_by: 'score', sort_dir: 'desc' });
      setStrategies(data.strategies || []);
    } catch (e) { console.error(e); }
    finally { setListLoading(false); }
  }, []);

  useEffect(() => { fetchStrategies(); }, [fetchStrategies]);

  const toggleSelect = (id) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 10 ? [...prev, id] : prev);
    setResult(null);
  };

  const handleAnalyze = async () => {
    if (selected.length < 2) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await analyzePortfolio(selected);
      setResult(data.portfolio);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleAutoBuild = async () => {
    setAbLoading(true); setAbError(null); setAbResult(null);
    try {
      const data = await autoBuildPortfolio({
        target_size: abSize,
        max_pair_corr: abMaxCorr,
        min_score: abMinScore,
        min_safety: abMinSafety,
      });
      setAbResult(data);
      // Also select these strategies in manual mode
      if (data.selected_ids) {
        setSelected(data.selected_ids.filter(Boolean));
      }
    } catch (e) { setAbError(e.message); }
    finally { setAbLoading(false); }
  };

  const toggleLaSelect = (id) => {
    setLaSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 10 ? [...prev, id] : prev);
    setLaResult(null);
  };

  const handleLiveAllocation = async () => {
    if (laSelected.length < 2) return;
    setLaLoading(true); setLaError(null); setLaResult(null);
    try {
      const data = await getLiveAllocation(laSelected, {
        alloc_rules: {
          STABLE: laStableW / 100,
          WARNING: laWarningW / 100,
          FAILING: laFailingW / 100,
          AUTO_DISABLED: 0,
        },
        use_safety_adjustment: laSafetyAdj,
      });
      setLaResult(data);
    } catch (e) { setLaError(e.message); }
    finally { setLaLoading(false); }
  };

  // Auto-refresh for Live Allocation (60s)
  useEffect(() => {
    if (laIntervalRef.current) clearInterval(laIntervalRef.current);
    if (mode === 'live' && laAutoRefresh && laSelected.length >= 2 && laResult) {
      laIntervalRef.current = setInterval(() => {
        handleLiveAllocation();
      }, 60000);
    }
    return () => { if (laIntervalRef.current) clearInterval(laIntervalRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, laAutoRefresh, laSelected, laResult]);

  // Fetch history when switching to history sub-tab
  useEffect(() => {
    if (mode === 'live' && liveSubTab === 'history') fetchHistory();
    if (mode === 'live' && liveSubTab === 'rebalance') fetchRbData();
  }, [mode, liveSubTab, fetchHistory, fetchRbData]);

  // Auto-rebalance interval
  useEffect(() => {
    if (rbIntervalRef.current) clearInterval(rbIntervalRef.current);
    if (mode === 'live' && rbConfig?.enabled && rbConfig?.interval_minutes > 0) {
      rbIntervalRef.current = setInterval(() => {
        handleRunRebalance('interval');
      }, rbConfig.interval_minutes * 60000);
    }
    return () => { if (rbIntervalRef.current) clearInterval(rbIntervalRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, rbConfig?.enabled, rbConfig?.interval_minutes]);

  const selectClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded px-2 py-1 text-[10px] font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none";
  const ab = abResult;
  const la = laResult;

  return (
    <div data-testid="portfolio-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="p-4 pb-0">
        <PortfolioIntelligence />
      </div>
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <div className="asf-legacy-title flex items-center gap-2 flex-1 min-w-0">
          <ChartPieSlice size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">Portfolio Risk Control</h2>
          <span className="ml-auto text-[10px] font-mono text-zinc-500">{strategies.length} in library</span>
        </div>
      </div>

      {/* Mode Tabs */}
      <div className="border-b border-zinc-800 flex">
        <button data-testid="mode-manual" onClick={() => setMode('manual')}
          className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'manual' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
          <ChartPieSlice size={11} /> Manual
        </button>
        <button data-testid="mode-auto-build" onClick={() => setMode('auto')}
          className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'auto' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
          <Lightning size={11} /> Auto Build
        </button>
        <button data-testid="mode-live-alloc" onClick={() => { setMode('live'); if (strategies.length === 0) fetchStrategies(); }}
          className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'live' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
          <Pulse size={11} /> Live Allocation
        </button>
      </div>

      <div className="p-4">
        {/* ═══════ MANUAL MODE ═══════ */}
        {mode === 'manual' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-2">Select Strategies (2-10)</p>
              {listLoading ? (
                <p className="text-xs font-mono text-zinc-500 animate-pulse py-4">Loading...</p>
              ) : strategies.length === 0 ? (
                <p className="text-xs font-mono text-zinc-600 py-4">No strategies in library.</p>
              ) : (
                <div className="flex flex-col gap-1 max-h-[300px] overflow-y-auto">
                  {strategies.map((s, i) => {
                    const isSel = selected.includes(s.id);
                    const m = s.metrics || s.backtest_results || {};
                    return (
                      <button key={s.id || i} data-testid={`portfolio-strat-${i}`}
                        onClick={() => s.id && toggleSelect(s.id)}
                        className={`text-left bg-zinc-950 border rounded-md px-3 py-2 flex items-center justify-between transition-colors ${
                          isSel ? 'border-yellow-500/50 bg-yellow-500/5' : 'border-zinc-800 hover:bg-zinc-800/50'
                        }`}>
                        <div className="flex items-center gap-2">
                          <span className={`w-4 h-4 rounded flex items-center justify-center border text-[9px] ${
                            isSel ? 'border-yellow-500 bg-yellow-500 text-zinc-900' : 'border-zinc-700 text-zinc-600'
                          }`}>{isSel ? <CheckCircle size={10} weight="bold" /> : ''}</span>
                          <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                          <span className="text-[10px] font-mono text-zinc-500">{s.timeframe}</span>
                          <span className="text-[9px] font-mono text-zinc-600">{(s.strategy_type || '').replace('_', ' ')}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                          <span className={`font-bold ${(s.score || 0) >= 50 ? 'text-emerald-500' : 'text-yellow-500'}`}>{s.score || 0}</span>
                          <span className={m.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}>${m.net_profit?.toFixed?.(0) || 0}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
              <button data-testid="analyze-portfolio-btn" onClick={handleAnalyze} disabled={selected.length < 2 || loading}
                className="mt-3 bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40 w-full justify-center">
                {loading ? <><CircleNotch size={14} className="animate-spin" /> Analyzing...</> : <><ChartPieSlice size={14} /> Analyze ({selected.length})</>}
              </button>
              {error && <p data-testid="portfolio-error" className="text-red-500 text-xs font-mono mt-2">{error}</p>}
            </div>
            <div>
              {!result && !loading && (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
                  <ChartPieSlice size={32} weight="thin" className="opacity-30 mb-2" />
                  <p className="text-sm">Select 2+ strategies and click Analyze</p>
                </div>
              )}
              {result && <PortfolioResults r={result} />}
            </div>
          </div>
        )}

        {/* ═══════ AUTO BUILD MODE ═══════ */}
        {mode === 'auto' && (
          <div className="flex flex-col gap-4">
            <div className="bg-zinc-950 border border-zinc-800 rounded-md p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm font-semibold text-white">Auto Portfolio Builder</p>
                  <p className="text-[10px] font-mono text-zinc-500">Automatically selects the best diversified combination from your library</p>
                </div>
                <Lightning size={20} className="text-yellow-500" />
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Portfolio Size</label>
                  <select data-testid="ab-size" value={abSize} onChange={e => setAbSize(Number(e.target.value))} className={selectClass + ' w-full'}>
                    {[2, 3, 4, 5, 6, 7].map(n => <option key={n} value={n}>{n} strategies</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Max Correlation</label>
                  <select data-testid="ab-max-corr" value={abMaxCorr} onChange={e => setAbMaxCorr(Number(e.target.value))} className={selectClass + ' w-full'}>
                    {[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map(v => <option key={v} value={v}>{v} ({v <= 0.4 ? 'strict' : v <= 0.6 ? 'moderate' : 'relaxed'})</option>)}
                  </select>
                </div>
              </div>

              <button data-testid="ab-toggle-advanced" onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-[10px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1 mb-2">
                <Sliders size={10} /> Advanced Filters <CaretDown size={8} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              </button>

              {showAdvanced && (
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Score</label>
                    <input data-testid="ab-min-score" type="number" min="0" max="100" value={abMinScore} onChange={e => setAbMinScore(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Safety</label>
                    <input data-testid="ab-min-safety" type="number" min="0" max="100" value={abMinSafety} onChange={e => setAbMinSafety(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                </div>
              )}

              <button data-testid="auto-build-btn" onClick={handleAutoBuild} disabled={abLoading}
                className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40 w-full justify-center">
                {abLoading ? <><CircleNotch size={14} className="animate-spin" /> Building...</> : <><Lightning size={14} /> Auto Build Portfolio</>}
              </button>
            </div>

            {abError && <p data-testid="ab-error" className="text-red-500 text-xs font-mono">{abError}</p>}

            {ab && (
              <div className="flex flex-col gap-3">
                {/* Selection Summary */}
                <div data-testid="ab-summary" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                  <div className="grid grid-cols-3 gap-2 text-center mb-2">
                    <div>
                      <p className="text-lg font-bold font-mono text-zinc-400">{ab.num_candidates}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Candidates</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-zinc-300">{ab.num_viable}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Viable</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-emerald-500">{ab.num_selected}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Selected</p>
                    </div>
                  </div>
                </div>

                {/* Selection Log */}
                {ab.selection_log && ab.selection_log.length > 0 && (
                  <details className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                    <summary className="px-3 py-2 text-[10px] font-medium text-zinc-500 uppercase tracking-wider cursor-pointer hover:text-zinc-300">
                      Selection Log ({ab.selection_log.length} steps)
                    </summary>
                    <div className="px-3 pb-3 max-h-[160px] overflow-y-auto">
                      {ab.selection_log.map((line, i) => (
                        <p key={i} className={`text-[9px] font-mono ${
                          line.startsWith('Seed') || line.startsWith('Added') ? 'text-emerald-500' :
                          line.startsWith('Skip') ? 'text-yellow-500' : 'text-zinc-600'
                        }`}>{line}</p>
                      ))}
                    </div>
                  </details>
                )}

                {/* Full Portfolio Results */}
                {ab.portfolio && <PortfolioResults r={ab.portfolio} />}
              </div>
            )}
          </div>
        )}

        {/* ═══════ LIVE ALLOCATION MODE ═══════ */}
        {mode === 'live' && (
          <div data-testid="la-content" className="flex flex-col gap-4">
            {/* Sub-tabs: Allocate | History | Rebalance */}
            <div className="flex gap-1 bg-zinc-950 rounded-md p-0.5 w-fit">
              <button data-testid="la-sub-allocate" onClick={() => setLiveSubTab('allocate')}
                className={`px-3 py-1.5 text-[10px] font-medium rounded transition-colors flex items-center gap-1.5 ${liveSubTab === 'allocate' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
                <Pulse size={10} /> Allocate
              </button>
              <button data-testid="la-sub-history" onClick={() => setLiveSubTab('history')}
                className={`px-3 py-1.5 text-[10px] font-medium rounded transition-colors flex items-center gap-1.5 ${liveSubTab === 'history' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
                <ClockCounterClockwise size={10} /> History
              </button>
              <button data-testid="la-sub-rebalance" onClick={() => setLiveSubTab('rebalance')}
                className={`px-3 py-1.5 text-[10px] font-medium rounded transition-colors flex items-center gap-1.5 ${liveSubTab === 'rebalance' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
                <Repeat size={10} /> Rebalance
              </button>
            </div>

            {/* ── ALLOCATE SUB-TAB ── */}
            {liveSubTab === 'allocate' && (<>
            {/* Config + Strategy Selection */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Left: Strategy Selection */}
              <div>
                <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-2">Select Strategies (2-10)</p>
                {listLoading ? (
                  <p className="text-xs font-mono text-zinc-500 animate-pulse py-4">Loading...</p>
                ) : strategies.length === 0 ? (
                  <p className="text-xs font-mono text-zinc-600 py-4">No strategies in library.</p>
                ) : (
                  <div className="flex flex-col gap-1 max-h-[260px] overflow-y-auto">
                    {strategies.map((s, i) => {
                      const isSel = laSelected.includes(s.id);
                      const m = s.metrics || s.backtest_results || {};
                      return (
                        <button key={s.id || i} data-testid={`la-strat-${i}`}
                          onClick={() => s.id && toggleLaSelect(s.id)}
                          className={`text-left bg-zinc-950 border rounded-md px-3 py-2 flex items-center justify-between transition-colors ${
                            isSel ? 'border-yellow-500/50 bg-yellow-500/5' : 'border-zinc-800 hover:bg-zinc-800/50'
                          }`}>
                          <div className="flex items-center gap-2">
                            <span className={`w-4 h-4 rounded flex items-center justify-center border text-[9px] ${
                              isSel ? 'border-yellow-500 bg-yellow-500 text-zinc-900' : 'border-zinc-700 text-zinc-600'
                            }`}>{isSel ? <CheckCircle size={10} weight="bold" /> : ''}</span>
                            <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                            <span className="text-[10px] font-mono text-zinc-500">{s.timeframe}</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] font-mono">
                            <span className={`font-bold ${(s.score || 0) >= 50 ? 'text-emerald-500' : 'text-yellow-500'}`}>{s.score || 0}</span>
                            <span className={m.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}>${m.net_profit?.toFixed?.(0) || 0}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Right: Allocation Config */}
              <div className="flex flex-col gap-3">
                <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                  <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Allocation Rules</p>
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <CheckCircle size={12} className="text-emerald-500" />
                        <span className="text-[10px] font-mono text-emerald-400">STABLE</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input data-testid="la-stable-weight" type="range" min="0" max="100" step="10" value={laStableW}
                          onChange={e => setLaStableW(Number(e.target.value))}
                          className="w-20 h-1 accent-emerald-500 bg-zinc-800 rounded-full appearance-none cursor-pointer" />
                        <span className="text-[10px] font-mono text-emerald-400 w-8 text-right">{laStableW}%</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Warning size={12} className="text-yellow-500" />
                        <span className="text-[10px] font-mono text-yellow-400">WARNING</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input data-testid="la-warning-weight" type="range" min="0" max="100" step="10" value={laWarningW}
                          onChange={e => setLaWarningW(Number(e.target.value))}
                          className="w-20 h-1 accent-yellow-500 bg-zinc-800 rounded-full appearance-none cursor-pointer" />
                        <span className="text-[10px] font-mono text-yellow-400 w-8 text-right">{laWarningW}%</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Warning size={12} weight="bold" className="text-red-500" />
                        <span className="text-[10px] font-mono text-red-400">FAILING</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input data-testid="la-failing-weight" type="range" min="0" max="100" step="10" value={laFailingW}
                          onChange={e => setLaFailingW(Number(e.target.value))}
                          className="w-20 h-1 accent-red-500 bg-zinc-800 rounded-full appearance-none cursor-pointer" />
                        <span className="text-[10px] font-mono text-red-400 w-8 text-right">{laFailingW}%</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3 flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-mono text-zinc-400">Safety Adjustment</p>
                    <p className="text-[8px] font-mono text-zinc-600">Reduce allocation for high drawdown</p>
                  </div>
                  <button data-testid="la-safety-toggle" onClick={() => setLaSafetyAdj(!laSafetyAdj)}
                    className={`w-9 h-5 rounded-full transition-colors relative ${laSafetyAdj ? 'bg-emerald-500' : 'bg-zinc-700'}`}>
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${laSafetyAdj ? 'left-[18px]' : 'left-0.5'}`} />
                  </button>
                </div>

                <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3 flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-mono text-zinc-400">Auto-Refresh (60s)</p>
                    <p className="text-[8px] font-mono text-zinc-600">Periodically re-fetch allocations</p>
                  </div>
                  <button data-testid="la-autorefresh-toggle" onClick={() => setLaAutoRefresh(!laAutoRefresh)}
                    className={`w-9 h-5 rounded-full transition-colors relative ${laAutoRefresh ? 'bg-emerald-500' : 'bg-zinc-700'}`}>
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${laAutoRefresh ? 'left-[18px]' : 'left-0.5'}`} />
                  </button>
                </div>
              </div>
            </div>

            {/* Compute Button */}
            <button data-testid="la-compute-btn" onClick={handleLiveAllocation} disabled={laSelected.length < 2 || laLoading}
              className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40 w-full justify-center">
              {laLoading ? <><CircleNotch size={14} className="animate-spin" /> Computing...</> : <><Pulse size={14} /> Compute Live Allocation ({laSelected.length})</>}
            </button>

            {laError && <p data-testid="la-error" className="text-red-500 text-xs font-mono">{laError}</p>}

            {/* Results */}
            {la && (
              <div className="flex flex-col gap-3">
                {/* Summary Bar */}
                <div data-testid="la-summary" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div>
                      <p className="text-lg font-bold font-mono text-zinc-300">{la.num_strategies}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Strategies</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-emerald-500">{la.summary?.active_strategies || 0}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Active</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-yellow-500">{la.summary?.reduced_count || 0}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Reduced</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-red-500">{la.summary?.zero_allocation_count || 0}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Disabled</p>
                    </div>
                  </div>
                </div>

                {/* Per-Strategy Allocation Bars */}
                <div data-testid="la-allocations" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider">Per-Strategy Allocation</p>
                    {laAutoRefresh && laResult && (
                      <span className="flex items-center gap-1 text-[8px] font-mono text-zinc-600">
                        <CircleNotch size={9} className="animate-spin" style={{ animationDuration: '4s' }} /> Auto-refresh
                      </span>
                    )}
                  </div>
                  <div className="flex flex-col gap-2">
                    {(la.adjustments || []).map((a, i) => {
                      const statusCfg = {
                        STABLE: { barBg: 'bg-emerald-500/70', textColor: 'text-emerald-400', borderColor: 'border-emerald-500/30', icon: <CheckCircle size={11} weight="bold" /> },
                        WARNING: { barBg: 'bg-yellow-500/70', textColor: 'text-yellow-400', borderColor: 'border-yellow-500/30', icon: <Warning size={11} weight="bold" /> },
                        FAILING: { barBg: 'bg-red-500/70', textColor: 'text-red-400', borderColor: 'border-red-500/30', icon: <Warning size={11} weight="bold" /> },
                        AUTO_DISABLED: { barBg: 'bg-zinc-700/50', textColor: 'text-zinc-500', borderColor: 'border-zinc-700/30', icon: <Warning size={11} weight="bold" /> },
                      };
                      const sc = statusCfg[a.status] || statusCfg.STABLE;
                      const allocPct = (a.allocation * 100).toFixed(1);
                      const isReduced = a.reduced;
                      const isDisabled = a.allocation < 0.001;

                      return (
                        <div key={a.strategy_id || i} data-testid={`la-row-${i}`}
                          className={`bg-zinc-900/50 border rounded-md p-2.5 ${isDisabled ? 'border-red-500/20 opacity-60' : isReduced ? sc.borderColor : 'border-zinc-800'}`}>
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{a.pair}</span>
                              <span className="text-[10px] font-mono text-zinc-500">{a.timeframe}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${sc.textColor}`}>
                                {sc.icon} {a.status}
                              </span>
                              <span className={`text-sm font-bold font-mono ${isDisabled ? 'text-red-500' : isReduced ? 'text-yellow-400' : 'text-emerald-400'}`}>
                                {allocPct}%
                              </span>
                            </div>
                          </div>

                          {/* Allocation Bar */}
                          <div className="h-2.5 bg-zinc-800 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full transition-all duration-500 ${sc.barBg}`}
                              style={{ width: `${Math.max(a.allocation * 100, 0.5)}%` }} />
                          </div>

                          {/* Detail Row */}
                          <div className="flex items-center gap-3 mt-1.5 text-[9px] font-mono text-zinc-600">
                            <span>Base: {(a.base_weight * 100).toFixed(0)}%</span>
                            <span>Status x{a.status_multiplier}</span>
                            <span>Safety x{a.safety_multiplier}</span>
                            {a.live_dd > 0 && <span className="text-yellow-600">DD: {a.live_dd.toFixed(1)}%</span>}
                            {a.consecutive_failures > 0 && <span className="text-red-600">Fails: {a.consecutive_failures}</span>}
                            {a.direction !== 'UNCHANGED' && (
                              <span className={a.direction === 'INCREASED' ? 'text-emerald-600' : 'text-red-600'}>
                                {a.direction === 'INCREASED' ? <TrendUp size={9} className="inline" /> : <TrendDown size={9} className="inline" />}
                                {' '}{a.direction}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Equal vs Dynamic Comparison */}
                {la.equal_portfolio && la.dynamic_portfolio && (
                  <div data-testid="la-comparison" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                    <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Dynamic vs Equal Allocation</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="border border-zinc-800 rounded-md p-2">
                        <p className="text-[8px] font-bold text-zinc-500 uppercase mb-1.5">Dynamic (Live)</p>
                        <div className="grid grid-cols-2 gap-1.5">
                          <div>
                            <p className={`text-xs font-bold font-mono ${la.dynamic_portfolio?.combined_metrics?.total_profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              ${la.dynamic_portfolio?.combined_metrics?.total_profit?.toFixed(0) || 0}
                            </p>
                            <p className="text-[7px] text-zinc-600">Profit</p>
                          </div>
                          <div>
                            <p className="text-xs font-bold font-mono text-yellow-400">
                              {la.dynamic_portfolio?.combined_metrics?.max_drawdown_pct?.toFixed(1) || 0}%
                            </p>
                            <p className="text-[7px] text-zinc-600">Max DD</p>
                          </div>
                          <div>
                            <p className={`text-xs font-bold font-mono ${la.dynamic_portfolio?.combined_metrics?.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {la.dynamic_portfolio?.combined_metrics?.total_return_pct?.toFixed(1) || 0}%
                            </p>
                            <p className="text-[7px] text-zinc-600">Return</p>
                          </div>
                          <div>
                            <p className="text-xs font-bold font-mono text-zinc-300">
                              {la.dynamic_portfolio?.portfolio_risk_score || 0}
                            </p>
                            <p className="text-[7px] text-zinc-600">Risk Score</p>
                          </div>
                        </div>
                      </div>
                      <div className="border border-zinc-800 rounded-md p-2">
                        <p className="text-[8px] font-bold text-zinc-500 uppercase mb-1.5">Equal Weight</p>
                        <div className="grid grid-cols-2 gap-1.5">
                          <div>
                            <p className={`text-xs font-bold font-mono ${la.equal_portfolio?.total_profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              ${la.equal_portfolio?.total_profit?.toFixed(0) || 0}
                            </p>
                            <p className="text-[7px] text-zinc-600">Profit</p>
                          </div>
                          <div>
                            <p className="text-xs font-bold font-mono text-yellow-400">
                              {la.equal_portfolio?.max_drawdown_pct?.toFixed(1) || 0}%
                            </p>
                            <p className="text-[7px] text-zinc-600">Max DD</p>
                          </div>
                          <div>
                            <p className={`text-xs font-bold font-mono ${la.equal_portfolio?.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {la.equal_portfolio?.total_return_pct?.toFixed(1) || 0}%
                            </p>
                            <p className="text-[7px] text-zinc-600">Return</p>
                          </div>
                          <div>
                            <p className="text-xs font-bold font-mono text-zinc-300">
                              {la.equal_portfolio?.risk_score || 0}
                            </p>
                            <p className="text-[7px] text-zinc-600">Risk Score</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Dynamic Portfolio Full Results */}
                {la.dynamic_portfolio && <PortfolioResults r={la.dynamic_portfolio} />}
              </div>
            )}
            </>)}

            {/* ── HISTORY SUB-TAB ── */}
            {liveSubTab === 'history' && (
              <div data-testid="la-history" className="flex flex-col gap-4">
                {/* Filters */}
                <div className="flex items-center gap-2 flex-wrap">
                  <Funnel size={11} className="text-zinc-500" />
                  <select data-testid="hist-filter-symbol" value={histFilterSymbol} onChange={e => setHistFilterSymbol(e.target.value)} className={selectClass}>
                    <option value="">All Pairs</option>
                    {PORTFOLIO_PAIRS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <select data-testid="hist-filter-tf" value={histFilterTf} onChange={e => setHistFilterTf(e.target.value)} className={selectClass}>
                    <option value="">All TF</option>
                    {['H1', '4H', '1D', '15m'].map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <input data-testid="hist-filter-strategy" type="text" placeholder="Strategy ID" value={histFilterStrategy}
                    onChange={e => setHistFilterStrategy(e.target.value)} className={selectClass + ' w-32'} />
                  {(histFilterSymbol || histFilterTf || histFilterStrategy) && (
                    <button data-testid="hist-clear-filters" onClick={() => { setHistFilterSymbol(''); setHistFilterTf(''); setHistFilterStrategy(''); }}
                      className="text-[9px] font-mono text-zinc-500 hover:text-white transition-colors flex items-center gap-1">
                      <X size={9} /> Clear
                    </button>
                  )}
                  <button data-testid="hist-refresh-btn" onClick={fetchHistory} disabled={histLoading}
                    className="ml-auto text-[10px] font-mono text-zinc-400 hover:text-white transition-colors flex items-center gap-1">
                    <ClockCounterClockwise size={10} className={histLoading ? 'animate-spin' : ''} /> Refresh
                  </button>
                </div>

                {histError && <p data-testid="hist-error" className="text-red-500 text-xs font-mono">{histError}</p>}

                {histLoading && <p className="text-xs font-mono text-zinc-500 animate-pulse py-4 text-center">Loading history...</p>}

                {histData && !histLoading && (
                  <>
                    {/* Summary */}
                    <div data-testid="hist-summary" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                      <div className="grid grid-cols-4 gap-2 text-center">
                        <div>
                          <p className="text-lg font-bold font-mono text-zinc-300">{histData.total}</p>
                          <p className="text-[8px] text-zinc-500 uppercase">Records</p>
                        </div>
                        <div>
                          <p className="text-lg font-bold font-mono text-emerald-500">{histData.status_frequency?.STABLE || 0}</p>
                          <p className="text-[8px] text-zinc-500 uppercase">Stable</p>
                        </div>
                        <div>
                          <p className="text-lg font-bold font-mono text-yellow-500">{histData.status_frequency?.WARNING || 0}</p>
                          <p className="text-[8px] text-zinc-500 uppercase">Warning</p>
                        </div>
                        <div>
                          <p className="text-lg font-bold font-mono text-red-500">{histData.status_frequency?.FAILING || 0}</p>
                          <p className="text-[8px] text-zinc-500 uppercase">Failing</p>
                        </div>
                      </div>
                    </div>

                    {/* Allocation Over Time Chart */}
                    {histData.history && histData.history.length > 1 && (() => {
                      const hist = [...histData.history].reverse();
                      const allStrategies = {};
                      hist.forEach(h => (h.adjustments || []).forEach(a => {
                        if (!allStrategies[a.strategy_id]) allStrategies[a.strategy_id] = { pair: a.pair, tf: a.timeframe };
                      }));
                      const stratKeys = Object.keys(allStrategies);
                      const CHART_COLORS = ['#34d399', '#60a5fa', '#a78bfa', '#f59e0b', '#f87171', '#2dd4bf', '#818cf8', '#fb923c', '#e879f9', '#4ade80'];
                      const n = hist.length;

                      return (
                        <div data-testid="hist-chart" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                          <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Allocation % Over Time</p>
                          <div className="relative h-40">
                            <svg viewBox={`0 0 ${Math.max(n - 1, 1)} 100`} className="w-full h-full" preserveAspectRatio="none">
                              {stratKeys.map((sid, si) => {
                                const pts = hist.map((h, j) => {
                                  const adj = (h.adjustments || []).find(a => a.strategy_id === sid);
                                  return { x: j, y: adj ? adj.allocation * 100 : 0 };
                                });
                                return (
                                  <polyline key={sid} fill="none" stroke={CHART_COLORS[si % CHART_COLORS.length]}
                                    strokeWidth="1.5" strokeLinejoin="round" opacity={0.85}
                                    points={pts.map(p => `${p.x},${100 - p.y}`).join(' ')} />
                                );
                              })}
                            </svg>
                            {/* Y-axis labels */}
                            <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-[7px] font-mono text-zinc-600 -ml-1" style={{ transform: 'translateX(-100%)' }}>
                              <span>100%</span><span>50%</span><span>0%</span>
                            </div>
                          </div>
                          {/* X-axis time labels */}
                          <div className="flex justify-between mt-1 text-[7px] font-mono text-zinc-600 px-1">
                            <span>{hist[0]?.timestamp ? new Date(hist[0].timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                            <span>{hist[n - 1]?.timestamp ? new Date(hist[n - 1].timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                          </div>
                          {/* Legend */}
                          <div className="flex flex-wrap gap-3 mt-2">
                            {stratKeys.map((sid, si) => (
                              <div key={sid} className="flex items-center gap-1.5">
                                <span className="w-3 h-0.5 rounded" style={{ backgroundColor: CHART_COLORS[si % CHART_COLORS.length] }}></span>
                                <span className="text-[8px] font-mono text-zinc-500">{allStrategies[sid].pair}/{allStrategies[sid].tf}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Status Transitions */}
                    {histData.transitions && histData.transitions.length > 0 && (
                      <div data-testid="hist-transitions" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                        <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Status Transitions</p>
                        <div className="flex flex-col gap-1 max-h-[120px] overflow-y-auto">
                          {histData.transitions.map((t, i) => {
                            const fromColor = t.from === 'STABLE' ? 'text-emerald-400' : t.from === 'WARNING' ? 'text-yellow-400' : 'text-red-400';
                            const toColor = t.to === 'STABLE' ? 'text-emerald-400' : t.to === 'WARNING' ? 'text-yellow-400' : 'text-red-400';
                            return (
                              <div key={i} className="flex items-center gap-2 text-[9px] font-mono">
                                <span className="text-zinc-600 w-28 text-right">{t.timestamp ? new Date(t.timestamp).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                                <span className="text-zinc-400 font-semibold bg-zinc-800 px-1 py-0.5 rounded">{t.pair}</span>
                                <span className={fromColor}>{t.from}</span>
                                <ArrowRight size={8} className="text-zinc-600" />
                                <span className={toColor}>{t.to}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Timeline Table */}
                    <div data-testid="hist-timeline" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                      <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider px-3 pt-2.5 pb-1">Allocation Timeline</p>
                      <div className="max-h-[300px] overflow-y-auto">
                        <table className="w-full text-[10px] font-mono">
                          <thead>
                            <tr className="text-zinc-600 border-b border-zinc-800 bg-zinc-900/50 sticky top-0">
                              <th className="text-left px-3 py-1.5">Time</th>
                              <th className="text-center px-2 py-1.5">Strategies</th>
                              <th className="text-center px-2 py-1.5">Active</th>
                              <th className="text-center px-2 py-1.5">Reduced</th>
                              <th className="text-center px-2 py-1.5">Disabled</th>
                              <th className="text-left px-2 py-1.5">Allocations</th>
                            </tr>
                          </thead>
                          <tbody>
                            {histData.history.map((h, i) => (
                              <tr key={i} data-testid={`hist-row-${i}`} className="border-b border-zinc-800/30 hover:bg-zinc-800/20">
                                <td className="px-3 py-1.5 text-zinc-400 whitespace-nowrap">
                                  {h.timestamp ? new Date(h.timestamp).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                                </td>
                                <td className="px-2 py-1.5 text-center text-zinc-300">{h.num_strategies}</td>
                                <td className="px-2 py-1.5 text-center text-emerald-500">{h.summary?.active_strategies || 0}</td>
                                <td className="px-2 py-1.5 text-center text-yellow-500">{h.summary?.reduced_count || 0}</td>
                                <td className="px-2 py-1.5 text-center text-red-500">{h.summary?.zero_allocation_count || 0}</td>
                                <td className="px-2 py-1.5">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    {(h.adjustments || []).map((a, j) => {
                                      const stColor = a.status === 'STABLE' ? 'text-emerald-400 border-emerald-500/20' :
                                        a.status === 'WARNING' ? 'text-yellow-400 border-yellow-500/20' :
                                        'text-red-400 border-red-500/20';
                                      const dirIcon = a.direction === 'INCREASED' ? <TrendUp size={7} className="text-emerald-500" /> :
                                        a.direction === 'DECREASED' ? <TrendDown size={7} className="text-red-500" /> : null;
                                      return (
                                        <span key={j} className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded border text-[8px] ${stColor}`}>
                                          {a.pair} {(a.allocation * 100).toFixed(0)}% {dirIcon}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {histData.total === 0 && (
                      <div className="flex flex-col items-center py-8 text-zinc-600">
                        <ClockCounterClockwise size={28} weight="thin" className="opacity-30 mb-2" />
                        <p className="text-sm">No allocation history yet</p>
                        <p className="text-[10px] font-mono text-zinc-700">Run Live Allocation to start tracking</p>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ── REBALANCE SUB-TAB ── */}
            {liveSubTab === 'rebalance' && (
              <div data-testid="la-rebalance" className="flex flex-col gap-4">
                {rbLoading && <p className="text-xs font-mono text-zinc-500 animate-pulse py-4 text-center">Loading config...</p>}
                {rbError && <p data-testid="rb-error" className="text-red-500 text-xs font-mono">{rbError}</p>}

                {rbConfig && !rbLoading && (
                  <>
                    {/* Enable Toggle + Strategy Selection */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      <div className="bg-zinc-950 border border-zinc-800 rounded-md p-4">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <p className="text-sm font-semibold text-white flex items-center gap-1.5"><Repeat size={13} /> Auto-Rebalance</p>
                            <p className="text-[9px] font-mono text-zinc-500 mt-0.5">Automatically rebalance on schedule</p>
                          </div>
                          <button data-testid="rb-enable-toggle" onClick={() => handleSaveRbConfig({ enabled: !rbConfig.enabled })}
                            className={`w-11 h-6 rounded-full transition-colors relative ${rbConfig.enabled ? 'bg-emerald-500' : 'bg-zinc-700'}`}>
                            <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${rbConfig.enabled ? 'left-[22px]' : 'left-0.5'}`} />
                          </button>
                        </div>

                        <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Strategies</p>
                        <div className="flex flex-col gap-1 max-h-[180px] overflow-y-auto mb-2">
                          {strategies.map((s, i) => {
                            const isSel = (rbConfig.strategy_ids || []).includes(s.id);
                            return (
                              <button key={s.id || i} data-testid={`rb-strat-${i}`}
                                onClick={() => {
                                  const ids = rbConfig.strategy_ids || [];
                                  const updated = isSel ? ids.filter(x => x !== s.id) : [...ids, s.id];
                                  handleSaveRbConfig({ strategy_ids: updated });
                                }}
                                className={`text-left bg-zinc-900 border rounded px-2.5 py-1.5 flex items-center justify-between transition-colors text-[10px] font-mono ${
                                  isSel ? 'border-yellow-500/40 bg-yellow-500/5' : 'border-zinc-800 hover:bg-zinc-800/50'
                                }`}>
                                <div className="flex items-center gap-1.5">
                                  <span className={`w-3.5 h-3.5 rounded flex items-center justify-center border text-[8px] ${
                                    isSel ? 'border-yellow-500 bg-yellow-500 text-zinc-900' : 'border-zinc-700'
                                  }`}>{isSel ? <CheckCircle size={8} weight="bold" /> : ''}</span>
                                  <span className="font-semibold text-white">{s.pair}</span>
                                  <span className="text-zinc-500">{s.timeframe}</span>
                                </div>
                                <span className={`font-bold ${(s.score || 0) >= 50 ? 'text-emerald-500' : 'text-yellow-500'}`}>{s.score || 0}</span>
                              </button>
                            );
                          })}
                        </div>
                        <p className="text-[8px] font-mono text-zinc-600">{(rbConfig.strategy_ids || []).length} selected</p>
                      </div>

                      {/* Config + Run */}
                      <div className="flex flex-col gap-3">
                        <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                          <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Settings</p>
                          <div className="flex flex-col gap-2.5">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-mono text-zinc-400">Interval</span>
                              <select data-testid="rb-interval" value={rbConfig.interval_minutes || 60}
                                onChange={e => handleSaveRbConfig({ interval_minutes: Number(e.target.value) })} className={selectClass}>
                                <option value={15}>15 min</option><option value={30}>30 min</option>
                                <option value={60}>1 hour</option><option value={240}>4 hours</option><option value={1440}>1 day</option>
                              </select>
                            </div>
                            <div className="flex items-center justify-between">
                              <div><span className="text-[10px] font-mono text-zinc-400">Max Alloc Cap</span><p className="text-[8px] font-mono text-zinc-600">Prevent spikes</p></div>
                              <div className="flex items-center gap-2">
                                <input data-testid="rb-max-cap" type="range" min="20" max="80" step="5" value={rbConfig.max_allocation_pct || 50}
                                  onChange={e => handleSaveRbConfig({ max_allocation_pct: Number(e.target.value) })}
                                  className="w-20 h-1 accent-yellow-500 bg-zinc-800 rounded-full appearance-none cursor-pointer" />
                                <span className="text-[10px] font-mono text-yellow-400 w-8 text-right">{rbConfig.max_allocation_pct || 50}%</span>
                              </div>
                            </div>
                            <div className="flex items-center justify-between">
                              <div><span className="text-[10px] font-mono text-zinc-400">Deviation Threshold</span><p className="text-[8px] font-mono text-zinc-600">Min change to flag</p></div>
                              <div className="flex items-center gap-2">
                                <input data-testid="rb-deviation" type="range" min="2" max="30" step="1" value={rbConfig.deviation_threshold_pct || 10}
                                  onChange={e => handleSaveRbConfig({ deviation_threshold_pct: Number(e.target.value) })}
                                  className="w-20 h-1 accent-yellow-500 bg-zinc-800 rounded-full appearance-none cursor-pointer" />
                                <span className="text-[10px] font-mono text-yellow-400 w-8 text-right">{rbConfig.deviation_threshold_pct || 10}%</span>
                              </div>
                            </div>
                          </div>
                        </div>

                        <button data-testid="rb-run-btn" onClick={() => handleRunRebalance('manual')} disabled={rbRunning || (rbConfig.strategy_ids || []).length < 2}
                          className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-4 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40 justify-center">
                          {rbRunning ? <><CircleNotch size={14} className="animate-spin" /> Rebalancing...</> : <><Play size={14} weight="fill" /> Run Rebalance Now</>}
                        </button>

                        <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                          <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">Status</p>
                          <div className="flex items-center gap-2 text-[10px] font-mono">
                            <span className={`w-2 h-2 rounded-full ${rbConfig.enabled ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`}></span>
                            <span className={rbConfig.enabled ? 'text-emerald-400' : 'text-zinc-500'}>{rbConfig.enabled ? 'Active' : 'Disabled'}</span>
                          </div>
                          {rbStatus?.last_rebalance && (
                            <p className="text-[9px] font-mono text-zinc-600 mt-1">Last: {new Date(rbStatus.last_rebalance).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</p>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Last Result */}
                    {rbLastResult && (
                      <div data-testid="rb-last-result" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider">Last Rebalance Result</p>
                          <span className="text-[8px] font-mono text-zinc-600">{rbLastResult.timestamp ? new Date(rbLastResult.timestamp).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-center mb-2">
                          <div><p className="text-sm font-bold font-mono text-zinc-300">{rbLastResult.num_strategies}</p><p className="text-[7px] text-zinc-600 uppercase">Strategies</p></div>
                          <div><p className="text-sm font-bold font-mono text-yellow-400">{rbLastResult.changes?.length || 0}</p><p className="text-[7px] text-zinc-600 uppercase">Changes</p></div>
                          <div><p className={`text-sm font-bold font-mono ${rbLastResult.capped ? 'text-yellow-400' : 'text-zinc-500'}`}>{rbLastResult.capped ? 'Yes' : 'No'}</p><p className="text-[7px] text-zinc-600 uppercase">Capped</p></div>
                        </div>
                        {rbLastResult.changes && rbLastResult.changes.length > 0 ? (
                          <div className="flex flex-col gap-1">
                            {rbLastResult.changes.map((c, i) => (
                              <div key={i} className="flex items-center gap-2 text-[9px] font-mono">
                                <span className="text-zinc-400 font-semibold bg-zinc-800 px-1 py-0.5 rounded">{c.pair}</span>
                                <span className={c.status === 'STABLE' ? 'text-emerald-400' : c.status === 'WARNING' ? 'text-yellow-400' : 'text-red-400'}>{c.status}</span>
                                <span className="text-zinc-600">{(c.old_allocation * 100).toFixed(1)}%</span>
                                <ArrowRight size={8} className="text-zinc-600" />
                                <span className={c.direction === 'INCREASED' ? 'text-emerald-400' : 'text-red-400'}>{(c.new_allocation * 100).toFixed(1)}%</span>
                                {c.direction === 'INCREASED' ? <TrendUp size={8} className="text-emerald-500" /> : <TrendDown size={8} className="text-red-500" />}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[9px] font-mono text-zinc-600 text-center">No significant changes</p>
                        )}
                      </div>
                    )}

                    {/* Recent Events */}
                    {rbStatus?.recent_events && rbStatus.recent_events.length > 0 && (
                      <div data-testid="rb-recent-events" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                        <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Recent Rebalance Events</p>
                        <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto">
                          {rbStatus.recent_events.map((ev, i) => (
                            <div key={i} data-testid={`rb-event-${i}`} className="flex items-center gap-2 text-[9px] font-mono border-b border-zinc-800/30 pb-1.5">
                              <span className="text-zinc-500 w-32">{ev.timestamp ? new Date(ev.timestamp).toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${
                                ev.rebalance_reason === 'manual' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                                ev.rebalance_reason === 'interval' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                              }`}>{ev.rebalance_reason || 'unknown'}</span>
                              <span className="text-zinc-400">{ev.changes?.length || 0} changes</span>
                              {ev.capped && <span className="text-yellow-500 text-[8px]">CAPPED</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
