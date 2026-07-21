/*
 * LoginScreen — Trust Before Credentials (E2 §9).
 * refs DESIGN_FREEZE_v1.0.md §1.2 principle E1 · §1.4 surface Login
 *
 * Pre-auth signals visible: product wordmark · UTC clock · mode chip ·
 * env identifier · status rail · kill-posture indicator · left-rail preview.
 * The AppShell is not rendered on this route; instead, LoginScreen paints
 * its own trust-signal chrome.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../workspace-state/authStore';
import { DEFAULT_AUTHENTICATED_ROUTE } from '../routing/routes';
import { StatusRail } from '../shell/StatusRail';
import { ROUTES } from '../routing/routes';

const useUtcClock = () => {
  const [utc, setUtc] = useState('');
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const hh = String(d.getUTCHours()).padStart(2, '0');
      const mm = String(d.getUTCMinutes()).padStart(2, '0');
      const ss = String(d.getUTCSeconds()).padStart(2, '0');
      setUtc(`${hh}:${mm}:${ss}Z`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return utc;
};

export const LoginScreen = () => {
  const utc = useUtcClock();
  const stance = useAuthStore((s) => s.stance);
  const error = useAuthStore((s) => s.error);
  const login = useAuthStore((s) => s.login);
  const clearError = useAuthStore((s) => s.clearError);
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    if (stance === 'authenticated') {
      const nextParam = new URLSearchParams(location.search).get('next');
      navigate(nextParam || DEFAULT_AUTHENTICATED_ROUTE, { replace: true });
    }
  }, [stance, navigate, location.search]);

  const onSubmit = async (e) => {
    e.preventDefault();
    await login(email.trim(), password);
  };

  return (
    <div className="os-body" data-testid="login-screen"
         style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '220px 1fr', gridTemplateRows: 'auto 1fr auto' }}>

      {/* Left rail preview (pre-auth trust signal 1) */}
      <aside data-testid="login-leftrail-preview"
             style={{ gridRow: '1 / span 2', background: 'var(--surface-1)', borderRight: '1px solid var(--stroke-1)', padding: 'var(--space-4)' }}>
        <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 'var(--space-4)' }}>
          Navigation
        </div>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {ROUTES.map((r) => (
            <li key={r.path}
                data-testid={`login-nav-preview-${r.surface}`}
                style={{ color: 'var(--content-lo)', fontSize: 'var(--font-body-sm)', letterSpacing: '0.06em', padding: 'var(--space-2) 0', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <r.icon size={14} strokeWidth={1.5} />
              <span>{r.label}</span>
            </li>
          ))}
        </ul>
      </aside>

      {/* Top bar (pre-auth trust signals 2-5) */}
      <header data-testid="login-topbar"
              style={{ gridColumn: '2', background: 'var(--surface-1)', borderBottom: '1px solid var(--stroke-1)', padding: 'var(--space-3) var(--space-5)', display: 'flex', alignItems: 'center', gap: 'var(--space-5)', fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--content-md)' }}>
        <span data-testid="wordmark" style={{ color: 'var(--content-hi)', fontWeight: 600, letterSpacing: '0.12em' }}>Strategy · Factory</span>
        <span data-testid="cmdk-hint-disabled" style={{ color: 'var(--content-lo)' }}>⌘K disabled</span>
        <span data-testid="mode-preview">Mode · Operations</span>
        <span style={{ marginLeft: 'auto' }} data-testid="utc-clock" className="mono-num">{utc}</span>
        <span data-testid="env-tag" style={{ color: 'var(--content-lo)' }}>Env · Preview</span>
      </header>

      {/* Login card */}
      <main style={{ gridColumn: '2', display: 'grid', placeItems: 'center', padding: 'var(--space-6)' }}>
        <form onSubmit={onSubmit} data-testid="login-form"
              style={{ width: 380, background: 'var(--surface-1)', border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-3)', padding: 'var(--space-6)', boxShadow: 'var(--elev-2)' }}>
          <h1 style={{ margin: 0, marginBottom: 'var(--space-4)', fontSize: 'var(--font-h3)', fontWeight: 500, letterSpacing: '-0.01em' }}>
            Sign in
          </h1>
          <p style={{ margin: 0, marginBottom: 'var(--space-5)', color: 'var(--content-md)', fontSize: 'var(--font-body-sm)', lineHeight: 1.55 }}>
            The Factory needs to know who's on shift before it hands you the controls.
          </p>

          <label htmlFor="email" style={{ display: 'block', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 'var(--space-2)' }}>Email</label>
          <input id="email" type="email" autoComplete="username" value={email}
                 onChange={(e) => { setEmail(e.target.value); if (error) clearError(); }}
                 data-testid="login-email"
                 style={inputStyle} />

          <label htmlFor="password" style={{ display: 'block', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.08em', textTransform: 'uppercase', margin: 'var(--space-4) 0 var(--space-2)' }}>Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password}
                 onChange={(e) => { setPassword(e.target.value); if (error) clearError(); }}
                 data-testid="login-password"
                 style={inputStyle} />

          {error && (
            <div data-testid="login-error"
                 role="alert"
                 style={{ marginTop: 'var(--space-3)', color: 'var(--sig-crit)', fontSize: 'var(--font-body-sm)' }}>
              {error}
            </div>
          )}

          <button type="submit"
                  data-testid="login-submit"
                  disabled={stance === 'authenticating'}
                  style={{ marginTop: 'var(--space-5)', width: '100%', background: 'var(--sig-info)', color: 'var(--surface-0)', border: 'none', borderRadius: 'var(--radius-2)', padding: 'var(--space-3) var(--space-4)', fontSize: 'var(--font-body-sm)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', cursor: 'pointer', opacity: stance === 'authenticating' ? 0.6 : 1 }}>
            {stance === 'authenticating' ? 'Signing in…' : 'Sign in'}
          </button>

          <div data-testid="login-fixture-credentials"
               style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)', background: 'var(--surface-2)', border: '1px dashed var(--stroke-2)', borderRadius: 'var(--radius-2)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', lineHeight: 1.6 }}>
            <div style={{ color: 'var(--content-md)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-1)' }}>Fixture credentials (Sprint 1 M1)</div>
            operator@coinnike.com · prototype123
          </div>
        </form>
      </main>

      {/* Status rail (pre-auth trust signals 6-8) */}
      <div style={{ gridColumn: '1 / -1' }}>
        <StatusRail preAuth />
      </div>
    </div>
  );
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  background: 'var(--surface-2)',
  color: 'var(--content-hi)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-2)',
  padding: 'var(--space-3)',
  fontSize: 'var(--font-body-sm)',
  fontFamily: 'inherit',
  outline: 'none',
};
