# Phase D1 · Evaluation Harness — Architecture Diagram

_Read-only visualization of the 24-criterion Interactive Prototype Gate.
Ships as a net-new additive surface. No backend contract change._

## 1. Component graph

```
                              ┌─────────────────────────────┐
                              │       AppRouter.jsx         │
                              │   /c/evaluation   (D1)      │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │   surfaces/                 │
                              │   EvaluationHarness.jsx     │◀──── DOM · data-testid="evaluation-harness"
                              │   (read-only in D1)         │
                              └───┬───────────┬─────────────┘
                                  │           │
                 ┌────────────────┘           └──────────────────┐
                 │                                               │
                 ▼                                               ▼
     ┌──────────────────────────┐                    ┌──────────────────────────┐
     │  workspace-state/         │                    │  primitives/             │
     │  evaluationStore.js       │                    │   • SurfaceHeader        │
     │   • DIMENSIONS (24 crit.) │                    │   • SignatureFrame       │
     │   • summariseDimension    │                    │   • Chip                 │
     │   • overallReadiness      │                    │  (unchanged · Phase A/B) │
     │   • mutators (D2 wire)    │                    └──────────────────────────┘
     └────────────┬──────────────┘
                  │
                  ▼
        ┌────────────────────────┐
        │   localStorage         │
        │   key = sf.eval.v1     │
        │   { verdicts, notes,   │
        │     session }          │
        └────────────────────────┘

              (NO backend adapter · NO API call · NO SSE)
```

## 2. Route contract

| Route              | Component            | Phase | Status |
|--------------------|----------------------|-------|--------|
| `/c/evaluation`    | `EvaluationHarness`  | D1    | **NEW** — additive, no legacy pair |

No existing routes are modified. Rollback = revert this single commit.

## 3. State model

`useEvaluationStore` is client-only and persists to `localStorage`
under `sf.eval.v1`. In D1 the surface **reads** three slices:

| Slice     | D1 behaviour              | D2 behaviour                     |
|-----------|---------------------------|----------------------------------|
| verdicts  | Rendered as pill colours  | Mutated by verdict buttons       |
| notes     | Rendered read-only        | Editable via textarea            |
| session   | Rendered read-only        | Editable via session input       |

Mutators (`setVerdict`, `clearAll`, `markAllPass`, `setNotes`,
`setSession`) are already exported from the store but are **not wired to
DOM handlers in D1** — the surface passes `disabled` / `readOnly` to
every write control instead. This keeps D1 → D2 a pure "unlock" change
with zero layout drift.

## 4. Derived helpers

```
verdicts (Record<criterionId, EvalVerdict>)
        │
        ├── summariseDimension(d, verdicts) → { pass, review, fail, unset, verdict }
        │       used by the six dimension summary cards and section badges
        │
        └── overallReadiness(verdicts)      → { verdict, pass, review, fail, unset,
                                                 total, passPct, headline, detail }
                used by the SignatureFrame readiness card
                verdict ∈ { unstarted · nearly · blocked · ready }
```

## 5. Discovery affordance

`MissionControl.jsx` renders a subtle link block after the "Latest
activity" section:

```
[ClipboardCheck] Interactive Prototype Gate  · [D1 preview] ·  Open Evaluation Harness →
```

Wired via `data-testid="mc-open-evaluation"`. Mirrors the Phase B
`mc-open-approvals` and Phase C explorer discovery patterns.

## 6. What lands in D2 (not this commit)

- Enable `onClick` handlers on the four verdict buttons per criterion
  (setVerdict).
- Enable session-label `onChange` (setSession).
- Enable notes textarea `onChange` (setNotes).
- Enable `reset verdicts` and `mark all pass` buttons.
- Add discovery affordance from Mission Control **only when** the
  operator has an active in-progress session (nearly / blocked).
- Formal Playwright coverage for the write path.

## 7. Testing surface

| Layer      | File                                                  | Scope |
|------------|-------------------------------------------------------|-------|
| Store      | `workspace-state/evaluationStore.js`                  | Unit-ready (pure fns) |
| Component  | `surfaces/EvaluationHarness.jsx`                      | data-testid coverage |
| Storybook  | `surfaces/EvaluationHarness.stories.jsx`              | 4 states (Unstarted / InProgress / Blocked / Ready) |
| E2E        | `tests/e2e/evaluation-harness.spec.cjs`               | 5 tests (anatomy, 24 criteria, disabled state, discovery, back-nav) |

## 8. Backend freeze compliance

- No new API endpoints.
- No new adapters.
- No changes to `factoryAdapter`, `strategyLabAdapter`, `missionAggregator`.
- Surface performs **zero** network calls.
- `MissionControl.jsx` gains a single anchor tag; no new adapter calls.

Verified by grep:

```
$ rg -n "fetch|axios|adapter" frontend/src/os/surfaces/EvaluationHarness.jsx
(no matches)
```
