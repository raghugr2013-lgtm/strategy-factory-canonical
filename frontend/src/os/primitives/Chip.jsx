/*
 * Chip — Bible §7.1 · P·W·F·A·I taxonomy with colour-blind letter glyph.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · prototype/src/primitives/Chip.tsx
 */
import React from 'react';

// Tone → glyph mapping (P·W·F·A·I taxonomy, Bible §5.1).
// P Passing → ok · W Working → info · F Failed → crit · A Attention → warn/advisory · I Idle → dormant
const GLYPH = { ok: 'P', info: 'W', warn: 'A', crit: 'F', advisory: 'A', dormant: 'I' };
const BG = {
  ok: 'rgba(61,220,132,0.14)',
  info: 'rgba(78,161,243,0.14)',
  warn: 'rgba(240,180,41,0.14)',
  crit: 'rgba(255,91,91,0.14)',
  advisory: 'rgba(184,147,95,0.14)',
  dormant: 'rgba(107,118,132,0.14)',
};
const FG = {
  ok: 'var(--sig-ok)',
  info: 'var(--sig-info)',
  warn: 'var(--sig-warn)',
  crit: 'var(--sig-crit)',
  advisory: 'var(--sig-advisory)',
  dormant: 'var(--sig-dormant)',
};

export const Chip = ({ tone, label, showGlyph = true, testId }) => (
  <span data-testid={testId}
        className="mono-num"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          background: BG[tone], color: FG[tone],
          padding: '2px 8px', borderRadius: 'var(--radius-1)',
          fontSize: 'var(--font-caption)', textTransform: 'uppercase',
          letterSpacing: '0.06em', lineHeight: 1, whiteSpace: 'nowrap',
        }}>
    {showGlyph && <span style={{ fontWeight: 600 }}>{GLYPH[tone]}</span>}
    <span>{label}</span>
  </span>
);
