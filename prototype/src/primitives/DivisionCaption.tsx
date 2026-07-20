/*
 * DivisionCaption — D4 §5.1.1, §5.2.
 * Sectional heading that opens with the *purpose* of a workforce division,
 * followed by an optional status glyph. Never uses raw team names alone.
 */
import type { LucideIcon } from 'lucide-react';

export interface DivisionCaptionProps {
  eyebrow: string;      // e.g. "Master Bot · Workforce"
  purpose: string;      // e.g. "Coordinates every research plan."
  icon?: LucideIcon;
  status?: string;      // e.g. "v55 · plan #47 · 3/7"
  testId?: string;
}

export const DivisionCaption: React.FC<DivisionCaptionProps> = ({
  eyebrow, purpose, icon: Icon, status, testId,
}) => (
  <header
    data-testid={testId ?? `division-caption-${eyebrow.toLowerCase().replace(/\W+/g, '-')}`}
    style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
  >
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
        fontSize: 'var(--font-caption)',
        color: 'var(--content-lo)',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}
    >
      {Icon && <Icon size={12} strokeWidth={1.5} aria-hidden="true" />}
      <span>{eyebrow}</span>
      {status && (
        <>
          <span aria-hidden="true">·</span>
          <span className="mono-num">{status}</span>
        </>
      )}
    </div>
    <h2
      style={{
        margin: 0,
        fontSize: 'var(--font-h3)',
        fontWeight: 500,
        color: 'var(--content-hi)',
        lineHeight: 1.25,
        maxWidth: '52ch',
      }}
    >
      {purpose}
    </h2>
  </header>
);
