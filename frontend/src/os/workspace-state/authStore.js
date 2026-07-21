/*
 * authStore — fixture auth store for M1 Foundation.
 * refs DESIGN_FREEZE_v1.0.md §1.4 (Login) · E2 §9 Trust Before Credentials
 *
 * Sprint 1 M1 ships with an in-memory fixture store; M5 replaces this with
 * real backend auth against v1.1.0-stage4 via `services/api.js`.
 *
 * Fixture credentials (prototype-parity):
 *   operator@coinnike.com / prototype123
 *   locked@coinnike.com   (locked-account error path)
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export const AUTH_STANCES = ['anonymous', 'authenticating', 'authenticated', 'expired'];

const FIXTURE_EMAIL = 'operator@coinnike.com';
const FIXTURE_PASSWORD = 'prototype123';
const LOCKED_EMAIL = 'locked@coinnike.com';

const emailValid = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

export const useAuthStore = create(
  persist(
    (set) => ({
      stance: 'anonymous',
      email: null,
      error: null,

      login: async (email, password) => {
        set({ stance: 'authenticating', error: null });
        // Simulate latency (P0-parity)
        await new Promise((r) => setTimeout(r, 260));

        if (!email && !password) {
          set({ stance: 'anonymous', error: 'Enter email and password.' });
          return false;
        }
        if (!emailValid(email)) {
          set({ stance: 'anonymous', error: 'That email address is not valid.' });
          return false;
        }
        if (email === LOCKED_EMAIL) {
          set({
            stance: 'anonymous',
            error: 'This account is locked. Try again in 15 minutes.',
          });
          return false;
        }
        if (email !== FIXTURE_EMAIL || password !== FIXTURE_PASSWORD) {
          set({ stance: 'anonymous', error: 'Wrong email or password.' });
          return false;
        }
        set({ stance: 'authenticated', email, error: null });
        return true;
      },

      logout: () => set({ stance: 'anonymous', email: null, error: null }),

      expireSession: () =>
        set({
          stance: 'expired',
          error: 'Your session expired. Please sign in again.',
        }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'sf-auth-v1',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ stance: s.stance, email: s.email }),
    }
  )
);
