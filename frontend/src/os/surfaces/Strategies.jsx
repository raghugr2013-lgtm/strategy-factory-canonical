/*
 * Strategy Explorer — S5 minimal.
 * refs DESIGN_FREEZE_v1.0.md §1.4
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart } from 'lucide-react';
import { FacetBar } from '../features/FacetBar';
import { TableTile } from '../primitives/TableTile';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchStrategies } from '../adapters/factoryAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';

const STATUS_OPTIONS = [
  { key: 'all', label: 'All' },
  { key: 'live', label: 'Live' },
  { key: 'paper', label: 'Paper' },
  { key: 'archived', label: 'Archived' },
];

const STATUS_TONE = { live: 'ok', paper: 'info', archived: 'dormant' };

const columns = [
  { key: 'id', label: 'id', sortable: true },
  { key: 'name', label: 'name', sortable: true },
  { key: 'status', label: 'status', sortable: true,
    render: (r) => <Chip tone={STATUS_TONE[r.status]} label={r.status} /> },
  { key: 'sharpe', label: 'sharpe', align: 'right', sortable: true,
    render: (r) => r.sharpe.toFixed(2) },
  { key: 'drawdown', label: 'drawdown', align: 'right', sortable: true,
    render: (r) => `${r.drawdown}%` },
];

export const Strategies = () => {
  const statusFacet = useNavigationStore((s) => s.facets.status);
  const [rows, setRows] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    setRows(null);
    fetchStrategies({ status: statusFacet }).then((r) => { if (live) setRows(r); });
    return () => { live = false; };
  }, [statusFacet]);

  return (
    <section data-testid="strategies"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                       letterSpacing: '0.1em', textTransform: 'uppercase',
                       marginBottom: 'var(--space-2)' }}>Strategies</div>
        <h1 data-testid="strategies-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, color: 'var(--content-hi)' }}>
          Every strategy. One table. Click through to a full passport.
        </h1>
        <p data-testid="strategies-briefing"
           style={{ margin: 0, maxWidth: 720, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          Sort by any column. Facet by status — the plane you build here is remembered when you
          return from a passport.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
        <FacetBar axis="status" options={STATUS_OPTIONS} testIdPrefix="strategies-facet" />
        <span data-testid="strategies-cascade-hint" className="mono-num"
              style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                       color: 'var(--content-lo)', textTransform: 'uppercase',
                       letterSpacing: '0.08em' }}>
          cascade · status {statusFacet}
        </span>
      </div>

      {rows === null ? (
        <div style={{ color: 'var(--content-lo)' }}>Loading strategies…</div>
      ) : rows.length === 0 ? (
        <StateTemplate variant="empty" code="strategies-empty" icon={LineChart} tone="dormant"
                       headline="No strategies match this facet."
                       purpose="Clear the status filter to see everything." />
      ) : (
        <TableTile caption={`Strategies · ${rows.length}`}
                   columns={columns}
                   rows={rows}
                   onRowActivate={(r) => navigate(`/c/strategies/${encodeURIComponent(r.id)}`)}
                   testId="strategies-table" />
      )}
    </section>
  );
};
