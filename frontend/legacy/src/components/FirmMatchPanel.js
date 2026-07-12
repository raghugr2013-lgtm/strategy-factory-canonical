import React, { useState } from 'react';
import {
  Trophy,
  ShieldCheck,
  Warning,
  XCircle,
  Target,
  ArrowsClockwise,
  TrendUp,
  Coins,
  Gauge,
} from '@phosphor-icons/react';
import { matchFirmsPhase4 } from '../services/api';
import { AsfEmptyState } from './ui-asf';

/**
 * Phase 4 — Strategy ↔ Prop Firm Match Panel
 *
 * Accepts one of:
 *   - strategyId
 *   - trades  (array of trade dicts)
 *   - strategyText + pair + timeframe  (ad-hoc backtest on server)
 *
 * Variants:
 *   - "compact"  → condensed strip for Dashboard drawer.
 *   - "full"     → BEST-MATCH hero card + OTHER MATCHES list inside Deep-Dive panel.
 *
 * Backend is stateless — nothing is persisted.
 */
export default function FirmMatchPanel({
  strategyId,
  trades,
  strategyText,
  pair,
  timeframe,
  variant = 'full',
  initialBalance = 10000,
  nSimulations = 30,
  autoRun = false,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const canRun =
    !!strategyId ||
    (Array.isArray(trades) && trades.length > 0) ||
    (strategyText && pair && timeframe);

  const run = async () => {
    if (!canRun) {
      setError('No strategy input available to match.');
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await matchFirmsPhase4({
        strategyId,
        trades,
        strategyText,
        pair,
        timeframe,
        initialBalance,
        nSimulations,
      });
      setData(res.matching);
    } catch (e) {
      setError(e.message || 'Match failed');
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (autoRun && canRun && !data && !loading) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);

  return (
    <div data-testid="firm-match-panel" className="space-y-3">
      <Header data={data} loading={loading} canRun={canRun} onRun={run} />
      {error && <ErrorBanner message={error} />}
      {!data && !loading && !error && (
        <HintBanner canRun={canRun} />
      )}
      {data && (data.ranked_matches || []).length === 0 && (
        <EmptyBanner rejectedCount={data.rejected?.length || 0} />
      )}
      {data && (data.ranked_matches || []).length > 0 && (
        variant === 'compact'
          ? <CompactList matches={data.ranked_matches} />
          : <FullLayout matches={data.ranked_matches} rejected={data.rejected || []} meta={data} />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Header
// ═══════════════════════════════════════════════════════════════════

function Header({ data, loading, canRun, onRun }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 min-w-0">
        <Trophy size={14} weight="bold" className="text-emerald-400 flex-shrink-0" />
        <h4 className="text-[11px] font-mono uppercase tracking-wider text-zinc-300">
          Best Prop Firm Matches
        </h4>
        {data && (
          <span className="text-[10px] font-mono text-zinc-500 truncate">
            · {data.firms_compatible}/{data.firms_analyzed} firms
            {data.overfit_score > 0 ? ` · overfit ${data.overfit_score}` : ''}
          </span>
        )}
      </div>
      <button
        data-testid="firm-match-run-btn"
        onClick={onRun}
        disabled={loading || !canRun}
        className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-wait px-3 py-1.5 rounded transition-colors"
      >
        {loading ? (
          <>
            <ArrowsClockwise size={11} weight="bold" className="animate-spin" />
            Matching…
          </>
        ) : (
          <>
            <Target size={11} weight="bold" />
            {data ? 'Re-run' : 'Find Best Firms'}
          </>
        )}
      </button>
    </div>
  );
}

function HintBanner({ canRun }) {
  return (
    <div className="text-[11px] text-zinc-500 italic">
      {canRun
        ? 'Run the matcher to rank every compatible prop-firm challenge plan for this strategy.'
        : 'No strategy trades or id available — run a backtest first.'}
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <AsfEmptyState
      slug="firm-match-error"
      testId="firm-match-error"
      title="Match failed"
      body={message}
    />
  );
}

function EmptyBanner({ rejectedCount }) {
  return (
    <div
      data-testid="firm-match-empty"
      className="text-[11px] text-zinc-400 italic bg-zinc-900/60 border border-zinc-800 rounded p-3"
    >
      No compatible firms. {rejectedCount ? `${rejectedCount} firm(s) were rejected at prefilter.` : ''}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Full layout — BEST MATCH hero + OTHER MATCHES list
// ═══════════════════════════════════════════════════════════════════

function FullLayout({ matches, rejected, meta }) {
  const [best, ...rest] = matches;
  const others = rest.slice(0, 5);

  return (
    <div className="space-y-4">
      <BestMatchHero match={best} />
      {others.length > 0 && (
        <section className="space-y-2">
          <h5 className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
            Other Matches
          </h5>
          <div className="space-y-1.5">
            {others.map((m, i) => (
              <MatchRow key={`${m.firm_slug}-${i}`} match={m} rank={i + 2} testIdPrefix="firm-match-other" />
            ))}
          </div>
        </section>
      )}
      {rejected.length > 0 && (
        <details className="text-[11px] text-zinc-500">
          <summary
            data-testid="firm-match-rejected-toggle"
            className="cursor-pointer hover:text-zinc-300 font-mono uppercase tracking-wider"
          >
            Rejected at prefilter ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-1 pl-4">
            {rejected.map((r, i) => (
              <li key={`${r.firm_slug}-${i}`} className="font-mono">
                <span className="text-zinc-400">{r.firm}</span>
                <span className="text-zinc-600"> · {r.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {meta?.weights && (
        <div className="text-[10px] font-mono text-zinc-600 italic pt-1 border-t border-zinc-900">
          weights: pass {meta.weights.pass_probability} · ev {meta.weights.expected_value} ·
          safety {meta.weights.safety} · stability {meta.weights.stability} ·
          overfit −{meta.weights.overfit_penalty}
        </div>
      )}
    </div>
  );
}

function BestMatchHero({ match }) {
  const v = VERDICT_STYLES[match.verdict] || VERDICT_STYLES.RISKY;
  const frameCls =
    match.verdict === 'BEST'
      ? 'border-emerald-400/60 bg-gradient-to-br from-emerald-950/70 via-zinc-950 to-zinc-900 shadow-[0_0_30px_-10px_rgba(16,185,129,0.35)]'
      : match.verdict === 'SAFE'
      ? 'border-sky-500/50 bg-gradient-to-br from-sky-950/60 via-zinc-950 to-zinc-900'
      : 'border-rose-500/50 bg-gradient-to-br from-rose-950/60 via-zinc-950 to-zinc-900';

  const VerdictIcon = v.Icon;

  return (
    <div
      data-testid="firm-match-best"
      className={`relative border rounded-lg p-4 ${frameCls} transition-all`}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              Best Match · Rank #1
            </span>
            <RiskBadge risk={match.risk} />
          </div>
          <h3 className="text-lg font-bold text-white truncate" data-testid="firm-match-best-firm">
            {match.firm}
          </h3>
          <p className="text-xs font-mono text-zinc-400" data-testid="firm-match-best-plan">
            {match.plan}
          </p>
        </div>
        <div
          data-testid={`firm-match-best-verdict-${match.verdict}`}
          className={`inline-flex items-center gap-1.5 border rounded-full px-3 py-1 text-[10px] font-mono uppercase tracking-widest ${v.c}`}
        >
          <VerdictIcon size={12} weight="bold" />
          {match.verdict}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat
          icon={<Gauge size={11} weight="bold" />}
          label="Score"
          value={match.score.toFixed(1)}
          tone="white"
          testId="firm-match-best-score"
        />
        <Stat
          icon={<TrendUp size={11} weight="bold" />}
          label="Pass Probability"
          value={`${Math.round(match.pass_probability)}%`}
          tone="emerald"
          testId="firm-match-best-pass"
        />
        <Stat
          icon={<Coins size={11} weight="bold" />}
          label="Expected Value"
          value={`${match.expected_value >= 0 ? '+' : ''}$${match.expected_value.toFixed(0)}`}
          tone={match.expected_value >= 0 ? 'emerald' : 'rose'}
          testId="firm-match-best-ev"
        />
        <Stat
          icon={<ShieldCheck size={11} weight="bold" />}
          label="Risk"
          value={match.risk}
          tone={match.risk === 'LOW' ? 'emerald' : match.risk === 'MEDIUM' ? 'amber' : 'rose'}
          testId="firm-match-best-risk"
        />
      </div>

      {match.score_components && (
        <div className="mt-3 pt-3 border-t border-white/5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-zinc-500">
          <span>pass: <span className="text-zinc-300">{match.score_components.pass_prob_pts}</span></span>
          <span>ev: <span className="text-zinc-300">{match.score_components.ev_pts}</span></span>
          <span>safety: <span className="text-zinc-300">{match.score_components.safety_pts}</span></span>
          <span>stability: <span className="text-zinc-300">{match.score_components.stability_pts}</span></span>
          {match.score_components.overfit_penalty > 0 && (
            <span className="text-rose-400">overfit: −{match.score_components.overfit_penalty}</span>
          )}
        </div>
      )}

      {(Array.isArray(match.realism_notes) && match.realism_notes.length > 0) || match.challenge_type ? (
        <div
          data-testid={`firm-match-realism-${match.firm_slug}`}
          className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] font-mono text-zinc-500"
          title={[
            match.firm_strictness && `Firm: ${match.firm_strictness}`,
            match.challenge_type_label && `Type: ${match.challenge_type_label}`,
            typeof match.pass_probability_raw === 'number' &&
              `Raw prob: ${match.pass_probability_raw}% → ${match.pass_probability}%`,
            typeof match.expected_value_raw === 'number' &&
              `Raw EV: $${match.expected_value_raw} → $${match.expected_value}`,
          ].filter(Boolean).join('\n')}
        >
          <span className="text-zinc-400">realism:</span>
          {match.challenge_type && (
            <span className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-zinc-300">
              {match.challenge_type}
            </span>
          )}
          {(match.realism_notes || []).map((n, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-300">
              {n}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Stat({ icon, label, value, tone = 'white', testId }) {
  const toneCls = {
    white: 'text-white',
    emerald: 'text-emerald-300',
    amber: 'text-amber-300',
    rose: 'text-rose-300',
  }[tone] || 'text-white';
  return (
    <div data-testid={testId} className="min-w-0">
      <div className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-wider text-zinc-500 mb-0.5">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className={`text-base font-bold font-mono ${toneCls}`}>{value}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Row for compact / other-matches lists
// ═══════════════════════════════════════════════════════════════════

function MatchRow({ match, rank, testIdPrefix }) {
  const toneCls = {
    BEST:  'border-emerald-500/40 bg-emerald-950/30',
    SAFE:  'border-sky-500/30 bg-sky-950/20',
    RISKY: 'border-rose-500/30 bg-rose-950/20',
  }[match.verdict] || 'border-zinc-800 bg-zinc-900/40';

  return (
    <div
      data-testid={`${testIdPrefix}-row-${rank - 2}`}
      className={`flex items-center justify-between gap-2 border rounded px-3 py-2 ${toneCls}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[10px] font-mono text-zinc-500 w-6 flex-shrink-0">#{rank}</span>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-white truncate">{match.firm}</p>
          <p className="text-[10px] font-mono text-zinc-500 truncate">{match.plan}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-[10px] font-mono text-zinc-400">{match.score.toFixed(1)}</span>
        <span className="text-[10px] font-mono text-emerald-400">{Math.round(match.pass_probability)}%</span>
        <span
          className={`text-[10px] font-mono ${
            match.expected_value >= 0 ? 'text-emerald-400' : 'text-rose-400'
          } hidden sm:inline`}
        >
          {match.expected_value >= 0 ? '+' : ''}${match.expected_value.toFixed(0)}
        </span>
        <RiskBadge risk={match.risk} />
        <VerdictBadge verdict={match.verdict} />
      </div>
    </div>
  );
}

function CompactList({ matches }) {
  const [best, ...rest] = matches;
  const top = rest.slice(0, 3);
  return (
    <div data-testid="firm-match-compact-list" className="space-y-1.5">
      <BestMatchHero match={best} />
      {top.map((m, i) => (
        <MatchRow key={`${m.firm_slug}-${i}`} match={m} rank={i + 2} testIdPrefix="firm-match-compact" />
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Badges
// ═══════════════════════════════════════════════════════════════════

const RISK_STYLES = {
  LOW:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  MEDIUM: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  HIGH:   'bg-red-500/15 text-red-300 border-red-500/40',
};

function RiskBadge({ risk }) {
  const cls = RISK_STYLES[risk] || RISK_STYLES.HIGH;
  return (
    <span
      data-testid={`firm-match-risk-${risk}`}
      className={`inline-block text-[9px] font-mono uppercase tracking-wider border rounded px-1.5 py-0.5 ${cls}`}
    >
      {risk}
    </span>
  );
}

const VERDICT_STYLES = {
  BEST:  { c: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50', Icon: Trophy,      label: 'BEST' },
  SAFE:  { c: 'bg-sky-500/15 text-sky-300 border-sky-500/40',             Icon: ShieldCheck, label: 'SAFE' },
  RISKY: { c: 'bg-rose-500/15 text-rose-300 border-rose-500/40',          Icon: Warning,     label: 'RISKY' },
};

function VerdictBadge({ verdict }) {
  const s = VERDICT_STYLES[verdict] || {
    c: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/40',
    Icon: XCircle,
    label: verdict || '—',
  };
  const Icon = s.Icon;
  return (
    <span
      data-testid={`firm-match-verdict-${verdict}`}
      className={`inline-flex items-center gap-1 text-[9px] font-mono uppercase tracking-wider border rounded px-1.5 py-0.5 ${s.c}`}
    >
      <Icon size={10} weight="bold" />
      {s.label}
    </span>
  );
}
