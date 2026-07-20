/*
 * StateTemplate — D7 §3.
 * Six-slot anatomy: icon · headline · purpose · actions · advanced footnote · framing.
 * Every non-happy state in the prototype uses this component.
 */
import type { LucideIcon } from 'lucide-react';
import { useWorkspaceStore } from '../workspace-state/store';

export interface StateTemplateProps {
  variant: 'empty' | 'loading' | 'error' | 'dormant' | 'replay-empty' | 'success';
  icon?: LucideIcon;
  headline: string;
  purpose?: string;
  primaryAction?: { label: string; onClick: () => void };
  secondaryLink?: { label: string; onClick: () => void };
  advancedFootnote?: string;
  code: string; // stable D7 code, e.g. "mc-empty-nothing-pending"
  tone?: 'ok' | 'warn' | 'crit' | 'advisory' | 'info' | 'dormant';
}

const toneToVar: Record<NonNullable<StateTemplateProps['tone']>, string> = {
  ok: 'var(--sig-ok)',
  warn: 'var(--sig-warn)',
  crit: 'var(--sig-crit)',
  advisory: 'var(--sig-advisory)',
  info: 'var(--sig-info)',
  dormant: 'var(--sig-dormant)',
};

const ariaLiveFor = (v: StateTemplateProps['variant']) =>
  v === 'error' ? 'assertive' : 'polite';

export const StateTemplate: React.FC<StateTemplateProps> = (p) => {
  const Icon = p.icon;
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const tone = p.tone ?? (p.variant === 'error' ? 'warn' : p.variant === 'dormant' ? 'dormant' : 'ok');
  const iconColor = toneToVar[tone];

  return (
    <div
      role="status"
      aria-live={ariaLiveFor(p.variant)}
      data-testid={`state-template-${p.code}`}
      className="flex flex-col items-start max-w-[480px] mx-auto text-left"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--stroke-1)',
        borderRadius: 'var(--radius-3)',
        padding: 'var(--space-6) var(--space-5)',
        gap: 'var(--space-4)',
      }}
    >
      {Icon && (
        <Icon size={24} strokeWidth={1.5} color={iconColor} aria-hidden="true" />
      )}
      <div style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)', lineHeight: 1.4 }}>
        {p.headline}
      </div>
      {p.purpose && (
        <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}>
          {p.purpose}
        </div>
      )}
      {(p.primaryAction || p.secondaryLink) && (
        <div className="flex gap-3 items-center" style={{ marginTop: 'var(--space-2)' }}>
          {p.primaryAction && (
            <button
              onClick={p.primaryAction.onClick}
              data-testid={`${p.code}-primary`}
              style={{
                fontSize: 'var(--font-body-sm)',
                color: 'var(--sig-info)',
                background: 'transparent',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              → {p.primaryAction.label}
            </button>
          )}
          {p.secondaryLink && (
            <>
              <span style={{ color: 'var(--content-lo)' }}>·</span>
              <button
                onClick={p.secondaryLink.onClick}
                data-testid={`${p.code}-secondary`}
                style={{
                  fontSize: 'var(--font-body-sm)',
                  color: 'var(--content-md)',
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                {p.secondaryLink.label}
              </button>
            </>
          )}
        </div>
      )}
      {advLens && p.advancedFootnote && (
        <div
          className="mono-num"
          style={{
            marginTop: 'var(--space-2)',
            fontSize: 'var(--font-caption)',
            color: 'var(--content-lo)',
          }}
        >
          {p.advancedFootnote}
        </div>
      )}
    </div>
  );
};
