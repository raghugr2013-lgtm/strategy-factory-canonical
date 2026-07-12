/* ─────────────────────────────────────────────────────────────────────────────
 * themeStore — Single source of truth for the application theme.
 * -----------------------------------------------------------------------------
 * Operator directive (2026-02):
 *   • Implement only the INTERNAL source-of-truth layer.
 *   • Dark mode is the DEFAULT and the only theme currently allowed.
 *   • Light theme remains DISABLED — `setTheme('light')` is a no-op until
 *     activation is authorised (flip the `LIGHT_THEME_ENABLED` flag below).
 *   • NO visible toggle, NO toolbar button, NO visual changes.
 *
 * Architectural goals:
 *   • Module-level singleton — no Provider needed, can be imported anywhere
 *     (React components OR plain modules — e.g. test utilities).
 *   • `useSyncExternalStore` for tear-free React reads.
 *   • Writes `<html data-theme="…">` AND toggles `<html class="dark">`
 *     (shadcn relies on the .dark class; the ASF token blocks key off
 *     `[data-theme]`). Keeping both in lock-step here means callers only
 *     ever talk to this store.
 *   • Persists to localStorage under `asf.theme.v2` (new key — does NOT
 *     touch the legacy `asf.theme` key used by hooks/useTheme.js, which
 *     remains as a separate unmounted artefact and is not wired in App.js).
 *   • SSR-safe: every browser-only access is guarded by `typeof window`.
 *
 * NOTE on the legacy useTheme.js:
 *   The codebase already contains a ThemeProvider/useTheme hook
 *   (frontend/src/hooks/useTheme.js) that was never mounted in App.js.
 *   That hook activates `light` from `prefers-color-scheme`, which would
 *   violate the current operator lock. It is intentionally NOT wired —
 *   this themeStore is the SSOT going forward. The legacy file is
 *   retained for parity but is dormant.
 * ───────────────────────────────────────────────────────────────────────── */

const STORAGE_KEY = 'asf.theme.v2';

/* Set to `true` ONLY when the operator authorises light-theme activation.
 * No code outside this file should read this constant.
 *
 * M0 2026-06-11 — operator-locked DARK-ONLY. Light theme is permanently
 * disabled at the design-system level. Calls to setTheme('light') silently
 * coerce to 'dark'. ThemeToggle is excised from the topbar. See
 * /app/memory/visual_approval_package/11_THEMETOGGLE_REMOVAL.md. */
const LIGHT_THEME_ENABLED = false;

const ALLOWED_THEMES = ['dark', 'light'];

/* ── State ──────────────────────────────────────────────────────────────── */

let state = { theme: 'dark' };
const listeners = new Set();

function emit() {
  listeners.forEach((listener) => {
    try { listener(); } catch (_e) { /* listener may have unmounted */ }
  });
}

/* ── DOM bridge ─────────────────────────────────────────────────────────── */

function applyToDom(theme) {
  if (typeof document === 'undefined') return;
  const html = document.documentElement;
  html.setAttribute('data-theme', theme);
  html.classList.toggle('dark', theme === 'dark');
  // U-4.3 — mirror the attribute onto <body> so legacy selectors that target
  // `body[data-theme]` (and any future tooltip / portal containers attached
  // to body) resolve to the correct theme.
  if (document.body) {
    document.body.setAttribute('data-theme', theme);
  }
}

/* ── localStorage bridge ───────────────────────────────────────────────── */

function readStoredTheme() {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (ALLOWED_THEMES.includes(v)) return v;
  } catch (_e) { /* storage disabled (e.g. private mode) */ }
  return null;
}

function persistTheme(theme) {
  if (typeof window === 'undefined') return;
  try { window.localStorage.setItem(STORAGE_KEY, theme); }
  catch (_e) { /* storage disabled */ }
}

/* ── Public API ────────────────────────────────────────────────────────── */

/**
 * Returns the current theme. Always one of: 'dark' (today) | 'light' (once
 * activation is authorised).
 *
 * Stable reference is NOT guaranteed — read via `useThemeStore()` in React
 * to get the live value; this raw getter is for non-React callers.
 */
export function getTheme() {
  return state.theme;
}

/**
 * Set the active theme. While `LIGHT_THEME_ENABLED === false`, any value
 * other than 'dark' is silently coerced to 'dark' — this preserves the
 * operator lock without breaking call-sites that may already use the API.
 */
export function setTheme(next) {
  let target = ALLOWED_THEMES.includes(next) ? next : 'dark';
  if (target === 'light' && !LIGHT_THEME_ENABLED) target = 'dark';
  if (target === state.theme) return;
  state = { theme: target };
  applyToDom(target);
  persistTheme(target);
  emit();
}

/**
 * Subscribe to theme changes. Returns an unsubscribe function.
 * Required by `useSyncExternalStore`.
 */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * U-4.3 — Toggle dark ⇄ light. Operator-elective; only takes effect when
 * `LIGHT_THEME_ENABLED === true`. Used by the Command Palette command
 * `cmd:theme-toggle` and any future Posture menu button.
 */
export function toggleTheme() {
  setTheme(state.theme === 'dark' ? 'light' : 'dark');
}

/**
 * `true` once the operator authorises light-theme activation. Exposed
 * read-only so future toolbar code can render its toggle conditionally.
 */
export function isLightThemeEnabled() {
  return LIGHT_THEME_ENABLED;
}

/* ── Bootstrap ─────────────────────────────────────────────────────────── */

/**
 * Initialise the store and write `<html>` attributes ONCE during app boot.
 * Idempotent — safe to call multiple times (no-op after the first).
 *
 * Resolution order:
 *   1. localStorage 'asf.theme.v2' if it stores an allowed value
 *      → falls back to 'dark' if the value is 'light' but light is locked.
 *   2. Default 'dark'.
 *
 * `prefers-color-scheme` is intentionally NOT consulted — the operator's
 * lock requires deterministic dark default regardless of OS preference.
 */
let booted = false;
export function bootstrapThemeStore() {
  if (booted) return;
  booted = true;
  const stored = readStoredTheme();
  let initial = 'dark';
  if (stored === 'light' && LIGHT_THEME_ENABLED) initial = 'light';
  state = { theme: initial };
  applyToDom(initial);
  // Don't `persistTheme` here — we don't want bootstrap to write to storage
  // unless `setTheme` was called explicitly.
}

/* ── React hook (lazy import to keep this module React-agnostic) ──────── */

import { useSyncExternalStore } from 'react';

/**
 * Live-read the current theme inside React components. Subscribes
 * automatically and tears down on unmount.
 *
 *   const theme = useThemeStore();
 */
export function useThemeStore() {
  return useSyncExternalStore(
    subscribe,
    () => state.theme,
    () => 'dark',          // SSR snapshot
  );
}
