import React from 'react';
import { MetricBlock } from './MetricBlock';

export default {
  title: 'Primitives/MetricBlock',
  component: MetricBlock,
  parameters: { docs: { description: { component: 'Bible §7.11.1 · A/B/C variants · 5 canonical states.' } } },
};

export const VariantA_Happy = { args: { variant: 'A', eyebrow: 'Strategies live', value: '18', deltaLabel: '+2 today', deltaTone: 'ok' } };
export const VariantB_Neural = { args: { variant: 'B', eyebrow: 'Approvals pending', value: '3', deltaLabel: '1 aged', deltaTone: 'warn' } };
export const VariantC_Hero = { args: { variant: 'C', eyebrow: 'Signals in queue', value: '241', unit: '/hr', deltaLabel: 'stable', deltaTone: 'info' } };
export const LoadingState = { args: { variant: 'A', eyebrow: 'Loading metric', value: '—', state: 'loading' } };
export const EmptyState = { args: { variant: 'A', eyebrow: 'No data', value: '—', state: 'empty' } };
export const ErrorState = { args: { variant: 'A', eyebrow: 'Failed metric', value: '—', state: 'error' } };
export const DormantState = { args: { variant: 'A', eyebrow: 'Paused metric', value: '12', state: 'dormant' } };
