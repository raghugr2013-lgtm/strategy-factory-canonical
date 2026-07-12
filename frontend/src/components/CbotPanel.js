import React, { useState } from 'react';
import { Code, CircleNotch, DownloadSimple, Copy, CheckCircle, Gear, ShieldCheck } from '@phosphor-icons/react';
import { generateCbot } from '../services/api';
import { AsfEmptyState } from './ui-asf';

function ParamTag({ label, value, color }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded border ${color || 'bg-zinc-800 text-zinc-300 border-zinc-700'}`}>
      <span className="text-zinc-500">{label}:</span> <strong>{value}</strong>
    </span>
  );
}

export default function CbotPanel({ strategy, pair, timeframe, backtestResults }) {
  const [code, setCode] = useState(null);
  const [botName, setBotName] = useState('');
  const [filename, setFilename] = useState('');
  const [paramsUsed, setParamsUsed] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    if (!strategy) return;
    setLoading(true);
    setError(null);
    setCode(null);
    setParamsUsed(null);
    try {
      const params = backtestResults?.parameters || null;
      const sim = backtestResults?.simulation || null;
      const safety = backtestResults?.safety?.thresholds || null;
      const strategyType = backtestResults?.strategy_type || null;
      const extraction = backtestResults?.extraction || null;

      // Build indicators from extraction data or backtest indicators_used
      let indicators = null;
      if (extraction?.raw) {
        const raw = extraction.raw;
        const ind = {};
        if (raw.rsi_period) {
          ind.rsi = { period: raw.rsi_period, buy_threshold: raw.rsi_buy_threshold || 50, sell_threshold: raw.rsi_sell_threshold || 50 };
        }
        if (raw.macd) {
          ind.macd = raw.macd;
        }
        if (raw.bollinger) {
          ind.bollinger = raw.bollinger;
        }
        if (Object.keys(ind).length > 0) indicators = ind;
      }

      const data = await generateCbot(strategy, pair, timeframe, params, sim, safety, indicators, strategyType, extraction);
      setCode(data.code);
      setBotName(data.bot_name);
      setFilename(data.filename);
      setParamsUsed(data.params_used || null);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleDownload = () => {
    if (!code) return;
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'AIStrategyBot.cs';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!code) return;
    try { await navigator.clipboard.writeText(code); }
    catch { const ta = document.createElement('textarea'); ta.value = code; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const pu = paramsUsed;
  const ind = pu?.indicators;

  return (
    <div data-testid="cbot-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
        <div className="asf-legacy-title flex items-center gap-2">
          <Code size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">cTrader cBot</h2>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button data-testid="generate-cbot-btn" onClick={handleGenerate} disabled={!strategy || loading}
            className="bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-3 py-1.5 text-xs transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
            {loading ? <><CircleNotch size={12} className="animate-spin" /> Generating...</> : <><Code size={12} /> Generate cBot</>}
          </button>
        </div>
      </div>

      <div className="p-4">
        {!strategy && !code && (
          <p className="text-sm text-zinc-600 text-center py-6">Generate and backtest a strategy first</p>
        )}
        {strategy && !code && !loading && !error && (
          <p className="text-sm text-zinc-600 text-center py-6">Generate a cTrader Automate C# bot from this strategy</p>
        )}
        {error && (
          <AsfEmptyState
            slug="cbot-error"
            testId="cbot-error"
            title="cBot generation failed"
            body={error}
          />
        )}

        {code && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <p data-testid="cbot-bot-name" className="text-sm font-mono text-white font-semibold">{botName}</p>
                <p className="text-[10px] font-mono text-zinc-500">{filename}</p>
              </div>
              <div className="flex gap-2">
                <button data-testid="copy-cbot-btn" onClick={handleCopy}
                  className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-2.5 py-1.5 text-[10px] font-medium transition-colors duration-150 flex items-center gap-1">
                  {copied ? <><CheckCircle size={10} className="text-emerald-500" /> Copied</> : <><Copy size={10} /> Copy</>}
                </button>
                <button data-testid="download-cbot-btn" onClick={handleDownload}
                  className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-md px-2.5 py-1.5 text-[10px] font-medium transition-colors duration-150 flex items-center gap-1">
                  <DownloadSimple size={10} weight="bold" /> .cs
                </button>
              </div>
            </div>

            {/* Parameters Used Section */}
            {pu && (
              <div data-testid="cbot-params-used" className="bg-zinc-950 border border-zinc-800 rounded-md p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Gear size={11} className="text-zinc-500" />
                  <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Parameters Used in cBot</span>
                  {pu.strategy_type && (
                    <span data-testid="cbot-strategy-type" className="text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-500 border border-yellow-500/20">
                      {pu.strategy_type.replace('_', ' ')}
                    </span>
                  )}
                </div>

                {/* Core params */}
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <ParamTag label="Fast EMA" value={pu.core?.fast_ema} />
                  <ParamTag label="Slow EMA" value={pu.core?.slow_ema} />
                  <ParamTag label="SL" value={`${pu.core?.stop_loss_pips}p`} color="bg-red-500/10 text-red-400 border-red-500/20" />
                  <ParamTag label="TP" value={`${pu.core?.take_profit_pips}p`} color="bg-emerald-500/10 text-emerald-400 border-emerald-500/20" />
                </div>

                {/* Indicator params */}
                {ind && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {ind.rsi && (
                      <>
                        <ParamTag label="RSI" value={ind.rsi.period} color="bg-violet-500/10 text-violet-400 border-violet-500/20" />
                        <ParamTag label="RSI Buy" value={`>${ind.rsi.buy_threshold}`} color="bg-violet-500/10 text-violet-400 border-violet-500/20" />
                        <ParamTag label="RSI Sell" value={`<${ind.rsi.sell_threshold}`} color="bg-violet-500/10 text-violet-400 border-violet-500/20" />
                      </>
                    )}
                    {ind.macd && (
                      <ParamTag label="MACD" value={`${ind.macd.fast}/${ind.macd.slow}/${ind.macd.signal}`} color="bg-blue-500/10 text-blue-400 border-blue-500/20" />
                    )}
                    {ind.bollinger && (
                      <ParamTag label="BB" value={`${ind.bollinger.period}, ${ind.bollinger.std_dev}σ`} color="bg-orange-500/10 text-orange-400 border-orange-500/20" />
                    )}
                  </div>
                )}

                {/* Safety params */}
                {pu.safety && (
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck size={10} className="text-emerald-500" />
                    <span className="text-[9px] font-mono text-zinc-500">
                      Safety: DD {pu.safety.max_drawdown_pct}% | Daily {pu.safety.daily_loss_pct}% | {pu.safety.max_trades_per_day} trades/day
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Code display */}
            <div data-testid="cbot-code-display" className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
              <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
                <span className="text-[10px] font-mono text-zinc-500">C# &middot; cTrader Automate</span>
                <span className="text-[10px] font-mono text-zinc-600">{code.split('\n').length} lines</span>
              </div>
              <pre className="p-4 text-xs font-mono text-zinc-300 overflow-x-auto overflow-y-auto max-h-[400px] leading-relaxed whitespace-pre">
                {code}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
