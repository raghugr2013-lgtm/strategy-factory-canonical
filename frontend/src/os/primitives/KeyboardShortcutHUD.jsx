/*
 * KeyboardShortcut + KeyboardShortcutHUD — Bible §7.10.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useMotionEnabled, fadeIn } from './motion';

export const KeyboardShortcut = ({ chord, label, testId }) => (
  <span data-testid={testId ?? `kbd-${chord.replace(/\W+/g, '')}`}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}>
    <kbd className="mono-num"
         style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                  background: 'var(--surface-2)', border: '1px solid var(--stroke-2)',
                  borderBottom: '2px solid var(--stroke-2)', borderRadius: 'var(--radius-1)',
                  padding: '2px 6px', lineHeight: 1 }}>
      {chord}
    </kbd>
    {label && (
      <span style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                     textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </span>
    )}
  </span>
);

const DEFAULT_ENTRIES = [
  { chord: '⌘K', label: 'find anything' },
  { chord: '⌘/', label: 'toggle advanced lens' },
  { chord: '⌘[', label: 'back' },
  { chord: '⌘]', label: 'forward' },
  { chord: 'g m', label: 'go · mission control' },
  { chord: 'g t', label: 'go · timeline' },
  { chord: 'g a', label: 'go · approvals' },
  { chord: 'Esc', label: 'close overlay' },
  { chord: '?', label: 'toggle this HUD' },
];

export const KeyboardShortcutHUD = ({ entries = DEFAULT_ENTRIES, triggerKey = '?', testId }) => {
  const [open, setOpen] = useState(false);
  const motionEnabled = useMotionEnabled();

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === triggerKey && !e.metaKey && !e.ctrlKey) {
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [triggerKey]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div data-testid={testId ?? 'keyboard-shortcut-hud'}
                    role="dialog" aria-label="Keyboard shortcuts"
                    initial={motionEnabled ? 'hidden' : 'visible'} animate="visible"
                    exit={motionEnabled ? 'hidden' : 'visible'} variants={fadeIn}
                    onClick={() => setOpen(false)}
                    style={{ position: 'fixed', inset: 0, background: 'rgba(5,7,10,0.72)',
                             backdropFilter: 'blur(6px)', display: 'flex',
                             alignItems: 'center', justifyContent: 'center', zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()}
               style={{ minWidth: 480, background: 'var(--surface-1)',
                        border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-3)',
                        padding: 'var(--space-5)', boxShadow: 'var(--elev-2)' }}>
            <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-4)' }}>
              Keyboard shortcuts
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 'var(--space-2)' }}>
              {entries.map((e) => (
                <div key={e.chord}
                     style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                              padding: 'var(--space-2) 0', borderBottom: '1px solid var(--stroke-1)' }}>
                  <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>{e.label}</span>
                  <KeyboardShortcut chord={e.chord} />
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
