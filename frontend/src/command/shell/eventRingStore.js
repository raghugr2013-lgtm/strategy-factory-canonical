/**
 * COMMAND · Phase U.5.c — Event Ring Store (posture-aware live-stream)
 * ============================================================================
 * PURE INFRASTRUCTURE — no DOM, no animation. The cognition-safety layer
 * that sits BETWEEN the call-log poll endpoint and any future visible
 * river (U.5.d). Owns:
 *
 *   1. A module-level singleton (no React state at this layer) so multiple
 *      subscribers share ONE polling cycle and ONE dedup set.
 *   2. Two-stage flow:
 *        fetch → dedup → pending queue → drip-reveal → visible ring (50 FIFO)
 *      Even a burst of 10 new calls is revealed one row at a time at the
 *      posture-tuned drip rate, so the operator's cognition is never spammed.
 *   3. Posture-aware cadence:
 *        workstation : poll 3000ms · drip 600ms
 *        tablet      : poll 6000ms · drip 1500ms
 *        briefing    : DISABLED — companion mode is monitoring, not telemetry
 *   4. Operator gating: `window.__cmd.river(true|false|null)`. Persisted
 *      in localStorage['cmd-ui-river']. Default = OFF. The store does
 *      nothing when disabled — no fetches, no timers.
 *
 * DOCTRINE
 *  - Never reveal >1 row per drip tick.
 *  - Never animate at this layer (U.5.d owns reveal animations).
 *  - Never auto-scroll, never bounce, never re-order.
 *  - Briefing posture means the operator is on a phone — telemetry stream
 *    is intentionally absent; companion mode receives Mission Briefing only.
 *  - Subscribers receive immutable snapshots; never mutate the ring.
 *
 * SHAPE OF SNAPSHOT
 *   {
 *     enabled:        boolean,    // operator preference
 *     available:      boolean,    // enabled && posture !== 'briefing'
 *     posture:        'workstation' | 'tablet' | 'briefing',
 *     ring:           Array<row>, // newest first, max 50
 *     pendingCount:   number,     // received but not yet revealed
 *     lastTickAt:     ISO string | null,
 *     lastError:      string | null,
 *   }
 *
 * NO BACKEND CHANGES. Source: `/api/llm/call-log/recent?limit=10` (already
 * polled by useBriefingData — we coexist independently; both can run.)
 */

const STORAGE_KEY = 'cmd-ui-river';
const RING_MAX = 50;

const POLL_MS = {
  workstation: 3000,
  tablet:      6000,
  briefing:    0,
};
const DRIP_MS = {
  workstation: 600,
  tablet:      1500,
  briefing:    0,
};

function readPref() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'on';
  } catch (_) { return false; }
}
function writePref(v) {
  try {
    if (v === null || v === undefined) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, v ? 'on' : 'off');
  } catch (_) { /* noop */ }
}
function rowKey(row) {
  // ts is the most stable; provider+task disambiguate identical timestamps
  return `${row?.ts || ''}|${row?.task || ''}|${row?.provider || ''}`;
}
function nowIso() { return new Date().toISOString(); }

class EventRingStore {
  constructor() {
    this.subscribers = new Set();
    this.pending = [];
    this.seen = new Set();
    this.pollTimer = null;
    this.dripTimer = null;
    this.postureObserver = null;

    // Public snapshot — replaced (never mutated) when subscribers are notified
    this.snapshot = {
      enabled: readPref(),
      available: false,
      posture: 'workstation',
      ring: [],
      pendingCount: 0,
      lastTickAt: null,
      lastError: null,
    };

    // Observe document.body[data-cmd-posture] directly so the store stays
    // posture-correct even when no React component is consuming the hook
    // (relevant during debug via __cmd.river() before U.5.d ships UI).
    this._wireBodyPostureObserver();

    // If enabled was persisted as on, reconcile immediately (best-effort —
    // posture will be refined by the observer / first useEventRing() consumer).
    this._reconcile();
  }

  _wireBodyPostureObserver() {
    if (typeof document === 'undefined') return;
    const apply = () => {
      try {
        const cur = document.body && document.body.getAttribute('data-cmd-posture');
        if (cur === 'workstation' || cur === 'tablet' || cur === 'briefing') {
          this.setPosture(cur);
        }
      } catch (_) { /* noop */ }
    };
    const install = () => {
      if (!document.body) return;
      apply();
      if (typeof MutationObserver !== 'undefined') {
        try {
          this.postureObserver = new MutationObserver(apply);
          this.postureObserver.observe(document.body, {
            attributes: true,
            attributeFilter: ['data-cmd-posture'],
          });
        } catch (_) { /* noop */ }
      }
    };
    if (document.body) install();
    else if (typeof window !== 'undefined') {
      window.addEventListener('DOMContentLoaded', install, { once: true });
    }
  }

  // ── public API ─────────────────────────────────────────────────────────
  subscribe(fn) {
    this.subscribers.add(fn);
    // Immediate snapshot so the subscriber doesn't render against undefined
    try { fn(this.snapshot); } catch (_) { /* noop */ }
    return () => { this.subscribers.delete(fn); };
  }

  setPosture(posture) {
    if (posture !== 'workstation' && posture !== 'tablet' && posture !== 'briefing') return;
    if (this.snapshot.posture === posture) return;
    this.snapshot = { ...this.snapshot, posture };
    this._reconcile();
  }

  setEnabled(next) {
    if (next === null || next === undefined) {
      writePref(null);
      this.snapshot = { ...this.snapshot, enabled: false };
    } else {
      writePref(!!next);
      this.snapshot = { ...this.snapshot, enabled: !!next };
    }
    this._reconcile();
  }

  clear() {
    this.pending = [];
    this.seen.clear();
    this.snapshot = { ...this.snapshot, ring: [], pendingCount: 0 };
    this._emit();
  }

  getSnapshot() { return this.snapshot; }

  // ── internals ──────────────────────────────────────────────────────────
  _emit() {
    const snap = this.snapshot;
    for (const fn of this.subscribers) {
      try { fn(snap); } catch (_) { /* noop — subscriber bugs don't poison others */ }
    }
  }

  _stopTimers() {
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
    if (this.dripTimer) { clearInterval(this.dripTimer); this.dripTimer = null; }
  }

  _reconcile() {
    const { enabled, posture } = this.snapshot;
    const available = !!enabled && posture !== 'briefing';
    if (this.snapshot.available !== available) {
      this.snapshot = { ...this.snapshot, available };
    }
    this._stopTimers();
    if (!available) {
      this._emit();
      return;
    }
    const pollMs = POLL_MS[posture] || POLL_MS.workstation;
    const dripMs = DRIP_MS[posture] || DRIP_MS.workstation;
    // Kick a tick immediately so the first call doesn't wait `pollMs`.
    this._tick();
    this.pollTimer = setInterval(() => this._tick(), pollMs);
    this.dripTimer = setInterval(() => this._drip(), dripMs);
    this._emit();
  }

  async _tick() {
    const BACKEND = (typeof process !== 'undefined' && process.env && process.env.REACT_APP_BACKEND_URL) || '';
    let token = null;
    try { token = localStorage.getItem('asf_auth_token'); } catch (_) { /* noop */ }
    try {
      const r = await fetch(`${BACKEND}/api/llm/call-log/recent?limit=10`, {
        credentials: 'omit',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) {
        this.snapshot = { ...this.snapshot, lastError: `HTTP ${r.status}`, lastTickAt: nowIso() };
        this._emit();
        return;
      }
      const j = await r.json();
      const rows = Array.isArray(j?.rows) ? j.rows : Array.isArray(j) ? j : [];
      // Build a list of NEW rows in the order they arrived (newest-first
      // from the endpoint — we preserve that ordering into pending).
      const fresh = [];
      for (const row of rows) {
        const k = rowKey(row);
        if (this.seen.has(k)) continue;
        this.seen.add(k);
        fresh.push(row);
      }
      // Cap `seen` memory at 4x ring (so it can dedup across the entire
      // expected horizon without growing unbounded).
      if (this.seen.size > RING_MAX * 4) {
        // Rebuild seen from current ring + remaining pending (the only
        // things we'd ever need to dedup against going forward).
        const keep = new Set();
        for (const r of this.snapshot.ring) keep.add(rowKey(r));
        for (const r of this.pending) keep.add(rowKey(r));
        this.seen = keep;
      }
      let changed = false;
      if (fresh.length > 0) {
        // Sort fresh rows by ts descending so pending is ALWAYS newest-first
        // regardless of the endpoint's returned order. Drip then pops from
        // the back (oldest unrevealed first), which prepends them to the
        // ring in chronological order — newest ends up at the visual top.
        fresh.sort((a, b) => {
          const ta = a?.ts || '';
          const tb = b?.ts || '';
          if (ta === tb) return 0;
          return ta < tb ? 1 : -1;  // descending
        });
        this.pending = [...fresh, ...this.pending];
        changed = true;
      }
      this.snapshot = {
        ...this.snapshot,
        pendingCount: this.pending.length,
        lastTickAt: nowIso(),
        lastError: null,
      };
      if (changed) this._emit();
      else this._emit();   // emit even on no-change so subscribers get tick time
    } catch (e) {
      this.snapshot = { ...this.snapshot, lastError: e?.message || 'network', lastTickAt: nowIso() };
      this._emit();
    }
  }

  _drip() {
    if (this.pending.length === 0) return;
    // Pull from the BACK of pending (oldest unrevealed first). Each newly
    // revealed row is prepended to the ring — so when a burst is processed,
    // the *chronologically newest* row ends up at the visual top, preserving
    // operator expectations (newest = top of the tape).
    const row = this.pending.pop();
    const ring = [row, ...this.snapshot.ring];
    if (ring.length > RING_MAX) ring.length = RING_MAX;
    this.snapshot = {
      ...this.snapshot,
      ring,
      pendingCount: this.pending.length,
    };
    this._emit();
  }
}

const eventRingStore = new EventRingStore();

// ── Console operator hook ─────────────────────────────────────────────────
// `__cmd.river()`         → returns small inspection snapshot
// `__cmd.river(true)`     → enable (persisted)
// `__cmd.river(false)`    → disable (persisted)
// `__cmd.river(null)`     → clear preference (= disabled, default)
// `__cmd.river.dump()`    → returns current visible ring (debug)
// `__cmd.river.clear()`   → purges ring + pending + dedup set
function installRiverHelper() {
  if (typeof window === 'undefined') return;
  // installCommandToggle() (Phase U.0) re-assigns `window.__cmd` to a fresh
  // object during app boot, which would wipe our helper if we installed
  // synchronously at import time. We attach the helper now AND again on a
  // microtask so we survive that re-assignment.
  window.__cmd = window.__cmd || {};
  const helper = (next) => {
    if (next === undefined) {
      const s = eventRingStore.getSnapshot();
      return {
        enabled: s.enabled,
        available: s.available,
        posture: s.posture,
        ring_size: s.ring.length,
        pending: s.pendingCount,
        last_tick_at: s.lastTickAt,
        last_error: s.lastError,
      };
    }
    eventRingStore.setEnabled(next);
    return eventRingStore.getSnapshot().enabled;
  };
  helper.dump  = () => eventRingStore.getSnapshot().ring;
  helper.clear = () => eventRingStore.clear();
  window.__cmd.river = helper;
}
installRiverHelper();
if (typeof queueMicrotask === 'function') {
  queueMicrotask(installRiverHelper);
} else if (typeof Promise !== 'undefined') {
  Promise.resolve().then(installRiverHelper);
}

export { eventRingStore, RING_MAX, POLL_MS, DRIP_MS };
