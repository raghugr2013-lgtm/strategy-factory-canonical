/**
 * Phase U-3 · ShortcutsOverlay
 * ----------------------------------------------------------------------------
 * Press `?` (or Shift+/ on US layouts) to surface a keyboard-shortcut cheat
 * sheet. Esc to dismiss. Read-only, additive — does not modify behaviour.
 */
import React, { useEffect, useRef } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';

const ROWS = [
  { keys: ['?'],                label: 'Show this shortcuts overlay' },
  { keys: ['⌘ K', 'Ctrl K'],    label: 'Open Command Palette' },
  { keys: ['⌘ ⇧ F'],            label: 'Toggle Focus Mode' },
  { keys: ['⌘ ⌥ C'],            label: 'Copy current URL' },
  { keys: ['⌘ .'],              label: 'Toggle Inspector pane' },
  { keys: ['⌘ ⇧ N'],            label: 'Toggle Notifications drawer' },
  { keys: ['Esc'],              label: 'Close any drawer / palette / overlay' },
];

export default function ShortcutsOverlay({ open, onClose }) {
  const cardRef = useRef(null);
  useFocusTrap(cardRef, open, { initialFocus: 'container', onEscape: onClose });

  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) { if (e.key === 'Escape') onClose && onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      data-testid="asf-shortcuts-overlay"
      className="asf-shortcuts-overlay"
      onClick={onClose}
    >
      <div
        ref={cardRef}
        className="asf-shortcuts-card"
        onClick={(e) => e.stopPropagation()}
        data-testid="asf-shortcuts-card"
        data-asf-modal=""
        role="dialog"
        aria-modal="true"
        aria-labelledby="asf-shortcuts-title"
      >
        <h3 id="asf-shortcuts-title">Keyboard Shortcuts</h3>
        {ROWS.map((r) => (
          <div className="asf-shortcuts-row" key={r.label} data-testid={`asf-shortcuts-row-${r.label.split(' ').slice(0, 2).join('-').toLowerCase()}`}>
            <div>
              {r.keys.map((k, i) => (
                <React.Fragment key={k}>
                  <kbd>{k}</kbd>
                  {i < r.keys.length - 1 && <span style={{ margin: '0 4px', color: 'var(--cmd-ink-3, #64748b)' }}>or</span>}
                </React.Fragment>
              ))}
            </div>
            <div>{r.label}</div>
          </div>
        ))}
        <div style={{ marginTop: 16, fontSize: 10, color: 'var(--cmd-ink-3, #64748b)' }}>
          Press <kbd style={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}>Esc</kbd> to close ·
          U-3 keyboard surface · read-only.
        </div>
      </div>
    </div>
  );
}
