import React, { useEffect, useState, useCallback } from 'react';
import { Info, CircleNotch, ArrowClockwise } from '@phosphor-icons/react';
import { describeStrategy } from '../services/api';

/**
 * Strategy Description panel — async, read-only enrichment.
 *
 * Props:
 *   strategy_text  (required)
 *   pair, timeframe, style, backtest   (optional context)
 *   variant        ('panel' | 'inline' — layout preset)
 *   auto           (bool, default true — auto-load on mount)
 *
 * Never blocks the parent. Shows loading spinner, error fallback with
 * a retry, and renders the structured description when ready.
 */
export default function StrategyDescription({
  strategy_text,
  pair,
  timeframe,
  style,
  backtest,
  variant = 'panel',
  auto = true,
}) {
  const [state, setState] = useState('idle'); // idle|loading|ready|error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async (force = false) => {
    if (!strategy_text) return;
    setState('loading'); setError(null);
    try {
      const res = await describeStrategy({
        strategy_text, pair, timeframe, style, backtest, force,
      });
      if (res?.description?.error) {
        setError(res.description.error);
        setData(res);
        setState('error');
      } else {
        setData(res);
        setState('ready');
      }
    } catch (e) {
      setError(e.message || 'Failed to load description');
      setState('error');
    }
  }, [strategy_text, pair, timeframe, style, backtest]);

  useEffect(() => {
    if (auto) load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategy_text, pair, timeframe]);

  if (!strategy_text) return null;

  const desc = data?.description || {};
  const isInline = variant === 'inline';

  return (
    <div
      data-testid="strategy-description"
      className={
        isInline
          ? "border border-zinc-800 bg-zinc-950/40 rounded-md p-3 space-y-2"
          : "card-premium p-4 space-y-3"
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Info size={14} weight="bold" className="text-cyan-400" />
          <h4 className="text-[11px] font-mono uppercase tracking-wider text-zinc-300">
            Description
          </h4>
          {data?.cached && (
            <span className="text-[9px] font-mono uppercase tracking-wider text-cyan-400/80 border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 rounded">
              cached
            </span>
          )}
        </div>
        {(state === 'ready' || state === 'error') && (
          <button
            data-testid="description-reload-btn"
            onClick={() => load(true)}
            className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 hover:text-zinc-200 inline-flex items-center gap-1"
            title="Regenerate (bypass cache)"
          >
            <ArrowClockwise size={10} weight="bold" /> reload
          </button>
        )}
      </div>

      {state === 'loading' && (
        <div data-testid="description-loading" className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
          <CircleNotch size={12} weight="bold" className="animate-spin" />
          Generating description…
        </div>
      )}

      {state === 'error' && (
        <div data-testid="description-error" className="text-[11px] font-mono text-red-300 bg-red-950/30 border border-red-900/60 rounded p-2">
          {error || 'Description unavailable'}
          <button
            onClick={() => load(true)}
            className="ml-2 underline hover:text-red-200"
          >retry</button>
        </div>
      )}

      {state === 'ready' && (
        <div data-testid="description-body" className="space-y-2">
          {desc.summary && (
            <p className="text-sm text-zinc-100 leading-snug">{desc.summary}</p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {desc.entry_logic && (
              <div data-testid="description-entry">
                <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">Entry</span>
                <p className="text-[12px] text-zinc-300 leading-relaxed">{desc.entry_logic}</p>
              </div>
            )}
            {desc.exit_logic && (
              <div data-testid="description-exit">
                <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">Exit</span>
                <p className="text-[12px] text-zinc-300 leading-relaxed">{desc.exit_logic}</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            <InfoCell label="Best for" value={desc.best_for} />
            <InfoCell label="Risk / Reward" value={desc.risk_reward} />
            <InfoCell label="Confidence" value={desc.confidence} capitalise />
          </div>

          {Array.isArray(desc.indicators_used) && desc.indicators_used.length > 0 && (
            <div data-testid="description-indicators" className="flex flex-wrap gap-1.5 pt-1">
              <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500 mr-1 self-center">
                indicators:
              </span>
              {desc.indicators_used.map((x, i) => (
                <span
                  key={i}
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-zinc-700 bg-zinc-900 text-zinc-300"
                >{x}</span>
              ))}
            </div>
          )}

          {Array.isArray(desc.risks) && desc.risks.length > 0 && (
            <div data-testid="description-risks">
              <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">Key risks</span>
              <ul className="list-disc list-inside text-[12px] text-zinc-400 space-y-0.5 mt-0.5">
                {desc.risks.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}

          {Array.isArray(desc.tags) && desc.tags.length > 0 && (
            <div data-testid="description-tags" className="flex flex-wrap gap-1.5 pt-1">
              {desc.tags.map((x, i) => (
                <span
                  key={i}
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
                >#{x}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {state === 'idle' && !auto && (
        <button
          data-testid="description-trigger"
          onClick={() => load(false)}
          className="text-[11px] font-mono text-cyan-300 hover:text-cyan-200 underline"
        >Generate description</button>
      )}
    </div>
  );
}

function InfoCell({ label, value, capitalise = false }) {
  return (
    <div>
      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">{label}</span>
      <p className={`text-[12px] text-zinc-200 ${capitalise ? 'capitalize' : ''}`}>
        {value || '—'}
      </p>
    </div>
  );
}
