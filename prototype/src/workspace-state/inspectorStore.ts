/*
 * Inspector store — PROTOTYPE ONLY.
 * Controls the Fixture Debug Panel's state toggles.
 * NOT part of the production contract. Removed at Design Freeze.
 */
import { create } from 'zustand';

export type CanonicalState = 'happy' | 'loading' | 'empty' | 'error' | 'dormant';

interface InspectorState {
  canonicalState: CanonicalState;
  reducedMotion: boolean;
  longContent: boolean;

  setCanonicalState: (s: CanonicalState) => void;
  setReducedMotion: (v: boolean) => void;
  setLongContent: (v: boolean) => void;
}

export const useInspectorStore = create<InspectorState>((set) => ({
  canonicalState: 'happy',
  reducedMotion: false,
  longContent: false,

  setCanonicalState: (canonicalState) => set({ canonicalState }),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
  setLongContent: (longContent) => set({ longContent }),
}));
