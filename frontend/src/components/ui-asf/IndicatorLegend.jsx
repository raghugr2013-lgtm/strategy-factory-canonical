/**
 * ASF · IndicatorLegend — Phase U-1 (+S2)
 * ----------------------------------------------------------------------------
 * One-line legend that explains which verdict colours mean what on the
 * current screen. Sits directly under the module title belt on every page
 * that uses verdict-coloured indicators.
 *
 * Props:
 *   screen   — short identifier for test-id grammar (e.g. 'dashboard',
 *              'explorer', 'mutate').
 *   items    — array of { verdict, label, letter? }. If omitted, the
 *              canonical 5-verdict legend is rendered.
 *   className — optional extra class.
 *
 * Tokens consumed: --asf-bg-surface-sunken, --asf-border-default,
 *                  --asf-accent-<verdict>, --asf-font-sans.
 */
import React from 'react';

const DEFAULT_ITEMS = [
  { verdict: 'success', label: 'Passed',     letter: 'P' },
  { verdict: 'warn',    label: 'Needs evidence', letter: 'W' },
  { verdict: 'danger',  label: 'Failed',     letter: 'F' },
  { verdict: 'neutral', label: 'Advisory',   letter: 'A' },
  { verdict: 'info',    label: 'Info',       letter: 'I' },
];

export default function IndicatorLegend({
  screen = 'screen',
  items = DEFAULT_ITEMS,
  className = '',
  ...rest
}) {
  return (
    <div
      className={`asf-legend ${className}`.trim()}
      data-testid={`indicator-legend-${screen}`}
      role="note"
      aria-label="Verdict colour legend"
      {...rest}
    >
      <span className="asf-legend__title">Legend</span>
      {items.map((it) => (
        <span key={it.verdict} className="asf-legend__item">
          <span className="asf-legend__dot" data-verdict={it.verdict} aria-hidden="true" />
          <span className="asf-legend__letter" aria-hidden="true">{it.letter || ''}</span>
          <span>{it.label}</span>
        </span>
      ))}
    </div>
  );
}

export { IndicatorLegend };
