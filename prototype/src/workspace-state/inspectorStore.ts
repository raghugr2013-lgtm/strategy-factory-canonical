/*
 * Inspector store — PROTOTYPE ONLY.
 * Controls the Fixture Debug Panel's state toggles + scenario preset selection.
 * NOT part of the production contract. Removed at Design Freeze.
 */
import { create } from 'zustand';
import { SCENARIOS, type ScenarioKey } from '../gallery/scenarios';
import { useWorkspaceStore } from './store';

export type CanonicalState = 'happy' | 'loading' | 'empty' | 'error' | 'dormant';

interface InspectorState {
  canonicalState: CanonicalState;
  reducedMotion: boolean;
  longContent: boolean;
  scenarioKey: ScenarioKey | null;
  showSheet: boolean;

  setCanonicalState: (s: CanonicalState) => void;
  setReducedMotion: (v: boolean) => void;
  setLongContent: (v: boolean) => void;
  applyScenario: (key: ScenarioKey) => void;
  clearScenario: () => void;
  toggleSheet: () => void;
  setShowSheet: (v: boolean) => void;
}

export const useInspectorStore = create<InspectorState>((set) => ({
  canonicalState: 'happy',
  reducedMotion: false,
  longContent: false,
  scenarioKey: null,
  showSheet: false,

  setCanonicalState: (canonicalState) => set({ canonicalState, scenarioKey: null }),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
  setLongContent: (longContent) => set({ longContent, scenarioKey: null }),
  applyScenario: (key) => {
    const s = SCENARIOS.find((x) => x.key === key);
    if (!s) return;
    // Fan-out into workspace store. Fixture-only; no simulated events.
    const ws = useWorkspaceStore.getState();
    ws.setMode(s.mode);
    ws.setDensity(s.density);
    if (s.advancedLens !== ws.advancedLens) ws.toggleAdvancedLens();
    ws.armKillPosture(s.killPosture);
    set({
      scenarioKey: key,
      canonicalState: s.canonicalState,
      longContent: s.longContent,
    });
  },
  clearScenario: () => set({ scenarioKey: null }),
  toggleSheet: () => set((s) => ({ showSheet: !s.showSheet })),
  setShowSheet: (showSheet) => set({ showSheet }),
}));
