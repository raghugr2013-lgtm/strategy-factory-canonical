/**
 * ASF · VerdictChip — Phase U-1 (+S1 base layer)
 * ----------------------------------------------------------------------------
 * Outlined verdict chip for inline use inside table rows and module headers.
 *
 * Same prop surface as VerdictBadge but renders an outline rather than a
 * fill — used when the chip sits adjacent to other content (table rows,
 * sentence-flow contexts) and a fill would be visually heavy.
 *
 * Tokens consumed: --asf-accent-<verdict>, --asf-accent-<verdict>-hover,
 *                  --asf-radius-chip, --asf-font-sans, --asf-fs-caption.
 */
import React from 'react';

const LETTER = { success: 'P', warn: 'W', danger: 'F', neutral: 'A', info: 'I' };
const SR_TONE = { success: 'Pass', warn: 'Warning', danger: 'Fail', neutral: 'Neutral', info: 'Info' };

function slugify(label) {
  return String(label || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'chip';
}

export default function VerdictChip({
  verdict = 'neutral',
  label,
  density = 'default',
  showDot = true,
  onClick,
  className = '',
  testId,
  children,
  ...rest
}) {
  const text = label != null ? label : children;
  const tid = testId || `verdict-chip-${verdict}-${slugify(text)}`;
  const interactive = typeof onClick === 'function';
  const Tag = interactive ? 'button' : 'span';
  const tagProps = interactive
    ? { type: 'button', onClick, style: { background: 'transparent', cursor: 'pointer' } }
    : {};
  return (
    <Tag
      className={`asf-vchip ${className}`.trim()}
      data-verdict={verdict}
      data-density={density}
      data-testid={tid}
      {...tagProps}
      {...rest}
    >
      {showDot && <span className="asf-vchip__dot" aria-hidden="true" />}
      <span className="asf-vchip__letter" aria-hidden="true">{LETTER[verdict] || ''}</span>
      <span className="sr-only">{SR_TONE[verdict] || 'Status'}: </span>
      <span className="asf-vchip__label">{text}</span>
    </Tag>
  );
}

export { VerdictChip };
