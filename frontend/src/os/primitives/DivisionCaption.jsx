/*
 * DivisionCaption — D4 §5.1.1, §5.2. Purpose-first sectional heading.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';

export const DivisionCaption = ({ eyebrow, purpose, icon: Icon, status, testId }) => (
  <header data-testid={testId ?? `division-caption-${eyebrow.toLowerCase().replace(/\W+/g, '-')}`}
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                  fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                  textTransform: 'uppercase', letterSpacing: '0.08em' }}>
      {Icon && <Icon size={12} strokeWidth={1.5} aria-hidden />}
      <span>{eyebrow}</span>
      {status && <><span aria-hidden>·</span><span className="mono-num">{status}</span></>}
    </div>
    <h2 style={{ margin: 0, fontSize: 'var(--font-h3)', fontWeight: 500,
                 color: 'var(--content-hi)', lineHeight: 1.25, maxWidth: '52ch' }}>
      {purpose}
    </h2>
  </header>
);
