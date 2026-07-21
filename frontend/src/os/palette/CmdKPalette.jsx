/*
 * CmdKPalette — Sprint 1 subset (I8).
 * refs DESIGN_FREEZE_v1.0.md §2.1 (deferred → resolved) · D8 §5.4 · Bible §7.10
 *
 * Sprint 1 commands:
 *   - Jump to each surface
 *   - Toggle kill posture (M1 dev aid; M5 will wire to real state)
 *   - Sign out
 *
 * Keyboard: Cmd+K (Mac) · Ctrl+K (Linux/Win) opens. Escape closes.
 * Selection via ↑↓ + Enter or mouse.
 */
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Command } from 'cmdk';
import { ROUTES } from '../routing/routes';
import { useAuthStore } from '../workspace-state/authStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useFocusTrap } from '../features/useFocusTrap';
import { queueProposal } from '../features/paletteProposals';

// Sprint 2.0 tail-patch · R3 · thin wrapper — see features/paletteProposals.js.
const emitProposal = queueProposal;

export const CmdKPalette = () => {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const setKill = useWorkspaceStore((s) => s.setKillPosture);
  const selectedStrategy = useWorkspaceStore((s) => s.selectedStrategy);
  const inputRef = useRef(null);
  const paletteRef = useRef(null);
  useFocusTrap(paletteRef, open);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const run = (action) => {
    setOpen(false);
    setTimeout(action, 0);
  };

  if (!open) return null;

  return (
    <div data-testid="cmdk-overlay"
         role="presentation"
         onClick={() => setOpen(false)}
         style={{
           position: 'fixed',
           inset: 0,
           background: 'rgba(5, 7, 10, 0.72)',
           backdropFilter: 'blur(4px)',
           zIndex: 50,
           display: 'grid',
           placeItems: 'start center',
           paddingTop: '12vh',
         }}>
      <Command data-testid="cmdk-palette"
               ref={paletteRef}
               onClick={(e) => e.stopPropagation()}
               style={{
                 width: 600,
                 maxWidth: '90vw',
                 background: 'var(--surface-1)',
                 border: '1px solid var(--stroke-2)',
                 borderRadius: 'var(--radius-3)',
                 boxShadow: 'var(--elev-2)',
                 overflow: 'hidden',
                 fontSize: 'var(--font-body-sm)',
                 color: 'var(--content-hi)',
               }}
               label="Command palette">
        <Command.Input ref={inputRef}
                       data-testid="cmdk-input"
                       placeholder="Type a command or search…"
                       style={{
                         width: '100%',
                         boxSizing: 'border-box',
                         background: 'transparent',
                         color: 'var(--content-hi)',
                         border: 'none',
                         borderBottom: '1px solid var(--stroke-1)',
                         padding: 'var(--space-4)',
                         fontSize: 'var(--font-body)',
                         fontFamily: 'inherit',
                         outline: 'none',
                       }} />
        <Command.List style={{ maxHeight: 360, overflow: 'auto', padding: 'var(--space-2)' }}>
          <Command.Empty style={{ padding: 'var(--space-4)', color: 'var(--content-lo)', fontSize: 'var(--font-body-sm)' }}>
            No matching command.
          </Command.Empty>
          <Command.Group heading="Jump to surface" style={groupStyle}>
            {ROUTES.map((r) => (
              <Command.Item key={r.path}
                            data-testid={`cmdk-item-${r.surface}`}
                            value={`jump ${r.label}`}
                            onSelect={() => run(() => navigate(r.path))}
                            style={itemStyle}>
                <r.icon size={14} strokeWidth={1.5} />
                <span>Go to {r.label.toLowerCase()}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>{r.path}</span>
              </Command.Item>
            ))}
          </Command.Group>

          <Command.Group heading="Propose (drops into Approvals)" style={groupStyle}>
            <Command.Item data-testid="cmdk-item-propose-new-strategy"
                          value="propose new strategy"
                          onSelect={() => run(() => {
                            emitProposal({
                              title: 'Propose new strategy',
                              origin: 'proposal',
                              risk: 'low',
                              summary: 'Operator-initiated. Master Bot will run discover→generate→backtest and return an approval bundle.',
                              decisionIdentity: 'proposal-new-strategy',
                            });
                            navigate('/c/approvals');
                          })}
                          style={itemStyle}>
              Propose new strategy…
              <span style={{ marginLeft: 'auto', color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>drops in /c/approvals</span>
            </Command.Item>
            <Command.Item data-testid="cmdk-item-optimize-strategy"
                          value="optimize strategy run optimization cycle"
                          onSelect={() => run(() => {
                            emitProposal({
                              title: selectedStrategy ? `Run optimization cycle · ${selectedStrategy}` : 'Run optimization cycle',
                              origin: 'compute-quota',
                              risk: 'moderate',
                              summary: 'Requests a multi-cycle optimization pass. Compute quota adjusted for the duration of the cycle.',
                              decisionIdentity: selectedStrategy ?? 'proposal-optimize',
                            });
                            navigate('/c/approvals');
                          })}
                          style={itemStyle}>
              Optimize strategy…
              <span style={{ marginLeft: 'auto', color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>drops in /c/approvals</span>
            </Command.Item>
            <Command.Item data-testid="cmdk-item-promote-to-live"
                          value="promote to live deployment"
                          onSelect={() => run(() => {
                            emitProposal({
                              title: selectedStrategy ? `Promote ${selectedStrategy} to live` : 'Promote current strategy to live',
                              origin: 'deployment',
                              risk: 'high',
                              summary: 'Moves the selected strategy from paper to live capital. Two governance approvers required.',
                              decisionIdentity: selectedStrategy ?? 'proposal-promote',
                            });
                            navigate('/c/approvals');
                          })}
                          style={itemStyle}>
              Promote to live…
              <span style={{ marginLeft: 'auto', color: 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>drops in /c/approvals</span>
            </Command.Item>
          </Command.Group>

          <Command.Group heading="Session" style={groupStyle}>
            <Command.Item data-testid="cmdk-item-kill-posture"
                          value={killArmed ? 'disarm kill posture' : 'arm kill posture'}
                          onSelect={() => run(() => setKill(!killArmed))}
                          style={itemStyle}>
              {killArmed ? 'Disarm kill posture' : 'Arm kill posture'}
              <span style={{ marginLeft: 'auto', color: killArmed ? 'var(--sig-crit)' : 'var(--content-lo)', fontSize: 'var(--font-caption)' }}>
                {killArmed ? 'ARMED' : 'DISARMED'}
              </span>
            </Command.Item>
            <Command.Item data-testid="cmdk-item-signout"
                          value="sign out"
                          onSelect={() => run(logout)}
                          style={itemStyle}>
              Sign out
            </Command.Item>
          </Command.Group>

          <div data-testid="cmdk-current-path"
               style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--content-lo)', fontSize: 'var(--font-caption)', borderTop: '1px solid var(--stroke-1)', marginTop: 'var(--space-2)' }}>
            Currently at · <span className="mono-num">{location.pathname}</span>
          </div>
        </Command.List>
      </Command>
    </div>
  );
};

const groupStyle = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  padding: 'var(--space-2)',
};

const itemStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
  padding: 'var(--space-2) var(--space-3)',
  borderRadius: 'var(--radius-1)',
  cursor: 'pointer',
  color: 'var(--content-hi)',
};
