/*
 * Workspace state store — Context Never Lost foundation.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · Bible §1.4.4 · D8 §3.1
 *
 * Holds mode · advanced_lens · density · selected_strategy · kill_posture.
 * Persistent slices (mode · advanced_lens · density) sync to localStorage;
 * transient slices (selected_strategy · kill_posture) live in-memory only.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export const MODES = ['executive', 'operations', 'research', 'developer'];
export const DENSITIES = ['compact', 'cozy', 'cinema'];

const persistentSlice = (set) => ({
  mode: 'operations',
  advancedLens: false,
  density: 'cozy',
  setMode: (mode) => set({ mode }),
  toggleAdvancedLens: () => set((s) => ({ advancedLens: !s.advancedLens })),
  setDensity: (density) => set({ density }),
});

const transientSlice = (set) => ({
  selectedStrategyId: null,
  killPostureArmed: false,
  selectStrategy: (id) => set({ selectedStrategyId: id }),
  setKillPosture: (armed) => set({ killPostureArmed: armed }),
});

export const useWorkspaceStore = create(
  persist(
    (set, get) => ({
      ...persistentSlice(set, get),
      ...transientSlice(set, get),
    }),
    {
      name: 'sf-workspace-v2',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        mode: s.mode,
        advancedLens: s.advancedLens,
        density: s.density,
        timeWindow: s.timeWindow,
      }),
    }
  )
);
