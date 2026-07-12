/**
 * BI5 R1 · BI5 Health Panel
 * ----------------------------------------------------------------------------
 * Per-symbol BI5 ingest health surface mounted inside MonitoringSuite.
 *
 * Reads /api/diag/bi5/health and shows:
 *   • Roll-up strip — symbols tracked · OK / error / manual / no-data ·
 *     avg coverage % · total ticks stored
 *   • Sortable per-symbol table — Coverage % · Last BI5 Sync ·
 *     Last Gap Repair · Ticks Stored · Status · Health Score (reserved)
 *
 * Health Score column is *reserved* — populated by Phase 13 + Phase 14
 * once the Evidence + Trust engines land. Today it shows "—".
 */
import React, { useEffect, useState, useCallback } from 'react';
import './BI5HealthPanel.css';

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

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
  } catch (_) { return ts; }
}

function statusTone(s) {
  switch (s) {
    case 'ok':              return 'ok';
    case 'partial':         return 'warn';
    case 'fetched-no-new':  return 'info';
    case 'manual_only':     return 'muted';
    case 'error':           return 'danger';
    default:                return 'muted';
  }
}

// BI5 R2 / B-8 — per-symbol cert verdict chip class.
function certChip(v) {
  const u = (v || '').toUpperCase();
  if (u === 'PASS') return 'bi5h__cert bi5h__cert--pass';
  if (u === 'WARN') return 'bi5h__cert bi5h__cert--warn';
  if (u === 'FAIL') return 'bi5h__cert bi5h__cert--fail';
  return 'bi5h__cert bi5h__cert--muted';
}

export default function BI5HealthPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState('symbol');
  const [sortDir, setSortDir] = useState('asc');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/diag/bi5/health`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      setData(j);
    } catch (e) {
      setError(e.message || 'load_failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000); // refresh every 30 s
    return () => clearInterval(t);
  }, [load]);

  const sortedRows = (() => {
    const rows = data?.rows || [];
    const cp = [...rows];
    cp.sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      const cmp = (av == null && bv == null) ? 0
        : (av == null) ? 1
        : (bv == null) ? -1
        : (typeof av === 'number' && typeof bv === 'number') ? (av - bv)
        : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return cp;
  })();

  const headers = [
    { id: 'symbol',           label: 'Symbol' },
    { id: 'coverage_percent', label: 'Coverage %' },
    { id: 'last_bi5_sync',    label: 'Last BI5 Sync' },
    { id: 'last_gap_repair',  label: 'Last Gap Repair' },
    { id: 'ticks_stored',     label: 'Ticks Stored' },
    { id: 'status',           label: 'Status' },
    // BI5 R2 / B-8 — per-symbol data-cert verdict chip column.
    { id: 'data_cert_verdict', label: 'Data Cert' },
    { id: 'health_score_reserved', label: 'Health Score', reserved: true },
    { id: 'latency_ms',       label: 'Latency (ms)' },
  ];

  return (
    <div className="bi5h" data-testid="bi5-health-panel">
      <header className="bi5h__hd">
        <div className="bi5h__hd-row">
          <span className="bi5h__badge">BI5 R1</span>
          <h2 className="bi5h__title">BI5 Health</h2>
          <span className="bi5h__schema-tag">schema · {data?.ingest_version || 'r1-v1'}</span>
          <button
            type="button"
            className="bi5h__refresh"
            data-testid="bi5h-refresh"
            onClick={load}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
        <p className="bi5h__sub">
          Per-symbol BI5 ingest telemetry. Aggregates the extended
          <code> bi5_ingest_log</code> schema. <b>Health Score</b> is
          reserved for Phase 13 (Evidence) + Phase 14 (Trust) — shows
          <code> —</code> today.
        </p>
      </header>

      {/* Roll-up summary */}
      {data?.summary && (
        <div className="bi5h__summary" data-testid="bi5h-summary">
          <div className="bi5h__tile">
            <span className="bi5h__tile-label">Symbols tracked</span>
            <span className="bi5h__tile-val">{data.summary.symbols_tracked}</span>
          </div>
          <div className="bi5h__tile bi5h__tile--ok">
            <span className="bi5h__tile-label">OK</span>
            <span className="bi5h__tile-val">{data.summary.symbols_ok}</span>
          </div>
          <div className="bi5h__tile bi5h__tile--warn">
            <span className="bi5h__tile-label">Manual only</span>
            <span className="bi5h__tile-val">{data.summary.symbols_manual_only}</span>
          </div>
          <div className="bi5h__tile bi5h__tile--danger">
            <span className="bi5h__tile-label">Error</span>
            <span className="bi5h__tile-val">{data.summary.symbols_error}</span>
          </div>
          <div className="bi5h__tile bi5h__tile--muted">
            <span className="bi5h__tile-label">No data yet</span>
            <span className="bi5h__tile-val">{data.summary.symbols_no_data}</span>
          </div>
          <div className="bi5h__tile">
            <span className="bi5h__tile-label">Avg coverage</span>
            <span className="bi5h__tile-val">{data.summary.avg_coverage_pct}%</span>
          </div>
          <div className="bi5h__tile">
            <span className="bi5h__tile-label">Total ticks stored</span>
            <span className="bi5h__tile-val">{(data.summary.total_ticks_stored || 0).toLocaleString()}</span>
          </div>
        </div>
      )}

      {error && (
        <div className="bi5h__err" data-testid="bi5h-error">{error}</div>
      )}

      {/* Per-symbol table */}
      <div className="bi5h__table-wrap">
        <div
          className="bi5h__table"
          role="table"
          style={{ gridTemplateColumns: `repeat(${headers.length}, 1fr)` }}
        >
          <div className="bi5h__trow bi5h__trow--head" role="row">
            {headers.map(h => (
              <span
                key={h.id}
                role="columnheader"
                className="bi5h__cell-head"
                data-testid={`bi5h-col-${h.id}`}
                aria-sort={sortBy === h.id ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                tabIndex={0}
                onClick={() => {
                  if (sortBy === h.id) {
                    setSortDir(d => d === 'asc' ? 'desc' : 'asc');
                  } else {
                    setSortBy(h.id);
                    setSortDir('asc');
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    if (sortBy === h.id) {
                      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
                    } else {
                      setSortBy(h.id);
                      setSortDir('asc');
                    }
                  }
                }}
              >
                {h.label}
                {h.reserved && <span className="bi5h__reserved-tag">reserved</span>}
                {sortBy === h.id && <span className="bi5h__sort" aria-hidden="true">{sortDir === 'asc' ? '▲' : '▼'}</span>}
              </span>
            ))}
          </div>
          {sortedRows.length === 0 && !loading && (
            <div className="bi5h__empty" data-testid="bi5h-empty">
              No symbols registered for BI5 ingestion.
            </div>
          )}
          {sortedRows.map(r => (
            <div
              key={r.symbol}
              className="bi5h__trow"
              role="row"
              data-testid={`bi5h-row-${r.symbol}`}
            >
              <span role="cell" className="bi5h__cell-sym">{r.symbol}</span>
              <span role="cell" className="bi5h__cell-num">
                <span className="bi5h__cov-bar" style={{ width: `${Math.min(100, r.coverage_percent)}%` }} />
                <span className="bi5h__cov-val">{(r.coverage_percent || 0).toFixed(1)}%</span>
              </span>
              <span role="cell">{fmtTs(r.last_bi5_sync)}</span>
              <span role="cell">{fmtTs(r.last_gap_repair)}</span>
              <span role="cell" className="bi5h__cell-num">{(r.ticks_stored || 0).toLocaleString()}</span>
              <span role="cell">
                <span className={`bi5h__status bi5h__status--${statusTone(r.status)}`}>{r.status}</span>
              </span>
              <span role="cell" data-testid={`bi5h-cert-${r.symbol}`}>
                {r.data_cert_verdict ? (
                  <span
                    className={certChip(r.data_cert_verdict)}
                    title={r.data_cert_score != null ? `score ${(r.data_cert_score || 0).toFixed(4)}` : ''}
                  >
                    {r.data_cert_verdict}
                  </span>
                ) : (
                  <span className="bi5h__cert bi5h__cert--muted">—</span>
                )}
              </span>
              <span role="cell" className="bi5h__cell-reserved">
                {r.health_score_reserved == null ? '—' : r.health_score_reserved}
              </span>
              <span role="cell" className="bi5h__cell-num">{r.latency_ms || 0}</span>
            </div>
          ))}
        </div>
      </div>

      {data?.schema_note && (
        <p className="bi5h__note" data-testid="bi5h-schema-note">{data.schema_note}</p>
      )}
    </div>
  );
}
