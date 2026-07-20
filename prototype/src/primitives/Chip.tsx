/*
 * Chip primitive — Bible §7.1.
 * Signal chip with letter-glyph fallback for colour-blind safety.
 */

export type ChipTone = 'ok' | 'info' | 'warn' | 'crit' | 'advisory' | 'dormant';

const glyphFor: Record<ChipTone, string> = {
  ok: 'P', info: 'I', warn: 'W', crit: 'F', advisory: 'A', dormant: '·',
};
const bgFor: Record<ChipTone, string> = {
  ok: 'rgba(61,220,132,0.14)',
  info: 'rgba(78,161,243,0.14)',
  warn: 'rgba(240,180,41,0.14)',
  crit: 'rgba(255,91,91,0.14)',
  advisory: 'rgba(184,147,95,0.14)',
  dormant: 'rgba(107,118,132,0.14)',
};
const fgFor: Record<ChipTone, string> = {
  ok: 'var(--sig-ok)', info: 'var(--sig-info)', warn: 'var(--sig-warn)',
  crit: 'var(--sig-crit)', advisory: 'var(--sig-advisory)', dormant: 'var(--sig-dormant)',
};

export interface ChipProps {
  tone: ChipTone;
  label: string;
  showGlyph?: boolean;
  testId?: string;
}

export const Chip: React.FC<ChipProps> = ({ tone, label, showGlyph = true, testId }) => (
  <span
    data-testid={testId}
    className="mono-num inline-flex items-center gap-1"
    style={{
      background: bgFor[tone],
      color: fgFor[tone],
      padding: '2px 8px',
      borderRadius: 'var(--radius-1)',
      fontSize: 'var(--font-caption)',
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      lineHeight: 1,
      whiteSpace: 'nowrap',
    }}
  >
    {showGlyph && <span style={{ fontWeight: 600 }}>{glyphFor[tone]}</span>}
    <span>{label}</span>
  </span>
);
