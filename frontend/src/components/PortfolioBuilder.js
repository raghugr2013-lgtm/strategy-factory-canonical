import React, { useCallback, useEffect, useState } from 'react';
import {
  ChartPieSlice, Spinner, Lightning, Shield, FloppyDisk,
  ArrowsClockwise, Globe, Trophy, Scales,
} from '@phosphor-icons/react';
import {
  buildPortfolioBuilder,
  savePortfolioBuilder,
  getPortfolioBuilderRecent,
} from '../services/api';
import { AsfKpiTile, AsfEmptyState, VerdictChip } from './ui-asf';

/**
 * Phase 4 — Portfolio Builder.
 *
 * Consumes the Phase-3 Auto Selection pool and assembles a diversified
 * 3–5 strategy portfolio with normalised risk allocation + combined
 * metrics. Additive; the existing Phase-7 Portfolio tab is untouched.
 */

const DEFAULT_FILTERS = {
  pool_size: 10,
  target_min: 3,
  target_max: 5,
  min_pass_probability: 60,
  min_env_confidence: 0.7,
  min_match_score: 0.8,
  allow_risky: false,
  total_risk_cap: 3.0,
  max_same_type: 2,
  run_missing_matches: true,
};

function fmt(n, d = 2) {
  if (n === null || n === undefined) return '—';
  return typeof n === 'number' ? n.toFixed(d) : String(n);
}

function StatusPill({ status }) {
  const verdict =
    status === 'PASS'  ? 'success' :
    status === 'RISKY' ? 'warn'    :
    status === 'FAIL'  ? 'danger'  : 'neutral';
  return <VerdictChip verdict={verdict} label={status || '—'} testId="portfolio-status-pill" />;
}

function MetricCard({ label, value, accent = 'zinc', suffix = '', testId }) {
  const cls = {
    zinc: 'text-zinc-100',
    primary: 'text-accent-primary',
    emerald: 'text-emerald-300',
    yellow: 'text-yellow-300',
    red: 'text-red-300',
  }[accent] || 'text-zinc-100';
  return (
    <div
      data-testid={testId}
      className="rounded border border-zinc-800 bg-[#121821] px-4 py-3"
    >
      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</p>
      <p className={`text-xl font-bold mt-1 tabular-nums ${cls}`}>
        {value}
        {suffix && <span className="text-xs font-mono text-zinc-500 ml-1">{suffix}</span>}
      </p>
    </div>
  );
}

function AllocationBar({ weight, color = 'bg-accent-primary' }) {
  const pct = Math.max(0, Math.min(100, (weight || 0) * 100));
  return (
    <div className="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function PortfolioBuilder() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [recent, setRecent] = useState([]);
  const [toast, setToast] = useState(null);

  const pushToast = (msg, kind = 'ok') => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  const build = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await buildPortfolioBuilder(filters);
      setData(res);
    } catch (e) {
      setError(e.message || 'Portfolio build failed');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadRecent = useCallback(async () => {
    try {
      const r = await getPortfolioBuilderRecent(5);
      setRecent(r.portfolios || []);
    } catch { /* non-blocking */ }
  }, []);

  useEffect(() => { loadRecent(); }, [loadRecent]);

  const handleSave = async () => {
    if (!data || !data.strategies || data.strategies.length === 0) return;
    setSaving(true);
    try {
      const res = await savePortfolioBuilder(data);
      pushToast(`Portfolio saved: ${res.portfolio_id?.slice(0, 19) || 'ok'}`, 'ok');
      await loadRecent();
    } catch (e) {
      pushToast(`Save failed: ${e.message}`, 'err');
    } finally {
      setSaving(false);
    }
  };

  const strategies = data?.strategies || [];
  const allocation = data?.allocation || {};
  const canSave = strategies.length > 0 && data?.status === 'ok';

  return (
    <div className="asf-section asf-u2-panel space-y-5" data-testid="portfolio-builder">
      {/* Header */}
      <div className="asf-section__hd flex items-center justify-between flex-wrap gap-3">
        <div className="asf-legacy-title">
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <ChartPieSlice size={20} className="text-accent-primary" weight="bold" />
            Portfolio Builder
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            Assembles a 3–5 strategy portfolio from the Auto Selection pool.
            Enforces pass %, env confidence, and match-score gates; diversifies
            by pair, timeframe &amp; style; normalises <code className="text-zinc-300">safe_risk</code> across
            a total risk cap.
          </p>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2">
          <button
            data-testid="portfolio-regenerate-btn"
            onClick={build}
            disabled={loading}
            className="text-xs font-semibold px-3 py-2 rounded border border-zinc-700 hover:border-zinc-500 text-zinc-300 bg-[#0B0F14] disabled:opacity-50 flex items-center gap-2"
            title="Re-run with current filters"
          >
            {loading ? <Spinner size={14} className="animate-spin" /> : <ArrowsClockwise size={14} weight="bold" />}
            Regenerate
          </button>
          <button
            data-testid="portfolio-build-btn"
            onClick={build}
            disabled={loading}
            className="text-xs font-semibold px-4 py-2 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? <Spinner size={14} className="animate-spin" /> : <Lightning size={14} weight="bold" />}
            Build Portfolio
          </button>
          <button
            data-testid="portfolio-save-btn"
            onClick={handleSave}
            disabled={!canSave || saving}
            className="text-xs font-semibold px-3 py-2 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-40 flex items-center gap-2"
            title={canSave ? 'Save snapshot' : 'Build a valid portfolio first'}
          >
            {saving ? <Spinner size={14} className="animate-spin" /> : <FloppyDisk size={14} weight="bold" />}
            Save
          </button>
        </div>
      </div>

      {/* Filters */}
      <div
        className="rounded-md border border-zinc-800 bg-[#121821] p-3 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3"
        data-testid="portfolio-filters"
      >
        {[
          ['pool_size', 'Pool N', 1, 2, 50],
          ['target_max', 'Target Size', 1, 1, 10],
          ['min_pass_probability', 'Min Pass %', 1, 0, 100],
          ['min_env_confidence', 'Min Env Conf', 0.05, 0, 1],
          ['min_match_score', 'Min Match', 0.05, -1, 2],
          ['total_risk_cap', 'Risk Cap %', 0.1, 0.5, 10],
        ].map(([key, label, step, mn, mx]) => (
          <label key={key} className="flex flex-col gap-1">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
            <input
              data-testid={`portfolio-filter-${key}`}
              type="number"
              step={step}
              min={mn}
              max={mx}
              value={filters[key]}
              onChange={(e) => setFilters((f) => ({ ...f, [key]: Number(e.target.value) }))}
              className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 tabular-nums focus:outline-none focus:border-accent-primary/40"
            />
          </label>
        ))}
        <label className="flex items-center gap-2 text-[10px] font-mono text-zinc-400 cursor-pointer pt-4 col-span-2 md:col-span-1">
          <input
            data-testid="portfolio-allow-risky"
            type="checkbox"
            checked={filters.allow_risky}
            onChange={(e) => setFilters((f) => ({ ...f, allow_risky: e.target.checked }))}
            className="accent-accent-primary"
          />
          Include RISKY
        </label>
      </div>

      {error && (
        <AsfEmptyState
          slug="portfolio-error"
          testId="portfolio-error"
          title="Portfolio build failed"
          body={error}
          action={{ label: 'Retry', onClick: build, testId: 'portfolio-error-retry' }}
        />
      )}

      {/* Pipeline funnel */}
      {data && (
        <div
          className="asf-kpi-grid"
          data-testid="portfolio-funnel"
        >
          <AsfKpiTile label="Pool"          value={data.pool_size ?? 0}        verdict="neutral" testId="portfolio-funnel-pool" />
          <AsfKpiTile label="After Filters" value={data.filtered_count ?? 0}   verdict="neutral" testId="portfolio-funnel-filtered" />
          <AsfKpiTile label="Diversified"   value={data.diversified_count ?? 0} verdict="neutral" testId="portfolio-funnel-diversified" />
          <AsfKpiTile label="Selected"      value={data.selected_count ?? 0}   verdict="info"    testId="portfolio-funnel-selected" />
          <AsfKpiTile
            label="Built At"
            value={data.built_at ? new Date(data.built_at).toLocaleTimeString() : '—'}
            verdict="neutral"
            testId="portfolio-funnel-built-at"
          />
        </div>
      )}

      {/* Insufficient candidates banner */}
      {data && data.status === 'insufficient_candidates' && (
        <AsfEmptyState
          slug="portfolio-insufficient"
          testId="portfolio-insufficient"
          title={`Only ${data.selected_count} strategies survived the filters (need ≥ ${filters.target_min})`}
          body="Loosen the gates (Min Pass %, Min Env Conf, Min Match) or enable Include RISKY, then rebuild."
        />
      )}

      {/* Combined metrics */}
      {data && strategies.length > 0 && (
        <div
          className="grid grid-cols-2 md:grid-cols-5 gap-3"
          data-testid="portfolio-metrics"
        >
          <MetricCard
            label="Expected PF"
            value={fmt(data.expected_pf)}
            accent={data.expected_pf >= 1.3 ? 'emerald' : 'yellow'}
            testId="portfolio-metric-pf"
          />
          <MetricCard
            label="Combined DD (est)"
            value={fmt(data.expected_dd, 2)}
            suffix="%"
            accent={data.expected_dd <= 4 ? 'emerald' : 'yellow'}
            testId="portfolio-metric-dd"
          />
          <MetricCard
            label="Pass Probability"
            value={fmt(data.pass_probability, 1)}
            suffix="%"
            accent={data.pass_probability >= 65 ? 'emerald' : data.pass_probability >= 50 ? 'yellow' : 'red'}
            testId="portfolio-metric-pp"
          />
          <MetricCard
            label="Stability"
            value={fmt(data.stability_score, 2)}
            testId="portfolio-metric-stability"
          />
          <MetricCard
            label="Diversification"
            value={fmt(data.diversification_score, 2)}
            accent={data.diversification_score >= 0.7 ? 'emerald' : 'yellow'}
            testId="portfolio-metric-div"
          />
        </div>
      )}

      {/* Strategies table */}
      <div
        className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden"
        data-testid="portfolio-strategies"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <tr>
                <th className="text-left px-3 py-2.5">#</th>
                <th className="text-left px-3 py-2.5">Strategy</th>
                <th className="text-left px-3 py-2.5">Environment</th>
                <th className="text-left px-3 py-2.5">Firm · Challenge</th>
                <th className="text-left px-3 py-2.5">Status</th>
                <th className="text-right px-3 py-2.5">Pass %</th>
                <th className="text-right px-3 py-2.5">Match</th>
                <th className="text-right px-3 py-2.5">Safe Risk</th>
                <th className="text-left px-3 py-2.5">Allocation</th>
                <th className="text-right px-3 py-2.5">Risk %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loading && strategies.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-10 text-center text-zinc-500 font-mono">
                    <Spinner size={14} className="animate-spin inline mr-2" /> Building…
                  </td>
                </tr>
              )}
              {!loading && !data && (
                <tr>
                  <td
                    colSpan={10}
                    className="px-3 py-8 text-center text-zinc-500 font-mono text-xs"
                    data-testid="portfolio-empty"
                  >
                    Click <strong>Build Portfolio</strong> to assemble a diversified
                    deploy-ready bundle from the Auto Selection pool.
                  </td>
                </tr>
              )}
              {!loading && data && strategies.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-10 text-center text-zinc-500 font-mono">
                    No strategies survived the filters. Loosen the thresholds and
                    try again.
                  </td>
                </tr>
              )}
              {strategies.map((s, i) => {
                const a = allocation[s.strategy_hash] || {};
                return (
                  <tr
                    key={s.strategy_hash}
                    data-testid={`portfolio-row-${s.strategy_hash}`}
                    className="hover:bg-zinc-900/40 transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-zinc-500 tabular-nums">#{i + 1}</td>
                    <td className="px-3 py-2">
                      <p className="font-medium text-zinc-200">{s.strategy_name || '—'}</p>
                      <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                        {s.type || '—'} · PF {fmt(s.strategy_best_pf)} · stab {fmt(s.strategy_stability)}
                      </p>
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 font-mono text-xs text-zinc-200">
                        <Globe size={11} className="text-accent-primary" />
                        {s.pair} · {s.timeframe}
                      </span>
                      <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                        conf {fmt(s.env_confidence)}
                      </p>
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 font-mono text-xs text-zinc-200">
                        <Trophy size={11} className="text-yellow-400" />
                        {s.firm_name || s.firm_slug}
                      </span>
                      <p className="text-[9px] font-mono text-zinc-500 mt-0.5">{s.challenge}</p>
                    </td>
                    <td className="px-3 py-2"><StatusPill status={s.status} /></td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-200 tabular-nums">
                      {fmt(s.pass_probability, 1)}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-zinc-300 tabular-nums">
                      {fmt(s.match_score, 3)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="inline-flex items-center gap-1 text-[10px] font-mono">
                        <Shield size={10} className="text-accent-primary" />
                        <span className="text-zinc-200 tabular-nums">{fmt(s.safe_risk)}%</span>
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <AllocationBar weight={a.weight} />
                        <span className="text-[10px] font-mono text-zinc-300 tabular-nums">
                          {a.weight !== undefined ? `${(a.weight * 100).toFixed(1)}%` : '—'}
                        </span>
                      </div>
                    </td>
                    <td
                      className="px-3 py-2 text-right font-mono tabular-nums text-accent-primary"
                      data-testid={`portfolio-risk-${s.strategy_hash}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        <Scales size={10} />
                        {a.risk_pct !== undefined ? `${fmt(a.risk_pct, 2)}%` : '—'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {strategies.length > 0 && (
                <tr className="bg-zinc-900/40">
                  <td
                    colSpan={8}
                    className="px-3 py-2 text-right text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500"
                  >
                    Total risk cap
                  </td>
                  <td />
                  <td
                    data-testid="portfolio-total-risk"
                    className="px-3 py-2 text-right font-mono font-bold text-accent-primary tabular-nums"
                  >
                    {fmt(data?.total_risk, 2)}%
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent saves */}
      {recent.length > 0 && (
        <div
          className="rounded-md border border-zinc-800 bg-[#121821] p-3"
          data-testid="portfolio-recent"
        >
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2">
            Recent saved portfolios
          </p>
          <ul className="space-y-1 text-[11px] font-mono text-zinc-400">
            {recent.map((r) => {
              const meta = r.meta || {};
              return (
                <li
                  key={r.portfolio_id}
                  className="flex items-center justify-between px-2 py-1 rounded bg-zinc-900/40"
                >
                  <span>{new Date(r.saved_at).toLocaleString()}</span>
                  <span>
                    <span className="text-zinc-200">{meta.selected_count ?? '—'}</span> strat ·
                    PF <span className="text-zinc-200">{fmt(meta.expected_pf)}</span> ·
                    Pass <span className="text-zinc-200">{fmt(meta.pass_probability, 1)}%</span> ·
                    DD <span className="text-zinc-200">{fmt(meta.expected_dd, 2)}%</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {toast && (
        <div
          data-testid="portfolio-toast"
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
