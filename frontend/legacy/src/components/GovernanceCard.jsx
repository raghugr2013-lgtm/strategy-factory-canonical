import React, { useEffect, useState } from 'react';
import { ShieldCheck, ChartLineUp, CircleNotch } from '@phosphor-icons/react';
import { AsfKpiTile, AsfEmptyState, AsfDetailDrawer } from './ui-asf';

// Phase 30.1 · Δ5 — Governance Card (read-only institutional visibility).
//
// Operator constraint:
//   • Minimal · institutional · read-only-first.
//   • Surfaces survivor universe count, replacement queue depth, and
//     deployment-ready count. Polls three READ endpoints; no writes,
//     no controls, no operational clutter.
//
// Phase 30.2 addition (single read-only pill, no authority duplication):
//   • Adds a one-line "Universe" summary so operator can see the
//     allowed-ecosystem boundary alongside survivor metrics. The
//     UniverseGovernancePanel remains the sole read/write authority.
//
// Endpoints (all GET, read-only):
//   • /api/governance/survivor-registry
//   • /api/governance/replacement-candidates
//   • /api/deployment/registry
//   • /api/governance/universe              ← Phase 30.2 summary

const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

async function fetchJson(path) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Accept': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} on ${path}`);
  return res.json();
}

function Pill({ label, value, color = 'text-zinc-100', testId, hint }) {
  return (
    <div data-testid={testId} className="flex flex-col" title={hint}>
      <span className="text-[9px] text-zinc-500 uppercase tracking-[0.14em] font-mono">
        {label}
      </span>
      <span className={`font-mono ${color} text-base font-semibold`}>
        {value ?? '—'}
      </span>
    </div>
  );
}

export default function GovernanceCard() {
  const [universe, setUniverse] = useState(null);
  const [replacement, setReplacement] = useState(null);
  const [deployment, setDeployment] = useState(null);
  const [allowedUniverse, setAllowedUniverse] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  // U-3 drill-through state. `drill` is one of: null | 'universe' |
  // 'replacements' | 'deployment'. We open AsfDetailDrawer with the
  // corresponding payload.
  const [drill, setDrill] = useState(null);

  const refresh = async () => {
    setError(null);
    try {
      const [u, r, d, au] = await Promise.all([
        fetchJson('/api/governance/survivor-registry'),
        fetchJson('/api/governance/replacement-candidates'),
        fetchJson('/api/deployment/registry'),
        fetchJson('/api/governance/universe').catch(() => null),
      ]);
      setUniverse(u);
      setReplacement(r);
      setDeployment(d);
      setAllowedUniverse(au);
      setRefreshedAt(new Date().toISOString());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // Light polling (60s) — read-only governance visibility, no urgency.
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, []);

  const activeCount = universe?.active_count ?? 0;
  const cap = universe?.cap ?? 0;
  const headroom = universe?.headroom ?? 0;
  const advisoryReplacements = replacement?.advisory_replacements || [];
  const eligibleReplacements = (replacement?.would_execute_if_enabled || []).length;
  const totalReplacements = advisoryReplacements.length;
  const deploymentReady = deployment?.count ?? 0;
  const bi5Verified = deployment?.bi5_verified ?? 0;

  return (
    <div
      data-testid="governance-card"
      className="asf-section asf-u2-panel card-premium p-4 border border-zinc-800/80 bg-zinc-950/40 mb-4"
    >
      <div className="asf-section__hd flex items-center justify-between mb-3">
        <div className="asf-legacy-title flex items-center gap-2">
          <ShieldCheck size={14} weight="fill" className="text-emerald-400" />
          <h3 className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-300">
            Governance · Phase 30.1
          </h3>
          <span className="text-[9px] font-mono text-zinc-600 uppercase tracking-wider">
            read-only
          </span>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions flex items-center gap-2 text-[10px] font-mono text-zinc-500">
          {loading && <CircleNotch size={11} className="animate-spin" />}
          {refreshedAt && !loading && (
            <span data-testid="governance-card-refreshed">
              refreshed {new Date(refreshedAt).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3">
          <AsfEmptyState
            slug="governance-card-error"
            testId="governance-card-error"
            title="Governance failed to load"
            body={error}
            action={{ label: 'Retry', onClick: refresh, testId: 'governance-card-error-retry' }}
          />
        </div>
      )}

      <div className="asf-kpi-grid">
        <AsfKpiTile
          label="Survivor Universe"
          value={`${activeCount} / ${cap}`}
          verdict="info"
          testId="governance-pill-universe"
          title="Active strategies in elite / portfolio_worthy / deployment_ready"
          onClick={() => setDrill('universe')}
        />
        <AsfKpiTile
          label="Headroom"
          value={headroom}
          verdict={headroom > 0 ? 'success' : 'warn'}
          testId="governance-pill-headroom"
          title="Survivor cap minus active count"
        />
        <AsfKpiTile
          label="Replacement Queue"
          value={`${eligibleReplacements} / ${totalReplacements}`}
          verdict={eligibleReplacements > 0 ? 'warn' : 'neutral'}
          testId="governance-pill-replacement"
          title="Eligible / advisory replacement candidates · click to drill through"
          onClick={() => setDrill('replacements')}
        />
        <AsfKpiTile
          label="Deployment Ready"
          value={deploymentReady}
          verdict={deploymentReady > 0 ? 'success' : 'neutral'}
          testId="governance-pill-deployment"
          title="Strategies at lifecycle stage = deployment_ready · click to drill through"
          onClick={() => setDrill('deployment')}
        />
        <AsfKpiTile
          label="BI5 Verified"
          value={bi5Verified}
          verdict="neutral"
          testId="governance-pill-bi5"
          title="Deployment-ready strategies with BI5 realism passed"
        />
      </div>

      {universe && (
        <div className="mt-3 pt-3 border-t border-zinc-800/60 flex items-center gap-3 flex-wrap text-[10px] font-mono text-zinc-500">
          <span data-testid="governance-stage-breakdown" className="flex items-center gap-1.5">
            <ChartLineUp size={11} weight="bold" />
            stage-mix:
            {Object.entries(universe.by_stage_counts || {}).map(([s, n]) => (
              <span key={s} className="text-zinc-400">
                {s} <span className="text-zinc-200">{n}</span>
              </span>
            ))}
          </span>
          {universe.over_cap && (
            <span className="text-amber-300">universe over cap</span>
          )}
        </div>
      )}

      {/* Phase 30.2 — read-only allowed-universe summary (no authority duplication).
          UniverseGovernancePanel remains the sole read/write surface. */}
      {allowedUniverse && (
        <div
          data-testid="governance-allowed-universe-summary"
          className="mt-2 pt-2 border-t border-zinc-800/40 flex items-center gap-1.5 text-[10px] font-mono text-zinc-500"
        >
          <span className="text-zinc-600 uppercase tracking-wider">universe:</span>
          <span className="text-cyan-300">
            {(allowedUniverse.pairs || []).length} pairs
          </span>
          <span className="text-zinc-700">·</span>
          <span className="text-cyan-300">
            {(allowedUniverse.timeframes || []).length} TFs
          </span>
          <span className="text-zinc-700">·</span>
          <span className="text-cyan-300">
            {(allowedUniverse.styles || []).length} styles
          </span>
          <span className="text-zinc-700">·</span>
          <span className="text-zinc-400">
            floor {Number(allowedUniverse.exploration_floor_pct ?? 0).toFixed(0)}%
          </span>
        </div>
      )}

      {/* U-3 — Drill-through detail drawer. */}
      <AsfDetailDrawer
        open={drill !== null}
        onClose={() => setDrill(null)}
        testId="governance-detail-drawer"
        subtitle="Governance · drill-through"
        title={
          drill === 'universe'     ? 'Survivor Universe'
          : drill === 'replacements' ? 'Replacement Queue'
          : drill === 'deployment'   ? 'Deployment Ready'
          : ''
        }
      >
        {drill === 'universe' && (
          <div data-testid="drill-universe">
            <div style={{ fontSize: 11, color: 'var(--cmd-ink-2, #94a3b8)', marginBottom: 12 }}>
              {activeCount} of {cap} survivor slots in use — {headroom} headroom.
            </div>
            <pre style={{
              fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--cmd-ink-1, #cbd5e1)',
              background: 'var(--cmd-surface-2, #1f2937)', padding: 10, borderRadius: 4,
              overflow: 'auto', maxHeight: '60vh',
            }}>
              {JSON.stringify(universe || {}, null, 2)}
            </pre>
          </div>
        )}
        {drill === 'replacements' && (
          <div data-testid="drill-replacements">
            <div style={{ fontSize: 11, color: 'var(--cmd-ink-2, #94a3b8)', marginBottom: 12 }}>
              {eligibleReplacements} eligible / {totalReplacements} advisory candidates.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(advisoryReplacements || []).slice(0, 50).map((c, i) => (
                <div
                  key={c.id || c.strategy_id || i}
                  data-testid={`drill-replacement-row-${i}`}
                  style={{
                    padding: 8, borderRadius: 4,
                    background: 'var(--cmd-surface-2, #1f2937)',
                    fontSize: 11, fontFamily: 'JetBrains Mono',
                    color: 'var(--cmd-ink-1, #cbd5e1)',
                  }}
                >
                  {c.strategy_id || c.id || `row ${i + 1}`} · {c.reason || c.lifecycle_stage || '—'}
                </div>
              ))}
              {(advisoryReplacements || []).length === 0 && (
                <div style={{ fontSize: 11, color: 'var(--cmd-ink-3, #64748b)' }}>No advisory candidates.</div>
              )}
            </div>
          </div>
        )}
        {drill === 'deployment' && (
          <div data-testid="drill-deployment">
            <div style={{ fontSize: 11, color: 'var(--cmd-ink-2, #94a3b8)', marginBottom: 12 }}>
              {deploymentReady} deployment-ready, {bi5Verified} BI5-verified.
            </div>
            <pre style={{
              fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--cmd-ink-1, #cbd5e1)',
              background: 'var(--cmd-surface-2, #1f2937)', padding: 10, borderRadius: 4,
              overflow: 'auto', maxHeight: '60vh',
            }}>
              {JSON.stringify(deployment || {}, null, 2)}
            </pre>
          </div>
        )}
      </AsfDetailDrawer>
    </div>
  );
}
