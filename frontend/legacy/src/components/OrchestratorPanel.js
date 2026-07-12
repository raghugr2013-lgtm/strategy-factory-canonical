import React, { useEffect, useRef, useState, useCallback } from 'react';
import EnvPriorityPanel from './EnvPriorityPanel';

const API_URL = process.env.REACT_APP_BACKEND_URL;

async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

const POLL_MS = 5000;
const INTERVAL_OPTIONS = [15, 30, 60];

/**
 * AI Orchestrator Panel — controls + live state for the rule-based
 * decision engine and its 15-min scheduler.
 *
 * Wraps the endpoints:
 *   - POST /api/orchestrator/scheduler/start   { interval_minutes }
 *   - POST /api/orchestrator/scheduler/stop
 *   - GET  /api/orchestrator/scheduler/status
 *   - POST /api/orchestrator/tick              { execute }
 *
 * Mirrors the visual language of `AutoSchedulerControl` for
 * consistency across the dashboard.
 */
export default function OrchestratorPanel() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [runMsg, setRunMsg] = useState(null);
  const [interval, setIntervalChoice] = useState(15);
  const [intervalSynced, setIntervalSynced] = useState(false);   // sync UI to backend value once on first load
  const [executeMode, setExecuteMode] = useState(true);   // execute=true by default
  const pollRef = useRef(null);

  // ── HTTP helpers ────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/scheduler/status`);
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setStatus(data);
      setError(null);
      // Sync interval picker with backend on first successful load.
      if (!intervalSynced && data?.interval_minutes) {
        setIntervalChoice(data.interval_minutes);
        setIntervalSynced(true);
      }
    } catch (e) {
      setError(e.message || 'status fetch failed');
    }
  }, [intervalSynced]);

  const startScheduler = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/scheduler/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_minutes: interval }),
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'start failed');
    } finally {
      setBusy(false);
    }
  }, [interval, fetchStatus]);

  const stopScheduler = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/scheduler/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'stop failed');
    } finally {
      setBusy(false);
    }
  }, [fetchStatus]);

  const runNow = useCallback(async () => {
    setBusy(true); setError(null); setRunMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/orchestrator/tick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ execute: executeMode }),
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);

      const recCount = (data?.recommendations || []).length;
      const execCount = (data?.executions || []).length;

      if (data?.status === 'cooldown_skip') {
        setRunMsg(
          `Cooldown — wait ${Math.ceil(data?.seconds_remaining ?? 0)}s before another execute. ` +
          `Showing ${recCount} advisory recommendation${recCount === 1 ? '' : 's'}.`,
        );
      } else if (executeMode) {
        setRunMsg(`Tick executed — ${recCount} recs, ${execCount} actions.`);
      } else {
        setRunMsg(`Preview only — ${recCount} recommendation${recCount === 1 ? '' : 's'} (no execution).`);
      }
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'run-now failed');
    } finally {
      setBusy(false);
    }
  }, [executeMode, fetchStatus]);

  // ── Polling lifecycle ───────────────────────────────────────────
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchStatus]);

  // ── Derived display state ───────────────────────────────────────
  const enabled    = !!status?.enabled;
  const intervalMin   = status?.interval_minutes ?? interval;
  const lastTickAt    = status?.last_tick_at;
  const nextRunAt     = status?.next_run_at;
  const tickCount     = status?.tick_count ?? 0;
  const executedCount = status?.executed_count ?? 0;
  const advisoryCount = status?.advisory_count ?? 0;
  const lastError     = status?.last_error;
  const recs          = status?.last_recommendations || [];
  const execs         = status?.last_executions || [];
  const cooldownLeft  = status?.cooldown?.remaining ?? 0;

  const fmtTs = (iso) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch { return iso; }
  };

  const onToggle = () => {
    if (busy) return;
    enabled ? stopScheduler() : startScheduler();
  };

  return (
    <div
      data-testid="orchestrator-panel"
      className="border border-zinc-700/50 rounded-lg bg-zinc-900/40 p-4 mb-4"
    >
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            data-testid="orchestrator-status-dot"
            className={
              'w-2 h-2 rounded-full ' +
              (enabled
                ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]'
                : 'bg-zinc-600')
            }
          />
          <h3 className="text-sm font-mono font-semibold text-zinc-200 truncate">
            AI Orchestrator
          </h3>
          <span
            data-testid="orchestrator-state-label"
            className={
              'text-[10px] font-mono px-2 py-0.5 rounded-full border ' +
              (enabled
                ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                : 'border-zinc-600 text-zinc-400 bg-zinc-800/40')
            }
          >
            {enabled ? 'RUNNING' : 'STOPPED'}
          </span>
        </div>

        {/* Toggle */}
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Toggle orchestrator scheduler"
          data-testid="orchestrator-toggle"
          onClick={onToggle}
          disabled={busy}
          className={
            'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full ' +
            'border-2 border-transparent transition-colors duration-200 ease-in-out ' +
            'focus:outline-none focus:ring-2 focus:ring-accent-primary/40 ' +
            (busy ? 'opacity-60 cursor-wait ' : '') +
            (enabled ? 'bg-emerald-500' : 'bg-zinc-700')
          }
        >
          <span
            aria-hidden="true"
            className={
              'pointer-events-none inline-block h-5 w-5 transform rounded-full ' +
              'bg-white shadow ring-0 transition duration-200 ease-in-out ' +
              (enabled ? 'translate-x-5' : 'translate-x-0')
            }
          />
        </button>
      </div>

      {/* ── Controls row: interval + execute mode ──────────────── */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
            Interval
          </span>
          <div
            data-testid="orchestrator-interval-group"
            className="inline-flex rounded border border-zinc-700 overflow-hidden"
          >
            {INTERVAL_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                data-testid={`orchestrator-interval-${opt}`}
                onClick={() => setIntervalChoice(opt)}
                disabled={busy}
                className={
                  'px-2 py-1 text-[11px] font-mono transition-colors ' +
                  (interval === opt
                    ? 'bg-accent-primary/20 text-accent-primary'
                    : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200')
                }
              >
                {opt}m
              </button>
            ))}
          </div>
          {enabled && interval !== intervalMin && (
            <button
              type="button"
              data-testid="orchestrator-interval-apply"
              onClick={startScheduler}
              disabled={busy}
              className="text-[10px] font-mono px-2 py-1 rounded border border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
            >
              apply
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
            Mode
          </span>
          <div className="inline-flex rounded border border-zinc-700 overflow-hidden">
            <button
              type="button"
              data-testid="orchestrator-mode-advisory"
              onClick={() => setExecuteMode(false)}
              className={
                'px-2 py-1 text-[11px] font-mono transition-colors ' +
                (!executeMode
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200')
              }
            >
              Advisory
            </button>
            <button
              type="button"
              data-testid="orchestrator-mode-execute"
              onClick={() => setExecuteMode(true)}
              className={
                'px-2 py-1 text-[11px] font-mono transition-colors ' +
                (executeMode
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200')
              }
            >
              Execute
            </button>
          </div>
        </div>

        <div className="flex-1" />

        <button
          type="button"
          data-testid="orchestrator-run-now"
          onClick={runNow}
          disabled={busy || (executeMode && cooldownLeft > 0)}
          title={executeMode && cooldownLeft > 0 ? `Cooldown: ${Math.ceil(cooldownLeft)}s remaining` : ''}
          className={
            'text-[11px] font-mono px-3 py-1.5 rounded border ' +
            'border-zinc-600 hover:border-accent-primary/60 ' +
            'bg-zinc-800 hover:bg-accent-primary/10 ' +
            'text-zinc-200 hover:text-accent-primary transition-colors ' +
            (busy || (executeMode && cooldownLeft > 0) ? 'opacity-60 cursor-not-allowed' : '')
          }
        >
          {busy
            ? '…'
            : executeMode && cooldownLeft > 0
              ? `Cooldown ${Math.ceil(cooldownLeft)}s`
              : 'Run Now'}
        </button>
      </div>

      {/* ── Stats grid ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="Interval"  value={`${intervalMin} min`}     testId="orchestrator-interval" />
        <Stat label="Ticks"     value={tickCount}                 testId="orchestrator-tick-count" />
        <Stat label="Last tick" value={fmtTs(lastTickAt)}         testId="orchestrator-last-tick" />
        <Stat label="Next tick" value={fmtTs(nextRunAt)}          testId="orchestrator-next-tick" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat
          label="Executed"
          value={executedCount}
          testId="orchestrator-executed-count"
          tone={executedCount > 0 ? 'good' : 'neutral'}
        />
        <Stat
          label="Advisory"
          value={advisoryCount}
          testId="orchestrator-advisory-count"
          tone="neutral"
        />
        <Stat
          label="Last recs"
          value={recs.length}
          testId="orchestrator-last-recs-count"
        />
        <Stat
          label="Errors"
          value={lastError ? '1' : '0'}
          testId="orchestrator-error-count"
          tone={lastError ? 'bad' : 'neutral'}
        />
      </div>

      {/* ── Last decision: recommendations ────────────────────── */}
      {recs.length > 0 && (
        <div className="border-t border-zinc-700/40 pt-3 mb-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
            Last Decision · Recommendations ({recs.length})
          </div>
          <div
            data-testid="orchestrator-recommendations"
            className="flex flex-col gap-1.5 max-h-48 overflow-y-auto"
          >
            {recs.map((r, idx) => (
              <RecRow key={`${r.rule_id}-${idx}`} rec={r} />
            ))}
          </div>
        </div>
      )}

      {/* ── Last decision: executions ─────────────────────────── */}
      {execs.length > 0 && (
        <div className="border-t border-zinc-700/40 pt-3 mb-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-zinc-500 mb-2">
            Last Decision · Executions ({execs.length})
          </div>
          <div
            data-testid="orchestrator-executions"
            className="flex flex-col gap-1.5 max-h-32 overflow-y-auto"
          >
            {execs.map((e, idx) => (
              <ExecRow key={`${e.rule_id}-${idx}`} ex={e} />
            ))}
          </div>
        </div>
      )}

      {/* ── Status / error messages ──────────────────────────── */}
      {runMsg && (
        <div
          data-testid="orchestrator-run-msg"
          className="text-[11px] font-mono text-emerald-300 border-t border-zinc-700/40 pt-2"
        >
          {runMsg}
        </div>
      )}
      {error && (
        <div
          data-testid="orchestrator-error"
          className="text-[11px] font-mono text-red-300 border-t border-zinc-700/40 pt-2"
        >
          {error}
        </div>
      )}
      {lastError && !error && (
        <div
          data-testid="orchestrator-last-error"
          className="text-[11px] font-mono text-amber-300 border-t border-zinc-700/40 pt-2"
        >
          Last tick error: {lastError}
        </div>
      )}

      {/* Phase 23 — Adaptive Environment Priority */}
      <EnvPriorityPanel />
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Sub-components
// ───────────────────────────────────────────────────────────────────

function Stat({ label, value, testId, tone = 'neutral' }) {
  const toneClass = {
    good:    'text-emerald-300',
    warn:    'text-amber-300',
    bad:     'text-red-300',
    neutral: 'text-zinc-200',
  }[tone] || 'text-zinc-200';

  return (
    <div className="flex flex-col min-w-0">
      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <span
        data-testid={testId}
        className={`text-[12px] font-mono ${toneClass} truncate`}
        title={typeof value === 'string' ? value : undefined}
      >
        {value}
      </span>
    </div>
  );
}

function severityClasses(severity) {
  switch (severity) {
    case 'critical': return 'border-red-500/40 text-red-300 bg-red-500/10';
    case 'warn':     return 'border-amber-500/40 text-amber-300 bg-amber-500/10';
    case 'info':
    default:         return 'border-zinc-600 text-zinc-300 bg-zinc-800/40';
  }
}

function actionLabel(action) {
  switch (action) {
    case 'trigger_multi_cycle':   return 'TRIGGER';
    case 'stop_multi_cycle':      return 'STOP';
    case 'log_recommendation':    return 'ADVISORY';
    case 'promote_best_strategy': return 'PROMOTE';
    default:                      return (action || '').toUpperCase();
  }
}

function RecRow({ rec }) {
  return (
    <div
      data-testid="orchestrator-rec-row"
      className="flex items-start gap-2 text-[11px] font-mono p-2 rounded border border-zinc-700/40 bg-zinc-800/30"
    >
      <span
        className={
          'shrink-0 px-1.5 py-0.5 rounded-full border text-[9px] uppercase tracking-wider ' +
          severityClasses(rec.severity)
        }
      >
        {rec.severity || 'info'}
      </span>
      <span className="shrink-0 text-zinc-400">{actionLabel(rec.action)}</span>
      <span className="shrink-0 text-accent-primary">{rec.rule_id}</span>
      <span className="text-zinc-300 truncate" title={rec.reason}>
        {rec.reason}
      </span>
    </div>
  );
}

function ExecRow({ ex }) {
  const status = ex.status || 'unknown';
  const tone =
    status === 'executed' ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10' :
    status === 'error'    ? 'text-red-300 border-red-500/40 bg-red-500/10' :
    status === 'skipped'  ? 'text-amber-300 border-amber-500/40 bg-amber-500/10' :
                            'text-zinc-300 border-zinc-600 bg-zinc-800/40';
  return (
    <div
      data-testid="orchestrator-exec-row"
      className="flex items-center gap-2 text-[11px] font-mono p-2 rounded border border-zinc-700/40 bg-zinc-800/30"
    >
      <span className={`shrink-0 px-1.5 py-0.5 rounded-full border text-[9px] uppercase tracking-wider ${tone}`}>
        {status}
      </span>
      <span className="shrink-0 text-zinc-400">{actionLabel(ex.action)}</span>
      <span className="shrink-0 text-accent-primary">{ex.rule_id}</span>
      {ex.error && (
        <span className="text-red-300 truncate" title={ex.error}>· {ex.error}</span>
      )}
      {ex.run_id && (
        <span className="text-zinc-500 truncate" title={ex.run_id}>· run {ex.run_id.slice(0, 8)}</span>
      )}
    </div>
  );
}
