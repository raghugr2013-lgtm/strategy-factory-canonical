/*
 * SurfaceHeader — reusable per-surface header primitive.
 *
 * Every operator surface opens with purpose before status
 * (Bible §2.1). This primitive enforces a consistent anatomy so that
 * "eyebrow · headline · briefing · mono trailer" reads the same on every
 * surface without prop-drilling styling.
 *
 * refs DESIGN_FREEZE_v1.0.md §7.11 · prototype/src/surfaces/SurfaceHeader.tsx
 */
import React from 'react';

export const SurfaceHeader = ({
  eyebrow,
  headline,
  briefing,
  status,   // optional mono trailer (e.g. "orchestrator · running · 1h uptime")
  testId,
  actions,  // optional slot for surface-level buttons (right-aligned)
}) => (
  <header
    data-testid={testId ?? 'surface-header'}
    style={{
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 'var(--space-4)',
    }}
  >
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', maxWidth: '76ch' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          fontSize: 'var(--font-caption)',
          color: 'var(--content-lo)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
        }}
      >
        <span data-testid={`${testId ?? 'surface-header'}-eyebrow`}>{eyebrow}</span>
        {status && (
          <>
            <span aria-hidden="true">·</span>
            <span
              className="mono-num"
              data-testid={`${testId ?? 'surface-header'}-status`}
            >
              {status}
            </span>
          </>
        )}
      </div>
      <h1
        data-testid={`${testId ?? 'surface-header'}-headline`}
        style={{
          margin: 0,
          fontSize: 'var(--font-h2)',
          fontWeight: 500,
          color: 'var(--content-hi)',
          lineHeight: 1.2,
        }}
      >
        {headline}
      </h1>
      {briefing && (
        <p
          data-testid={`${testId ?? 'surface-header'}-briefing`}
          style={{
            margin: 0,
            fontSize: 'var(--font-body-sm)',
            color: 'var(--content-md)',
            lineHeight: 1.5,
          }}
        >
          {briefing}
        </p>
      )}
    </div>
    {actions && (
      <div
        data-testid={`${testId ?? 'surface-header'}-actions`}
        style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}
      >
        {actions}
      </div>
    )}
  </header>
);

export default SurfaceHeader;
