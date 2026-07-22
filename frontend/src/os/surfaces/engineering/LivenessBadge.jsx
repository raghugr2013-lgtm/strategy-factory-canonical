/*
 * LivenessBadge — Sprint 3 Phase-2 pill shared across Engineering live surfaces.
 * refs UX-Review-2026-07-22 (Engineering Workspace) · Bible §5.1 signal palette
 *
 * Four verdicts: LIVE · PARTIAL LIVE · GATED · ERROR.
 * Never renders synthetic data. When the payload is empty we still render the
 * real interface with the badge switched to PARTIAL LIVE and an operator-
 * legible reason.
 */
import React from 'react';

const TONES = {
  'live':         { color: 'var(--sig-ok)',   label: 'LIVE'         },
  'partial-live': { color: 'var(--sig-warn)', label: 'PARTIAL LIVE' },
  'gated':        { color: 'var(--sig-dormant)', label: 'GATED'    },
  'error':        { color: 'var(--sig-crit)', label: 'ERROR'        },
};

export const LivenessBadge = ({ liveness = 'partial-live', reason, testId = 'liveness-badge' }) => {
  const t = TONES[liveness] || TONES['partial-live'];
  return (
    <span data-testid={testId}
          title={reason || undefined}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '3px 10px', borderRadius: 999,
            background: `color-mix(in oklab, ${t.color} 12%, transparent)`,
            border: `1px solid color-mix(in oklab, ${t.color} 40%, transparent)`,
            color: t.color,
            fontSize: 'var(--font-caption)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor' }} />
      {t.label}
    </span>
  );
};

export const FreezeCaption = ({ testId = 'freeze-caption' }) => (
  <div data-testid={testId}
       style={{
         fontSize: 'var(--font-caption)',
         color: 'var(--content-lo)',
         letterSpacing: '0.08em',
         textTransform: 'uppercase',
       }}>
    Backend Feature Freeze · v1.1.0-stage4
  </div>
);
