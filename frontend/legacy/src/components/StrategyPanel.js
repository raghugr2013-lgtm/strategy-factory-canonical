import React, { useState } from 'react';
import { Lightning, CircleNotch } from '@phosphor-icons/react';
import { generateStrategy } from '../services/api';
import { useMarketUniverse } from '../hooks/useMarketUniverse';
import { AsfEmptyState } from './ui-asf';

const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];
const STYLES = ['trend-following', 'mean-reversion', 'breakout', 'scalping'];

export default function StrategyPanel({ onStrategyGenerated }) {
  const { options: PAIRS } = useMarketUniverse({ eligibility: 'discovery' });
  const [pair, setPair] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('H1');
  const [style, setStyle] = useState('trend-following');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await generateStrategy(pair, timeframe, style);
      onStrategyGenerated(data.strategy, pair, timeframe);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const selectClass = "w-full bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-md px-3 py-2 text-sm font-mono focus:ring-1 focus:ring-zinc-600 focus:border-zinc-600 focus:outline-none transition-colors";
  const labelClass = "text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-1.5 block";

  return (
    <div data-testid="strategy-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <div className="asf-legacy-title flex items-center gap-2">
          <Lightning size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">Strategy Generator</h2>
        </div>
      </div>
      <div className="p-4 flex flex-col gap-4">
        <div>
          <label className={labelClass}>Symbol</label>
          <select data-testid="currency-pair-select" value={pair} onChange={(e) => setPair(e.target.value)} className={selectClass}>
            {PAIRS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>Timeframe</label>
          <select data-testid="timeframe-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className={selectClass}>
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass}>Style</label>
          <select data-testid="strategy-style-select" value={style} onChange={(e) => setStyle(e.target.value)} className={selectClass}>
            {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <button
          data-testid="generate-strategy-btn"
          onClick={handleGenerate}
          disabled={loading}
          className="w-full bg-zinc-100 text-zinc-900 hover:bg-zinc-200 font-medium rounded-md px-4 py-2.5 text-sm transition-colors duration-150 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? (
            <><CircleNotch size={14} weight="bold" className="animate-spin" /> Generating...</>
          ) : (
            <><Lightning size={14} weight="bold" /> Generate Strategy</>
          )}
        </button>
        {error && (
          <AsfEmptyState
            slug="strategy-generator-error"
            testId="strategy-error"
            title="Strategy generation failed"
            body={error}
          />
        )}
      </div>
    </div>
  );
}
