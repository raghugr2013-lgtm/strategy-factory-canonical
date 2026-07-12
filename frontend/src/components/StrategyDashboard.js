import React, { useEffect, useState } from 'react';
import {
  Lightning, CircleNotch, Trophy, Warning, ShieldCheck,
  XCircle, TrendUp, ChartLineDown, CaretRight, BookmarkSimple, Check, Plus, Flask,
} from '@phosphor-icons/react';
import { generateDashboardStrategies, saveStrategyToLibrary, autoSaveTopStrategies, listChallengeFirms, mutateStrategy, fetchQualityProfile, generateMultiAssetPortfolio, savePortfolio, listSavedPortfolios, loadSavedPortfolio, deleteSavedPortfolio } from '../services/api';
import { useDatasetAvailability } from '../hooks/useDatasetAvailability';
import { DataAvailabilityBanner, DataLoadStatus, PairOptions, TimeframeOptions } from './DataAvailability';
import StrategyDescription from './StrategyDescription';
import AddFirmModal from './AddFirmModal';
import FirmMatchPanel from './FirmMatchPanel';
import PipelineLogsPanel from './PipelineLogsPanel';
// COMMAND · U.2 — additive lineage chip. Renders ONLY when body has
// [data-ui="command"] (CSS-gated via .cmd-only-show). Mocked data for the
// A/B experiment until /api/strategies/:id/lineage lands in U.4.
import { LineageInline, mockLineage } from '../command/shell/LineageStrip';

const STYLES = ['trend-following', 'mean-reversion', 'breakout', 'scalping'];
const DEFAULT_FIRMS = [{ slug: 'ftmo', name: 'FTMO' }, { slug: 'fundednext', name: 'FundedNext' }, { slug: 'pipfarm', name: 'PipFarm' }];

// ── Badges ────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }) {
  const map = {
    TRADE:  { c: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40', icon: TrendUp,      label: 'TRADE' },
    RISKY:  { c: 'bg-amber-500/15 text-amber-400 border-amber-500/40',       icon: Warning,      label: 'RISKY' },
    REJECT: { c: 'bg-red-500/15 text-red-400 border-red-500/40',             icon: XCircle,      label: 'REJECT' },
  };
  const m = map[verdict] || { c: 'bg-zinc-800 text-zinc-400 border-zinc-700', icon: Warning, label: verdict || '—' };
  const Icon = m.icon;
  return (
    <span
      data-testid={`verdict-${verdict || 'unknown'}`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded ${m.c}`}
    >
      <Icon size={11} weight="bold" /> {m.label}
    </span>
  );
}

function StatusBadge({ status }) {
  const map = {
    SAFE:  { c: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40', icon: ShieldCheck, label: 'SAFE' },
    RISKY: { c: 'bg-amber-500/15 text-amber-400 border-amber-500/40',       icon: Warning,     label: 'RISKY' },
    FAIL:  { c: 'bg-red-500/15 text-red-400 border-red-500/40',             icon: XCircle,     label: 'FAIL' },
  };
  const m = map[status] || { c: 'bg-zinc-800 text-zinc-400 border-zinc-700', icon: Warning, label: status || '—' };
  const Icon = m.icon;
  return (
    <span
      data-testid={`panel-status-${status || 'unknown'}`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded ${m.c}`}
    >
      <Icon size={11} weight="bold" /> {m.label}
    </span>
  );
}

function Metric({ label, value, mono = true, color = 'text-white', testId }) {
  return (
    <div data-testid={testId} className="flex flex-col">
      <span className="text-[9px] text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className={`${mono ? 'font-mono' : ''} ${color} text-sm font-semibold`}>{value ?? '—'}</span>
    </div>
  );
}

// ── Decision-level helpers (presentational only, no backend changes) ──

function pfColorClass(pf) {
  if (pf == null || Number.isNaN(Number(pf))) return 'text-zinc-300';
  const v = Number(pf);
  if (v > 1.2) return 'text-emerald-400';
  if (v >= 1.0) return 'text-amber-400';
  return 'text-red-400';
}

function ddColorClass(dd) {
  if (dd == null || Number.isNaN(Number(dd))) return 'text-zinc-300';
  const v = Number(dd);
  if (v < 20) return 'text-emerald-400';
  if (v <= 30) return 'text-amber-400';
  return 'text-red-400';
}

function deriveQuickVerdict(pf, dd) {
  const hasPF = pf != null && !Number.isNaN(Number(pf));
  const hasDD = dd != null && !Number.isNaN(Number(dd));
  if (!hasPF && !hasDD) return null;
  const p = hasPF ? Number(pf) : null;
  const d = hasDD ? Number(dd) : null;
  // Reject wins over Neutral wins over Promising (strictest gate first)
  if ((p != null && p < 1.0) || (d != null && d > 30)) return 'REJECT';
  if (p != null && p > 1.2 && d != null && d < 20) return 'PROMISING';
  return 'NEUTRAL';
}

function QuickVerdictBadge({ verdict }) {
  if (!verdict) return null;
  const map = {
    PROMISING: { c: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40', label: 'Promising' },
    NEUTRAL:   { c: 'bg-amber-500/15 text-amber-300 border-amber-500/40',       label: 'Neutral'   },
    REJECT:    { c: 'bg-red-500/15 text-red-300 border-red-500/40',             label: 'Reject'    },
  };
  const m = map[verdict];
  return (
    <span
      data-testid={`quick-verdict-${verdict.toLowerCase()}`}
      title="Quick verdict from PF + DD thresholds"
      className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded ${m.c}`}
    >
      {m.label}
    </span>
  );
}

// ── Strategy Card ─────────────────────────────────────────────────────

function StrategyCard({ s, onDeepDive, onSave, onImprove, saveState, improveState }) {
  const ddRaw = s.max_drawdown;
  const pfRaw = s.backtest?.profit_factor;
  const retRaw = s.backtest?.total_return_pct;
  const trades = s.backtest?.total_trades;

  const dd = ddRaw != null ? `${ddRaw}%` : '—';
  const daily = s.daily_drawdown != null ? `${s.daily_drawdown}%` : '—';
  const prob = s.pass_probability != null ? `${Math.round(s.pass_probability)}%` : '—';
  const score = s.score != null ? s.score.toFixed(1) : '—';
  const wr = s.backtest?.win_rate != null ? `${s.backtest.win_rate}%` : '—';
  const pf = pfRaw != null ? pfRaw : '—';
  const ret = retRaw != null ? `${retRaw}%` : '—';
  const tradesDisplay = trades != null ? trades : '—';

  const pfColor = pfColorClass(pfRaw);
  const ddColor = ddColorClass(ddRaw);
  const retColor = retRaw == null ? 'text-zinc-300' : (retRaw > 0 ? 'text-emerald-400' : 'text-red-400');
  const quickVerdict = deriveQuickVerdict(pfRaw, ddRaw);

  // Save eligibility mirrors backend rule: TRADE (and not FAIL) always;
  // RISKY needs score>=45 AND (pass_prob>=50 OR consistency/stability>=50).
  const pp = s.pass_probability != null ? s.pass_probability : 0;
  const stab = s.consistency_score != null ? s.consistency_score : 0;
  const eligible =
    s.status !== 'FAIL' && (
      s.verdict === 'TRADE' ||
      (s.verdict === 'RISKY' && (s.score || 0) >= 45 && (pp >= 50 || stab >= 50))
    );

  return (
    <div
      data-testid={`strategy-card-rank-${s.rank}`}
      className="card-premium card-premium-hover p-4"
    >
      {/* Top row: rank + verdict + status */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-md bg-zinc-900 border border-zinc-800">
            {s.rank === 1 ? (
              <Trophy size={18} weight="fill" className="text-amber-400" />
            ) : (
              <span className="font-mono text-sm font-bold text-zinc-300">#{s.rank}</span>
            )}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold text-white">
                {s.pair} · {s.timeframe}
              </span>
              {s.refined && (
                <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-cyan-500/40 bg-cyan-500/10 text-cyan-400">
                  refined
                </span>
              )}
            </div>
            <span className="text-[10px] font-mono text-zinc-500">
              score <span className="text-zinc-300">{score}</span>
              {s.confidence != null && (
                <> · conf <span className="text-zinc-300">{s.confidence}</span></>
              )}
            </span>
            {/* COMMAND · U.2 — lineage chip (CSS-gated: visible only when body
                has [data-ui="command"]). Pure CSS, mocked data, zero impact
                on legacy operators. See LineageStrip.jsx + tokens.css. */}
            <span className="cmd-only-show" style={{ marginTop: 4, display: 'inline-flex' }}>
              <LineageInline lineage={mockLineage(s.strategy_id || `STR-${s.rank}`)} />
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-1 items-end">
          <div className="flex items-center gap-1 flex-wrap justify-end">
            <VerdictBadge verdict={s.verdict} />
            <QuickVerdictBadge verdict={quickVerdict} />
          </div>
          <StatusBadge status={s.status} />
        </div>
      </div>

      {/* Prop-firm sub-line (pass-prob + daily DD kept compact) */}
      <div
        data-testid={`card-propfirm-line-${s.rank}`}
        className="flex items-center gap-4 pb-3 text-[10px] font-mono text-zinc-500 border-b border-zinc-800/60"
      >
        <span>pass prob <span className="text-emerald-400 font-semibold">{prob}</span></span>
        <span>daily dd <span className="text-amber-300 font-semibold">{daily}</span></span>
        {s.consistency_score != null && (
          <span>consistency <span className="text-zinc-300 font-semibold">{s.consistency_score}</span></span>
        )}
      </div>

      {/* Key metrics — Profit Factor, Max DD, Trades, Win Rate, Net Return */}
      <div className="grid grid-cols-5 gap-3 pt-3">
        <Metric label="PF"        value={pf}            color={pfColor} testId={`metric-pf-${s.rank}`} />
        <Metric label="Max DD"    value={dd}            color={ddColor} testId={`metric-dd-${s.rank}`} />
        <Metric label="Trades"    value={tradesDisplay}                 testId={`metric-trades-${s.rank}`} />
        <Metric label="Win Rate"  value={wr}                            testId={`metric-wr-${s.rank}`} />
        <Metric label="Net Return" value={ret}          color={retColor} testId={`metric-return-${s.rank}`} />
      </div>

      {/* Recommendation */}
      {(s.recommendation || s.reason) && (
        <div className="mt-3 pt-3 border-t border-zinc-800/60">
          <p className="text-[11px] text-zinc-400 leading-relaxed">
            {s.recommendation || s.reason}
          </p>
        </div>
      )}

      {/* Phase 3 — Engine telemetry chips (MTF / regime / ATR / trailing) */}
      <PhaseTelemetrySection phase2={s.phase2} phase3={s.phase3} phase4={s.phase4} phase5={s.phase5} />

      {/* Phase 3 — Random-search optimisation result for this card */}
      <OptimizationSection optimized={s.optimized} baseline={s.backtest} />

      {/* Action */}
      <div className="mt-3 pt-3 border-t border-zinc-800/60 flex items-center justify-end gap-2">
        <SaveButton
          rank={s.rank}
          eligible={eligible}
          saveState={saveState}
          onClick={() => onSave(s)}
        />
        <button
          data-testid={`improve-btn-${s.rank}`}
          onClick={() => onImprove(s)}
          disabled={improveState === 'loading'}
          title="Run mutation engine on this strategy (Phase 14/15/16)"
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-violet-300 hover:text-violet-200 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/30 hover:border-violet-500/50 disabled:opacity-60 disabled:cursor-wait px-3 py-1.5 rounded transition-colors"
        >
          {improveState === 'loading' ? (
            <><CircleNotch size={11} weight="bold" className="animate-spin" /> Improving…</>
          ) : (
            <><Flask size={11} weight="bold" /> Improve</>
          )}
        </button>
        <button
          data-testid={`deep-dive-btn-${s.rank}`}
          onClick={() => onDeepDive(s)}
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700 px-3 py-1.5 rounded transition-colors"
        >
          Deep Dive <CaretRight size={11} weight="bold" />
        </button>
      </div>
    </div>
  );
}

function SaveButton({ rank, eligible, saveState, onClick }) {
  const state = saveState || 'idle';
  let label = 'Save';
  let Icon = BookmarkSimple;
  let cls = 'text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border-zinc-800 hover:border-zinc-700';
  if (!eligible) {
    cls = 'text-zinc-600 bg-zinc-950 border-zinc-900 cursor-not-allowed';
    label = 'Not saveable';
  } else if (state === 'saving') {
    Icon = CircleNotch;
    label = 'Saving…';
    cls = 'text-zinc-400 bg-zinc-900 border-zinc-800 cursor-wait';
  } else if (state === 'saved') {
    Icon = Check;
    label = 'Saved';
    cls = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
  } else if (state === 'duplicate') {
    Icon = Check;
    label = 'Already in library';
    cls = 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30';
  } else if (state === 'error') {
    label = 'Retry save';
    cls = 'text-red-400 bg-red-500/10 border-red-500/30';
  }
  return (
    <button
      data-testid={`save-btn-${rank}`}
      disabled={!eligible || state === 'saving' || state === 'saved' || state === 'duplicate'}
      onClick={onClick}
      className={`inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider border px-3 py-1.5 rounded transition-colors ${cls}`}
    >
      <Icon size={11} weight="bold" className={state === 'saving' ? 'animate-spin' : ''} />
      {label}
    </button>
  );
}

// ── Phase 3 — Portfolio / Optimisation / Phase-telemetry panels ──────

function gradeColor(grade) {
  switch ((grade || '').toUpperCase()) {
    case 'A': return 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10';
    case 'B': return 'text-cyan-300 border-cyan-500/40 bg-cyan-500/10';
    case 'C': return 'text-amber-300 border-amber-500/40 bg-amber-500/10';
    case 'D': return 'text-orange-300 border-orange-500/40 bg-orange-500/10';
    case 'F': return 'text-red-300 border-red-500/40 bg-red-500/10';
    default:  return 'text-zinc-300 border-zinc-700 bg-zinc-900';
  }
}

function fmtPct(v, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return `${Number(v).toFixed(digits)}%`;
}

function fmtNum(v, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Number(v).toFixed(digits);
}

// ── P4 — Multi-Asset Portfolio Panel ────────────────────────────────

function MultiAssetPanel({
  datasets, availablePairs, maPairs, setMaPairs,
  timeframe, loading, error, result, onRun,
  // P1 — persistence wiring (all optional; panel falls back to
  // the non-persistent layout when they're absent).
  portfolioName, setPortfolioName,
  onSave, saveInFlight, saveMessage,
  loadedPortfolio, onClearLoaded,
}) {
  // `datasets` is the raw API response (`{pairs:[{pair, timeframes:[...]}]}`).
  // Only offer pairs that the backend confirms have ≥ min_candles data
  // for the currently-selected timeframe. This mirrors the dataset
  // availability banner logic so the user can never submit a pair that
  // will certainly fail the backend guard.
  const pairRows = (datasets && datasets.pairs) || [];
  const withData = pairRows
    .filter((d) => (d.timeframes || []).some(
      (t) => t.tf === timeframe && t.sufficient,
    ))
    .map((d) => d.pair);

  const selectablePairs = withData.length >= 2
    ? withData
    : Array.from(new Set([...(availablePairs || []), ...withData]));

  const togglePair = (p) => {
    setMaPairs((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );
  };

  const disabled = loading || (maPairs || []).length < 2;

  return (
    <div data-testid="multi-asset-panel" className="card-premium p-4 space-y-3 border-violet-500/30 bg-violet-950/10">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.18em] text-violet-300 font-semibold">
            Multi-Asset Portfolio
          </div>
          <div className="text-[11px] font-mono text-zinc-400">
            Run generation + asset gate (5-seed baseline) per pair; combine survivors into a diversified portfolio.
          </div>
        </div>
        <button
          data-testid="multi-asset-run-btn"
          onClick={onRun}
          disabled={disabled}
          title={
            (maPairs || []).length < 2
              ? 'Select at least 2 pairs'
              : `Run multi-asset rollout on ${maPairs.length} pairs (${timeframe})`
          }
          className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white border border-violet-400/40 px-3 py-2 rounded-md transition-colors"
        >
          {loading ? (
            <><CircleNotch size={12} weight="bold" className="animate-spin" /> Running multi-asset…</>
          ) : (
            <><Lightning size={12} weight="fill" /> Run Multi-Asset Rollout</>
          )}
        </button>
      </div>

      <div data-testid="multi-asset-pairs" className="flex flex-wrap gap-2">
        {selectablePairs.length === 0 ? (
          <span className="text-[11px] font-mono text-zinc-500">
            No pairs with sufficient data for {timeframe}. Load data in the Generate panel first.
          </span>
        ) : selectablePairs.map((p) => {
          const on = (maPairs || []).includes(p);
          const hasData = withData.includes(p);
          return (
            <label
              key={p}
              data-testid={`multi-asset-pair-${p}`}
              className={`inline-flex items-center gap-1.5 px-2 py-1 text-[11px] font-mono uppercase tracking-wider border rounded cursor-pointer transition-colors ${
                on
                  ? 'border-violet-400 bg-violet-500/20 text-violet-200'
                  : hasData
                    ? 'border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-violet-400/60'
                    : 'border-zinc-800 bg-zinc-950 text-zinc-500 opacity-60'
              }`}
            >
              <input
                type="checkbox"
                checked={on}
                onChange={() => togglePair(p)}
                disabled={!hasData}
                className="accent-violet-500"
              />
              <span>{p}</span>
              {!hasData ? <span className="opacity-60">(no data)</span> : null}
            </label>
          );
        })}
      </div>

      {error ? (
        <div data-testid="multi-asset-error" className="text-[11px] font-mono text-red-300 bg-red-950/30 border border-red-900/50 rounded p-2">
          {error}
        </div>
      ) : null}

      {result ? (
        <MultiAssetResults
          result={result}
          portfolioName={portfolioName}
          setPortfolioName={setPortfolioName}
          onSave={onSave}
          saveInFlight={saveInFlight}
          saveMessage={saveMessage}
          loadedPortfolio={loadedPortfolio}
          onClearLoaded={onClearLoaded}
        />
      ) : null}
    </div>
  );
}


function MultiAssetResults({
  result,
  portfolioName, setPortfolioName,
  onSave, saveInFlight, saveMessage,
  loadedPortfolio, onClearLoaded,
}) {
  const port = result.portfolio || null;
  const cm = port?.combined_metrics || {};
  const contribs = port?.asset_contributions_pct || {};

  return (
    <div data-testid="multi-asset-results" className="space-y-3 pt-3 border-t border-zinc-800/60">
      {/* Per-pair gate + contribution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {(result.per_pair || []).map((p) => {
          const g = p.gate || {};
          const passed = !!p.passed;
          return (
            <div
              key={p.pair}
              data-testid={`multi-asset-pair-card-${p.pair}`}
              className={`p-2 border rounded text-[11px] font-mono space-y-1 ${
                passed
                  ? 'border-emerald-500/30 bg-emerald-950/10'
                  : 'border-red-500/30 bg-red-950/10'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="uppercase tracking-wider font-semibold">
                  {p.pair} · {p.timeframe}
                </span>
                <span data-testid={`multi-asset-pair-status-${p.pair}`}
                  className={passed ? 'text-emerald-300' : 'text-red-300'}>
                  {passed ? 'PASS' : 'REJECT'}
                </span>
              </div>
              <div className="text-zinc-400">
                Gate: median OOS PF {g.median_oos_pf ?? '—'} · max OOS DD {g.max_oos_dd ?? '—'}%
                {g.threshold != null ? ` · thr ${g.threshold}` : ''}
              </div>
              {!passed ? (
                <div className="text-red-300">
                  Reason: {g.reason || p.error || 'no_top_strategies'}
                </div>
              ) : (
                <div className="text-zinc-300">
                  Contribution: <span className="text-emerald-300">{contribs[p.pair] != null ? `${contribs[p.pair]}%` : '—'}</span>
                  {' · '}
                  Top strategies: {(p.top_strategies || []).length}
                </div>
              )}
              <div className="text-zinc-500 text-[10px]">
                candles {p.candles} · {p.elapsed_seconds}s
              </div>
            </div>
          );
        })}
      </div>

      {/* Combined portfolio KPIs */}
      {port ? (
        <div data-testid="multi-asset-portfolio" className="p-3 border border-violet-500/30 rounded bg-violet-950/20 space-y-2">
          <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-wider">
            <span className="text-violet-200 font-semibold">Combined Portfolio</span>
            <span data-testid="multi-asset-grade" className="text-violet-300">
              Grade {port.diversification_grade || '—'}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono">
            <KPI testId="ma-kpi-strategies" label="Strategies" value={port.num_strategies ?? '—'} />
            <KPI testId="ma-kpi-dd"         label="Max DD"    value={cm.max_drawdown_pct != null ? `${cm.max_drawdown_pct}%` : '—'} />
            <KPI testId="ma-kpi-return"     label="Return"    value={cm.total_return_pct != null ? `${cm.total_return_pct}%` : '—'} />
            <KPI testId="ma-kpi-corr"       label="Avg Corr"  value={port.avg_correlation ?? '—'} />
          </div>
          <div data-testid="multi-asset-contributions" className="flex flex-wrap gap-1.5">
            {Object.keys(contribs).length === 0 ? (
              <span className="text-zinc-500 text-[10px] font-mono">No contributions recorded.</span>
            ) : Object.entries(contribs).map(([pair, pct]) => (
              <span
                key={pair}
                data-testid={`multi-asset-contribution-${pair}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono border border-violet-500/40 bg-violet-500/10 text-violet-200 rounded"
              >
                {pair}: <span className="text-emerald-300 font-semibold">{pct}%</span>
              </span>
            ))}
          </div>
          {(port.warnings || []).length > 0 ? (
            <div className="text-[10px] font-mono text-amber-300 bg-amber-950/20 border border-amber-900/40 p-1.5 rounded">
              {port.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
            </div>
          ) : null}

          {/* P1 — Save controls. Only grade A/B portfolios can be saved
               (backend enforces this) and we only show the input when a
               handler is wired in. */}
          {onSave ? (
            <SavePortfolioControls
              grade={port.diversification_grade}
              portfolioName={portfolioName}
              setPortfolioName={setPortfolioName}
              onSave={onSave}
              saveInFlight={saveInFlight}
              saveMessage={saveMessage}
              loadedPortfolio={loadedPortfolio}
              onClearLoaded={onClearLoaded}
            />
          ) : null}
        </div>
      ) : (
        <div className="text-[11px] font-mono text-zinc-400">
          Portfolio not built — fewer than 2 assets passed the gate.
          {result.pairs_rejected?.length > 0
            ? ` Rejected: ${result.pairs_rejected.map((r) => `${r.pair}(${r.reason})`).join(', ')}`
            : ''}
        </div>
      )}
    </div>
  );
}


function KPI({ label, value, testId }) {
  return (
    <div data-testid={testId} className="p-2 border border-zinc-800 rounded bg-zinc-950">
      <div className="text-[10px] font-mono uppercase tracking-[0.12em] text-zinc-500">{label}</div>
      <div className="text-sm font-mono text-zinc-100">{value}</div>
    </div>
  );
}


// ── P1 — Save / load / delete controls ────────────────────────────────

function SavePortfolioControls({
  grade, portfolioName, setPortfolioName,
  onSave, saveInFlight, saveMessage,
  loadedPortfolio, onClearLoaded,
}) {
  const gradeUpper = (grade || '').toUpperCase();
  const canSave = gradeUpper === 'A' || gradeUpper === 'B';

  return (
    <div data-testid="save-portfolio-controls" className="mt-2 pt-2 border-t border-violet-900/40 space-y-1.5">
      {loadedPortfolio ? (
        <div data-testid="loaded-portfolio-banner" className="flex items-center justify-between text-[11px] font-mono text-cyan-300 bg-cyan-950/30 border border-cyan-900/40 rounded p-1.5">
          <span>Loaded · <span className="text-cyan-200 font-semibold">{loadedPortfolio.name}</span></span>
          <button
            data-testid="loaded-portfolio-clear"
            onClick={onClearLoaded}
            className="text-[10px] font-mono text-cyan-200 hover:text-cyan-100 underline"
          >clear</button>
        </div>
      ) : null}
      {canSave ? (
        <div className="flex items-center gap-2 flex-wrap">
          <input
            data-testid="portfolio-name-input"
            type="text"
            placeholder="Portfolio name (e.g. Gold+FX balanced)"
            value={portfolioName || ''}
            onChange={(e) => setPortfolioName(e.target.value)}
            disabled={saveInFlight}
            className="flex-1 min-w-[200px] px-2 py-1 text-[11px] font-mono bg-zinc-900 border border-zinc-700 rounded text-zinc-100 placeholder-zinc-500 focus:border-violet-400 focus:outline-none disabled:opacity-50"
          />
          <button
            data-testid="save-portfolio-btn"
            onClick={onSave}
            disabled={saveInFlight || !(portfolioName || '').trim()}
            className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white border border-emerald-400/40 px-2.5 py-1 rounded transition-colors"
          >
            {saveInFlight ? 'Saving…' : 'Save Portfolio'}
          </button>
        </div>
      ) : (
        <div data-testid="save-blocked-notice" className="text-[10px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded p-1.5">
          Save is only enabled for grade A or B portfolios (current: {gradeUpper || '—'}).
        </div>
      )}
      {saveMessage ? (
        <div
          data-testid={saveMessage.type === 'success' ? 'save-portfolio-success' : 'save-portfolio-error'}
          className={`text-[10px] font-mono rounded p-1.5 ${
            saveMessage.type === 'success'
              ? 'text-emerald-300 bg-emerald-950/30 border border-emerald-900/40'
              : 'text-red-300 bg-red-950/30 border border-red-900/40'
          }`}
        >
          {saveMessage.text}
        </div>
      ) : null}
    </div>
  );
}


function SavedPortfoliosPanel({ items, loading, error, onRefresh, onLoad, onDelete }) {
  return (
    <div data-testid="saved-portfolios-panel" className="card-premium p-4 space-y-2 border-cyan-500/30 bg-cyan-950/10">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.18em] text-cyan-300 font-semibold">
            Saved Portfolios
          </div>
          <div className="text-[11px] font-mono text-zinc-400">
            Reload any previously-saved portfolio into the dashboard without re-running the pipeline.
          </div>
        </div>
        <button
          data-testid="saved-portfolios-refresh-btn"
          onClick={onRefresh}
          disabled={loading}
          className="text-[10px] font-mono uppercase tracking-wider bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-700 px-2.5 py-1 rounded disabled:opacity-40"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error ? (
        <div data-testid="saved-portfolios-error" className="text-[11px] font-mono text-red-300 bg-red-950/30 border border-red-900/40 rounded p-2">{error}</div>
      ) : null}

      {items && items.length > 0 ? (
        <div data-testid="saved-portfolios-list" className="space-y-1.5">
          {items.map((p) => {
            const cm = p.combined_metrics || {};
            return (
              <div
                key={p.portfolio_id}
                data-testid={`saved-portfolio-item-${p.portfolio_id}`}
                className="flex items-center justify-between gap-2 text-[11px] font-mono bg-zinc-950 border border-zinc-800 rounded p-2"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-zinc-100 truncate">{p.name}</span>
                    <span className={`px-1.5 py-0.5 text-[10px] border rounded ${
                      p.diversification_grade === 'A'
                        ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                        : 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300'
                    }`}>Grade {p.diversification_grade || '—'}</span>
                  </div>
                  <div className="text-[10px] text-zinc-400 flex gap-2 flex-wrap">
                    <span>{(p.pairs || []).join(' + ') || '—'}</span>
                    <span>· {p.num_strategies || 0} strat</span>
                    <span>· DD {cm.max_drawdown_pct != null ? `${cm.max_drawdown_pct}%` : '—'}</span>
                    <span>· Ret {cm.total_return_pct != null ? `${cm.total_return_pct}%` : '—'}</span>
                    <span className="text-zinc-500">· {new Date(p.created_at).toLocaleString()}</span>
                  </div>
                </div>
                <button
                  data-testid={`saved-portfolio-load-${p.portfolio_id}`}
                  onClick={() => onLoad(p.portfolio_id)}
                  className="text-[10px] font-mono uppercase tracking-wider bg-cyan-700 hover:bg-cyan-600 text-white px-2 py-1 rounded"
                >Load</button>
                <button
                  data-testid={`saved-portfolio-delete-${p.portfolio_id}`}
                  onClick={() => {
                    // eslint-disable-next-line no-alert
                    if (window.confirm(`Delete portfolio "${p.name}"?`)) onDelete(p.portfolio_id);
                  }}
                  className="text-[10px] font-mono uppercase tracking-wider bg-red-900/40 hover:bg-red-800/50 text-red-200 border border-red-900/50 px-2 py-1 rounded"
                >Delete</button>
              </div>
            );
          })}
        </div>
      ) : (
        <div data-testid="saved-portfolios-empty" className="text-[11px] font-mono text-zinc-500">
          No saved portfolios yet. Run a Multi-Asset Rollout, hit <em>Save Portfolio</em> when the grade is A or B.
        </div>
      )}
    </div>
  );
}





function PortfolioPanel({ portfolio, topStrategies }) {
  if (!portfolio) return null;
  const cm = portfolio.combined_metrics || {};
  const allocs = portfolio.suggested_allocations || portfolio.allocations || [];
  const ids = portfolio.strategy_ids || [];

  // Derive a friendly "combined PF" estimate: weighted average of each
  // top strategy's PF (the backend doesn't ship a true combined PF, so
  // we surface a clearly-labeled weighted blend instead — additive,
  // best-effort).
  let pfBlended = null;
  if (topStrategies?.length && allocs.length === topStrategies.length) {
    let acc = 0, wsum = 0;
    topStrategies.forEach((s, i) => {
      const pf = Number(s?.backtest?.profit_factor);
      const w = Number(allocs[i]);
      if (Number.isFinite(pf) && Number.isFinite(w)) {
        acc += pf * w; wsum += w;
      }
    });
    if (wsum > 0) pfBlended = acc / wsum;
  }
  const grade = portfolio.diversification_grade || '—';

  return (
    <div data-testid="portfolio-panel" className="card-premium p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-400">
            Portfolio
          </span>
          <span className="text-[10px] font-mono text-zinc-500">
            · {portfolio.num_strategies ?? topStrategies?.length ?? 0} strategies
          </span>
        </div>
        <span
          data-testid="portfolio-grade"
          className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider border rounded ${gradeColor(grade)}`}
          title="Diversification grade — A is best, F is worst"
        >
          Grade {grade}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Metric
          label="Combined PF"
          value={pfBlended != null ? pfBlended.toFixed(2) : '—'}
          color={pfColorClass(pfBlended)}
          testId="portfolio-combined-pf"
        />
        <Metric
          label="Combined DD"
          value={fmtPct(cm.max_drawdown_pct)}
          color={ddColorClass(cm.max_drawdown_pct)}
          testId="portfolio-combined-dd"
        />
        <Metric
          label="Total Return"
          value={fmtPct(cm.total_return_pct)}
          color={(cm.total_return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}
          testId="portfolio-total-return"
        />
        <Metric
          label="Avg Corr"
          value={fmtNum(portfolio.avg_correlation, 3)}
          testId="portfolio-avg-corr"
        />
        <Metric
          label="Risk Score"
          value={portfolio.portfolio_risk_score != null ? Number(portfolio.portfolio_risk_score).toFixed(1) : '—'}
          color={(portfolio.portfolio_risk_score ?? 100) <= 40 ? 'text-emerald-400' : (portfolio.portfolio_risk_score ?? 100) <= 60 ? 'text-amber-400' : 'text-red-400'}
          testId="portfolio-risk-score"
        />
      </div>

      {/* Suggested allocations */}
      {allocs.length > 0 && (
        <div className="mt-4 pt-3 border-t border-zinc-800/60">
          <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
            Suggested allocation
            <span className="text-zinc-600 ml-2">· inverse-DD weighting</span>
          </div>
          <div className="space-y-1.5" data-testid="portfolio-allocations">
            {allocs.map((w, i) => {
              const pct = Math.round(Number(w) * 1000) / 10; // 1-decimal %
              const idDisplay = ids[i] || `strategy_${i + 1}`;
              const labelStrategy = topStrategies?.[i];
              const label = labelStrategy
                ? `#${labelStrategy.rank} · ${labelStrategy.pair}/${labelStrategy.timeframe}`
                : idDisplay;
              return (
                <div
                  key={`${idDisplay}-${i}`}
                  data-testid={`portfolio-allocation-${i}`}
                  className="flex items-center gap-2 text-[11px] font-mono"
                >
                  <span className="w-32 text-zinc-300 truncate">{label}</span>
                  <div className="flex-1 h-1.5 bg-zinc-900 border border-zinc-800 rounded overflow-hidden">
                    <div
                      className="h-full bg-cyan-500/70"
                      style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
                    />
                  </div>
                  <span className="w-12 text-right text-zinc-200">{pct.toFixed(1)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {Array.isArray(portfolio.warnings) && portfolio.warnings.length > 0 && (
        <div className="mt-3 pt-3 border-t border-zinc-800/60 space-y-1" data-testid="portfolio-warnings">
          {portfolio.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[11px] text-amber-300/90">
              <Warning size={11} weight="bold" className="mt-0.5 flex-shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OptimizationSection({ optimized, baseline }) {
  if (!optimized) return null;
  const isMet = optimized.is_metrics || {};
  const oosMet = optimized.oos_metrics || {};
  const params = optimized.params || {};
  const optimizerName = optimized.optimizer || 'random_search';
  // P2 — use explicit backend `comparison` block when present; fall back
  // to computing delta from baseline for backward-compat with older runs.
  const cmp = optimized.comparison || null;
  const basePF = cmp ? cmp.before_is_pf : Number(baseline?.profit_factor);
  const newPF  = cmp ? cmp.after_is_pf  : Number(isMet.profit_factor);
  const oosBasePF = cmp ? cmp.before_oos_pf : null;
  const oosNewPF  = cmp ? cmp.after_oos_pf  : Number(oosMet.profit_factor);

  const delta = (a, b) => (Number.isFinite(a) && Number.isFinite(b)) ? (b - a) : null;
  const isPfDelta  = cmp ? cmp.is_pf_delta  : delta(basePF, newPF);
  const oosPfDelta = cmp ? cmp.oos_pf_delta : delta(oosBasePF, oosNewPF);

  const cls = (d) => d == null ? 'text-zinc-400'
    : d > 0 ? 'text-emerald-400'
    : d < 0 ? 'text-red-400'
    : 'text-zinc-400';
  const sign = (d) => (d != null && d > 0) ? '+' : '';

  const fitness = optimized.is_fitness;
  const gaInfo = optimized._ga || null;

  return (
    <div
      data-testid="optimization-section"
      className="mt-3 pt-3 border-t border-zinc-800/60"
    >
      <div className="flex items-center justify-between mb-2">
        <span
          data-testid="opt-optimizer-name"
          className={`text-[10px] font-mono uppercase tracking-[0.16em] ${
            optimizerName === 'ga' ? 'text-emerald-300' : 'text-cyan-300'
          }`}
        >
          Optimization ·{' '}
          {optimizerName === 'ga'
            ? 'Genetic Algorithm'
            : 'Random Search'}
        </span>
        <span className="text-[10px] font-mono text-zinc-500">
          {optimizerName === 'ga' && gaInfo
            ? `gen ${gaInfo.generations} · pop ${gaInfo.population_size} · ${gaInfo.evaluations || '—'} evals`
            : optimized.variants_evaluated != null
              ? `${optimized.variants_evaluated} variants`
              : ''}
        </span>
      </div>

      {/* Before → After comparison (P2) */}
      {cmp && (
        <div
          data-testid="opt-comparison"
          className="mb-3 grid grid-cols-2 gap-3 p-2 rounded border border-zinc-800/60 bg-zinc-900/40 dark:bg-zinc-950/60"
        >
          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
              IS · PF
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[11px] font-mono text-zinc-400 line-through">
                {basePF != null ? Number(basePF).toFixed(2) : '—'}
              </span>
              <span className="text-zinc-500">→</span>
              <span className={`text-sm font-mono font-semibold ${pfColorClass(newPF)}`}>
                {newPF != null ? Number(newPF).toFixed(2) : '—'}
              </span>
              <span className={`text-[11px] font-mono ${cls(isPfDelta)}`} data-testid="opt-pf-delta">
                ({sign(isPfDelta)}{isPfDelta == null ? '—' : Number(isPfDelta).toFixed(2)})
              </span>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
              OOS · PF
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[11px] font-mono text-zinc-400 line-through">
                {oosBasePF != null ? Number(oosBasePF).toFixed(2) : '—'}
              </span>
              <span className="text-zinc-500">→</span>
              <span className={`text-sm font-mono font-semibold ${pfColorClass(oosNewPF)}`}>
                {oosNewPF != null ? Number(oosNewPF).toFixed(2) : '—'}
              </span>
              <span className={`text-[11px] font-mono ${cls(oosPfDelta)}`} data-testid="opt-oos-pf-delta">
                ({sign(oosPfDelta)}{oosPfDelta == null ? '—' : Number(oosPfDelta).toFixed(2)})
              </span>
            </div>
          </div>
          {/* P2-stability — IS↔OOS gap + stability badge */}
          {cmp.pf_gap !== undefined && cmp.pf_gap !== null && (
            <div className="col-span-2 pt-1.5 mt-1 border-t border-zinc-800/50 flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                IS − OOS gap
              </span>
              <div className="flex items-center gap-2">
                <span
                  data-testid="opt-pf-gap"
                  className={`text-[11px] font-mono ${
                    Math.abs(cmp.pf_gap) <= 0.3 ? 'text-emerald-300'
                      : Math.abs(cmp.pf_gap) <= 0.6 ? 'text-amber-300'
                      : 'text-red-300'
                  }`}
                >
                  {cmp.pf_gap >= 0 ? '+' : ''}{Number(cmp.pf_gap).toFixed(2)}
                </span>
                <span
                  data-testid="opt-stability-badge"
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider border ${
                    Math.abs(cmp.pf_gap) <= 0.3
                      ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
                      : Math.abs(cmp.pf_gap) <= 0.6
                      ? 'text-amber-300 border-amber-500/40 bg-amber-500/10'
                      : 'text-red-300 border-red-500/40 bg-red-500/10'
                  }`}
                  title={
                    Math.abs(cmp.pf_gap) <= 0.3
                      ? 'Consistent — IS and OOS match closely'
                      : Math.abs(cmp.pf_gap) <= 0.6
                      ? 'Moderate — some IS↔OOS divergence'
                      : 'Overfit — large IS↔OOS divergence'
                  }
                >
                  {Math.abs(cmp.pf_gap) <= 0.3
                    ? 'Consistent'
                    : Math.abs(cmp.pf_gap) <= 0.6
                    ? 'Moderate'
                    : 'Overfit'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric
          label="Fitness"
          value={fitness != null ? Number(fitness).toFixed(2) : '—'}
          color="text-cyan-300"
          testId="opt-fitness"
        />
        <Metric
          label="IS PF"
          value={isMet.profit_factor != null ? Number(isMet.profit_factor).toFixed(2) : '—'}
          color={pfColorClass(isMet.profit_factor)}
          testId="opt-is-pf"
        />
        <Metric
          label="OOS PF"
          value={oosMet.profit_factor != null ? Number(oosMet.profit_factor).toFixed(2) : '—'}
          color={pfColorClass(oosMet.profit_factor)}
          testId="opt-oos-pf"
        />
        <Metric
          label="DD (IS)"
          value={isMet.max_drawdown_pct != null ? `${Number(isMet.max_drawdown_pct).toFixed(1)}%` : '—'}
          color={ddColorClass(isMet.max_drawdown_pct)}
          testId="opt-is-dd"
        />
      </div>

      {Object.keys(params).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5" data-testid="opt-params">
          {Object.entries(params).map(([k, v]) => (
            <span
              key={k}
              className="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-300 bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5"
            >
              <span className="text-zinc-500">{k}</span>
              <span className="text-zinc-100">{String(v)}</span>
            </span>
          ))}
        </div>
      )}

      {/* P2 — Quality-aware optimization indicator */}
      {optimized.signal_quality && optimized.signal_quality.filter_enabled && (
        <div
          data-testid="opt-quality-aware"
          className="mt-2 flex items-center gap-2 text-[10px] font-mono px-2 py-1 rounded border border-cyan-500/30 bg-cyan-500/5 text-cyan-300"
          title="Optimizer evaluated every variant inside the high-quality entry space (entries with score < threshold were rejected during evaluation)."
        >
          <span className="font-semibold uppercase tracking-wider">Quality-aware</span>
          <span className="text-zinc-400">·</span>
          <span>thr {optimized.signal_quality.threshold}</span>
          <span className="text-zinc-500">|</span>
          <span data-testid="opt-quality-is">
            IS avg {optimized.signal_quality.is_avg_score ?? '—'}
            {optimized.signal_quality.is_filter_pct != null
              ? ` · ${optimized.signal_quality.is_filter_pct}% filtered`
              : ''}
          </span>
          <span className="text-zinc-500">|</span>
          <span data-testid="opt-quality-oos">
            OOS avg {optimized.signal_quality.oos_avg_score ?? '—'}
            {optimized.signal_quality.oos_filter_pct != null
              ? ` · ${optimized.signal_quality.oos_filter_pct}% filtered`
              : ''}
          </span>
        </div>
      )}
    </div>
  );
}

function PhaseTelemetrySection({ phase2, phase3, phase4, phase5 }) {
  const hasAny =
    (phase2 && (phase2.regime_filter_enabled != null
      || phase2.is_atr_used != null
      || phase2.is_trailing_used != null))
    || (phase3 && phase3.mtf_filter_enabled != null)
    || (phase4 && phase4.quality_filter_enabled != null)
    || (phase5 && phase5.atr_stops_enabled != null);

  if (!hasAny) return null;

  const mtfOn = phase3?.mtf_filter_enabled === true;
  const regimeOn = phase2?.regime_filter_enabled === true;

  const mtfBlocked = (phase3?.is_mtf_blocked || 0) + (phase3?.oos_mtf_blocked || 0);
  const regimeBlocked = (phase2?.is_regime_blocked || 0) + (phase2?.oos_regime_blocked || 0);
  const atrUsed = (phase2?.is_atr_used || 0) + (phase2?.oos_atr_used || 0);
  const trailingUsed = (phase2?.is_trailing_used || 0) + (phase2?.oos_trailing_used || 0);

  // P2 — Signal Quality (phase4)
  const qOn = phase4?.quality_filter_enabled === true;
  const qThr = phase4?.quality_threshold;
  const qIsAvg = phase4?.is_avg_score;
  const qOosAvg = phase4?.oos_avg_score;
  const qBlockedTotal = (phase4?.is_quality_blocked || 0) + (phase4?.oos_quality_blocked || 0);
  const qFilterPctIs = phase4?.is_quality_filter_pct;
  const qDetail = (() => {
    if (!phase4) return null;
    const avg = qIsAvg != null ? `avg ${qIsAvg}` : null;
    if (qOn) {
      const pct = qFilterPctIs != null ? `${qFilterPctIs}% filtered` : `${qBlockedTotal} blocked`;
      return [avg, `thr ${qThr}`, pct].filter(Boolean).join(' · ');
    }
    return [avg, `OOS ${qOosAvg ?? '—'}`, 'filter off'].join(' · ');
  })();

  return (
    <div
      data-testid="phase-telemetry-section"
      className="mt-3 pt-3 border-t border-zinc-800/60"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-400">
          Engine telemetry
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <TelemetryChip
          testId="chip-mtf"
          label="MTF H1→H4"
          active={mtfOn}
          detail={
            mtfOn
              ? `${mtfBlocked} entries blocked`
              : 'off'
          }
          tone={mtfOn ? (mtfBlocked > 0 ? 'cyan' : 'zinc') : 'muted'}
        />
        <TelemetryChip
          testId="chip-regime"
          label="Regime filter"
          active={regimeOn}
          detail={
            regimeOn
              ? `${regimeBlocked} entries blocked`
              : 'off'
          }
          tone={regimeOn ? (regimeBlocked > 0 ? 'violet' : 'zinc') : 'muted'}
        />
        <TelemetryChip
          testId="chip-atr"
          label="ATR exits"
          active={atrUsed > 0}
          detail={atrUsed > 0 ? `${atrUsed} trades` : 'unused'}
          tone={atrUsed > 0 ? 'amber' : 'muted'}
        />
        <TelemetryChip
          testId="chip-trailing"
          label="Trailing stop"
          active={trailingUsed > 0}
          detail={trailingUsed > 0 ? `${trailingUsed} hits` : 'unused'}
          tone={trailingUsed > 0 ? 'emerald' : 'muted'}
        />
        {phase4 ? (
          <TelemetryChip
            testId="chip-quality"
            label="Signal Quality"
            active={qOn}
            detail={qDetail || 'n/a'}
            tone={qOn ? (qBlockedTotal > 0 ? 'cyan' : 'emerald') : 'muted'}
          />
        ) : null}
        {phase5 ? (() => {
          const atrOn = phase5.atr_stops_enabled === true;
          const ruinHits =
            (phase5.is_ruin_triggered ? 1 : 0) +
            (phase5.oos_ruin_triggered ? 1 : 0);
          const risk = phase5.risk_model || (atrOn ? 'atr' : 'pip');
          const atrK = phase5.atr_k;
          const atrM = phase5.atr_m;
          const atrDetail = atrOn
            ? (atrK != null && atrM != null
                ? `${risk} · SL ${atrK}× · TP ${atrM}×`
                : `${risk} stops`)
            : 'pip stops';
          const ruinDetail = ruinHits > 0
            ? `ruin guard fired (${ruinHits}/2)`
            : 'ruin guard: clean';
          return (
            <>
              <TelemetryChip
                testId="chip-risk-calibration"
                label="Risk calibration"
                active={atrOn}
                detail={atrDetail}
                tone={atrOn ? 'amber' : 'muted'}
              />
              <TelemetryChip
                testId="chip-ruin-floor"
                label="Ruin floor"
                active={ruinHits > 0}
                detail={ruinDetail}
                tone={ruinHits > 0 ? 'red' : 'emerald'}
              />
            </>
          );
        })() : null}
      </div>
    </div>
  );
}

// ── P2 — Quality Threshold Calibration Panel ────────────────────────

function QualityCalibrationPanel({ profile, error, currentThreshold, onDismiss }) {
  if (error) {
    return (
      <div
        data-testid="quality-calibration-panel"
        className="card-premium p-3 border-amber-500/30 bg-amber-950/20"
      >
        <div className="flex items-center justify-between">
          <div className="text-xs font-mono text-amber-300">
            <span className="font-semibold uppercase tracking-wider">Calibration failed</span>
            <span className="ml-2 text-amber-200/80">{error}</span>
          </div>
          <button
            data-testid="quality-calibration-dismiss"
            onClick={onDismiss}
            className="text-[10px] font-mono text-zinc-400 hover:text-zinc-200"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }
  if (!profile) return null;

  const avg = profile.avg_score || {};
  const dist = profile.distribution || {};
  const evaluated = profile.evaluated || {};
  const histogram = profile.histogram || [];
  const maxCount = Math.max(1, ...histogram.map((b) => b.count || 0));
  const rec = profile.recommended_threshold;
  const cur = Number(currentThreshold);

  return (
    <div
      data-testid="quality-calibration-panel"
      className="card-premium p-4 border-cyan-500/30 bg-cyan-950/10"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-cyan-300">
            Quality Threshold Calibration
          </div>
          <div className="text-[11px] font-mono text-zinc-400 mt-0.5">
            {profile.pair} · {profile.timeframe} · {profile.style}
            {' · '}
            <span className="text-zinc-500">
              {evaluated.total} entries evaluated ({evaluated.is} IS / {evaluated.oos} OOS)
            </span>
          </div>
        </div>
        <button
          data-testid="quality-calibration-dismiss"
          onClick={onDismiss}
          className="text-[10px] font-mono text-zinc-400 hover:text-zinc-200"
        >
          Dismiss
        </button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-3">
        <Metric label="Avg (IS)" value={avg.is ?? '—'} color="text-cyan-300" testId="calib-avg-is" />
        <Metric label="Avg (OOS)" value={avg.oos ?? '—'} color="text-cyan-300" testId="calib-avg-oos" />
        <Metric label="Min" value={dist.min ?? '—'} color="text-zinc-300" testId="calib-min" />
        <Metric label="Median" value={dist.p50 ?? '—'} color="text-zinc-300" testId="calib-p50" />
        <Metric label="Max" value={dist.max ?? '—'} color="text-zinc-300" testId="calib-max" />
        <Metric
          label={`Recommended (+${profile.offset_applied ?? 5})`}
          value={rec ?? '—'}
          color="text-emerald-300"
          testId="calib-recommended"
        />
      </div>

      {/* Histogram */}
      {histogram.length > 0 && (
        <div
          data-testid="quality-histogram"
          className="relative flex items-end gap-0.5 h-16 border-t border-b border-zinc-800/60 py-1"
        >
          {histogram.map((b, i) => {
            const h = Math.max(2, Math.round((b.count / maxCount) * 55));
            const midpoint = (b.bucket_start + b.bucket_end) / 2;
            // Highlight bucket the current threshold lives in.
            const isCurrent = cur >= b.bucket_start && cur < b.bucket_end;
            const isRec = rec != null && rec >= b.bucket_start && rec < b.bucket_end;
            const cls = isCurrent
              ? 'bg-cyan-400'
              : isRec
              ? 'bg-emerald-400'
              : b.count > 0
              ? 'bg-zinc-600'
              : 'bg-zinc-800';
            return (
              <div
                key={i}
                title={`${b.bucket_start}–${b.bucket_end}: ${b.count} entries`}
                className="flex-1 relative flex items-end"
              >
                <div
                  className={`w-full ${cls} rounded-t-sm transition-colors`}
                  style={{ height: `${h}px` }}
                />
                <span
                  className="absolute -bottom-4 left-0 right-0 text-center text-[8px] font-mono text-zinc-600"
                >
                  {Math.round(midpoint)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {Array.isArray(profile.notes) && profile.notes.length > 0 && (
        <div className="mt-5 space-y-1">
          {profile.notes.map((n, i) => (
            <div
              key={i}
              data-testid={`calib-note-${i}`}
              className="text-[10px] font-mono text-amber-300/90"
            >
              • {n}
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 text-[10px] font-mono text-zinc-500">
        Threshold now set to{' '}
        <span data-testid="calib-applied-threshold" className="text-cyan-300">{cur}</span>.{' '}
        Override manually any time — the filter uses whatever value is in the input.
      </div>
    </div>
  );
}



function TelemetryChip({ label, detail, active, tone = 'zinc', testId }) {
  const tones = {
    zinc:    'text-zinc-300 border-zinc-700 bg-zinc-900',
    cyan:    'text-cyan-300 border-cyan-500/40 bg-cyan-500/10',
    violet:  'text-violet-300 border-violet-500/40 bg-violet-500/10',
    amber:   'text-amber-300 border-amber-500/40 bg-amber-500/10',
    emerald: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
    red:     'text-red-300 border-red-500/40 bg-red-500/10',
    muted:   'text-zinc-500 border-zinc-800 bg-zinc-950',
  };
  const cls = tones[tone] || tones.zinc;
  return (
    <span
      data-testid={testId}
      title={`${label}: ${detail}`}
      className={`inline-flex items-center gap-1.5 text-[10px] font-mono border rounded px-1.5 py-0.5 ${cls}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-current' : 'bg-current/40'}`}
        style={{ opacity: active ? 1 : 0.35 }}
      />
      <span className="font-semibold tracking-wider uppercase">{label}</span>
      <span className="opacity-70">· {detail}</span>
    </span>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────

export default function StrategyDashboard() {
  const [pair, setPair] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('H1');
  const [style, setStyle] = useState('trend-following');
  const [firm, setFirm] = useState('ftmo');
  const [count, setCount] = useState(5);     // Phase-1 UI: numeric 1-50
  // P2 — optimiser choice. Default stays `random_search` so the
  // existing user experience doesn't change until they explicitly
  // flip the toggle.
  const [optimizer, setOptimizer] = useState('random_search');
  // P2 — Signal Quality Score filter (entry-quality gate). Default OFF.
  // When ON, entries below the score threshold are rejected. The UI
  // still shows `phase4` telemetry whether the filter is on or off.
  const [qualityFilter, setQualityFilter] = useState(false);
  const [qualityThreshold, setQualityThreshold] = useState(60);
  // P2 — Data-driven threshold calibration.
  const [qualityProfile, setQualityProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [detail, setDetail] = useState(null);
  // P4 — Multi-asset portfolio rollout state.
  const [maPairs, setMaPairs] = useState([]);
  const [maLoading, setMaLoading] = useState(false);
  const [maResult, setMaResult] = useState(null);
  const [maError, setMaError] = useState(null);
  // P1 — Multi-asset portfolio persistence state.
  const [savedPortfolios, setSavedPortfolios] = useState([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState(null);
  const [portfolioName, setPortfolioName] = useState('');
  const [saveInFlight, setSaveInFlight] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);
  const [loadedPortfolio, setLoadedPortfolio] = useState(null);
  // Phase 11 — save state per-card: { [strategy_id]: 'idle'|'saving'|'saved'|'duplicate'|'error' }
  const [saveStates, setSaveStates] = useState({});
  const [savingTop, setSavingTop] = useState(false);
  const [saveTopResult, setSaveTopResult] = useState(null);
  // Phase 16 — mutation trigger state per-card + last result for modal
  const [improveStates, setImproveStates] = useState({});       // { [id]: 'loading'|'done'|'error' }
  const [mutationResult, setMutationResult] = useState(null);   // { strategy_id, pair, data, error? }
  // Phase 2 + 3 — dynamic firm list + unified Add/Discover modal
  const [firms, setFirms] = useState(DEFAULT_FIRMS);
  const [showAddFirm, setShowAddFirm] = useState(false);

  // P2 — Dataset availability + Load Data flow, extracted into a
  // shared hook so every surface (dashboard, AutoMutationRunner, …)
  // uses the exact same source of truth + click flow.
  const {
    datasets,
    availablePairs,
    availableTFs,
    currentDataset,
    dataStatus,
    isDataReady,
    downloading,
    downloadResult,
    downloadError,
    loadData: handleLoadData,
    clearDownload,
  } = useDatasetAvailability(pair, setPair, timeframe, setTimeframe);

  const refreshFirms = async () => {
    try {
      const data = await listChallengeFirms();
      const list = Object.entries(data.firms || {}).map(([slug, info]) => ({
        slug, name: info?.name || slug.toUpperCase(),
      }));
      if (list.length) setFirms(list);
    } catch (e) {
      // Keep default list on failure (e.g. preview-proxy 404) — matches existing UX.
      console.warn('Failed to load firms:', e);
    }
  };

  useEffect(() => { refreshFirms(); }, []);

  const handleGenerate = async () => {
    const safeCount = Math.max(1, Math.min(50, Number(count) || 5));
    setLoading(true);
    setError(null);
    setResult(null);
    setSaveStates({});
    setSaveTopResult(null);
    try {
      const data = await generateDashboardStrategies({
        pair, timeframe, style, firm,
        count: safeCount,
        topN: Math.min(safeCount, 10),
        refineTop: Math.min(3, safeCount),
        optimizer,
        qualityFilter,
        qualityThreshold,
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // P4 — Multi-asset portfolio rollout: run generation independently
  // per selected pair, apply the asset gate, and combine survivors.
  const handleRunMultiAsset = async () => {
    if (!maPairs || maPairs.length < 2) {
      setMaError('Select at least 2 pairs for a multi-asset portfolio.');
      return;
    }
    setMaLoading(true);
    setMaError(null);
    setMaResult(null);
    try {
      const data = await generateMultiAssetPortfolio({
        pairs: maPairs,
        timeframe,
        style,
        firm,
        count: 2,
        topNPerPair: 2,
        gateEnabled: true,
        gateThreshold: 1.10,
        // Keep gate fast for UX (3 seeds ≈ 2s/pair vs 5 seeds ≈ 4s)
        gateSeeds: [7, 42, 101],
        gatePopulation: 8,
        gateGenerations: 2,
        qualityFilter,
        qualityThreshold,
      });
      setMaResult(data);
    } catch (e) {
      setMaError(e.message);
    } finally {
      setMaLoading(false);
    }
  };

  // P1 — Persistence handlers.
  const refreshSavedPortfolios = async () => {
    setSavedError(null);
    try {
      const res = await listSavedPortfolios({ limit: 50 });
      setSavedPortfolios(res.items || []);
    } catch (e) {
      setSavedError(e.message);
    }
  };

  useEffect(() => { refreshSavedPortfolios(); }, []);

  const handleSavePortfolio = async () => {
    if (!maResult || !maResult.portfolio) return;
    if (!portfolioName || !portfolioName.trim()) {
      setSaveMessage({ type: 'error', text: 'Please enter a portfolio name first.' });
      return;
    }
    setSaveInFlight(true);
    setSaveMessage(null);
    try {
      const res = await savePortfolio({
        name: portfolioName.trim(),
        portfolioResult: maResult,
        requestEcho: {
          pairs: maPairs,
          timeframe,
          style,
          firm,
          gate_config: {
            threshold: 1.10,
            seeds: [7, 42, 101],
            population: 8,
            generations: 2,
          },
        },
      });
      if (res.success) {
        setSaveMessage({
          type: 'success',
          text: `Saved "${res.name}" · grade ${res.grade} · ${res.num_strategies} strategies.`,
        });
        setPortfolioName('');
        await refreshSavedPortfolios();
      } else {
        setSaveMessage({
          type: 'error',
          text: res.reason || res.error || 'Save rejected.',
        });
      }
    } catch (e) {
      setSaveMessage({ type: 'error', text: e.message });
    } finally {
      setSaveInFlight(false);
    }
  };

  const handleLoadPortfolio = async (portfolioId) => {
    setSavedError(null);
    try {
      const res = await loadSavedPortfolio(portfolioId);
      if (!res.success) {
        setSavedError(res.error || 'Load failed.');
        return;
      }
      const doc = res.portfolio || {};
      // Rebuild a `maResult`-shaped view from the persisted doc so the
      // existing MultiAssetResults renderer can display it without a
      // second network call / re-running the pipeline.
      const byPair = {};
      for (const s of (doc.strategies || [])) {
        const key = s.pair;
        if (!byPair[key]) byPair[key] = { pair: key, timeframe: s.timeframe, passed: true,
                                           gate: { passed: true, median_oos_pf: null, max_oos_dd: null },
                                           top_strategies: [], candles: 0, elapsed_seconds: 0 };
        byPair[key].top_strategies.push({
          strategy_id: s.strategy_id, pair: s.pair, timeframe: s.timeframe,
          style: s.style, strategy_text: s.strategy_text,
          verdict: s.verdict, score: s.score,
          backtest: s.backtest || {}, equity_curve: s.equity_curve,
          phase4: s.phase4, phase5: s.phase5,
        });
      }
      const rebuilt = {
        success: true,
        pairs_requested: doc.pairs || [],
        pairs_passed: doc.pairs_passed || [],
        pairs_rejected: doc.pairs_rejected || [],
        per_pair: Object.values(byPair),
        portfolio: {
          num_strategies: doc.num_strategies,
          combined_metrics: doc.combined_metrics || {},
          avg_correlation: doc.avg_correlation,
          diversification_grade: doc.diversification_grade,
          portfolio_risk_score: doc.portfolio_risk_score,
          asset_contributions_pct: doc.asset_contributions_pct || {},
          warnings: [],
        },
      };
      setMaPairs(doc.pairs || []);
      setMaResult(rebuilt);
      setLoadedPortfolio({
        id: doc.portfolio_id, name: doc.name, created_at: doc.created_at,
      });
      setMaError(null);
      setSaveMessage(null);
    } catch (e) {
      setSavedError(e.message);
    }
  };

  const handleDeletePortfolio = async (portfolioId) => {
    setSavedError(null);
    try {
      const res = await deleteSavedPortfolio(portfolioId);
      if (!res.success) {
        setSavedError(res.error || 'Delete failed.');
        return;
      }
      if (loadedPortfolio && loadedPortfolio.id === portfolioId) {
        setLoadedPortfolio(null);
      }
      await refreshSavedPortfolios();
    } catch (e) {
      setSavedError(e.message);
    }
  };

  // P2 — Recommend a data-driven quality threshold. Runs a calibration
  // backtest at threshold=0 on the current pair/timeframe/style and
  // auto-fills the threshold input with `avg + offset`. The user can
  // always override. Auto-enables the filter toggle so the new
  // threshold is immediately active (previously editable-but-inert).
  const handleRecommendThreshold = async () => {
    setProfileError(null);
    setProfileLoading(true);
    try {
      const data = await fetchQualityProfile({ pair, timeframe, style, offset: 5 });
      setQualityProfile(data);
      if (data?.recommended_threshold != null) {
        setQualityThreshold(Math.round(Number(data.recommended_threshold)));
        // Auto-enable the filter so the recommended threshold is
        // immediately in effect for the next Generate run.
        setQualityFilter(true);
      }
    } catch (e) {
      setProfileError(e.message || String(e));
    } finally {
      setProfileLoading(false);
    }
  };

  const handleSaveOne = async (card) => {    setSaveStates((p) => ({ ...p, [card.strategy_id]: 'saving' }));
    try {
      const res = await saveStrategyToLibrary(card);
      const next = res.status === 'duplicate' ? 'duplicate' : (res.status === 'saved' ? 'saved' : 'error');
      setSaveStates((p) => ({ ...p, [card.strategy_id]: next }));
    } catch (e) {
      setSaveStates((p) => ({ ...p, [card.strategy_id]: 'error' }));
    }
  };

  // Phase 16 — Improve (mutation) handler. Does NOT refresh the dashboard.
  const handleImprove = async (card) => {
    const id = card.strategy_id;
    setImproveStates((p) => ({ ...p, [id]: 'loading' }));
    try {
      const data = await mutateStrategy({
        strategy_text: card.strategy_text,
        pair: card.pair,
        timeframe: card.timeframe,
        max_variants: 10,
      });
      setMutationResult({ strategy_id: id, source: card, data });
      setImproveStates((p) => ({ ...p, [id]: 'done' }));
    } catch (e) {
      setMutationResult({ strategy_id: id, source: card, error: e.message });
      setImproveStates((p) => ({ ...p, [id]: 'error' }));
    }
  };

  const handleSaveTop = async () => {
    if (!result?.top_strategies?.length) return;
    setSavingTop(true);
    setSaveTopResult(null);
    try {
      const res = await autoSaveTopStrategies(result.top_strategies);
      setSaveTopResult(res);
      // mark per-card states based on result
      setSaveStates((prev) => {
        const copy = { ...prev };
        (result.top_strategies || []).forEach((s, idx) => {
          if (res.saved?.includes((res.saved || [])[idx])) copy[s.strategy_id] = 'saved';
          else if (res.duplicates?.length) copy[s.strategy_id] = copy[s.strategy_id] || 'duplicate';
          else copy[s.strategy_id] = copy[s.strategy_id] || 'error';
        });
        return copy;
      });
    } catch (e) {
      setSaveTopResult({ error: e.message });
    } finally {
      setSavingTop(false);
    }
  };

  const selectClass = "bg-surface-sunken border border-border-subtle text-zinc-100 rounded-md px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-accent-primary/40 focus:border-accent-primary/50 focus:outline-none";
  const labelClass = "text-[10px] font-medium text-zinc-500 uppercase tracking-[0.14em] mr-2 font-mono";

  return (
    <div data-testid="strategy-dashboard" className="space-y-5">
      {/* ── Controls ───────────────────────────────────────── */}
      <div className="card-premium p-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center">
              <span className={labelClass}>Pair</span>
              <select data-testid="pair-select" value={pair} onChange={(e) => setPair(e.target.value)} className={selectClass}>
                <PairOptions datasets={datasets} availablePairs={availablePairs} />
              </select>
            </div>
            <div className="flex items-center">
              <span className={labelClass}>TF</span>
              <select data-testid="tf-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className={selectClass}>
                <TimeframeOptions currentDataset={currentDataset} availableTFs={availableTFs} />
              </select>
            </div>
            <div className="flex items-center">
              <span className={labelClass}>Style</span>
              <select data-testid="style-select" value={style} onChange={(e) => setStyle(e.target.value)} className={selectClass}>
                {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex items-center">
              <span className={labelClass}>Firm</span>
              <select data-testid="firm-select" value={firm} onChange={(e) => setFirm(e.target.value)} className={selectClass}>
                {firms.map((f) => <option key={f.slug} value={f.slug}>{f.name}</option>)}
              </select>
              <button
                data-testid="add-firm-btn"
                onClick={() => setShowAddFirm(true)}
                title="Add new prop firm (single config or multi-plan discovery)"
                className="ml-1.5 inline-flex items-center gap-1 px-2 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-800 hover:border-zinc-700 rounded-md transition-colors"
              >
                <Plus size={11} weight="bold" /> Add Firm
              </button>
            </div>
            <div className="flex items-center">
              <span className={labelClass}>Count</span>
              <input
                data-testid="count-input"
                type="number"
                min={1}
                max={50}
                step={1}
                value={count}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (Number.isNaN(v)) return setCount('');
                  setCount(Math.max(1, Math.min(50, v)));
                }}
                className={`${selectClass} w-20 text-center`}
              />
            </div>
            <div className="flex items-center">
              <span className={labelClass}>Optimizer</span>
              <select
                data-testid="optimizer-select"
                value={optimizer}
                onChange={(e) => setOptimizer(e.target.value)}
                className={selectClass}
                title="Pick the parameter-optimiser applied to the top-2 strategies post-ranking"
              >
                <option value="random_search">Random Search</option>
                <option value="ga">Genetic Algorithm</option>
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <label
                className={`${labelClass} flex items-center gap-1.5 cursor-pointer`}
                title="Reject entries below the quality threshold (0-100). Higher = stricter."
              >
                <input
                  data-testid="quality-filter-toggle"
                  type="checkbox"
                  checked={qualityFilter}
                  onChange={(e) => setQualityFilter(e.target.checked)}
                  className="accent-cyan-400 w-3 h-3"
                />
                Quality Filter
              </label>
              <input
                data-testid="quality-threshold-input"
                type="number"
                min={0}
                max={100}
                step={5}
                value={qualityThreshold}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (Number.isNaN(v)) return;
                  setQualityThreshold(Math.max(0, Math.min(100, v)));
                }}
                disabled={!qualityFilter}
                title="Score threshold (0-100). Entries scoring below this value are rejected."
                className={`${selectClass} w-16 text-center disabled:opacity-40`}
              />
              <button
                data-testid="recommend-threshold-btn"
                type="button"
                onClick={handleRecommendThreshold}
                disabled={profileLoading}
                title="Run a calibration backtest and recommend a data-driven threshold"
                className="ml-1 inline-flex items-center gap-1 px-2 py-1.5 text-[10px] font-mono uppercase tracking-wider bg-cyan-900/40 hover:bg-cyan-800/50 text-cyan-200 border border-cyan-700/60 hover:border-cyan-500 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {profileLoading ? 'Calibrating…' : 'Recommend'}
              </button>
            </div>
          </div>
          <button
            data-testid="generate-dashboard-btn"
            onClick={handleGenerate}
            disabled={loading || !isDataReady}
            title={!isDataReady ? `Cannot generate — ${dataStatus.label}` : 'Run the generate → backtest → validate → rank pipeline'}
            className="btn-primary btn-primary-lg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <><CircleNotch size={14} weight="bold" className="animate-spin" /> Running pipeline…</>
            ) : (
              <><Lightning size={14} weight="fill" /> Generate Strategies</>
            )}
          </button>
        </div>

        {/* P2 — Shared availability banner (same component as
            AutoMutationRunner so the UX is byte-for-byte identical). */}
        <DataAvailabilityBanner
          pair={pair}
          timeframe={timeframe}
          dataStatus={dataStatus}
          currentDataset={currentDataset}
          downloading={downloading}
          onLoadData={handleLoadData}
          className="mt-3"
        />

        {/* P2 — Shared Load Data status banner. */}
        <DataLoadStatus
          result={downloadResult}
          error={downloadError}
          pair={pair}
          timeframe={timeframe}
          onDismiss={clearDownload}
        />
      </div>

      {/* ── P4 — Multi-Asset Portfolio Rollout ─────────────── */}
      <MultiAssetPanel
        datasets={datasets}
        availablePairs={availablePairs}
        maPairs={maPairs}
        setMaPairs={setMaPairs}
        timeframe={timeframe}
        loading={maLoading}
        error={maError}
        result={maResult}
        onRun={handleRunMultiAsset}
        portfolioName={portfolioName}
        setPortfolioName={setPortfolioName}
        onSave={handleSavePortfolio}
        saveInFlight={saveInFlight}
        saveMessage={saveMessage}
        loadedPortfolio={loadedPortfolio}
        onClearLoaded={() => setLoadedPortfolio(null)}
      />

      {/* ── P1 — Saved Portfolios list ────────────────────── */}
      <SavedPortfoliosPanel
        items={savedPortfolios}
        loading={savedLoading}
        error={savedError}
        onRefresh={async () => {
          setSavedLoading(true);
          try { await refreshSavedPortfolios(); } finally { setSavedLoading(false); }
        }}
        onLoad={handleLoadPortfolio}
        onDelete={handleDeletePortfolio}
      />

      {/* ── Error ───────────────────────────────────────────── */}
      {error && (
        <div data-testid="dashboard-error" className="bg-red-950/40 border border-red-900/60 rounded-lg p-3">
          <p className="text-xs font-mono text-red-400">{error}</p>
        </div>
      )}

      {/* ── P2 — Quality Threshold Calibration panel ────────── */}
      {(qualityProfile || profileError) && (
        <QualityCalibrationPanel
          profile={qualityProfile}
          error={profileError}
          currentThreshold={qualityThreshold}
          onDismiss={() => { setQualityProfile(null); setProfileError(null); }}
        />
      )}

      {/* ── Summary ─────────────────────────────────────────── */}
      {result && (
        <div className="flex items-center gap-3 flex-wrap">
          <div data-testid="dashboard-summary" className="grid grid-cols-2 md:grid-cols-5 gap-3 flex-1 min-w-[480px]">
            <SummaryCell label="Firm" value={result.firm} />
            <SummaryCell label="Candles" value={result.candles} />
            <SummaryCell label="Candidates" value={result.total_candidates} />
            <SummaryCell label="Refined" value={result.refined_count} color="text-cyan-400" />
            <SummaryCell
              label="Verdicts"
              value={`${result.verdict_counts?.TRADE || 0}/${result.verdict_counts?.RISKY || 0}/${result.verdict_counts?.REJECT || 0}`}
            />
          </div>
          {result.top_strategies?.length > 0 && (
            <button
              data-testid="save-top-btn"
              onClick={handleSaveTop}
              disabled={savingTop}
              className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-wait px-3 py-2 rounded transition-colors"
            >
              {savingTop ? (
                <><CircleNotch size={12} weight="bold" className="animate-spin" /> Saving top…</>
              ) : (
                <><BookmarkSimple size={12} weight="fill" /> Save Top to Library</>
              )}
            </button>
          )}
        </div>
      )}

      {saveTopResult && !saveTopResult.error && (
        <div
          data-testid="save-top-result"
          className="text-[11px] font-mono text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded p-2"
        >
          Saved <span className="text-emerald-400">{saveTopResult.counts?.saved || 0}</span>
          {' · '}Duplicates <span className="text-cyan-400">{saveTopResult.counts?.duplicates || 0}</span>
          {' · '}Rejected <span className="text-zinc-500">{saveTopResult.counts?.rejected || 0}</span>
        </div>
      )}

      {/* ── Phase 3 — Portfolio panel (combined PF/DD/grade/allocations) ── */}
      {result?.portfolio && result.top_strategies?.length >= 2 && (
        <PortfolioPanel
          portfolio={result.portfolio}
          topStrategies={result.top_strategies}
        />
      )}

      {/* ── Top 5 cards ─────────────────────────────────────── */}
      {result?.top_strategies?.length > 0 && (
        <div data-testid="top-strategies" className="space-y-3">
          {result.top_strategies.map((s) => (
            <StrategyCard
              key={s.strategy_id}
              s={s}
              onDeepDive={setDetail}
              onSave={handleSaveOne}
              onImprove={handleImprove}
              saveState={saveStates[s.strategy_id]}
              improveState={improveStates[s.strategy_id]}
            />
          ))}
        </div>
      )}

      {/* ── Phase 4 — Best Firm Match for the top strategy ──── */}
      {result?.top_strategies?.length > 0 && (
        <div
          data-testid="dashboard-firm-match"
          className="card-premium p-4"
        >
          <FirmMatchPanel
            variant="full"
            strategyText={result.top_strategies[0].strategy_text}
            pair={result.top_strategies[0].pair || result.pair}
            timeframe={result.top_strategies[0].timeframe || result.timeframe}
          />
        </div>
      )}

      {/* ── Empty state — post-run, nothing survived ────────── */}
      {result && (!result.top_strategies || result.top_strategies.length === 0) && (
        <div data-testid="dashboard-empty" className="empty-state">
          <div className="empty-state-icon"><ChartLineDown size={22} weight="bold" /></div>
          <div className="empty-state-title">No strategies survived the pipeline</div>
          <p className="empty-state-sub">
            Every candidate was filtered by validation or the prop-firm panel.
            Try a different pair, timeframe, or style — or raise the count.
          </p>
          <button
            data-testid="dashboard-empty-retry"
            onClick={handleGenerate}
            disabled={loading}
            className="btn-primary mt-1"
          >
            <Lightning size={13} weight="fill" /> Retry with current filters
          </button>
        </div>
      )}

      {/* ── Empty state — pre-run (first visit) ─────────────── */}
      {!result && !loading && !error && (
        <div data-testid="dashboard-idle" className="empty-state">
          <div className="empty-state-icon"><Lightning size={22} weight="fill" /></div>
          <div className="empty-state-title">Ready to generate strategies</div>
          <p className="empty-state-sub">
            Pick a pair, timeframe and style above, then hit <span className="text-accent-primary">Generate Strategies</span> to
            run the full backtest · validation · prop-firm readiness pipeline.
          </p>
        </div>
      )}

      {/* ── Deep-Dive drawer ────────────────────────────────── */}
      {detail && (
        <DeepDiveDrawer strategy={detail} onClose={() => setDetail(null)} />
      )}

      {/* ── Phase 16 — Mutation result modal ─────────────────── */}
      {mutationResult && (
        <MutationResultModal
          payload={mutationResult}
          onClose={() => setMutationResult(null)}
        />
      )}

      {/* ── Phase 14.4 — Pipeline Logs (live tail) ─────────── */}
      <PipelineLogsPanel runId={result?.run_id || null} />

      {/* ── Unified Add Firm modal (Phase 2 + Phase 3) ─────── */}
      <AddFirmModal
        open={showAddFirm}
        onClose={() => setShowAddFirm(false)}
        onSaved={async (result) => {
          await refreshFirms();
          if (result?.kind === 'rules' && result.config?.firm_slug) {
            setFirm(result.config.firm_slug);
          } else if (result?.kind === 'plans') {
            const firstPlan = result.result?.mirrored_plan_slugs?.[0];
            if (firstPlan) setFirm(firstPlan);
          }
        }}
      />
    </div>
  );
}

function SummaryCell({ label, value, color = 'text-white' }) {
  return (
    <div className="bg-surface-card border border-zinc-800 rounded-md p-2.5">
      <p className="text-[9px] text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className={`text-sm font-mono font-bold ${color}`}>{value ?? '—'}</p>
    </div>
  );
}

function DeepDiveDrawer({ strategy, onClose }) {
  return (
    <div
      data-testid="deep-dive-drawer"
      className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-card border border-zinc-800 rounded-lg max-w-2xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-surface-card border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-white">
              #{strategy.rank} — {strategy.pair} · {strategy.timeframe}
            </span>
            <VerdictBadge verdict={strategy.verdict} />
            <StatusBadge status={strategy.status} />
          </div>
          <button
            data-testid="deep-dive-close"
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-xs font-mono uppercase"
          >
            Close
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Scores */}
          <section>
            <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">Scores</h4>
            <div className="grid grid-cols-4 gap-3">
              <Metric label="Score" value={strategy.score?.toFixed(1)} />
              <Metric label="Pass Prob" value={strategy.pass_probability != null ? `${Math.round(strategy.pass_probability)}%` : '—'} color="text-emerald-400" />
              <Metric label="Confidence" value={strategy.confidence} />
              <Metric label="Consistency" value={strategy.consistency_score} />
            </div>
          </section>

          {/* Backtest */}
          <section>
            <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">Backtest</h4>
            <div className="grid grid-cols-4 gap-3">
              <Metric label="Return" value={strategy.backtest?.total_return_pct != null ? `${strategy.backtest.total_return_pct}%` : '—'}
                      color={strategy.backtest?.total_return_pct > 0 ? 'text-emerald-400' : 'text-red-400'} />
              <Metric label="Win Rate" value={strategy.backtest?.win_rate != null ? `${strategy.backtest.win_rate}%` : '—'} />
              <Metric label="PF" value={strategy.backtest?.profit_factor ?? '—'} />
              <Metric label="Trades" value={strategy.backtest?.total_trades ?? '—'} />
            </div>
          </section>

          {/* Risk */}
          <section>
            <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">Risk</h4>
            <div className="grid grid-cols-4 gap-3">
              <Metric label="Max DD" value={strategy.max_drawdown != null ? `${strategy.max_drawdown}%` : '—'} color="text-red-300" />
              <Metric label="Daily DD" value={strategy.daily_drawdown != null ? `${strategy.daily_drawdown}%` : '—'} color="text-amber-300" />
              <Metric label="Daily Viol." value={strategy.violations?.daily_dd ?? 0} />
              <Metric label="Total Viol." value={strategy.violations?.max_dd ?? 0} />
            </div>
          </section>

          {/* Reason */}
          <section>
            <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">Recommendation</h4>
            <p className="text-xs text-zinc-300 leading-relaxed">{strategy.recommendation || '—'}</p>
            {strategy.reason && (
              <p className="text-[11px] text-zinc-500 mt-1 font-mono">{strategy.reason}</p>
            )}
          </section>

          {/* Phase 4 — Firm Match (compact) */}
          <section data-testid="dashboard-firm-match-section">
            <FirmMatchPanel
              variant="compact"
              strategyText={strategy.strategy_text}
              pair={strategy.pair}
              timeframe={strategy.timeframe}
            />
          </section>

          {/* Strategy text */}
          {strategy.strategy_text && (
            <section>
              <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">Strategy</h4>
              <pre
                data-testid="deep-dive-strategy-text"
                className="text-[11px] text-zinc-300 bg-zinc-950 border border-zinc-800 rounded p-3 whitespace-pre-wrap font-mono max-h-60 overflow-y-auto"
              >
                {strategy.strategy_text}
              </pre>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Phase 16 — Mutation Result Modal ────────────────────────────────
function MutationResultModal({ payload, onClose }) {
  const { source, data, error } = payload || {};
  const src = source || {};
  const best = data?.best_variant || {};
  const bt = best.backtest || {};
  const evo = data?.evolution || {};
  const autoSave = data?.auto_save_result || null;
  const totals = data?.totals || {};
  const variants = data?.variants || [];

  const pfColor = bt.profit_factor == null
    ? 'text-zinc-300'
    : (bt.profit_factor > 1.2 ? 'text-emerald-400' : bt.profit_factor >= 1.0 ? 'text-amber-400' : 'text-red-400');
  const ddColor = bt.max_drawdown_pct == null
    ? 'text-zinc-300'
    : (bt.max_drawdown_pct < 20 ? 'text-emerald-400' : bt.max_drawdown_pct <= 30 ? 'text-amber-400' : 'text-red-400');
  const retColor = bt.total_return_pct == null
    ? 'text-zinc-300'
    : (bt.total_return_pct > 0 ? 'text-emerald-400' : 'text-red-400');

  return (
    <div
      data-testid="mutation-result-modal"
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-card border border-violet-500/30 rounded-lg max-w-3xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-surface-card border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Flask size={16} weight="bold" className="text-violet-400" />
            <span className="text-sm font-semibold text-white">
              Mutation Result — {src.pair} · {src.timeframe}
            </span>
          </div>
          <button
            data-testid="mutation-modal-close"
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-xs font-mono uppercase"
          >
            Close
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div
              data-testid="mutation-modal-error"
              className="bg-red-950/40 border border-red-900/60 rounded p-3 text-xs font-mono text-red-400"
            >
              {error}
            </div>
          )}

          {!error && data?.status === 'data_missing' && (
            <div className="bg-amber-950/40 border border-amber-900/60 rounded p-3 text-xs font-mono text-amber-300">
              {data.message || 'Not enough market data. Download via Market Data tab first.'}
            </div>
          )}

          {!error && data?.status === 'ok' && (
            <>
              {/* Summary */}
              <section
                data-testid="mutation-summary"
                className="grid grid-cols-4 gap-3"
              >
                <Metric label="Variants" value={totals.variants_generated ?? variants.length} />
                <Metric label="Backtested" value={totals.variants_backtested ?? variants.length} />
                <Metric label="Errors" value={totals.errors ?? 0} />
                <Metric label="Runtime" value={data.runtime_sec != null ? `${data.runtime_sec}s` : '—'} />
              </section>

              {/* Best variant metrics */}
              <section data-testid="mutation-best-variant">
                <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
                  Best Variant · <span className="text-violet-300">{best.mutation_type || '—'}</span>
                </h4>
                <div className="grid grid-cols-5 gap-3">
                  <Metric label="PF"        value={bt.profit_factor ?? '—'} color={pfColor} />
                  <Metric label="Max DD"    value={bt.max_drawdown_pct != null ? `${bt.max_drawdown_pct}%` : '—'} color={ddColor} />
                  <Metric label="Trades"    value={bt.total_trades ?? '—'} />
                  <Metric label="Win Rate"  value={bt.win_rate != null ? `${bt.win_rate}%` : '—'} />
                  <Metric label="Net Return" value={bt.total_return_pct != null ? `${bt.total_return_pct}%` : '—'} color={retColor} />
                </div>
              </section>

              {/* Description of the best variant (async, non-blocking) */}
              {best.strategy_text && (
                <StrategyDescription
                  variant="inline"
                  strategy_text={best.strategy_text}
                  pair={src.pair}
                  timeframe={src.timeframe}
                  backtest={bt}
                />
              )}

              {/* Auto-save */}
              <section data-testid="mutation-auto-save">
                <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
                  Auto-Save
                </h4>
                {autoSave ? (
                  <AutoSaveBlock res={autoSave} />
                ) : (
                  <p className="text-[11px] font-mono text-zinc-500">
                    Not requested (auto_save=false). Mutation produced variants only — none were passed through the save pipeline.
                  </p>
                )}
              </section>

              {/* Evolution */}
              <section data-testid="mutation-evolution">
                <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
                  Evolution · Regime
                </h4>
                <div className="grid grid-cols-3 gap-3 mb-2">
                  <Metric
                    label="Evolution applied"
                    value={evo.applied ? 'yes' : 'no'}
                    color={evo.applied ? 'text-emerald-400' : 'text-zinc-400'}
                  />
                  <Metric
                    label="Regime"
                    value={evo.regime_type || '—'}
                    color="text-cyan-300"
                  />
                  <Metric
                    label="Regime weights"
                    value={evo.regime_weights_used ? `used (${evo.regime_weights_used})` : 'global / legacy'}
                    color={evo.regime_weights_used ? 'text-violet-300' : 'text-zinc-400'}
                  />
                </div>
                {Array.isArray(evo.selected_types) && evo.selected_types.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {evo.selected_types.map((t, i) => (
                      <span
                        key={i}
                        className="text-[10px] font-mono px-2 py-0.5 rounded border border-violet-500/30 bg-violet-500/10 text-violet-300"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </section>

              {/* All variants mini-table */}
              {variants.length > 0 && (
                <section data-testid="mutation-variants-table">
                  <h4 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
                    All Variants (ranked)
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[11px] font-mono">
                      <thead>
                        <tr className="text-zinc-500 border-b border-zinc-800">
                          <th className="text-left pb-1.5 pr-2">Type</th>
                          <th className="text-right pb-1.5 px-2">PF</th>
                          <th className="text-right pb-1.5 px-2">DD %</th>
                          <th className="text-right pb-1.5 px-2">Trades</th>
                          <th className="text-right pb-1.5 px-2">WR %</th>
                          <th className="text-right pb-1.5 pl-2">Return %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {variants.map((v, idx) => {
                          const m = v.backtest || {};
                          return (
                            <tr key={idx} className="border-b border-zinc-900 text-zinc-300">
                              <td className="py-1 pr-2 text-violet-300">{v.mutation_type}</td>
                              <td className="py-1 px-2 text-right">{m.profit_factor ?? '—'}</td>
                              <td className="py-1 px-2 text-right">{m.max_drawdown_pct ?? '—'}</td>
                              <td className="py-1 px-2 text-right">{m.total_trades ?? '—'}</td>
                              <td className="py-1 px-2 text-right">{m.win_rate ?? '—'}</td>
                              <td className="py-1 pl-2 text-right">{m.total_return_pct ?? '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function AutoSaveBlock({ res }) {
  const status = res?.status;
  const map = {
    saved:     { c: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300', label: 'SAVED' },
    duplicate: { c: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300',         label: 'DUPLICATE' },
    rejected:  { c: 'border-amber-500/40 bg-amber-500/10 text-amber-300',      label: 'REJECTED' },
    skipped:   { c: 'border-zinc-700 bg-zinc-900 text-zinc-400',               label: 'SKIPPED' },
    error:     { c: 'border-red-500/40 bg-red-500/10 text-red-300',            label: 'ERROR' },
  };
  const m = map[status] || { c: 'border-zinc-700 bg-zinc-900 text-zinc-400', label: (status || '—').toUpperCase() };
  return (
    <div data-testid={`auto-save-${status || 'unknown'}`} className={`border ${m.c} rounded p-3 text-[11px] font-mono space-y-1`}>
      <div className="flex items-center gap-2">
        <span className="font-bold">{m.label}</span>
        {res?.mutation_type && <span className="opacity-70">· {res.mutation_type}</span>}
      </div>
      {res?.reason && <div className="opacity-80">{res.reason}</div>}
      {res?.strategy_id && <div className="opacity-60">strategy_id: {res.strategy_id}</div>}
      {(res?.score != null || res?.verdict) && (
        <div className="opacity-70">
          {res?.score != null && <>score {res.score} · </>}
          {res?.verdict && <>verdict {res.verdict} · </>}
          {res?.prop_status && <>panel {res.prop_status}</>}
        </div>
      )}
    </div>
  );
}
