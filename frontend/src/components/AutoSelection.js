import React, { useCallback, useEffect, useState } from 'react';
import {
  Crosshair, Trophy, Spinner, Warning, CheckCircle, Globe,
  ShieldCheck, Target, ArrowsClockwise, Lightning, Shield,
} from '@phosphor-icons/react';
import {
  runAutoSelection, getAutoSelectionRecent,
  downloadStrategyCbotByHash, exportStrategyByHash,
} from '../services/api';

/**
 * Phase 3 — Auto Selection Engine UI.
 * Shows deployment-ready (strategy × pair × timeframe × firm × challenge)
 * combinations ranked by a composite deploy_score.
 */

const DEFAULT_FILTERS = {
  top_n: 10,
  min_pf: 1.2,
  min_runs: 3,
  min_stability: 0.5,
  min_pass_probability: 40,
  min_match_score: 0.2,
  min_env_confidence: 0.4,
  pass_only: false,
  run_missing_matches: true,
};

function fmt(n, d = 2) {
  if (n === null || n === undefined) return '—';
  return typeof n === 'number' ? n.toFixed(d) : String(n);
}

function ScoreBar({ value, max = 2 }) {
  if (value === null || value === undefined) return <span className="text-zinc-500 text-[10px]">—</span>;
  const pct = Math.max(0, Math.min(100, (Number(value) / max) * 100));
  const cls = pct >= 60 ? 'bg-emerald-400' : pct >= 30 ? 'bg-yellow-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${cls}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-mono tabular-nums text-zinc-200">{fmt(value)}</span>
    </div>
  );
}

function StatusPill({ status }) {
  const cfg = {
    PASS: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    RISKY: 'bg-yellow-500/10 border-yellow-500/40 text-yellow-300',
    FAIL: 'bg-red-500/10 border-red-500/40 text-red-300',
  };
  return (
    <span className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${cfg[status] || cfg.FAIL}`}>
      {status || '—'}
    </span>
  );
}

export default function AutoSelection() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [recent, setRecent] = useState([]);
  const [busyExport, setBusyExport] = useState(null);
  const [toast, setToast] = useState(null);

  const run = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await runAutoSelection(filters);
      setData(res);
      const r = await getAutoSelectionRecent(5);
      setRecent(r.runs || []);
    } catch (e) {
      setError(e.message || 'Auto-select failed');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadRecent = useCallback(async () => {
    try {
      const r = await getAutoSelectionRecent(5);
      setRecent(r.runs || []);
    } catch { /* informational */ }
  }, []);

  useEffect(() => { loadRecent(); }, [loadRecent]);

  const pushToast = (msg, kind = 'ok') => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3000);
  };

  const handleExportCbot = async (hash, name) => {
    setBusyExport(`cbot-${hash}`);
    try {
      await downloadStrategyCbotByHash(hash, name);
      pushToast('Exported cBot skeleton (.cs)', 'ok');
    } catch (e) {
      pushToast(`Export failed: ${e.message}`, 'err');
    } finally {
      setBusyExport(null);
    }
  };

  const handleExportJson = async (hash, name) => {
    setBusyExport(`json-${hash}`);
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
      pushToast(`Export failed: ${e.message}`, 'err');
    } finally {
      setBusyExport(null);
    }
  };

  const top = data?.top || [];

  return (
    <div className="space-y-5" data-testid="auto-selection">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <Crosshair size={20} className="text-accent-primary" weight="bold" />
            Auto Selection
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            One-click deployment picker. Walks the pipeline (memory → market → prop → match)
            and ranks the best <em>strategy × pair × timeframe × firm × challenge</em> combos
            by composite <code className="text-zinc-300">deploy_score</code>.
          </p>
        </div>
        <button
          data-testid="autosel-run-btn"
          onClick={run}
          disabled={loading}
          className="text-xs font-semibold px-4 py-2 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-50 flex items-center gap-2"
        >
          {loading ? <Spinner size={14} className="animate-spin" /> : <Lightning size={14} weight="bold" />}
          Run Auto Selection
        </button>
      </div>

      {/* Filters */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] p-3 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3" data-testid="autosel-filters">
        {[
          ['top_n', 'Top N', 1, 1, 50],
          ['min_pass_probability', 'Min Pass %', 1, 0, 100],
          ['min_match_score', 'Min Match', 0.05, -1, 2],
          ['min_pf', 'Min PF', 0.05, 0.1, 5],
          ['min_runs', 'Min Runs', 1, 1, 100],
          ['min_stability', 'Min Stability', 0.05, 0, 1],
          ['min_env_confidence', 'Min Env Conf', 0.05, 0, 1],
        ].map(([key, label, step, mn, mx]) => (
          <label key={key} className="flex flex-col gap-1">
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
            <input
              data-testid={`autosel-filter-${key}`}
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
        <label className="flex items-center gap-2 text-[10px] font-mono text-zinc-400 cursor-pointer pt-4">
          <input
            data-testid="autosel-pass-only"
            type="checkbox"
            checked={filters.pass_only}
            onChange={(e) => setFilters((f) => ({ ...f, pass_only: e.target.checked }))}
            className="accent-accent-primary"
          />
          PASS only
        </label>
      </div>

      {error && (
        <div className="rounded border border-red-500/30 bg-red-500/10 text-red-300 text-xs px-3 py-2" data-testid="autosel-error">
          {error}
        </div>
      )}

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-4 gap-3" data-testid="autosel-stats">
          <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
            <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Considered</p>
            <p className="text-xl font-bold text-zinc-100 mt-1 tabular-nums">{data.considered}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
            <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Eligible</p>
            <p className="text-xl font-bold text-accent-primary mt-1 tabular-nums">{data.eligible}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
            <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Top Returned</p>
            <p className="text-xl font-bold text-emerald-300 mt-1 tabular-nums">{data.count}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-[#121821] px-4 py-3">
            <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">Ran At</p>
            <p className="text-[11px] font-mono text-zinc-300 mt-1 truncate">
              {data.ran_at ? new Date(data.ran_at).toLocaleTimeString() : '—'}
            </p>
          </div>
        </div>
      )}

      {/* Results */}
      <div className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden" data-testid="autosel-results">
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
                <th className="text-right px-3 py-2.5">Days</th>
                <th className="text-right px-3 py-2.5">Safe Risk</th>
                <th className="text-left px-3 py-2.5">Deploy Score</th>
                <th className="text-right px-3 py-2.5">Export</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loading && top.length === 0 && (
                <tr><td colSpan={11} className="px-3 py-10 text-center text-zinc-500 font-mono">
                  <Spinner size={14} className="animate-spin inline mr-2" /> Running…
                </td></tr>
              )}
              {!loading && !data && (
                <tr><td colSpan={11} className="px-3 py-8 text-center text-zinc-500 font-mono text-xs" data-testid="autosel-empty">
                  Click <strong>Run Auto Selection</strong> to surface deployment-ready combos.
                </td></tr>
              )}
              {!loading && data && top.length === 0 && (
                <tr><td colSpan={11} className="px-3 py-10 text-center text-zinc-500 font-mono">
                  No candidates matched current filters. Loosen the thresholds and try again.
                </td></tr>
              )}
              {top.map((c, i) => (
                <tr
                  key={`${c.strategy_hash}-${i}`}
                  data-testid={`autosel-row-${c.strategy_hash}`}
                  className="hover:bg-zinc-900/40 transition-colors"
                >
                  <td className="px-3 py-2 font-mono text-zinc-500 tabular-nums">#{i + 1}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium text-zinc-200">{c.strategy_name || '—'}</p>
                    <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                      {c.type || '—'} · PF {fmt(c.strategy_best_pf)} · stab {fmt(c.strategy_stability)}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 font-mono text-xs text-zinc-200">
                      <Globe size={11} className="text-accent-primary" />
                      {c.pair} · {c.timeframe}
                    </span>
                    <p className="text-[9px] font-mono text-zinc-500 mt-0.5">
                      conf {fmt(c.env_confidence)}
                      {c.env_flag ? <span className="text-yellow-400 ml-1">· {c.env_flag}</span> : null}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 font-mono text-xs text-zinc-200">
                      <Trophy size={11} className="text-yellow-400" />
                      {c.firm_name || c.firm_slug}
                    </span>
                    <p className="text-[9px] font-mono text-zinc-500 mt-0.5">{c.challenge}</p>
                  </td>
                  <td className="px-3 py-2"><StatusPill status={c.status} /></td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-200 tabular-nums">{fmt(c.pass_probability, 1)}%</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-300 tabular-nums" data-testid={`autosel-match-${c.strategy_hash}`}>{fmt(c.match_score, 3)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-300 tabular-nums">{c.expected_days ?? '—'}</td>
                  <td className="px-3 py-2 text-right">
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono">
                      <Shield size={10} className="text-accent-primary" />
                      <span className="text-zinc-200 tabular-nums">{fmt(c.safe_risk)}%</span>
                    </span>
                  </td>
                  <td className="px-3 py-2"><ScoreBar value={c.deploy_score} /></td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        data-testid={`autosel-export-json-${c.strategy_hash}`}
                        onClick={() => handleExportJson(c.strategy_hash, c.strategy_name)}
                        disabled={busyExport === `json-${c.strategy_hash}`}
                        title="Export deployment JSON"
                        className="text-[9px] font-mono px-2 py-1 rounded border border-zinc-700 hover:border-accent-primary/50 hover:text-accent-primary text-zinc-300 bg-[#0B0F14] disabled:opacity-50"
                      >
                        {busyExport === `json-${c.strategy_hash}` ? <Spinner size={8} className="animate-spin" /> : 'JSON'}
                      </button>
                      <button
                        data-testid={`autosel-export-cbot-${c.strategy_hash}`}
                        onClick={() => handleExportCbot(c.strategy_hash, c.strategy_name)}
                        disabled={busyExport === `cbot-${c.strategy_hash}`}
                        title="Export cAlgo cBot skeleton (.cs)"
                        className="text-[9px] font-mono px-2 py-1 rounded border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 disabled:opacity-50"
                      >
                        {busyExport === `cbot-${c.strategy_hash}` ? <Spinner size={8} className="animate-spin" /> : 'cBot'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent runs */}
      {recent.length > 0 && (
        <div className="rounded-md border border-zinc-800 bg-[#121821] p-3" data-testid="autosel-recent">
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 mb-2">
            Recent runs
          </p>
          <ul className="space-y-1 text-[11px] font-mono text-zinc-400">
            {recent.map((r) => (
              <li key={r.run_id} className="flex items-center justify-between px-2 py-1 rounded bg-zinc-900/40">
                <span>{new Date(r.ran_at).toLocaleString()}</span>
                <span>
                  top <span className="text-zinc-200">{r.count}</span>
                  {r.filters?.pass_only ? ' · PASS only' : ''}
                  {r.filters?.firm_slug ? ` · ${r.filters.firm_slug}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {toast && (
        <div
          data-testid="autosel-toast"
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
