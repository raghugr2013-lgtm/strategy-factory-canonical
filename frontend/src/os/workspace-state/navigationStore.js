/*
 * navigationStore — cross-surface facet plane + State Memory + return-crumb.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · Bible §7.4a · E5 §4.5 · D8 §3.2
 *
 * Encodes the three cross-module invariants:
 *   1. Rule of Predictable Return (E5 §4.5) — surface state restored on return.
 *   2. Shared Facet Plane (Bible §7.4a) — actor · status · risk axes cascade
 *      across Timeline · Approvals · Explorer; each surface owns one axis.
 *   3. Decision Identity (D6 §8.1a) — selected strategy id is the shared truth
 *      and cross-nav intent is recorded via a return-crumb.
 *
 * State Memory is session-scoped: uses sessionStorage so tab-local state
 * survives within-tab navigation but does not enter the URL.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

const DEFAULT_FACETS = { actor: 'all', status: 'all', risk: 'all' };

export const useNavigationStore = create(
  persist(
    (set, get) => ({
      facets: { ...DEFAULT_FACETS },
      memory: {},
      crumb: null,

      setFacet: (axis, value) =>
        set((s) => ({ facets: { ...s.facets, [axis]: value } })),
      resetFacets: () => set({ facets: { ...DEFAULT_FACETS } }),

      saveSurface: (pathname, slice) =>
        set((s) => ({
          memory: {
            ...s.memory,
            [pathname]: { ...(s.memory[pathname] || {}), ...slice },
          },
        })),
      readSurface: (pathname) => get().memory[pathname],
      clearSurface: (pathname) =>
        set((s) => {
          const next = { ...s.memory };
          delete next[pathname];
          return { memory: next };
        }),

      setCrumb: (crumb) => set({ crumb }),
      consumeCrumb: () => {
        const c = get().crumb;
        if (c) set({ crumb: null });
        return c;
      },
    }),
    {
      name: 'sf-navigation-v1',
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
