import React, { useState, useRef, useEffect } from 'react';
import {
  Rocket, CircleNotch, Crown, Code, DownloadSimple, Copy, CheckCircle,
  ListNumbers, ShieldCheck, Warning, Gear, Play, Stop, Timer, FloppyDisk
} from '@phosphor-icons/react';
import { runPipeline, runAutoFactory } from '../services/api';
import { useMarketUniverse } from '../hooks/useMarketUniverse';

function StatusBadge({ status }) {
  const cfg = {
    READY: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', border: 'border-emerald-500/20' },
    MODERATE: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500/20' },
    RISKY: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500/20' },
  };
  const c = cfg[status] || cfg.RISKY;
  return <span className={`text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded border ${c.bg} ${c.text} ${c.border}`}>{status}</span>;
}

export default function AutoFactory() {
  const [mode, setMode] = useState('quick'); // 'quick' | 'auto'

  // R4 — registry-backed pair list. Falls back to legacy 7 when API unreachable.
  const { options: PAIRS } = useMarketUniverse({ eligibility: 'discovery' });

  // Quick Pipeline state
  const [qPair, setQPair] = useState('EURUSD');
  const [qTf, setQTf] = useState('H1');
  const [qCount, setQCount] = useState(5);
  const [qRisk, setQRisk] = useState('1.0');
  const [qLoading, setQLoading] = useState(false);
  const [qResult, setQResult] = useState(null);
  const [qError, setQError] = useState(null);
  const [copied, setCopied] = useState(false);

  // Auto Factory state
  const [afSymbols, setAfSymbols] = useState(['EURUSD']);
  const [afTimeframes, setAfTimeframes] = useState(['H1']);
  const [afPerPair, setAfPerPair] = useState(5);
  const [afKeepN, setAfKeepN] = useState(1);
  const [afMinTrades, setAfMinTrades] = useState(5);
  const [afMinWR, setAfMinWR] = useState(0);
  const [afMinScore, setAfMinScore] = useState(0);
  const [afMinSafety, setAfMinSafety] = useState(0);
  const [afLoading, setAfLoading] = useState(false);
  const [afResult, setAfResult] = useState(null);
  const [afError, setAfError] = useState(null);

  // Continuous mode
  const [continuous, setContinuous] = useState(false);
  const [intervalMin, setIntervalMin] = useState(30);
  const [runCount, setRunCount] = useState(0);
  const [totalSavedAll, setTotalSavedAll] = useState(0);
  const intervalRef = useRef(null);

  // Readiness gate — structured 412 payload when a run is blocked.
  const [readinessBlock, setReadinessBlock] = useState(null);

  const toggleSymbol = (s) => {
    setAfSymbols(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  };
  const toggleTf = (tf) => {
    setAfTimeframes(prev => prev.includes(tf) ? prev.filter(x => x !== tf) : [...prev, tf]);
  };

  const handleQuickRun = async () => {
    setQLoading(true); setQError(null); setQResult(null);
    try { const data = await runPipeline(qPair, qTf, qCount, parseFloat(qRisk) || 1.0); setQResult(data); }
    catch (e) { setQError(e.message); }
    finally { setQLoading(false); }
  };

  const handleAutoRun = async () => {
    if (afSymbols.length === 0 || afTimeframes.length === 0) return;
    setAfLoading(true); setAfError(null); setAfResult(null); setReadinessBlock(null);
    try {
      const data = await runAutoFactory({
        symbols: afSymbols,
        timeframes: afTimeframes,
        strategies_per_pair: afPerPair,
        keep_top_n: afKeepN,
        min_trades: afMinTrades,
        min_win_rate: afMinWR,
        min_score: afMinScore,
        min_safety_score: afMinSafety,
      });
      setAfResult(data);
      setRunCount(c => c + 1);
      setTotalSavedAll(t => t + (data.summary?.total_saved || 0));
    } catch (e) {
      // Pre-flight readiness gate — render structured block modal.
      const detail = e?.body?.detail;
      if (e?.status === 412 && detail && detail.code === 'readiness_blocked') {
        setReadinessBlock(detail);
        // If continuous mode is running, stop it — a red state must not
        // auto-retry on the interval.
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
          setContinuous(false);
        }
      } else {
        setAfError(e.message);
      }
    }
    finally { setAfLoading(false); }
  };

  const startContinuous = () => {
    setContinuous(true);
    handleAutoRun();
    intervalRef.current = setInterval(() => {
      handleAutoRun();
    }, intervalMin * 60 * 1000);
  };

  const stopContinuous = () => {
    setContinuous(false);
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
  };

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const handleDownload = () => {
    if (!qResult?.cbot?.code) return;
    const blob = new Blob([qResult.cbot.code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = qResult.cbot.filename || 'AIStrategyBot.cs';
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };
  const handleCopy = async () => {
    if (!qResult?.cbot?.code) return;
    try { await navigator.clipboard.writeText(qResult.cbot.code); }
    catch { const ta = document.createElement('textarea'); ta.value = qResult.cbot.code; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); }
    setCopied(true); setTimeout(() => setCopied(false), 2000);
  };

  const selectClass = "bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-3 py-2 text-sm font-mono focus:ring-1 focus:ring-zinc-600 focus:outline-none transition-colors";
  const best = qResult?.best_strategy;
  const bt = best?.backtest_results;
  const cbot = qResult?.cbot;
  const ranked = qResult?.ranked_strategies;
  const af = afResult;

  return (
    <div data-testid="auto-factory-section" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd asf-legacy-title border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <Rocket size={14} weight="bold" className="text-yellow-500" />
        <h2 className="text-sm font-semibold text-white">Auto Factory</h2>
        {continuous && (
          <span data-testid="continuous-indicator" className="flex items-center gap-1 text-[9px] font-mono text-emerald-500 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Running
          </span>
        )}
        <span className="ml-auto text-[10px] font-mono text-zinc-500">
          {runCount > 0 && `${runCount} runs, ${totalSavedAll} saved`}
        </span>
      </div>

      {/* Mode Tabs */}
      <div className="border-b border-zinc-800 flex">
        <button data-testid="mode-quick" onClick={() => setMode('quick')}
          className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'quick' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
          <Rocket size={11} /> Quick Pipeline
        </button>
        <button data-testid="mode-auto" onClick={() => setMode('auto')}
          className={`flex-1 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'auto' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
          <Gear size={11} /> Auto Factory
        </button>
      </div>

      <div className="p-4">
        {/* ═══════ QUICK PIPELINE ═══════ */}
        {mode === 'quick' && (
          <div className="flex flex-col gap-4">
            {!qResult && (
              <>
                <div className="flex items-end gap-3 flex-wrap">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Pair</label>
                    <select data-testid="factory-pair-select" value={qPair} onChange={e => setQPair(e.target.value)} className={selectClass}>
                      {PAIRS.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Timeframe</label>
                    <select data-testid="factory-tf-select" value={qTf} onChange={e => setQTf(e.target.value)} className={selectClass}>
                      {['M1','M5','M15','M30','H1','H4','D1'].map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Count</label>
                    <input
                      data-testid="factory-count-input"
                      type="number"
                      min={1}
                      max={50}
                      step={1}
                      value={qCount}
                      onChange={e => {
                        const v = Number(e.target.value);
                        if (Number.isNaN(v)) return;
                        setQCount(Math.max(1, Math.min(50, v)));
                      }}
                      className={`${selectClass} w-20 text-center`}
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Risk %</label>
                    <input data-testid="factory-risk-input" type="number" step="0.5" min="0.5" max="5" value={qRisk} onChange={e => setQRisk(e.target.value)}
                      className={`${selectClass} w-16 text-center`} />
                  </div>
                  <button data-testid="run-factory-btn" onClick={handleQuickRun} disabled={qLoading}
                    className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40">
                    {qLoading ? <><CircleNotch size={14} className="animate-spin" /> Running...</> : <><Rocket size={14} /> Run Pipeline</>}
                  </button>
                </div>
                {qLoading && (
                  <div data-testid="factory-progress" className="bg-zinc-950 border border-zinc-800 rounded-md p-4">
                    <p className="text-xs font-mono text-yellow-500 animate-pulse">Pipeline in progress...</p>
                  </div>
                )}
              </>
            )}
            {qError && <p data-testid="factory-error" className="text-red-500 text-xs font-mono">{qError}</p>}

            {qResult && (
              <div className="flex flex-col gap-3">
                <div data-testid="factory-summary" className="bg-zinc-950 border border-zinc-800 rounded-md p-3 text-xs font-mono text-zinc-400">
                  Generated {qResult.total_generated}, backtested {qResult.total_backtested}, best: {best?.style || 'N/A'} (score {best?.ranking?.score})
                </div>

                {best && bt && (
                  <div data-testid="factory-best-strategy" className="border border-yellow-500/30 bg-yellow-500/5 rounded-md p-3 relative">
                    <div className="absolute -top-2 left-3 flex items-center gap-1 bg-yellow-500 text-zinc-900 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase">
                      <Crown size={9} weight="bold" /> Best
                    </div>
                    <div className="grid grid-cols-5 gap-2 mt-1">
                      <div className="text-center"><p className={`text-sm font-bold font-mono ${bt.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${bt.net_profit >= 0 ? '+' : ''}{bt.net_profit?.toLocaleString()}</p><p className="text-[8px] text-zinc-500">Profit</p></div>
                      <div className="text-center"><p className={`text-sm font-bold font-mono ${bt.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{bt.win_rate}%</p><p className="text-[8px] text-zinc-500">WR</p></div>
                      <div className="text-center"><p className="text-sm font-bold font-mono text-yellow-500">{bt.max_drawdown_pct?.toFixed(1)}%</p><p className="text-[8px] text-zinc-500">DD</p></div>
                      <div className="text-center"><p className="text-sm font-bold font-mono text-white">{bt.total_trades}</p><p className="text-[8px] text-zinc-500">Trades</p></div>
                      <div className="text-center"><p className="text-sm font-bold font-mono text-yellow-500">{best.ranking?.score}</p><p className="text-[8px] text-zinc-500">Score</p></div>
                    </div>
                  </div>
                )}

                {ranked && ranked.length > 1 && (
                  <div data-testid="factory-ranked-list" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                    <table className="w-full text-[11px] font-mono">
                      <thead><tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left px-3 py-1.5">#</th><th className="text-left px-2">Style</th>
                        <th className="text-right px-2">Score</th><th className="text-right px-2">Net $</th>
                        <th className="text-right px-2">WR</th><th className="text-right px-2">PF</th>
                        <th className="text-center px-2">Safety</th>
                      </tr></thead>
                      <tbody>
                        {ranked.map((s, i) => {
                          const b = s.backtest_results || {};
                          const r = s.ranking || {};
                          const sf = s.safety || {};
                          return (
                            <tr key={i} data-testid={`factory-ranked-row-${i}`} className={`border-b border-zinc-800/50 ${r.is_best ? 'bg-yellow-500/5' : 'hover:bg-zinc-800/30'}`}>
                              <td className="px-3 py-1.5"><span className={r.is_best ? 'text-yellow-500 font-bold' : 'text-zinc-600'}>#{r.rank}</span></td>
                              <td className="px-2 py-1.5 text-zinc-300">{s.style}</td>
                              <td className={`px-2 py-1.5 text-right font-bold ${r.score >= 50 ? 'text-emerald-500' : r.score >= 30 ? 'text-yellow-500' : 'text-red-500'}`}>{r.score}</td>
                              <td className={`px-2 py-1.5 text-right ${b.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${b.net_profit?.toFixed(0)}</td>
                              <td className={`px-2 py-1.5 text-right ${b.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{b.win_rate}%</td>
                              <td className={`px-2 py-1.5 text-right ${b.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'}`}>{b.profit_factor}</td>
                              <td className="px-2 py-1.5 text-center">
                                <span className={`text-[8px] font-bold ${sf.is_safe ? 'text-emerald-500' : 'text-red-500'}`}>{sf.safety_score}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {cbot && (
                  <div data-testid="factory-cbot" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                    <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Code size={12} className="text-yellow-500" />
                        <span className="text-[10px] font-mono text-zinc-500">{cbot.filename}</span>
                      </div>
                      <div className="flex gap-1.5">
                        <button data-testid="factory-copy-btn" onClick={handleCopy} className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-2 py-1 text-[9px] font-medium flex items-center gap-1">
                          {copied ? <><CheckCircle size={9} className="text-emerald-500" /> Copied</> : <><Copy size={9} /> Copy</>}
                        </button>
                        <button data-testid="factory-download-btn" onClick={handleDownload} className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-md px-2 py-1 text-[9px] font-medium flex items-center gap-1">
                          <DownloadSimple size={9} weight="bold" /> .cs
                        </button>
                      </div>
                    </div>
                    <pre className="p-3 text-[10px] font-mono text-zinc-300 overflow-auto max-h-[200px] whitespace-pre">{cbot.code}</pre>
                  </div>
                )}

                <button data-testid="factory-reset-btn" onClick={() => setQResult(null)}
                  className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-4 py-2 text-xs font-medium flex items-center justify-center gap-2 w-full sm:w-auto">
                  <Rocket size={12} /> Run Again
                </button>
              </div>
            )}
          </div>
        )}

        {/* ═══════ AUTO FACTORY ═══════ */}
        {mode === 'auto' && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Config Left */}
              <div className="flex flex-col gap-3">
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Symbols</label>
                  <div className="flex flex-wrap gap-1.5">
                    {PAIRS.map(s => (
                      <button key={s} data-testid={`af-sym-${s}`} onClick={() => toggleSymbol(s)}
                        className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${afSymbols.includes(s) ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30' : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-600'}`}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Timeframes</label>
                  <div className="flex flex-wrap gap-1.5">
                    {['M1','M5','M15','M30','H1','H4','D1'].map(t => (
                      <button key={t} data-testid={`af-tf-${t}`} onClick={() => toggleTf(t)}
                        className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${afTimeframes.includes(t) ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30' : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:border-zinc-600'}`}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Per Pair</label>
                    <input
                      data-testid="af-per-pair-input"
                      type="number"
                      min={1}
                      max={50}
                      step={1}
                      value={afPerPair}
                      onChange={e => {
                        const v = Number(e.target.value);
                        if (Number.isNaN(v)) return;
                        setAfPerPair(Math.max(1, Math.min(50, v)));
                      }}
                      className={selectClass + ' w-full text-center'}
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block">Keep Top N</label>
                    <select data-testid="af-keep-n" value={afKeepN} onChange={e => setAfKeepN(Number(e.target.value))} className={selectClass + ' w-full'}>
                      {[1,2,3,5].map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              {/* Filters Right */}
              <div className="flex flex-col gap-3">
                <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Performance Filters</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Trades</label>
                    <input data-testid="af-min-trades" type="number" min="0" value={afMinTrades} onChange={e => setAfMinTrades(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Win Rate %</label>
                    <input data-testid="af-min-wr" type="number" min="0" max="100" value={afMinWR} onChange={e => setAfMinWR(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Score</label>
                    <input data-testid="af-min-score" type="number" min="0" max="100" value={afMinScore} onChange={e => setAfMinScore(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Min Safety Score</label>
                    <input data-testid="af-min-safety" type="number" min="0" max="100" value={afMinSafety} onChange={e => setAfMinSafety(Number(e.target.value))}
                      className={selectClass + ' w-full'} />
                  </div>
                </div>
                <div>
                  <label className="text-[10px] font-mono text-zinc-500 mb-1 block">Continuous Interval (min)</label>
                  <input data-testid="af-interval" type="number" min="5" max="1440" value={intervalMin} onChange={e => setIntervalMin(Number(e.target.value))}
                    className={selectClass + ' w-full'} />
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-3">
              <button data-testid="af-run-once" onClick={handleAutoRun} disabled={afLoading || afSymbols.length === 0}
                className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40">
                {afLoading ? <><CircleNotch size={14} className="animate-spin" /> Running...</> : <><Play size={14} /> Run Once</>}
              </button>
              {!continuous ? (
                <button data-testid="af-start-continuous" onClick={startContinuous} disabled={afLoading || afSymbols.length === 0}
                  className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2 disabled:opacity-40">
                  <Timer size={14} /> Start Continuous
                </button>
              ) : (
                <button data-testid="af-stop-continuous" onClick={stopContinuous}
                  className="bg-red-500/10 text-red-500 hover:bg-red-500/20 border border-red-500/20 font-medium rounded-md px-5 py-2.5 text-sm transition-colors flex items-center gap-2">
                  <Stop size={14} /> Stop
                </button>
              )}
              <span className="text-[10px] font-mono text-zinc-600">
                {afSymbols.length} pairs x {afTimeframes.length} TFs x {afPerPair} = {afSymbols.length * afTimeframes.length * afPerPair} strategies
              </span>
            </div>

            {afError && <p data-testid="af-error" className="text-red-500 text-xs font-mono">{afError}</p>}

            {/* Auto Factory Results */}
            {af && (
              <div className="flex flex-col gap-3">
                <div data-testid="af-summary" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                  <div className="grid grid-cols-5 gap-2 text-center">
                    <div>
                      <p className="text-lg font-bold font-mono text-white">{af.summary.total_generated}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Generated</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-zinc-300">{af.summary.total_backtested}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Backtested</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-yellow-500">{af.summary.total_filtered_out}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Filtered Out</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold font-mono text-zinc-600">{af.summary.total_duplicates}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Duplicates</p>
                    </div>
                    <div>
                      <p className={`text-lg font-bold font-mono ${af.summary.total_saved > 0 ? 'text-emerald-500' : 'text-zinc-500'}`}>{af.summary.total_saved}</p>
                      <p className="text-[8px] text-zinc-500 uppercase">Saved</p>
                    </div>
                  </div>
                </div>

                {/* Saved strategies table */}
                {af.saved_strategies && af.saved_strategies.length > 0 && (
                  <div data-testid="af-saved-table" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                    <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2">
                      <FloppyDisk size={11} className="text-emerald-500" />
                      <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Auto-Saved to Library</span>
                    </div>
                    <table className="w-full text-[11px] font-mono">
                      <thead><tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left px-3 py-1.5">Pair</th><th className="text-left px-2">TF</th>
                        <th className="text-right px-2">Score</th><th className="text-right px-2">PF</th>
                        <th className="text-right px-2">WR</th><th className="text-right px-2">DD</th>
                        <th className="text-right px-2">Profit</th><th className="text-right px-2">Safety</th>
                        <th className="text-center px-2">Status</th>
                      </tr></thead>
                      <tbody>
                        {af.saved_strategies.map((s, i) => (
                          <tr key={i} data-testid={`af-saved-row-${i}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="px-3 py-1.5"><span className="text-[10px] font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span></td>
                            <td className="px-2 py-1.5 text-zinc-400">{s.timeframe}</td>
                            <td className={`px-2 py-1.5 text-right font-bold ${s.score >= 50 ? 'text-emerald-500' : s.score >= 30 ? 'text-yellow-500' : 'text-red-500'}`}>{s.score}</td>
                            <td className={`px-2 py-1.5 text-right ${s.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'}`}>{s.profit_factor?.toFixed(2)}</td>
                            <td className={`px-2 py-1.5 text-right ${s.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}`}>{s.win_rate}%</td>
                            <td className="px-2 py-1.5 text-right text-yellow-500">{s.max_drawdown_pct?.toFixed(1)}%</td>
                            <td className={`px-2 py-1.5 text-right ${s.net_profit >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>${s.net_profit?.toFixed(0)}</td>
                            <td className={`px-2 py-1.5 text-right ${s.safety_score >= 65 ? 'text-emerald-500' : 'text-yellow-500'}`}>{s.safety_score}</td>
                            <td className="px-2 py-1.5 text-center"><StatusBadge status={s.status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {af.saved_strategies && af.saved_strategies.length === 0 && (
                  <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3 text-center">
                    <p className="text-xs font-mono text-zinc-500">No strategies met the filter criteria this run. Try lowering thresholds.</p>
                  </div>
                )}

                {/* Run Log */}
                {af.run_log && af.run_log.length > 0 && (
                  <details className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
                    <summary className="px-3 py-2 text-[10px] font-medium text-zinc-500 uppercase tracking-wider cursor-pointer hover:text-zinc-300">
                      Run Log ({af.run_log.length} entries)
                    </summary>
                    <div className="px-3 pb-3 max-h-[200px] overflow-y-auto">
                      {af.run_log.map((line, i) => (
                        <p key={i} className={`text-[9px] font-mono ${line.startsWith('---') ? 'text-yellow-500 mt-1' : line.includes('SAVED') ? 'text-emerald-500' : 'text-zinc-600'}`}>
                          {line}
                        </p>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Readiness gate modal (non-overridable) ── */}
      {readinessBlock && (
        <div
          data-testid="af-readiness-block-modal"
          className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="af-readiness-block-title"
        >
          <div className="w-full max-w-xl rounded-lg border border-red-500/40 bg-[#121821] shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-red-500/30 bg-red-500/10 flex items-start gap-3">
              <div className="w-9 h-9 rounded-full bg-red-500/20 border border-red-500/40 flex items-center justify-center flex-shrink-0">
                <span className="text-red-300 text-lg font-bold">!</span>
              </div>
              <div className="flex-1 min-w-0">
                <h3
                  id="af-readiness-block-title"
                  className="text-sm font-bold text-red-200"
                  data-testid="af-readiness-block-title"
                >
                  System is not ready. Fix issues before running Auto Factory.
                </h3>
                <p className="text-[11px] text-red-300/80 mt-0.5">
                  The pre-flight readiness check failed. This block cannot be overridden.
                </p>
              </div>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                Failed checks ({(readinessBlock.failed_checks || []).length})
              </div>
              <ul data-testid="af-readiness-block-list" className="space-y-2">
                {(readinessBlock.failed_checks || []).map((c) => (
                  <li
                    key={c.id}
                    data-testid={`af-readiness-block-item-${c.id}`}
                    className="border border-red-500/25 bg-red-500/5 rounded px-3 py-2"
                  >
                    <div className="text-xs font-semibold text-zinc-100">{c.label || c.id}</div>
                    <div className="mt-0.5 text-[11px] text-zinc-400">{c.summary}</div>
                  </li>
                ))}
              </ul>
              <div className="text-[11px] text-zinc-400 pt-2 border-t border-zinc-800">
                Resolve each red check in the <span className="font-mono text-accent-primary">Admin → System Readiness</span> panel,
                then try again.
              </div>
            </div>
            <div className="px-5 py-3 bg-[#0B0F14] border-t border-zinc-800 flex items-center justify-end gap-2">
              <button
                data-testid="af-readiness-block-close"
                onClick={() => setReadinessBlock(null)}
                className="text-xs font-semibold px-3 py-1.5 rounded border border-zinc-700 bg-zinc-800/60 hover:bg-zinc-800 text-zinc-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
