import React, { useEffect, useState } from 'react';
import { Lightning, SignIn, UserPlus, Spinner, CheckCircle, Warning } from '@phosphor-icons/react';
import {
  login as apiLogin, signup as apiSignup,
  getStoredUser, fetchMe, clearAuth, getToken,
} from '../services/auth';

/**
 * AuthGate — modal gate that blocks the app until the user is logged in
 * AND approved. Uses localStorage JWT. No router library — a single
 * overlay covers the app until `onAuthed(user)` is fired.
 */
export default function AuthGate({ onAuthed }) {
  const [mode, setMode] = useState('login');      // 'login' | 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pendingMessage, setPendingMessage] = useState(null);
  const [checking, setChecking] = useState(true);

  // If a token is stored, validate once on mount via /auth/me.
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!getToken()) { setChecking(false); return; }
      try {
        const me = await fetchMe();
        if (!cancelled) onAuthed(me.user);
      } catch {
        clearAuth();
        if (!cancelled) setChecking(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [onAuthed]);

  const submit = async (e) => {
    e.preventDefault();
    setError(null); setPendingMessage(null); setLoading(true);
    try {
      if (mode === 'signup') {
        await apiSignup(email, password);
        setPendingMessage('Account created — awaiting admin approval.');
        setMode('login');
        setPassword('');
      } else {
        const res = await apiLogin(email, password);
        onAuthed(res.user);
      }
    } catch (err) {
      setError(err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  if (checking) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-surface-main"
        data-testid="auth-gate-loading"
      >
        <Spinner size={24} className="animate-spin text-accent-primary" />
      </div>
    );
  }

  return (
    <div
      data-testid="auth-gate"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4"
    >
      <div className="w-full max-w-md rounded-lg border border-accent-primary/30 bg-surface-card shadow-xl">
        <div className="px-6 pt-6 pb-2 border-b border-border-subtle flex items-center gap-2">
          <span className="inline-flex w-8 h-8 rounded-md bg-gradient-to-br from-accent-primary to-accent-primary-dim items-center justify-center text-[#061812]">
            <Lightning size={18} weight="bold" />
          </span>
          <div>
            <h1 className="font-heading text-base font-bold text-white">AI Strategy Factory</h1>
            <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4" data-testid="auth-form">
          <label className="block">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400">Email</span>
            <input
              data-testid="auth-email-input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 w-full bg-[#0B0F14] border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-primary/60"
            />
          </label>
          <label className="block">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400">Password</span>
            <input
              data-testid="auth-password-input"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={mode === 'signup' ? 6 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 w-full bg-[#0B0F14] border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-primary/60"
            />
            {mode === 'signup' && (
              <span className="block mt-1 text-[10px] font-mono text-zinc-500">Min 6 characters.</span>
            )}
          </label>

          {error && (
            <div
              data-testid="auth-error"
              className="flex items-start gap-2 text-xs rounded border border-red-500/30 bg-red-500/10 text-red-300 px-3 py-2"
            >
              <Warning size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {pendingMessage && (
            <div
              data-testid="auth-pending-message"
              className="flex items-start gap-2 text-xs rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 px-3 py-2"
            >
              <CheckCircle size={14} className="mt-0.5 shrink-0" />
              <span>{pendingMessage}</span>
            </div>
          )}

          <button
            data-testid="auth-submit-btn"
            type="submit"
            disabled={loading || !email || !password}
            className="w-full text-sm font-semibold px-4 py-2.5 rounded border border-accent-primary/40 bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {loading
              ? <Spinner size={14} className="animate-spin" />
              : (mode === 'login' ? <SignIn size={14} weight="bold" /> : <UserPlus size={14} weight="bold" />)}
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>

          <div className="pt-2 text-center text-[11px] font-mono text-zinc-500">
            {mode === 'login' ? (
              <>
                New here?{' '}
                <button
                  type="button"
                  data-testid="auth-switch-signup"
                  onClick={() => { setMode('signup'); setError(null); setPendingMessage(null); }}
                  className="text-accent-primary hover:underline"
                >
                  Create account
                </button>
              </>
            ) : (
              <>
                Already have an account?{' '}
                <button
                  type="button"
                  data-testid="auth-switch-login"
                  onClick={() => { setMode('login'); setError(null); setPendingMessage(null); }}
                  className="text-accent-primary hover:underline"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

// Small re-export so App.js can read the persisted user before render.
export { getStoredUser };
