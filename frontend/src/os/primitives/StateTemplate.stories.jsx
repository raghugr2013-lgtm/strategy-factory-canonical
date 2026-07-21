import React from 'react';
import { AlertTriangle, MinusCircle } from 'lucide-react';
import { StateTemplate } from './StateTemplate';

export default {
  title: 'Primitives/StateTemplate',
  component: StateTemplate,
  parameters: { docs: { description: { component: 'D7 §3 · six-slot state anatomy.' } } },
};

export const ErrorVariant = { args: { variant: 'error', icon: AlertTriangle, tone: 'crit', code: 'demo-error',
  headline: 'This surface could not load.', purpose: 'Retrying every 60s.', advancedFootnote: 'aggregator@v1 · retry #3' } };
export const EmptyVariant = { args: { variant: 'empty', icon: MinusCircle, tone: 'dormant', code: 'demo-empty',
  headline: 'Nothing here yet.', purpose: 'Widen the time window or ingest more data.' } };
export const DormantVariant = { args: { variant: 'dormant', icon: MinusCircle, tone: 'dormant', code: 'demo-dormant',
  headline: 'Feature paused.', purpose: 'Enable in Settings → Feature Flags.' } };
export const ReplayEmptyVariant = { args: { variant: 'replay-empty', icon: MinusCircle, tone: 'dormant', code: 'demo-replay',
  headline: "This artefact didn't exist at the replayed time.", purpose: 'Move the time window forward.' } };
