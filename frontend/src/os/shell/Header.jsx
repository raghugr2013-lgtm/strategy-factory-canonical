/*
 * Header — top-of-shell chrome.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · D8 §3.5 (I4·I7)
 *
 * Contains: wordmark · surface eyebrow · ⌘K hint · mode switcher ·
 * advanced-lens toggle · density switcher · UTC clock · env tag · user menu.
 */
import React, { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useWorkspaceStore, MODES, DENSITIES } from '../workspace-state/store';
import { ROUTES } from '../routing/routes';
import { ChevronDown } from 'lucide-react';
import { WorkspaceContextChip } from './WorkspaceContextChip';
import { UserMenu } from '../auth/UserMenu';

const useUtcClock = () => {
  const [t, setT] = useState('');
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const hh = String(d.getUTCHours()).padStart(2, '0');
      const mm = String(d.getUTCMinutes()).padStart(2, '0');
      const ss = String(d.getUTCSeconds()).padStart(2, '0');
      setT(`${hh}:${mm}:${ss}Z`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return t;
};

export const Header = () => {
  const utc = useUtcClock();
  const location = useLocation();
  const currentRoute = ROUTES.find((r) => location.pathname.startsWith(r.path));
  const surfaceLabel = currentRoute?.label ?? '—';

  return (
    <div style={{
      background: 'var(--surface-1)',
      borderBottom: '1px solid var(--stroke-1)',
      padding: 'var(--space-3) var(--space-5)',
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-5)',
      fontSize: 'var(--font-caption)',
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: 'var(--content-md)',
    }}>
      <span data-testid="wordmark" style={{ color: 'var(--content-hi)', fontWeight: 600, letterSpacing: '0.12em' }}>Strategy · Factory</span>
      <span style={{ color: 'var(--content-lo)' }}>/</span>
      <span data-testid="surface-eyebrow" style={{ color: 'var(--content-hi)' }}>{surfaceLabel}</span>

      <span data-testid="cmdk-hint" style={{ marginLeft: 'var(--space-4)', color: 'var(--content-lo)' }}>⌘K · find anything</span>

      <WorkspaceContextChip />

      <ModeSwitcher />
      <AdvancedLensToggle />
      <DensitySwitcher />

      <span style={{ marginLeft: 'auto' }} className="mono-num" data-testid="utc-clock">{utc}</span>
      <span data-testid="env-tag" style={{ color: 'var(--content-lo)' }}>Env · Preview</span>

      <UserMenu />
    </div>
  );
};

const ModeSwitcher = () => {
  const mode = useWorkspaceStore((s) => s.mode);
  const setMode = useWorkspaceStore((s) => s.setMode);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button data-testid="mode-switcher-button"
              onClick={() => setOpen((o) => !o)}
              style={btnStyle}>
        Mode · {mode.toUpperCase()} <ChevronDown size={12} strokeWidth={1.5} />
      </button>
      {open && (
        <div data-testid="mode-switcher-menu"
             style={menuStyle}>
          {MODES.map((m) => (
            <button key={m}
                    data-testid={`mode-option-${m}`}
                    onClick={() => { setMode(m); setOpen(false); }}
                    style={{ ...menuItemStyle, color: m === mode ? 'var(--sig-info)' : 'var(--content-md)' }}>
              {m.toUpperCase()}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const AdvancedLensToggle = () => {
  const advancedLens = useWorkspaceStore((s) => s.advancedLens);
  const toggle = useWorkspaceStore((s) => s.toggleAdvancedLens);
  return (
    <button data-testid="advanced-lens-toggle"
            onClick={toggle}
            aria-pressed={advancedLens}
            style={{
              ...btnStyle,
              color: advancedLens ? 'var(--sig-info)' : 'var(--content-md)',
              borderColor: advancedLens ? 'var(--sig-info)' : 'var(--stroke-2)',
            }}>
      Lens · {advancedLens ? 'Advanced' : 'Standard'}
    </button>
  );
};

const DensitySwitcher = () => {
  const density = useWorkspaceStore((s) => s.density);
  const setDensity = useWorkspaceStore((s) => s.setDensity);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button data-testid="density-switcher-button"
              onClick={() => setOpen((o) => !o)}
              style={btnStyle}>
        Density · {density.toUpperCase()} <ChevronDown size={12} strokeWidth={1.5} />
      </button>
      {open && (
        <div data-testid="density-switcher-menu" style={menuStyle}>
          {DENSITIES.map((d) => (
            <button key={d}
                    data-testid={`density-option-${d}`}
                    onClick={() => { setDensity(d); setOpen(false); }}
                    style={{ ...menuItemStyle, color: d === density ? 'var(--sig-info)' : 'var(--content-md)' }}>
              {d.toUpperCase()}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const btnStyle = {
  background: 'transparent',
  color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '4px 10px',
  fontSize: 'var(--font-caption)',
  fontFamily: 'inherit',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  cursor: 'pointer',
};

const menuStyle = {
  position: 'absolute',
  top: 'calc(100% + 4px)',
  left: 0,
  background: 'var(--surface-2)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-2)',
  boxShadow: 'var(--elev-2)',
  minWidth: 160,
  zIndex: 20,
  overflow: 'hidden',
};

const menuItemStyle = {
  display: 'block',
  width: '100%',
  background: 'transparent',
  color: 'var(--content-md)',
  border: 'none',
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--font-caption)',
  fontFamily: 'inherit',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  textAlign: 'left',
  cursor: 'pointer',
};
