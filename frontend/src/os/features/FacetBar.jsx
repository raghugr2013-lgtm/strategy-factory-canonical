/*
 * FacetBar — F1. Reads/writes navigationStore.facets on a chosen axis.
 * refs DESIGN_FREEZE_v1.0.md §1.5 shared facet plane · Bible §7.4a
 */
import React from 'react';
import { useNavigationStore } from '../workspace-state/navigationStore';

export const FacetBar = ({ axis, options, testIdPrefix }) => {
  const value = useNavigationStore((s) => s.facets[axis]);
  const setFacet = useNavigationStore((s) => s.setFacet);
  const prefix = testIdPrefix ?? `facet-${axis}`;

  return (
    <div data-testid={`${prefix}-bar`}
         role="tablist"
         aria-label={`${axis} facet`}
         style={{ display: 'inline-flex', gap: 4, background: 'var(--surface-1)',
                  border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-1)',
                  padding: 2 }}>
      {options.map((opt) => {
        const selected = value === opt.key;
        return (
          <button key={opt.key}
                  data-testid={`${prefix}-${opt.key}`}
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setFacet(axis, opt.key)}
                  style={{ background: selected ? 'var(--surface-2)' : 'transparent',
                           color: selected ? 'var(--content-hi)' : 'var(--content-md)',
                           borderTop: `1px solid ${selected ? 'var(--sig-info)' : 'transparent'}`,
                           border: 'none',
                           padding: '4px 10px', fontSize: 'var(--font-caption)',
                           textTransform: 'uppercase', letterSpacing: '0.08em',
                           fontFamily: 'inherit', cursor: 'pointer', borderRadius: 3,
                           transition: 'background var(--dur-fast) var(--ease-standard)' }}>
            {opt.label}
            {opt.count !== undefined && (
              <span className="mono-num" style={{ marginLeft: 6, color: 'var(--content-lo)' }}>
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};
