/*
 * SignatureFrame — D5 §2. Editorial gallery-card framing.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';

const TONE = {
  ok: 'var(--sig-ok)', info: 'var(--sig-info)', warn: 'var(--sig-warn)', crit: 'var(--sig-crit)',
  advisory: 'var(--sig-advisory)', dormant: 'var(--sig-dormant)', gold: 'var(--accent-gold)',
};

export const SignatureFrame = ({ tone = 'info', icon: Icon, caption, children, testId }) => (
  <section data-testid={testId ?? 'signature-frame'}
           style={{ position: 'relative', background: 'var(--surface-1)',
                    border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-3)',
                    padding: 'var(--space-5)', overflow: 'hidden' }}>
    <div aria-hidden style={{ position: 'absolute', top: 0, left: 0, height: 2, width: 40, background: TONE[tone] }} />
    {Icon && (
      <div aria-hidden style={{ position: 'absolute', top: 'var(--space-3)', right: 'var(--space-3)',
                                color: TONE[tone], opacity: 0.6 }}>
        <Icon size={14} strokeWidth={1.5} />
      </div>
    )}
    {caption && (
      <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-3)' }}>
        {caption}
      </div>
    )}
    {children}
  </section>
);
