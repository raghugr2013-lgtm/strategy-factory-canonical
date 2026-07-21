/*
 * TimeWindowChip — F2. Reads/writes workspaceStore.timeWindow.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · Bible §14
 */
import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Clock } from 'lucide-react';
import { useWorkspaceStore } from '../workspace-state/store';

const WINDOWS = [
  { key: 'last-1h',  label: 'Last 1h' },
  { key: 'last-6h',  label: 'Last 6h' },
  { key: 'last-24h', label: 'Last 24h' },
  { key: 'last-7d',  label: 'Last 7d' },
  { key: 'last-30d', label: 'Last 30d' },
  { key: 'ytd',      label: 'Year to date' },
];

export const TimeWindowChip = ({ testId = 'time-window-chip' }) => {
  const value = useWorkspaceStore((s) => s.timeWindow);
  const setTimeWindow = useWorkspaceStore((s) => s.setTimeWindow);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = WINDOWS.find((w) => w.key === value) ?? WINDOWS[2];

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button data-testid={testId} onClick={() => setOpen((o) => !o)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                       background: 'transparent', color: 'var(--content-md)',
                       border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-1)',
                       padding: '4px 10px', fontSize: 'var(--font-caption)',
                       textTransform: 'uppercase', letterSpacing: '0.08em',
                       fontFamily: 'inherit', cursor: 'pointer' }}>
        <Clock size={12} strokeWidth={1.5} />
        {current.label}
        <ChevronDown size={12} strokeWidth={1.5} />
      </button>
      {open && (
        <div data-testid={`${testId}-menu`}
             style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0,
                      background: 'var(--surface-2)', border: '1px solid var(--stroke-2)',
                      borderRadius: 'var(--radius-2)', boxShadow: 'var(--elev-2)',
                      minWidth: 160, zIndex: 20, overflow: 'hidden' }}>
          {WINDOWS.map((w) => (
            <button key={w.key}
                    data-testid={`${testId}-${w.key}`}
                    onClick={() => { setTimeWindow(w.key); setOpen(false); }}
                    style={{ display: 'block', width: '100%', textAlign: 'left',
                             background: 'transparent',
                             color: w.key === value ? 'var(--sig-info)' : 'var(--content-md)',
                             border: 'none', padding: 'var(--space-2) var(--space-3)',
                             fontSize: 'var(--font-caption)', textTransform: 'uppercase',
                             letterSpacing: '0.08em', fontFamily: 'inherit', cursor: 'pointer' }}>
              {w.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
