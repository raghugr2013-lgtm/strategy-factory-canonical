/*
 * Workspace state store — Bible §1.4.4 Context Never Lost.
 * Zustand-backed; localStorage for persistent posture; sessionStorage for CNL fields.
 */
import { create } from 'zustand';

type Mode = 'executive' | 'operations' | 'research' | 'developer';
type Density = 'compact' | 'cozy' | 'cinema';

interface WorkspaceState {
  mode: Mode;
  advancedLens: boolean;
  density: Density;
  timeWindow: string;         // 'live' | 'last-24h' | 'last-7d' etc.
  selectedStrategy: string | null;
  selectedWorker: string | null;
  killPostureArmed: boolean;
  isFirstTime: boolean;
  cmdkHintDismissed: boolean;
  advancedLensHintDismissed: boolean;

  setMode: (mode: Mode) => void;
  toggleAdvancedLens: () => void;
  setDensity: (d: Density) => void;
  setTimeWindow: (t: string) => void;
  selectStrategy: (id: string | null) => void;
  selectWorker: (id: string | null) => void;
  armKillPosture: (armed: boolean) => void;
  markCmdkDiscovered: () => void;
  markAdvancedLensDiscovered: () => void;
  markVisited: () => void;
}

const readLocal = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch { return fallback; }
};
const writeLocal = (key: string, val: unknown) => {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  mode: readLocal<Mode>('sf.mode', 'operations'),
  advancedLens: readLocal<boolean>('sf.advancedLens', false),
  density: readLocal<Density>('sf.density', 'compact'),
  timeWindow: 'live',
  selectedStrategy: null,
  selectedWorker: null,
  killPostureArmed: false,
  isFirstTime: !readLocal<boolean>('sf.hasVisited', false),
  cmdkHintDismissed: readLocal<boolean>('sf.hint.cmdkUsed', false),
  advancedLensHintDismissed: readLocal<boolean>('sf.hint.advancedLensUsed', false),

  setMode: (mode) => { writeLocal('sf.mode', mode); set({ mode }); },
  toggleAdvancedLens: () => set((s) => {
    const next = !s.advancedLens;
    writeLocal('sf.advancedLens', next);
    return { advancedLens: next };
  }),
  setDensity: (density) => { writeLocal('sf.density', density); set({ density }); },
  setTimeWindow: (timeWindow) => set({ timeWindow }),
  selectStrategy: (selectedStrategy) => set({ selectedStrategy }),
  selectWorker: (selectedWorker) => set({ selectedWorker }),
  armKillPosture: (killPostureArmed) => set({ killPostureArmed }),
  markCmdkDiscovered: () => {
    writeLocal('sf.hint.cmdkUsed', true);
    set({ cmdkHintDismissed: true });
  },
  markAdvancedLensDiscovered: () => {
    writeLocal('sf.hint.advancedLensUsed', true);
    set({ advancedLensHintDismissed: true });
  },
  markVisited: () => { writeLocal('sf.hasVisited', true); set({ isFirstTime: false }); },
}));

/* D6: declarative concept/density helpers — Decision Identity contract */
export const conceptFor = (mode: Mode): 'A' | 'B' | 'C' =>
  mode === 'executive' ? 'C' : mode === 'research' ? 'B' : 'A';

export const defaultDensityFor = (mode: Mode): Density =>
  mode === 'executive' ? 'cinema' : mode === 'research' ? 'cozy' : 'compact';
