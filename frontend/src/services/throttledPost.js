/**
 * Phase G2 — client-side throttle for POST/PUT/DELETE write paths.
 *
 * Purpose
 * -------
 *   The COMMAND OS frontend exposes 55+ operator-clickable write
 *   endpoints with no native debounce. A determined operator (or a
 *   distracted hand) can fire the same POST repeatedly while the
 *   first call is still in flight, producing the kind of incident
 *   seen during R5.h.continue.C (12× `/api/download-data` in 30 min).
 *
 *   This module wraps the in-flight + minimum-interval guards into
 *   a single primitive that any panel can adopt without re-wiring
 *   the surrounding state.
 *
 * Semantics
 * ---------
 *   throttledPost(key, fn, { minIntervalMs = 1500 })
 *     * `key`            stable string identifying the logical action.
 *                        Two clicks with the same key throttle each
 *                        other; different keys do not.
 *     * `fn`             () => Promise<any>  — your actual fetch.
 *     * `minIntervalMs`  default 1500ms cooldown after the previous
 *                        successful or failed attempt completed.
 *
 *   Returns
 *     {
 *       ok:        boolean,         // false => throttled (no call)
 *       throttled: boolean,         // true  if rate-limited / in-flight
 *       reason:    'in-flight' | 'cooldown' | undefined,
 *       result:    <fn return value when ok=true>
 *     }
 *
 *   The wrapped fn is NEVER invoked twice concurrently for the same key.
 *
 * Usage (React)
 * -------------
 *   import { throttledPost } from '../services/throttledPost';
 *
 *   const onClick = async () => {
 *     const r = await throttledPost(
 *       `download-data:${symbol}:${timeframe}`,
 *       () => downloadMarketData(symbol, timeframe, from, to),
 *       { minIntervalMs: 3000 },
 *     );
 *     if (!r.ok) { toast(`Throttled (${r.reason}). Try again shortly.`); return; }
 *     setResult(r.result);
 *   };
 *
 * Notes
 * -----
 *   * Pure client-side. The server still owns the truth via the
 *     advisory_lock collection (Phase G2 backend) — this is an
 *     additional UX shield, not a substitute.
 *   * Module-level state is per-tab. Survives navigation within
 *     the SPA. Resets on a hard reload.
 */

const _inFlight = new Map();    // key -> Promise
const _lastEnded = new Map();   // key -> epoch ms when last attempt resolved

export async function throttledPost(key, fn, opts = {}) {
  const minIntervalMs = Number.isFinite(opts.minIntervalMs)
    ? opts.minIntervalMs
    : 1500;

  // 1) In-flight guard
  if (_inFlight.has(key)) {
    return { ok: false, throttled: true, reason: 'in-flight' };
  }

  // 2) Cooldown guard
  const now = Date.now();
  const lastEnd = _lastEnded.get(key);
  if (lastEnd !== undefined && now - lastEnd < minIntervalMs) {
    return { ok: false, throttled: true, reason: 'cooldown' };
  }

  // 3) Execute under lock
  const p = (async () => {
    try {
      const result = await fn();
      return { ok: true, throttled: false, result };
    } finally {
      _inFlight.delete(key);
      _lastEnded.set(key, Date.now());
    }
  })();
  _inFlight.set(key, p);
  return await p;
}

/**
 * Read-only inspection helper for tests / dev console.
 * Returns { inFlight: [...keys], lastEnded: { key: epochMs } }.
 */
export function _debugState() {
  return {
    inFlight: Array.from(_inFlight.keys()),
    lastEnded: Object.fromEntries(_lastEnded),
  };
}
