/*
 * Stream adapter — Sprint 2 N3.
 * refs SPRINT_2_PLANNING.md §2 N3 · Design Freeze §1.3 (live surfaces)
 *
 * Purpose:
 *   Provide a unified "streaming subscription" API to the Timeline,
 *   Approvals, and StatusRail surfaces.
 *
 * Modes (transparent to callers):
 *   1. WSS  → REACT_APP_WSS_URL is set AND the socket opens successfully.
 *             Server pushes {channel, event, ts} frames; onTick() is invoked.
 *   2. Poll → fallback whenever the socket cannot open (freeze / no env / dev).
 *             onTick() is invoked at `intervalMs` (default 15 000 ms).
 *
 * The two paths are behaviourally equivalent to consumers: both call onTick.
 *
 * Under the current Backend Feature Freeze (v1.1.0-stage4) there is no
 * WSS surface, so this adapter runs in poll mode until the freeze lifts.
 * Callers should not need to change.
 */

const WSS_URL = (typeof process !== 'undefined' && process.env.REACT_APP_WSS_URL) || '';

export const isStreamLive = () => Boolean(WSS_URL);

/**
 * Subscribe to a stream channel.
 * @param {string} channel                    — logical channel name (e.g. 'timeline')
 * @param {(payload: object) => void} onTick  — invoked on every event / poll tick
 * @param {{ intervalMs?: number, initial?: boolean }} [opts]
 * @returns {() => void}                      — unsubscribe function
 */
export const subscribe = (channel, onTick, opts = {}) => {
  const intervalMs = opts.intervalMs ?? 15_000;
  let disposed = false;
  let ws = null;
  let pollTimer = null;

  const emit = (mode, extra = {}) => {
    if (disposed) return;
    onTick({ channel, mode, ts: Date.now(), ...extra });
  };

  const startPoll = (reason) => {
    if (disposed || pollTimer) return;
    emit('poll', { reason });
    pollTimer = setInterval(() => emit('poll', { reason: 'tick' }), intervalMs);
  };

  if (opts.initial !== false) emit('initial');

  if (WSS_URL && typeof WebSocket !== 'undefined') {
    try {
      ws = new WebSocket(`${WSS_URL}/api/stream/${channel}`);
      ws.addEventListener('open', () => emit('open'));
      ws.addEventListener('message', (ev) => {
        try {
          const data = JSON.parse(ev.data);
          emit('event', { event: data });
        } catch {
          emit('event', { raw: String(ev.data).slice(0, 200) });
        }
      });
      ws.addEventListener('close', () => startPoll('ws-close'));
      ws.addEventListener('error', () => {
        try { ws.close(); } catch { /* noop */ }
        startPoll('ws-error');
      });
    } catch (e) {
      startPoll('ws-throw');
    }
  } else {
    startPoll(WSS_URL ? 'no-websocket-runtime' : 'freeze-no-wss-url');
  }

  return () => {
    disposed = true;
    if (pollTimer) clearInterval(pollTimer);
    if (ws) { try { ws.close(); } catch { /* noop */ } }
  };
};
