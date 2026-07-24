/*
 * StrategyExplorer — Phase C: institutional portfolio-browse surface.
 *
 * Merges the prototype's visual language (prototype/src/surfaces/StrategyExplorer.tsx)
 * with the production wiring of the sibling Strategies surface:
 *
 *   • Visual language (prototype):
 *     - SurfaceHeader anatomy (eyebrow · headline · briefing · mono trailer)
 *     - Selected-row highlight (▸ arrow + info-blue tint on the id column)
 *     - Surface memory for last-opened passport id (Predictable Return)
 *     - Return crumb on activation (`back to explorer`)
 *     - Shared status-facet cascade via navigationStore.facets.status
 *     - Optional owner / hit% / policyFlag columns (rendered only when
 *       the adapter response actually carries them — pure additive)
 *
 *   • Production wiring (kept from Strategies.jsx):
 *     - Real API via fetchStrategies() with transparent fixture fallback
 *     - HKB banner surfaces imported legacy corpus when live inventory
 *       is empty (pre-VPS-activation)
 *     - StateTemplate empty-state carries the operator's next step
 *     - Facet vocabulary matches the real API contract
 *       (all/live/paper/archived) — the prototype's paused/reviewing
 *       states have no backend equivalent yet and are dropped.
 *
 * Coexistence contract:
 *   /c/strategies         → legacy Strategies surface (unchanged)
 *   /c/strategies/explorer → this new surface
 * The existing surface is untouched. Rollback = revert this commit.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Briefcase, LineChart, Sparkles } from 'lucide-react';
import { SurfaceHeader } from '../primitives/SurfaceHeader';
import { TableTile } from '../primitives/TableTile';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchStrategies } from '../adapters/factoryAdapter';
import { fetchKnowledgeStatistics } from '../adapters/strategyLabAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const STATUS_FILTERS = [
  { key: 'all',      label: 'all' },
  { key: 'live',     label: 'live' },
  { key: 'paper',    label: 'paper' },
  { key: 'archived', label: 'archived' },
];

const STATUS_TONE = {
  live: 'ok',
  paper: 'info',
  archived: 'dormant',
  paused: 'warn',
  reviewing: 'advisory',
  draft: 'dormant',
};

const fmt = (v, digits = 2) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

export const StrategyExplorer = () => {
  const nav = useNavigate();
  const loc = useLocation();

  const statusFacet    = useNavigationStore((s) => s.facets.status);
  const setFacet       = useNavigationStore((s) => s.setFacet);
  const saveSurface    = useNavigationStore((s) => s.saveSurface);
  const readSurface    = useNavigationStore((s) => s.readSurface);
  const setCrumb       = useNavigationStore((s) => s.setCrumb);
  const selectedStrategy = useWorkspaceStore((s) => s.selectedStrategy);
  const selectStrategy   = useWorkspaceStore((s) => s.selectStrategy);

  const [rows, setRows] = useState(null);
  const [kbStats, setKbStats] = useState(null);

  // Restore last-active row highlight from surface memory. Do NOT overwrite
  // a workspace-wide selection made elsewhere (Decision Identity precedence).
  useEffect(() => {
    const mem = readSurface(loc.pathname);
    if (mem?.activeId && !selectedStrategy) selectStrategy(mem.activeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc.pathname]);

  // Fetch on facet change (shared axis cascade).
  useEffect(() => {
    let live = true;
    setRows(null);
    fetchStrategies({ status: statusFacet }).then((r) => { if (live) setRows(r); });
    return () => { live = false; };
  }, [statusFacet]);

  // HKB stats (once, best-effort).
  useEffect(() => {
    let live = true;
    fetchKnowledgeStatistics().then((r) => { if (live && r?.payload) setKbStats(r.payload); });
    return () => { live = false; };
  }, []);

  const activate = (r) => {
    selectStrategy(r.id);
    saveSurface(loc.pathname, { activeId: r.id });
    setCrumb({
      path: loc.pathname,
      label: 'back to explorer',
      origin: 'explorer',
      originId: r.id,
    });
    nav(`/c/strategies/${encodeURIComponent(r.id)}`);
  };

  const legacyCount = kbStats?.total_strategies ?? 0;
  const families    = kbStats?.canonical_families ?? 0;

  // Detect optional fields once — if the adapter payload carries them we
  // render additional columns; otherwise we drop them silently. Keeps this
  // surface working against BOTH the current backend (5 fields) and any
  // future enriched contract (owner/hit%/policyFlag) without a redeploy.
  const hasOwner   = Array.isArray(rows) && rows.some((r) => typeof r.owner === 'string');
  const hasHitPct  = Array.isArray(rows) && rows.some((r) => typeof r.hitPct === 'number');
  const hasPolicy  = Array.isArray(rows) && rows.some((r) => r.policyFlag);

  const columns = [
    {
      key: 'id', label: 'id', sortable: true,
      render: (r) => (
        <span
          className="mono-num"
          style={{
            color: r.id === selectedStrategy ? 'var(--sig-info)' : 'var(--content-md)',
            fontWeight: r.id === selectedStrategy ? 500 : 400,
          }}
          data-testid={`strategy-explorer-id-${r.id}`}
        >
          {r.id === selectedStrategy ? '▸ ' : ''}{r.id}
        </span>
      ),
    },
    { key: 'name', label: 'strategy', sortable: true },
    ...(hasOwner ? [{ key: 'owner', label: 'owner', sortable: true }] : []),
    {
      key: 'sharpe', label: 'sharpe', align: 'right', sortable: true,
      render: (r) => <span className="mono-num">{fmt(r.sharpe, 2)}</span>,
    },
    {
      key: 'drawdown', label: 'dd %', align: 'right', sortable: true,
      render: (r) => <span className="mono-num">{fmt(r.drawdown, 1)}</span>,
    },
    ...(hasHitPct ? [{
      key: 'hitPct', label: 'hit %', align: 'right', sortable: true,
      render: (r) => <span className="mono-num">{fmt(r.hitPct, 0)}</span>,
    }] : []),
    {
      key: 'status', label: 'status', sortable: true,
      render: (r) => (
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <Chip tone={STATUS_TONE[r.status] ?? 'dormant'} label={r.status} showGlyph={false} />
          {hasPolicy && r.policyFlag && (
            <Chip tone="advisory" label="flagged" showGlyph={false}
                  testId={`strategy-explorer-policy-flag-${r.id}`} />
          )}
        </span>
      ),
    },
  ];

  const totalCount = Array.isArray(rows) ? rows.length : null;
  const trailer = totalCount === null ? 'loading…' : `${totalCount} strategies`;

  const isLoading = rows === null;
  const isEmpty   = Array.isArray(rows) && rows.length === 0;

  return (
    <section
      data-testid="strategy-explorer"
      style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
               display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
    >
      <SurfaceHeader
        eyebrow="Strategy Explorer · portfolio"
        headline="Every strategy. One table. Click through to a full passport."
        briefing="Sort by any column. The status facet cascades to every other surface. Selecting a row remembers your last-opened passport for a Predictable Return."
        status={trailer}
        testId="strategy-explorer-header"
      />

      <div
        data-testid="strategy-explorer-facet-bar"
        role="tablist"
        aria-label="Filter strategies by status"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span style={facetLegend}>status ·</span>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`strategy-explorer-facet-${f.key}`}
            role="tab"
            aria-selected={statusFacet === f.key}
            onClick={() => setFacet('status', f.key)}
            style={facetChip(statusFacet === f.key)}
          >
            {f.label}
          </button>
        ))}
        <span data-testid="strategy-explorer-cascade-hint"
              style={{ ...facetLegend, marginLeft: 'auto',
                       display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Briefcase size={12} /> cascade · status {statusFacet}
        </span>
      </div>

      {/* HKB banner (production-only). */}
      {legacyCount > 0 && (
        <Link
          to="/c/factory/curated"
          data-testid="strategy-explorer-hkb-banner"
          style={{
            display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
            padding: 'var(--space-3) var(--space-4)',
            background: 'var(--surface-2)', border: '1px solid var(--stroke-1)',
            borderRadius: 'var(--radius-2)', textDecoration: 'none', color: 'inherit',
          }}
        >
          <Sparkles size={14} color="var(--content-md)" aria-hidden />
          <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em',
                          textTransform: 'uppercase', color: 'var(--content-md)' }}>
            Historical Knowledge Base
          </span>
          <Chip tone="info" label={`${legacyCount} legacy`} showGlyph={false}
                testId="strategy-explorer-hkb-count" />
          <Chip tone="info" label={`${families} families`} showGlyph={false}
                testId="strategy-explorer-hkb-families" />
          <span style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                          color: 'var(--content-lo)' }}>
            View curated candidates →
          </span>
        </Link>
      )}

      {isLoading ? (
        <div style={{ color: 'var(--content-lo)' }}>Loading strategies…</div>
      ) : isEmpty ? (
        <StateTemplate
          variant="empty"
          code={`strategy-explorer-empty-${statusFacet}`}
          icon={LineChart}
          tone="dormant"
          headline={
            statusFacet === 'all'
              ? 'No strategies yet.'
              : `No ${statusFacet} strategies right now.`
          }
          purpose={
            legacyCount > 0
              ? `Live inventory is empty. ${legacyCount} legacy specimens live in the Historical KB — open the Curated Library above.`
              : statusFacet === 'all'
                ? 'Once strategies are backtested and promoted they appear here.'
                : 'Try a different status facet.'
          }
        />
      ) : (
        <TableTile
          caption={`strategies · ${rows.length}`}
          columns={columns}
          rows={rows}
          onRowActivate={activate}
          testId="strategy-explorer-table"
        />
      )}
    </section>
  );
};

// ─── styles ───────────────────────────────────────────────
const facetLegend = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const facetChip = (active) => ({
  background: active ? 'var(--sig-info)' : 'var(--surface-2)',
  color: active ? 'var(--surface-0)' : 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '4px 10px',
  fontFamily: 'ui-monospace, monospace',
  fontSize: 'var(--font-caption)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
});

export default StrategyExplorer;
