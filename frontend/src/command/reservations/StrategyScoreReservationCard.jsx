/**
 * COMMAND · M3 — Strategy Score Reservation Card (3-metric architecture)
 * ----------------------------------------------------------------------------
 * Read-only reservation surfacing the THREE future-facing operator metrics
 * that will later feed Phase 13 (Dossier), Phase 14 (Automated Valuation)
 * and Phase 15 (Marketplace). Informational ONLY — NO pricing UI, NO manual
 * pricing controls anywhere on this card.
 *
 *   • Quality Score   → "How rigorously was this strategy validated?"
 *   • Evidence Score  → "How much real-world evidence backs it?"
 *   • Market Score    → "How attractive is it to customers / market fit?"
 *
 * ASF stays internal. Customers interact via a separate customer-facing
 * website; this card documents the score schema that the future Marketplace
 * cards will surface on the public portal.
 */
import React from 'react';
import './reservations.css';

const SCORES = [
  {
    id: 'quality',
    label: 'Quality Score',
    range: '0 — 100',
    tone: 'gold',
    purpose: 'Validation rigour · statistical significance · backtest realism',
    feeds: ['Phase 13 Strategy Dossier · top-of-passport stamp', 'Phase 14 Auto Valuation · primary input'],
    inputs: [
      'PF (profit factor)',
      'Sharpe (30/90/365 d)',
      'Calmar / MAR',
      'Max drawdown (historical + Monte Carlo p99)',
      'Walk-forward score (parameter drift)',
      'OOS hold-out delta to IS',
      'Monte Carlo distribution width',
      'Trade count · statistical significance',
    ],
  },
  {
    id: 'evidence',
    label: 'Evidence Score',
    range: '0 — 100',
    tone: 'cyan',
    purpose: 'Real-world evidence depth · forward-test breadth · live track record',
    feeds: ['Phase 13 Strategy Dossier · Forward + Live report tabs', 'Phase 14 Auto Valuation · longevity weight'],
    inputs: [
      'Forward-test history vs backtest fidelity',
      'Live deployment history (survivor-bias corrected)',
      'BI5 realism certification verdict',
      'Slippage / spread / latency-attached fills',
      'Pair compatibility breadth (cross-symbol transfer)',
      'Timeframe compatibility breadth (cross-TF transfer)',
      'Regime robustness (per-regime PnL)',
      'Days-since-promotion · longevity tier',
    ],
  },
  {
    id: 'market',
    label: 'Market Score',
    range: '0 — 100',
    tone: 'violet',
    purpose: 'Customer-facing attractiveness · capacity · narrative quality',
    feeds: ['Phase 14 Auto Valuation · pricing modifier', 'Phase 15 Marketplace · ranking + listing rotation'],
    inputs: [
      'Capacity (price-impact-aware)',
      'Story narrative quality (auto-generated synopsis)',
      'Prop-firm fitness breadth (passes for how many firms?)',
      'Investor fitness (long-term risk-adjusted appeal)',
      'Customer-type breadth (prop / personal / both)',
      'Risk tier alignment (T1 conservative → T4 aggressive)',
      'Exclusivity / scarcity (units already sold)',
      'Marketplace rotation velocity',
    ],
  },
  {
    id: 'trust',
    label: 'Trust Score',
    range: '0 — 100',
    tone: 'teal',
    purpose: 'Operator confidence · time-proven longevity · execution consistency',
    feeds: [
      'Phase 13 Strategy Dossier · Trust stamp + risk profile pane',
      'Phase 14 Auto Valuation · longevity multiplier',
      'Phase 15 Marketplace · ranking tie-breaker + customer trust signal',
    ],
    inputs: [
      'Forward-test duration (calendar days observed)',
      'Live-test duration (live deployment runtime)',
      'BI5 realism (slippage / spread / latency fidelity)',
      'Slippage consistency (variance vs expected)',
      'Drawdown consistency (max-DD stability over time)',
      'Stability (rolling-PnL variance · regime survival)',
      'Calibration quality (predicted vs realised PnL fit)',
    ],
  },
];

const EXAMPLE_ROWS = [
  { id: 's_021', sym: 'EURUSD H1',  q: 87, e: 72, m: 81, t: 79 },
  { id: 's_011', sym: 'GBPUSD M15', q: 78, e: 65, m: 74, t: 58 },
  { id: 's_044', sym: 'USDJPY H4',  q: 91, e: 84, m: 68, t: 88 },
  { id: 's_032', sym: 'XAUUSD M15', q: 73, e: 48, m: 79, t: 42 },
];

function scoreToneClass(v) {
  if (v >= 80) return 'm3-score__cell--strong';
  if (v >= 60) return 'm3-score__cell--okay';
  if (v >= 40) return 'm3-score__cell--weak';
  return 'm3-score__cell--poor';
}

export default function StrategyScoreReservationCard() {
  return (
    <div className="m2-reservation m3-score" data-testid="m3-reservation-scores" data-phase="13-14-15">
      <div className="m2-reservation__hd">
        <span className="m2-reservation__badge">RESERVED · PHASES 13 · 14 · 15</span>
        <span className="m2-reservation__title">Strategy Score Architecture · Quality · Evidence · Market · Trust</span>
        <span className="m2-reservation__tag">Read-only · informational</span>
      </div>
      <p className="m2-reservation__desc">
        Every strategy in the workstation will carry <b>four</b> independent
        operator-facing scores. They are <b>informational only</b> — no
        pricing UI is exposed to operators, no manual override fields, no
        cost/fee/subscription inputs anywhere. The four signals feed the
        future <b>Strategy Dossier (Phase 13)</b>, <b>Automated Valuation Engine
        (Phase 14)</b> and <b>Marketplace ranking (Phase 15)</b>. Customers
        never see ASF — they see only the marketplace listings, which surface
        these scores as the canonical decision aids.
      </p>

      {/* Score definitions */}
      <div className="m3-score__defs">
        {SCORES.map(s => (
          <div key={s.id} className={`m3-score__def m3-score__def--${s.tone}`} data-testid={`m3-score-def-${s.id}`}>
            <div className="m3-score__def-hd">
              <span className={`m3-score__chip m3-score__chip--${s.tone}`}>{s.label}</span>
              <span className="m3-score__def-range">{s.range}</span>
              <span className="m2-reservation__slot-state">read-only</span>
            </div>
            <p className="m3-score__def-purpose">{s.purpose}</p>
            <div className="m3-score__def-feeds">
              <span className="m3-score__def-key">Feeds</span>
              <ul>
                {s.feeds.map(f => <li key={f}>{f}</li>)}
              </ul>
            </div>
            <div className="m3-score__def-inputs">
              <span className="m3-score__def-key">Input signals</span>
              <ul>
                {s.inputs.map(i => <li key={i}>{i}</li>)}
              </ul>
            </div>
          </div>
        ))}
      </div>

      {/* Worked example — how Explorer rows will look post-Phase-13 */}
      <div className="m3-score__example" data-testid="m3-score-example">
        <div className="m3-score__example-hd">
          <span className="m2-reservation__badge m2-reservation__badge--small">EXAMPLE ROWS</span>
          <span className="m3-score__example-title">
            How the four scores will surface in Explorer (post-Phase 13)
          </span>
        </div>
        <div className="m3-score__table" role="table">
          <div className="m3-score__row m3-score__row--head" role="row">
            <span role="columnheader">Strategy</span>
            <span role="columnheader">Symbol · TF</span>
            <span role="columnheader" className="m3-score__col--gold">Quality</span>
            <span role="columnheader" className="m3-score__col--cyan">Evidence</span>
            <span role="columnheader" className="m3-score__col--violet">Market</span>
            <span role="columnheader" className="m3-score__col--teal">Trust</span>
            <span role="columnheader">Composite verdict</span>
          </div>
          {EXAMPLE_ROWS.map(r => {
            const comp = Math.round((r.q + r.e + r.m + r.t) / 4);
            const verdict = comp >= 80 ? 'dossier-ready' : comp >= 65 ? 'evidence-pending' : comp >= 50 ? 'needs-forward-test' : 'low-conviction';
            return (
              <div key={r.id} className="m3-score__row" role="row">
                <span role="cell" className="m3-score__cell-id">{r.id}</span>
                <span role="cell" className="m3-score__cell-sym">{r.sym}</span>
                <span role="cell" className={`m3-score__cell m3-score__col--gold ${scoreToneClass(r.q)}`}>{r.q}</span>
                <span role="cell" className={`m3-score__cell m3-score__col--cyan ${scoreToneClass(r.e)}`}>{r.e}</span>
                <span role="cell" className={`m3-score__cell m3-score__col--violet ${scoreToneClass(r.m)}`}>{r.m}</span>
                <span role="cell" className={`m3-score__cell m3-score__col--teal ${scoreToneClass(r.t)}`}>{r.t}</span>
                <span role="cell" className={`m3-score__cell-verdict m3-score__cell-verdict--${verdict}`}>{verdict}</span>
              </div>
            );
          })}
        </div>
        <p className="m3-score__example-note">
          The numbers above are illustrative only. Phase 13 computes them from the
          per-strategy dossier reports; Phase 14 turns the scores into a
          system-generated price (no manual override); Phase 15 surfaces the
          four pills as the primary decision aid in the customer-facing
          marketplace listings — ASF itself stays private.
        </p>
      </div>
    </div>
  );
}
