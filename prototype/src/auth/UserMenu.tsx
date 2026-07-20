/*
 * UserMenu — E2 §4.2, §7, §8.
 * Header-anchored disclosure with session info, mode switcher, sign-out.
 * Advanced Lens (E2 §4.2) exposes session id + issued-by + hard expiry.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, LogOut, RefreshCw } from 'lucide-react';
import { useAuthStore } from '../workspace-state/authStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useMotionEnabled, fadeIn } from '../primitives/motion';

const modes: Array<'executive' | 'operations' | 'research' | 'developer'> =
  ['executive', 'operations', 'research', 'developer'];

const formatHHMM = (iso: string) => new Date(iso).toISOString().slice(11, 16);

export const UserMenu: React.FC = () => {
  const { session, signOut, expireSession } = useAuthStore();
  const { mode, setMode, advancedLens } = useWorkspaceStore();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const wrapRef = useRef<HTMLDivElement>(null);
  const motionEnabled = useMotionEnabled();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!session) return null;

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button
        data-testid="user-menu-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: 'transparent',
          border: '1px solid var(--stroke-2)',
          borderRadius: 'var(--radius-1)',
          color: 'var(--content-md)',
          fontFamily: 'inherit',
          fontSize: 'var(--font-caption)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          padding: '4px 8px',
          cursor: 'pointer',
        }}
      >
        {session.displayName.toLowerCase()} · {session.role}
        <ChevronDown size={12} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            data-testid="user-menu-panel"
            role="menu"
            initial={motionEnabled ? 'hidden' : 'visible'}
            animate="visible" exit="hidden"
            variants={fadeIn}
            style={{
              position: 'absolute',
              top: 'calc(100% + 6px)', right: 0,
              minWidth: 280,
              background: 'var(--surface-1)',
              border: '1px solid var(--stroke-2)',
              borderRadius: 'var(--radius-2)',
              boxShadow: 'var(--elev-2)',
              padding: 'var(--space-3)',
              display: 'flex', flexDirection: 'column', gap: 'var(--space-3)',
              zIndex: 30,
            }}
          >
            <div>
              <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)' }}>
                {session.email}
              </div>
              <div
                style={{
                  fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                  textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2,
                }}
              >
                ● {mode} mode
              </div>
            </div>

            <div>
              <div style={heading}>Session</div>
              <div className="mono-num" style={metaLine}>· signed in {formatHHMM(session.signedInAt)}</div>
              <div style={metaLine}>· extends every action</div>
              <div className="mono-num" style={metaLine}>· expires {formatHHMM(session.expiresAt)} or sooner</div>
              {advancedLens && (
                <>
                  <div className="mono-num" style={metaLine}>· session id  {session.sessionId}</div>
                  <div className="mono-num" style={metaLine}>· issued by   auth.strategy-factory</div>
                  <div className="mono-num" style={metaLine}>· expires at  {session.expiresAt}</div>
                </>
              )}
            </div>

            <div>
              <div style={heading}>Mode</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {modes.map((m) => (
                  <button
                    key={m}
                    data-testid={`user-menu-mode-${m}`}
                    onClick={() => setMode(m)}
                    style={{
                      background: mode === m ? 'var(--sig-info)' : 'var(--surface-2)',
                      color: mode === m ? 'var(--surface-0)' : 'var(--content-md)',
                      border: '1px solid var(--stroke-2)',
                      borderRadius: 'var(--radius-1)',
                      padding: '4px 8px',
                      fontSize: 'var(--font-caption)',
                      fontFamily: 'ui-monospace, monospace',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      cursor: 'pointer',
                    }}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
              <button
                data-testid="user-menu-expire"
                onClick={() => { expireSession(); setOpen(false); nav(`/auth/sign-in?next=${encodeURIComponent(window.location.pathname)}`); }}
                title="Prototype only — simulate a 401 to exercise E2 §5"
                style={menuButton}
              >
                <RefreshCw size={12} /> expire session (proto)
              </button>
              <button
                data-testid="user-menu-signout"
                onClick={() => { signOut(); nav('/auth/sign-in'); }}
                style={{ ...menuButton, color: 'var(--sig-warn)', borderColor: 'var(--sig-warn)' }}
              >
                <LogOut size={12} /> sign out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const heading: React.CSSProperties = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  marginBottom: 4,
};

const metaLine: React.CSSProperties = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-md)',
  lineHeight: 1.6,
};

const menuButton: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  background: 'transparent',
  border: '1px solid var(--stroke-2)',
  color: 'var(--content-md)',
  borderRadius: 'var(--radius-1)',
  padding: '6px 8px',
  fontFamily: 'inherit',
  fontSize: 'var(--font-caption)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
};
