/*
 * ProvenanceTriple — Bible §10.2 (canonical §10.1 in v1).
 * Chip strip that captures the who/what/when triple for any artefact:
 *   [source] · [transform] · [attested]
 * All three chips are always present; unknowns render as dormant.
 */
import { Chip, type ChipTone } from './Chip';

export interface ProvenanceTripleProps {
  source?: string;
  transform?: string;
  attested?: string;
  testId?: string;
}

const label = (v?: string) => v ?? 'unknown';
const tone  = (v?: string): ChipTone => (v ? 'info' : 'dormant');

export const ProvenanceTriple: React.FC<ProvenanceTripleProps> = ({
  source, transform, attested, testId,
}) => (
  <div
    data-testid={testId ?? 'provenance-triple'}
    role="group"
    aria-label="Provenance triple"
    style={{
      display: 'inline-flex', gap: 'var(--space-2)', flexWrap: 'wrap',
      alignItems: 'center',
    }}
  >
    <span
      style={{
        fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
        textTransform: 'uppercase', letterSpacing: '0.08em',
      }}
    >
      provenance ·
    </span>
    <Chip tone={tone(source)} label={`src ${label(source)}`} showGlyph={false} testId="prov-src" />
    <Chip tone={tone(transform)} label={`xf ${label(transform)}`} showGlyph={false} testId="prov-xf" />
    <Chip tone={tone(attested)} label={`att ${label(attested)}`} showGlyph={false} testId="prov-att" />
  </div>
);
