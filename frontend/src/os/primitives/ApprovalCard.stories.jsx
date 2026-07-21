import React from 'react';
import { ApprovalCard } from './ApprovalCard';

export default {
  title: 'Primitives/ApprovalCard',
  component: ApprovalCard,
  parameters: { docs: { description: { component: 'Bible §7.5 · D3 §2.' } } },
};

const baseProvenance = { source: 'candles@v3', transform: 'signal-forge@v2', attested: 'bt-891' };

export const LowRisk = { args: { title: 'Promote strategy #47 to paper-trading', origin: 'strategy', risk: 'low',
  summary: 'Passing all gates. Sharpe 1.9 · drawdown 3.1%.', provenance: baseProvenance, ageMinutes: 15 } };
export const ModerateRisk = { args: { title: 'Increase compute quota to 32 workers', origin: 'compute-quota', risk: 'moderate',
  summary: 'Backfill of 2y candles across 4 markets.', provenance: baseProvenance, ageMinutes: 45 } };
export const HighRiskAged = { args: { title: 'Deploy schema change · trade_events v4', origin: 'schema-change', risk: 'high',
  summary: 'Breaking change. Requires 2 human approvals + validator sign-off.', provenance: baseProvenance, ageMinutes: 128 } };
