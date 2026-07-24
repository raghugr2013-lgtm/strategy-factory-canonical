/*
 * UserMenu — Phase A: header-anchored disclosure with session info + role
 * badge + walkthrough launcher + sign-out.
 *
 * Extracted from shell/Header.jsx (which previously carried an inline copy)
 * and enriched with the prototype's Advanced-Lens session panel per
 * DESIGN_FREEZE_v1.0.md §1.5 (I4·I7) · prototype/src/auth/UserMenu.tsx.
 *
 * Preserved production features not present in the prototype:
 *   - Factory Walkthrough launcher
 *   - Help & About link
 *   - Role badge (operator | admin) with signature-color chip
 *   - Auth-mode indicator (fixture | live)
 *
 * New (from prototype):
 *   - Signed-in timestamp, extends-every-action hint, expiry
 *   - Advanced-Lens reveals session id + issuer + iso expiry
 *
 * Intentionally NOT ported:
 *   - "expire session (proto)" test button — a design-validation-only
 *     affordance that would leak into the production surface.
 *   - In-menu mode switcher — production keeps ModeSwitcher external
 *     (better IA than the prototype's stacked chip grid).
 */
import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, LogOut, Compass, Info } from 'lucide-react';
import { useAuthStore } from '../workspace-state/authStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useMotionEnabled, fadeIn } from '../primitives/motion';
import { openWalkthrough } from '../onboarding/FactoryWalkthrough';

const formatHHMM = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toISOString().slice(11, 16) + 'Z'; }
  catch { return '—'; }
};

export const UserMenu = () => {
  const email = useAuthStore((s) => s.email);
  const role = useAuthStore((s) => s.role);
  const authMode = useAuthStore((s) => s.authMode);
  const signedInAt = useAuthStore((s) => s.signedInAt);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const sessionId = useAuthStore((s) => s.sessionId);
  const logout = useAuthStore((s) => s.logout);
  const advancedLens = useWorkspaceStore((s) => s.advancedLens);
  const motionEnabled = useMotionEnabled();

  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const closeOnPointer = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const closeOnEsc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', closeOnPointer);
    window.addEventListener('keydown', closeOnEsc);
    return () => {
      document.removeEventListener('pointerdown', closeOnPointer);
      window.removeEventListener('keydown', closeOnEsc);
    };
  }, [open]);

  const shortLabel = email ? email.split('@')[0].toUpperCase() : 'GUEST';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        data-testid="user-menu-button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        style={triggerStyle}
      >
        {shortLabel} <ChevronDown size={12} strokeWidth={1.5} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            data-testid="user-menu"
            role="menu"
            initial={motionEnabled ? 'hidden' : 'visible'}
            animate="visible"
            exit="hidden"
            variants={fadeIn}
            style={panelStyle}
          >
            {/* ── Identity block ──────────────────────────── */}
            <div style={identityBlock}>
              <div data-testid="user-menu-email" style={emailLine}>{email || 'anonymous'}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                <span data-testid="user-menu-role" style={roleBadge(role)}>
                  <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor' }} />
                  {role || 'operator'}
                </span>
                <span data-testid="user-menu-auth-mode" style={authModeCaption}>
                  {authMode === 'live' ? 'live · /api/auth/me' : 'fixture'}
                </span>
              </div>
            </div>

            {/* ── Session panel (E2 §4.2 · prototype parity) ── */}
            <div style={sessionBlock}>
              <div style={sectionHeading}>Session</div>
              <div className="mono-num" style={metaLine} data-testid="user-menu-signed-in">
                · signed in {formatHHMM(signedInAt)}
              </div>
              <div style={metaLine}>· extends every action</div>
              <div className="mono-num" style={metaLine} data-testid="user-menu-expires">
                · expires {formatHHMM(expiresAt)} or sooner
              </div>
              {advancedLens && (
                <>
                  <div
                    className="mono-num"
                    style={{ ...metaLine, color: 'var(--content-lo)' }}
                    data-testid="user-menu-session-id"
                  >
                    · session id  {sessionId || '—'}
                  </div>
                  <div className="mono-num" style={{ ...metaLine, color: 'var(--content-lo)' }}>
                    · issued by   auth.strategy-factory
                  </div>
                  <div
                    className="mono-num"
                    style={{ ...metaLine, color: 'var(--content-lo)' }}
                    data-testid="user-menu-expires-iso"
                  >
                    · expires at  {expiresAt || '—'}
                  </div>
                </>
              )}
            </div>

            {/* ── Actions ─────────────────────────────────── */}
            <button
              data-testid="user-menu-walkthrough"
              onClick={() => { openWalkthrough(); setOpen(false); }}
              style={menuItem}
            >
              <Compass size={12} strokeWidth={1.5} /> Factory Walkthrough
            </button>
            <button
              data-testid="user-menu-help"
              onClick={() => {
                window.open('https://strategy.coinnike.com/docs', '_blank', 'noopener');
                setOpen(false);
              }}
              style={{ ...menuItem, borderBottom: '1px solid var(--stroke-1)' }}
            >
              <Info size={12} strokeWidth={1.5} /> Help &amp; About
            </button>
            <button
              data-testid="user-menu-logout"
              onClick={() => { logout(); setOpen(false); }}
              style={menuItem}
            >
              <LogOut size={12} strokeWidth={1.5} /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── styles ───────────────────────────────────────────────
const triggerStyle = {
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

const panelStyle = {
  position: 'absolute',
  top: 'calc(100% + 6px)',
  right: 0,
  minWidth: 280,
  background: 'var(--surface-2)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-2)',
  boxShadow: 'var(--elev-2)',
  zIndex: 30,
  overflow: 'hidden',
};

const identityBlock = {
  padding: 'var(--space-3)',
  borderBottom: '1px solid var(--stroke-1)',
};

const sessionBlock = {
  padding: 'var(--space-3)',
  borderBottom: '1px solid var(--stroke-1)',
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
};

const emailLine = {
  fontSize: 'var(--font-body-sm)',
  color: 'var(--content-hi)',
};

const roleBadge = (role) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '2px 8px',
  borderRadius: 999,
  background: role === 'admin'
    ? 'color-mix(in oklab, var(--accent-gold) 12%, transparent)'
    : 'color-mix(in oklab, var(--sig-info) 12%, transparent)',
  border: `1px solid color-mix(in oklab, ${role === 'admin' ? 'var(--accent-gold)' : 'var(--sig-info)'} 40%, transparent)`,
  color: role === 'admin' ? 'var(--accent-gold)' : 'var(--sig-info)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  fontWeight: 500,
});

const authModeCaption = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
};

const sectionHeading = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  marginBottom: 4,
};

const metaLine = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-md)',
  lineHeight: 1.6,
};

const menuItem = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
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

export default UserMenu;
