import React, { useState, useEffect, useCallback } from 'react';
import {
  Sparkle, CircleNotch, Shield, ChartLineUp, Scales, Warning, ClockCounterClockwise, ArrowsClockwise,
} from '@phosphor-icons/react';
import {
  buildPortfolioIntelligence,
  getPortfolioIntelligenceCurrent,
  getPortfolioIntelligenceHistory,
} from '../services/api';

function MetricCard({ label, value, suffix, tone = 'default', testId }) {
  const tones = {
    default: 'text-zinc-100',
    good: 'text-emerald-400',
    warn: 'text-yellow-400',
    bad: 'text-red-400',
  };
  return (
    <div
      data-testid={testId}
      className="bg-zinc-950 border border-zinc-800 rounded p-3 flex flex-col gap-1"
    >
      <span className="text-[9px] font-mono uppercase tracking-widest text-zinc-500">
        {label}
      </span>
      <span className={`text-lg font-mono font-bold ${tones[tone]}`}>
        {value}
        {suffix && <span className="text-xs text-zinc-500 ml-1">{suffix}</span>}
      </span>
    </div>
  );
}

function AllocationBar({ row, maxAlloc }) {
  const pct = Math.round(row.allocation * 100);
  const widthPct = Math.min(100, (row.allocation / Math.max(maxAlloc, 0.01)) * 100);
  const capped = row.allocation >= 0.399;
  const floored = row.allocation <= 0.051;
  return (
    <div
      data-testid={`pi-alloc-row-${row.strategy_id}`}
      className="flex flex-col gap-1 border border-zinc-800 rounded p-2 bg-zinc-950"
    >
      <div className="flex items-center justify-between gap-2 text-[10px] font-mono">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-zinc-100 truncate">{row.strategy || row.strategy_id}</span>
          <span className="text-[9px] uppercase tracking-wider text-zinc-500 bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded">
            {row.pair}/{row.timeframe}
          </span>
          {row.style && (
            <span className="text-[9px] uppercase tracking-wider text-cyan-400/80 border border-cyan-500/20 px-1.5 py-0.5 rounded">
              {row.style}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-zinc-300">
          <span className="tabular-nums">{pct}%</span>
          <span className="text-zinc-500">risk {row.risk}</span>
        </div>
      </div>
      <div className="h-2 bg-zinc-900 rounded overflow-hidden">
        <div
          className={`h-full transition-all duration-500 ${
            capped ? 'bg-yellow-500/70' : floored ? 'bg-zinc-500/70' : 'bg-emerald-500/70'
          }`}
          style={{ width: `${widthPct}%` }}
        />
      </div>
      <div className="flex justify-between text-[9px] font-mono text-zinc-500">
        <span>
          PF {row.pf} · stab {row.stability} · pp {row.pass_probability}% · env {row.env_confidence}
        </span>
        <span>DD {row.max_drawdown_pct}%</span>
      </div>
    </div>
  );
}

function DiversificationBadge({ score }) {
  const s = Number(score) || 0;
  const tone =
    s >= 80 ? { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', label: 'DIVERSE' } :
    s >= 60 ? { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/30', label: 'BALANCED' } :
    s >= 40 ? { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', label: 'CONCENTRATED' } :
              { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', label: 'CORRELATED' };
  return (
    <div
      data-testid="pi-diversification-badge"
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded border ${tone.bg} ${tone.text} ${tone.border}`}
    >
      <Scales size={14} weight="bold" />
      <span className="text-[10px] font-mono font-bold tracking-widest">{tone.label}</span>
      <span className="text-[10px] font-mono text-zinc-400">{s}/100</span>
    </div>
  );
}

function HistoryRow({ entry }) {
  const ts = entry.built_at ? new Date(entry.built_at).toLocaleString() : '—';
  return (
    <div className="flex items-center justify-between gap-3 text-[10px] font-mono border border-zinc-800 rounded px-2 py-1.5 bg-zinc-950">
      <div className="flex items-center gap-2 text-zinc-400 min-w-0">
        <ClockCounterClockwise size={12} />
        <span className="truncate">{ts}</span>
      </div>
      <div className="flex items-center gap-3 text-zinc-300 whitespace-nowrap">
        <span>n={entry.selected_count ?? (entry.portfolio?.length || 0)}</span>
        <span className="text-emerald-400">PF {entry.expected_pf}</span>
        <span className="text-yellow-400">DD {entry.expected_dd}%</span>
        <span className="text-sky-400">div {entry.diversification_score}</span>
        <span className="text-zinc-500 uppercase">{entry.source || 'auto_factory'}</span>
      </div>
    </div>
  );
}

export default function PortfolioIntelligence() {
  const [source, setSource] = useState('auto_factory');
  const [targetMax, setTargetMax] = useState(5);
  const [maxDD, setMaxDD] = useState(10);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [cur, hist] = await Promise.all([
        getPortfolioIntelligenceCurrent(),
        getPortfolioIntelligenceHistory(10),
      ]);
      setCurrent(cur?.status === 'ok' ? cur.portfolio : null);
      setHistory(hist?.history || []);
    } catch (e) {
      // Soft-fail on refresh: don't blow up the panel.
      console.warn('Portfolio Intelligence refresh:', e.message);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const runBuild = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await buildPortfolioIntelligence({
        source,
        target_min: 3,
        target_max: Number(targetMax),
        max_portfolio_dd: Number(maxDD),
        min_weight: 0.05,
        max_weight: 0.40,
      });
      setCurrent(result);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const rows = current?.portfolio || [];
  const maxAlloc = rows.reduce((m, r) => Math.max(m, r.allocation || 0), 0.1);
  const ddTone = current ? (current.expected_dd > 10 ? 'bad' : current.expected_dd > 7 ? 'warn' : 'good') : 'default';
  const pfTone = current ? (current.expected_pf >= 1.8 ? 'good' : current.expected_pf >= 1.3 ? 'warn' : 'bad') : 'default';

  return (
    <div
      data-testid="portfolio-intelligence-section"
      className="asf-section asf-u2-panel bg-gradient-to-br from-zinc-950 to-black border border-cyan-500/20 rounded-lg p-4 mb-4 flex flex-col gap-3"
    >
      <div className="asf-section__hd flex items-center justify-between gap-3 flex-wrap">
        <div className="asf-legacy-title flex items-center gap-2">
          <Sparkle size={18} weight="fill" className="text-cyan-400" />
          <h3 className="text-sm font-mono font-bold tracking-widest text-zinc-100 uppercase">
            Portfolio Intelligence
          </h3>
          <span className="text-[9px] font-mono uppercase tracking-widest text-cyan-400/70 border border-cyan-500/20 bg-cyan-500/5 px-1.5 py-0.5 rounded">
            Phase 7 Upgrade
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 flex-wrap">
          <label className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
            source
            <select
              data-testid="pi-source-select"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[10px] font-mono text-zinc-100 focus:outline-none focus:border-cyan-500/50"
            >
              <option value="auto_factory">auto_factory</option>
              <option value="explorer">explorer</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
            size≤
            <input
              data-testid="pi-target-max-input"
              type="number"
              min={2}
              max={10}
              value={targetMax}
              onChange={(e) => setTargetMax(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 w-14 text-[10px] font-mono text-zinc-100 focus:outline-none focus:border-cyan-500/50"
            />
          </label>
          <label className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
            DD≤
            <input
              data-testid="pi-max-dd-input"
              type="number"
              min={1}
              max={50}
              step={0.5}
              value={maxDD}
              onChange={(e) => setMaxDD(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 w-14 text-[10px] font-mono text-zinc-100 focus:outline-none focus:border-cyan-500/50"
            />
            %
          </label>
          <button
            data-testid="pi-build-button"
            onClick={runBuild}
            disabled={running}
            className="flex items-center gap-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 disabled:opacity-40 disabled:cursor-not-allowed border border-cyan-500/30 text-cyan-300 px-3 py-1.5 rounded text-[10px] font-mono font-bold uppercase tracking-widest transition-colors"
          >
            {running ? <CircleNotch size={12} className="animate-spin" /> : <ChartLineUp size={12} weight="bold" />}
            {running ? 'Optimising…' : 'Build Optimised'}
          </button>
          <button
            data-testid="pi-refresh-button"
            onClick={refresh}
            className="flex items-center gap-1 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 px-2 py-1.5 rounded text-[10px] font-mono transition-colors"
            title="Refresh"
          >
            <ArrowsClockwise size={12} />
          </button>
        </div>
      </div>

      {error && (
        <div
          data-testid="pi-error-banner"
          className="flex items-center gap-2 text-[10px] font-mono text-red-400 bg-red-500/5 border border-red-500/20 rounded px-2 py-1.5"
        >
          <Warning size={12} weight="bold" /> {error}
        </div>
      )}

      {!current && !running && (
        <div
          data-testid="pi-empty-state"
          className="text-[10px] font-mono text-zinc-500 border border-dashed border-zinc-800 rounded p-6 text-center"
        >
          No optimised portfolio yet — click <span className="text-cyan-400">Build Optimised</span> to run the intelligence engine.
        </div>
      )}

      {current && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <MetricCard
              testId="pi-expected-pf"
              label="Expected PF"
              value={current.expected_pf ?? '—'}
              tone={pfTone}
            />
            <MetricCard
              testId="pi-expected-dd"
              label="Expected DD"
              value={current.expected_dd ?? '—'}
              suffix="%"
              tone={ddTone}
            />
            <MetricCard
              testId="pi-expected-pass-prob"
              label="Pass Prob"
              value={current.expected_pass_probability ?? '—'}
              suffix="%"
            />
            <MetricCard
              testId="pi-diversification-score"
              label="Diversification"
              value={current.diversification_score ?? '—'}
              suffix="/100"
              tone={current.diversification_score >= 70 ? 'good' : 'warn'}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <DiversificationBadge score={current.diversification_score} />
            <div className="text-[10px] font-mono text-zinc-400 bg-zinc-950 border border-zinc-800 px-2 py-1 rounded">
              avg|corr| <span className="text-zinc-100">{current.avg_correlation}</span>
            </div>
            {current.trimmed_count > 0 && (
              <div
                data-testid="pi-trim-indicator"
                className="flex items-center gap-1 text-[10px] font-mono text-yellow-400 bg-yellow-500/5 border border-yellow-500/20 px-2 py-1 rounded"
              >
                <Shield size={12} weight="bold" />
                trimmed {current.trimmed_count} high-DD strategy(ies)
              </div>
            )}
            {Array.isArray(current.warnings) && current.warnings.map((w, i) => (
              <div
                key={i}
                className="flex items-center gap-1 text-[10px] font-mono text-yellow-400 bg-yellow-500/5 border border-yellow-500/20 px-2 py-1 rounded"
              >
                <Warning size={12} /> {w}
              </div>
            ))}
          </div>

          <div data-testid="pi-allocation-list" className="flex flex-col gap-1.5">
            {rows.map((r) => (
              <AllocationBar key={r.strategy_id} row={r} maxAlloc={maxAlloc} />
            ))}
          </div>
        </>
      )}

      {history.length > 0 && (
        <details className="mt-1 group">
          <summary
            data-testid="pi-history-toggle"
            className="cursor-pointer text-[10px] font-mono uppercase tracking-widest text-zinc-500 hover:text-zinc-300 select-none list-none"
          >
            ▸ History ({history.length})
          </summary>
          <div data-testid="pi-history-list" className="flex flex-col gap-1 mt-2">
            {history.map((h, i) => (
              <HistoryRow key={h.portfolio_id || i} entry={h} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
