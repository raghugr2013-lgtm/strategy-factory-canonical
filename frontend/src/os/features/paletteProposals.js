/*
 * Palette proposals · Sprint 2.0 tail patch R3.
 * Module-level FIFO buffer + custom event so a Cmd+K palette entry can drop
 * an ApprovalCard onto /c/approvals even when Approvals is not yet mounted.
 *
 * Palette emits via `queueProposal({...})` which:
 *   1. Appends to the module-level buffer.
 *   2. Fires the `sf-approval-proposed` window event (for surfaces already mounted).
 * Approvals surface calls `drainProposals()` on mount to reclaim any buffered
 * proposals it missed, then keeps listening for future events.
 */

const buffer = [];
const EVT = 'sf-approval-proposed';

export const queueProposal = (partial) => {
  const now = Date.now();
  const approval = {
    id: `proposal-${now.toString(36)}`,
    ageMinutes: 0,
    provenance: { source: 'operator@coinnike', transform: 'palette-proposal', attested: 'pending' },
    ...partial,
  };
  buffer.push(approval);
  try {
    window.dispatchEvent(new CustomEvent(EVT, { detail: { approval } }));
  } catch { /* noop */ }
  return approval;
};

export const drainProposals = () => {
  const out = buffer.slice();
  buffer.length = 0;
  return out;
};

export const PROPOSAL_EVENT = EVT;
