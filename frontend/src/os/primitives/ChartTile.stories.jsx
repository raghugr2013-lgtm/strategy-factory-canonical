import React from 'react';
import { ChartTile } from './ChartTile';

export default {
  title: 'Primitives/ChartTile',
  component: ChartTile,
  parameters: { docs: { description: { component: 'Bible §7.11.2 · line + sparkline variants.' } } },
};

const trend = [12, 15, 18, 14, 19, 24, 22, 28, 26, 29, 33, 30, 34, 36, 32, 38, 41, 39, 44, 46, 42, 48, 51, 49];

export const LineHappy = { args: { caption: 'Throughput · signals/hour · last 24h', points: trend, tone: 'info', timeWindow: 'last 24h' } };
export const LineGold = { args: { caption: 'Flagship equity curve', points: trend, tone: 'gold', variant: 'line', timeWindow: 'week' } };
export const SparklineOk = { args: { caption: 'Latency ms', points: trend, variant: 'sparkline', tone: 'ok', timeWindow: '5m' } };
export const LoadingState = { args: { caption: 'Throughput', points: [], tone: 'info', state: 'loading' } };
export const EmptyState = { args: { caption: 'Throughput', points: [], tone: 'info', state: 'empty' } };
export const ErrorState = { args: { caption: 'Throughput', points: [], tone: 'info', state: 'error' } };
