import React, { useEffect, useRef, useState, useCallback } from 'react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

const POLL_MS = 5000;

/**
 * Auto-Discovery Scheduler Control — compact card.
 *
 * Wraps the existing endpoints:
 *   - POST  /api/auto/scheduler/start
 *   - POST  /api/auto/scheduler/stop
 *   - GET   /api/auto/scheduler/status
 *   - POST  /api/auto/run-once
 *
 * UI elements:
 *   • Toggle switch  → start / stop scheduler at default (15-min) cadence
 *   • Status display → running/stopped, last run timestamp, cycles total
 *   • "Run Now"      → fires a single off-cycle run
 *
 * No scheduler logic lives here — this is pure HTTP + presentation.
 */
export default function AutoSchedulerControl() {
  const [status, setStatus] = useState(null);    // raw status from /status
  const [busy, setBusy] = useState(false);        // toggle / run-now in flight
  const [error, setError] = useState(null);
  const [runOnceMsg, setRunOnceMsg] = useState(null);
  const pollRef = useRef(null);

  // ── HTTP helpers ──────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/auto/scheduler/status`);
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e.message || 'status fetch failed');
    }
  }, []);

  const startScheduler = useCallback(async (overrides = {}) => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/auto/scheduler/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(overrides),     // server-side defaults: 15min, batch=5
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'start failed');
    } finally {
      setBusy(false);
    }
  }, [fetchStatus]);

  const stopScheduler = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/api/auto/scheduler/stop`, {
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

  const runOnce = useCallback(async () => {
    setBusy(true); setError(null); setRunOnceMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/auto/run-once`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await _safeJson(res);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      const saved = data?.strategies_saved ?? 0;
      const dur = data?.duration_sec ?? null;
      setRunOnceMsg(
        data?.status === 'skipped'
          ? `Skipped: ${data?.reason || 'another run is active'}`
          : `Cycle ${data?.status || 'done'} — saved ${saved}` +
            (dur != null ? ` · ${dur.toFixed(1)}s` : ''),
      );
      await fetchStatus();
    } catch (e) {
      setError(e.message || 'run-once failed');
    } finally {
      setBusy(false);
    }
  }, [fetchStatus]);

  // ── Polling lifecycle ─────────────────────────────────────────────
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchStatus]);

  // ── Derived display state ─────────────────────────────────────────
  const enabled    = !!status?.enabled;
  const runtime    = status?.runtime || {};
  const config     = status?.config  || {};
  const interval   = config.interval_minutes ?? 15;
  const lastTickAt = runtime.last_tick_at;
  const lastStatus = runtime.last_status;
  const nextRunAt  = runtime.next_run_at;
  const tickCount  = runtime.tick_count ?? 0;
  const errorCount = runtime.error_count ?? 0;
  const skipCount  = runtime.skip_count ?? 0;
  // Phase 27.1 / G2 — subordination state surfaced by the backend.
  // `subordinateMode` is the persisted config flag (True = defer to
  // orchestrator). `isSubordinatedNow` is True only when the
  // orchestrator scheduler is currently active AND the flag is on.
  const subordinateMode      = config.subordinate_to_orchestrator !== false;
  const isSubordinatedNow    = !!runtime.is_subordinated_now;
  const subordinateSkipCount = runtime.subordinate_skip_count ?? 0;

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
      data-testid="auto-scheduler-card"
      className="border border-zinc-700/50 rounded-lg bg-zinc-900/40 p-4 mb-4"
    >
      {/* ── Header row ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            data-testid="auto-scheduler-status-dot"
            className={
              'w-2 h-2 rounded-full ' +
              (enabled
                ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]'
                : 'bg-zinc-600')
            }
          />
          <h3 className="text-sm font-mono font-semibold text-zinc-200 truncate">
            Auto-Discovery Scheduler
          </h3>
          <span
            data-testid="auto-scheduler-state-label"
            className={
              'text-[10px] font-mono px-2 py-0.5 rounded-full border ' +
              (enabled
                ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'
                : 'border-zinc-600 text-zinc-400 bg-zinc-800/40')
            }
          >
            {enabled ? 'RUNNING' : 'STOPPED'}
          </span>
          {enabled && isSubordinatedNow && (
            <span
              data-testid="auto-scheduler-subordinate-pill"
              title="Orchestrator scheduler is active — discovery ticks are deferred to it. Toggle Independent mode below to override."
              className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-violet-500/40 text-violet-300 bg-violet-500/10"
            >
              SUBORDINATE
            </span>
          )}
        </div>

        {/* ── Toggle switch ──────────────────────────────────────── */}
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Toggle auto-discovery scheduler"
          data-testid="auto-scheduler-toggle"
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

      {/* ── Stats grid ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="Interval"   value={`${interval} min`} testId="auto-scheduler-interval" />
        <Stat label="Cycles"     value={tickCount}         testId="auto-scheduler-cycles" />
        <Stat label="Last run"   value={fmtTs(lastTickAt)} testId="auto-scheduler-last-run" />
        <Stat label="Next run"   value={fmtTs(nextRunAt)}  testId="auto-scheduler-next-run" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat
          label="Last status"
          value={lastStatus || '—'}
          testId="auto-scheduler-last-status"
          tone={
            lastStatus === 'completed' ? 'good' :
            lastStatus === 'error' || lastStatus === 'timeout' ? 'bad' :
            lastStatus === 'skipped' ? 'warn' :
            lastStatus === 'skipped_subordinate' ? 'info' : 'neutral'
          }
        />
        <Stat label="Skipped"  value={skipCount}  testId="auto-scheduler-skipped" tone={skipCount > 0 ? 'warn' : 'neutral'} />
        <Stat label="Errors"   value={errorCount} testId="auto-scheduler-errors"  tone={errorCount > 0 ? 'bad' : 'neutral'} />
        <div className="flex items-end justify-end">
          <button
            type="button"
            data-testid="auto-scheduler-run-now"
            onClick={runOnce}
            disabled={busy}
            className={
              'text-[11px] font-mono px-3 py-1.5 rounded border ' +
              'border-zinc-600 hover:border-accent-primary/60 ' +
              'bg-zinc-800 hover:bg-accent-primary/10 ' +
              'text-zinc-200 hover:text-accent-primary transition-colors ' +
              (busy ? 'opacity-60 cursor-wait' : '')
            }
          >
            {busy ? '…' : 'Run Now'}
          </button>
        </div>
      </div>

      {/* ── Phase 27.1 / G2 — subordination row ───────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-center">
        <Stat
          label="Subordinate skips"
          value={subordinateSkipCount}
          testId="auto-scheduler-subordinate-skip-count"
          tone={subordinateSkipCount > 0 && isSubordinatedNow ? 'info' : 'neutral'}
        />
        <div className="md:col-span-3 flex items-center justify-end gap-2">
          <label
            className="flex items-center gap-2 cursor-pointer select-none text-[11px] font-mono text-zinc-300"
            title="When OFF, this scheduler defers to the orchestrator scheduler whenever the orchestrator is active (recommended). When ON, both schedulers run independently."
          >
            <input
              type="checkbox"
              data-testid="auto-scheduler-independent-mode"
              checked={!subordinateMode}
              disabled={busy}
              onChange={(ev) => {
                const independent = ev.target.checked;
                // Persist immediately: subordinate_to_orchestrator = !independent
                startScheduler({ subordinate_to_orchestrator: !independent });
              }}
              className="h-3 w-3 rounded border-zinc-600 bg-zinc-800 text-accent-primary focus:ring-accent-primary/40"
            />
            <span>Independent mode</span>
            <span className="text-[10px] text-zinc-500">
              {subordinateMode
                ? '(off — defers to orchestrator)'
                : '(on — runs alongside orchestrator)'}
            </span>
          </label>
        </div>
      </div>

      {/* ── Status messages ──────────────────────────────────────── */}
      {runOnceMsg && (
        <div
          data-testid="auto-scheduler-run-once-msg"
          className="text-[11px] font-mono text-emerald-300 border-t border-zinc-700/40 pt-2"
        >
          {runOnceMsg}
        </div>
      )}
      {error && (
        <div
          data-testid="auto-scheduler-error"
          className="text-[11px] font-mono text-red-300 border-t border-zinc-700/40 pt-2"
        >
          {error}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Tiny presentational stat tile — local to this component.
// ─────────────────────────────────────────────────────────────────────
function Stat({ label, value, testId, tone = 'neutral' }) {
  const toneClass = {
    good:    'text-emerald-300',
    warn:    'text-amber-300',
    bad:     'text-red-300',
    info:    'text-violet-300',
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
