/*
 * StrategyExplorer — E1 · Strategy Experience. Phase 5-wired:
 *   • Status facet reads from + writes to `navigationStore.facets.status`
 *     (facet cascade with Approvals/Timeline).
 *   • The active row (last-opened passport) is written to surface
 *     memory so returning here highlights the row (Predictable Return).
 *   • Row activation sets Decision Identity + drops a return-crumb.
 */
import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Briefcase } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { TableTile, type TableColumn } from '../primitives/TableTile';
import { Chip, type ChipTone } from '../primitives/Chip';
import { useScenarioFixture, type StrategyRow } from '../gallery/scenarioFixtures';
import { useNavigationStore, type StrategyStatusFacet } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const statusTone: Record<StrategyRow['status'], ChipTone> = {
  live: 'ok',
  paper: 'info',
  paused: 'warn',
  reviewing: 'advisory',
};

const STATUS_FILTERS: Array<{ key: StrategyStatusFacet; label: string }> = [
  { key: 'all',       label: 'all' },
  { key: 'live',      label: 'live' },
  { key: 'paper',     label: 'paper' },
  { key: 'paused',    label: 'paused' },
  { key: 'reviewing', label: 'reviewing' },
];

export const StrategyExplorer: React.FC = () => {
  const fx = useScenarioFixture();
  const nav = useNavigate();
  const loc = useLocation();

  const statusFacet    = useNavigationStore((s) => s.facets.status);
  const setFacet       = useNavigationStore((s) => s.setFacet);
  const saveSurface    = useNavigationStore((s) => s.saveSurface);
  const readSurface    = useNavigationStore((s) => s.readSurface);
  const setCrumb       = useNavigationStore((s) => s.setCrumb);
  const selectedStrategy = useWorkspaceStore((s) => s.selectedStrategy);
  const selectStrategy   = useWorkspaceStore((s) => s.selectStrategy);

  // Restore last active id highlight (memory), but do NOT overwrite
  // an id set by another surface (Decision Identity is workspace-wide).
  useEffect(() => {
    const mem = readSurface<{ activeId: string }>(loc.pathname);
    if (mem?.activeId && !selectedStrategy) selectStrategy(mem.activeId);
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = statusFacet === 'all'
    ? fx.strategies
    : fx.strategies.filter((s) => s.status === statusFacet);

  const activate = (r: StrategyRow) => {
    selectStrategy(r.id);
    saveSurface(loc.pathname, { activeId: r.id });
    setCrumb({
      path: loc.pathname,
      label: 'back to explorer',
      origin: 'explorer',
      originId: r.id,
    });
    nav(`/c/strategies/${r.id}`);
  };

  const cols: TableColumn<StrategyRow>[] = [
    { key: 'id',          label: 'id',      sortable: true,
      render: (r) => (
        <span className="mono-num"
          style={{
            color: r.id === selectedStrategy ? 'var(--sig-info)' : 'var(--content-md)',
            fontWeight: r.id === selectedStrategy ? 500 : 400,
          }}
        >
          {r.id === selectedStrategy ? '▸ ' : ''}{r.id}
        </span>
      )
    },
    { key: 'name',        label: 'strategy', sortable: true },
    { key: 'owner',       label: 'owner',    sortable: true },
    { key: 'sharpe',      label: 'sharpe',   sortable: true, align: 'right',
      render: (r) => <span className="mono-num">{r.sharpe.toFixed(2)}</span> },
    { key: 'drawdownPct', label: 'dd %',     sortable: true, align: 'right',
      render: (r) => <span className="mono-num">{r.drawdownPct.toFixed(1)}</span> },
    { key: 'hitPct',      label: 'hit %',    sortable: true, align: 'right',
      render: (r) => <span className="mono-num">{r.hitPct}</span> },
    { key: 'status',      label: 'status',   sortable: true,
      render: (r) => (
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <Chip tone={statusTone[r.status]} label={r.status} showGlyph={false} />
          {r.policyFlag && <Chip tone="advisory" label="flagged" showGlyph={false} testId={`policy-flag-${r.id}`} />}
        </span>
      ),
    },
  ];

  const counts = fx.strategies.reduce<Record<string, number>>((acc, s) => {
    acc[s.status] = (acc[s.status] ?? 0) + 1; return acc;
  }, {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Strategy Explorer · portfolio"
        headline="Every strategy. One table. Click through to a full passport."
        briefing="Sort by any column. Flagged rows carry an unresolved policy or upstream concern; open the passport to see the full trail."
        status={`${filtered.length} of ${fx.strategies.length} strategies`}
        testId="strategies-header"
      />

      <div
        data-testid="strategies-facet-bar"
        role="tablist"
        aria-label="Filter strategies by status"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span
          style={{
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          status ·
        </span>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`strategies-facet-${f.key}`}
            role="tab"
            aria-selected={statusFacet === f.key}
            onClick={() => setFacet('status', f.key)}
            style={{
              background: statusFacet === f.key ? 'var(--sig-info)' : 'var(--surface-2)',
              color: statusFacet === f.key ? 'var(--surface-0)' : 'var(--content-md)',
              border: '1px solid var(--stroke-2)',
              borderRadius: 'var(--radius-1)',
              padding: '4px 10px',
              fontFamily: 'ui-monospace, monospace',
              fontSize: 'var(--font-caption)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              cursor: 'pointer',
            }}
          >
            {f.label} {f.key !== 'all' && counts[f.key] ? `· ${counts[f.key]}` : ''}
          </button>
        ))}
        <span
          data-testid="strategies-cascade-hint"
          style={{
            marginLeft: 'auto', fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}
        >
          <Briefcase size={12} /> cascade · status {statusFacet}
        </span>
      </div>

      <TableTile
        caption="strategies"
        columns={cols}
        rows={filtered}
        onRowActivate={activate}
        testId="strategies-table"
      />
    </div>
  );
};
