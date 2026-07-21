import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { StrategyPassport } from './StrategyPassport';

export default {
  title: 'Surfaces/StrategyPassport',
  component: StrategyPassport,
  parameters: {
    docs: { description: { component: 'Sprint 2 N5 · Surface D5. Signature header + identity + evidence + guardrails + equity curve + backtest + approvals. Live via GET /api/strategies/{id} with fixture fallback.' } },
    layout: 'fullscreen',
  },
};

const WithId = (id) => () => (
  <MemoryRouter initialEntries={[`/c/strategies/${id}`]}>
    <div style={{ background: 'var(--surface-0)', minHeight: '100vh' }}>
      <Routes>
        <Route path="/c/strategies/:id" element={<StrategyPassport />} />
      </Routes>
    </div>
  </MemoryRouter>
);

export const FlagshipMomentum = { render: WithId('strat-014') };
export const VolCarryPaper = { render: WithId('strat-030') };
export const UnknownIdFallback = { render: WithId('strat-999') };
