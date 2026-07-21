import React from 'react';
import { LineageBar } from './LineageBar';

export default {
  title: 'Primitives/LineageBar',
  component: LineageBar,
  parameters: { docs: { description: { component: 'Bible §10.1 · one hop up + one hop down.' } } },
};

const self = { id: 's47', kind: 'strategy', label: 'strategy #47' };
const ancestors = [{ id: 'p47', kind: 'plan', label: 'plan #47' }];
const descendants = [{ id: 'bt-891', kind: 'backtest', label: 'backtest 891' }];

export const FullLineage = { args: { self, ancestors, descendants } };
export const RootGeneration = { args: { self, ancestors: [], descendants: [] } };
export const ReplayEmpty = { args: { self, replayEmpty: true } };
