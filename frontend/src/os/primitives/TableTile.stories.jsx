import React from 'react';
import { TableTile } from './TableTile';

export default {
  title: 'Primitives/TableTile',
  component: TableTile,
  parameters: { docs: { description: { component: 'Bible §7.11.3 · dense sortable list.' } } },
};

const columns = [
  { key: 'name', label: 'name', sortable: true },
  { key: 'sharpe', label: 'sharpe', sortable: true, align: 'right' },
  { key: 'drawdown', label: 'ddown', sortable: true, align: 'right' },
];
const rows = [
  { name: 'flagship-alpha', sharpe: 1.9, drawdown: 3.1 },
  { name: 'momentum-mid', sharpe: 1.4, drawdown: 5.2 },
  { name: 'meanrev-hi', sharpe: 0.9, drawdown: 8.3 },
];

export const Happy = { args: { caption: 'Strategies', columns, rows } };
export const LoadingState = { args: { caption: 'Strategies', columns, rows: [], state: 'loading' } };
export const EmptyState = { args: { caption: 'Strategies', columns, rows: [], state: 'empty' } };
export const ErrorState = { args: { caption: 'Strategies', columns, rows: [], state: 'error' } };
