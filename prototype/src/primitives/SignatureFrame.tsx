/*
 * SignatureFrame — D5 §2.
 * A minimalist framing device that gives chart tiles and signature graphics
 * an editorial "gallery card" feel: dark surface, hairline stroke, optional
 * tone bar top-left and small icon top-right. No decorative shadows.
 */
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export type SignatureTone = 'ok' | 'info' | 'warn' | 'crit' | 'advisory' | 'dormant' | 'gold';

const toneVar: Record<SignatureTone, string> = {
  ok: 'var(--sig-ok)',
  info: 'var(--sig-info)',
  warn: 'var(--sig-warn)',
  crit: 'var(--sig-crit)',
  advisory: 'var(--sig-advisory)',
  dormant: 'var(--sig-dormant)',
  gold: 'var(--accent-gold)',
};

export interface SignatureFrameProps {
  tone?: SignatureTone;
  icon?: LucideIcon;
  caption?: string;
  children: ReactNode;
  testId?: string;
}

export const SignatureFrame: React.FC<SignatureFrameProps> = ({
  tone = 'info',
  icon: Icon,
  caption,
  children,
  testId,
}) => (
  <section
    data-testid={testId ?? 'signature-frame'}
    style={{
      position: 'relative',
      background: 'var(--surface-1)',
      border: '1px solid var(--stroke-1)',
      borderRadius: 'var(--radius-3)',
      padding: 'var(--space-5)',
      overflow: 'hidden',
    }}
  >
    <div
      aria-hidden="true"
      style={{
        position: 'absolute',
        top: 0, left: 0, height: 2, width: 40,
        background: toneVar[tone],
      }}
    />
    {Icon && (
      <div
        aria-hidden="true"
        style={{
          position: 'absolute', top: 'var(--space-3)', right: 'var(--space-3)',
          color: toneVar[tone], opacity: 0.6,
        }}
      >
        <Icon size={14} strokeWidth={1.5} />
      </div>
    )}
    {caption && (
      <div
        style={{
          fontSize: 'var(--font-caption)',
          color: 'var(--content-lo)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: 'var(--space-3)',
        }}
      >
        {caption}
      </div>
    )}
    {children}
  </section>
);
