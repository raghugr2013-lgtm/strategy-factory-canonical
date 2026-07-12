/**
 * COMMAND · Phase U.6.a — Premium mode preference hook
 * ----------------------------------------------------------------------------
 * Mirrors useDensity. Operator preference only; never set by code based on
 * posture. Two values:
 *
 *   'on'  (default)  — full cinematic premium aesthetic (graphite layering,
 *                      reflection hairlines, hover lift, ambient pulse)
 *   'off'             — flat U.4-era panel rendering · identical layout ·
 *                      identical interactions · reduced visual depth for
 *                      long-session focus
 *
 * Persistence:  localStorage['cmd-ui-premium']
 * Body attr:    [data-cmd-premium="on" | "off"]
 * Console:      window.__cmd.premium()                 → returns current
 *               window.__cmd.premium('on'|'off'|null)  → sets + persists
 *
 * Doctrine:
 *   - Instant CSS-only switch · no animated transition between modes
 *   - Layout IDENTICAL in both states · only depth/gradient/reflection differ
 *   - Premium OFF must never feel "broken" or "downgraded" — it is a
 *     legitimate operator preference for deep-focus sessions
 */
import { useEffect, useState, useCallback } from 'react';

const KEY = 'cmd-ui-premium';
const VALID = ['on', 'off'];

function readPref() {
  try {
    const v = localStorage.getItem(KEY);
    if (VALID.includes(v)) return v;
  } catch (_) { /* noop */ }
  return 'on';
}

function applyToDocument(value) {
  if (typeof document === 'undefined') return;
  document.body.setAttribute('data-cmd-premium', value);
}

export function usePremium() {
  const [premium, setPremiumState] = useState(() => readPref());

  useEffect(() => { applyToDocument(premium); }, [premium]);

  const setPremium = useCallback((next) => {
    if (next === null || next === undefined) {
      try { localStorage.removeItem(KEY); } catch (_) {}
      setPremiumState('on');
      return 'on';
    }
    if (!VALID.includes(next)) {
      // eslint-disable-next-line no-console
      console.warn('[command] premium must be on|off|null');
      return null;
    }
    try { localStorage.setItem(KEY, next); } catch (_) {}
    setPremiumState(next);
    return next;
  }, []);

  const toggle = useCallback(() => {
    setPremium(readPref() === 'off' ? 'on' : 'off');
  }, [setPremium]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.__cmd = window.__cmd || {};
    window.__cmd.premium = (next) => {
      if (next === undefined) return readPref();
      return setPremium(next);
    };
  }, [setPremium]);

  return { premium, setPremium, toggle };
}
