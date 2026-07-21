/*
 * DangerRibbon — top-of-viewport hazard indicator (Bible §14.2 · D8 §4.I I9).
 * refs DESIGN_FREEZE_v1.0.md §1.5 danger ribbon
 *
 * Only renders when kill posture is armed. Occupies its own grid row above
 * the header so no chrome shifts when it appears.
 */
import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { useWorkspaceStore } from '../workspace-state/store';

export const DangerRibbon = () => {
  const armed = useWorkspaceStore((s) => s.killPostureArmed);
  if (!armed) return null;
  return (
    <div data-testid="danger-ribbon"
         role="alert"
         style={{
           background: 'var(--sig-crit)',
           color: '#0a0202',
           padding: 'var(--space-2) var(--space-5)',
           fontSize: 'var(--font-caption)',
           letterSpacing: '0.1em',
           textTransform: 'uppercase',
           fontWeight: 700,
           display: 'flex',
           alignItems: 'center',
           gap: 'var(--space-2)',
         }}>
      <AlertTriangle size={14} strokeWidth={2.5} />
      DANGER · Kill posture armed · Deliberate freeze in effect
    </div>
  );
};
