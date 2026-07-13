/**
 * MarketDataWorkbench
 * --------------------------------------------------------------------------
 * Phase R3 — Market Data consolidation
 * Composes the previously-separate Manual Data Workbench, Data Maintenance,
 * and Data Backup sections into a single operator surface with sub-tabs.
 * Read-only composition; underlying components are unchanged.
 *
 * Preserves:
 *  - BID download workflow (Manual sub-tab)
 *  - BI5 download workflow (Manual sub-tab)
 *  - CSV upload workflow (Manual sub-tab)
 *  - Server Import workflow (Manual sub-tab)
 *  - Date-range download (Manual sub-tab)
 *  - Gap-fix workflow (Manual sub-tab)
 *  - Auto-maintenance scheduler (Automated sub-tab)
 *  - Archive import/export (Archive sub-tab — via OperatorEndpointPanel wrapper)
 */
import React, { Suspense, useEffect, useState } from 'react';
import { API_URL } from '../services/api';

const DataUpload         = React.lazy(() => import('./DataUpload'));
const DataMaintenance    = React.lazy(() => import('./DataMaintenancePanel'));
const { DataBackupPanel } = require('./OperatorParityPanels');


/**
 * Restoration Step 4c — BI5 readiness strip. One-line answer to the
 * operator's first question on this tab: "is data ready?" Reads the
 * existing /api/diag/bi5/health endpoint (read-only; JWT via global
 * fetch interceptor). Deep detail stays at diag/bi5-health.
 */
function Bi5ReadinessStrip() {
  const [summary, setSummary] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/diag/bi5/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setSummary(data.summary || null);
      } catch (_) {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (failed) return null; // strip is a pure affordance — never block the tab

  const ok      = summary ? summary.symbols_ok : null;
  const tracked = summary ? summary.symbols_tracked : null;
  const cov     = summary ? summary.avg_coverage_pct : null;
  const ticks   = summary ? summary.total_ticks_stored : null;
  const ready   = summary && tracked > 0 && ok === tracked;
  const partial = summary && ok > 0 && ok < tracked;
  const dotColor = ready ? 'var(--cmd-green, #34D399)' : partial ? 'var(--cmd-amber, #FBBF24)' : 'var(--cmd-ink-2, #A1A1AA)';
  const verdict  = !summary ? 'checking…' : ready ? 'READY' : partial ? 'PARTIAL' : 'NOT READY';

  return (
    <div
      data-testid="market-data-bi5-strip"
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 16px',
        borderBottom: '1px solid var(--cmd-line, #2A2D33)',
        background: 'var(--cmd-panel, #14171C)',
        fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)',
        fontFamily: 'JetBrains Mono, monospace',
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
      <span style={{ color: 'var(--cmd-ink-1, #E4E4E7)', letterSpacing: '0.08em' }}>
        BI5 DATA · {verdict}
      </span>
      {summary && (
        <span data-testid="market-data-bi5-strip-detail">
          {ok}/{tracked} symbols ok · avg coverage {Number(cov).toFixed(1)}% · {Number(ticks).toLocaleString()} ticks stored
        </span>
      )}
      <div style={{ flex: 1 }} />
      <span style={{ fontSize: 10 }}>detail → Diagnostics · BI5 Health</span>
    </div>
  );
}

const TABS = [
  { id: 'manual',    label: 'Manual',    description: 'BID · BI5 · CSV · Server Import · Date-Range · Gap-Fix' },
  { id: 'automated', label: 'Automated', description: 'Auto-maintenance scheduler · coverage · backfill' },
  { id: 'archive',   label: 'Archive',   description: 'Import / export full data archives' },
];

export default function MarketDataWorkbench() {
  const [tab, setTab] = useState('manual');

  return (
    <section
      data-testid="market-data-workbench"
      className="asf-section"
      aria-label="Market Data Workbench"
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px',
          borderBottom: '1px solid var(--cmd-line, #2A2D33)',
          background: 'var(--cmd-panel, #14171C)',
        }}
      >
        <div style={{ flex: 1 }}>
          <h2
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'var(--cmd-ink-1, #E4E4E7)',
              margin: 0,
            }}
          >
            Market Data
          </h2>
          <p
            style={{
              fontSize: 11,
              color: 'var(--cmd-ink-2, #A1A1AA)',
              margin: '4px 0 0',
            }}
          >
            Historical data ingestion · coverage · archive. BID + BI5 + CSV + Server + Gap-Fix all preserved.
          </p>
        </div>
      </header>

      {/* Restoration Step 4c — "is data ready?" answered before sub-tabs. */}
      <Bi5ReadinessStrip />

      <nav
        role="tablist"
        aria-label="Market Data sub-sections"
        style={{
          display: 'flex',
          gap: 4,
          padding: '8px 16px',
          borderBottom: '1px solid var(--cmd-line, #2A2D33)',
          background: 'var(--cmd-panel, #14171C)',
        }}
      >
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              data-testid={`market-data-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              title={t.description}
              style={{
                padding: '6px 12px',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                borderRadius: 4,
                border: '1px solid',
                borderColor: active ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-line, #2A2D33)',
                background: active ? 'rgba(122,184,255,0.12)' : 'transparent',
                color: active ? 'var(--cmd-accent, #7AB8FF)' : 'var(--cmd-ink-1, #E4E4E7)',
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      <div style={{ padding: 0 }}>
        <Suspense fallback={<div style={{ padding: 24, fontSize: 11, color: 'var(--cmd-ink-2)' }}>Loading…</div>}>
          {tab === 'manual'    && <DataUpload />}
          {tab === 'automated' && <DataMaintenance />}
          {tab === 'archive'   && <DataBackupPanel />}
        </Suspense>
      </div>
    </section>
  );
}
