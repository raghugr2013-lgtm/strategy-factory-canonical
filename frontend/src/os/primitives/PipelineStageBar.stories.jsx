import React from 'react';
import { PipelineStageBar } from './PipelineStageBar';

export default {
  title: 'Primitives/PipelineStageBar',
  component: PipelineStageBar,
  parameters: { docs: { description: { component: 'Bible §7.3 · 8 canonical stages.' } } },
};

export const HealthyPipeline = { args: {} };

export const StuckAtSignal = { args: { stages: [
  { key: 'ingest', label: 'ingest', status: 'done', detail: '18/18' },
  { key: 'candle', label: 'candle', status: 'done' },
  { key: 'feature', label: 'feature', status: 'done' },
  { key: 'signal', label: 'signal', status: 'blocked', detail: 'gpu quota' },
  { key: 'backtest', label: 'backtest', status: 'pending' },
  { key: 'approve', label: 'approve', status: 'pending' },
  { key: 'deploy', label: 'deploy', status: 'pending' },
  { key: 'monitor', label: 'monitor', status: 'pending' },
] } };

export const AllDone = { args: { stages: [
  { key: 'ingest', label: 'ingest', status: 'done' },
  { key: 'candle', label: 'candle', status: 'done' },
  { key: 'feature', label: 'feature', status: 'done' },
  { key: 'signal', label: 'signal', status: 'done' },
  { key: 'backtest', label: 'backtest', status: 'done' },
  { key: 'approve', label: 'approve', status: 'done' },
  { key: 'deploy', label: 'deploy', status: 'done' },
  { key: 'monitor', label: 'monitor', status: 'done' },
] } };
