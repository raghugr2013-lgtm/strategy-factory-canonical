/**
 * Phase U-3 · AsfDetailDrawer (drill-through pane)
 * ----------------------------------------------------------------------------
 * Generic right-edge slide-out used for drill-through navigation:
 *   KPI tile → table row → detail drawer.
 *
 * The drawer is purely presentational; callers control what to render via
 * `title` / `subtitle` / `children`. Width is posture-aware via the
 * --asf-detail-w token (default 480px desktop, 92vw on briefing).
 */
import React, { useEffect, useId, useRef } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';

export default function AsfDetailDrawer({
  open,
  onClose,
  title,
  subtitle,
  testId = 'asf-detail-drawer',
  children,
}) {
  const drawerRef = useRef(null);
  const titleId = useId();

  useFocusTrap(drawerRef, open, { initialFocus: 'first', onEscape: onClose });

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
          data-testid={`${testId}-overlay`}
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0, zIndex: 86,
            background: 'rgba(7,10,18,0.55)',
          }}
        />
      )}
      <aside
        ref={drawerRef}
        data-testid={testId}
        data-asf-modal=""
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-hidden={!open}
        className="asf-detail-drawer"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 'var(--asf-detail-w, min(520px, 92vw))', zIndex: 87,
          background: 'var(--asf-surface-1, #0f1420)',
          borderLeft: '1px solid var(--asf-hairline, #1f2937)',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 220ms cubic-bezier(.4,.2,.2,1)',
          display: 'flex', flexDirection: 'column',
          boxShadow: open ? '-12px 0 32px rgba(0,0,0,0.4)' : 'none',
        }}
      >
        <header
          style={{
            display: 'flex', alignItems: 'baseline', gap: 10,
            padding: '14px 16px', borderBottom: '1px solid var(--asf-hairline, #1f2937)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
            {subtitle && (
              <span
                data-testid={`${testId}-subtitle`}
                style={{
                  fontFamily: 'JetBrains Mono', fontSize: 9, letterSpacing: '0.2em',
                  textTransform: 'uppercase', color: 'var(--asf-ink-3, #64748b)',
                }}
              >
                {subtitle}
              </span>
            )}
            {title && (
              <h2
                id={titleId}
                data-testid={`${testId}-title`}
                style={{
                  fontSize: 14, color: 'var(--asf-text-primary, #f3f4f6)', fontWeight: 600, margin: 0,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}
              >
                {title}
              </h2>
            )}
          </div>
          <button
            type="button"
            data-testid={`${testId}-close`}
            onClick={onClose}
            className="kbd"
            aria-label="Close detail panel (Escape)"
            style={{ cursor: 'pointer', background: 'transparent' }}
          >
            esc
          </button>
        </header>
        <div style={{ overflow: 'auto', flex: 1, padding: '14px 16px' }}>
          {children}
        </div>
      </aside>
    </>
  );
}
