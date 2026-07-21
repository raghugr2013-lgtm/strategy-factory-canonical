/*
 * inspectorStore — Sprint 1 debug affordance behind ?debug=1.
 * refs DESIGN_FREEZE_v1.0.md §2 (deferred) · P0 §5.2
 *
 * M1 ships a minimal stub so downstream primitives compile against the
 * same store surface as the prototype's Inspector. The full inspector is
 * out of Sprint 1 scope; see DESIGN_FREEZE §2.1.
 */
import { create } from 'zustand';

export const useInspectorStore = create((set) => ({
  open: false,
  canonicalState: 'happy',
  scenarioKey: null,
  toggle: () => set((s) => ({ open: !s.open })),
  setCanonicalState: (canonicalState) => set({ canonicalState }),
  setScenario: (scenarioKey) => set({ scenarioKey }),
}));
