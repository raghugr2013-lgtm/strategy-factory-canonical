/**
 * COMMAND · M4 — Operator Inbox Drawer
 * ----------------------------------------------------------------------------
 * Lightweight categorised event stream for the operator. NOT a chat system —
 * a notification-oriented inbox that aggregates posture-meaningful events
 * from the workstation backends.
 *
 * Five categories (per operator brief):
 *   • Factory Events       (Generate / Mutate / Validate / Auto Factory runner)
 *   • Validation Events    (Validation suite · BI5 realism · OOS · MC)
 *   • Deployment Events    (Master Bot compile · signing · cBot pack · deploy)
 *   • Infrastructure Events(BI5 ingest · scheduler · LLM runner · governance)
 *   • Marketplace Events   (future · Phase 15 reservation — grayed out)
 *
 * Each event carries:
 *   { severity, ts, source, title, subtitle, quickAction: { label, route } }
 *
 * Lock: 12_M1_ARCHITECTURAL_PRINCIPLES.md P1 (preserve capability surfaces)
 *       and 10_FUTURE_PHASES (Phase 15 marketplace stream reserved, not wired).
 */
import React, { useEffect, useRef, useState, useMemo } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';
import { MOCK_EVENTS, INBOX_CATEGORIES as CATEGORIES, SEVERITY_TONE, fmtAgo } from './inboxEvents';
import './OperatorInboxDrawer.css';

export default function OperatorInboxDrawer({ open, onClose, onNavigate, events = MOCK_EVENTS }) {
  const drawerRef = useRef(null);
  const previouslyFocusedRef = useRef(null);
  const [filter, setFilter] = useState('all');

  // Focus trap + Escape-to-close, mirroring AsfNotificationDrawer.
  useFocusTrap(drawerRef, open, { initialFocus: 'first', onEscape: onClose });
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) { if (e.key === 'Escape') onClose && onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // M5 a11y nit fix: capture the element that had focus when the drawer
  // opened, and restore focus to it on close. Standard ARIA dialog pattern —
  // ensures keyboard / screen-reader users return to the inbox trigger
  // after dismissing the drawer.
  useEffect(() => {
    if (open) {
      previouslyFocusedRef.current = (typeof document !== 'undefined') ? document.activeElement : null;
    } else if (previouslyFocusedRef.current && typeof previouslyFocusedRef.current.focus === 'function') {
      // Defer the focus restoration until after React commits the close
      // transition so we don't fight the focus trap's cleanup.
      const el = previouslyFocusedRef.current;
      previouslyFocusedRef.current = null;
      window.requestAnimationFrame(() => {
        try { el.focus(); } catch (_) { /* element may be unmounted */ }
      });
    }
  }, [open]);

  // Group events by category, sorted by ts desc.
  const grouped = useMemo(() => {
    const out = {};
    CATEGORIES.forEach(c => { out[c.id] = []; });
    events.forEach(e => {
      if (out[e.category]) out[e.category].push(e);
    });
    Object.keys(out).forEach(k => out[k].sort((a, b) => b.ts - a.ts));
    return out;
  }, [events]);

  const totalsByCat = useMemo(() => {
    const out = {};
    CATEGORIES.forEach(c => { out[c.id] = (grouped[c.id] || []).length; });
    return out;
  }, [grouped]);

  const totalAll = events.length;
  const dangerCount = events.filter(e => e.severity === 'danger').length;
  const warnCount   = events.filter(e => e.severity === 'warn').length;

  const handleQuickAction = (route) => {
    if (typeof window === 'undefined' || !route) return;
    // Use the existing router pattern: pushState + popstate dispatch so
    // sibling useRoute() consumers re-render. Hash navigation is supported.
    const [path, hash] = route.split('#');
    if (path && window.location.pathname !== path) {
      window.history.pushState({}, '', route);
    } else if (hash) {
      window.history.replaceState({}, '', `${window.location.pathname}#${hash}`);
    }
    try { window.dispatchEvent(new PopStateEvent('popstate', { state: {} })); } catch (_) { /* noop */ }
    try { window.dispatchEvent(new HashChangeEvent('hashchange')); } catch (_) { /* noop */ }
    if (onNavigate) onNavigate(route);
    if (onClose) onClose();
  };

  return (
    <>
      {open && (
        <div
          data-testid="inbox-overlay"
          onClick={onClose}
          className="m4-inbox__overlay"
          aria-hidden="true"
        />
      )}
      <aside
        ref={drawerRef}
        className={`m4-inbox${open ? ' m4-inbox--open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="m4-inbox-title"
        data-testid="operator-inbox-drawer"
        data-open={open ? '1' : '0'}
      >
        <header className="m4-inbox__hd">
          <div className="m4-inbox__hd-row">
            <span className="m4-inbox__badge">OPERATOR INBOX</span>
            <h2 id="m4-inbox-title" className="m4-inbox__title">Events stream</h2>
            <button
              type="button"
              className="m4-inbox__close"
              data-testid="inbox-close"
              onClick={onClose}
              aria-label="Close inbox"
            >
              ✕
            </button>
          </div>
          <p className="m4-inbox__sub">
            Lightweight notification stream · ⌘⇧I to toggle · ASF stays private,
            customers never see these events.
          </p>
          <div className="m4-inbox__counters" role="status">
            <span className="m4-inbox__counter">
              <strong>{totalAll}</strong> total
            </span>
            {dangerCount > 0 && (
              <span className="m4-inbox__counter m4-inbox__counter--danger">
                <strong>{dangerCount}</strong> danger
              </span>
            )}
            {warnCount > 0 && (
              <span className="m4-inbox__counter m4-inbox__counter--warn">
                <strong>{warnCount}</strong> warn
              </span>
            )}
          </div>
          <nav className="m4-inbox__filters" aria-label="Category filter">
            <button
              type="button"
              className={`m4-inbox__filter${filter === 'all' ? ' m4-inbox__filter--active' : ''}`}
              data-testid="inbox-filter-all"
              onClick={() => setFilter('all')}
            >
              All <span className="m4-inbox__filter-n">{totalAll}</span>
            </button>
            {CATEGORIES.map(c => (
              <button
                key={c.id}
                type="button"
                className={`m4-inbox__filter${filter === c.id ? ' m4-inbox__filter--active' : ''}${c.future ? ' m4-inbox__filter--future' : ''}`}
                data-testid={`inbox-filter-${c.id}`}
                onClick={() => setFilter(c.id)}
                style={{ '--cat-accent': c.accent }}
              >
                <span className="m4-inbox__filter-glyph">{c.icon}</span>
                {c.label.replace(' Events', '')}
                <span className="m4-inbox__filter-n">{c.future ? '·' : (totalsByCat[c.id] || 0)}</span>
              </button>
            ))}
          </nav>
        </header>

        <div className="m4-inbox__body" role="region" aria-label="Inbox events">
          {CATEGORIES.filter(c => filter === 'all' || filter === c.id).map(cat => (
            <section
              key={cat.id}
              className={`m4-inbox__cat${cat.future ? ' m4-inbox__cat--future' : ''}`}
              data-testid={`inbox-cat-${cat.id}`}
              style={{ '--cat-accent': cat.accent }}
            >
              <header className="m4-inbox__cat-hd">
                <span className="m4-inbox__cat-glyph" aria-hidden="true">{cat.icon}</span>
                <h3 className="m4-inbox__cat-label">{cat.label}</h3>
                <span className="m4-inbox__cat-n">{cat.future ? 'reserved' : (totalsByCat[cat.id] || 0)}</span>
              </header>
              <ul className="m4-inbox__list">
                {cat.future ? (
                  <li className="m4-inbox__future" data-testid={`inbox-cat-${cat.id}-future`}>
                    <span className="m4-inbox__future-badge">RESERVED · PHASE 15</span>
                    <p className="m4-inbox__future-copy">
                      The Marketplace events stream activates when the public
                      product distribution layer lands (Phase 15). ASF will
                      surface listing rotations, customer activity counts,
                      and licence-state changes here — but the customers
                      themselves never reach into ASF.
                    </p>
                  </li>
                ) : (grouped[cat.id] || []).length === 0 ? (
                  <li className="m4-inbox__empty" data-testid={`inbox-cat-${cat.id}-empty`}>
                    No events.
                  </li>
                ) : (
                  (grouped[cat.id] || []).map(ev => {
                    const tone = SEVERITY_TONE[ev.severity] || SEVERITY_TONE.info;
                    return (
                      <li
                        key={ev.id}
                        className={`m4-inbox__evt m4-inbox__evt--${ev.severity}`}
                        data-testid={`inbox-evt-${ev.id}`}
                      >
                        <span
                          className="m4-inbox__evt-dot"
                          style={{ background: tone.dot, boxShadow: `0 0 8px ${tone.dot}55` }}
                          aria-label={`Severity ${tone.label}`}
                        />
                        <div className="m4-inbox__evt-body">
                          <div className="m4-inbox__evt-meta">
                            <span className="m4-inbox__evt-source" title={ev.source}>{ev.source}</span>
                            <span className="m4-inbox__evt-time">{fmtAgo(ev.ts)}</span>
                          </div>
                          <p className="m4-inbox__evt-title">{ev.title}</p>
                          {ev.subtitle && (
                            <p className="m4-inbox__evt-sub">{ev.subtitle}</p>
                          )}
                          {ev.quickAction && (
                            <button
                              type="button"
                              className="m4-inbox__evt-action"
                              data-testid={`inbox-evt-${ev.id}-action`}
                              onClick={() => handleQuickAction(ev.quickAction.route)}
                            >
                              {ev.quickAction.label} <span aria-hidden="true">▸</span>
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })
                )}
              </ul>
            </section>
          ))}
        </div>

        <footer className="m4-inbox__ft">
          <span className="m4-inbox__ft-key">Schema</span>
          <span className="m4-inbox__ft-val">
            severity · ts · source · title · subtitle · quickAction — forward-compatible with the
            future <code>/api/inbox/events</code> ledger
          </span>
        </footer>
      </aside>
    </>
  );
}
