import React from 'react';
import { ProvenanceTriple } from './ProvenanceTriple';

export default {
  title: 'Primitives/ProvenanceTriple',
  component: ProvenanceTriple,
  parameters: { docs: { description: { component: 'Bible §10.2 · SRC · XF · ATT.' } } },
};

export const AllPresent = { args: { source: 'candles@v3', transform: 'signal-forge@v2', attested: 'bt-891' } };
export const PartialUnknown = { args: { source: 'candles@v3', transform: undefined, attested: 'bt-891' } };
export const AllUnknown = { args: {} };
