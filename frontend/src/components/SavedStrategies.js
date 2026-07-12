/* eslint-disable */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Database, Funnel, SortAscending, SortDescending, Trash, Code,
  CaretDown, CaretUp, ShieldCheck, Warning, X, ArrowRight, Eye,
  Scales, CheckCircle, TrendUp, TrendDown, Pulse
} from '@phosphor-icons/react';
import { getLibraryStrategies, deleteLibraryStrategy, deleteStrategy, getStrategyDetail, compareStrategies } from '../services/api';
import { useMarketUniverse } from '../hooks/useMarketUniverse';

const TIMEFRAMES = ['', '1h', '4h', '15m', '30m', '1d', '5m', '1m'];
const STATUSES = ['', 'READY', 'MODERATE', 'RISKY'];

function StatusBadge({ status }) {
  const cfg = {
    READY: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20' },
    MODERATE: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20' },
    RISKY: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20' },
  };
  const c = cfg[status] || cfg.RISKY;
  return (
    <span data-testid="strategy-status-badge" className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>
      {status || 'N/A'}
    </span>
  );
}

function MetricCell({ value, good, format }) {
  const v = value ?? 0;
  const isGood = good !== undefined ? good : true;
  const color = isGood ? 'text-emerald-500' : 'text-red-500';
  return <span className={`font-bold ${color}`}>{format ? format(v) : v}</span>;
}

function DetailSection({ title, children }) {
  return (
    <div className="mb-3">
      <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">{title}</p>
      {children}
    </div>
  );
}

function ParamPill({ label, value, color }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded border ${color || 'bg-zinc-800 text-zinc-300 border-zinc-700'}`}>
      <span className="text-zinc-500">{label}:</span> <strong>{value}</strong>
    </span>
  );
}

export default function StrategyLibrary() {
  // R4 — registry-backed symbol filter (leading "" remains the "All" option).
  const { all: REG_SYMBOLS } = useMarketUniverse();
  const SYMBOLS = useMemo(() => ['', ...REG_SYMBOLS], [REG_SYMBOLS]);
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Compare mode
  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState([]);
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState(null);

  // Filters
  const [filterSymbol, setFilterSymbol] = useState('');
  const [filterTf, setFilterTf] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState('desc');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {};
      if (filterSymbol) filters.symbol = filterSymbol;
      if (filterTf) filters.timeframe = filterTf;
      if (filterStatus) filters.status = filterStatus;
      if (sortBy) { filters.sort_by = sortBy; filters.sort_dir = sortDir; }
      const data = await getLibraryStrategies(filters);
      setStrategies(data.strategies || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [filterSymbol, filterTf, filterStatus, sortBy, sortDir]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleSelect = async (id) => {
    if (selectedId === id) { setSelectedId(null); setDetail(null); return; }
    setSelectedId(id);
    setDetailLoading(true);
    // Use the already-loaded library row as the source of truth. Library
    // rows come from strategy_library (via /api/auto-factory/saved) and
    // carry the full metrics + parameters + strategy_text inline, so no
    // extra detail fetch is required. We still opportunistically ask the
    // legacy /api/strategies/{id} endpoint for any enrichment (safety,
    // monte_carlo, validation) — but ignore 404s since library strategies
    // don't live in that collection.
    const row = strategies.find((s) => s.id === id);
    const fallback = row ? {
      ...row,
      metrics: row.metrics || {},
      indicators: row.indicators || {},
      safety: null, monte_carlo: null, validation: null,
    } : null;
    try {
      const data = await getStrategyDetail(id);
      setDetail((data && data.strategy) || fallback);
    } catch (e) {
      setDetail(fallback);
    }
    finally { setDetailLoading(false); }
  };

  const handleDelete = async (id) => {
    try {
      // Library rows live in strategy_library → /api/auto-factory/saved/{id}
      await deleteLibraryStrategy(id);
    } catch (e) {
      // Fallback: some rows may pre-date strategy_library and still live
      // in the legacy `strategies` collection.
      try { await deleteStrategy(id); } catch (_) { console.error(e); }
    }
    if (selectedId === id) { setSelectedId(null); setDetail(null); }
    fetchList();
  };

  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
  };

  const toggleCompareId = (id) => {
    setCompareIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
    setCompareData(null);
  };

  const handleCompare = async () => {
    if (compareIds.length < 2) return;
    setCompareLoading(true); setCompareError(null); setCompareData(null);
    try {
      const data = await compareStrategies(compareIds);
      setCompareData(data.strategies);
    } catch (e) { setCompareError(e.message); }
    finally { setCompareLoading(false); }
  };

  const COMPARE_COLORS = ['text-emerald-400', 'text-blue-400', 'text-violet-400'];
  const COMPARE_BAR_COLORS = ['bg-emerald-500', 'bg-blue-500', 'bg-violet-500'];
  const COMPARE_BG_COLORS = ['border-emerald-500/20', 'border-blue-500/20', 'border-violet-500/20'];

  const SortIcon = ({ field }) => {
    if (sortBy !== field) return <SortAscending size={10} className="text-zinc-700" />;
    return sortDir === 'desc' ? <SortDescending size={10} className="text-yellow-500" /> : <SortAscending size={10} className="text-yellow-500" />;
  };

  const selectClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded px-2 py-1 text-[10px] font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none";
  const d = detail;
  const m = d?.metrics || {};
  const sf = d?.safety || {};
  const mc = d?.monte_carlo || {};
  const val = d?.validation || {};
  const params = d?.parameters || {};
  const ind = d?.indicators || {};

  return (
    <div data-testid="strategy-library" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd asf-legacy-title border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <Database size={14} weight="bold" className="text-yellow-500" />
        <h2 className="text-sm font-semibold text-white">Strategy Library</h2>
        <span className="ml-auto text-xs font-mono text-zinc-500">{strategies.length} strategies</span>
        <button data-testid="compare-toggle-btn" onClick={() => { setCompareMode(!compareMode); setCompareIds([]); setCompareData(null); }}
          className={`ml-2 flex items-center gap-1.5 text-[10px] font-medium px-2.5 py-1.5 rounded transition-colors ${
            compareMode ? 'bg-yellow-500 text-zinc-900' : 'bg-zinc-800 text-zinc-400 hover:text-white'
          }`}>
          <Scales size={11} weight="bold" /> {compareMode ? 'Exit Compare' : 'Compare'}
        </button>
      </div>

      {/* Compare Selection Bar */}
      {compareMode && (
        <div data-testid="compare-bar" className="border-b border-zinc-800 px-4 py-2 flex items-center gap-3 bg-yellow-500/5">
          <Scales size={12} className="text-yellow-500" />
          <span className="text-[10px] font-mono text-yellow-400">Select 2-3 strategies to compare</span>
          <span className="text-[10px] font-mono text-zinc-500">({compareIds.length}/3 selected)</span>
          <button data-testid="run-compare-btn" onClick={handleCompare} disabled={compareIds.length < 2 || compareLoading}
            className="ml-auto bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded px-3 py-1 text-[10px] transition-colors flex items-center gap-1.5 disabled:opacity-40">
            {compareLoading ? 'Comparing...' : <><Scales size={10} /> Compare ({compareIds.length})</>}
          </button>
        </div>
      )}

      {/* Filters */}
      <div data-testid="library-filters" className="border-b border-zinc-800 px-4 py-2.5 flex items-center gap-3 flex-wrap bg-zinc-900/50">
        <Funnel size={11} className="text-zinc-500" />
        <select data-testid="filter-symbol" value={filterSymbol} onChange={e => setFilterSymbol(e.target.value)} className={selectClass}>
          <option value="">All Pairs</option>
          {SYMBOLS.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select data-testid="filter-timeframe" value={filterTf} onChange={e => setFilterTf(e.target.value)} className={selectClass}>
          <option value="">All TF</option>
          {TIMEFRAMES.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select data-testid="filter-status" value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className={selectClass}>
          <option value="">All Status</option>
          {STATUSES.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {(filterSymbol || filterTf || filterStatus || sortBy) && (
          <button data-testid="clear-filters-btn" onClick={() => { setFilterSymbol(''); setFilterTf(''); setFilterStatus(''); setSortBy(''); }}
            className="text-[9px] font-mono text-zinc-500 hover:text-white transition-colors flex items-center gap-1">
            <X size={9} /> Clear
          </button>
        )}
      </div>

      <div className="flex">
        {/* Table */}
        <div className={`flex-1 overflow-auto ${selectedId ? 'border-r border-zinc-800' : ''}`}>
          {strategies.length === 0 && !loading ? (
            <p className="text-sm text-zinc-600 text-center py-12">No strategies saved yet. Generate and save strategies from the Workspace.</p>
          ) : (
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800 bg-zinc-950/50">
                  {compareMode && <th className="text-center px-2 py-2 w-8"></th>}
                  <th className="text-left px-3 py-2">Pair</th>
                  <th className="text-left px-2 py-2">TF</th>
                  <th className="text-left px-2 py-2">Type</th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort('score')}>
                    <span className="flex items-center justify-end gap-1">Score <SortIcon field="score" /></span>
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort('profit_factor')}>
                    <span className="flex items-center justify-end gap-1">PF <SortIcon field="profit_factor" /></span>
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort('drawdown')}>
                    <span className="flex items-center justify-end gap-1">DD <SortIcon field="drawdown" /></span>
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort('win_rate')}>
                    <span className="flex items-center justify-end gap-1">WR <SortIcon field="win_rate" /></span>
                  </th>
                  <th className="text-right px-2 py-2">Trades</th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort('net_profit')}>
                    <span className="flex items-center justify-end gap-1">Profit <SortIcon field="net_profit" /></span>
                  </th>
                  <th className="text-center px-2 py-2">Status</th>
                  <th className="text-center px-2 py-2">Act</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((s, i) => {
                  const sm = s.metrics || s.backtest_results || {};
                  const isSelected = selectedId === s.id;
                  return (
                    <tr key={s.id || i} data-testid={`library-row-${i}`}
                      onClick={() => compareMode ? (s.id && toggleCompareId(s.id)) : (s.id && handleSelect(s.id))}
                      className={`border-b border-zinc-800/50 cursor-pointer transition-colors ${
                        compareMode && compareIds.includes(s.id) ? 'bg-yellow-500/10 border-l-2 border-l-yellow-500' :
                        isSelected ? 'bg-yellow-500/5' : 'hover:bg-zinc-800/30'
                      }`}>
                      {compareMode && (
                        <td className="px-2 py-2 text-center">
                          <span data-testid={`compare-check-${i}`} className={`w-4 h-4 rounded flex items-center justify-center border text-[9px] inline-flex ${
                            compareIds.includes(s.id) ? 'border-yellow-500 bg-yellow-500 text-zinc-900' : 'border-zinc-700 text-zinc-600'
                          }`}>{compareIds.includes(s.id) ? <CheckCircle size={10} weight="bold" /> : ''}</span>
                        </td>
                      )}
                      <td className="px-3 py-2">
                        <span className="text-[10px] font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                      </td>
                      <td className="px-2 py-2 text-zinc-400">{s.timeframe}</td>
                      <td className="px-2 py-2 text-zinc-500 text-[9px]">{(s.strategy_type || '').replace('_', ' ')}</td>
                      <td className="px-2 py-2 text-right">
                        <MetricCell value={s.score} good={(s.score || 0) >= 50} format={v => v?.toFixed?.(0) || '0'} />
                      </td>
                      <td className="px-2 py-2 text-right">
                        <MetricCell value={sm.profit_factor} good={(sm.profit_factor || 0) >= 1} format={v => v?.toFixed?.(2) || '0'} />
                      </td>
                      <td className="px-2 py-2 text-right text-yellow-500">{sm.max_drawdown_pct?.toFixed?.(1) || '0'}%</td>
                      <td className="px-2 py-2 text-right">
                        <MetricCell value={sm.win_rate} good={(sm.win_rate || 0) >= 50} format={v => `${v?.toFixed?.(0) || 0}%`} />
                      </td>
                      <td className="px-2 py-2 text-right text-zinc-400">{sm.total_trades || 0}</td>
                      <td className="px-2 py-2 text-right">
                        <MetricCell value={sm.net_profit} good={(sm.net_profit || 0) >= 0} format={v => `$${v >= 0 ? '+' : ''}${v?.toFixed?.(0) || 0}`} />
                      </td>
                      <td className="px-2 py-2 text-center"><StatusBadge status={s.status} /></td>
                      <td className="px-2 py-2 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button data-testid={`view-btn-${i}`} onClick={e => { e.stopPropagation(); s.id && handleSelect(s.id); }}
                            className="text-zinc-600 hover:text-white transition-colors p-0.5" title="View details">
                            <Eye size={11} />
                          </button>
                          <button data-testid={`delete-btn-${i}`} onClick={e => { e.stopPropagation(); s.id && handleDelete(s.id); }}
                            className="text-zinc-600 hover:text-red-500 transition-colors p-0.5" title="Delete">
                            <Trash size={11} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Detail Panel */}
        {selectedId && (
          <div data-testid="strategy-detail-panel" className="w-[380px] shrink-0 max-h-[600px] overflow-y-auto bg-zinc-950 p-4">
            {detailLoading ? (
              <p className="text-xs font-mono text-zinc-500 animate-pulse text-center py-8">Loading...</p>
            ) : d ? (
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{d.pair}</span>
                    <span className="text-[10px] font-mono text-zinc-500">{d.timeframe}</span>
                    <StatusBadge status={d.status} />
                  </div>
                  <button onClick={() => { setSelectedId(null); setDetail(null); }} className="text-zinc-600 hover:text-white transition-colors"><X size={12} /></button>
                </div>

                {d.strategy_type && (
                  <span data-testid="detail-strategy-type" className="text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 w-fit mb-2">
                    {d.strategy_type.replace('_', ' ')}
                  </span>
                )}

                {/* Score */}
                {d.score !== undefined && (
                  <div className="flex items-center gap-3 mb-3">
                    <span className={`text-2xl font-bold font-mono ${d.score >= 65 ? 'text-emerald-500' : d.score >= 40 ? 'text-yellow-500' : 'text-red-500'}`}>
                      {d.score}
                    </span>
                    <span className="text-[10px] font-mono text-zinc-500">/100 overall score</span>
                  </div>
                )}

                {/* Metrics */}
                <DetailSection title="Backtest Metrics">
                  <div className="grid grid-cols-3 gap-1.5">
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className={`text-sm font-bold font-mono ${m.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${m.net_profit?.toFixed(0)}</p><p className="text-[7px] text-zinc-600">Profit</p></div>
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className={`text-sm font-bold font-mono ${m.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{m.win_rate}%</p><p className="text-[7px] text-zinc-600">Win Rate</p></div>
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className={`text-sm font-bold font-mono ${m.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'}`}>{m.profit_factor}</p><p className="text-[7px] text-zinc-600">PF</p></div>
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className="text-sm font-bold font-mono text-yellow-500">{m.max_drawdown_pct?.toFixed(1)}%</p><p className="text-[7px] text-zinc-600">Max DD</p></div>
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className="text-sm font-bold font-mono text-white">{m.total_trades}</p><p className="text-[7px] text-zinc-600">Trades</p></div>
                    <div className="bg-zinc-900 rounded p-1.5 text-center"><p className={`text-sm font-bold font-mono ${m.total_return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>{m.total_return_pct?.toFixed(1)}%</p><p className="text-[7px] text-zinc-600">Return</p></div>
                  </div>
                </DetailSection>

                {/* Parameters */}
                <DetailSection title="Parameters">
                  <div className="flex flex-wrap gap-1">
                    {params.fast_ema && <ParamPill label="Fast EMA" value={params.fast_ema} />}
                    {params.slow_ema && <ParamPill label="Slow EMA" value={params.slow_ema} />}
                    {params.stop_loss_pips && <ParamPill label="SL" value={`${params.stop_loss_pips}p`} color="bg-red-500/10 text-red-400 border-red-500/20" />}
                    {params.take_profit_pips && <ParamPill label="TP" value={`${params.take_profit_pips}p`} color="bg-emerald-500/10 text-emerald-400 border-emerald-500/20" />}
                    {ind.rsi && <ParamPill label="RSI" value={`${ind.rsi.period} (${ind.rsi.buy}/${ind.rsi.sell})`} color="bg-violet-500/10 text-violet-400 border-violet-500/20" />}
                    {ind.macd && <ParamPill label="MACD" value={`${ind.macd.fast}/${ind.macd.slow}/${ind.macd.signal}`} color="bg-blue-500/10 text-blue-400 border-blue-500/20" />}
                    {ind.bollinger && <ParamPill label="BB" value={`${ind.bollinger.period},${ind.bollinger.std_dev}σ`} color="bg-orange-500/10 text-orange-400 border-orange-500/20" />}
                  </div>
                </DetailSection>

                {/* Safety */}
                {sf && sf.safety_score !== undefined && (
                  <DetailSection title="Safety">
                    <div className="flex items-center gap-2 mb-1">
                      {sf.is_safe ? <ShieldCheck size={12} className="text-emerald-500" /> : <Warning size={12} className="text-red-500" />}
                      <span className={`text-sm font-bold font-mono ${sf.safety_score >= 65 ? 'text-emerald-500' : sf.safety_score >= 40 ? 'text-yellow-500' : 'text-red-500'}`}>
                        {sf.safety_score}/100
                      </span>
                      <span className="text-[9px] font-mono text-zinc-500">Grade {sf.grade}</span>
                    </div>
                    {sf.flags && sf.flags.length > 0 && (
                      <div className="flex flex-col gap-0.5">
                        {sf.flags.map((f, i) => (
                          <span key={i} className="text-[8px] font-mono text-red-400 flex items-center gap-1"><Warning size={8} /> {f}</span>
                        ))}
                      </div>
                    )}
                  </DetailSection>
                )}

                {/* Monte Carlo */}
                {mc && mc.success && (
                  <DetailSection title="Monte Carlo">
                    <div className="flex items-center gap-3 text-[10px] font-mono">
                      <span className={`font-bold ${mc.score >= 60 ? 'text-violet-400' : 'text-yellow-500'}`}>{mc.score}/100</span>
                      <span className="text-zinc-500">Prob: {mc.statistics?.prob_profit}%</span>
                      <span className="text-zinc-500">Worst DD: {mc.statistics?.worst_drawdown}%</span>
                    </div>
                  </DetailSection>
                )}

                {/* Validation */}
                {val && val.success && (
                  <DetailSection title="Walk-Forward">
                    <div className="flex items-center gap-3 text-[10px] font-mono">
                      {val.stability && (
                        <>
                          <span className={`font-bold ${val.stability.score >= 60 ? 'text-emerald-500' : 'text-yellow-500'}`}>{val.stability.score}/100</span>
                          <span className="text-zinc-500">Grade {val.stability.grade}</span>
                          <span className="text-zinc-500">{val.stability.profitable_segments}/{val.stability.total_segments} profitable</span>
                        </>
                      )}
                    </div>
                  </DetailSection>
                )}

                {/* Strategy Text */}
                <DetailSection title="Strategy Text">
                  <pre className="text-[9px] font-mono text-zinc-500 whitespace-pre-wrap leading-relaxed max-h-[120px] overflow-y-auto bg-zinc-900 rounded p-2">
                    {d.strategy_text?.substring(0, 500)}
                  </pre>
                </DetailSection>

                <p className="text-[8px] font-mono text-zinc-700 mt-1">
                  {d.created_at ? new Date(d.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                </p>
              </div>
            ) : (
              <p className="text-xs font-mono text-zinc-600 text-center py-8">Failed to load details</p>
            )}
          </div>
        )}
      </div>

      {/* ═══════ COMPARISON RESULTS ═══════ */}
      {compareMode && compareError && (
        <p data-testid="compare-error" className="text-red-500 text-xs font-mono px-4 py-2">{compareError}</p>
      )}

      {compareMode && compareData && compareData.length >= 2 && (
        <div data-testid="compare-results" className="border-t border-zinc-800">
          {/* Header row */}
          <div className="px-4 py-3 bg-zinc-950/50 border-b border-zinc-800 flex items-center gap-2">
            <Scales size={14} weight="bold" className="text-yellow-500" />
            <span className="text-sm font-semibold text-white">Strategy Comparison</span>
            <span className="text-[10px] font-mono text-zinc-500">{compareData.length} strategies</span>
          </div>

          {/* Strategy Labels */}
          <div className="grid px-4 py-2 border-b border-zinc-800 bg-zinc-950/30" style={{ gridTemplateColumns: `140px repeat(${compareData.length}, 1fr)` }}>
            <div></div>
            {compareData.map((s, i) => (
              <div key={s.id} className="text-center px-2">
                <div className="flex items-center justify-center gap-1.5 mb-0.5">
                  <span className={`w-2 h-2 rounded-full ${COMPARE_BAR_COLORS[i]}`}></span>
                  <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                  <span className="text-[10px] font-mono text-zinc-500">{s.timeframe}</span>
                </div>
                <p className="text-[8px] font-mono text-zinc-600 truncate">{(s.strategy_type || '').replace('_', ' ')}</p>
              </div>
            ))}
          </div>

          {/* Metrics Comparison */}
          <div className="px-4 py-3 border-b border-zinc-800">
            <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Performance Metrics</p>
            {[
              { key: 'net_profit', label: 'Profit', fmt: v => `$${v >= 0 ? '+' : ''}${v?.toFixed(0) || 0}`, higher: true },
              { key: 'profit_factor', label: 'Profit Factor', fmt: v => v?.toFixed(2) || '0', higher: true },
              { key: 'win_rate', label: 'Win Rate', fmt: v => `${v?.toFixed(0) || 0}%`, higher: true },
              { key: 'max_drawdown_pct', label: 'Max Drawdown', fmt: v => `${v?.toFixed(1) || 0}%`, higher: false },
              { key: 'total_trades', label: 'Trades', fmt: v => v || 0, higher: null },
              { key: 'total_return_pct', label: 'Return %', fmt: v => `${v?.toFixed(1) || 0}%`, higher: true },
              { key: 'risk_adjusted_return', label: 'Risk Adj Return', fmt: v => v?.toFixed(2) || '0', higher: true },
            ].map(({ key, label, fmt, higher }) => {
              const vals = compareData.map(s => (s.metrics || {})[key] || 0);
              const bestIdx = higher === null ? -1 : higher
                ? vals.indexOf(Math.max(...vals))
                : vals.indexOf(Math.min(...vals));
              return (
                <div key={key} className="grid items-center py-1" style={{ gridTemplateColumns: `140px repeat(${compareData.length}, 1fr)` }}>
                  <span className="text-[10px] font-mono text-zinc-500">{label}</span>
                  {compareData.map((s, i) => {
                    const v = (s.metrics || {})[key] || 0;
                    const isBest = i === bestIdx;
                    return (
                      <div key={s.id} className="text-center">
                        <span className={`text-[11px] font-bold font-mono ${
                          isBest ? COMPARE_COLORS[i] : 'text-zinc-400'
                        } ${isBest ? 'bg-zinc-800/50 px-1.5 py-0.5 rounded' : ''}`}>
                          {fmt(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Safety & Score */}
          <div className="px-4 py-3 border-b border-zinc-800">
            <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Safety & Score</p>
            {[
              { key: 'score', label: 'Overall Score', get: s => s.score || 0, fmt: v => `${v}/100`, higher: true },
              { key: 'safety', label: 'Safety Score', get: s => s.safety?.safety_score || 0, fmt: v => `${v}/100`, higher: true },
              { key: 'grade', label: 'Safety Grade', get: s => s.safety?.grade || 'N/A', fmt: v => v, higher: null },
              { key: 'live_status', label: 'Live Status', get: s => s.live_status || 'N/A', fmt: v => v, higher: null },
            ].map(({ key, label, get, fmt, higher }) => {
              const vals = compareData.map(get);
              const numVals = vals.map(v => typeof v === 'number' ? v : 0);
              const bestIdx = higher === null ? -1 : higher ? numVals.indexOf(Math.max(...numVals)) : numVals.indexOf(Math.min(...numVals));
              return (
                <div key={key} className="grid items-center py-1" style={{ gridTemplateColumns: `140px repeat(${compareData.length}, 1fr)` }}>
                  <span className="text-[10px] font-mono text-zinc-500">{label}</span>
                  {compareData.map((s, i) => {
                    const v = get(s);
                    const isBest = i === bestIdx;
                    const statusColor = key === 'live_status' ? (v === 'STABLE' ? 'text-emerald-400' : v === 'WARNING' ? 'text-yellow-400' : v === 'FAILING' ? 'text-red-400' : 'text-zinc-500') : '';
                    const gradeColor = key === 'grade' ? (v === 'A' ? 'text-emerald-400' : v === 'B' ? 'text-emerald-300' : v === 'C' ? 'text-yellow-400' : v === 'D' ? 'text-red-400' : 'text-zinc-500') : '';
                    return (
                      <div key={s.id} className="text-center">
                        <span className={`text-[11px] font-bold font-mono ${
                          statusColor || gradeColor || (isBest ? COMPARE_COLORS[i] : 'text-zinc-400')
                        } ${isBest && !statusColor && !gradeColor ? 'bg-zinc-800/50 px-1.5 py-0.5 rounded' : ''}`}>
                          {fmt(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Equity Curve Overlay */}
          <div className="px-4 py-3 border-b border-zinc-800">
            <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Equity Curve Overlay</p>
            <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
              <div className="relative h-32">
                {compareData.map((s, si) => {
                  const eq = s.backtest_results?.equity_curve || [];
                  if (eq.length < 2) return null;
                  const allEqs = compareData.flatMap(st => st.backtest_results?.equity_curve || []);
                  const mn = Math.min(...allEqs);
                  const mx = Math.max(...allEqs);
                  const range = mx - mn || 1;
                  return (
                    <div key={s.id} className="absolute inset-0 flex items-end">
                      <svg viewBox={`0 0 ${eq.length - 1} 100`} className="w-full h-full" preserveAspectRatio="none">
                        <polyline
                          fill="none"
                          stroke={si === 0 ? '#34d399' : si === 1 ? '#60a5fa' : '#a78bfa'}
                          strokeWidth="2"
                          strokeLinejoin="round"
                          opacity={0.8}
                          points={eq.map((v, j) => `${j},${100 - ((v - mn) / range) * 90 - 5}`).join(' ')}
                        />
                      </svg>
                    </div>
                  );
                })}
              </div>
              {/* Legend */}
              <div className="flex items-center gap-4 mt-2">
                {compareData.map((s, i) => (
                  <div key={s.id} className="flex items-center gap-1.5">
                    <span className={`w-3 h-0.5 rounded ${COMPARE_BAR_COLORS[i]}`}></span>
                    <span className="text-[9px] font-mono text-zinc-500">{s.pair}/{s.timeframe}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Parameter Comparison */}
          <div className="px-4 py-3">
            <p className="text-[9px] font-medium text-zinc-500 uppercase tracking-wider mb-2">Parameters</p>
            {[
              { key: 'fast_ema', label: 'Fast EMA', get: s => s.parameters?.fast_ema },
              { key: 'slow_ema', label: 'Slow EMA', get: s => s.parameters?.slow_ema },
              { key: 'sl', label: 'Stop Loss', get: s => s.parameters?.stop_loss_pips, fmt: v => `${v}p` },
              { key: 'tp', label: 'Take Profit', get: s => s.parameters?.take_profit_pips, fmt: v => `${v}p` },
              { key: 'rsi', label: 'RSI', get: s => s.indicators?.rsi ? `${s.indicators.rsi.period} (${s.indicators.rsi.buy}/${s.indicators.rsi.sell})` : null },
              { key: 'macd', label: 'MACD', get: s => s.indicators?.macd ? `${s.indicators.macd.fast}/${s.indicators.macd.slow}/${s.indicators.macd.signal}` : null },
              { key: 'bb', label: 'Bollinger', get: s => s.indicators?.bollinger ? `${s.indicators.bollinger.period}, ${s.indicators.bollinger.std_dev}` : null },
            ].map(({ key, label, get, fmt }) => {
              const vals = compareData.map(get);
              if (vals.every(v => v == null)) return null;
              return (
                <div key={key} className="grid items-center py-1" style={{ gridTemplateColumns: `140px repeat(${compareData.length}, 1fr)` }}>
                  <span className="text-[10px] font-mono text-zinc-500">{label}</span>
                  {compareData.map((s, i) => {
                    const v = get(s);
                    return (
                      <div key={s.id} className="text-center">
                        <span className={`text-[10px] font-mono ${v != null ? 'text-zinc-300' : 'text-zinc-700'}`}>
                          {v != null ? (fmt ? fmt(v) : v) : '-'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
