/**
 * COMMAND · Phase U.5.a — Density preference hook
 * ----------------------------------------------------------------------------
 * Mirrors the usePosture pattern. Operator preference only; never set by
 * code based on viewport. Two values:
 *
 *   'comfortable' (default)  — current spacing, long-session breathing room
 *   'compact'                — ~30% tighter vertical rhythm
 *
 * Persistence:  localStorage['cmd-ui-density']
 * Body attr:    [data-cmd-density="comfortable" | "compact"]
 * Console:      window.__cmd.density()                 → returns current
 *               window.__cmd.density('compact')        → sets + persists
 *               window.__cmd.density('comfortable')    → sets + persists
 *               window.__cmd.density(null)             → clears (= default)
 *
 * Briefing posture is handled in CSS, not here — see density.css.
 */
import { useEffect, useState, useCallback } from 'react';

const KEY = 'cmd-ui-density';
const VALID = ['comfortable', 'compact'];

function readPref() {
  try {
    const v = localStorage.getItem(KEY);
    if (VALID.includes(v)) return v;
  } catch (_) { /* noop */ }
  return 'comfortable';
}

function applyToDocument(value) {
  if (typeof document === 'undefined') return;
  document.body.setAttribute('data-cmd-density', value);
}

export function useDensity() {
  const [density, setDensityState] = useState(() => readPref());

  // Apply to body whenever it changes
  useEffect(() => { applyToDocument(density); }, [density]);

  const setDensity = useCallback((next) => {
    if (next === null || next === undefined) {
      try { localStorage.removeItem(KEY); } catch (_) {}
      setDensityState('comfortable');
      return 'comfortable';
    }
    if (!VALID.includes(next)) {
      // eslint-disable-next-line no-console
      console.warn('[command] density must be comfortable|compact|null');
      return null;
    }
    try { localStorage.setItem(KEY, next); } catch (_) {}
    setDensityState(next);
    return next;
  }, []);

  const toggle = useCallback(() => {
    setDensity(readPref() === 'compact' ? 'comfortable' : 'compact');
  }, [setDensity]);

  // Expose console hook (idempotent — installCommandToggle already sets __cmd)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.__cmd = window.__cmd || {};
    window.__cmd.density = (next) => {
      if (next === undefined) return readPref();
      return setDensity(next);
    };
  }, [setDensity]);

  return { density, setDensity, toggle };
}
