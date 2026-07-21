/*
 * LineageBar — Bible §10.1 · one hop up + one hop down.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { ChevronRight, GitBranch } from 'lucide-react';
import { StateTemplate } from './StateTemplate';

const NodeChip = ({ n, onOpen, muted, strong }) => (
  <button data-testid={`lineage-node-${n.id}`}
          onClick={onOpen ? () => onOpen(n) : undefined}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                   background: strong ? 'var(--surface-2)' : 'transparent',
                   border: `1px solid ${strong ? 'var(--stroke-3)' : 'var(--stroke-2)'}`,
                   borderRadius: 'var(--radius-1)',
                   color: muted ? 'var(--content-lo)' : 'var(--content-md)',
                   fontSize: 'var(--font-caption)', textTransform: 'uppercase',
                   letterSpacing: '0.06em', padding: '4px 8px',
                   cursor: onOpen ? 'pointer' : 'default', fontFamily: 'inherit' }}>
    {n.kind && <span style={{ color: 'var(--content-lo)' }}>{n.kind} ·</span>}
    <span className="mono-num">{n.label}</span>
  </button>
);

export const LineageBar = ({ self, ancestors = [], descendants = [], onOpen, replayEmpty, testId }) => {
  if (replayEmpty) {
    return (
      <StateTemplate variant="replay-empty" code="lineage-replay-empty" icon={GitBranch} tone="dormant"
                     headline="This artefact didn't exist at the replayed time."
                     purpose="Move the time window forward or open the current view." />
    );
  }
  if (!ancestors.length && !descendants.length) {
    return (
      <div data-testid={testId ?? 'lineage-bar-root'}
           style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                    padding: 'var(--space-3)', background: 'var(--surface-1)',
                    border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)' }}>
        <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                       textTransform: 'uppercase', letterSpacing: '0.08em' }}>root generation</span>
        <NodeChip n={self} strong />
      </div>
    );
  }
  return (
    <div data-testid={testId ?? 'lineage-bar'}
         style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                  padding: 'var(--space-3)', background: 'var(--surface-1)',
                  border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)',
                  overflowX: 'auto' }}>
      {ancestors.map((a) => (
        <span key={a.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <NodeChip n={a} onOpen={onOpen} muted />
          <ChevronRight size={12} color="var(--content-lo)" />
        </span>
      ))}
      <NodeChip n={self} strong />
      {descendants.map((d) => (
        <span key={d.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <ChevronRight size={12} color="var(--content-lo)" />
          <NodeChip n={d} onOpen={onOpen} muted />
        </span>
      ))}
    </div>
  );
};
