import React from 'react';
import { Cpu, Bot, Activity } from 'lucide-react';
import { WorkerCard } from './WorkerCard';

export default {
  title: 'Primitives/WorkerCard',
  component: WorkerCard,
  parameters: { docs: { description: { component: 'Bible §7.6 · D4 §5.3.' } } },
};

export const Active = { args: { name: 'signal-forge', purpose: 'Trains signals from candles.', subject: 'plan #47 · epoch 4/6', state: 'active', icon: Cpu } };
export const Idle = { args: { name: 'validator', purpose: 'Attests backtest results.', state: 'idle', icon: Bot } };
export const Blocked = { args: { name: 'ingestion', purpose: 'Pulls candles from exchange feeds.', subject: 'coinbase · degraded', state: 'blocked', icon: Activity } };
export const ErrorState = { args: { name: 'gpu-pool-b', purpose: 'GPU worker pool B.', subject: 'oom · restarting', state: 'error', icon: Cpu } };
export const Dormant = { args: { name: 'legacy-forge', purpose: 'Deprecated forge worker.', state: 'dormant', icon: Cpu } };
