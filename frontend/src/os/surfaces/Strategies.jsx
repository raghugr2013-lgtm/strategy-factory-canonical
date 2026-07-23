/*
 * Strategy Explorer — S5 minimal.
 * refs DESIGN_FREEZE_v1.0.md §1.4
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { LineChart, Sparkles } from 'lucide-react';
import { FacetBar } from '../features/FacetBar';
import { TableTile } from '../primitives/TableTile';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchStrategies } from '../adapters/factoryAdapter';
import { fetchKnowledgeStatistics as fetchKnowledgeStats } from '../adapters/strategyLabAdapter';
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
  const [kbStats, setKbStats] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    setRows(null);
    fetchStrategies({ status: statusFacet }).then((r) => { if (live) setRows(r); });
    return () => { live = false; };
  }, [statusFacet]);

  useEffect(() => {
    let live = true;
    fetchKnowledgeStats().then((r) => { if (live && r?.payload) setKbStats(r.payload); });
    return () => { live = false; };
  }, []);

  const legacyCount = kbStats?.total_strategies ?? 0;
  const families = kbStats?.canonical_families ?? 0;

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

      {/* Historical Knowledge Base banner — surfaces the imported HKB corpus
          when the live production inventory is still empty (pre-VPS-activation). */}
      {legacyCount > 0 && (
        <Link to="/c/factory/curated" data-testid="strategies-hkb-banner"
              style={{
                display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                padding: 'var(--space-3) var(--space-4)',
                background: 'var(--surface-2)', border: '1px solid var(--stroke-1)',
                borderRadius: 'var(--radius-2)', textDecoration: 'none', color: 'inherit',
              }}>
          <Sparkles size={14} color="var(--content-md)" aria-hidden />
          <span style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.08em',
                          textTransform: 'uppercase', color: 'var(--content-md)' }}>
            Historical Knowledge Base
          </span>
          <Chip tone="info" label={`${legacyCount} legacy`} testId="strategies-hkb-count" />
          <Chip tone="info" label={`${families} families`} testId="strategies-hkb-families" />
          <span style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                          color: 'var(--content-lo)' }}>
            View curated candidates →
          </span>
        </Link>
      )}

      {rows === null ? (
        <div style={{ color: 'var(--content-lo)' }}>Loading strategies…</div>
      ) : rows.length === 0 ? (
        <StateTemplate variant="empty" code="strategies-empty" icon={LineChart} tone="dormant"
                       headline="No live strategies yet."
                       purpose={legacyCount > 0
                         ? `Live inventory is empty (pre-VPS-activation). ${legacyCount} legacy specimens live in the Historical KB — open the Curated Library above.`
                         : "Clear the status filter to see everything."} />
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
