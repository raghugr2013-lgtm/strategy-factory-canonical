/*
 * navigationStore — Phase 5 · Cross-module wiring contract.
 *
 * Encodes three of the four Phase 5 invariants:
 *   1. Rule of Predictable Return  (E5 §4.5) — the last surface state
 *      (facets, drawer, scroll intent, resolved-strip visibility) is
 *      restored when the operator returns to a surface via back-nav.
 *   2. Facet Bar cascade           (Bible §7.4a) — a shared facet plane
 *      (actor kind, status, risk) cascades across Timeline, Approval
 *      Center, Strategy Explorer, and passports. Each surface projects
 *      the cascade onto its own facet axis.
 *   3. Decision Identity           (D6 §8.1a) — the selected strategy id
 *      is the shared truth. When cross-navigation intent is captured
 *      (`origin` + `originLabel`), Predictable Return uses it to render
 *      the correct back-button copy on the passport.
 *
 * The fourth invariant (Master Bot three-view toggle) lives on the
 * MasterBot surface itself; it does not need cross-module state.
 *
 * PROTOTYPE ONLY. Removed at Design Freeze; production Sprint 1 replaces
 * this with a URL-scheme + IndexedDB-backed workspace state store per D8 §5.
 */
import { create } from 'zustand';
import type { ActorKind } from '../primitives/ActivityRow';
import type { RiskLevel } from '../primitives/ApprovalCard';

// ─── Facet cascade ─────────────────────────────────────────────────────

export type StrategyStatusFacet = 'live' | 'paper' | 'paused' | 'reviewing' | 'all';
export type ActorFacet = ActorKind | 'all';
export type RiskFacet = RiskLevel | 'all';

export interface FacetPlane {
  actor: ActorFacet;
  status: StrategyStatusFacet;
  risk: RiskFacet;
}

const DEFAULT_FACETS: FacetPlane = { actor: 'all', status: 'all', risk: 'all' };

// ─── Surface state memory ──────────────────────────────────────────────
// A per-pathname dictionary of arbitrary state slices. Surfaces
// hand-select which state they want to persist (drawer id, scroll to
// row, resolved chip). Keyed by pathname to keep it O(surfaces).

export interface SurfaceMemory {
  [pathname: string]: Record<string, unknown>;
}

// ─── Return-path breadcrumb ────────────────────────────────────────────
// When a surface navigates to a passport/detail view, it drops a
// breadcrumb describing where the operator came from and what label
// should appear on the back button. Passport reads it on mount.

export interface ReturnCrumb {
  path: string;      // e.g. '/c/timeline'
  label: string;     // e.g. 'back to timeline'
  origin: 'timeline' | 'approvals' | 'explorer' | 'mission' | 'workforce' | 'gallery' | 'eval';
  originId?: string; // optional focus id in the origin surface
}

// ─── Store shape ───────────────────────────────────────────────────────

interface NavigationState {
  facets: FacetPlane;
  memory: SurfaceMemory;
  crumb: ReturnCrumb | null;

  // Facet cascade helpers
  setFacet: <K extends keyof FacetPlane>(k: K, v: FacetPlane[K]) => void;
  resetFacets: () => void;

  // Surface memory
  saveSurface: (path: string, slice: Record<string, unknown>) => void;
  readSurface: <T extends Record<string, unknown>>(path: string) => T | undefined;
  clearSurface: (path: string) => void;

  // Return-path breadcrumb
  setCrumb: (c: ReturnCrumb | null) => void;
  consumeCrumb: () => ReturnCrumb | null;
}

export const useNavigationStore = create<NavigationState>((set, get) => ({
  facets: { ...DEFAULT_FACETS },
  memory: {},
  crumb: null,

  setFacet: (k, v) => set((s) => ({ facets: { ...s.facets, [k]: v } })),
  resetFacets: () => set({ facets: { ...DEFAULT_FACETS } }),

  saveSurface: (path, slice) =>
    set((s) => ({ memory: { ...s.memory, [path]: { ...(s.memory[path] ?? {}), ...slice } } })),
  readSurface: <T extends Record<string, unknown>>(path: string) =>
    (get().memory[path] as T | undefined),
  clearSurface: (path) => set((s) => {
    const next = { ...s.memory }; delete next[path];
    return { memory: next };
  }),

  setCrumb: (crumb) => set({ crumb }),
  consumeCrumb: () => {
    const c = get().crumb;
    if (c) set({ crumb: null });
    return c;
  },
}));
