/*
 * TableTile — Bible §7.11.3, §7.9.
 * Dense virtualised-style row list. Prototype does not virtualise DOM (fixture
 * volumes are small) but observes all visual rules: uppercase 11px column
 * caption, tabular-nums values, hover-actions, column-sort, drill-through.
 */
import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, ArrowDown, ArrowUp, MinusCircle } from 'lucide-react';
import { useMotionEnabled, fadeInUp } from './motion';
import { StateTemplate } from './StateTemplate';
import { useWorkspaceStore } from '../workspace-state/store';

export type Cell = string | number | React.ReactNode;

export interface TableColumn<Row> {
  key: keyof Row & string;
  label: string;
  align?: 'left' | 'right';
  sortable?: boolean;
  render?: (row: Row) => Cell;
}

export type TableState = 'happy' | 'loading' | 'empty' | 'error' | 'dormant';

export interface TableTileProps<Row extends Record<string, any>> {
  caption: string;
  columns: TableColumn<Row>[];
  rows: Row[];
  state?: TableState;
  onRowActivate?: (row: Row) => void;
  testId?: string;
}

const densityRowPad: Record<'compact' | 'cozy' | 'cinema', string> = {
  compact: '6px 12px',
  cozy: '10px 14px',
  cinema: '14px 16px',
};

export function TableTile<Row extends Record<string, any>>({
  caption, columns, rows, state = 'happy', onRowActivate, testId,
}: TableTileProps<Row>) {
  const motionEnabled = useMotionEnabled();
  const density = useWorkspaceStore((s) => s.density);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const code = caption.toLowerCase().replace(/\W+/g, '-');

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      if (av === bv) return 0;
      return av > bv ? dir : -dir;
    });
  }, [rows, sortKey, sortDir]);

  const clickSort = (col: TableColumn<Row>) => {
    if (!col.sortable) return;
    if (sortKey === col.key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortKey(col.key); setSortDir('asc'); }
  };

  const El: React.ElementType = motionEnabled ? motion.section : 'section';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};

  return (
    <El
      data-testid={testId ?? `table-${code}`}
      {...motionProps}
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--stroke-1)',
        borderRadius: 'var(--radius-3)',
        overflow: 'hidden',
        opacity: state === 'dormant' ? 0.6 : 1,
      }}
    >
      <div
        style={{
          padding: 'var(--space-3) var(--space-4)',
          fontSize: 'var(--font-caption)',
          color: 'var(--content-lo)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          borderBottom: '1px solid var(--stroke-1)',
          display: 'flex', justifyContent: 'space-between',
        }}
      >
        <span>{caption}</span>
        <span className="mono-num">{rows.length} rows</span>
      </div>

      {state === 'error' ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <StateTemplate
            variant="error" code={`${code}-error`} icon={AlertTriangle} tone="crit"
            headline="Table load failed."
            purpose="The evidence store returned an error."
          />
        </div>
      ) : state === 'empty' || (state === 'happy' && !rows.length) ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <StateTemplate
            variant="empty" code={`${code}-empty`} icon={MinusCircle} tone="dormant"
            headline="No rows match this filter."
            purpose="Clear a facet or widen the time window."
          />
        </div>
      ) : state === 'loading' ? (
        <div style={{ padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {[0,1,2,3,4].map((i) => (
            <div key={i}
              aria-hidden="true"
              style={{
                height: 14,
                background: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3) 50%, var(--surface-2) 100%)',
                backgroundSize: '200% 100%',
                animation: 'sf-skeleton 1.6s var(--ease-standard) infinite',
                borderRadius: 'var(--radius-1)',
              }}
            />
          ))}
        </div>
      ) : (
        <div role="table" aria-label={caption}>
          <div
            role="row"
            style={{
              display: 'grid',
              gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))`,
              padding: '8px 12px',
              borderBottom: '1px solid var(--stroke-1)',
              background: 'var(--surface-2)',
            }}
          >
            {columns.map((col) => (
              <button
                key={col.key}
                role="columnheader"
                data-testid={`${code}-col-${col.key}`}
                onClick={() => clickSort(col)}
                style={{
                  textAlign: col.align === 'right' ? 'right' : 'left',
                  fontSize: 'var(--font-caption)',
                  color: 'var(--content-lo)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  background: 'transparent', border: 'none', padding: 0,
                  fontFamily: 'inherit',
                  cursor: col.sortable ? 'pointer' : 'default',
                  display: 'inline-flex', gap: 4, alignItems: 'center',
                  justifyContent: col.align === 'right' ? 'flex-end' : 'flex-start',
                }}
              >
                {col.label}
                {sortKey === col.key && (
                  sortDir === 'asc'
                    ? <ArrowUp size={10} />
                    : <ArrowDown size={10} />
                )}
              </button>
            ))}
          </div>
          <div role="rowgroup">
            {sorted.map((row, ri) => (
              <div
                role="row"
                key={ri}
                tabIndex={0}
                data-testid={`${code}-row-${ri}`}
                onClick={() => onRowActivate?.(row)}
                onKeyDown={(e) => { if (e.key === 'Enter') onRowActivate?.(row); }}
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))`,
                  padding: densityRowPad[density],
                  borderBottom: '1px solid var(--stroke-1)',
                  cursor: onRowActivate ? 'pointer' : 'default',
                  transition: `background-color var(--dur-fast) var(--ease-standard)`,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {columns.map((col) => (
                  <div
                    role="cell"
                    key={col.key}
                    className={typeof row[col.key] === 'number' ? 'mono-num' : ''}
                    style={{
                      textAlign: col.align === 'right' ? 'right' : 'left',
                      fontSize: 'var(--font-body-sm)',
                      color: 'var(--content-hi)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {col.render ? col.render(row) : (row[col.key] as any)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </El>
  );
}
