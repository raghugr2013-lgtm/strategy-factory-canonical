/*
 * evaluationStore — Phase 6 · Evaluation Harness.
 *
 * Codifies the six evaluation dimensions from `P0_PROTOTYPE_BLUEPRINT.md`
 * §5 as walkable checklists. Each dimension carries authored criteria
 * mapped to concrete surfaces/behaviours in the prototype. The operator
 * marks each criterion as pass · review · fail, and a rolled-up
 * readiness indicator determines whether Design Freeze can be declared.
 *
 * PROTOTYPE ONLY. Persists to localStorage under `sf.eval.v1`. Removed
 * at Design Freeze; production Sprint 1 uses formal Playwright + axe
 * pipelines.
 */
import { create } from 'zustand';

export type EvalVerdict = 'pass' | 'review' | 'fail' | 'unset';

export type DimensionKey =
  | 'discoverability'
  | 'navigation-predictability'
  | 'cognitive-load'
  | 'interaction-rhythm'
  | 'trust'
  | 'identity';

export interface Criterion {
  id: string;                 // stable id used as data-testid + storage key
  headline: string;           // short imperative describing what to verify
  detail: string;             // where/how to verify (surface + interaction)
  reference?: string;         // D/E-series citation
}

export interface Dimension {
  key: DimensionKey;
  title: string;
  purpose: string;            // what this dimension is really measuring
  criteria: Criterion[];
}

// ─── Dimension catalogue ───────────────────────────────────────────────

export const DIMENSIONS: Dimension[] = [
  {
    key: 'discoverability',
    title: 'Discoverability',
    purpose: 'Can a first-time operator find the surface + action they need without a guide?',
    criteria: [
      { id: 'disc-1', headline: 'Primary navigation is obvious.',
        detail: 'The LeftRail exposes every top-level module with an icon + label.',
        reference: 'Bible §4.2, E2 §3.1' },
      { id: 'disc-2', headline: '⌘K hint is visible on first authenticated view.',
        detail: 'Header carries the ⌘K hint until dismissed once.',
        reference: 'D8 §5.4' },
      { id: 'disc-3', headline: 'Approval workflow is reachable from Mission in one click.',
        detail: 'Mission Control surfaces an "open Approval Center →" affordance when approvals are pending.',
        reference: 'D3 §4' },
      { id: 'disc-4', headline: 'Advanced Lens is discoverable but never blocking.',
        detail: 'Inspector toggle + subtle in-surface footnotes reveal expert data.',
        reference: 'Bible §1.4.3' },
    ],
  },
  {
    key: 'navigation-predictability',
    title: 'Navigation Predictability',
    purpose: 'Do return trips restore the operator to exactly where they were?',
    criteria: [
      { id: 'pred-1', headline: 'Rule of Predictable Return honoured Timeline → Passport → back.',
        detail: 'Back button copy reads "back to timeline"; row + facet are restored.',
        reference: 'E5 §4.5' },
      { id: 'pred-2', headline: 'Rule of Predictable Return honoured Approvals → Passport → back.',
        detail: 'Back button copy reads "back to approvals"; resolved chips + risk facet restored.',
        reference: 'E5 §4.5' },
      { id: 'pred-3', headline: 'Facet Bar cascade is visible across surfaces.',
        detail: 'Timeline actor facet, Approvals risk facet, Explorer status facet all persist between surfaces.',
        reference: 'Bible §7.4a' },
      { id: 'pred-4', headline: 'Cross-navigation shortcuts carry Decision Identity.',
        detail: 'Opening a strategy from Timeline or Approvals lands on the same passport that Explorer opens.',
        reference: 'D6 §8.1a' },
    ],
  },
  {
    key: 'cognitive-load',
    title: 'Cognitive Load',
    purpose: 'Does the interface open with purpose, not with status noise?',
    criteria: [
      { id: 'load-1', headline: 'Every surface opens with Purpose Before Status.',
        detail: 'SurfaceHeader eyebrow + headline are purpose-first; version/plan trailers are meta.',
        reference: 'D4 §5.1.1' },
      { id: 'load-2', headline: 'Only relevant data is dense.',
        detail: 'Mission Control shows three KPIs (not ten); Explorer status counts summarise, not compete.',
        reference: 'Bible §7.11' },
      { id: 'load-3', headline: 'State templates are visually consistent.',
        detail: 'Empty · loading · error · dormant follow the StateTemplate.',
        reference: 'D7 §3' },
      { id: 'load-4', headline: 'Advanced Lens off does not hide danger.',
        detail: 'Kill posture, aged approvals, governance holds are visible without expert toggles.',
        reference: 'D6 §5.2' },
    ],
  },
  {
    key: 'interaction-rhythm',
    title: 'Interaction Rhythm',
    purpose: 'Does the interface breathe? Do reveal-motion, latency, and hover feedback feel deliberate?',
    criteria: [
      { id: 'rhy-1', headline: 'Reveal-motion is staggered, not synchronous.',
        detail: 'Timeline rows + WorkerCards use fadeInUp with stagger.',
        reference: 'Bible §6.1' },
      { id: 'rhy-2', headline: 'Drawer + sheet transitions feel physical.',
        detail: 'EvidenceDrawer + InspectorSheet slide with the drawerSlide preset.',
        reference: 'Bible §6.2' },
      { id: 'rhy-3', headline: 'Reduced-motion is honoured.',
        detail: 'Inspector reduced-motion + prefers-reduced-motion both flatten all motion presets.',
        reference: 'Bible §6.4' },
      { id: 'rhy-4', headline: 'Hover feedback is present but never noisy.',
        detail: 'Table rows + WorkerCards translate 1px on hover; no bouncy transforms.',
        reference: 'D1 §7.2' },
    ],
  },
  {
    key: 'trust',
    title: 'Operator Trust',
    purpose: 'Does the operator ever have to guess whether an artefact is real, attested, and safe to act on?',
    criteria: [
      { id: 'trust-1', headline: 'Provenance triple appears on every material artefact.',
        detail: 'Passport, ApprovalCard, EvidenceDrawer each carry ProvenanceTriple.',
        reference: 'Bible §10' },
      { id: 'trust-2', headline: 'Kill posture cannot be missed when armed.',
        detail: 'Danger ribbon + kill-posture chip + MasterBot notice all fire together.',
        reference: 'E2 §9.4, D4 §7' },
      { id: 'trust-3', headline: 'Aged approvals are visually elevated.',
        detail: 'Approval Center sorts high-risk first, then by age; aged >60m is rendered distinctly.',
        reference: 'D3 §5' },
      { id: 'trust-4', headline: 'Trust Before Credentials — auth surface exposes kill posture + version pre-login.',
        detail: 'Sign-in screen shows environment posture chips even to anonymous visitors.',
        reference: 'E2 §9' },
    ],
  },
  {
    key: 'identity',
    title: 'Product Identity',
    purpose: 'Is the product recognisable? Does the visual language feel invisible-luxury and consistent?',
    criteria: [
      { id: 'id-1', headline: 'Signature Frame is applied consistently.',
        detail: 'Mission, Approvals, Passport, MasterBot all frame content with SignatureFrame variants.',
        reference: 'D5 §2' },
      { id: 'id-2', headline: 'Division Caption expresses D2 storytelling voice.',
        detail: 'DivisionCaption declares purpose in Mission + MasterBot before showing data.',
        reference: 'D2 addendum' },
      { id: 'id-3', headline: 'Token-only styling — nothing hardcoded outside tokens.css.',
        detail: 'Colours + spacing + typography reference CSS variables only.',
        reference: 'D8 §4' },
      { id: 'id-4', headline: 'Decision Identity is a chip, not a note.',
        detail: 'Every artefact carries a monospace `identity · <id>` chip in surfaces + drawers.',
        reference: 'D6 §8.1a' },
    ],
  },
];

// ─── State ─────────────────────────────────────────────────────────────

export type VerdictMap = Record<string, EvalVerdict>;

interface EvaluationState {
  verdicts: VerdictMap;
  notes: string;
  session: string;              // free-form label for this walk-through
  setVerdict: (criterionId: string, v: EvalVerdict) => void;
  clearAll: () => void;
  markAllPass: () => void;
  setNotes: (notes: string) => void;
  setSession: (session: string) => void;
}

const STORAGE_KEY = 'sf.eval.v1';

interface Persist { verdicts: VerdictMap; notes: string; session: string; }

const read = (): Persist => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Persist : { verdicts: {}, notes: '', session: '' };
  } catch { return { verdicts: {}, notes: '', session: '' }; }
};
const write = (p: Persist) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(p)); } catch {}
};

export const useEvaluationStore = create<EvaluationState>((set, get) => {
  const persisted = read();
  return {
    verdicts: persisted.verdicts,
    notes: persisted.notes,
    session: persisted.session,

    setVerdict: (criterionId, v) => {
      const next = { ...get().verdicts, [criterionId]: v };
      write({ verdicts: next, notes: get().notes, session: get().session });
      set({ verdicts: next });
    },
    clearAll: () => { write({ verdicts: {}, notes: get().notes, session: get().session }); set({ verdicts: {} }); },
    markAllPass: () => {
      const next: VerdictMap = {};
      DIMENSIONS.forEach((d) => d.criteria.forEach((c) => { next[c.id] = 'pass'; }));
      write({ verdicts: next, notes: get().notes, session: get().session });
      set({ verdicts: next });
    },
    setNotes:   (notes)   => { write({ verdicts: get().verdicts, notes, session: get().session }); set({ notes }); },
    setSession: (session) => { write({ verdicts: get().verdicts, notes: get().notes, session }); set({ session }); },
  };
});

// ─── Derived helpers ───────────────────────────────────────────────────

export interface DimensionSummary {
  key: DimensionKey;
  title: string;
  total: number;
  pass: number;
  review: number;
  fail: number;
  unset: number;
  verdict: EvalVerdict;
}

export const summariseDimension = (d: Dimension, v: VerdictMap): DimensionSummary => {
  const s: DimensionSummary = { key: d.key, title: d.title, total: d.criteria.length,
    pass: 0, review: 0, fail: 0, unset: 0, verdict: 'unset' };
  d.criteria.forEach((c) => {
    const x = v[c.id] ?? 'unset';
    s[x] += 1;
  });
  s.verdict = s.fail > 0 ? 'fail'
            : s.review > 0 ? 'review'
            : s.unset > 0 ? 'unset'
            : 'pass';
  return s;
};

export interface OverallReadiness {
  verdict: 'ready' | 'nearly' | 'blocked' | 'unstarted';
  pass: number;
  review: number;
  fail: number;
  unset: number;
  total: number;
  passPct: number;
  headline: string;
  detail: string;
}

export const overallReadiness = (v: VerdictMap): OverallReadiness => {
  let pass = 0, review = 0, fail = 0, unset = 0, total = 0;
  DIMENSIONS.forEach((d) => d.criteria.forEach((c) => {
    total += 1;
    const x = v[c.id] ?? 'unset';
    if (x === 'pass') pass += 1;
    else if (x === 'review') review += 1;
    else if (x === 'fail') fail += 1;
    else unset += 1;
  }));
  const passPct = total ? Math.round((pass / total) * 100) : 0;

  if (fail > 0) {
    return { verdict: 'blocked', pass, review, fail, unset, total, passPct,
      headline: 'Design Freeze BLOCKED.',
      detail: `${fail} criterion${fail === 1 ? '' : 'a'} failing. Author addenda and re-verify before requesting sign-off.` };
  }
  if (pass === total) {
    return { verdict: 'ready', pass, review, fail, unset, total, passPct,
      headline: 'Design Freeze READY.',
      detail: 'Every dimension is passing. Capture the summary and request operator sign-off.' };
  }
  if (unset === total) {
    return { verdict: 'unstarted', pass, review, fail, unset, total, passPct,
      headline: 'Evaluation not started.',
      detail: 'Walk each surface and mark verdicts against the six dimensions.' };
  }
  return { verdict: 'nearly', pass, review, fail, unset, total, passPct,
    headline: 'Evaluation IN PROGRESS.',
    detail: `${unset} unmarked · ${review} under review · ${pass}/${total} passing (${passPct}%).` };
};
