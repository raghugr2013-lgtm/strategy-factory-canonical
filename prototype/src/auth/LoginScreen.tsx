/*
 * LoginScreen — E2 §3.
 * Centred card inside the persistent shell chrome. Kill posture pre-auth
 * banner renders above the sign-in header when armed (E2 §9.5).
 * Fixture credentials: operator@coinnike.com / prototype123.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertCircle, Clock } from 'lucide-react';
import { useAuthStore, type LoginErrorKind } from '../workspace-state/authStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useMotionEnabled, fadeInUp } from '../primitives/motion';

const errorCopy: Record<Exclude<LoginErrorKind, null>, string> = {
  'field-empty-email':      'Email is required.',
  'field-empty-password':   'Password is required.',
  'email-invalid':          'Enter a valid email address.',
  'credentials-wrong':      'Email or password is incorrect.',
  'account-locked':         'Account is temporarily locked. Try again in 15 minutes or contact your admin.',
  'session-expired-notice': 'Your session expired. Sign in again to resume.',
  'backend-down':           'Sign-in service is unavailable. Retrying in 8 s.',
};

const isInformational = (e: LoginErrorKind) => e === 'session-expired-notice';

export const LoginScreen: React.FC = () => {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const nextUrl = params.get('next') || '/c/mission';

  const { attemptLogin, lastError, stance } = useAuthStore();
  const killArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const motionEnabled = useMotionEnabled();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => { emailRef.current?.focus(); }, []);

  useEffect(() => {
    if (stance === 'authenticated') {
      nav(nextUrl, { replace: true });
    }
  }, [stance, nav, nextUrl]);

  useEffect(() => {
    if (lastError === 'credentials-wrong') passwordRef.current?.focus();
  }, [lastError]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    attemptLogin(email.trim(), password);
  };

  const submitting = stance === 'authenticating';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - 220px)',
      }}
    >
      <motion.form
        onSubmit={submit}
        data-testid="login-form"
        initial={motionEnabled ? 'hidden' : 'visible'}
        animate="visible"
        variants={fadeInUp}
        style={{
          width: 'min(360px, 92vw)',
          background: 'var(--surface-1)',
          border: '1px solid var(--stroke-1)',
          borderRadius: 'var(--radius-3)',
          padding: 'var(--space-5)',
          display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
          boxShadow: 'var(--elev-2)',
        }}
      >
        {killArmed && (
          <div
            data-testid="login-kill-posture-banner"
            role="note"
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)',
              background: 'rgba(107,118,132,0.12)',
              border: '1px solid var(--stroke-2)',
              color: 'var(--content-md)',
              borderRadius: 'var(--radius-2)',
              padding: 'var(--space-3)',
              fontSize: 'var(--font-caption)',
              lineHeight: 1.5,
            }}
          >
            <span style={{ color: 'var(--sig-dormant)', marginTop: 2 }}>●</span>
            <div>
              <div style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Kill posture is armed.
              </div>
              <div style={{ color: 'var(--content-lo)', marginTop: 2 }}>
                Deliberate operational freeze in effect.
              </div>
            </div>
          </div>
        )}

        <div>
          <div
            style={{
              fontSize: 'var(--font-caption)',
              color: 'var(--content-lo)',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: 'var(--space-2)',
            }}
          >
            Strategy Factory
          </div>
          <h2 style={{ margin: 0, fontSize: 'var(--font-h2)', color: 'var(--content-hi)', fontWeight: 500 }}>
            Sign in
          </h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <label htmlFor="login-email" style={fieldLabel}>Email</label>
          <input
            id="login-email"
            ref={emailRef}
            data-testid="login-email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={fieldInput}
            aria-invalid={lastError === 'field-empty-email' || lastError === 'email-invalid'}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <label htmlFor="login-password" style={fieldLabel}>Password</label>
          <input
            id="login-password"
            ref={passwordRef}
            data-testid="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={fieldInput}
            aria-invalid={lastError === 'field-empty-password' || lastError === 'credentials-wrong'}
          />
          {lastError && (
            <div
              data-testid="login-error"
              role="alert"
              aria-live="polite"
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 6,
                fontSize: 'var(--font-caption)',
                color: isInformational(lastError) ? 'var(--sig-info)' : 'var(--sig-warn)',
                lineHeight: 1.5,
              }}
            >
              {isInformational(lastError)
                ? <Clock size={12} style={{ marginTop: 2 }} />
                : <AlertCircle size={12} style={{ marginTop: 2 }} />}
              <span>{errorCopy[lastError]}</span>
            </div>
          )}
        </div>

        <button
          type="submit"
          data-testid="login-submit"
          disabled={submitting}
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'space-between',
            background: 'var(--sig-info)',
            color: 'var(--surface-0)',
            border: 'none',
            borderRadius: 'var(--radius-1)',
            padding: '10px 14px',
            fontFamily: 'inherit',
            fontSize: 'var(--font-body-sm)',
            cursor: submitting ? 'progress' : 'pointer',
            opacity: submitting ? 0.7 : 1,
            transition: 'filter var(--dur-fast) var(--ease-standard)',
          }}
        >
          {submitting ? 'Signing in…' : 'Sign in'} <span aria-hidden="true">→</span>
        </button>

        <div
          style={{
            fontSize: 'var(--font-caption)',
            color: 'var(--content-lo)',
            lineHeight: 1.5,
          }}
        >
          If you don't have an account, contact your admin.
        </div>

        <div
          data-testid="login-fixture-hint"
          className="mono-num"
          style={{
            fontSize: 10,
            color: 'var(--content-lo)',
            borderTop: '1px solid var(--stroke-1)',
            paddingTop: 'var(--space-2)',
            lineHeight: 1.5,
          }}
        >
          prototype fixture · operator@coinnike.com · prototype123
        </div>
      </motion.form>
    </div>
  );
};

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const fieldInput: React.CSSProperties = {
  background: 'var(--surface-2)',
  color: 'var(--content-hi)',
  border: '1px solid var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '10px 12px',
  fontFamily: 'inherit',
  fontSize: 'var(--font-body)',
  outline: 'none',
};
