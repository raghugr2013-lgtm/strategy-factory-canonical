/**
 * Phase U-4.4 · localeStore  (i18n infrastructure — NOT full translation)
 * ----------------------------------------------------------------------------
 * Mirror of the U-1 themeStore architecture: a tiny pub/sub store backed by
 * `useSyncExternalStore` that persists the active locale to localStorage and
 * exposes a small public API for setting / cycling / subscribing.
 *
 * Goals (U-4.4 scope):
 *   • Provide the *infrastructure* for translation:
 *       — string-extraction surface (`t(key, fallback, params)` resolves
 *         against locale dictionaries lazy-loaded from
 *         `/app/frontend/src/i18n/locales/<locale>.json`).
 *       — language switching foundation (`setLocale`, `toggleLocale`,
 *         `cycleLocale`).
 *       — IntlProvider-style ergonomics without a hard dep on `react-intl`
 *         (so we don't bloat the bundle until full translation is on the
 *         roadmap).
 *
 *   • Do NOT extract every panel string in this phase. We ship en-US as the
 *     source of truth and seed a single secondary locale (de-DE) with a
 *     small pilot dictionary so the operator can validate the switching
 *     pipeline end-to-end.
 *
 * Defaults:
 *   • First load → en-US.
 *   • localStorage persistence under `asf.locale.v1`.
 *   • Falls back to en-US if the stored locale is unknown.
 *
 * Public API:
 *   • SUPPORTED_LOCALES      — array of registered locale codes.
 *   • getLocale()            — current locale (sync).
 *   • setLocale(code)        — set + persist + DOM bridge (`<html lang>`).
 *   • toggleLocale()         — en-US ⇄ de-DE.
 *   • cycleLocale()          — walks SUPPORTED_LOCALES in order.
 *   • subscribe(fn)          — store subscriber.
 *   • useLocaleStore()       — React hook (live read).
 *   • bootstrapLocaleStore() — idempotent boot.
 *   • t(key, fallback)       — translation accessor.
 *   • registerLocaleDict()   — register a dictionary (used by IntlProvider).
 */

import { useSyncExternalStore } from 'react';

export const SUPPORTED_LOCALES = ['en-US', 'de-DE'];
const STORAGE_KEY = 'asf.locale.v1';
const DEFAULT_LOCALE = 'en-US';

let state = { locale: DEFAULT_LOCALE };
const listeners = new Set();
const dicts = new Map(); // locale -> { key: string }

function emit() {
  listeners.forEach((l) => { try { l(); } catch (_) { /* unmounted */ } });
}

function applyToDom(locale) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('lang', locale.split('-')[0]);
  document.documentElement.setAttribute('data-locale', locale);
}

function readStored() {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return SUPPORTED_LOCALES.includes(v) ? v : null;
  } catch (_) { return null; }
}

function persist(locale) {
  if (typeof window === 'undefined') return;
  try { window.localStorage.setItem(STORAGE_KEY, locale); } catch (_) { /* noop */ }
}

export function getLocale() { return state.locale; }

export function setLocale(next) {
  const target = SUPPORTED_LOCALES.includes(next) ? next : DEFAULT_LOCALE;
  if (target === state.locale) return;
  state = { locale: target };
  applyToDom(target);
  persist(target);
  emit();
}

export function toggleLocale() {
  setLocale(state.locale === 'en-US' ? 'de-DE' : 'en-US');
}

export function cycleLocale() {
  const i = SUPPORTED_LOCALES.indexOf(state.locale);
  setLocale(SUPPORTED_LOCALES[(i + 1) % SUPPORTED_LOCALES.length]);
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function registerLocaleDict(locale, dict) {
  if (!SUPPORTED_LOCALES.includes(locale)) return;
  dicts.set(locale, { ...(dicts.get(locale) || {}), ...(dict || {}) });
  // Resolved values may have changed even though locale didn't — re-emit so
  // any subscribed component re-renders.
  emit();
}

/**
 * Translation accessor. Reads from the currently active locale's dictionary
 * with a per-key fallback to en-US, then to the provided literal fallback.
 *
 * Param interpolation: `t('greeting', 'Hello {name}', { name: 'Op' })`.
 */
export function t(key, fallback, params) {
  const active = dicts.get(state.locale) || {};
  const en = dicts.get('en-US') || {};
  let str = active[key] != null ? active[key] : (en[key] != null ? en[key] : (fallback != null ? fallback : key));
  if (params && typeof str === 'string') {
    Object.keys(params).forEach((k) => {
      str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), String(params[k]));
    });
  }
  return str;
}

let booted = false;
export function bootstrapLocaleStore() {
  if (booted) return;
  booted = true;
  const stored = readStored();
  const initial = stored || DEFAULT_LOCALE;
  state = { locale: initial };
  applyToDom(initial);
}

export function useLocaleStore() {
  return useSyncExternalStore(
    subscribe,
    () => state.locale,
    () => DEFAULT_LOCALE,
  );
}
