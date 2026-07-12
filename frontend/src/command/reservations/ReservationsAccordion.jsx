/**
 * ReservationsAccordion — Restoration Step 4b (GATE 0 follow-up)
 * --------------------------------------------------------------------------
 * Per UI_RESTORATION_MASTERPLAN.md §1.7/§1.8 + §5 "Reservations in the way":
 * the Phase 13 / 14 / 15 + Strategy Score reservation cards move into a
 * SINGLE collapsed accordion at the bottom of their parent module so they
 * never interrupt the operator's daily browse scroll.
 *
 * IMPORTANT: the reservation cards themselves are UNTOUCHED (M2/M3 visual
 * locks). This file is a pure collapse-wrapper — expanding the accordion
 * renders the exact same components that were previously inline.
 */
import React, { Suspense } from 'react';

const StrategyScoreReservationCard  = React.lazy(() => import('./StrategyScoreReservationCard'));
const Phase13ReservationsCard       = React.lazy(() => import('./Phase13ReservationsCard'));
const Phase15MarketplaceReservation = React.lazy(() => import('./Phase15MarketplaceReservation'));
const Phase14DualScorecardCard      = React.lazy(() => import('./Phase14DualScorecardCard'));

function Skeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      <span className="cmd-skel-line" style={{ width: '40%' }} />
      <span className="cmd-skel-line" style={{ width: '68%' }} />
    </div>
  );
}

function Accordion({ id, summary, hint, children }) {
  return (
    <details data-testid={`reservations-accordion-${id}`} style={{ borderRadius: 6, border: '1px solid var(--cmd-hairline, #2A2D33)' }}>
      <summary
        data-testid={`reservations-accordion-toggle-${id}`}
        style={{
          cursor: 'pointer', listStyle: 'none', userSelect: 'none',
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px',
          fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase',
          color: 'var(--cmd-ink-1, #E4E4E7)',
        }}
      >
        <span>{summary}</span>
        <div style={{ flex: 1 }} />
        <span className="chip chip--amber">
          <span className="chip__dot" />
          <span className="chip__label">reserved · collapsed</span>
        </span>
      </summary>
      <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--cmd-ink-2, #A1A1AA)' }}>{hint}</p>
        <Suspense fallback={<Skeleton />}>{children}</Suspense>
      </div>
    </details>
  );
}

/** Explorer bottom accordion — Strategy Score (M3) + Phase 13 Dossier +
 *  Phase 15 Marketplace reservation cards, in their original order. */
export function ExplorerReservationsAccordion() {
  return (
    <Accordion
      id="explorer"
      summary="Phase 13 · 14 · 15 — Future-phase reservations"
      hint="Layout placeholders for the Strategy Score architecture, the Phase 13 Strategy Dossier, and the Phase 15 Marketplace. Zero-reflow plug-in slots — expand to inspect."
    >
      <StrategyScoreReservationCard />
      <Phase13ReservationsCard />
      <Phase15MarketplaceReservation />
    </Accordion>
  );
}

/** Portfolio bottom accordion — Phase 14 Dual Scorecard + Auto Valuation. */
export function PortfolioReservationsAccordion() {
  return (
    <Accordion
      id="portfolio"
      summary="Phase 14 — Dual scorecards + auto valuation"
      hint="Prop Firm + Investor scorecard reservations and the Automated Pricing Engine inputs. Expand to inspect."
    >
      <Phase14DualScorecardCard />
    </Accordion>
  );
}
