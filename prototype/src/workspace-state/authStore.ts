/*
 * Auth store — Bible §1.4.4, E2 §2 & §4.
 * Four stances: anonymous · authenticating · authenticated · expired.
 * Fixture-only: real auth arrives in Sprint 1 production build.
 *
 * Prototype fixture credentials (E2 §16 acceptance):
 *   operator@coinnike.com / prototype123
 *   Any other credential returns E2 §3.3 "Email or password is incorrect."
 *
 * A `?scenario=locked` or `?scenario=backend-down` query allows the
 * walkthrough to exercise the E2 validation-state taxonomy without leaving
 * the login screen.
 */
import { create } from 'zustand';

export type AuthStance = 'anonymous' | 'authenticating' | 'authenticated' | 'expired';

export interface Session {
  email: string;
  displayName: string;
  role: 'admin' | 'operator';
  signedInAt: string;   // ISO
  expiresAt: string;    // ISO (8h TTL, sliding)
  sessionId: string;    // for Advanced Lens footnote
  mustChangePassword: boolean;
}

export type LoginErrorKind =
  | 'field-empty-email'
  | 'field-empty-password'
  | 'email-invalid'
  | 'credentials-wrong'
  | 'account-locked'
  | 'session-expired-notice'
  | 'backend-down'
  | null;

interface AuthState {
  stance: AuthStance;
  session: Session | null;
  lastError: LoginErrorKind;
  nextUrl: string | null;

  attemptLogin: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  expireSession: () => void;
  captureNext: (url: string) => void;
  setError: (e: LoginErrorKind) => void;
}

const eightHoursMs = 8 * 60 * 60 * 1000;

const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

// Fixture-only credential vault — replaced by real backend in Sprint 1.
const FIXTURE_EMAIL = 'operator@coinnike.com';
const FIXTURE_PASSWORD = 'prototype123';
const LOCKED_EMAIL = 'locked@coinnike.com';

export const useAuthStore = create<AuthState>((set, get) => ({
  stance: 'anonymous',
  session: null,
  lastError: null,
  nextUrl: null,

  attemptLogin: async (email, password) => {
    set({ stance: 'authenticating', lastError: null });
    // Simulate the 300ms latency budget (E2 §6.3 / §3.2). No timers past this.
    await new Promise((r) => setTimeout(r, 260));

    if (!email) { set({ stance: 'anonymous', lastError: 'field-empty-email' }); return; }
    if (!password) { set({ stance: 'anonymous', lastError: 'field-empty-password' }); return; }
    if (!isEmail(email)) { set({ stance: 'anonymous', lastError: 'email-invalid' }); return; }
    if (email.toLowerCase() === LOCKED_EMAIL) { set({ stance: 'anonymous', lastError: 'account-locked' }); return; }

    if (email.toLowerCase() !== FIXTURE_EMAIL || password !== FIXTURE_PASSWORD) {
      set({ stance: 'anonymous', lastError: 'credentials-wrong' });
      return;
    }

    const now = new Date();
    const expires = new Date(now.getTime() + eightHoursMs);
    set({
      stance: 'authenticated',
      lastError: null,
      session: {
        email,
        displayName: 'Operator',
        role: 'admin',
        signedInAt: now.toISOString(),
        expiresAt: expires.toISOString(),
        sessionId: `sess_${Math.random().toString(36).slice(2, 10)}`,
        mustChangePassword: false,
      },
    });
  },

  signOut: () => set({ stance: 'anonymous', session: null, lastError: null, nextUrl: null }),

  expireSession: () => {
    const { session } = get();
    if (!session) return;
    set({ stance: 'expired', lastError: 'session-expired-notice' });
  },

  captureNext: (nextUrl) => set({ nextUrl }),
  setError: (lastError) => set({ lastError }),
}));
