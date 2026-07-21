/*
 * ProvenanceTriple — Bible §10.2 · SRC · XF · ATT.
 * refs DESIGN_FREEZE_v1.0.md §1.5 provenance triple
 */
import React from 'react';
import { Chip } from './Chip';

const label = (v) => v ?? 'unknown';
const tone = (v) => (v ? 'info' : 'dormant');

export const ProvenanceTriple = ({ source, transform, attested, testId }) => (
  <div data-testid={testId ?? 'provenance-triple'}
       role="group" aria-label="Provenance triple"
       style={{ display: 'inline-flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}>
    <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                   textTransform: 'uppercase', letterSpacing: '0.08em' }}>
      provenance ·
    </span>
    <Chip tone={tone(source)} label={`src ${label(source)}`} showGlyph={false} testId="prov-src" />
    <Chip tone={tone(transform)} label={`xf ${label(transform)}`} showGlyph={false} testId="prov-xf" />
    <Chip tone={tone(attested)} label={`att ${label(attested)}`} showGlyph={false} testId="prov-att" />
  </div>
);
