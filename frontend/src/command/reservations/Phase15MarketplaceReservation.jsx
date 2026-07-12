/**
 * COMMAND · M2 — Phase 15 Marketplace Reservation Card
 * ----------------------------------------------------------------------------
 * Reserves the Marketplace metadata fields per operator brief. ASF remains
 * PRIVATE — the marketplace is a future public website that exposes:
 *   • Individual Strategies
 *   • Portfolio Bundles
 *   • Master Bots
 * Customers buy/download products, not access ASF itself.
 *
 * Lock: 10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md §1, §3.4
 */
import React from 'react';
import './reservations.css';

const MARKETPLACE_FIELDS = [
  { id: 'quality_score',      label: 'Quality Score',      hint: 'System-generated · evidence-weighted (Sharpe + DD + OOS + MC + BI5 + Forward)' },
  { id: 'valuation_score',    label: 'Valuation Score',    hint: 'Phase 14-derived · drives subscription + one-shot pricing' },
  { id: 'marketplace_status', label: 'Marketplace Status', hint: 'draft · review · published · withdrawn · sold-out' },
  { id: 'customer_type',      label: 'Customer Type',      hint: 'prop-firm-suitable · personal-capital-suitable · both' },
  { id: 'risk_tier',          label: 'Risk Tier',          hint: 'T1 conservative · T2 balanced · T3 growth · T4 aggressive' },
  { id: 'evidence_level',     label: 'Evidence Level',     hint: 'backtest-only · WF · OOS+MC · BI5-certified · forward-tested · live-verified' },
];

const PRODUCT_TYPES = [
  { id: 'strategies',  label: 'Individual Strategies', surface: 'Marketplace tab (More ▾) · Phase 15' },
  { id: 'portfolios',  label: 'Portfolio Bundles',     surface: 'Marketplace tab (More ▾) · Phase 15' },
  { id: 'master-bots', label: 'Master Bots (.cbotpack)', surface: 'Master Bot Marketplace tab (More ▾) · Phase 15' },
];

export default function Phase15MarketplaceReservation() {
  return (
    <div className="m2-reservation" data-testid="m2-reservation-phase15" data-phase="15">
      <div className="m2-reservation__hd">
        <span className="m2-reservation__badge">RESERVED · PHASE 15</span>
        <span className="m2-reservation__title">Marketplace Layer</span>
        <span className="m2-reservation__tag">⑤c · Public product distribution</span>
      </div>
      <p className="m2-reservation__desc">
        ASF stays <b>private</b>. The future public website exposes <b>products</b>
        (strategies · portfolio bundles · signed Master Bot <code>.cbotpack</code>).
        Customers buy / download — they never log into ASF itself.
      </p>

      <div className="m2-reservation__grid m2-reservation__grid--3">
        {PRODUCT_TYPES.map(t => (
          <div key={t.id} className="m2-reservation__slot" data-testid={`m2-slot-phase15-${t.id}`}>
            <div className="m2-reservation__slot-hd">
              <span className="m2-reservation__slot-label">{t.label}</span>
              <span className="m2-reservation__slot-state">reserved</span>
            </div>
            <p className="m2-reservation__slot-hint">{t.surface}</p>
          </div>
        ))}
      </div>

      <div className="m2-reservation__pricing">
        <div className="m2-reservation__pricing-hd">
          <span className="m2-reservation__badge m2-reservation__badge--small">MARKETPLACE METADATA</span>
          <span className="m2-reservation__pricing-title">Reserved fields per listing</span>
        </div>
        <div className="m2-reservation__grid m2-reservation__grid--3">
          {MARKETPLACE_FIELDS.map(f => (
            <div key={f.id} className="m2-reservation__slot m2-reservation__slot--compact" data-testid={`m2-slot-phase15-field-${f.id}`}>
              <div className="m2-reservation__slot-hd">
                <code className="m2-reservation__slot-code">{f.id}</code>
              </div>
              <p className="m2-reservation__slot-hint">{f.hint}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
