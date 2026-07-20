/*
 * MetricBlock — Bible §7.11.1, D1 §7.2.
 * Concept A/B/C variants:
 *   - A (default): eyebrow + hero value + delta + advanced footnote
 *   - B (neural):  same anatomy with subtle info-glow rail
 *   - C (executive/gold): larger hero value, gold accent bar
 *
 * Supports canonical states: happy, loading (skeleton), empty, error, dormant.
 */
import { motion } from 'framer-motion';
import { AlertTriangle, MinusCircle, Sparkles } from 'lucide-react';
import { useMotionEnabled, fadeInUp } from './motion';
import { Chip } from './Chip';
import { StateTemplate } from './StateTemplate';
import { useWorkspaceStore } from '../workspace-state/store';

export type MetricVariant = 'A' | 'B' | 'C';
export type MetricState = 'happy' | 'loading' | 'empty' | 'error' | 'dormant';

export interface MetricBlockProps {
  variant?: MetricVariant;
  eyebrow: string;
  value: string;
  unit?: string;
  deltaLabel?: string;
  deltaTone?: 'ok' | 'warn' | 'crit' | 'advisory' | 'info' | 'dormant';
  footnote?: string;             // shown only when Advanced Lens is on
  state?: MetricState;
  testId?: string;
}

const variantAccent: Record<MetricVariant, string> = {
  A: 'var(--stroke-2)',
  B: 'var(--sig-info)',
  C: 'var(--accent-gold)',
};

const Skeleton: React.FC<{ w: string; h?: number }> = ({ w, h = 12 }) => (
  <div
    aria-hidden="true"
    style={{
      width: w, height: h,
      background: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3) 50%, var(--surface-2) 100%)',
      backgroundSize: '200% 100%',
      animation: 'sf-skeleton 1.6s var(--ease-standard) infinite',
      borderRadius: 'var(--radius-1)',
    }}
  />
);

export const MetricBlock: React.FC<MetricBlockProps> = ({
  variant = 'A',
  eyebrow,
  value,
  unit,
  deltaLabel,
  deltaTone = 'ok',
  footnote,
  state = 'happy',
  testId,
}) => {
  const motionEnabled = useMotionEnabled();
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const code = eyebrow.toLowerCase().replace(/\W+/g, '-');

  const frame: React.CSSProperties = {
    position: 'relative',
    background: 'var(--surface-1)',
    border: '1px solid var(--stroke-1)',
    borderLeft: `2px solid ${variantAccent[variant]}`,
    borderRadius: 'var(--radius-3)',
    padding: 'var(--space-5)',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
    boxShadow: variant === 'B' ? 'var(--glow-neural)' : undefined,
    opacity: state === 'dormant' ? 0.6 : 1,
    filter: state === 'dormant' ? 'saturate(0.6)' : undefined,
  };

  if (state === 'error') {
    return (
      <div style={frame} data-testid={testId ?? `metric-${code}`}>
        <StateTemplate
          variant="error"
          code={`${code}-error`}
          icon={AlertTriangle}
          tone="crit"
          headline="This metric could not be computed."
          purpose="A dependent worker is offline. We are retrying every 60s."
          advancedFootnote="ingestion@v22 · retry #3 · next @ 15:04Z"
        />
      </div>
    );
  }
  if (state === 'empty') {
    return (
      <div style={frame} data-testid={testId ?? `metric-${code}`}>
        <StateTemplate
          variant="empty"
          code={`${code}-empty`}
          icon={MinusCircle}
          tone="dormant"
          headline="No data in the selected window."
          purpose="Widen the time window or check ingestion coverage."
        />
      </div>
    );
  }

  const body = (
    <>
      <div
        style={{
          fontSize: 'var(--font-caption)',
          color: 'var(--content-lo)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
        }}
      >
        {variant === 'C' && <Sparkles size={12} color="var(--accent-gold)" aria-hidden="true" />}
        <span>{eyebrow}</span>
      </div>
      <div className="mono-num" style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
        {state === 'loading' ? (
          <Skeleton w="140px" h={variant === 'C' ? 36 : 28} />
        ) : (
          <>
            <span
              style={{
                fontSize: variant === 'C' ? 'var(--font-metric-hero)' : 'var(--font-h2)',
                color: 'var(--content-hi)',
                fontWeight: 500,
                lineHeight: 1,
              }}
            >
              {value}
            </span>
            {unit && (
              <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-lo)' }}>
                {unit}
              </span>
            )}
          </>
        )}
      </div>
      {state === 'loading' ? (
        <Skeleton w="90px" h={10} />
      ) : (
        deltaLabel && <Chip tone={deltaTone} label={deltaLabel} showGlyph={false} />
      )}
      {advLens && footnote && (
        <div
          className="mono-num"
          style={{
            fontSize: 'var(--font-caption)',
            color: 'var(--content-lo)',
            borderTop: '1px solid var(--stroke-1)',
            paddingTop: 'var(--space-2)',
            marginTop: 'var(--space-2)',
          }}
        >
          {footnote}
        </div>
      )}
    </>
  );

  const El: React.ElementType = motionEnabled ? motion.div : 'div';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};

  return (
    <El data-testid={testId ?? `metric-${code}`} style={frame} {...motionProps}>
      {body}
    </El>
  );
};
