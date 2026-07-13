import React, { useEffect, useState, useRef, useCallback } from 'react';
import { AsfEmptyState } from './ui-asf';
import { API_URL } from '../services/api';


// Single-read safe JSON parser — avoids "body stream already read".
async function _safeJson(res) {
  const raw = await res.text().catch(() => '');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

/**
 * Strategy Ingestion — compact dashboard card.
 *
 * Shows: ON/OFF toggle, last run, total ingested, accepted vs rejected,
 * avg confidence, best PF from ingested runs. Button triggers a one-off
 * ingestion pass in the background.
 */
export default function StrategyIngestionCard() {
  const [state, setState] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [recent, setRecent] = useState([]);
  const pollRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const [stRes, lgRes] = await Promise.all([
        fetch(`${API_URL}/api/ingestion/status`),
        fetch(`${API_URL}/api/ingestion/logs?limit=10`),
      ]);
      if (stRes.ok) setState(await _safeJson(stRes));
      if (lgRes.ok) {
        const d = await _safeJson(lgRes);
        setRecent(d.strategies || []);
      }
    } catch { /* silent poll */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 6000);
    return () => pollRef.current && clearInterval(pollRef.current);
  }, [fetchStatus]);

  const runNow = async () => {
    setError(null);
    setRunning(true);
    try {
      const r = await fetch(`${API_URL}/api/ingestion/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_strategies: 5, background: true }),
      });
      const d = await _safeJson(r);
      if (!r.ok) setError(d.detail || `HTTP ${r.status}`);
      fetchStatus();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  const toggleScheduler = async (enabled) => {
    setError(null);
    try {
      const r = await fetch(`${API_URL}/api/ingestion/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, interval_hours: state?.scheduler_interval_hours || 3 }),
      });
      if (!r.ok) {
        const d = await _safeJson(r);
        setError(d.detail || `HTTP ${r.status}`);
      }
      fetchStatus();
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const s = state || {};
  const stats = s.last_run_stats || {};
  const byStatus = recent.reduce(
    (acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }),
    {},
  );
  const avgConf = (() => {
    const withConf = recent.filter((r) => typeof r.confidence === 'number');
    if (!withConf.length) return null;
    return withConf.reduce((a, r) => a + r.confidence, 0) / withConf.length;
  })();
  const busy = s.currently_running;

  return (
    <div
      data-testid="strategy-ingestion-card"
      className="asf-section asf-u2-panel bg-surface-card border border-zinc-800 rounded-md p-4 mb-4"
    >
      <div className="asf-section__hd flex items-center justify-between mb-3">
        <div className="asf-legacy-title flex items-center gap-2">
          <span className="inline-flex w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_8px_#38bdf8]" />
          <h3 className="text-sm font-heading font-semibold text-zinc-100 tracking-tight">
            Strategy Ingestion
          </h3>
          <span className="text-[10px] font-mono text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5">
            AI parser · GitHub / TradingView / local
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 text-[10px] font-mono">
          <span
            data-testid="ingestion-status-badge"
            className={`px-2 py-0.5 rounded border ${
              busy
                ? 'text-sky-300 border-sky-500/40 bg-sky-500/10'
                : s.last_run_status === 'error'
                ? 'text-red-300 border-red-500/40 bg-red-500/10'
                : 'text-zinc-400 border-zinc-700 bg-surface-elevated'
            }`}
          >
            {busy ? 'running' : s.last_run_status || 'idle'}
          </span>
          <label className="flex items-center gap-1 cursor-pointer select-none">
            <input
              data-testid="ingestion-toggle"
              type="checkbox"
              checked={!!s.scheduler_enabled}
              onChange={(e) => toggleScheduler(e.target.checked)}
              className="accent-sky-500"
            />
            <span className="text-zinc-400">
              auto every {s.scheduler_interval_hours || 3}h
            </span>
          </label>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-3">
        <Stat label="last run" value={fmtTime(s.last_run_at)} testid="ing-stat-last" mono />
        <Stat
          label="fetched"
          value={stats.total_fetched ?? 0}
          testid="ing-stat-fetched"
        />
        <Stat
          label="accepted"
          value={stats.total_valid ?? 0}
          testid="ing-stat-accepted"
          color="text-emerald-300"
        />
        <Stat
          label="rejected"
          value={stats.total_rejected ?? 0}
          testid="ing-stat-rejected"
          color="text-amber-300"
        />
        <Stat
          label="avg confidence"
          value={avgConf != null ? avgConf.toFixed(2) : '—'}
          testid="ing-stat-conf"
          color="text-sky-300"
        />
        <Stat
          label="best PF (ingested)"
          value={
            stats.best_pf_from_ingested != null
              ? Number(stats.best_pf_from_ingested).toFixed(2)
              : '—'
          }
          testid="ing-stat-best-pf"
          color="text-accent-primary"
          hint={stats.best_pf_source ? `src: ${stats.best_pf_source}` : null}
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          data-testid="ingestion-run-btn"
          onClick={runNow}
          disabled={running || busy}
          className={`px-3 py-1.5 rounded-md text-xs font-semibold tracking-tight transition-colors ${
            running || busy
              ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700'
              : 'bg-gradient-to-r from-sky-500 to-cyan-500 text-white shadow-[0_0_14px_rgba(56,189,248,0.35)] hover:brightness-110'
          }`}
        >
          {running || busy ? 'Ingesting…' : 'Run Ingestion (5)'}
        </button>
        <span className="text-[10px] font-mono text-zinc-500">
          fetches up to 5 external strategies · parses · validates · injects
        </span>
        {s.local_queue_size > 0 && (
          <span
            data-testid="ingestion-queue-count"
            className="ml-auto text-[10px] font-mono text-zinc-400 border border-zinc-700 rounded px-2 py-0.5"
          >
            queue: {s.local_queue_size}
          </span>
        )}
      </div>

      {error && (
        <div className="mt-2">
          <AsfEmptyState
            slug="ingestion-error"
            testId="ingestion-error"
            title="Ingestion failed"
            body={error}
          />
        </div>
      )}

      {recent.length > 0 && (
        <details data-testid="ingestion-recent" className="mt-3">
          <summary className="cursor-pointer text-[10px] font-mono text-zinc-500 hover:text-zinc-300">
            ▸ Recent ingested ({recent.length}) — accepted {byStatus.accepted || 0} / rejected {byStatus.rejected || 0}
          </summary>
          <div className="mt-2 max-h-48 overflow-auto border border-zinc-800 rounded">
            <table className="w-full text-[10px] font-mono">
              <thead className="sticky top-0 bg-surface-elevated">
                <tr className="text-zinc-500 text-left">
                  <th className="px-2 py-1">src</th>
                  <th className="px-2 py-1">type</th>
                  <th className="px-2 py-1">status</th>
                  <th className="px-2 py-1">conf</th>
                  <th className="px-2 py-1">best PF</th>
                  <th className="px-2 py-1">reason</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r, i) => (
                  <tr key={i} className="border-t border-zinc-800 text-zinc-200">
                    <td className="px-2 py-1">{r.source || '—'}</td>
                    <td className="px-2 py-1">{r.type || '—'}</td>
                    <td
                      className={`px-2 py-1 ${
                        r.status === 'accepted' ? 'text-emerald-300' : 'text-amber-300'
                      }`}
                    >
                      {r.status}
                    </td>
                    <td className="px-2 py-1">
                      {typeof r.confidence === 'number' ? r.confidence.toFixed(2) : '—'}
                    </td>
                    <td className="px-2 py-1 text-accent-primary">
                      {r.injection?.best_pf != null
                        ? Number(r.injection.best_pf).toFixed(2)
                        : '—'}
                    </td>
                    <td className="px-2 py-1 text-zinc-400 truncate max-w-[220px]" title={r.reason}>
                      {r.reason || '—'}
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
      data-testid={testid}
      className="bg-surface-elevated border border-zinc-800 rounded px-2 py-1.5"
    >
      <div className="text-[9px] font-mono text-zinc-500 uppercase tracking-wide">
        {label}
      </div>
      <div
        className={`text-sm font-semibold truncate ${color || 'text-zinc-100'} ${
          mono ? 'font-mono text-xs' : ''
        }`}
      >
        {value}
      </div>
      {hint && <div className="text-[9px] font-mono text-zinc-600">{hint}</div>}
    </div>
  );
}

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso.slice(11, 16);
  }
}
