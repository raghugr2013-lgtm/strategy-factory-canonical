/*
 * timelineShim — canonical §13 · Event vocabulary (frontend shim).
 * refs docs/ARCHITECTURE.md §13 · Event vocabulary
 *
 * Under Backend Feature Freeze v1.1.0-stage4 there is no
 * POST /api/timeline/events endpoint. This shim implements the §13.2
 * event shape and §13.1 naming convention entirely client-side:
 *   · session-lived append-only in-memory list (mirrored to sessionStorage)
 *   · zustand store so surfaces can subscribe to filtered streams
 *   · console breadcrumb for developer visibility
 *
 * Every emitted event conforms to §13.2 verbatim so the day the backend
 * exposes a real Timeline endpoint, the shim swap is a two-line change.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

const uuid = () => `evt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export const useTimelineShim = create(
  persist(
    (set, get) => ({
      events: [],

      emit: (partial) => {
        const evt = {
          event_id: uuid(),
          event_name: partial.event_name,
          actor: partial.actor || { email: null, role: null, session_id: null },
          object: partial.object || { type: 'unknown', id: null },
          context: partial.context || {},
          reason: partial.reason || null,
          ts: new Date().toISOString(),
          source: partial.source || 'operator-os',
          framework_version: 'v1.1.0-stage4',
        };
        // eslint-disable-next-line no-console
        console.info('[timeline·shim §13]', evt.event_name, evt);
        set({ events: [...get().events, evt] });
        return evt;
      },

      clear: () => set({ events: [] }),
    }),
    {
      name: 'sf-timeline-shim-v1',
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);

/**
 * useTimelineEvents — read-side subscription helper (§19.2). Filters by
 * object.id / event_name prefix / arbitrary predicate. Returns latest-first.
 */
export const useTimelineEvents = ({ objectId, eventPrefix, predicate } = {}) => {
  const events = useTimelineShim((s) => s.events);
  const filtered = events.filter((e) => {
    if (objectId && e.object?.id !== objectId) return false;
    if (eventPrefix && !String(e.event_name || '').startsWith(eventPrefix)) return false;
    if (predicate && !predicate(e)) return false;
    return true;
  });
  return [...filtered].reverse();
};
