/*
 * useStream — Sprint 2 N3 React hook wrapper around streamAdapter.subscribe.
 * refs SPRINT_2_PLANNING.md §2 N3
 *
 * Returns { mode, tickAt, tickCount, reason } so surfaces can render a
 * postmark ("streamed 12:34:07Z · WSS" vs "polled 12:34:07Z · poll").
 */
import { useEffect, useRef, useState } from 'react';
import { subscribe } from '../adapters/streamAdapter';

export const useStream = (channel, { intervalMs = 15_000, onTick } = {}) => {
  const [status, setStatus] = useState({ mode: 'boot', tickAt: null, tickCount: 0, reason: null });
  const onTickRef = useRef(onTick);
  onTickRef.current = onTick;

  useEffect(() => {
    const unsub = subscribe(channel, (payload) => {
      setStatus((prev) => ({
        mode: payload.mode === 'event' || payload.mode === 'open' ? 'wss' : payload.mode === 'initial' ? 'initial' : 'poll',
        tickAt: payload.ts,
        tickCount: prev.tickCount + 1,
        reason: payload.reason ?? null,
      }));
      if (onTickRef.current) onTickRef.current(payload);
    }, { intervalMs });
    return unsub;
  }, [channel, intervalMs]);

  return status;
};
