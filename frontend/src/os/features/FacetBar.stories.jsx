import React from 'react';
import { FacetBar } from './FacetBar';

export default {
  title: 'Features/FacetBar',
  component: FacetBar,
  parameters: { docs: { description: { component: 'F1 · shared-facet plane control across surfaces.' } } },
};

const options = [
  { key: 'all', label: 'All', count: 24 },
  { key: 'live', label: 'Live', count: 12 },
  { key: 'paper', label: 'Paper', count: 8 },
  { key: 'archived', label: 'Archived', count: 4 },
];

export const StatusAxis = { args: { axis: 'status', options } };
export const RiskAxis = { args: { axis: 'risk', options: [
  { key: 'all', label: 'All' },
  { key: 'low', label: 'Low', count: 8 },
  { key: 'moderate', label: 'Moderate', count: 5 },
  { key: 'high', label: 'High', count: 2 },
] } };
