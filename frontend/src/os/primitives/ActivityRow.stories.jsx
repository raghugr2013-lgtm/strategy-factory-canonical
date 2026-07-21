import React from 'react';
import { Activity, Bot } from 'lucide-react';
import { ActivityRow } from './ActivityRow';

export default {
  title: 'Primitives/ActivityRow',
  component: ActivityRow,
  parameters: { docs: { description: { component: 'Bible §7.4 · D2 §3–§5.' } } },
};

const wrap = (children) => (
  <div style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-3)' }}>
    {children}
  </div>
);

export const MasterBotDecision = {
  render: () => wrap(
    <ActivityRow timestamp="14:22Z" actor={{ kind: 'master-bot', name: 'Master Bot', icon: Bot }}
                 verb="promoted" subject="strategy #47 to production"
                 outcome={{ tone: 'ok', label: 'promoted' }} />
  ),
};

export const OperatorAction = {
  render: () => wrap(
    <ActivityRow timestamp="14:18Z" actor={{ kind: 'operator', name: 'operator@coinnike', icon: Activity }}
                 verb="approved" subject="policy change 2026-Q1"
                 outcome={{ tone: 'info', label: 'approved' }} />
  ),
};

export const ValidatorFailure = {
  render: () => wrap(
    <ActivityRow timestamp="14:11Z" actor={{ kind: 'validator', name: 'schema-guard', icon: Activity }}
                 verb="rejected" subject="candle stream drift"
                 outcome={{ tone: 'crit', label: 'blocked' }} />
  ),
};
