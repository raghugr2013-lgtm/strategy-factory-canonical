# Phase D2 · Evaluation Harness — Unlock Diff

_Interactive controls unlocked. Layout, testids, and route unchanged from D1._

## 1. Change surface

| File                                                | D1 → D2 diff |
|-----------------------------------------------------|--------------|
| `frontend/src/os/surfaces/EvaluationHarness.jsx`    | Bound `setVerdict` / `setSession` / `setNotes` / `clearAll` / `markAllPass` from `useEvaluationStore`. Removed `disabled` / `readOnly` / `aria-disabled` / D2 tooltip on write controls. Wired `onClick` / `onChange`. `data-phase="d2"`. |
| `frontend/src/os/surfaces/MissionControl.jsx`       | Discovery badge label `D1 preview` → `walkable checklist`. |
| `frontend/tests/e2e/evaluation-harness.spec.cjs`    | Replaced 5 read-only assertions with 9 interaction tests (see §4). |
| `frontend/src/os/workspace-state/evaluationStore.js`| **Untouched** — mutators pre-declared in D1. |
| `frontend/src/os/routing/AppRouter.jsx`             | **Untouched** — `/c/evaluation` route unchanged. |
| Backend                                             | **Untouched** — Feature Freeze preserved. |

## 2. Interaction graph

```
EvaluationHarness.jsx
    │
    │  ─── UI ────────────────────────────────────────────────
    │
    ├── verdict button (24 × 4 = 96)         onClick → setVerdict(id, verdict)
    ├── eval-session-label     <input>       onChange → setSession(str)
    ├── eval-notes             <textarea>    onChange → setNotes(str)
    ├── eval-reset             <button>      onClick → clearAll()
    ├── eval-mark-all-pass     <button>      onClick → markAllPass()
    │
    ▼
useEvaluationStore  (zustand, single writer)
    │
    ▼
writePersisted() → localStorage['sf.eval.v1'] = { verdicts, notes, session }
    │
    ▼
set() → subscribed components re-render
    │
    ▼
summariseDimension / overallReadiness re-derive → chips + readiness card update
```

## 3. Layout stability

Every write control in D2 renders with the same size, position, colour,
and font as D1. Verdict buttons keep `minWidth: 60` — the D1 `disabled`
attribute was purely additive, so removing it does not resize the
button box. Session-label input keeps `minWidth: 280`.

Sanity-checked via the "surface anatomy is preserved from D1" test in
`evaluation-harness.spec.cjs` — all six dimensions, all 24 criteria
testids, and the readiness card render at the same nesting depth.

## 4. E2E coverage (9 tests)

1. Surface anatomy preserved (data-phase=d2, 6 dims, 24 criteria)
2. All write controls enabled (verdict buttons, reset, mark-all, session input, notes)
3. `setVerdict` updates criterion pill · dimension summary · readiness card
4. `setSession` + `setNotes` persist to store + localStorage
5. `markAllPass` flips every criterion to pass · readiness → ready
6. `clearAll` wipes verdicts · readiness → unstarted
7. Verdicts persist across a page reload (localStorage restore)
8. Discovery link `mc-open-evaluation` still routes to `/c/evaluation`
9. Back-to-Mission button navigates home

## 5. Backend freeze compliance

- No new API endpoints.
- No new adapters.
- Zero network calls added.
- All persistence stays in `localStorage['sf.eval.v1']` (client-only).

## 6. Rollback

Single commit. `git revert <sha>` restores D1's read-only mode without
touching any other surface.
