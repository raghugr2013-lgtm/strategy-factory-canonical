/*
 * StrategyExplorer — E1 · Strategy Experience.
 * Grid + table hybrid: hero table of every strategy with sparkline preview,
 * status chip, and click-through to Strategy Passport.
 */
import { useNavigate } from 'react-router-dom';
import { Briefcase } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { TableTile, type TableColumn } from '../primitives/TableTile';
import { Chip, type ChipTone } from '../primitives/Chip';
import { useScenarioFixture, type StrategyRow } from '../gallery/scenarioFixtures';

const statusTone: Record<StrategyRow['status'], ChipTone> = {
  live: 'ok',
  paper: 'info',
  paused: 'warn',
  reviewing: 'advisory',
};

export const StrategyExplorer: React.FC = () => {
  const fx = useScenarioFixture();
  const nav = useNavigate();

  const cols: TableColumn<StrategyRow>[] = [
    { key: 'id',          label: 'id',      sortable: true,
      render: (r) => <span className="mono-num" style={{ color: 'var(--content-md)' }}>{r.id}</span> },
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
        status={`${fx.strategies.length} strategies`}
        testId="strategies-header"
      />

      <div
        data-testid="strategies-status-strip"
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
        {Object.entries(counts).map(([status, count]) => (
          <Chip
            key={status}
            tone={statusTone[status as StrategyRow['status']]}
            label={`${count} ${status}`}
            showGlyph={false}
            testId={`strategies-status-${status}`}
          />
        ))}
        <div
          style={{
            marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
            color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
            textTransform: 'uppercase', letterSpacing: '0.06em',
          }}
        >
          <Briefcase size={12} /> portfolio
        </div>
      </div>

      <TableTile
        caption="strategies"
        columns={cols}
        rows={fx.strategies}
        onRowActivate={(r) => nav(`/c/strategies/${r.id}`)}
        testId="strategies-table"
      />
    </div>
  );
};
