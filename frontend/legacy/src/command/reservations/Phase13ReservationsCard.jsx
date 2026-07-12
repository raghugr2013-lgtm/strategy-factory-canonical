/**
 * COMMAND · M2 — Phase 13 Strategy Dossier Reservation Card
 * ----------------------------------------------------------------------------
 * Renders the 12 reserved report slots that the Strategy Dossier Engine
 * (Phase 13) will plug into the Explorer right pane / detail drawer.
 *
 * Locked spec:
 *   /app/memory/visual_approval_package/10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md §3.2
 *   /app/memory/visual_approval_package/12_M1_ARCHITECTURAL_PRINCIPLES.md P4
 *
 * NO implementation: this is layout-only architecture reservation. Each slot
 * shows a dashed border, label, and "RESERVED · Phase 13" tag so the
 * operator can SEE the future shape, and Phase 13 plug-in is zero-reflow.
 */
import React from 'react';
import './reservations.css';

const REPORT_SLOTS = [
  { id: 'passport',      label: 'Strategy Passport',         hint: 'Canonical 1-page identity · ID · lineage · signed evidence' },
  { id: 'backtest',      label: 'Backtest Report',           hint: 'Static historical-window result archive' },
  { id: 'walk-forward',  label: 'Walk-Forward Report',       hint: 'Rolling re-fit / out-of-fit; WFA score · param drift' },
  { id: 'oos',           label: 'OOS Report',                hint: 'Hold-out evidence (last 20% of data never seen)' },
  { id: 'monte-carlo',   label: 'Monte Carlo Report',        hint: 'Trade-sequence + param perturbation + bootstrap' },
  { id: 'bi5-realism',   label: 'BI5 Realism Report',        hint: 'Slippage / spread / latency-attached fills (ties to BI5 R2)' },
  { id: 'forward-test',  label: 'Forward Test Report',       hint: 'Live/paper forward evidence post-promotion' },
  { id: 'live-perf',     label: 'Live Performance Report',   hint: 'Master Bot runner ledger · per-deployment timeline' },
  { id: 'pair-tf',       label: 'Pair / TF Compatibility',   hint: 'Cross-symbol + cross-TF transfer heatmaps' },
  { id: 'regime',        label: 'Regime Compatibility',      hint: 'Per-regime PnL · regime fit heatmap' },
  { id: 'risk-profile',  label: 'Risk Profile',              hint: 'MaxDD + tail-loss + Sharpe + Calmar · 5-axis radar' },
  { id: 'valuation',     label: 'Automated Valuation',       hint: 'System-generated price · Phase 14 driven' },
];

export default function Phase13ReservationsCard() {
  return (
    <div className="m2-reservation" data-testid="m2-reservation-phase13" data-phase="13">
      <div className="m2-reservation__hd">
        <span className="m2-reservation__badge">RESERVED · PHASE 13</span>
        <span className="m2-reservation__title">Strategy Dossier Engine</span>
        <span className="m2-reservation__tag">⑤a · Lifecycle insertion point</span>
      </div>
      <p className="m2-reservation__desc">
        Each deployment-ready strategy becomes a <b>Strategy Passport</b> with a stack of
        signed evidence reports. The Explorer right pane + detail drawer reserve these slots
        so Phase 13 plugs in without re-flow. The Passport is operator-visible from <b>step ⑤
        Select</b> onwards and becomes the canonical strategy detail page in the future
        Marketplace (Phase 15).
      </p>
      <div className="m2-reservation__grid">
        {REPORT_SLOTS.map(s => (
          <div key={s.id} className="m2-reservation__slot" data-testid={`m2-slot-phase13-${s.id}`}>
            <div className="m2-reservation__slot-hd">
              <span className="m2-reservation__slot-label">{s.label}</span>
              <span className="m2-reservation__slot-state">reserved</span>
            </div>
            <p className="m2-reservation__slot-hint">{s.hint}</p>
          </div>
        ))}
      </div>
      <div className="m2-reservation__ft">
        <span className="m2-reservation__ft-key">Reservation contract</span>
        <span className="m2-reservation__ft-val">
          Layout geometry preserved · drawer geometry preserved · zero re-flow when Phase 13 lands.
        </span>
      </div>
    </div>
  );
}
