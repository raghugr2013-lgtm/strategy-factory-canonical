import React, { useMemo, useState } from 'react';
import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, ReferenceDot
} from 'recharts';
import { X, TrendUp, TrendDown } from '@phosphor-icons/react';

/**
 * Phase 7.5 — Minimal Trade Visualization
 *
 * Renders the backtest `report` as:
 *   • price line (from report-parent.prices or equity fallback)
 *   • BUY/SELL entry markers + TP/SL exit markers
 *   • one connector line per trade (entry → exit, colored by direction)
 *   • compact clickable trade table; selected row highlights its trade
 *
 * No styling polish, no SL/TP zones, no MAE/MFE, no replay, no filters.
 */
export default function StrategyChartView({ report, prices, onClose }) {
  const [selectedIdx, setSelectedIdx] = useState(null);

  const trades = report?.trades || [];

  // Build chart data: one point per bar with price.
  const data = useMemo(() => {
    const series = prices && prices.length ? prices : [];
    return series.map((p, i) => ({ bar: i, price: Number(p) }));
  }, [prices]);

  // Only render markers whose bar index is inside the current price series.
  const { entryPoints, exitPoints, tradeLines } = useMemo(() => {
    const entry = [];
    const exit = [];
    const lines = [];
    const maxBar = data.length - 1;
    trades.forEach((t, idx) => {
      const ei = Number.isInteger(t.entry_idx) ? t.entry_idx : null;
      const xi = Number.isInteger(t.exit_idx) ? t.exit_idx : null;
      if (ei == null || xi == null || ei > maxBar || xi > maxBar) return;
      const dir = (t.direction || t.side || '').toUpperCase();
      const outcome = (t.outcome || t.result || '').toUpperCase();
      entry.push({ bar: ei, price: Number(t.entry_price), dir, idx });
      exit.push({ bar: xi, price: Number(t.exit_price), outcome, idx });
      lines.push({
        idx, ei, xi,
        entry: Number(t.entry_price),
        exit: Number(t.exit_price),
        dir,
        sl: Number(t.sl ?? t.sl_price),
        tp: Number(t.tp ?? t.tp_price),
      });
    });
    return { entryPoints: entry, exitPoints: exit, tradeLines: lines };
  }, [trades, data.length]);

  // Custom shape for entry (triangle) and exit (dot)
  const EntryShape = (props) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null;
    const highlighted = selectedIdx != null && payload?.idx === selectedIdx;
    const isBuy = payload?.dir === 'BUY';
    const color = isBuy ? '#10b981' : '#ef4444';
    const yOffset = isBuy ? 10 : -10;
    const tip = isBuy
      ? `${cx},${cy + yOffset + 8} ${cx - 6},${cy + yOffset} ${cx + 6},${cy + yOffset}`
      : `${cx},${cy + yOffset - 8} ${cx - 6},${cy + yOffset} ${cx + 6},${cy + yOffset}`;
    return (
      <g>
        <polygon
          points={tip}
          fill={color}
          stroke={highlighted ? '#fff' : color}
          strokeWidth={highlighted ? 2 : 1}
          data-testid={`chart-entry-marker-${payload.idx}`}
        />
      </g>
    );
  };

  const ExitShape = (props) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null;
    const highlighted = selectedIdx != null && payload?.idx === selectedIdx;
    const isTP = payload?.outcome === 'TP';
    const color = isTP ? '#10b981' : '#ef4444';
    return (
      <circle
        cx={cx}
        cy={cy}
        r={highlighted ? 5 : 3.5}
        fill={color}
        stroke={highlighted ? '#fff' : color}
        strokeWidth={highlighted ? 1.5 : 0}
        data-testid={`chart-exit-marker-${payload.idx}`}
      />
    );
  };

  if (!data.length) {
    return (
      <div className="p-6 text-center text-zinc-400 text-sm font-mono"
           data-testid="chart-empty">
        No price data available to render chart.
      </div>
    );
  }

  // Highlighted trade — draw a thicker connector + vertical markers.
  const hl = selectedIdx != null ? tradeLines.find(t => t.idx === selectedIdx) : null;

  return (
    <div data-testid="strategy-chart-view" className="flex flex-col h-full bg-zinc-950">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <TrendUp size={14} weight="bold" className="text-emerald-500" />
          <h3 className="text-sm font-semibold text-white">Trade Visualization</h3>
          <span className="text-[11px] font-mono text-zinc-500">
            {trades.length} trades · {data.length} bars
          </span>
        </div>
        {onClose && (
          <button
            data-testid="chart-close-btn"
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800"
          >
            <X size={16} weight="bold" />
          </button>
        )}
      </div>

      <div className="flex-1 min-h-[320px] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 40 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis
              dataKey="bar"
              type="number"
              domain={['dataMin', 'dataMax']}
              stroke="#52525b"
              tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }}
              label={{ value: 'Bar', position: 'insideBottom', offset: -2, fill: '#71717a', fontSize: 10 }}
            />
            <YAxis
              dataKey="price"
              domain={['auto', 'auto']}
              stroke="#52525b"
              tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }}
              tickFormatter={(v) => Number(v).toFixed(5)}
              width={70}
            />
            <Tooltip
              contentStyle={{
                background: '#18181b',
                border: '1px solid #3f3f46',
                borderRadius: 4,
                fontSize: 11,
                fontFamily: 'monospace'
              }}
              labelStyle={{ color: '#a1a1aa' }}
              formatter={(value, name) => [Number(value).toFixed(5), name]}
            />

            {/* Price line */}
            <Line
              type="monotone"
              dataKey="price"
              stroke="#71717a"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />

            {/* Per-trade connector lines (entry → exit) + SL/TP dashed
                segments (only spanning the trade's duration). When a trade
                is selected, non-selected trades fade further. */}
            {tradeLines.map((tl) => {
              const isBuy = tl.dir === 'BUY';
              const color = isBuy ? '#10b981' : '#ef4444';
              const isHl = hl && hl.idx === tl.idx;
              const dimmed = selectedIdx != null && !isHl;
              const connectorOpacity = dimmed ? 0.15 : (isHl ? 1 : 0.55);
              const slTpOpacity = dimmed ? 0.08 : (isHl ? 0.95 : 0.35);
              const slTpWidth = isHl ? 2 : 1;
              return (
                <React.Fragment key={`tl-${tl.idx}`}>
                  {/* entry → exit connector */}
                  <ReferenceLine
                    segment={[{ x: tl.ei, y: tl.entry }, { x: tl.xi, y: tl.exit }]}
                    stroke={color}
                    strokeOpacity={connectorOpacity}
                    strokeWidth={isHl ? 2.5 : 1.2}
                    ifOverflow="extendDomain"
                  />
                  {/* SL dashed line (red) — only during trade */}
                  {Number.isFinite(tl.sl) && (
                    <ReferenceLine
                      segment={[{ x: tl.ei, y: tl.sl }, { x: tl.xi, y: tl.sl }]}
                      stroke="#ef4444"
                      strokeDasharray="4 3"
                      strokeOpacity={slTpOpacity}
                      strokeWidth={slTpWidth}
                      ifOverflow="extendDomain"
                    />
                  )}
                  {/* TP dashed line (green) — only during trade */}
                  {Number.isFinite(tl.tp) && (
                    <ReferenceLine
                      segment={[{ x: tl.ei, y: tl.tp }, { x: tl.xi, y: tl.tp }]}
                      stroke="#10b981"
                      strokeDasharray="4 3"
                      strokeOpacity={slTpOpacity}
                      strokeWidth={slTpWidth}
                      ifOverflow="extendDomain"
                    />
                  )}
                </React.Fragment>
              );
            })}

            {/* Highlighted trade — vertical guide lines */}
            {hl && (
              <>
                <ReferenceLine
                  x={hl.ei}
                  stroke="#fbbf24"
                  strokeDasharray="3 3"
                  strokeOpacity={0.7}
                />
                <ReferenceLine
                  x={hl.xi}
                  stroke="#fbbf24"
                  strokeDasharray="3 3"
                  strokeOpacity={0.7}
                />
              </>
            )}

            {/* Entry markers */}
            <Scatter data={entryPoints} shape={<EntryShape />} isAnimationActive={false} />
            {/* Exit markers */}
            <Scatter data={exitPoints} shape={<ExitShape />} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 px-4 py-2 border-t border-zinc-800 text-[10px] font-mono text-zinc-500">
        <span className="flex items-center gap-1"><span className="inline-block w-0 h-0 border-l-[4px] border-r-[4px] border-t-[6px] border-l-transparent border-r-transparent border-t-emerald-500"></span> BUY entry</span>
        <span className="flex items-center gap-1"><span className="inline-block w-0 h-0 border-l-[4px] border-r-[4px] border-b-[6px] border-l-transparent border-r-transparent border-b-red-500"></span> SELL entry</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-emerald-500"></span> Exit TP</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-red-500"></span> Exit SL/CLOSED</span>
        <span className="flex items-center gap-1"><span className="inline-block w-4 border-t border-dashed border-emerald-500"></span> TP level</span>
        <span className="flex items-center gap-1"><span className="inline-block w-4 border-t border-dashed border-red-500"></span> SL level</span>
        <span className="ml-auto">Click a row below to highlight</span>
      </div>

      {/* Phase 7.5 Advanced — selected-trade info panel (MAE / MFE / R) */}
      {selectedIdx != null && trades[selectedIdx] && (
        <div
          data-testid="chart-trade-info-panel"
          className="px-4 py-2.5 border-t border-amber-500/20 bg-amber-500/5 flex flex-wrap items-center gap-x-6 gap-y-1 text-[11px] font-mono"
        >
          <span className="text-amber-400 font-semibold">
            Trade #{selectedIdx + 1}
          </span>
          <span className="text-zinc-400">
            Dir: <span className={`font-semibold ${(trades[selectedIdx].direction || '').toUpperCase() === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
              {(trades[selectedIdx].direction || trades[selectedIdx].side || '-').toUpperCase()}
            </span>
          </span>
          <span className="text-zinc-400">
            SL: <span className="text-red-400">{Number(trades[selectedIdx].sl ?? trades[selectedIdx].sl_price).toFixed(5)}</span>
          </span>
          <span className="text-zinc-400">
            TP: <span className="text-emerald-400">{Number(trades[selectedIdx].tp ?? trades[selectedIdx].tp_price).toFixed(5)}</span>
          </span>
          <span className="text-zinc-400" data-testid="panel-mae">
            MAE: <span className="text-red-400">{Number(trades[selectedIdx].mae ?? 0).toFixed(1)} pips</span>
            <span className="text-zinc-600 ml-1">
              (${Number(trades[selectedIdx].mae_usd ?? 0).toFixed(2)})
            </span>
          </span>
          <span className="text-zinc-400" data-testid="panel-mfe">
            MFE: <span className="text-emerald-400">{Number(trades[selectedIdx].mfe ?? 0).toFixed(1)} pips</span>
            <span className="text-zinc-600 ml-1">
              (${Number(trades[selectedIdx].mfe_usd ?? 0).toFixed(2)})
            </span>
          </span>
          <span className="text-zinc-400" data-testid="panel-r-multiple">
            R: <span className={Number(trades[selectedIdx].r_multiple ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {Number(trades[selectedIdx].r_multiple ?? 0) >= 0 ? '+' : ''}
              {Number(trades[selectedIdx].r_multiple ?? 0).toFixed(2)}R
            </span>
          </span>
          <span className="text-zinc-400">
            Outcome: <span className={`font-semibold ${
              (trades[selectedIdx].outcome || '').toUpperCase() === 'TP' ? 'text-emerald-400'
              : (trades[selectedIdx].outcome || '').toUpperCase() === 'SL' ? 'text-red-400'
              : 'text-zinc-300'
            }`}>{(trades[selectedIdx].outcome || trades[selectedIdx].result || '-').toUpperCase()}</span>
          </span>
          <span className="text-zinc-400">
            Net: <span className={Number(trades[selectedIdx].net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {Number(trades[selectedIdx].net_pnl ?? 0) >= 0 ? '+' : ''}
              ${Number(trades[selectedIdx].net_pnl ?? 0).toFixed(2)}
            </span>
          </span>
        </div>
      )}

      {/* Trade table */}
      <div className="max-h-[260px] overflow-auto border-t border-zinc-800"
           data-testid="chart-trade-table">
        <table className="w-full text-[11px] font-mono">
          <thead className="bg-zinc-900 text-zinc-400 sticky top-0">
            <tr>
              <th className="text-left px-3 py-2 font-medium">#</th>
              <th className="text-left px-3 py-2 font-medium">Entry Time</th>
              <th className="text-left px-3 py-2 font-medium">Direction</th>
              <th className="text-right px-3 py-2 font-medium">Entry</th>
              <th className="text-right px-3 py-2 font-medium">Exit</th>
              <th className="text-left px-3 py-2 font-medium">Outcome</th>
              <th className="text-right px-3 py-2 font-medium">Net PnL</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, idx) => {
              const dir = (t.direction || t.side || '').toUpperCase();
              const out = (t.outcome || t.result || '').toUpperCase();
              const isSel = idx === selectedIdx;
              return (
                <tr
                  key={idx}
                  data-testid={`chart-trade-row-${idx}`}
                  onClick={() => setSelectedIdx(isSel ? null : idx)}
                  className={`cursor-pointer border-t border-zinc-900 hover:bg-zinc-900/60 ${
                    isSel ? 'bg-amber-500/10 hover:bg-amber-500/15' : ''
                  }`}
                >
                  <td className="px-3 py-1.5 text-zinc-500">{idx + 1}</td>
                  <td className="px-3 py-1.5 text-zinc-300">{String(t.entry_time ?? '-')}</td>
                  <td className={`px-3 py-1.5 font-semibold ${dir === 'BUY' ? 'text-emerald-500' : 'text-red-500'}`}>
                    {dir || '-'}
                  </td>
                  <td className="px-3 py-1.5 text-right text-zinc-200">
                    {Number(t.entry_price).toFixed(5)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-zinc-200">
                    {Number(t.exit_price).toFixed(5)}
                  </td>
                  <td className={`px-3 py-1.5 ${out === 'TP' ? 'text-emerald-500' : out === 'SL' ? 'text-red-500' : 'text-zinc-400'}`}>
                    {out || '-'}
                  </td>
                  <td className={`px-3 py-1.5 text-right ${t.net_pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {t.net_pnl >= 0 ? '+' : ''}{Number(t.net_pnl).toFixed(2)}
                  </td>
                </tr>
              );
            })}
            {!trades.length && (
              <tr><td colSpan="7" className="px-3 py-6 text-center text-zinc-500">No trades in report.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
