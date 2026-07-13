import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useDatasetAvailability } from '../hooks/useDatasetAvailability';
import { DataAvailabilityBanner, DataLoadStatus, PairOptions, TimeframeOptions } from './DataAvailability';
import { AsfKpiTile, AsfEmptyState, VerdictChip } from './ui-asf';
import { API_URL } from '../services/api';


// Single-read safe JSON parser — avoids "body stream already read".
async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

// Defaults chosen so 1-click = 100 mutation runs (20 iterations × 5 strategies)
const DEFAULT_ITERATIONS = 20;
const DEFAULT_STRATEGIES_PER_CYCLE = 5;

/**
 * Auto Mutation Runner — minimal control card.
 *
 * Posts to /api/auto/mutation-runner and polls /status every 2.5s while
 * the run is active. Shows progress bar, current cycle, best PF so far,
 * and a short cycle history tail.
 *
 * No changes to mutation, scoring, or evolution — this only drives the
 * existing engines through the new controlled-loop backend.
 */
export default function AutoMutationRunner({ defaultPair = 'EURUSD', defaultTimeframe = 'H1' }) {
  const [iterations, setIterations] = useState(DEFAULT_ITERATIONS);
  const [stratPerCycle, setStratPerCycle] = useState(DEFAULT_STRATEGIES_PER_CYCLE);
  const [pair, setPair] = useState(defaultPair);
  const [timeframe, setTimeframe] = useState(defaultTimeframe);
  const [state, setState] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // P2 — Shared dataset availability hook. Gives us the exact same
  // pair/TF dropdown source + banner + Load Data click flow the
  // Strategy Dashboard uses. This is the single source of truth —
  // any change to the dataset UX propagates to both surfaces.
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
    loadData,
    clearDownload,
  } = useDatasetAvailability(pair, setPair, timeframe, setTimeframe);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/api/auto/mutation-runner/status`);
      if (r.ok) {
        const d = await r.json();
        setState(d);
        return d;
      }
    } catch (e) {
      // silent poll error
    }
    return null;
  }, []);

  // Poll on mount + every 2.5s while running
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(async () => {
      const d = await fetchStatus();
      if (d && d.status !== 'running') {
        // slow down polling when idle
        clearInterval(pollRef.current);
        pollRef.current = setInterval(fetchStatus, 8000);
      }
    }, 2500);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, [fetchStatus]);

  const start = async () => {
    setError(null);
    setStarting(true);
    try {
      const body = {
        iterations: Math.max(1, Math.min(parseInt(iterations, 10) || 1, 200)),
        strategies_per_cycle: Math.max(1, Math.min(parseInt(stratPerCycle, 10) || 1, 20)),
        pair: (pair || 'EURUSD').toUpperCase(),
        timeframe: (timeframe || 'H1').toUpperCase(),
        auto_save: true,
      };
      const r = await fetch(`${API_URL}/api/auto/mutation-runner`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await _safeJson(r);
      if (!r.ok) {
        setError(d.detail || `HTTP ${r.status}`);
      } else {
        setState(d);
        // Accelerate polling during run
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(fetchStatus, 2500);
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setStarting(false);
    }
  };

  const stop = async () => {
    try {
      await fetch(`${API_URL}/api/auto/mutation-runner/stop`, { method: 'POST' });
      fetchStatus();
    } catch (e) { /* ignore */ }
  };

  const s = state || {};
  const progress = s.progress || {};
  const stats = s.stats || {};
  const cycles = s.cycle_history || [];
  const running = s.status === 'running';
  const totalRuns = (progress.total_cycles || 0) * (progress.strategies_per_cycle || 0);
  const doneRuns =
    ((progress.current_cycle || 1) - 1) * (progress.strategies_per_cycle || 0) +
    (progress.strategies_completed_this_cycle || 0);
  const pct = totalRuns > 0 ? Math.min(100, Math.round((doneRuns / totalRuns) * 100)) : 0;

  return (
    <div
      data-testid="auto-mutation-runner-card"
      className="asf-u2-panel bg-surface-card border border-zinc-800 rounded-md p-4 mb-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="asf-legacy-title flex items-center gap-2">
          <span className="inline-flex w-2 h-2 rounded-full bg-fuchsia-400 shadow-[0_0_8px_#e879f9]" />
          <h3 className="text-sm font-heading font-semibold text-zinc-100 tracking-tight">
            Auto Mutation Runner
          </h3>
          <span className="text-[10px] font-mono text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5">
            Semi-auto · bootstraps evolution logs
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <VerdictChip
            testId="auto-mutation-status"
            verdict={running ? 'info' : s.status === 'error' ? 'danger' : s.status === 'stopped' ? 'warn' : 'neutral'}
            label={s.status || 'idle'}
          />
          {s.job_id && (
            <span className="text-zinc-500">job {s.job_id.slice(0, 8)}</span>
          )}
        </div>
      </div>

      {/* ── Controls row ── */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-mono text-zinc-500">pair</span>
          <select
            data-testid="amr-pair"
            className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-zinc-100 font-mono text-xs"
            value={pair}
            onChange={(e) => setPair(e.target.value)}
            disabled={running}
          >
            <PairOptions datasets={datasets} availablePairs={availablePairs} />
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-mono text-zinc-500">timeframe</span>
          <select
            data-testid="amr-tf"
            className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-zinc-100 font-mono text-xs"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            disabled={running}
          >
            <TimeframeOptions currentDataset={currentDataset} availableTFs={availableTFs} />
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-mono text-zinc-500">iterations</span>
          <input
            data-testid="amr-iterations"
            type="number"
            min={1}
            max={200}
            className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-zinc-100 font-mono text-xs"
            value={iterations}
            onChange={(e) => setIterations(e.target.value)}
            disabled={running}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-mono text-zinc-500">strategies / cycle</span>
          <input
            data-testid="amr-spc"
            type="number"
            min={1}
            max={20}
            className="bg-surface-elevated border border-zinc-700 rounded px-2 py-1 text-zinc-100 font-mono text-xs"
            value={stratPerCycle}
            onChange={(e) => setStratPerCycle(e.target.value)}
            disabled={running}
          />
        </label>
        <div className="md:col-span-2 flex items-end gap-2">
          <button
            data-testid="amr-start-btn"
            onClick={start}
            disabled={running || starting || !isDataReady}
            title={!isDataReady ? `Cannot start — ${dataStatus.label}` : 'Run the controlled mutation loop'}
            className={`flex-1 px-3 py-1.5 rounded-md text-xs font-semibold tracking-tight transition-colors ${
              running || starting || !isDataReady
                ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700'
                : 'bg-gradient-to-r from-fuchsia-500 to-violet-500 text-white shadow-[0_0_14px_rgba(232,121,249,0.35)] hover:brightness-110'
            }`}
          >
            {starting
              ? 'Starting…'
              : running
              ? 'Running…'
              : !isDataReady
              ? 'No data'
              : `Run Auto Mutation (${(parseInt(iterations, 10) || 0) * (parseInt(stratPerCycle, 10) || 0)} runs)`}
          </button>
          {running && (
            <button
              data-testid="amr-stop-btn"
              onClick={stop}
              className="px-3 py-1.5 rounded-md text-xs font-semibold border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
            >
              Stop
            </button>
          )}
        </div>
      </div>

      {/* P2 — Shared availability banner (same component as
          StrategyDashboard). */}
      <DataAvailabilityBanner
        pair={pair}
        timeframe={timeframe}
        dataStatus={dataStatus}
        currentDataset={currentDataset}
        downloading={downloading}
        onLoadData={loadData}
        testIdPrefix="amr-data-availability"
        className="mb-3"
      />

      {/* P2 — Shared Load Data status / fallback banner. */}
      <DataLoadStatus
        result={downloadResult}
        error={downloadError}
        pair={pair}
        timeframe={timeframe}
        onDismiss={clearDownload}
        testIdPrefix="amr-data-load"
      />

      {/* ── Progress bar ── */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 mb-1">
          <span data-testid="amr-progress-label">
            cycle {progress.current_cycle || 0} / {progress.total_cycles || 0}
            {progress.strategies_per_cycle
              ? ` · strategy ${progress.strategies_completed_this_cycle || 0}/${progress.strategies_per_cycle}`
              : ''}
          </span>
          <span data-testid="amr-progress-pct">{pct}%</span>
        </div>
        <div className="h-1.5 w-full bg-surface-elevated rounded overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              running
                ? 'bg-gradient-to-r from-fuchsia-500 to-violet-500'
                : 'bg-zinc-700'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* ── Stats grid (U-2 AsfKpiTile) ── */}
      <div className="asf-kpi-grid mb-3" data-testid="amr-stats">
        <AsfKpiTile
          label="best PF overall"
          value={stats.best_pf_overall != null ? Number(stats.best_pf_overall).toFixed(2) : '—'}
          verdict={stats.best_pf_overall != null && stats.best_pf_overall >= 1.0 ? 'success' : 'neutral'}
          testId="amr-stat-best-pf"
        />
        <AsfKpiTile
          label="best mutation"
          value={stats.best_mutation_type_overall || '—'}
          testId="amr-stat-best-type"
        />
        <AsfKpiTile
          label="cycles done"
          value={stats.cycles_completed || 0}
          testId="amr-stat-cycles"
        />
        <AsfKpiTile
          label="auto-saves"
          value={`${stats.auto_save_saved || 0} / ${stats.auto_save_rejected || 0}`}
          delta="saved / rejected"
          testId="amr-stat-saves"
        />
        <AsfKpiTile
          label="bad streak"
          value={stats.consecutive_bad_cycles || 0}
          delta="stops at 3"
          verdict={(stats.consecutive_bad_cycles || 0) >= 2 ? 'warn' : 'neutral'}
          testId="amr-stat-bad-streak"
        />
      </div>

      {/* ── Errors ── */}
      {(error || s.last_error) && (
        <AsfEmptyState
          slug="amr-error"
          testId="amr-error"
          title="Mutation runner reported an error"
          body={error || s.last_error}
          action={running ? undefined : { label: 'Dismiss', onClick: () => setError(null), testId: 'amr-error-dismiss' }}
        />
      )}

      {/* ── Cycle history tail ── */}
      {cycles.length > 0 && (
        <details data-testid="amr-cycle-history" className="mt-2">
          <summary className="cursor-pointer text-[10px] font-mono text-zinc-500 hover:text-zinc-300">
            ▸ Cycle history ({cycles.length})
          </summary>
          <div className="mt-2 max-h-40 overflow-auto border border-zinc-800 rounded">
            <table className="w-full text-[10px] font-mono">
              <thead className="sticky top-0 bg-surface-elevated">
                <tr className="text-zinc-500 text-left">
                  <th className="px-2 py-1">#</th>
                  <th className="px-2 py-1">best PF</th>
                  <th className="px-2 py-1">trades</th>
                  <th className="px-2 py-1">saved</th>
                  <th className="px-2 py-1">rejected</th>
                  <th className="px-2 py-1">all&lt;0.9</th>
                </tr>
              </thead>
              <tbody>
                {cycles
                  .slice()
                  .reverse()
                  .map((c) => (
                    <tr
                      key={c.cycle_index}
                      className="border-t border-zinc-800 text-zinc-200"
                    >
                      <td className="px-2 py-1">{c.cycle_index}</td>
                      <td className="px-2 py-1">
                        {c.best_pf_cycle != null ? Number(c.best_pf_cycle).toFixed(2) : '—'}
                      </td>
                      <td className="px-2 py-1">{c.total_trades_cycle ?? '—'}</td>
                      <td className="px-2 py-1 text-emerald-300">
                        {c.counts?.auto_save_saved ?? 0}
                      </td>
                      <td className="px-2 py-1 text-amber-300">
                        {c.counts?.auto_save_rejected ?? 0}
                      </td>
                      <td className="px-2 py-1">
                        {c.all_below_threshold ? (
                          <span className="text-red-300">yes</span>
                        ) : (
                          <span className="text-zinc-500">no</span>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value, testid, color, mono, hint }) {
  return (
    <div
      className="bg-surface-elevated border border-zinc-800 rounded px-2 py-1.5"
      data-testid={testid}
    >
      <div className="text-[9px] font-mono text-zinc-500 uppercase tracking-wide">
        {label}
      </div>
      <div
        className={`text-sm font-semibold truncate ${color || 'text-zinc-100'} ${
          mono ? 'font-mono' : ''
        }`}
      >
        {value}
      </div>
      {hint && (
        <div className="text-[9px] font-mono text-zinc-600">{hint}</div>
      )}
    </div>
  );
}
