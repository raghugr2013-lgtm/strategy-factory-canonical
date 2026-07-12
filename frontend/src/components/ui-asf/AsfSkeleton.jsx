/**
 * ASF · AsfSkeleton — Phase U-1 (C-11)
 * ----------------------------------------------------------------------------
 * Skeleton shimmer placeholder. Replaces spinners on read paths.
 *
 * Variants: 'line' | 'block' | 'kpi' | 'table-row'
 *
 * Tokens consumed: --asf-bg-surface-elevated, --asf-border-default,
 *                  --asf-radius-chip. Respects prefers-reduced-motion.
 */
import React from 'react';

const VARIANTS = new Set(['line', 'block', 'kpi', 'table-row']);

export default function AsfSkeleton({
  variant = 'line',
  width,
  height,
  className = '',
  testId,
  style,
  stagger,
  ...rest
}) {
  const v = VARIANTS.has(variant) ? variant : 'line';
  const inline = { ...(width ? { width } : null), ...(height ? { height } : null), ...style };
  // Phase U-3 — when `stagger` (0..N) is set, the asf-u3-interactions CSS layer
  // applies a per-index animation-delay so cards/tiles hydrate as a soft wave.
  const staggerAttr = stagger != null
    ? { 'data-asf-stagger': String(Math.min(7, Math.max(0, stagger | 0))) }
    : null;
  return (
    <span
      className={`asf-skeleton asf-skeleton--${v} ${className}`.trim()}
      data-testid={testId || `skeleton-${v}`}
      aria-busy="true"
      aria-live="polite"
      style={inline}
      {...staggerAttr}
      {...rest}
    />
  );
}

export { AsfSkeleton };
