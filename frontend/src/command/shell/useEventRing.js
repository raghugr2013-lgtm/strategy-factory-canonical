/**
 * COMMAND · Phase U.5.c — useEventRing hook
 * ----------------------------------------------------------------------------
 * Thin React adapter over the module-level singleton `eventRingStore`. The
 * hook:
 *   1. pushes the current usePosture() value into the store so cadence
 *      reconciles correctly,
 *   2. subscribes to snapshot updates,
 *   3. returns the immutable snapshot.
 *
 * The store does the heavy lifting — multiple components consuming this
 * hook share ONE polling cycle and ONE dedup set, so there is zero cost
 * for additional subscribers (U.5.d will be the first visible consumer).
 *
 * U.5.c ships with NO visible UI. Verification is via `window.__cmd.river`.
 */
import { useEffect, useState } from 'react';
import { eventRingStore } from './eventRingStore';
import { usePosture } from './usePosture';

export function useEventRing() {
  const posture = usePosture();
  const [snapshot, setSnapshot] = useState(() => eventRingStore.getSnapshot());

  // Push posture into the store so polling/drip cadence is correct.
  useEffect(() => {
    eventRingStore.setPosture(posture);
  }, [posture]);

  // Subscribe to snapshot updates.
  useEffect(() => {
    const unsub = eventRingStore.subscribe(setSnapshot);
    return unsub;
  }, []);

  return snapshot;
}
