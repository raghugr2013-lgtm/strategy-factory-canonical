/**
 * Phase U-3 · AsfNotificationDrawer
 * ----------------------------------------------------------------------------
 * Right-side slide-out that surfaces queued operator notifications.
 * Driven by `/app/frontend/src/stores/notificationsStore.js`.
 * Tone tokens map to the existing asf-verdict palette.
 */
import React, { useEffect, useRef } from 'react';
import { useNotifications, dismiss, dismissAll, markAllRead } from '../../stores/notificationsStore';
import useFocusTrap from '../../hooks/useFocusTrap';

const TONE_DOT = {
  info:    'var(--asf-cyan, #38bdf8)',
  success: 'var(--asf-emerald, #34d399)',
  warn:    'var(--asf-amber, #fbbf24)',
  danger:  'var(--asf-rose, #f87171)',
};

function fmtAgo(at) {
  const dt = Math.max(0, Date.now() - at);
  if (dt < 60_000) return 'just now';
  if (dt < 3_600_000) return `${Math.floor(dt / 60_000)}m ago`;
  if (dt < 86_400_000) return `${Math.floor(dt / 3_600_000)}h ago`;
  return `${Math.floor(dt / 86_400_000)}d ago`;
}

export default function AsfNotificationDrawer({ open, onClose }) {
  const { items } = useNotifications();
  const drawerRef = useRef(null);

  // Mark all read when drawer opens (one render after open=true).
  useEffect(() => { if (open) markAllRead(); }, [open]);

  // U-4.1 — focus trap: keeps Tab inside the drawer + restores focus on close.
  useFocusTrap(drawerRef, open, { initialFocus: 'first', onEscape: onClose });

  // Esc to close
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) { if (e.key === 'Escape') onClose && onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <>
      {open && (
        <div
          data-testid="asf-notification-overlay"
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0, zIndex: 90,
            background: 'rgba(7,10,18,0.55)',
          }}
        />
      )}
      <aside
        ref={drawerRef}
        data-testid="asf-notification-drawer"
        data-asf-modal=""
        role="dialog"
        aria-modal="true"
        aria-labelledby="asf-notification-drawer-title"
        aria-hidden={!open}
        className="asf-notification-drawer"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 'min(420px, 92vw)', zIndex: 91,
          background: 'var(--asf-bg-surface, #0f1420)',
          borderLeft: '1px solid var(--asf-border-default, #1f2937)',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 220ms cubic-bezier(.4,.2,.2,1)',
          display: 'flex', flexDirection: 'column',
          boxShadow: open ? '-12px 0 32px rgba(0,0,0,0.4)' : 'none',
        }}
      >
        <header
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '12px 14px', borderBottom: '1px solid var(--asf-border-default, #1f2937)',
          }}
        >
          <h2
            id="asf-notification-drawer-title"
            style={{
              fontFamily: 'JetBrains Mono', fontSize: 10, letterSpacing: '0.18em',
              textTransform: 'uppercase', color: 'var(--asf-text-secondary, #94a3b8)',
              margin: 0, fontWeight: 600,
            }}
          >
            Notifications
          </h2>
          <span style={{ flex: 1 }} />
          {items.length > 0 && (
            <button
              type="button"
              data-testid="asf-notification-dismiss-all"
              onClick={dismissAll}
              className="kbd"
              aria-label="Clear all notifications"
              style={{ cursor: 'pointer', background: 'transparent' }}
            >
              clear all
            </button>
          )}
          <button
            type="button"
            data-testid="asf-notification-close"
            onClick={onClose}
            className="kbd"
            aria-label="Close notifications (Escape)"
            style={{ cursor: 'pointer', background: 'transparent' }}
          >
            esc
          </button>
        </header>

        <div style={{ overflow: 'auto', flex: 1, padding: '8px 10px' }}>
          {items.length === 0 && (
            <div
              data-testid="asf-notification-empty"
              style={{ padding: '32px 12px', textAlign: 'center', color: 'var(--asf-ink-3, #64748b)', fontSize: 12 }}
            >
              <div style={{ fontSize: 18, marginBottom: 8 }}>·</div>
              No notifications.
              <div style={{ fontSize: 10, marginTop: 6, opacity: 0.7 }}>
                Operator events, Retry failures, and workflow milestones surface here.
              </div>
            </div>
          )}
          {items.map((n) => (
            <article
              key={n.id}
              data-testid={`asf-notification-item-${n.slug || n.id}`}
              style={{
                display: 'grid', gridTemplateColumns: '8px 1fr auto', gap: 10,
                padding: '10px 10px',
                borderBottom: '1px solid var(--asf-hairline, #1f2937)',
                alignItems: 'start',
              }}
            >
              <span
                style={{
                  width: 8, height: 8, borderRadius: 999,
                  background: TONE_DOT[n.tone] || TONE_DOT.info,
                  marginTop: 6,
                  boxShadow: `0 0 8px ${TONE_DOT[n.tone] || TONE_DOT.info}`,
                }}
              />
              <div>
                {n.title && (
                  <div style={{ fontSize: 12, color: 'var(--asf-ink-0, #f3f4f6)', fontWeight: 600 }}>
                    {n.title}
                  </div>
                )}
                {n.body && (
                  <div style={{ fontSize: 11, color: 'var(--asf-ink-2, #94a3b8)', marginTop: 2, lineHeight: 1.45 }}>
                    {n.body}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 10, marginTop: 6, alignItems: 'center' }}>
                  <span
                    style={{
                      fontFamily: 'JetBrains Mono', fontSize: 9,
                      color: 'var(--asf-ink-3, #64748b)', textTransform: 'uppercase', letterSpacing: '0.14em',
                    }}
                  >
                    {fmtAgo(n.at)}
                  </span>
                  {n.action && (
                    <button
                      type="button"
                      data-testid={n.action.testId || `asf-notification-action-${n.id}`}
                      onClick={() => { try { n.action.onClick && n.action.onClick(); } catch (_) { /* noop */ } dismiss(n.id); }}
                      className="kbd"
                      style={{ cursor: 'pointer', background: 'transparent' }}
                    >
                      {n.action.label}
                    </button>
                  )}
                </div>
              </div>
              <button
                type="button"
                data-testid={`asf-notification-dismiss-${n.id}`}
                onClick={() => dismiss(n.id)}
                aria-label="dismiss"
                style={{
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  color: 'var(--asf-ink-3, #64748b)', fontSize: 14, lineHeight: 1, padding: 2,
                }}
              >
                ×
              </button>
            </article>
          ))}
        </div>
      </aside>
    </>
  );
}
