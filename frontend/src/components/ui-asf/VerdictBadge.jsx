/**
 * ASF · VerdictBadge — Phase U-1 (+S1 base layer)
 * ----------------------------------------------------------------------------
 * Filled verdict badge for status columns and standalone state pills.
 *
 * Props:
 *   verdict   — 'success' | 'warn' | 'danger' | 'neutral' | 'info'  (required)
 *   label     — display string (e.g. 'Passed', 'Stale', 'Diverged')
 *   density   — 'compact' | 'default' | 'spacious'  (default: 'default')
 *               compact density shows P/W/F/A/I letter prefix for colour-blind
 *               safety.
 *   showDot   — boolean, default true: prefix a coloured dot
 *   testId    — explicit test-id override (else derived as
 *               `verdict-badge-<verdict>-<slug>`)
 *
 * Tokens consumed: --asf-accent-<verdict>, --asf-accent-<verdict>-fill,
 *                  --asf-radius-chip, --asf-font-sans, --asf-fs-caption.
 */
import React from 'react';

const LETTER = { success: 'P', warn: 'W', danger: 'F', neutral: 'A', info: 'I' };
const SR_TONE = { success: 'Pass', warn: 'Warning', danger: 'Fail', neutral: 'Neutral', info: 'Info' };

function slugify(label) {
  return String(label || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'badge';
}

export default function VerdictBadge({
  verdict = 'neutral',
  label,
  density = 'default',
  showDot = true,
  className = '',
  testId,
  children,
  ...rest
}) {
  const text = label != null ? label : children;
  const tid = testId || `verdict-badge-${verdict}-${slugify(text)}`;
  return (
    <span
      className={`asf-vbadge ${className}`.trim()}
      data-verdict={verdict}
      data-density={density}
      data-testid={tid}
      {...rest}
    >
      {showDot && <span className="asf-vbadge__dot" aria-hidden="true" />}
      <span className="asf-vbadge__letter" aria-hidden="true">{LETTER[verdict] || ''}</span>
      <span className="sr-only">{SR_TONE[verdict] || 'Status'}: </span>
      <span className="asf-vbadge__label">{text}</span>
    </span>
  );
}

export { VerdictBadge };
