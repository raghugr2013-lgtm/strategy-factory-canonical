/**
 * BI5 R2 / B-8 — Strategy & Data Certification Panel
 * ----------------------------------------------------------------------------
 * Pre-named diag slot: `diag/bi5-cert`. Reads:
 *
 *   GET  /api/admin/bi5/data-certifications?verdict={PASS|WARN|FAIL}
 *   GET  /api/admin/bi5/certifications/stats?group_by=verdict
 *   GET  /api/admin/bi5/sweep/runs?limit=10
 *   GET  /api/admin/bi5/sweep/status
 *   POST /api/admin/bi5/sweep         (operator-triggered run)
 *
 * Surfaces:
 *   • Stats strip — last sweep summary (PASS/WARN/FAIL/early-fail counts)
 *     + next auto-cadence run time
 *   • Data-cert table — per-symbol verdicts pulled from the 4-symbol BI5
 *     calibration set (PASS/WARN/FAIL counts via separate calls)
 *   • Strategy-cert sweep history — most recent run rows
 *   • "Run sweep now" button — admin-only manual trigger
 *
 * The panel is read-only for non-admin users (the underlying endpoints
 * are admin-gated; the button will surface a 403 cleanly).
 */
import React, { useEffect, useState, useCallback } from 'react';
import './Bi5CertPanel.css';

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

function chipClass(v) {
  const u = (v || '').toUpperCase();
  if (u === 'PASS') return 'bi5c__chip bi5c__chip--pass';
  if (u === 'WARN') return 'bi5c__chip bi5c__chip--warn';
  if (u === 'FAIL') return 'bi5c__chip bi5c__chip--fail';
  return 'bi5c__chip bi5c__chip--muted';
}

function fmtTs(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const dt = Date.now() - d.getTime();
    if (dt < 60_000)        return 'just now';
    if (dt < 3_600_000)     return `${Math.floor(dt / 60_000)}m ago`;
    if (dt < 86_400_000)    return `${Math.floor(dt / 3_600_000)}h ago`;
    return `${Math.floor(dt / 86_400_000)}d ago`;
  } catch { return ts; }
}

function fmtUtc(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toISOString().replace('T', ' ').replace(/:\d{2}\..*$/, '') + ' UTC';
  } catch { return ts; }
}

async function authFetch(path, options = {}) {
  let token = '';
  try { token = localStorage.getItem('asf_auth_token') || ''; } catch { /* noop */ }
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(options.headers || {}),
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...(options.method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} ${res.statusText} · ${txt.slice(0, 120)}`);
  }
  return res.json();
}

const VERDICTS = ['PASS', 'WARN', 'FAIL'];

export default function Bi5CertPanel() {
  const [dataCerts, setDataCerts] = useState({ PASS: [], WARN: [], FAIL: [] });
  const [sweepRuns, setSweepRuns] = useState({ items: [], last: null });
  const [sweepStatus, setSweepStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pass, warn, fail, runs, status] = await Promise.all([
        authFetch('/api/admin/bi5/data-certifications?verdict=PASS&limit=20'),
        authFetch('/api/admin/bi5/data-certifications?verdict=WARN&limit=20'),
        authFetch('/api/admin/bi5/data-certifications?verdict=FAIL&limit=20'),
        authFetch('/api/admin/bi5/sweep/runs?limit=10'),
        authFetch('/api/admin/bi5/sweep/status'),
      ]);
      setDataCerts({
        PASS: pass.items || [],
        WARN: warn.items || [],
        FAIL: fail.items || [],
      });
      setSweepRuns(runs);
      setSweepStatus(status);
    } catch (e) {
      setError(e.message || 'load_failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const triggerSweep = async () => {
    setRunning(true);
    setToast(null);
    try {
      const res = await authFetch('/api/admin/bi5/sweep', {
        method: 'POST',
        body: JSON.stringify({ max_strategies: 200, dry_run: false }),
      });
      setToast({
        kind: 'ok',
        msg:
          `Sweep complete · run_id ${(res.run_id || '').slice(0, 8)}… · ` +
          `discovered=${res.discovered} · processed=${res.processed} · ` +
          `PASS=${res.pass_count} · WARN=${res.warn_count} · FAIL=${res.fail_count} · ` +
          `skipped=${res.skipped} · ${res.duration_seconds}s`,
      });
      await load();
    } catch (e) {
      setToast({ kind: 'err', msg: e.message || 'sweep_failed' });
    } finally {
      setRunning(false);
    }
  };

  // Flatten + sort the data-cert rows for the per-symbol table.
  const allDataCertRows = [
    ...dataCerts.PASS.map(d => ({ ...d, _verdict: 'PASS' })),
    ...dataCerts.WARN.map(d => ({ ...d, _verdict: 'WARN' })),
    ...dataCerts.FAIL.map(d => ({ ...d, _verdict: 'FAIL' })),
  ];
  // Latest per (symbol, window) — collection is already keyed that way,
  // so the rows are unique. Sort by symbol then window_start descending.
  allDataCertRows.sort((a, b) => {
    const symCmp = String(a.symbol || '').localeCompare(String(b.symbol || ''));
    if (symCmp !== 0) return symCmp;
    return String(b.window_start_utc || '').localeCompare(String(a.window_start_utc || ''));
  });

  const counts = {
    pass: dataCerts.PASS.length,
    warn: dataCerts.WARN.length,
    fail: dataCerts.FAIL.length,
  };
  const total = counts.pass + counts.warn + counts.fail;
  const last = sweepRuns.last;

  return (
    <div className="bi5c" data-testid="bi5-cert-panel">
      <header className="bi5c__hd">
        <span className="bi5c__badge">BI5 R2</span>
        <h2 className="bi5c__title">Strategy &amp; Data Certification</h2>
        <span className="bi5c__schema-tag">
          schema · {sweepStatus?.version || 'bi5_cert_sweep@R2-v1'}
        </span>
        <button
          type="button"
          className="bi5c__btn"
          data-testid="bi5c-refresh"
          onClick={load}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
        <button
          type="button"
          className="bi5c__btn bi5c__btn--primary"
          data-testid="bi5c-run-sweep"
          onClick={triggerSweep}
          disabled={running}
        >
          {running ? 'Running sweep…' : 'Run sweep now'}
        </button>
      </header>

      {error && <div className="bi5c__err" data-testid="bi5c-error">{error}</div>}
      {toast && (
        <div className={`bi5c__err ${toast.kind === 'ok' ? 'bi5c__chip--pass' : ''}`}
             style={{ borderLeftColor: toast.kind === 'ok' ? '#F0B90B' : undefined,
                      color: toast.kind === 'ok' ? '#d8dde6' : undefined,
                      background: toast.kind === 'ok' ? 'rgba(240,185,11,0.06)' : undefined }}
             data-testid="bi5c-toast">
          {toast.msg}
        </div>
      )}

      {/* ── Stats strip ─────────────────────────────────────── */}
      <div className="bi5c__stats" data-testid="bi5c-stats">
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">Data-cert total</span>
          <span className="bi5c__stat-val">{total}</span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">PASS</span>
          <span className="bi5c__stat-val bi5c__stat-val--pass">{counts.pass}</span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">WARN</span>
          <span className="bi5c__stat-val bi5c__stat-val--warn">{counts.warn}</span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">FAIL</span>
          <span className="bi5c__stat-val bi5c__stat-val--fail">{counts.fail}</span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">Last sweep</span>
          <span className="bi5c__stat-val" style={{ fontSize: '13px' }}>
            {last
              ? `${last.processed}/${last.discovered}`
              : <span className="bi5c__stat-val--muted">none yet</span>}
          </span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">Last sweep at</span>
          <span className="bi5c__stat-val" style={{ fontSize: '13px' }}>
            {last ? fmtTs(last.finished_at || last.started_at) : '—'}
          </span>
        </div>
        <div className="bi5c__stat">
          <span className="bi5c__stat-label">Next auto-sweep</span>
          <span className="bi5c__stat-val" style={{ fontSize: '13px' }}>
            {fmtUtc(sweepStatus?.next_run_utc)}
          </span>
        </div>
      </div>

      {/* ── Data-cert table ─────────────────────────────────── */}
      <section className="bi5c__section" data-testid="bi5c-data-section">
        <div className="bi5c__section-hd">
          <h3>Data Certifications · per (symbol × window)</h3>
          <span className="bi5c__count">{allDataCertRows.length} windows</span>
        </div>
        <div className="bi5c__table" data-testid="bi5c-data-table">
          <div
            className="bi5c__row bi5c__row--head"
            role="row"
            style={{ gridTemplateColumns: '90px 220px 1.5fr 0.8fr 110px' }}
          >
            <span>Symbol</span>
            <span>Window</span>
            <span>Sub-scores</span>
            <span>Composite</span>
            <span>Verdict</span>
          </div>
          {allDataCertRows.length === 0 && !loading && (
            <div className="bi5c__empty" data-testid="bi5c-empty-data">
              No data-cert documents found.
            </div>
          )}
          {allDataCertRows.map((d, i) => {
            const subs = d.subscores || {};
            return (
              <div
                key={`${d.symbol}-${d.window_start_utc}-${i}`}
                className="bi5c__row"
                role="row"
                style={{ gridTemplateColumns: '90px 220px 1.5fr 0.8fr 110px' }}
                data-testid={`bi5c-data-row-${d.symbol}`}
              >
                <span className="bi5c__cell-sym">{d.symbol}</span>
                <span title={`${d.window_start_utc} → ${d.window_end_utc}`}>
                  {String(d.window_start_utc || '').slice(0, 10)}
                  {' → '}
                  {String(d.window_end_utc || '').slice(0, 10)}
                </span>
                <span style={{ fontSize: '11px', color: '#9ca3af' }}>
                  cov {(subs.cov ?? 0).toFixed(2)} · integ {(subs.integrity ?? 0).toFixed(2)} · price {(subs.price ?? 0).toFixed(2)} · dens {(subs.density ?? 0).toFixed(2)} · cont {(subs.continuity ?? 0).toFixed(2)}
                </span>
                <span>{(d.bi5_score ?? 0).toFixed(4)}</span>
                <span>
                  <span className={chipClass(d._verdict)}>{d._verdict}</span>
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Strategy-cert sweep history ─────────────────────── */}
      <section className="bi5c__section" data-testid="bi5c-sweep-section">
        <div className="bi5c__section-hd">
          <h3>Strategy Certification · sweep history</h3>
          <span className="bi5c__count">{sweepRuns.items.length} recent runs</span>
        </div>
        <div className="bi5c__table" data-testid="bi5c-sweep-table">
          <div
            className="bi5c__row bi5c__row--head"
            role="row"
            style={{ gridTemplateColumns: '170px 130px 95px 75px 75px 75px 80px 90px' }}
          >
            <span>Run started</span>
            <span>Trigger</span>
            <span>Discovered</span>
            <span>PASS</span>
            <span>WARN</span>
            <span>FAIL</span>
            <span>Skipped</span>
            <span>Duration</span>
          </div>
          {sweepRuns.items.length === 0 && !loading && (
            <div className="bi5c__empty" data-testid="bi5c-empty-sweep">
              No sweep runs yet. Click &quot;Run sweep now&quot; to trigger the first manual run.
            </div>
          )}
          {sweepRuns.items.map((r) => (
            <div
              key={r.run_id}
              className="bi5c__row"
              role="row"
              style={{ gridTemplateColumns: '170px 130px 95px 75px 75px 75px 80px 90px' }}
              data-testid={`bi5c-sweep-row-${r.run_id}`}
            >
              <span title={r.started_at}>{fmtUtc(r.started_at)}</span>
              <span style={{ color: r.trigger === 'auto_weekly' ? '#F0B90B' : '#9ca3af' }}>
                {r.trigger}
              </span>
              <span>{r.discovered}</span>
              <span style={{ color: '#F0B90B' }}>{r.pass_count}</span>
              <span style={{ color: '#f9b441' }}>{r.warn_count}</span>
              <span style={{ color: '#ef4444' }}>{r.fail_count}</span>
              <span style={{ color: '#9ca3af' }}>{r.skipped}</span>
              <span>{(r.duration_seconds || 0).toFixed(2)}s</span>
            </div>
          ))}
        </div>
      </section>

      <p className="bi5c__schema-tag" style={{ marginTop: '4px' }}>
        Auto-sweep cadence: <b>Sunday 03:00 UTC</b> ·
        ranker weights: bi5_cert_verdict 0.07 · bi5_slippage_score 0.03 ·
        manual trigger available to admins.
      </p>
    </div>
  );
}
