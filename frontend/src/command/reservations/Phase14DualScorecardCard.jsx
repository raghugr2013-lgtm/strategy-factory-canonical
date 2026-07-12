/**
 * COMMAND · M2 — Phase 14 Dual Scorecard Reservation Card
 * ----------------------------------------------------------------------------
 * Reserves the two scorecard slots for the Automated Valuation Engine:
 *   • Prop Firm Scorecards (Track A operators)
 *   • Investor Scorecards   (Track B personal-capital operators)
 *
 * ASF must NEVER be a prop-firm-only platform. P2 lock in
 * /app/memory/visual_approval_package/12_M1_ARCHITECTURAL_PRINCIPLES.md
 *
 * No manual-pricing fields anywhere — pricing is system-generated per P5.
 */
import React from 'react';
import './reservations.css';

const SCORECARDS = [
  {
    id: 'prop-firm',
    track: 'Track A',
    label: 'Prop Firm Scorecards',
    audience: 'Prop Firm Trader',
    constraint: 'Pass a prop-firm challenge',
    firms: ['FTMO', 'MyForexFunds', 'The5%ers', '20+ firms'],
    metrics: ['Daily DD ≤ 5%', 'Total DD ≤ 10%', 'Min Profit Target', 'Min Trading Days'],
    verdict: 'pass / warn / fail per firm rule book',
  },
  {
    id: 'investor',
    track: 'Track B',
    label: 'Investor Scorecards',
    audience: 'Personal Capital Trader',
    constraint: 'Long-term risk-adjusted return',
    firms: ['Personal cTrader (live)', 'Personal cTrader (demo)'],
    metrics: ['Sharpe (30/90/365d)', 'Calmar / MAR', 'Capacity (price-impact)', 'Story narrative'],
    verdict: 'investor-grade summary · risk profile · expected monthly range',
  },
];

const PRICING_INPUTS = [
  'Sharpe (30/90/365d)', 'Calmar / MAR', 'Max drawdown (historical + MC p99)',
  'Trade count + statistical significance', 'BI5 realism certification verdict',
  'Walk-forward score', 'Pair / TF compatibility breadth', 'Regime robustness',
  'Capacity (price-impact-aware)', 'Forward-test history vs backtest',
  'Live deployment history (longevity)', 'Prop-firm fitness (per major firm)',
  'Investor fitness', 'Exclusivity / scarcity',
];

export default function Phase14DualScorecardCard() {
  return (
    <div className="m2-reservation" data-testid="m2-reservation-phase14" data-phase="14">
      <div className="m2-reservation__hd">
        <span className="m2-reservation__badge">RESERVED · PHASE 14</span>
        <span className="m2-reservation__title">Automated Valuation Engine</span>
        <span className="m2-reservation__tag">⑤b · Dual-track product model</span>
      </div>
      <p className="m2-reservation__desc">
        ASF is <b>not a prop-firm-only platform.</b> Strategies are scored against
        both prop-firm rule books <b>and</b> investor mandates. Pricing is computed
        by the Automated Valuation Engine — never manually entered.
      </p>

      <div className="m2-reservation__dual">
        {SCORECARDS.map(sc => (
          <div key={sc.id} className="m2-reservation__scorecard" data-testid={`m2-slot-phase14-${sc.id}`}>
            <div className="m2-reservation__scorecard-hd">
              <span className="m2-reservation__scorecard-track">{sc.track}</span>
              <span className="m2-reservation__scorecard-label">{sc.label}</span>
              <span className="m2-reservation__slot-state">reserved</span>
            </div>
            <div className="m2-reservation__scorecard-row">
              <span className="m2-reservation__scorecard-key">Audience</span>
              <span className="m2-reservation__scorecard-val">{sc.audience}</span>
            </div>
            <div className="m2-reservation__scorecard-row">
              <span className="m2-reservation__scorecard-key">Constraint</span>
              <span className="m2-reservation__scorecard-val">{sc.constraint}</span>
            </div>
            <div className="m2-reservation__scorecard-row">
              <span className="m2-reservation__scorecard-key">Deployment targets</span>
              <span className="m2-reservation__scorecard-val">{sc.firms.join(' · ')}</span>
            </div>
            <div className="m2-reservation__scorecard-row">
              <span className="m2-reservation__scorecard-key">Scoring axes</span>
              <span className="m2-reservation__scorecard-val">{sc.metrics.join(' · ')}</span>
            </div>
            <div className="m2-reservation__scorecard-row">
              <span className="m2-reservation__scorecard-key">Verdict format</span>
              <span className="m2-reservation__scorecard-val">{sc.verdict}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="m2-reservation__pricing" data-testid="m2-slot-phase14-pricing">
        <div className="m2-reservation__pricing-hd">
          <span className="m2-reservation__badge m2-reservation__badge--small">PRICING ENGINE</span>
          <span className="m2-reservation__pricing-title">System-generated · operator may NUDGE ±20%</span>
        </div>
        <p className="m2-reservation__pricing-rule">
          No manual-pricing fields are introduced anywhere in the restoration —
          even as placeholders — to prevent muscle-memory drift. The canonical
          price is <b>computed</b> from the evidence below.
        </p>
        <ul className="m2-reservation__pricing-list">
          {PRICING_INPUTS.map(p => <li key={p}>{p}</li>)}
        </ul>
      </div>
    </div>
  );
}
