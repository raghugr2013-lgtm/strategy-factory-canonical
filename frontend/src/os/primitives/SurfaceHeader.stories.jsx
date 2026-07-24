/*
 * SurfaceHeader.stories.jsx — Phase A gallery entry.
 *
 * Demonstrates the four canonical anatomies (headline only, with briefing,
 * with mono status trailer, with action slot) so surface authors can pick
 * the shape that matches their purpose.
 */
import React from 'react';
import { SurfaceHeader } from './SurfaceHeader';

export default {
  title: 'Primitives/SurfaceHeader',
  component: SurfaceHeader,
  parameters: { layout: 'padded' },
};

export const HeadlineOnly = () => (
  <SurfaceHeader
    eyebrow="Mission Control"
    headline="Today, the factory is calm."
  />
);

export const WithBriefing = () => (
  <SurfaceHeader
    eyebrow="Orchestrator"
    headline="Adaptive dispatch loop is live."
    briefing="The tick loop scored 133 candidates in the last minute. Six read-only tasks were dispatched; every autonomous writer is passive. This surface exists to make the tick decisions inspectable."
  />
);

export const WithStatusTrailer = () => (
  <SurfaceHeader
    eyebrow="Meta-Learning"
    headline="Emitting recommendations without applying them."
    briefing="Observational mode. Every cycle emits n_recommendations; none are auto-applied."
    status="observe · 6 cycles today · 0 applied"
  />
);

export const WithActions = () => (
  <SurfaceHeader
    eyebrow="Factory Cockpit"
    headline="Kill posture disarmed."
    briefing="Operator control point for all safety switches."
    status="ORCHESTRATOR_ENABLED=true"
    actions={
      <button
        style={{
          background: 'transparent',
          border: '1px solid var(--stroke-2)',
          color: 'var(--content-md)',
          borderRadius: 'var(--radius-1)',
          padding: '4px 12px',
          fontSize: 'var(--font-caption)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontFamily: 'inherit',
          cursor: 'pointer',
        }}
      >
        Refresh
      </button>
    }
  />
);
