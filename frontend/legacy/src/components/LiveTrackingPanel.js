import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Pulse, CircleNotch, Play, Stop, ArrowsClockwise, Trash,
  Warning, ShieldCheck, Plus, Prohibit, Lightning
} from '@phosphor-icons/react';
import {
  getStrategies, getTrackedStrategies, startLiveTracking, stopLiveTracking,
  updateAllLiveTracking, updateLiveTracking, removeLiveTracking
} from '../services/api';

function StatusBadge({ status }) {
  const cfg = {
    STABLE: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20', icon: ShieldCheck },
    WARNING: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20', icon: Warning },
    FAILING: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20', icon: Warning },
    AUTO_DISABLED: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/30', icon: Prohibit },
  };
  const c = cfg[status] || cfg.STABLE;
  const Icon = c.icon;
  return (
    <span data-testid="live-status-badge" className={`inline-flex items-center gap-1 text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>
      <Icon size={9} weight="bold" /> {status || 'N/A'}
    </span>
  );
}

function MiniEquity({ curve }) {
  if (!curve || curve.length < 2) return null;
  const mn = Math.min(...curve);
  const mx = Math.max(...curve);
  const range = mx - mn || 1;
  const positive = curve[curve.length - 1] >= curve[0];
  return (
    <div className="h-8 flex items-end gap-px">
      {curve.slice(-30).map((v, i) => {
        const pct = ((v - mn) / range) * 100;
        return (
          <div key={i} className="flex-1 min-w-[1px]" style={{ height: `${Math.max(pct, 4)}%` }}>
            <div className={`w-full h-full rounded-sm ${positive ? 'bg-emerald-500/50' : 'bg-red-500/50'}`} />
          </div>
        );
      })}
    </div>
  );
}

function StrategyCard({ t, i, onRefresh, onStop, onRemove }) {
  const m = t.live_metrics || {};
  const alerts = t.alerts || [];
  const isDisabled = t.status === 'AUTO_DISABLED' || t.auto_disabled;
  const failures = t.consecutive_failures || 0;
  const threshold = t.failure_threshold || 3;

  return (
    <div data-testid={`tracked-strategy-${i}`}
      className={`bg-zinc-950 border rounded-md p-3 ${isDisabled ? 'border-red-500/30 opacity-75' : 'border-zinc-800'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{t.pair}</span>
          <span className="text-[10px] font-mono text-zinc-500">{t.timeframe}</span>
          <StatusBadge status={t.status} />
          {failures > 0 && !isDisabled && (
            <span data-testid={`failure-count-${i}`} className="text-[8px] font-mono text-red-400 bg-red-500/10 px-1 py-0.5 rounded">
              {failures}/{threshold} fails
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {!isDisabled && (
            <>
              <button data-testid={`refresh-btn-${i}`} onClick={() => onRefresh(t.strategy_id)}
                className="text-zinc-600 hover:text-white transition-colors p-0.5" title="Update">
                <ArrowsClockwise size={11} />
              </button>
              <button data-testid={`stop-btn-${i}`} onClick={() => onStop(t.strategy_id)}
                className="text-zinc-600 hover:text-yellow-500 transition-colors p-0.5" title="Stop">
                <Stop size={11} />
              </button>
            </>
          )}
          <button data-testid={`remove-btn-${i}`} onClick={() => onRemove(t.strategy_id)}
            className="text-zinc-600 hover:text-red-500 transition-colors p-0.5" title="Remove">
            <Trash size={11} />
          </button>
        </div>
      </div>

      {/* Auto-disabled banner */}
      {isDisabled && (
        <div data-testid={`disabled-banner-${i}`} className="flex items-start gap-2 bg-red-500/5 border border-red-500/20 rounded px-2 py-1.5 mb-2">
          <Prohibit size={12} className="text-red-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-[9px] font-bold font-mono text-red-500 uppercase">Auto-Disabled</p>
            <p className="text-[9px] font-mono text-red-400">{t.disable_reason || 'Consecutive failures exceeded threshold'}</p>
            {t.disabled_at && <p className="text-[8px] font-mono text-zinc-600">{new Date(t.disabled_at).toLocaleString()}</p>}
          </div>
        </div>
      )}

      {m.equity_curve && m.equity_curve.length > 1 && (
        <div className="mb-2"><MiniEquity curve={m.equity_curve} /></div>
      )}

      {m.total_trades !== undefined && (
        <div className="grid grid-cols-5 gap-2 mb-2">
          <div className="text-center">
            <p className={`text-xs font-bold font-mono ${m.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
              ${m.net_profit >= 0 ? '+' : ''}{m.net_profit?.toFixed(0)}
            </p>
            <p className="text-[7px] text-zinc-600">Profit</p>
          </div>
          <div className="text-center">
            <p className={`text-xs font-bold font-mono ${m.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{m.win_rate}%</p>
            <p className="text-[7px] text-zinc-600">WR</p>
          </div>
          <div className="text-center">
            <p className={`text-xs font-bold font-mono ${m.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'}`}>{m.profit_factor}</p>
            <p className="text-[7px] text-zinc-600">PF</p>
          </div>
          <div className="text-center">
            <p className="text-xs font-bold font-mono text-yellow-500">{m.max_drawdown_pct?.toFixed(1)}%</p>
            <p className="text-[7px] text-zinc-600">DD</p>
          </div>
          <div className="text-center">
            <p className="text-xs font-bold font-mono text-white">{m.total_trades}</p>
            <p className="text-[7px] text-zinc-600">Trades</p>
          </div>
        </div>
      )}

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {alerts.map((a, ai) => (
            <div key={ai} data-testid={`alert-${i}-${ai}`} className={`flex items-center gap-1.5 text-[9px] font-mono ${
              a.type === 'AUTO_DISABLED' ? 'text-red-500 font-bold' : 'text-red-400'
            }`}>
              {a.type === 'AUTO_DISABLED' ? <Prohibit size={9} weight="bold" className="flex-shrink-0" /> : <Warning size={9} weight="bold" className="flex-shrink-0" />}
              {a.message}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 text-[8px] font-mono text-zinc-600 mt-1">
        <span>{t.candles_count || 0} candles</span>
        {t.last_updated && <span>Updated: {new Date(t.last_updated).toLocaleTimeString()}</span>}
        {m.open_position && <span className="text-yellow-500">Position open</span>}
        {t.auto_disable && !isDisabled && (
          <span className="text-zinc-700">Auto-disable: {threshold} fails</span>
        )}
      </div>
    </div>
  );
}

export default function LiveTrackingPanel() {
  const [tracked, setTracked] = useState([]);
  const [library, setLibrary] = useState([]);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [failureThreshold, setFailureThreshold] = useState(3);
  const [autoDisableOn, setAutoDisableOn] = useState(true);
  const intervalRef = useRef(null);

  const fetchTracked = useCallback(async () => {
    try {
      const data = await getTrackedStrategies();
      setTracked(data.tracked || []);
    } catch (e) { console.error(e); }
  }, []);

  const fetchLibrary = useCallback(async () => {
    try {
      const data = await getStrategies({ sort_by: 'score', sort_dir: 'desc' });
      setLibrary(data.strategies || []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchTracked(); }, [fetchTracked]);

  const handleAdd = async (strategyId) => {
    setLoading(true); setError(null);
    try {
      await startLiveTracking(strategyId, { failure_threshold: failureThreshold, auto_disable: autoDisableOn });
      setShowAdd(false);
      await fetchTracked();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleStop = async (sid) => {
    try { await stopLiveTracking(sid); await fetchTracked(); } catch (e) { console.error(e); }
  };
  const handleRemove = async (sid) => {
    try { await removeLiveTracking(sid); await fetchTracked(); } catch (e) { console.error(e); }
  };
  const handleUpdateAll = async () => {
    setUpdating(true);
    try { await updateAllLiveTracking(); await fetchTracked(); }
    catch (e) { setError(e.message); }
    finally { setUpdating(false); }
  };
  const handleUpdateOne = async (sid) => {
    try { await updateLiveTracking(sid); await fetchTracked(); } catch (e) { console.error(e); }
  };

  const toggleAutoRefresh = () => {
    if (autoRefresh) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      setAutoRefresh(false);
    } else {
      setAutoRefresh(true);
      handleUpdateAll();
      intervalRef.current = setInterval(() => handleUpdateAll(), 5 * 60 * 1000);
    }
  };

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const active = tracked.filter(t => t.active && t.status !== 'AUTO_DISABLED');
  const disabled = tracked.filter(t => t.status === 'AUTO_DISABLED' || t.auto_disabled);
  const stopped = tracked.filter(t => !t.active && t.status !== 'AUTO_DISABLED' && !t.auto_disabled);

  const selectClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded px-2 py-1 text-[10px] font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none";

  return (
    <div data-testid="live-tracking-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd asf-legacy-title border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <Pulse size={14} weight="bold" className="text-yellow-500" />
        <h2 className="text-sm font-semibold text-white">Live Tracking</h2>
        {autoRefresh && (
          <span className="flex items-center gap-1 text-[9px] font-mono text-emerald-500 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Auto
          </span>
        )}
        <span className="ml-auto flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          {disabled.length > 0 && <span className="text-red-500">{disabled.length} disabled</span>}
          <span>{active.length} active</span>
        </span>
      </div>

      {/* Action Bar */}
      <div className="border-b border-zinc-800 px-4 py-2.5 flex items-center gap-2 flex-wrap">
        <button data-testid="add-tracking-btn" onClick={() => { setShowAdd(!showAdd); if (!showAdd) fetchLibrary(); }}
          className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-2.5 py-1.5 text-[10px] font-medium flex items-center gap-1">
          <Plus size={10} /> Add
        </button>
        <button data-testid="update-all-btn" onClick={handleUpdateAll} disabled={updating || active.length === 0}
          className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-2.5 py-1.5 text-[10px] font-medium flex items-center gap-1 disabled:opacity-40">
          {updating ? <CircleNotch size={10} className="animate-spin" /> : <ArrowsClockwise size={10} />} Update All
        </button>
        <button data-testid="auto-refresh-btn" onClick={toggleAutoRefresh}
          className={`border rounded-md px-2.5 py-1.5 text-[10px] font-medium flex items-center gap-1 ${
            autoRefresh ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 'bg-zinc-800 text-zinc-400 border-zinc-700'
          }`}>
          {autoRefresh ? <><Stop size={10} /> Stop Auto</> : <><Play size={10} /> Auto (5m)</>}
        </button>
      </div>

      <div className="p-4">
        {/* Add Strategy Panel */}
        {showAdd && (
          <div data-testid="add-strategy-panel" className="bg-zinc-950 border border-zinc-800 rounded-md p-3 mb-4">
            <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-2">Add from Library</p>

            {/* Auto-disable config */}
            <div className="flex items-center gap-3 mb-3 bg-zinc-900 rounded px-2.5 py-2">
              <label className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400 cursor-pointer">
                <input data-testid="auto-disable-toggle" type="checkbox" checked={autoDisableOn} onChange={e => setAutoDisableOn(e.target.checked)}
                  className="rounded border-zinc-700 bg-zinc-800 text-yellow-500 focus:ring-0 w-3 h-3" />
                Auto-disable failing
              </label>
              {autoDisableOn && (
                <div className="flex items-center gap-1">
                  <span className="text-[9px] font-mono text-zinc-500">after</span>
                  <select data-testid="failure-threshold-select" value={failureThreshold} onChange={e => setFailureThreshold(Number(e.target.value))} className={selectClass}>
                    {[2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <span className="text-[9px] font-mono text-zinc-500">consecutive fails</span>
                </div>
              )}
            </div>

            {library.length === 0 ? (
              <p className="text-xs font-mono text-zinc-600 py-2">No strategies available</p>
            ) : (
              <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto">
                {library.map((s, i) => {
                  const isTracked = tracked.some(t => t.strategy_id === s.id);
                  const liveFailed = s.live_test_result === 'Failed';
                  return (
                    <button key={s.id || i} data-testid={`add-strat-${i}`}
                      onClick={() => !isTracked && s.id && handleAdd(s.id)}
                      disabled={isTracked || loading}
                      className={`text-left bg-zinc-900 border rounded-md px-3 py-2 flex items-center justify-between transition-colors ${
                        isTracked ? 'border-zinc-800 opacity-40' : 'border-zinc-800 hover:bg-zinc-800/50'
                      }`}>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                        <span className="text-[10px] font-mono text-zinc-500">{s.timeframe}</span>
                        {liveFailed && <span className="text-[8px] font-mono text-red-400 bg-red-500/10 px-1 py-0.5 rounded">Live-Tested: Failed</span>}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-mono">
                        <span className={`font-bold ${(s.score || 0) >= 50 ? 'text-emerald-500' : 'text-yellow-500'}`}>{s.score || 0}</span>
                        {isTracked && <span className="text-zinc-600 text-[8px]">TRACKING</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {error && <p data-testid="live-error" className="text-red-500 text-xs font-mono mb-3">{error}</p>}

        {/* Active Strategies */}
        {active.length === 0 && disabled.length === 0 && !showAdd ? (
          <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
            <Pulse size={32} weight="thin" className="opacity-30 mb-2" />
            <p className="text-sm">No strategies being tracked</p>
            <p className="text-xs text-zinc-700">Add strategies from your library to start paper trading</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {active.map((t, i) => (
              <StrategyCard key={t.strategy_id} t={t} i={i}
                onRefresh={handleUpdateOne} onStop={handleStop} onRemove={handleRemove} />
            ))}

            {/* Auto-Disabled Section */}
            {disabled.length > 0 && (
              <div data-testid="disabled-section" className="mt-2">
                <div className="flex items-center gap-2 mb-2">
                  <Prohibit size={12} className="text-red-500" />
                  <p className="text-[11px] font-medium text-red-500 uppercase tracking-wider">Auto-Disabled ({disabled.length})</p>
                </div>
                <div className="flex flex-col gap-2">
                  {disabled.map((t, i) => (
                    <StrategyCard key={t.strategy_id} t={t} i={`disabled-${i}`}
                      onRefresh={handleUpdateOne} onStop={handleStop} onRemove={handleRemove} />
                  ))}
                </div>
              </div>
            )}

            {/* Stopped Section */}
            {stopped.length > 0 && (
              <details className="mt-2">
                <summary className="text-[10px] font-medium text-zinc-600 cursor-pointer hover:text-zinc-400">
                  Stopped ({stopped.length})
                </summary>
                <div className="flex flex-col gap-1 mt-1">
                  {stopped.map((t, i) => (
                    <div key={t.strategy_id} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 opacity-50">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-zinc-500">{t.pair}/{t.timeframe}</span>
                        <StatusBadge status={t.status} />
                      </div>
                      <button onClick={() => handleRemove(t.strategy_id)} className="text-zinc-600 hover:text-red-500 transition-colors">
                        <Trash size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
