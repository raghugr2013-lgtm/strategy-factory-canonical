import React, { useEffect, useState } from 'react';
import { X, Spinner, Info, ChartLineUp } from '@phosphor-icons/react';
import { getStrategyDetails } from '../services/api';

/**
 * Phase 24 — Strategy Explorer Details Drawer.
 *
 * Cached, research-grade view. NO backtest re-run during open.
 * Expensive visuals (equity curve, monthly heat-map, trade distribution)
 * surface as "click to compute" stubs and are only triggered on explicit
 * user action.
 */
export default function StrategyDetailsPanel({ strategyId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!strategyId) return;
    let live = true;
    setLoading(true);
    setError(null);
    setData(null);
    getStrategyDetails(strategyId)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(e.message || 'failed to load details'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [strategyId]);

  if (!strategyId) return null;
  return (
    <div
      data-testid="strategy-details-overlay"
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        data-testid="strategy-details-drawer"
        className="w-full md:w-[760px] h-full bg-[#0B0F14] border-l border-zinc-800 shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 sticky top-0 bg-[#0B0F14] z-10">
          <div className="min-w-0">
            <h3 className="text-sm font-mono font-semibold text-zinc-100 truncate">
              {data?.name || 'Strategy details'}
            </h3>
            <p className="text-[10px] font-mono text-zinc-500 truncate">
              {data?.pair || '—'} · {data?.timeframe || '—'} · {data?.style || '—'}
              {data?.fingerprint && ` · ${data.fingerprint.slice(0, 10)}…`}
            </p>
          </div>
          <button
            type="button"
            data-testid="strategy-details-close"
            onClick={onClose}
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60"
          >
            <X size={16} />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16">
            <Spinner size={20} className="animate-spin text-zinc-500" />
          </div>
        )}
        {error && !loading && (
          <div className="m-4 px-3 py-2 rounded border border-red-500/30 bg-red-500/10 text-[11px] font-mono text-red-300">
            {error}
          </div>
        )}

        {!loading && data && (
          <div className="p-4 space-y-4">
            <ValidationSummary v={data.validation} />
            <BehaviorCard v={data.validation} />
            <WinLossCard v={data.validation} />
            <StreakCard v={data.validation} />
            <SmoothnessCard v={data.validation} />
            <IsOosCard cmp={data.is_oos_comparison} />
            <ExpectancyCard ev={data.expectancy_breakdown} />
            <PassProbabilityCard reasoning={data.pass_probability_reasoning} panel={data.prop_firm_panel} />
            <PfHistoryCard history={data.history} />
            <LineageCard strategyHash={data.strategy_hash || data.fingerprint} />
            <ClickToComputeCard visuals={data.computed_visuals} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Sub-cards ────────────────────────────────────────────────────────

const STAGE_COLORS = {
  // Legacy 4-stage ladder (still emitted by `validation.stage`).
  exploratory:      'border-zinc-600 text-zinc-300 bg-zinc-800/40',
  candidate:        'border-sky-500/40 text-sky-300 bg-sky-500/10',
  validated:        'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
  prop_safe:        'border-amber-400/40 text-amber-300 bg-amber-400/10',
  // Phase 26.5 / 27.2 — new lifecycle stages above PROP_SAFE.
  stable:           'border-emerald-600/50 text-emerald-200 bg-emerald-600/10',
  elite:            'border-violet-500/40 text-violet-300 bg-violet-500/10',
  portfolio_worthy: 'border-violet-400/60 text-violet-200 bg-violet-500/15',
  deployment_ready: 'border-yellow-400/60 text-yellow-200 bg-yellow-500/15',
};

// Phase 27.2 / G6 — bridge tooltip mapping. Helps operators familiar
// with the legacy 4-stage chip understand how the new 8-stage ladder
// extends it. Kept terse — every phrase fits on one line.
const STAGE_TOOLTIPS = {
  exploratory:      'No library entry yet OR fewer than 3 runs recorded.',
  candidate:        'Library-saved · ≥3 runs · IS PF ≥ 1.2 · ≥30 trades.',
  validated:        'Candidate + OOS ratio ≥ 0.7 · stability ≥ 60.',
  stable:           'Validated + ≥5 runs cross-run-consistent · behavior classified. (NEW)',
  prop_safe:        'Stable + DD < 5% · pass-prob ≥ 60% · smoothness OK.',
  elite:            'Prop-safe + deploy_score ≥ p90 · ≥2 regimes · recovery ≥ 1.5. (NEW)',
  portfolio_worthy: 'Elite + member of an active portfolio + verified-firm match. (NEW)',
  deployment_ready: 'Portfolio-worthy + BI5 realism ≥ 0.75 + cBot compiles + risk locked. (TERMINAL · NEW)',
};

const BADGE_TONE = {
  LOW_SAMPLE:   'border-amber-500/40 text-amber-300 bg-amber-500/10',
  OOS_WEAK:     'border-amber-500/40 text-amber-300 bg-amber-500/10',
  OVERFIT_RISK: 'border-red-500/40 text-red-300 bg-red-500/10',
  HIGH_DD:      'border-red-500/40 text-red-300 bg-red-500/10',
  STABLE:       'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
  PROP_SAFE:    'border-amber-400/40 text-amber-300 bg-amber-400/10',
  SMOOTH:       'border-sky-500/40 text-sky-300 bg-sky-500/10',
  VOLATILE:     'border-orange-500/40 text-orange-300 bg-orange-500/10',
};

const BEHAVIOR_INFO = {
  HIGH_WINRATE_SCALPER: {
    label: 'High-winrate scalper',
    tone: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
    note: 'Frequent small-RR trades. Watch for sudden big losses that wipe many small wins.',
  },
  TREND_FOLLOWER: {
    label: 'Trend follower',
    tone: 'border-sky-500/40 text-sky-300 bg-sky-500/10',
    note: 'Lower win-rate but RR ≥ 1.5. Long, slow grind with periodic wins.',
  },
  MEAN_REVERSION: {
    label: 'Mean reversion',
    tone: 'border-violet-500/40 text-violet-300 bg-violet-500/10',
    note: 'High win-rate, low RR. Performs in ranging regimes; struggles in strong trends.',
  },
  ASYMMETRIC_BREAKOUT: {
    label: 'Asymmetric breakout',
    tone: 'border-amber-500/40 text-amber-300 bg-amber-500/10',
    note: 'Low win-rate, very high RR. Long losing streaks expected — psychological discipline matters.',
  },
  LOW_FREQ_SWING: {
    label: 'Low-frequency swing',
    tone: 'border-cyan-500/40 text-cyan-300 bg-cyan-500/10',
    note: 'Few but selective trades. Sample-size risk — validate with extended OOS.',
  },
  BALANCED: {
    label: 'Balanced',
    tone: 'border-zinc-600 text-zinc-300 bg-zinc-800/40',
    note: 'No dominant behavioral signature.',
  },
  UNCLASSIFIED: {
    label: 'Unclassified',
    tone: 'border-zinc-600 text-zinc-300 bg-zinc-800/40',
    note: 'Not enough cached data to classify.',
  },
};

export function StageBadge({ stage, lifecycleStage }) {
  // Phase 27.2 / G6 — prefer the new 8-stage `lifecycleStage` when
  // present, fall back to the legacy 4-stage `stage` so any pre-G6
  // caller continues to render the same chip it used before.
  const effective = lifecycleStage || stage;
  if (!effective) return null;
  const tone = STAGE_COLORS[effective] || STAGE_COLORS.exploratory;
  const tooltip = STAGE_TOOLTIPS[effective] || effective.replace('_', ' ');
  return (
    <span
      data-testid={`strategy-stage-${effective}`}
      title={tooltip}
      className={`inline-flex items-center text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${tone}`}
    >
      {effective.replace(/_/g, ' ')}
    </span>
  );
}

export function ValidationBadges({ badges }) {
  if (!badges || badges.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b) => (
        <span
          key={b}
          data-testid={`strategy-badge-${b}`}
          className={`inline-flex items-center text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border ${BADGE_TONE[b] || 'border-zinc-600 text-zinc-300 bg-zinc-800/40'}`}
        >
          {b}
        </span>
      ))}
    </div>
  );
}

// ─── Phase 27.3 / BI5 Realism pill ──────────────────────────────────
// Tiny inline indicator next to the StageBadge. Reads the persisted
// `validation.bi5_realism` block plus `validation.lifecycle_flags` so
// it can show the four operator-relevant states without any new
// dashboard or API roundtrip:
//
//   • OK             →  "BI5 0.82 ✓"   (emerald)
//   • PARTIAL        →  "BI5 0.62 ⚠"   (amber)
//   • FAIL           →  "BI5 0.40 ✗"   (red)
//   • NOT VERIFIED   →  "BI5 not verified"  (zinc, BI5_DATA_MISSING flag)
//   • absent         →  null (don't render anything)
//
// Lives inline in Validation header to honour the "no UI proliferation"
// constraint — a single span, no card, no modal, no extra tab.
export function Bi5RealismPill({ realism, flags }) {
  const flagSet = new Set(flags || []);
  const dataMissing = flagSet.has('BI5_DATA_MISSING');
  const r = realism || {};
  const status = r.status || (dataMissing ? 'data_missing' : null);
  if (!status) return null;

  let label;
  let tone;
  let testStatus = status;
  switch (status) {
    case 'ok':
      tone = 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10';
      label = `BI5 ${(r.pf_ratio ?? 0).toFixed(2)} ✓`;
      break;
    case 'partial':
      tone = 'border-amber-500/40 text-amber-300 bg-amber-500/10';
      label = `BI5 ${(r.pf_ratio ?? 0).toFixed(2)} ⚠`;
      break;
    case 'fail':
      tone = 'border-red-500/40 text-red-300 bg-red-500/10';
      label = `BI5 ${(r.pf_ratio ?? 0).toFixed(2)} ✗`;
      break;
    case 'data_missing':
      tone = 'border-zinc-600 text-zinc-400 bg-zinc-800/40';
      label = 'BI5 not verified';
      testStatus = 'data_missing';
      break;
    case 'fresh_cache':
      // Treat fresh_cache the same way as the underlying status —
      // when the persisted block is fresh we already rendered the
      // appropriate pill via the actual pf_ratio above. This branch
      // only fires if the block was last persisted as fresh_cache,
      // which shouldn't happen with the current implementation.
      tone = 'border-zinc-600 text-zinc-400 bg-zinc-800/40';
      label = 'BI5 cached';
      break;
    default:
      // Unknown status — render zinc neutral so we never silently
      // hide a state the operator might need to see.
      tone = 'border-zinc-600 text-zinc-400 bg-zinc-800/40';
      label = `BI5 ${status}`;
      break;
  }
  const tooltip = (() => {
    if (status === 'data_missing') {
      return 'BI5 tick data is not loaded for this strategy\'s pair/timeframe. Upload BI5 chunks to enable realism certification.';
    }
    if (r.bi5_pf != null && r.cached_pf != null) {
      return `bi5_pf=${(+r.bi5_pf).toFixed(2)} / cached_pf=${(+r.cached_pf).toFixed(2)} = ratio ${(r.pf_ratio ?? 0).toFixed(2)} (last checked ${(r.last_checked_at || '').slice(0, 10)})`;
    }
    return `BI5 realism status: ${status}`;
  })();
  return (
    <span
      data-testid={`bi5-realism-${testStatus}`}
      title={tooltip}
      className={`inline-flex items-center text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${tone}`}
    >
      {label}
    </span>
  );
}

function ValidationSummary({ v }) {
  if (!v) return null;
  const m = v.metrics || {};
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Validation</span>
        <div className="flex items-center gap-1.5">
          <Bi5RealismPill realism={v.bi5_realism} flags={v.lifecycle_flags} />
          <StageBadge stage={v.stage} lifecycleStage={v.lifecycle_stage} />
        </div>
      </div>
      <p className="text-[12px] font-mono text-zinc-200 mb-2">{v.confidence_summary}</p>
      <ValidationBadges badges={v.badges} />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 mt-3 text-[11px] font-mono">
        <Stat label="Total trades"   value={fmtInt(m.total_trades)} />
        <Stat label="IS PF"          value={fmt(m.is_pf, 2)} />
        <Stat label="OOS PF"         value={fmt(m.oos_pf, 2)} />
        <Stat label="OOS ratio"      value={fmt(m.oos_ratio, 2)} />
        <Stat label="Max DD"         value={fmtPct(m.max_drawdown_pct, 1)} />
        <Stat label="Win rate"       value={fmtPct(m.win_rate / 100, 1)} />
        <Stat label="Expectancy"     value={fmt(m.expectancy, 2)} />
        <Stat label="Avg trade %"    value={fmt(m.avg_trade_pct, 3)} />
        <Stat label="Stability"      value={fmt(m.stability_score, 1)} />
        <Stat label="Pass prob"      value={m.pass_probability_pct != null ? `${m.pass_probability_pct.toFixed(1)}%` : '—'} />
        <Stat label="R:R"            value={fmt(m.risk_reward_ratio, 2)} />
        <Stat label="Total return %" value={fmt(m.total_return_pct, 2)} />
      </div>
    </div>
  );
}

// ─── Phase 25 — Behavioral transparency cards ────────────────────────

function BehaviorCard({ v }) {
  const m = v?.metrics || {};
  const profile = m.behavioral_profile;
  if (!profile) return null;
  const info = BEHAVIOR_INFO[profile] || BEHAVIOR_INFO.UNCLASSIFIED;
  return (
    <div
      data-testid="behavior-card"
      className="rounded border border-zinc-800 bg-zinc-900/40 p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Behavioral Profile
        </span>
        <span
          data-testid={`behavior-profile-${profile}`}
          className={`inline-flex items-center text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border ${info.tone}`}
        >
          {info.label}
        </span>
      </div>
      <p className="text-[11px] font-mono text-zinc-300 leading-relaxed">
        {info.note}
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 mt-3 text-[11px] font-mono">
        <Stat label="Win rate"      value={m.win_rate != null ? `${Number(m.win_rate).toFixed(1)}%` : '—'} />
        <Stat label="R:R"           value={fmt(m.risk_reward_ratio, 2)} />
        <Stat label="Total trades"  value={fmtInt(m.total_trades)} />
      </div>
    </div>
  );
}

function WinLossCard({ v }) {
  const m = v?.metrics || {};
  if (m.wins == null && m.losses == null && m.avg_win == null && m.avg_loss == null) {
    return null;
  }
  const total = (m.wins || 0) + (m.losses || 0);
  const winPct = total > 0 ? ((m.wins || 0) / total) * 100 : null;
  return (
    <div
      data-testid="winloss-card"
      className="rounded border border-zinc-800 bg-zinc-900/40 p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Win / Loss Profile
        </span>
        {winPct != null && (
          <span className="text-[10px] font-mono text-zinc-400 tabular-nums">
            {winPct.toFixed(1)}% wins
          </span>
        )}
      </div>
      {winPct != null && (
        <div className="flex h-1.5 rounded-full overflow-hidden bg-zinc-800 mb-3" data-testid="winloss-bar">
          <div className="bg-emerald-400/80" style={{ width: `${winPct}%` }} />
          <div className="bg-red-400/70" style={{ width: `${100 - winPct}%` }} />
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1.5 text-[11px] font-mono">
        <Stat label="Wins"     value={m.wins != null ? Number(m.wins).toLocaleString() : '—'} />
        <Stat label="Losses"   value={m.losses != null ? Number(m.losses).toLocaleString() : '—'} />
        <Stat label="Avg win"  value={m.avg_win != null ? fmt(m.avg_win, 2) : '—'} />
        <Stat label="Avg loss" value={m.avg_loss != null ? fmt(m.avg_loss, 2) : '—'} />
      </div>
    </div>
  );
}

function StreakCard({ v }) {
  const m = v?.metrics || {};
  if (
    m.expected_max_consec_losses == null
    && m.avg_consec_losses == null
    && m.recovery_factor == null
  ) {
    return null;
  }
  const exp = m.expected_max_consec_losses;
  const expTone =
    exp == null ? 'zinc'
    : exp >= 8 ? 'bad'
    : exp >= 5 ? 'warn'
    : 'good';
  const rec = m.recovery_factor;
  const recTone =
    rec == null ? 'zinc'
    : rec >= 3 ? 'good'
    : rec >= 1 ? 'warn'
    : 'bad';
  return (
    <div
      data-testid="streak-card"
      className="rounded border border-zinc-800 bg-zinc-900/40 p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Losing Streak Risk
        </span>
        <span className="text-[9px] font-mono text-zinc-600">cached · 95% confidence</span>
      </div>
      <div className="grid grid-cols-3 gap-3 text-[11px] font-mono">
        <Cell
          label="Expected worst run"
          value={exp != null ? `${exp} losses` : '—'}
          tone={expTone}
        />
        <Cell
          label="Avg consecutive losses"
          value={m.avg_consec_losses != null ? fmt(m.avg_consec_losses, 2) : '—'}
          tone="zinc"
        />
        <Cell
          label="Recovery factor"
          value={rec != null ? fmt(rec, 2) : '—'}
          tone={recTone}
        />
      </div>
      <p className="text-[10px] font-mono text-zinc-500 mt-2">
        Probabilistic estimate from cached win-rate &amp; trade-count — no backtest re-run.
      </p>
    </div>
  );
}

function SmoothnessCard({ v }) {
  const m = v?.metrics || {};
  const label = m.smoothness_label;
  const stab = m.stability_score;
  const dd = m.max_drawdown_pct;
  if (label == null && stab == null && dd == null) return null;
  const tone =
    label === 'SMOOTH' ? 'border-sky-500/40 text-sky-300 bg-sky-500/10'
    : label === 'VOLATILE' ? 'border-orange-500/40 text-orange-300 bg-orange-500/10'
    : 'border-zinc-700 text-zinc-300 bg-zinc-800/40';
  const note =
    label === 'SMOOTH' ? 'Equity curve is consistent — low DD, high stability across runs.'
    : label === 'VOLATILE' ? 'Equity curve shows large swings — expect significant DD episodes.'
    : 'Mixed equity profile — neither uniformly smooth nor volatile.';
  return (
    <div
      data-testid="smoothness-card"
      className="rounded border border-zinc-800 bg-zinc-900/40 p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Equity Smoothness
        </span>
        <span
          data-testid={`smoothness-label-${label || 'mixed'}`}
          className={`inline-flex items-center text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border ${tone}`}
        >
          {label || 'mixed'}
        </span>
      </div>
      <p className="text-[11px] font-mono text-zinc-300 leading-relaxed mb-2">
        {note}
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 text-[11px] font-mono">
        <Stat label="Stability" value={stab != null ? fmt(stab, 1) : '—'} />
        <Stat label="Max DD"    value={dd != null ? `${(dd * 100).toFixed(1)}%` : '—'} />
        <Stat label="Avg trade %" value={fmt(m.avg_trade_pct, 3)} />
      </div>
    </div>
  );
}

// ─── Phase 26 / G1 — Research lineage card ────────────────────────

function LineageCard({ strategyHash }) {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!strategyHash) return;
    let live = true;
    setRuns(null);
    setError(null);
    import('../services/api')
      .then(({ getResearchRunsForStrategy }) =>
        getResearchRunsForStrategy(strategyHash, { limit: 8 }))
      .then((d) => { if (live) setRuns(d.runs || []); })
      .catch((e) => { if (live) setError(e.message || 'lineage fetch failed'); });
    return () => { live = false; };
  }, [strategyHash]);

  if (!strategyHash) return null;
  if (runs === null && !error) {
    return (
      <div data-testid="lineage-card" className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Research Lineage
        </span>
        <p className="text-[11px] font-mono text-zinc-500 mt-2">Loading…</p>
      </div>
    );
  }
  if (error) return null;
  if (!runs.length) {
    return (
      <div data-testid="lineage-card" className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            Research Lineage
          </span>
          <span className="text-[9px] font-mono text-zinc-600">no runs recorded</span>
        </div>
        <p className="text-[11px] font-mono text-zinc-500 leading-relaxed">
          This strategy has no research-run lineage yet. Lineage is recorded for
          all strategies discovered after the G1 release.
        </p>
      </div>
    );
  }
  return (
    <div data-testid="lineage-card" className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Research Lineage
        </span>
        <span className="text-[9px] font-mono text-zinc-600">
          {runs.length} run{runs.length === 1 ? '' : 's'}
        </span>
      </div>
      <ul className="space-y-1.5">
        {runs.map((r) => (
          <li
            key={r.research_run_id}
            data-testid={`lineage-run-${r.research_run_id}`}
            className="flex items-center justify-between gap-2 text-[10px] font-mono"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <TriggerPill type={r.trigger?.type} />
                <span className="text-zinc-300 truncate">
                  {r.research_run_id.replace(/^rr_/, '')}
                </span>
              </div>
              <div className="text-zinc-600 truncate mt-0.5">
                {r.trigger?.rule_id ? `${r.trigger.rule_id} · ` : ''}
                {r.trigger?.reason || '—'}
              </div>
            </div>
            <div className="text-right shrink-0">
              <StatusPill status={r.status} />
              <div className="text-zinc-600 mt-0.5">
                {(r.summary?.strategies_saved ?? 0)}/{(r.summary?.strategies_generated ?? 0)} saved
              </div>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[10px] font-mono text-zinc-600 mt-3">
        Lineage rooted at the orchestrator/scheduler tick that discovered this
        strategy — every cycle, mutation and library save links back to its run.
      </p>
    </div>
  );
}

const TRIGGER_TONE = {
  orchestrator_tick:   'border-violet-500/40 text-violet-300 bg-violet-500/10',
  auto_scheduler_tick: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
  manual_api:          'border-sky-500/40 text-sky-300 bg-sky-500/10',
  manual_rerun:        'border-zinc-600 text-zinc-300 bg-zinc-800/40',
  ingestion:           'border-amber-400/40 text-amber-300 bg-amber-400/10',
  workspace_generate:  'border-zinc-600 text-zinc-300 bg-zinc-800/40',
};

function TriggerPill({ type }) {
  const tone = TRIGGER_TONE[type] || 'border-zinc-700 text-zinc-400 bg-zinc-800/40';
  const label = (type || 'unknown').replace(/_/g, ' ');
  return (
    <span className={`inline-flex items-center text-[8px] font-mono uppercase tracking-wider px-1 py-px rounded border ${tone}`}>
      {label}
    </span>
  );
}

const STATUS_TONE = {
  running:   'text-sky-300',
  completed: 'text-emerald-300',
  stopped:   'text-amber-300',
  error:     'text-red-300',
  timeout:   'text-orange-300',
  skipped:   'text-zinc-500',
};

function StatusPill({ status }) {
  return (
    <span className={`text-[9px] font-mono uppercase tracking-wider ${STATUS_TONE[status] || 'text-zinc-400'}`}>
      {status || '—'}
    </span>
  );
}

function IsOosCard({ cmp }) {
  if (!cmp) return null;
  const overfit = cmp.overfit_flagged;
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">IS vs OOS</span>
        {overfit != null && (
          <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border ${
            overfit
              ? 'border-red-500/40 text-red-300 bg-red-500/10'
              : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
          }`}>
            {overfit ? 'OVERFIT FLAGGED' : 'NO OVERFIT'}
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3 text-[11px] font-mono">
        <Cell label="In-sample PF"   value={fmt(cmp.is_pf, 2)}  tone="zinc" />
        <Cell label="Out-of-sample PF" value={fmt(cmp.oos_pf, 2)} tone="zinc" />
        <Cell label="OOS ratio"      value={fmt(cmp.ratio, 2)}
              tone={ratioTone(cmp.ratio)} />
        <Cell label="Train candles"  value={fmtInt(cmp.train_candles)} tone="zinc" />
        <Cell label="OOS candles"    value={fmtInt(cmp.oos_candles)}   tone="zinc" />
      </div>
    </div>
  );
}

function ExpectancyCard({ ev }) {
  if (!ev) {
    return (
      <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Expectancy</span>
        <p className="text-[11px] font-mono text-zinc-500 mt-1">No expectancy data cached.</p>
      </div>
    );
  }
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Expectancy</span>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 mt-2 text-[11px] font-mono">
        <Stat label="Expected value"   value={fmt(ev.expected_value, 2)} />
        <Stat label="Grade"            value={ev.ev_grade || '—'} />
        <Stat label="Risk : Reward"    value={fmt(ev.risk_reward_ratio, 2)} />
        <Stat label="Breakeven prob"   value={ev.breakeven_probability != null ? `${Number(ev.breakeven_probability).toFixed(1)}%` : '—'} />
        <Stat label="Pass-prob grade"  value={ev.pass_probability_grade || '—'} />
        <Stat label="Pass prob"        value={ev.pass_probability != null ? `${Number(ev.pass_probability).toFixed(1)}%` : '—'} />
      </div>
    </div>
  );
}

function PassProbabilityCard({ reasoning, panel }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center gap-1.5 mb-2">
        <Info size={12} className="text-zinc-500" />
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Pass-Probability Reasoning
        </span>
      </div>
      <ul className="text-[11px] font-mono text-zinc-300 list-disc pl-4 space-y-1">
        {(reasoning || []).map((r, i) => (
          <li key={i} data-testid={`strategy-reasoning-${i}`}>{r}</li>
        ))}
      </ul>
      {panel && Object.keys(panel.violations || {}).length > 0 && (
        <div className="mt-2 text-[10px] font-mono">
          <span className="text-zinc-500 uppercase tracking-wider">Prop violations: </span>
          {Object.entries(panel.violations).map(([k, v]) => (
            <span
              key={k}
              data-testid={`strategy-violation-${k}`}
              className={`inline-block mr-1 px-1.5 py-0.5 rounded border ${
                v
                  ? 'border-red-500/40 text-red-300 bg-red-500/10'
                  : 'border-emerald-500/40 text-emerald-400 bg-emerald-500/5'
              }`}
            >
              {k}: {v ? '✗' : '✓'}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function PfHistoryCard({ history }) {
  if (!history || !history.runs) return null;
  const series = history.pf_series || [];
  if (series.length === 0) return null;
  const pfs = series.map((r) => Number(r.pf || 0));
  const max = Math.max(...pfs, 1);
  const dist = history.trades_per_run_distribution || [];
  const stats = history.stats || {};
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center gap-1.5 mb-2">
        <ChartLineUp size={12} className="text-zinc-500" />
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          PF history · {history.runs} run{history.runs === 1 ? '' : 's'}
        </span>
      </div>
      {/* Inline mini-bars (no chart lib needed). */}
      <div className="flex items-end gap-0.5 h-12 mb-2" data-testid="strategy-pf-history">
        {series.slice(-60).map((r, i) => {
          const h = Math.max(2, (Number(r.pf || 0) / max) * 100);
          const tone = r.pf >= 1.4 ? 'bg-emerald-400'
                     : r.pf >= 1.0 ? 'bg-sky-400'
                     : 'bg-red-400';
          return <div key={i} className={`flex-1 ${tone} rounded-sm`} style={{ height: `${h}%` }} title={`PF ${r.pf?.toFixed?.(2)} · DD ${r.dd_pct?.toFixed?.(1)}% · ${r.regime || '—'}`} />;
        })}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-1 text-[11px] font-mono">
        <Stat label="Best PF"  value={fmt(stats.best_pf, 2)} />
        <Stat label="Avg PF"   value={fmt(stats.avg_pf, 2)} />
        <Stat label="Worst DD" value={fmtPct((stats.worst_dd_pct || 0) / 100, 1)} />
        <Stat label="Avg DD"   value={fmtPct((stats.avg_dd_pct || 0) / 100, 1)} />
      </div>
      {dist.length > 0 && (
        <div className="mt-2">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">Trade-count distribution per run</span>
          <div className="flex items-end gap-1 h-8 mt-1">
            {dist.map((b, i) => (
              <div key={i} className="flex-1 bg-zinc-700 rounded-sm" style={{ height: `${Math.min(100, b.count * 18)}%` }} title={`[${b.from}, ${b.to}): ${b.count}`} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ClickToComputeCard({ visuals }) {
  const items = [
    { key: 'equity_curve',         label: 'Equity curve' },
    { key: 'drawdown_curve',       label: 'Drawdown curve' },
    { key: 'monthly_performance',  label: 'Monthly performance' },
    { key: 'trade_distribution',   label: 'Per-trade distribution' },
  ];
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Expensive visuals</span>
      <p className="text-[10px] font-mono text-zinc-500 mt-1 mb-2">
        Cached only — click to compute (will trigger an on-demand backtest).
      </p>
      <div className="grid grid-cols-2 gap-2">
        {items.map((it) => (
          <button
            key={it.key}
            type="button"
            data-testid={`strategy-compute-${it.key}`}
            disabled
            title="On-demand backtest hook — not yet wired."
            className="text-left text-[11px] font-mono px-2 py-2 rounded border border-zinc-700 bg-zinc-900/40 text-zinc-400 hover:border-zinc-500 hover:text-zinc-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="block text-zinc-200">{it.label}</span>
            <span className="text-[9px] text-zinc-500 uppercase tracking-wider">
              {visuals?.[it.key]?.status || 'cached only'}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────

function Stat({ label, value }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</span>
      <span className="text-zinc-200">{value ?? '—'}</span>
    </div>
  );
}

function Cell({ label, value, tone = 'zinc' }) {
  const cls = {
    zinc:    'border-zinc-700 text-zinc-200 bg-zinc-900/40',
    good:    'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
    warn:    'border-amber-500/40 text-amber-300 bg-amber-500/10',
    bad:     'border-red-500/40 text-red-300 bg-red-500/10',
  }[tone] || 'border-zinc-700 text-zinc-200 bg-zinc-900/40';
  return (
    <div className={`px-2 py-1.5 rounded border ${cls}`}>
      <p className="text-[9px] uppercase tracking-wider opacity-70">{label}</p>
      <p className="text-[12px] font-mono">{value ?? '—'}</p>
    </div>
  );
}

function ratioTone(r) {
  if (r == null) return 'zinc';
  if (r >= 1.0) return 'good';
  if (r >= 0.7) return 'warn';
  return 'bad';
}

function fmt(v, d = 2) {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(d);
}

function fmtInt(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString();
}

function fmtPct(v, d = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Number(v) * 100;
  if (!Number.isFinite(n)) return '—';
  return `${n.toFixed(d)}%`;
}
