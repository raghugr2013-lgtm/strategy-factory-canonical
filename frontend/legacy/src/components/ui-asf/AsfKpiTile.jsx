/**
 * ASF · AsfKpiTile — Phase U-2 (C-07 unified KPI primitive)
 * ----------------------------------------------------------------------------
 * Single KPI tile: label (caption) + numeric value (mono) + optional verdict
 * dot + optional delta line. Replaces the five ad-hoc KPI strips on the
 * Dashboard, Trade Runner, Auto Factory, Prop Firm, and Portfolio screens.
 *
 * Props:
 *   label        — required, short uppercase caption (e.g. "EQUITY")
 *   value        — required, primary numeric/string value
 *   verdict      — optional 'success' | 'warn' | 'danger' | 'neutral' | 'info'
 *                  surfaces as a coloured dot beside the value
 *   delta        — optional secondary line (e.g. "+0.42 %")
 *   loading      — when true renders an AsfSkeleton in place of the value
 *   tone         — 'default' | 'sunken' (sunken uses --asf-bg-surface-sunken)
 *   testId       — explicit override; else derived from label
 *
 * Tokens consumed:
 *   --asf-bg-surface, --asf-border-default, --asf-radius-card,
 *   --asf-text-secondary (label), --asf-text-primary (value),
 *   --asf-font-mono (value), --asf-fs-caption / --asf-fs-h1, --asf-space-*.
 */
import React from 'react';
import AsfSkeleton from './AsfSkeleton';

function slug(s) {
  return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'kpi';
}

export default function AsfKpiTile({
  label,
  value,
  verdict,
  delta,
  loading = false,
  tone = 'default',
  className = '',
  testId,
  children,
  onClick,
  ...rest
}) {
  const tid = testId || `kpi-tile-${slug(label)}`;
  const clickable = typeof onClick === 'function';
  const cls = [
    'asf-kpi-tile',
    `asf-kpi-tile--${tone}`,
    clickable ? 'asf-clickable' : '',
    className,
  ].filter(Boolean).join(' ');
  const interactiveProps = clickable
    ? {
        role: 'button',
        tabIndex: 0,
        onClick,
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick(e);
          }
        },
      }
    : {};
  return (
    <div
      className={cls}
      data-testid={tid}
      style={clickable ? { position: 'relative' } : undefined}
      {...interactiveProps}
      {...rest}
    >
      <div className="asf-kpi-tile__label">{label}</div>
      <div className="asf-kpi-tile__value-row">
        {verdict && <span className="asf-kpi-tile__dot" data-verdict={verdict} aria-hidden="true" />}
        {loading
          ? <AsfSkeleton variant="line" width="60%" height={20} />
          : <span className="asf-kpi-tile__value asf-mono">{value}</span>}
      </div>
      {delta && <div className="asf-kpi-tile__delta asf-mono" data-verdict={verdict || 'neutral'}>{delta}</div>}
      {children}
    </div>
  );
}

export { AsfKpiTile };
