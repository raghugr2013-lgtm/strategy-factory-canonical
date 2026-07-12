/**
 * COMMAND · Phase U.1 — Mobile/Tablet drawer + Status sheet
 * ----------------------------------------------------------------------------
 * Two single-purpose overlays used by the responsive shell:
 *
 *   <ModuleDrawer />   — left slide-in drawer with the 10 modules
 *                        (tablet: full list. briefing: filtered to .briefing)
 *
 *   <StatusSheet />    — bottom sheet showing the 6 status chips + a short
 *                        recent-audit tail. Used only in briefing posture
 *                        when the operator taps the bar status pill.
 *
 * Both close on backdrop click or Escape.
 */
import React, { useEffect } from 'react';
import { MODULES } from './LeftRail';

function useEsc(open, onClose) {
  useEffect(() => {
    if (!open) return undefined;
    const f = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', f);
    return () => window.removeEventListener('keydown', f);
  }, [open, onClose]);
}

export function ModuleDrawer({ open, onClose, onSelect, posture, activeId }) {
  useEsc(open, onClose);
  if (!open) return null;

  const visible = MODULES.filter((m) => (posture === 'briefing' ? m.briefing : true));

  return (
    <div
      data-testid="cmd-drawer-overlay"
      style={{
        position: 'fixed', inset: 0, zIndex: 60,
        background: 'rgba(7, 10, 18, 0.55)',
        display: 'flex',
      }}
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="cmd-fade-in"
        data-testid="cmd-drawer"
        style={{
          width: posture === 'briefing' ? '82vw' : 300,
          maxWidth: 360,
          height: '100vh',
          background: 'var(--cmd-surface-1)',
          borderRight: '1px solid var(--cmd-hairline)',
          display: 'flex', flexDirection: 'column',
        }}
      >
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '14px 16px', borderBottom: '1px solid var(--cmd-hairline)',
            fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-2)',
            letterSpacing: '0.14em', textTransform: 'uppercase',
          }}
        >
          modules
        </div>
        <nav style={{ flex: 1, overflow: 'auto', padding: '6px 0' }}>
          {visible.map((m) => (
            <button
              key={m.id}
              type="button"
              data-testid={`cmd-drawer-${m.id}`}
              onClick={() => { onSelect && onSelect(m.id); onClose(); }}
              className={`cmd-rail__item${activeId === m.id ? ' cmd-rail__item--active' : ''}`}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <span className="cmd-rail__glyph">
                <m.Glyph />
              </span>
              <span className="cmd-rail__label" style={{ opacity: 1 }}>
                {m.label}
              </span>
            </button>
          ))}
        </nav>
        {posture === 'briefing' && (
          <div
            style={{
              padding: '12px 16px',
              borderTop: '1px solid var(--cmd-hairline)',
              fontSize: 11, color: 'var(--cmd-ink-2)',
            }}
            data-testid="cmd-drawer-briefing-note"
          >
            Workstation-only modules are hidden in Briefing mode.
            Open this site on a desktop for the full lab.
          </div>
        )}
      </aside>
    </div>
  );
}

export function StatusSheet({ open, onClose, chips }) {
  useEsc(open, onClose);
  if (!open) return null;

  const order = ['orch', 'ingest', 'sched', 'llm', 'govern', 'kill'];

  return (
    <div
      data-testid="cmd-status-sheet-overlay"
      style={{
        position: 'fixed', inset: 0, zIndex: 70,
        background: 'rgba(7, 10, 18, 0.55)',
        display: 'flex', alignItems: 'flex-end',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="cmd-fade-in"
        data-testid="cmd-status-sheet"
        style={{
          width: '100%',
          maxHeight: '85vh',
          background: 'var(--cmd-surface-1)',
          borderTop: '1px solid var(--cmd-hairline)',
          borderTopLeftRadius: 14, borderTopRightRadius: 14,
          padding: '16px 18px 26px',
          display: 'flex', flexDirection: 'column', gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span
            style={{
              flex: 1,
              fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--cmd-ink-2)',
              letterSpacing: '0.14em', textTransform: 'uppercase',
            }}
          >
            · status
          </span>
          <button
            type="button"
            className="cmd-btn"
            data-testid="cmd-status-sheet-close"
            onClick={onClose}
          >
            close
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {order.map((k) => {
            const c = chips?.[k] || { tone: 'amber', label: k, hint: '—' };
            return (
              <div
                key={k}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px',
                  border: '1px solid var(--cmd-hairline)',
                  borderRadius: 6,
                  background: 'var(--cmd-surface-2)',
                }}
                data-testid={`cmd-status-sheet-chip-${k}`}
              >
                <span className={`chip chip--${c.tone}`} style={{ height: 24 }}>
                  <span className="chip__dot cmd-dot--live" />
                  <span className="chip__label">{c.label}</span>
                </span>
                <span style={{ flex: 1 }} />
                <span
                  style={{
                    fontSize: 11, color: 'var(--cmd-ink-2)',
                    fontFamily: 'JetBrains Mono', letterSpacing: '0.04em',
                  }}
                >
                  {c.hint}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
