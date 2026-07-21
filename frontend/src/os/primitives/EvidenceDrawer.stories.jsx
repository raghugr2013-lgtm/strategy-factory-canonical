import React, { useState } from 'react';
import { EvidenceDrawer } from './EvidenceDrawer';

export default {
  title: 'Primitives/EvidenceDrawer',
  component: EvidenceDrawer,
  parameters: { docs: { description: { component: 'Bible §10 · evidence stack for any artefact.' } } },
};

const provenance = { source: 'candles@v3', transform: 'signal-forge@v2', attested: 'bt-891' };
const lineage = { self: { id: 's47', kind: 'strategy', label: 'strategy #47' },
  ancestors: [{ id: 'p47', kind: 'plan', label: 'plan #47' }],
  descendants: [{ id: 'bt-891', kind: 'backtest', label: 'backtest 891' }] };
const sections = [
  { heading: 'Backtest summary', body: 'Sharpe 1.9 · drawdown 3.1% · turnover 2.4x annualised.' },
  { heading: 'Regime coverage', body: 'Trained on 2018Q1–2025Q4. Robust across trending + range regimes.' },
];

const Wrapper = ({ state }) => {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button data-testid="open-drawer" onClick={() => setOpen(true)}>Open</button>
      <EvidenceDrawer open={open} onClose={() => setOpen(false)}
                      title="strategy #47" subtitle="sha 91a2b · plan #47"
                      provenance={provenance} lineage={lineage} sections={sections} state={state} />
    </div>
  );
};

export const Happy = { render: () => <Wrapper state="happy" /> };
export const LoadingState = { render: () => <Wrapper state="loading" /> };
export const EmptyState = { render: () => <Wrapper state="empty" /> };
export const ErrorState = { render: () => <Wrapper state="error" /> };
