/**
 * COMMAND · M2 — Execution Broker Chip Row
 * ----------------------------------------------------------------------------
 * Reserves the broker-account chip row for the Execution module, including
 * cTrader Live, cTrader Demo, Windows VPS Execution and Broker Telemetry
 * placeholders. None of the cTrader/VPS/Telemetry chips are wired today —
 * they are reservation slots so the layout doesn't reflow when those
 * integrations land post-RC1.
 *
 * Lock: 12_M1_ARCHITECTURAL_PRINCIPLES.md P1 (cTrader future architecture)
 *       and acceptance gate #4.
 */
import React from 'react';
import './reservations.css';

const BROKERS = [
  { id: 'paper-001',     label: 'Paper · paper-001',      track: 'Track A · Prop Firm', state: 'active',   note: 'Live (current operator account)' },
  { id: 'ctrader-demo',  label: 'cTrader · Demo',         track: 'Track B · Personal',  state: 'reserved', note: 'Reserved · post-RC1 cBot connector' },
  { id: 'ctrader-live',  label: 'cTrader · Live',         track: 'Track B · Personal',  state: 'reserved', note: 'Reserved · post-RC1 cBot connector' },
  { id: 'win-vps',       label: 'Windows VPS Execution',  track: 'Infrastructure',      state: 'reserved', note: 'Reserved · VPS-attached MasterBot' },
  { id: 'broker-tlm',    label: 'Broker Telemetry',       track: 'Infrastructure',      state: 'reserved', note: 'Reserved · fill / slippage / latency feed' },
];

export default function ExecutionBrokerChips() {
  return (
    <div className="m2-brokers" data-testid="m2-broker-chips">
      <div className="m2-brokers__hd">
        <span className="m2-brokers__badge">BROKER ACCOUNTS</span>
        <span className="m2-brokers__title">Execution targets · Track A (Prop Firm) + Track B (Personal Capital)</span>
      </div>
      <div className="m2-brokers__row">
        {BROKERS.map(b => (
          <div
            key={b.id}
            className={`m2-brokers__chip m2-brokers__chip--${b.state}`}
            data-testid={`m2-broker-${b.id}`}
            title={b.note}
          >
            <span className="m2-brokers__chip-dot" />
            <span className="m2-brokers__chip-label">{b.label}</span>
            <span className="m2-brokers__chip-track">{b.track}</span>
            {b.state === 'reserved' && (
              <span className="m2-brokers__chip-state">reserved</span>
            )}
          </div>
        ))}
      </div>
      <p className="m2-brokers__ft">
        Active broker only fires live orders. Reserved chips preserve layout so
        cTrader Live + cTrader Demo + Windows VPS connectors land post-RC1 with
        zero re-flow. Telemetry feeds tag fills with slippage / latency metadata
        consumed by Phase 13 BI5 Realism reports and Phase 14 Investor Scorecards.
      </p>
    </div>
  );
}
