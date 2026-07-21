/*
 * StateTemplate — D7 §3 six-slot anatomy.
 * refs DESIGN_FREEZE_v1.0.md §1.3 · D7 · prototype/src/primitives/StateTemplate.tsx
 */
import React from 'react';
import { useWorkspaceStore } from '../workspace-state/store';

const TONE = {
  ok: 'var(--sig-ok)', warn: 'var(--sig-warn)', crit: 'var(--sig-crit)',
  advisory: 'var(--sig-advisory)', info: 'var(--sig-info)', dormant: 'var(--sig-dormant)',
};

const ariaLiveFor = (v) => (v === 'error' ? 'assertive' : 'polite');

export const StateTemplate = ({
  variant, icon: Icon, headline, purpose, primaryAction, secondaryLink, advancedFootnote, code, tone,
}) => {
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const resolvedTone = tone ?? (variant === 'error' ? 'warn' : variant === 'dormant' ? 'dormant' : 'ok');
  const iconColor = TONE[resolvedTone];

  return (
    <div role="status"
         aria-live={ariaLiveFor(variant)}
         data-testid={`state-template-${code}`}
         style={{
           display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
           maxWidth: 480, textAlign: 'left',
           background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
           borderRadius: 'var(--radius-3)',
           padding: 'var(--space-6) var(--space-5)', gap: 'var(--space-4)',
         }}>
      {Icon && <Icon size={24} strokeWidth={1.5} color={iconColor} aria-hidden />}
      <div style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)', lineHeight: 1.4 }}>
        {headline}
      </div>
      {purpose && (
        <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}>
          {purpose}
        </div>
      )}
      {(primaryAction || secondaryLink) && (
        <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', marginTop: 'var(--space-2)' }}>
          {primaryAction && (
            <button onClick={primaryAction.onClick}
                    data-testid={`${code}-primary`}
                    style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
                             fontSize: 'var(--font-body-sm)', color: 'var(--sig-info)', fontFamily: 'inherit' }}>
              → {primaryAction.label}
            </button>
          )}
          {secondaryLink && (
            <>
              <span style={{ color: 'var(--content-lo)' }}>·</span>
              <button onClick={secondaryLink.onClick}
                      data-testid={`${code}-secondary`}
                      style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
                               fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', fontFamily: 'inherit' }}>
                {secondaryLink.label}
              </button>
            </>
          )}
        </div>
      )}
      {advLens && advancedFootnote && (
        <div className="mono-num"
             style={{ marginTop: 'var(--space-2)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)' }}>
          {advancedFootnote}
        </div>
      )}
    </div>
  );
};
