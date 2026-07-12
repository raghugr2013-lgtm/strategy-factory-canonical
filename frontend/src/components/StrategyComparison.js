import React from 'react';
import { Trophy, Crown, TrendUp, TrendDown, ChartLine } from '@phosphor-icons/react';

function ScoreBar({ score, label, max, color }) {
  const pct = max > 0 ? (score / max) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-[10px] font-mono">
      <span className="text-zinc-500 uppercase tracking-wider w-16">{label}</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-zinc-500 w-10 text-right">{score}/{max}</span>
    </div>
  );
}

function GradeBadge({ grade }) {
  const colors = {
    'A': 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30',
    'B': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    'C': 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    'D': 'bg-red-500/10 text-red-400 border-red-500/20',
    'F': 'bg-red-500/20 text-red-500 border-red-500/30',
    'N/A': 'bg-zinc-800 text-zinc-500 border-zinc-700',
  };
  return (
    <span className={`inline-flex items-center justify-center w-7 h-7 text-xs font-bold font-mono rounded-md border ${colors[grade] || colors['N/A']}`}>
      {grade}
    </span>
  );
}

export default function StrategyComparison({ strategies, onSelectStrategy }) {
  if (!strategies || strategies.length === 0) return null;

  return (
    <div data-testid="strategy-comparison-panel" className="bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="border-b border-zinc-800 px-4 py-3 flex items-center gap-2">
        <Trophy size={14} weight="bold" className="text-yellow-500" />
        <h2 className="text-sm font-semibold text-white">Strategy Ranking</h2>
        <span className="ml-auto text-xs font-mono text-zinc-500">{strategies.length} compared</span>
      </div>
      <div className="p-4 flex flex-col gap-3">
        {strategies.map((s, i) => {
          const r = s.ranking || {};
          const bd = r.breakdown || {};
          const bt = s.backtest_results || {};
          const pnl = bt.total_pnl_pips;
          return (
            <div key={i} data-testid={`ranked-strategy-${i}`} onClick={() => onSelectStrategy(s)}
              className={`relative border rounded-md p-4 transition-colors duration-150 cursor-pointer group ${
                r.is_best ? 'border-yellow-500/30 bg-yellow-500/5 hover:bg-yellow-500/10' : 'border-zinc-800 bg-zinc-950 hover:bg-zinc-800/50'
              }`}>
              {r.is_best && (
                <div data-testid="best-strategy-badge" className="absolute -top-2 left-3 flex items-center gap-1 bg-yellow-500 text-zinc-900 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase">
                  <Crown size={9} weight="bold" /> Best Strategy
                </div>
              )}
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center gap-1 pt-1">
                  <span data-testid={`rank-number-${i}`} className={`text-xl font-bold font-mono ${r.rank === 1 ? 'text-yellow-500' : 'text-zinc-600'}`}>#{r.rank}</span>
                  <GradeBadge grade={r.grade} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] font-mono font-semibold bg-zinc-800 px-1.5 py-0.5 rounded text-white">{s.pair}</span>
                    <span className="text-[10px] font-mono text-zinc-500">{s.timeframe}</span>
                    {pnl !== undefined && pnl !== null && (
                      <span className={`flex items-center gap-1 text-xs font-bold font-mono ml-auto ${pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                        {pnl >= 0 ? <TrendUp size={10} /> : <TrendDown size={10} />}
                        {pnl > 0 ? '+' : ''}{pnl}p
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] font-mono text-zinc-500 line-clamp-1 mb-2">{s.strategy_text.substring(0, 100)}...</p>
                  <div className="flex gap-3 text-[10px] font-mono mb-2">
                    <span className="text-zinc-500">WR: <strong className={bt.win_rate >= 50 ? 'text-emerald-500' : 'text-red-500'}>{bt.win_rate || 0}%</strong></span>
                    <span className="text-zinc-500">Trades: <strong className="text-white">{bt.total_trades || 0}</strong></span>
                    <span className="text-zinc-500">PF: <strong className={bt.profit_factor >= 1 ? 'text-emerald-500' : 'text-red-500'}>{bt.profit_factor || 0}</strong></span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <ScoreBar score={bd.profit || 0} label="Profit" max={35} color="bg-emerald-500" />
                    <ScoreBar score={bd.win_rate || 0} label="WR" max={25} color="bg-blue-500" />
                    <ScoreBar score={bd.drawdown || 0} label="DD" max={25} color="bg-yellow-500" />
                    <ScoreBar score={bd.profit_factor || 0} label="PF" max={15} color="bg-purple-500" />
                  </div>
                </div>
                <div className="flex flex-col items-center">
                  <span data-testid={`strategy-score-${i}`} className={`text-2xl font-bold font-mono ${
                    r.score >= 65 ? 'text-emerald-500' : r.score >= 40 ? 'text-yellow-500' : 'text-red-500'
                  }`}>{r.score}</span>
                  <span className="text-[9px] font-mono text-zinc-600">/100</span>
                </div>
              </div>
              <div className="absolute bottom-2 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="flex items-center gap-1 text-[9px] font-mono text-zinc-600"><ChartLine size={9} /> Click to analyze</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
