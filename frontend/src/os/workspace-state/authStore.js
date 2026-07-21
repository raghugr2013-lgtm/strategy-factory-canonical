/*
 * authStore — M5 real-auth wiring with fixture fallback.
 * refs DESIGN_FREEZE_v1.0.md §1.4 (Login) · E2 §9 Trust Before Credentials
 * refs Kickoff Plan §4 · M5 real-auth
 *
 * Real path: POST /api/auth/login → JWT → stored in sessionStorage as
 * `sf-auth-token` (consumed by apiClient). On network failure or 4xx, falls
 * back to fixture credentials (`operator@coinnike.com` / `prototype123`) so
 * the dev workspace continues to function without a running backend.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { isLiveMode, apiFetch } from '../adapters/apiClient';

export const AUTH_STANCES = ['anonymous', 'authenticating', 'authenticated', 'expired'];

const FIXTURE_EMAIL = 'operator@coinnike.com';
const FIXTURE_PASSWORD = 'prototype123';
const LOCKED_EMAIL = 'locked@coinnike.com';
const TOKEN_KEY = 'sf-auth-token';

const emailValid = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

const storeToken = (t) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch {} };
const clearToken = ()   => { try { sessionStorage.removeItem(TOKEN_KEY); } catch {} };

const attemptLiveLogin = async (email, password) => {
  if (!isLiveMode()) throw new Error('fixture-mode');
  const data = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  const token = data?.access_token || data?.token || data?.jwt;
  if (!token) throw new Error('no-token');
  return { token, email: data?.email || email };
};

const attemptFixtureLogin = (email, password) => {
  if (!email && !password) return { error: 'Enter email and password.' };
  if (!emailValid(email)) return { error: 'That email address is not valid.' };
  if (email === LOCKED_EMAIL) return { error: 'This account is locked. Try again in 15 minutes.' };
  if (email !== FIXTURE_EMAIL || password !== FIXTURE_PASSWORD) return { error: 'Wrong email or password.' };
  return { ok: true, email };
};

export const useAuthStore = create(
  persist(
    (set) => ({
      stance: 'anonymous',
      email: null,
      error: null,
      authMode: 'fixture', // 'fixture' or 'live'

      login: async (email, password) => {
        set({ stance: 'authenticating', error: null });
        await new Promise((r) => setTimeout(r, 200));

        // 1) Try live auth if backend is configured.
        if (isLiveMode()) {
          try {
            const { token, email: e } = await attemptLiveLogin(email, password);
            storeToken(token);
            set({ stance: 'authenticated', email: e, error: null, authMode: 'live' });
            return true;
          } catch (err) {
            // 401/403 → real credential error; other errors → fixture fallback
            if (err.status === 401 || err.status === 403) {
              set({ stance: 'anonymous', error: 'Wrong email or password.', authMode: 'live' });
              return false;
            }
            console.warn('[auth] live login unreachable, falling back to fixture:', err.message);
          }
        }

        // 2) Fixture path.
        const fix = attemptFixtureLogin(email, password);
        if (fix.error) {
          set({ stance: 'anonymous', error: fix.error, authMode: 'fixture' });
          return false;
        }
        clearToken();
        set({ stance: 'authenticated', email: fix.email, error: null, authMode: 'fixture' });
        return true;
      },

      logout: () => { clearToken(); set({ stance: 'anonymous', email: null, error: null }); },

      expireSession: () => {
        clearToken();
        set({ stance: 'expired', error: 'Your session expired. Please sign in again.' });
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'sf-auth-v1',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ stance: s.stance, email: s.email, authMode: s.authMode }),
    }
  )
);
