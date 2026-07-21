import React from 'react';
import { Chip } from './Chip';

export default {
  title: 'Primitives/Chip',
  component: Chip,
  parameters: { docs: { description: { component: 'Bible §7.1 · P·W·F·A·I taxonomy with colour-blind letter glyph.' } } },
};

export const PassingOk = { args: { tone: 'ok', label: 'passing' } };
export const WorkingInfo = { args: { tone: 'info', label: 'working' } };
export const AttentionWarn = { args: { tone: 'warn', label: 'attention' } };
export const FailedCrit = { args: { tone: 'crit', label: 'failed' } };
export const AdvisoryTone = { args: { tone: 'advisory', label: 'advisory' } };
export const IdleDormant = { args: { tone: 'dormant', label: 'idle' } };
export const WithoutGlyph = { args: { tone: 'info', label: 'plain label', showGlyph: false } };
