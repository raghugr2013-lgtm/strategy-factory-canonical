/**
 * COMMAND · M4.5 — Danger Ribbon
 * ----------------------------------------------------------------------------
 * Thin persistent status bar at the very top of the workstation. Surfaces the
 * single highest-priority warning currently in the Operator Inbox.
 *
 * Behaviour (per operator brief):
 *   • Shows ONLY the latest high-priority warning (danger > warn).
 *   • Click → opens the Operator Inbox (no in-place actions).
 *   • Status-only — NO chat functionality, NO inputs.
 *   • Lightweight — completely hidden when the inbox is all-clear.
 */
import React from 'react';
import { selectTopAlert, fmtAgo } from './inboxEvents';
import './DangerRibbon.css';

export default function DangerRibbon({ onOpenInbox, events }) {
  const top = selectTopAlert(events);
  if (!top) return null; // all-clear → ribbon stays hidden, zero shell height impact

  const tone = top.severity === 'danger' ? 'danger' : 'warn';

  return (
    <div
      className={`m45-ribbon m45-ribbon--${tone}`}
      role="button"
      tabIndex={0}
      data-testid="danger-ribbon"
      data-severity={top.severity}
      aria-label={`${top.severity === 'danger' ? 'Danger' : 'Warning'}: ${top.title}. ${top.source}, ${fmtAgo(top.ts)}. Press Enter to open the Operator Inbox.`}
      onClick={onOpenInbox}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          if (onOpenInbox) onOpenInbox();
        }
      }}
    >
      <span className="m45-ribbon__icon" aria-hidden="true">
        {top.severity === 'danger' ? '⚠' : '⚠'}
      </span>
      <span className="m45-ribbon__sev" aria-hidden="true">
        {top.severity === 'danger' ? 'DANGER' : 'WARNING'}
      </span>
      <span className="m45-ribbon__title">{top.title}</span>
      <span className="m45-ribbon__sep" aria-hidden="true">·</span>
      <span className="m45-ribbon__source">{top.source}</span>
      <span className="m45-ribbon__sep" aria-hidden="true">·</span>
      <span className="m45-ribbon__time">{fmtAgo(top.ts)}</span>
      <span className="m45-ribbon__spacer" />
      <span className="m45-ribbon__cta" data-testid="danger-ribbon-cta">
        view inbox <span aria-hidden="true">▸</span>
      </span>
    </div>
  );
}
