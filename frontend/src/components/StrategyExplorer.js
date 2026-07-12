import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Compass, ArrowsClockwise, ChartLine, Star, Download,
  MagnifyingGlass, X, FileCode, FileJs, Spinner, ArrowRight,
  Globe, Target, Lightning, Shield, ShieldCheck, Warning, CheckCircle, XCircle,
  Trophy, Crosshair, MagnifyingGlassPlus, CaretUp, CaretDown,
} from '@phosphor-icons/react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import {
  getExplorer,
  getStrategyHistory,
  reRunStrategyByHash,
  exportStrategyByHash,
  downloadStrategyCbotByHash,
  toggleStrategyFavorite,
  scanStrategyMarket,
  scanMarketEligible,
  getMarketIntelligenceRankings,
  analyzeStrategyProp,
  getStrategyPropAnalysis,
  batchAnalyzeProp,
  matchStrategyChallenges,
  getStrategyChallengeMatch,
  runEligibleChallengeMatch,
  listPropFirmReviewRules,
} from '../services/api';
import StrategyDetailsPanel, { StageBadge, ValidationBadges } from './StrategyDetailsPanel';
import { AsfEmptyState } from './ui-asf';

const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'ingestion', label: 'Ingestion' },
  { value: 'mutation_runner', label: 'Auto Mutation' },
  { value: 'manual_rerun', label: 'Manual Re-run' },
  { value: 'dashboard', label: 'Dashboard' },
];

// Phase 24 — sort resolvers for the new columns.
const SORT_RESOLVERS = {
  best_pf:          (r) => r.best_pf,
  pass_probability: (r) => r.validation?.metrics?.pass_probability_pct,
  win_rate:         (r) => r.validation?.metrics?.win_rate,
  oos_ratio:        (r) => r.validation?.metrics?.oos_ratio,
  stability:        (r) => r.validation?.metrics?.stability_score,
  max_dd:           (r) => r.validation?.metrics?.max_drawdown_pct,
  total_trades:     (r) => r.validation?.metrics?.total_trades,
  runs:             (r) => r.runs,
};

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (typeof n !== 'number') return String(n);
  return n.toFixed(digits);
}

function pfColor(pf) {
  if (pf === null || pf === undefined) return 'text-zinc-500';
  if (pf >= 1.5) return 'text-emerald-400';
  if (pf >= 1.2) return 'text-yellow-400';
  if (pf >= 1.0) return 'text-orange-400';
  return 'text-red-400';
}

function oosRatioColor(r) {
  if (r === null || r === undefined) return 'text-zinc-500';
  if (r >= 1.0) return 'text-emerald-400';
  if (r >= 0.7) return 'text-amber-300';
  return 'text-red-400';
}

function ddColor(d) {
  // d is fraction 0..1
  if (d === null || d === undefined) return 'text-zinc-500';
  if (d < 0.05) return 'text-emerald-400';
  if (d < 0.10) return 'text-amber-300';
  return 'text-red-400';
}

function winRateColor(wr) {
  // wr is 0..100 percentage. Visual gradient — neither high nor low is
  // "better" on its own; we just give a calm gradient for at-a-glance scan.
  if (wr === null || wr === undefined) return 'text-zinc-500';
  if (wr >= 60) return 'text-emerald-400';
  if (wr >= 45) return 'text-zinc-200';
  return 'text-amber-300';
}

function SortableHeader({ children, colKey, sortKey, sortDir, onClick, align = 'left', testId }) {
  const active = colKey === sortKey;
  const arrow = !active ? null : sortDir === 'asc'
    ? <CaretUp size={9} weight="bold" className="inline ml-0.5" />
    : <CaretDown size={9} weight="bold" className="inline ml-0.5" />;
  return (
    <th
      className={`text-${align} px-3 py-2.5 cursor-pointer select-none hover:text-zinc-200 ${active ? 'text-zinc-200' : ''}`}
      data-testid={testId}
      onClick={() => onClick(colKey)}
      title={`Sort by ${colKey}`}
    >
      {children}
      {arrow}
    </th>
  );
}

function StabilityBar({ score }) {
  const s = typeof score === 'number' ? Math.max(0, Math.min(1, score)) : 0;
  const pct = Math.round(s * 100);
  const bar =
    s >= 0.8 ? 'bg-emerald-400' : s >= 0.6 ? 'bg-yellow-400' : s >= 0.4 ? 'bg-orange-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2" data-testid="stability-bar">
      <div className="w-14 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={`h-full ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-mono text-zinc-400 tabular-nums">{fmt(s, 2)}</span>
    </div>
  );
}

function SourcePill({ src }) {
  const base =
    'text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-wider whitespace-nowrap';
  if (!src) return <span className={`${base} bg-zinc-900 border-zinc-800 text-zinc-500`}>—</span>;
  if (src.startsWith('ingestion'))
    return <span className={`${base} bg-sky-500/10 border-sky-500/30 text-sky-300`}>{src.replace('ingestion:', 'ing:')}</span>;
  if (src === 'mutation_runner')
    return <span className={`${base} bg-emerald-500/10 border-emerald-500/30 text-emerald-300`}>mutation</span>;
  if (src === 'manual_rerun')
    return <span className={`${base} bg-violet-500/10 border-violet-500/30 text-violet-300`}>rerun</span>;
  return <span className={`${base} bg-zinc-800 border-zinc-700 text-zinc-300`}>{src}</span>;
}

function BestEnvironmentCell({ env }) {
  if (!env) {
    return (
      <span className="text-[10px] font-mono text-zinc-600 italic" data-testid="env-none">
        not scanned
      </span>
    );
  }
  const pf = env.pf;
  const conf = env.confidence;
  const pfClass = pfColor(pf);
  return (
    <div className="flex flex-col gap-0.5" data-testid="env-cell">
      <div className="flex items-center gap-1.5">
        <Globe size={11} className="text-accent-primary" />
        <span className="font-mono text-xs text-zinc-200">
          {env.pair} · {env.timeframe}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[9px] font-mono text-zinc-500">
        <span>
          PF <span className={pfClass}>{fmt(pf)}</span>
        </span>
        <span>DD {fmt(env.dd_pct, 1)}%</span>
        <span className="text-accent-primary">conf {fmt(conf, 2)}</span>
      </div>
    </div>
  );
}

function PropStatusPill({ status }) {
  if (!status) {
    return (
      <span className="text-[9px] font-mono text-zinc-600 italic" data-testid="prop-status-none">
        not analyzed
      </span>
    );
  }
  const cfg = {
    PASS: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/40', text: 'text-emerald-300', Icon: CheckCircle },
    RISKY: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/40', text: 'text-yellow-300', Icon: Warning },
    FAIL: { bg: 'bg-red-500/10', border: 'border-red-500/40', text: 'text-red-300', Icon: XCircle },
  };
  const c = cfg[status] || cfg.FAIL;
  const Icon = c.Icon;
  return (
    <span
      data-testid={`prop-status-${status.toLowerCase()}`}
      className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${c.bg} ${c.border} ${c.text}`}
    >
      <Icon size={10} weight="bold" />
      {status}
    </span>
  );
}

function PassProbBar({ pct, riskLevel }) {
  if (pct === null || pct === undefined) {
    return <span className="text-[9px] font-mono text-zinc-600 italic">—</span>;
  }
  const p = Math.max(0, Math.min(100, Number(pct)));
  const bar =
    p >= 70 ? 'bg-emerald-400' : p >= 40 ? 'bg-yellow-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2" data-testid="prop-pass-prob">
      <div className="w-14 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={`h-full ${bar}`} style={{ width: `${p}%` }} />
      </div>
      <span className="text-[10px] font-mono text-zinc-300 tabular-nums">{p.toFixed(1)}%</span>
    </div>
  );
}

function SafeRiskCell({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-[9px] font-mono text-zinc-600 italic">—</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-mono" data-testid="prop-safe-risk">
      <Shield size={10} className="text-accent-primary" />
      <span className="tabular-nums text-zinc-200">{Number(value).toFixed(2)}%</span>
    </span>
  );
}

function ChallengeMatchCell({ match }) {
  if (!match || !match.best_firm) {
    return (
      <span className="text-[9px] font-mono text-zinc-600 italic" data-testid="match-none">
        not matched
      </span>
    );
  }
  return (
    <div className="flex flex-col gap-0.5" data-testid="match-cell">
      <div className="flex items-center gap-1.5">
        <Trophy size={11} className="text-yellow-400" />
        <span className="font-mono text-xs text-zinc-200">
          {(match.best_firm_name || match.best_firm || '').toString()}
        </span>
      </div>
      <span className="text-[9px] font-mono text-zinc-500">
        {match.best_challenge}
      </span>
    </div>
  );
}

function MatchScoreCell({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-[9px] font-mono text-zinc-600 italic">—</span>;
  }
  const v = Number(value);
  const cls =
    v >= 0.8 ? 'text-emerald-300' : v >= 0.3 ? 'text-yellow-300' :
    v >= 0 ? 'text-zinc-300' : 'text-red-400';
  return (
    <span className={`font-mono text-xs font-bold tabular-nums ${cls}`} data-testid="match-score">
      {v.toFixed(2)}
    </span>
  );
}

// ── History side-panel ────────────────────────────────────────────────

function ChallengeMatchSection({ strategyHash }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getStrategyChallengeMatch(strategyHash);
      setData(d);
    } catch (e) {
      setError(e.message || 'Failed');
    } finally {
      setLoading(false);
    }
  }, [strategyHash]);
  useEffect(() => { load(); }, [load]);

  const runMatch = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await matchStrategyChallenges(strategyHash, true);
      await load();
    } catch (e) {
      setError(e.message || 'Match failed');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="rounded-md border border-zinc-800 bg-[#121821] p-4" data-testid="challenge-match-section">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 flex items-center gap-2">
          <Trophy size={12} className="text-yellow-400" /> Challenge Match
        </p>
        <button
          data-testid="match-run-btn"
          onClick={runMatch}
          disabled={refreshing}
          className="text-[10px] font-medium px-2 py-1 rounded border border-yellow-500/40 bg-yellow-500/10 text-yellow-300 hover:bg-yellow-500/20 disabled:opacity-50 flex items-center gap-1"
        >
          {refreshing ? <Spinner size={10} className="animate-spin" /> : <ArrowsClockwise size={10} />}
          {data ? 'Re-match' : 'Match'}
        </button>
      </div>

      {loading && (
        <p className="text-xs font-mono text-zinc-500 py-3 text-center">
          <Spinner size={12} className="animate-spin inline mr-2" /> Loading…
        </p>
      )}
      {error && <p className="text-xs font-mono text-red-400 py-2">{error}</p>}
      {!loading && !data && !error && (
        <p className="text-xs font-mono text-zinc-500 py-3">
          No match yet — click <strong>Match</strong> to evaluate all firms × challenges.
        </p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2 col-span-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Best Match</p>
              <p className="font-mono text-sm text-zinc-100 mt-0.5 flex items-center gap-1.5">
                <Trophy size={12} className="text-yellow-400" />
                {data.best_firm_name || data.best_firm} · <span className="text-accent-primary">{data.best_challenge}</span>
              </p>
              <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                evaluated {data.evaluated_count} combos
              </p>
            </div>
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Pass Probability</p>
              <p className="text-lg font-bold text-zinc-100 tabular-nums mt-0.5">
                {fmt(data.pass_probability, 1)}%
              </p>
            </div>
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Match Score</p>
              <MatchScoreCell value={data.score} />
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 text-[10px] font-mono text-zinc-400">
            <div>Verdict: <PropStatusPill status={data.status} /></div>
            <div>Expected Days: <span className="text-zinc-200">{data.expected_days ?? '—'}</span></div>
            <div>Risk Level: <span className="text-zinc-200">{data.risk_level || '—'}</span></div>
            <div>Safe Risk: <span className="text-accent-primary">{fmt(data.safe_risk, 2)}%</span></div>
          </div>

          {data.alternatives && data.alternatives.length > 0 && (
            <div data-testid="match-alternatives">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1.5">
                Alternatives
              </p>
              <div className="rounded border border-zinc-800 overflow-hidden">
                <table className="w-full text-[11px]">
                  <thead className="bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                    <tr>
                      <th className="text-left px-2 py-1.5">Firm</th>
                      <th className="text-left px-2 py-1.5">Challenge</th>
                      <th className="text-right px-2 py-1.5">Pass%</th>
                      <th className="text-right px-2 py-1.5">Days</th>
                      <th className="text-right px-2 py-1.5">Score</th>
                      <th className="text-left px-2 py-1.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {data.alternatives.map((a, i) => (
                      <tr key={`${a.firm}-${a.challenge}-${i}`}>
                        <td className="px-2 py-1 font-mono text-zinc-300">{a.firm_name || a.firm}</td>
                        <td className="px-2 py-1 font-mono text-zinc-400">{a.challenge}</td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums text-zinc-200">
                          {fmt(a.pass_probability, 1)}%
                        </td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums text-zinc-400">
                          {a.expected_days ?? '—'}
                        </td>
                        <td className="px-2 py-1 text-right"><MatchScoreCell value={a.score} /></td>
                        <td className="px-2 py-1"><PropStatusPill status={a.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PropFirmAnalysisSection({ strategyHash }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getStrategyPropAnalysis(strategyHash, 'ftmo');
      setData(d);
    } catch (e) {
      setError(e.message || 'Failed to load analysis');
    } finally {
      setLoading(false);
    }
  }, [strategyHash]);

  useEffect(() => { load(); }, [load]);

  const runAnalysis = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await analyzeStrategyProp(strategyHash, 'ftmo');
      await load();
    } catch (e) {
      setError(e.message || 'Analysis failed');
    } finally {
      setRefreshing(false);
    }
  };

  const a = data?.analysis;
  const risk = data?.risk_profile;
  const rules = data?.rules;

  return (
    <div className="rounded-md border border-zinc-800 bg-[#121821] p-4" data-testid="prop-firm-section">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 flex items-center gap-2">
          <ShieldCheck size={12} /> Prop Firm Analysis ({rules?.firm_name || 'FTMO'})
        </p>
        <button
          data-testid="prop-analyze-btn"
          onClick={runAnalysis}
          disabled={refreshing}
          className="text-[10px] font-medium px-2 py-1 rounded border border-accent-primary/40 bg-accent-primary/10 text-accent-primary hover:bg-accent-primary/20 disabled:opacity-50 flex items-center gap-1"
        >
          {refreshing ? <Spinner size={10} className="animate-spin" /> : <ArrowsClockwise size={10} />}
          {a ? 'Re-analyze' : 'Analyze'}
        </button>
      </div>

      {loading && (
        <p className="text-xs font-mono text-zinc-500 py-3 text-center">
          <Spinner size={12} className="animate-spin inline mr-2" /> Loading…
        </p>
      )}

      {error && (
        <p className="text-xs font-mono text-red-400 py-2" data-testid="prop-analysis-error">{error}</p>
      )}

      {!loading && !a && !error && (
        <p className="text-xs font-mono text-zinc-500 py-3">
          No analysis yet — click <strong>Analyze</strong> to run against FTMO rules.
        </p>
      )}

      {a && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Verdict</p>
              <div className="mt-1.5"><PropStatusPill status={a.status} /></div>
            </div>
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Pass Probability</p>
              <p className="text-lg font-bold text-zinc-100 tabular-nums mt-0.5">
                {fmt(a.pass_probability, 1)}%
              </p>
            </div>
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Expected Days</p>
              <p className="text-lg font-bold text-zinc-100 tabular-nums mt-0.5">
                {a.expected_days_to_pass ?? '—'}
                {a.hits_time_limit && (
                  <span className="ml-1 text-[9px] text-red-400">exceeds limit</span>
                )}
              </p>
            </div>
            <div className="rounded border border-zinc-800 bg-[#0B0F14] px-3 py-2">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Safe Risk/Trade</p>
              <p className="text-lg font-bold text-accent-primary tabular-nums mt-0.5">
                {fmt(risk?.recommended_risk_per_trade, 2)}%
              </p>
            </div>
          </div>

          {/* Violations */}
          {a.violations && a.violations.length > 0 && (
            <div data-testid="prop-violations">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-red-400 mb-1.5">
                Violations ({a.violations.length})
              </p>
              <ul className="space-y-1">
                {a.violations.map((v, i) => (
                  <li key={i} className="text-[11px] font-mono text-red-300 bg-red-500/5 border border-red-500/20 rounded px-2 py-1">
                    <span className="text-red-400 font-bold uppercase text-[9px] mr-2">{v.severity}</span>
                    {v.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Warnings */}
          {a.warnings && a.warnings.length > 0 && (
            <div data-testid="prop-warnings">
              <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-yellow-400 mb-1.5">
                Warnings ({a.warnings.length})
              </p>
              <ul className="space-y-1">
                {a.warnings.map((v, i) => (
                  <li key={i} className="text-[11px] font-mono text-yellow-200 bg-yellow-500/5 border border-yellow-500/20 rounded px-2 py-1">
                    <span className="text-yellow-400 font-bold uppercase text-[9px] mr-2">{v.severity}</span>
                    {v.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Firm rule block */}
          {rules && (
            <div className="grid grid-cols-3 gap-2 text-[10px] font-mono text-zinc-400">
              <div>Max Daily Loss: <span className="text-zinc-200">{fmt(rules.max_daily_loss_pct, 1)}%</span></div>
              <div>Max Total Loss: <span className="text-zinc-200">{fmt(rules.max_total_loss_pct, 1)}%</span></div>
              <div>Profit Target: <span className="text-zinc-200">{fmt(rules.profit_target_pct, 1)}%</span></div>
              <div>Min Trading Days: <span className="text-zinc-200">{rules.min_trading_days ?? '—'}</span></div>
              <div>Trailing DD: <span className="text-zinc-200">{String(rules.trailing_drawdown ?? false)}</span></div>
              <div>Time Limit: <span className="text-zinc-200">{rules.time_limit_days ?? '—'}d</span></div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── History side-panel ────────────────────────────────────────────────

function HistoryPanel({ strategyHash, onClose }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getStrategyHistory(strategyHash)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(e.message || 'Failed to load history'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [strategyHash]);

  const chartData = useMemo(() => {
    if (!data?.history) return [];
    return data.history.map((row, i) => ({
      idx: i + 1,
      ts: row.ts ? new Date(row.ts).toLocaleString() : '',
      pf: typeof row.pf === 'number' ? row.pf : null,
      dd: typeof row.dd_pct === 'number' ? row.dd_pct : null,
      mutation_type: row.mutation_type || '',
      source: row.source || '',
    }));
  }, [data]);

  const mutationTypes = data?.summary?.mutation_type_counts || {};
  const mutationEntries = Object.entries(mutationTypes).sort((a, b) => b[1] - a[1]);

  return (
    <div
      className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm flex justify-end"
      data-testid="history-panel-overlay"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl h-full bg-[#0F141B] border-l border-zinc-800 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="history-panel"
      >
        <div className="sticky top-0 bg-[#0F141B]/95 backdrop-blur border-b border-zinc-800 px-5 py-3 flex items-center justify-between z-10">
          <div>
            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-[0.2em]">Strategy History</p>
            <p className="font-mono text-xs text-zinc-300 mt-0.5">{strategyHash}</p>
          </div>
          <button
            onClick={onClose}
            data-testid="history-close-btn"
            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200"
          >
            <X size={16} />
          </button>
        </div>

        {loading && (
          <div className="p-10 text-center text-xs font-mono text-zinc-500">
            <Spinner size={20} className="animate-spin inline mr-2" /> Loading history…
          </div>
        )}

        {error && (
          <div className="p-6 text-xs font-mono text-red-400" data-testid="history-error">
            {error}
          </div>
        )}

        {!loading && !error && data && (
          <div className="p-5 space-y-5">
            {/* Summary */}
            <div className="grid grid-cols-4 gap-3" data-testid="history-summary">
              {[
                ['Runs', data.runs],
                ['Best PF', fmt(data.summary?.best_pf)],
                ['Avg PF', fmt(data.summary?.avg_pf)],
                ['Last PF', fmt(data.summary?.last_pf)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md border border-zinc-800 bg-[#121821] px-3 py-2">
                  <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{k}</p>
                  <p className="text-lg font-bold text-zinc-100 tabular-nums mt-0.5">{v}</p>
                </div>
              ))}
            </div>

            {/* Chart */}
            <div className="rounded-md border border-zinc-800 bg-[#121821] p-4" data-testid="history-chart">
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-3 flex items-center gap-2">
                <ChartLine size={12} /> PF over time
              </p>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                    <XAxis dataKey="idx" stroke="#52525b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#52525b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{
                        background: '#0F141B',
                        border: '1px solid #27272a',
                        borderRadius: 6,
                        fontSize: 11,
                      }}
                      labelStyle={{ color: '#a1a1aa' }}
                      formatter={(value, key) => [fmt(value, 3), key === 'pf' ? 'PF' : key]}
                    />
                    <ReferenceLine y={1} stroke="#ef4444" strokeDasharray="2 2" />
                    <Line
                      type="monotone"
                      dataKey="pf"
                      stroke="#00E0B8"
                      strokeWidth={2}
                      dot={{ r: 3, fill: '#00E0B8' }}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-10">No PF data yet.</p>
              )}
            </div>

            {/* Challenge Match (Phase 2) */}
            <ChallengeMatchSection strategyHash={strategyHash} />

            {/* Prop Firm Analysis */}
            <PropFirmAnalysisSection strategyHash={strategyHash} />

            {/* Mutation type distribution */}
            <div className="rounded-md border border-zinc-800 bg-[#121821] p-4" data-testid="history-mutations">
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-3">
                Mutation types
              </p>
              {mutationEntries.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {mutationEntries.map(([mt, n]) => (
                    <span
                      key={mt}
                      className="text-[10px] font-mono px-2 py-1 rounded border border-zinc-700 bg-zinc-900 text-zinc-300"
                    >
                      {mt} <span className="text-accent-primary ml-1">×{n}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No mutation types recorded.</p>
              )}
            </div>

            {/* Raw runs */}
            <div className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden" data-testid="history-table">
              <table className="w-full text-xs">
                <thead className="bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                  <tr>
                    <th className="text-left px-3 py-2">#</th>
                    <th className="text-left px-3 py-2">When</th>
                    <th className="text-left px-3 py-2">Source</th>
                    <th className="text-left px-3 py-2">Mutation</th>
                    <th className="text-right px-3 py-2">PF</th>
                    <th className="text-right px-3 py-2">DD%</th>
                    <th className="text-right px-3 py-2">Trades</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {(data.history || []).map((row, i) => (
                    <tr key={`${row.ts}-${i}`} className="hover:bg-zinc-900/50">
                      <td className="px-3 py-1.5 font-mono text-zinc-500">{i + 1}</td>
                      <td className="px-3 py-1.5 font-mono text-zinc-400 whitespace-nowrap">
                        {row.ts ? new Date(row.ts).toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-1.5"><SourcePill src={row.source} /></td>
                      <td className="px-3 py-1.5 font-mono text-zinc-300">{row.mutation_type || '—'}</td>
                      <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${pfColor(row.pf)}`}>
                        {fmt(row.pf)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-zinc-300 tabular-nums">
                        {fmt(row.dd_pct)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-zinc-300 tabular-nums">
                        {row.trades ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main explorer ─────────────────────────────────────────────────────

export default function StrategyExplorer() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [source, setSource] = useState('');
  const [minPf, setMinPf] = useState('');
  const [minRuns, setMinRuns] = useState(0);
  const [favOnly, setFavOnly] = useState(false);
  const [search, setSearch] = useState('');

  const [historyHash, setHistoryHash] = useState(null);
  const [detailsId, setDetailsId] = useState(null);
  const [sortKey, setSortKey] = useState('best_pf');
  const [sortDir, setSortDir] = useState('desc');
  const [busyHash, setBusyHash] = useState(null);
  const [scanBusyHash, setScanBusyHash] = useState(null);
  const [matchBusyHash, setMatchBusyHash] = useState(null);
  const [batchScanBusy, setBatchScanBusy] = useState(false);
  const [batchAnalyzeBusy, setBatchAnalyzeBusy] = useState(false);
  const [batchMatchBusy, setBatchMatchBusy] = useState(false);
  const [unverifiedFirms, setUnverifiedFirms] = useState([]);
  const [toast, setToast] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        limit: 500,
        min_runs: Number(minRuns) || 0,
        favorites_only: favOnly,
      };
      if (source) params.source = source;
      if (minPf && !Number.isNaN(parseFloat(minPf))) params.min_pf = parseFloat(minPf);
      const data = await getExplorer(params);
      setRows(data.strategies || []);
    } catch (e) {
      setError(e.message || 'Failed to load explorer');
    } finally {
      setLoading(false);
    }
  }, [source, minPf, minRuns, favOnly]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Phase 20: surface unverified prop-firm rule sets so the user knows
  // some analyses / matches may be silently skipped.
  useEffect(() => {
    let live = true;
    listPropFirmReviewRules()
      .then((r) => {
        if (!live) return;
        const bad = (r.rules || []).filter((x) => x.status !== 'approved');
        setUnverifiedFirms(bad);
      })
      .catch(() => {});
    return () => { live = false; };
  }, []);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const base = q
      ? rows.filter((r) =>
          (r.name || '').toLowerCase().includes(q) ||
          (r.type || '').toLowerCase().includes(q) ||
          (r.pair || '').toLowerCase().includes(q) ||
          (r.strategy_hash || '').toLowerCase().includes(q),
        )
      : rows;

    // ── Sort by selected column (Phase 24) ──
    const sortFn = SORT_RESOLVERS[sortKey] || ((r) => r.best_pf || 0);
    const dirMul = sortDir === 'asc' ? 1 : -1;
    return [...base].sort((a, b) => {
      const va = sortFn(a);
      const vb = sortFn(b);
      const na = (va == null || Number.isNaN(va)) ? -Infinity : va;
      const nb = (vb == null || Number.isNaN(vb)) ? -Infinity : vb;
      if (na < nb) return -1 * dirMul;
      if (na > nb) return  1 * dirMul;
      return 0;
    });
  }, [rows, search, sortKey, sortDir]);

  const toggleSort = useCallback((key) => {
    setSortKey((curKey) => {
      if (curKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return key;
      }
      setSortDir('desc');
      return key;
    });
  }, []);

  const pushToast = (msg, kind = 'ok') => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  const handleReRun = async (hash) => {
    setBusyHash(hash);
    try {
      const r = await reRunStrategyByHash(hash, { max_variants: 10, auto_save: true });
      pushToast(
        `Re-run complete — best PF ${r.best_pf?.toFixed?.(2) ?? 'n/a'} (${r.best_mutation_type || 'n/a'})`,
        'ok',
      );
      await fetchData();
    } catch (e) {
      pushToast(`Re-run failed: ${e.message || 'unknown error'}`, 'err');
    } finally {
      setBusyHash(null);
    }
  };

  const handleFavorite = async (hash, current) => {
    try {
      await toggleStrategyFavorite(hash, !current);
      setRows((old) => old.map((r) => (r.strategy_hash === hash ? { ...r, is_favorite: !current } : r)));
    } catch (e) {
      pushToast(`Favorite failed: ${e.message || 'unknown error'}`, 'err');
    }
  };

  const handleExportJson = async (hash, name) => {
    try {
      const data = await exportStrategyByHash(hash);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(name || 'strategy').replace(/[^A-Za-z0-9_-]+/g, '_')}_${hash.slice(0, 8)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      pushToast('Exported JSON', 'ok');
    } catch (e) {
      pushToast(`Export failed: ${e.message || 'unknown error'}`, 'err');
    }
  };

  const handleExportCbot = async (hash, name) => {
    try {
      await downloadStrategyCbotByHash(hash, name);
      pushToast('Exported cBot skeleton (.cs)', 'ok');
    } catch (e) {
      pushToast(`Export failed: ${e.message || 'unknown error'}`, 'err');
    }
  };

  const handleMarketScan = async (hash, name) => {
    setScanBusyHash(hash);
    try {
      const r = await scanStrategyMarket(hash, {});
      const best = r.best_environment;
      if (best) {
        pushToast(
          `Scan complete — best ${best.pair} · ${best.timeframe} (PF ${fmt(best.pf)}, score ${fmt(best.score)})`,
          'ok',
        );
      } else {
        pushToast(`Scan complete — no usable environment found (${r.no_data?.length || 0} cells with no data)`, 'err');
      }
      await fetchData();
    } catch (e) {
      pushToast(`Market scan failed: ${e.message || 'unknown error'}`, 'err');
    } finally {
      setScanBusyHash(null);
    }
  };

  const handleScanEligibleBatch = async () => {
    setBatchScanBusy(true);
    try {
      const r = await scanMarketEligible({ limit: 3 });
      const scanned = r.scanned || [];
      const good = scanned.filter((s) => s.best_environment).length;
      pushToast(
        `Batch scan done — ${good}/${scanned.length} strategies now have a best environment`,
        good > 0 ? 'ok' : 'err',
      );
      await fetchData();
    } catch (e) {
      pushToast(`Batch scan failed: ${e.message || 'unknown error'}`, 'err');
    } finally {
      setBatchScanBusy(false);
    }
  };

  const handleBatchAnalyzeFtmo = async () => {
    setBatchAnalyzeBusy(true);
    try {
      const r = await batchAnalyzeProp({ firm_slug: 'ftmo', limit: 50, min_runs: 1 });
      if (r.status === 'skipped_unverified') {
        pushToast('Skipped — FTMO rules not verified. Approve them in Prop Firms.', 'err');
      } else {
        pushToast(
          `Analyzed ${r.analyzed} strategies · skipped ${r.skipped} · errors ${r.errors?.length || 0}`,
          r.analyzed > 0 ? 'ok' : 'err',
        );
      }
      await fetchData();
    } catch (e) {
      pushToast(`Batch analysis failed: ${e.message || 'unknown error'}`, 'err');
    } finally {
      setBatchAnalyzeBusy(false);
    }
  };

  const handleMatchChallenges = async (hash, name) => {
    setMatchBusyHash(hash);
    try {
      const r = await matchStrategyChallenges(hash, true);
      pushToast(
        `Matched — best: ${r.best_firm_name || r.best_firm} / ${r.best_challenge} (PP ${fmt(r.pass_probability, 1)}%, score ${fmt(r.score, 2)})`,
        r.status === 'PASS' ? 'ok' : 'err',
      );
      await fetchData();
    } catch (e) {
      const msg = e.message || 'unknown error';
      if (msg.includes('rules_not_verified')) {
        pushToast('Cannot match — all relevant firms are unverified. Approve them in Prop Firms.', 'err');
      } else {
        pushToast(`Match failed: ${msg}`, 'err');
      }
    } finally {
      setMatchBusyHash(null);
    }
  };

  const handleBatchMatchEligible = async () => {
    setBatchMatchBusy(true);
    try {
      const r = await runEligibleChallengeMatch({ limit: 3 });
      const errs = (r.errors || []).filter((e) =>
        (e.error || '').includes('rules_not_verified'),
      );
      if (errs.length > 0) {
        pushToast(
          `Matched ${r.matched} · ${errs.length} skipped (unverified firms — approve them first)`,
          r.matched > 0 ? 'ok' : 'err',
        );
      } else {
        pushToast(
          `Matched ${r.matched}/${r.considered} eligible strategies · errors ${r.errors?.length || 0}`,
          r.matched > 0 ? 'ok' : 'err',
        );
      }
      await fetchData();
    } catch (e) {
      pushToast(`Batch match failed: ${e.message || 'unknown error'}`, 'err');
    } finally {
      setBatchMatchBusy(false);
    }
  };

  return (
    <div data-testid="strategy-explorer" className="asf-section asf-u2-panel space-y-4">
      {/* ─── Header (legacy title hidden when wrapped). ─── */}
      <div className="asf-section__hd">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <Compass size={20} className="text-accent-primary" /> Strategy Explorer
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-2xl">
            Every strategy ever run across ingestion + auto-mutation, grouped by stable hash.
            See best PF, stability, and re-run the winners.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button
            data-testid="explorer-batch-match-btn"
            onClick={handleBatchMatchEligible}
            disabled={batchMatchBusy}
            title="Match top 3 eligible strategies to best firm × challenge"
            className="text-xs font-medium px-3 py-1.5 rounded border border-yellow-500/40 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-300 disabled:opacity-50 flex items-center gap-1.5"
          >
            {batchMatchBusy ? <Spinner size={12} className="animate-spin" /> : <Trophy size={12} />}
            Match Eligible (top 3)
          </button>
          <button
            data-testid="explorer-batch-analyze-btn"
            onClick={handleBatchAnalyzeFtmo}
            disabled={batchAnalyzeBusy}
            title="Run FTMO rule validation + pass probability on all strategies (skip ones already analyzed)"
            className="text-xs font-medium px-3 py-1.5 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-50 flex items-center gap-1.5"
          >
            {batchAnalyzeBusy ? (
              <Spinner size={12} className="animate-spin" />
            ) : (
              <ShieldCheck size={12} />
            )}
            Analyze all (FTMO)
          </button>
          <button
            data-testid="explorer-scan-eligible-btn"
            onClick={handleScanEligibleBatch}
            disabled={batchScanBusy}
            title="Scan top 3 eligible strategies (PF ≥ 1.2, runs ≥ 3) across pair × timeframe grid"
            className="text-xs font-medium px-3 py-1.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-50 flex items-center gap-1.5"
          >
            {batchScanBusy ? (
              <Spinner size={12} className="animate-spin" />
            ) : (
              <Target size={12} />
            )}
            Scan eligible (top 3)
          </button>
          <button
            data-testid="explorer-refresh-btn"
            onClick={fetchData}
            disabled={loading}
            className="text-xs font-medium px-3 py-1.5 rounded border border-zinc-700 hover:border-accent-primary/50 hover:text-accent-primary text-zinc-300 bg-[#121821] disabled:opacity-50 flex items-center gap-1.5"
          >
            <ArrowsClockwise size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* ─── Unverified firms warning (Phase 20) ─── */}
      {unverifiedFirms.length > 0 && (
        <div
          data-testid="unverified-firms-banner"
          className="rounded-md border border-yellow-500/30 bg-yellow-500/5 px-3 py-2 flex items-start gap-2"
        >
          <Warning size={14} className="text-yellow-400 mt-0.5 flex-shrink-0" weight="fill" />
          <div className="flex-1">
            <p className="text-[11px] font-mono text-yellow-200">
              <span className="font-bold uppercase tracking-[0.15em]">rules_not_verified</span> — {unverifiedFirms.length} firm(s)
              are skipped in analysis & matching until approved:
              <span className="text-zinc-300 ml-1">
                {unverifiedFirms.map((f) => (
                  <span key={f.firm_slug} className="inline-block mr-2">
                    {f.firm_name || f.firm_slug}
                    <span className="text-[9px] text-yellow-500 ml-0.5">({f.status})</span>
                  </span>
                ))}
              </span>
            </p>
            <p className="text-[10px] font-mono text-zinc-500 mt-0.5">
              Open <em>Prop Firms → Add New Firm</em> or the firm detail to review and approve.
            </p>
          </div>
        </div>
      )}

      {/* ─── Filters ─── */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] p-3 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col flex-1 min-w-[200px]">
          <label className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">Search</label>
          <div className="relative">
            <MagnifyingGlass size={12} className="absolute left-2.5 top-2.5 text-zinc-500" />
            <input
              data-testid="explorer-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name, type, pair, hash…"
              className="w-full pl-7 pr-3 py-1.5 bg-[#0B0F14] border border-zinc-800 rounded text-xs text-zinc-200 focus:outline-none focus:border-accent-primary/40"
            />
          </div>
        </div>
        <div className="flex flex-col">
          <label className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">Source</label>
          <select
            data-testid="explorer-filter-source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="bg-[#0B0F14] border border-zinc-800 rounded text-xs text-zinc-200 px-2 py-1.5 focus:outline-none focus:border-accent-primary/40"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col">
          <label className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">Min PF</label>
          <input
            data-testid="explorer-filter-min-pf"
            type="number"
            step="0.1"
            value={minPf}
            onChange={(e) => setMinPf(e.target.value)}
            placeholder="—"
            className="w-24 bg-[#0B0F14] border border-zinc-800 rounded text-xs text-zinc-200 px-2 py-1.5 focus:outline-none focus:border-accent-primary/40"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">Min Runs</label>
          <input
            data-testid="explorer-filter-min-runs"
            type="number"
            min="0"
            value={minRuns}
            onChange={(e) => setMinRuns(e.target.value)}
            className="w-20 bg-[#0B0F14] border border-zinc-800 rounded text-xs text-zinc-200 px-2 py-1.5 focus:outline-none focus:border-accent-primary/40"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer select-none pb-1.5">
          <input
            data-testid="explorer-filter-favorites"
            type="checkbox"
            checked={favOnly}
            onChange={(e) => setFavOnly(e.target.checked)}
            className="accent-accent-primary"
          />
          Favorites only
        </label>
      </div>

      {/* ─── Error banner (U-2 AsfEmptyState verdict=danger) ─── */}
      {error && (
        <AsfEmptyState
          slug="explorer-error"
          testId="explorer-error"
          title="Couldn’t load strategies"
          body={error}
          action={{ label: 'Retry', onClick: fetchData, testId: 'explorer-error-retry' }}
        />
      )}

      {/* ─── Table ─── */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="explorer-table">
            <thead className="bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <tr>
                <th className="text-left px-3 py-2.5">Strategy</th>
                <th className="text-left px-3 py-2.5">Stage</th>
                <th className="text-left px-3 py-2.5">Type</th>
                <SortableHeader testId="explorer-sort-best-pf"  align="right" sortKey={sortKey} sortDir={sortDir} colKey="best_pf"          onClick={toggleSort}>Best PF</SortableHeader>
                <SortableHeader testId="explorer-sort-oos"      align="right" sortKey={sortKey} sortDir={sortDir} colKey="oos_ratio"       onClick={toggleSort}>OOS ratio</SortableHeader>
                <SortableHeader testId="explorer-sort-trades"   align="right" sortKey={sortKey} sortDir={sortDir} colKey="total_trades"    onClick={toggleSort}>Trades</SortableHeader>
                <SortableHeader testId="explorer-sort-winrate"  align="right" sortKey={sortKey} sortDir={sortDir} colKey="win_rate"        onClick={toggleSort}>Win %</SortableHeader>
                <SortableHeader testId="explorer-sort-dd"       align="right" sortKey={sortKey} sortDir={sortDir} colKey="max_dd"          onClick={toggleSort}>Max DD</SortableHeader>
                <SortableHeader testId="explorer-sort-runs"     align="right" sortKey={sortKey} sortDir={sortDir} colKey="runs"            onClick={toggleSort}>Runs</SortableHeader>
                <SortableHeader testId="explorer-sort-stab"     align="left"  sortKey={sortKey} sortDir={sortDir} colKey="stability"       onClick={toggleSort}>Stability</SortableHeader>
                <SortableHeader testId="explorer-sort-pp"       align="left"  sortKey={sortKey} sortDir={sortDir} colKey="pass_probability" onClick={toggleSort}>Pass Prob</SortableHeader>
                <th className="text-left px-3 py-2.5">Badges</th>
                <th className="text-left px-3 py-2.5">Best Environment</th>
                <th className="text-left px-3 py-2.5">FTMO</th>
                <th className="text-right px-3 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loading && filteredRows.length === 0 && (
                <tr><td colSpan={15} className="px-3 py-10 text-center text-zinc-500 font-mono">
                  <Spinner size={16} className="animate-spin inline mr-2" /> Loading…
                </td></tr>
              )}
              {!loading && filteredRows.length === 0 && (
                <tr><td colSpan={15} className="px-3 py-10 text-center text-zinc-500 font-mono" data-testid="explorer-empty">
                  No strategies yet — run an ingestion or mutation cycle from the Dashboard.
                </td></tr>
              )}
              {filteredRows.map((r) => {
                const v = r.validation || {};
                const m = v.metrics || {};
                return (
                <tr
                  key={r.strategy_hash}
                  data-testid={`explorer-row-${r.strategy_hash}`}
                  className="hover:bg-zinc-900/50 transition-colors"
                >
                  <td className="px-3 py-2">
                    <div className="flex items-start gap-2">
                      <button
                        onClick={() => handleFavorite(r.strategy_hash, r.is_favorite)}
                        data-testid={`explorer-fav-${r.strategy_hash}`}
                        aria-pressed={!!r.is_favorite}
                        className={`mt-0.5 ${r.is_favorite ? 'text-yellow-400' : 'text-zinc-600 hover:text-yellow-400'}`}
                        title={r.is_favorite ? 'Remove favorite' : 'Mark as favorite'}
                      >
                        <Star size={14} weight={r.is_favorite ? 'fill' : 'regular'} />
                      </button>
                      <div className="min-w-0">
                        <p className="font-medium text-zinc-200 truncate" title={r.name || 'unnamed'}>{r.name || 'unnamed'}</p>
                        <p className="text-[9px] font-mono text-zinc-500 mt-0.5 truncate">
                          {r.pair || '—'} · {r.timeframe || '—'} · {r.strategy_hash?.slice(0, 10)}…
                        </p>
                        {v.confidence_summary && (
                          <p
                            data-testid={`explorer-summary-${r.strategy_hash}`}
                            className="text-[10px] font-mono text-zinc-400 mt-0.5 truncate"
                            title={v.confidence_summary}
                          >
                            {v.confidence_summary}
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-0.5 items-start">
                      <StageBadge stage={v.stage} lifecycleStage={v.lifecycle_stage} />
                      {m.behavioral_profile && m.behavioral_profile !== 'BALANCED' && m.behavioral_profile !== 'UNCLASSIFIED' && (
                        <span
                          data-testid={`explorer-profile-${r.strategy_hash}`}
                          className="text-[8px] font-mono uppercase tracking-wider px-1 py-0.5 rounded border border-zinc-700 text-zinc-400 bg-zinc-900/40 truncate max-w-[110px]"
                          title={m.behavioral_profile}
                        >
                          {m.behavioral_profile.replace(/_/g, ' ').toLowerCase()}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-zinc-300">{r.type || '—'}</td>
                  <td className={`px-3 py-2 text-right font-mono font-bold tabular-nums ${pfColor(r.best_pf)}`} title={`Avg ${fmt(r.avg_pf)} · Last ${fmt(r.last_pf)}`}>
                    {fmt(r.best_pf)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono tabular-nums ${oosRatioColor(m.oos_ratio)}`} title={m.is_pf != null && m.oos_pf != null ? `IS ${m.is_pf?.toFixed?.(2) ?? '—'} → OOS ${m.oos_pf?.toFixed?.(2) ?? '—'}` : ''}>
                    {fmt(m.oos_ratio)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-300 tabular-nums">
                    {m.total_trades != null ? Number(m.total_trades).toLocaleString() : '—'}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono tabular-nums ${winRateColor(m.win_rate)}`}
                    title={
                      m.wins != null && m.losses != null
                        ? `Wins ${m.wins} · Losses ${m.losses}${m.risk_reward_ratio ? ` · RR ${m.risk_reward_ratio}` : ''}`
                        : ''
                    }
                  >
                    <div className="flex flex-col items-end leading-tight">
                      <span>{m.win_rate != null ? `${Number(m.win_rate).toFixed(1)}%` : '—'}</span>
                      {(m.wins != null || m.losses != null) && (
                        <span
                          data-testid={`explorer-winloss-${r.strategy_hash}`}
                          className="text-[8px] text-zinc-500"
                        >
                          {m.wins ?? '—'}<span className="text-emerald-400/70">W</span>
                          {' / '}
                          {m.losses ?? '—'}<span className="text-red-400/70">L</span>
                        </span>
                      )}
                    </div>
                  </td>
                  <td className={`px-3 py-2 text-right font-mono tabular-nums ${ddColor(m.max_drawdown_pct)}`}>
                    {m.max_drawdown_pct != null ? `${(m.max_drawdown_pct * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-300 tabular-nums">{r.runs}</td>
                  <td className="px-3 py-2"><StabilityBar score={r.stability_score} /></td>
                  <td className="px-3 py-2">
                    <PassProbBar
                      pct={r.challenge_match?.pass_probability ?? r.prop_analysis?.pass_probability}
                      riskLevel={r.prop_analysis?.risk_level}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <ValidationBadges badges={v.badges} />
                  </td>
                  <td className="px-3 py-2">
                    <BestEnvironmentCell env={r.best_environment} />
                  </td>
                  <td className="px-3 py-2">
                    <PropStatusPill status={r.challenge_match?.status || r.prop_analysis?.status} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        data-testid={`explorer-details-${r.strategy_hash}`}
                        onClick={() => setDetailsId(r.library_id)}
                        disabled={!r.library_id}
                        title={r.library_id ? 'Open research details' : 'No saved library entry yet'}
                        className="p-1.5 rounded hover:bg-accent-primary/10 text-zinc-400 hover:text-accent-primary disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <MagnifyingGlassPlus size={13} />
                      </button>
                      <button
                        data-testid={`explorer-match-${r.strategy_hash}`}
                        onClick={() => handleMatchChallenges(r.strategy_hash, r.name)}
                        disabled={matchBusyHash === r.strategy_hash}
                        title="Match to best firm × challenge"
                        className="p-1.5 rounded hover:bg-yellow-500/10 text-zinc-400 hover:text-yellow-300 disabled:opacity-40"
                      >
                        {matchBusyHash === r.strategy_hash ? (
                          <Spinner size={13} className="animate-spin" />
                        ) : (
                          <Trophy size={13} />
                        )}
                      </button>
                      <button
                        data-testid={`explorer-scan-${r.strategy_hash}`}
                        onClick={() => handleMarketScan(r.strategy_hash, r.name)}
                        disabled={scanBusyHash === r.strategy_hash}
                        title="Scan pair × timeframe grid"
                        className="p-1.5 rounded hover:bg-accent-primary/10 text-zinc-400 hover:text-accent-primary disabled:opacity-40"
                      >
                        {scanBusyHash === r.strategy_hash ? (
                          <Spinner size={13} className="animate-spin" />
                        ) : (
                          <Target size={13} />
                        )}
                      </button>
                      <button
                        data-testid={`explorer-rerun-${r.strategy_hash}`}
                        onClick={() => handleReRun(r.strategy_hash)}
                        disabled={busyHash === r.strategy_hash}
                        title="Re-run mutation pipeline"
                        className="p-1.5 rounded hover:bg-emerald-500/10 text-zinc-400 hover:text-emerald-300 disabled:opacity-40"
                      >
                        {busyHash === r.strategy_hash ? (
                          <Spinner size={13} className="animate-spin" />
                        ) : (
                          <ArrowsClockwise size={13} />
                        )}
                      </button>
                      <button
                        data-testid={`explorer-history-${r.strategy_hash}`}
                        onClick={() => setHistoryHash(r.strategy_hash)}
                        title="View history"
                        className="p-1.5 rounded hover:bg-sky-500/10 text-zinc-400 hover:text-sky-300"
                      >
                        <ChartLine size={13} />
                      </button>
                      <button
                        data-testid={`explorer-export-json-${r.strategy_hash}`}
                        onClick={() => handleExportJson(r.strategy_hash, r.name)}
                        title="Export JSON"
                        className="p-1.5 rounded hover:bg-violet-500/10 text-zinc-400 hover:text-violet-300"
                      >
                        <FileJs size={13} />
                      </button>
                      <button
                        data-testid={`explorer-export-cbot-${r.strategy_hash}`}
                        onClick={() => handleExportCbot(r.strategy_hash, r.name)}
                        title="Export cBot (.cs) skeleton"
                        className="p-1.5 rounded hover:bg-amber-500/10 text-zinc-400 hover:text-amber-300"
                      >
                        <FileCode size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[10px] font-mono text-zinc-600 flex items-center gap-1.5">
        <ArrowRight size={10} /> Showing {filteredRows.length} of {rows.length} strategies from
        &nbsp;<code className="text-zinc-400">strategy_performance_history</code>
        &nbsp;· sort by <code className="text-zinc-400">{sortKey}</code> {sortDir === 'asc' ? '↑' : '↓'}
      </p>

      {historyHash && (
        <HistoryPanel strategyHash={historyHash} onClose={() => setHistoryHash(null)} />
      )}

      {detailsId && (
        <StrategyDetailsPanel strategyId={detailsId} onClose={() => setDetailsId(null)} />
      )}

      {toast && (
        <div
          data-testid="explorer-toast"
          className={`fixed bottom-4 right-4 z-50 text-xs font-medium px-3 py-2 rounded border shadow-lg max-w-sm ${
            toast.kind === 'err'
              ? 'bg-red-500/10 border-red-500/30 text-red-300'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          }`}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
