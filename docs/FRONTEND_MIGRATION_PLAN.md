# Frontend Gap Analysis & Migration Plan — Prototype → Production

_Generated 2026-07-24. Read-only analysis; no code changes in this document._

---

## TL;DR — the premise deserves a correction

The task brief states "The deployed frontend (frontend/) is the legacy
Mission Control UI." **The code disagrees.** Reality:

| Layer | Path | Status |
| --- | --- | --- |
| Legacy Mission Control (v01 CommandShell) | `frontend/.archive/v01/` and `frontend/legacy/src/` | **ARCHIVED** — not compiled by `frontend/Dockerfile`, not imported by `frontend/src/index.js` |
| Prototype (design-validation only) | `prototype/src/` | **Standalone Vite app** — never built into the production image |
| Production frontend (what ships) | `frontend/src/os/*` | **Already the prototype design** — the entry point (`frontend/src/index.js:13`) mounts `./os/routing/AppRouter`, `tokens.css` is identical between prototype and frontend/os (0 diff on `--vars`) |

Confirmations:
- `frontend/Dockerfile` builds `frontend/src/` only (`yarn build` → nginx). No reference to `legacy/`.
- `grep -r 'from.*legacy' frontend/src` → 0 hits.
- Design tokens: `comm -23 prototype/src/tokens.css frontend/src/os/tokens.css` → 0 unique tokens on either side.
- Primitive parity (MetricBlock sample): frontend version is a **line-for-line JSX conversion** of the prototype TSX, same imports, same states, same styling — 178→94 LOC purely from TS-annotation removal.

**The frontend is NOT a legacy UI. It is a matured version of the prototype.** In several places (AppShell, ApprovalsModal, CmdKPalette, FactoryWalkthrough) the frontend has **surpassed** the prototype — the prototype's inline chrome has been refactored into modular sub-components, and 3 subsystems (⌘K palette, onboarding walkthrough, global approvals modal) exist in the frontend that never existed in the prototype.

**What the operator probably sees on the deployed site is either (a) a real UI regression relative to their design memory (specific surface still stubbed), or (b) some Phase-1-era surfaces that are functionally complete but visually thin compared to the prototype's target polish.** This gap analysis identifies the concrete deltas.

---

## Delta inventory — code-level comparison

### 1. Directory shape

| Directory | prototype | frontend/os | Delta |
| --- | :---: | :---: | --- |
| `adapters/` | ✗ | 17 files | frontend adds real API integration (Phase-1) |
| `auth/` | 3 | 2 | frontend missing `UserMenu` |
| `features/` | ✗ | 7 files | frontend-only: FacetBar, StreamPostmark, TimeWindowChip, focus-trap hooks |
| `gallery/` | 4 | 1 | frontend has PrimitiveGallery only; prototype has Inspector + scenarios + fixtures |
| `hooks/` | ✗ | 1 file | frontend-only: `useWorkspaceContext` |
| `onboarding/` | ✗ | 2 files | frontend-only: `FactoryWalkthrough` |
| `palette/` | ✗ | 1 file | frontend-only: `CmdKPalette` |
| `primitives/` | 15 | 15 (+ 15 stories) | 100% ported; frontend adds Storybook |
| `routing/` | ✗ | 3 files | frontend-only: `AppRouter`, `navigation`, `routes` |
| `shell/` | 4 | 7 | frontend refactored inline chrome → 5 modular components; **missing InspectorSheet, LeftRailStub, UserMenu integration** |
| `surfaces/` | 11 | 26 | frontend has 15 additional Phase-1 surfaces (engineering, admin, factory dashboards); **missing 6 prototype surfaces** |
| `workspace-state/` | 5 | 5 | 4 of 5 ported; **missing `evaluationStore`** |

### 2. The 6 unported prototype surfaces (real gaps)

| Surface | prototype LOC | Ported? | Notes |
| --- | ---: | :---: | --- |
| `ApprovalCenter.tsx` | 266 | ❌ | Frontend has `ApprovalsModal` (globally mounted) — but that's an *overlay*, not a dedicated inbox surface. Frontend also has `Approvals.jsx` (79 LOC — stub). **True gap.** |
| `EvaluationHarness.tsx` | 397 | ❌ | Full evaluation-run UI (runs the walk-forward / OOS harness interactively). No equivalent in frontend/os. |
| `StrategyExplorer.tsx` | 175 | ❌ | Strategy discovery / library exploration surface. Frontend has `Strategies.jsx` (different surface) but not the exploratory browsing UI. |
| `ScenarioBanner.tsx` | 35 | ❌ | Sandbox scenario indicator (dev-only in prototype context). |
| `UserMenu.tsx` | 194 | ❌ | User avatar + settings/logout menu. Frontend `Header.jsx` has login/logout but no rich menu. **True gap.** |
| `SurfaceHeader.tsx` | 65 | ❌ | Reusable per-surface header (title/breadcrumb/actions). Frontend surfaces roll their own headers today. |

### 3. The 2 unported prototype dev/gallery pieces

| File | Purpose | Ported? | Recommendation |
| --- | --- | :---: | --- |
| `shell/InspectorSheet.tsx` | Dev-only scenario/state inspector | ❌ | **Do NOT port** — it's a design-validation tool, not a production feature |
| `shell/LeftRailStub.tsx` | Placeholder rail for signed-out chrome | ❌ | **Do NOT port** — frontend `LeftRail` already handles the auth-aware states |
| `gallery/Inspector.tsx` + `scenarios.ts` + `scenarioFixtures.ts` + `fixtures.ts` | Prototype-side design fixtures | ❌ | **Do NOT port** — frontend `adapters/fixtures.js` covers the real-data fixture set |

### 4. AppShell composition — refactored, not regressed

Prototype `AppShell.tsx` (211 LOC) is one big file with inline chrome (header, danger ribbon, footer, all styles co-located, InspectorSheet mounted).

Frontend `AppShell.jsx` (54 LOC) is a **modularized version**:

```
AppShell (54)
  ├─ DangerRibbon.jsx            (extracted, auth-aware)
  ├─ Header.jsx                  (extracted)
  ├─ LeftRail.jsx                (extracted)
  ├─ StatusRail.jsx              (extracted — replaces prototype footer)
  ├─ ApprovalsModal.jsx          (frontend-only)
  ├─ CmdKPalette.jsx             (frontend-only)
  └─ FactoryWalkthrough.jsx      (frontend-only)
```

**This is a code-review-approved improvement, not a regression.** The
frontend has 3 subsystems the prototype never had. The only real
composition gap is that the frontend `Header` does not yet mount
`UserMenu` (see §2).

### 5. Preserved subsystems — no work needed

| Subsystem | Confirmed intact |
| --- | --- |
| Design tokens (`tokens.css`) | ✅ identical vars, 118 vs 113 LOC (tail-of-file comment diff only) |
| Primitives (15 components) | ✅ all ported, same states, same variants; TS→JSX conversion only |
| Auth flow (`LoginScreen`, `RequireAuth`, `authStore`) | ✅ ported and expanded (real JWT integration via `adapters/apiClient.js`) |
| Motion helpers (`motion.ts` → `motion.js`) | ✅ ported |
| Workspace state (4 of 5 stores) | ✅ ported |
| Routing (React Router) | ✅ present at `os/routing/AppRouter.jsx` |
| API integration layer | ✅ 17 adapters, all Phase-1 tested |
| Backend compatibility | ✅ no HTTP-surface changes contemplated |

---

## Migration plan — phased, incremental, no rewrite

Design philosophy for every phase:
- **Preserve** authentication (`authStore` + `RequireAuth` untouched).
- **Preserve** routing (`AppRouter` untouched except for lazy-mount additions).
- **Preserve** API adapters (reuse existing `adapters/*.js`; do not add new HTTP calls without an existing endpoint).
- **Preserve** backend compatibility (API Feature Freeze respected — no route changes).
- **Avoid** rewriting anything already present. Every new surface is a **new file** that plugs into existing adapters.

### Phase A — Shell parity (P0 · small · ~4–6 h)

**Goal**: close the AppShell composition gap without regressing existing subsystems.

Deliverables:
1. Port `prototype/src/auth/UserMenu.tsx` → `frontend/src/os/auth/UserMenu.jsx`.
   Wire to `authStore.stance` + `authStore.logout()` + `RequireAuth` context. Add data-testid `user-menu-*` conventions.
2. Extend `frontend/src/os/shell/Header.jsx` to mount `UserMenu` in the top-right slot (already reserved for it — currently renders a plain "Logout" button).
3. Port `prototype/src/surfaces/SurfaceHeader.tsx` → `frontend/src/os/primitives/SurfaceHeader.jsx`.
   Provide a reusable title/breadcrumb/actions primitive. Do NOT force existing surfaces to adopt it in this phase — just make it available.
4. Storybook stories for both new components (frontend convention — every primitive has a `.stories.jsx`).

Risk: negligible. Additive-only. No routing, no adapter changes.

### Phase B — ApprovalCenter surface (P0 · medium · ~10–14 h)

**Goal**: replace the `Approvals.jsx` stub with a full inbox surface.

Deliverables:
1. Port `prototype/src/surfaces/ApprovalCenter.tsx` → `frontend/src/os/surfaces/ApprovalCenter.jsx`.
2. Wire to `adapters/approvalsAdapter.js` (already exists) for list / approve / reject actions.
3. Keep `ApprovalsModal.jsx` (the shell-global overlay) as the quick-action surface; `ApprovalCenter` becomes the full-page inbox. Route: `/approvals` (existing).
4. Delete or minimize `Approvals.jsx` stub.

Risk: low. Adapter and route already exist. Feature-freeze compliant (no new API).

### Phase C — StrategyExplorer surface (P1 · medium · ~10–14 h)

**Goal**: dedicated strategy discovery surface, complementing the existing `Strategies.jsx` list view.

Deliverables:
1. Port `prototype/src/surfaces/StrategyExplorer.tsx` → `frontend/src/os/surfaces/StrategyExplorer.jsx`.
2. Wire to `adapters/curatedLibraryAdapter.js` + `adapters/strategyLabAdapter.js` (both exist).
3. Decision point: does `Strategies.jsx` stay, or does `StrategyExplorer` supersede it? Recommend **keep both** — `Strategies` is a fast tabular list, `StrategyExplorer` is a browsing/discovery surface. Add a nav entry.

Risk: low. Adapters exist.

### Phase D — EvaluationHarness surface (P1 · large · ~16–22 h)

**Goal**: interactive evaluation-run UI.

Deliverables:
1. Port `prototype/src/surfaces/EvaluationHarness.tsx` → `frontend/src/os/surfaces/EvaluationHarness.jsx` (397 LOC — the largest single item).
2. Port `prototype/src/workspace-state/evaluationStore.ts` → `frontend/src/os/workspace-state/evaluationStore.js`.
3. Wire to `adapters/factoryEvalAdapter.js` (exists) for run history + insight lists. **Does not** require any new backend endpoints — the harness surface visualises existing factory_evaluation task output.
4. Route: `/factory/evaluation` (new, add to `routes.js`).

Risk: medium — largest surface, but no new backend contracts.

### Phase E — Scenario mode + polish (P2 · small · ~4–6 h)

**Goal**: bring back the prototype's scenario-toggle observability, adapted for production.

Deliverables:
1. Port `ScenarioBanner.tsx` → `frontend/src/os/shell/ScenarioBanner.jsx`.
   In production this shows the current backend build hash + orchestrator mode (from `/api/orchestrator/status`) instead of the prototype's dev-scenario key. Purely observational.
2. Mount conditionally in `AppShell.jsx` (below `DangerRibbon`).
3. Sweep all primitives for behavioural drift (compare each JSX ↔ TSX pair; restore any lost states / animations / a11y).

Risk: negligible.

### Phase F — Storybook + regression harness (P2 · small · ~4 h)

**Goal**: parity of dev tooling.

Deliverables:
1. Add `.stories.jsx` for each newly ported surface (ApprovalCenter, StrategyExplorer, EvaluationHarness, UserMenu, SurfaceHeader, ScenarioBanner).
2. Extend `frontend/tests/e2e/*` with 2-3 Playwright specs against the new surfaces (existing e2e infra).

Risk: none — additive.

---

## Total estimate

| Phase | Scope | Effort |
| --- | --- | --- |
| A | Shell parity (UserMenu, SurfaceHeader) | 4–6 h |
| B | ApprovalCenter surface | 10–14 h |
| C | StrategyExplorer surface | 10–14 h |
| D | EvaluationHarness surface | 16–22 h |
| E | Scenario banner + primitive polish | 4–6 h |
| F | Storybook + e2e | 4 h |
| **Total** | **6 phases** | **48–66 h** |

Every phase can be independently committed, PR'd, and rolled back. No phase requires a backend change. No phase requires a deployment freeze — new surfaces appear at new routes without disturbing existing ones.

---

## Explicit non-changes

Preserved throughout:

- `frontend/src/index.js` entry point (unchanged).
- `os/routing/AppRouter.jsx` router shape (only additions to `routes.js`).
- Every existing `adapters/*.js` file (no adapter changes; reuse only).
- `os/auth/{LoginScreen,RequireAuth,authStore}.js*` (untouched).
- `os/tokens.css` (untouched — identical to prototype already).
- `os/primitives/*.jsx` (untouched — refactors deferred to Phase E).
- `frontend/Dockerfile` (unchanged).
- `docker-compose.prod.yml` (unchanged).
- Backend / API surface (Feature Freeze respected).

## Explicit anti-goals

Things I will NOT do:

- ❌ Deploy `prototype/` as its own artifact (prototype is Vite, frontend is CRA; would need a whole second build pipeline).
- ❌ Port `prototype/src/gallery/*` fixtures — `frontend/src/os/adapters/fixtures.js` already covers this need with real-shape data.
- ❌ Port `prototype/src/shell/InspectorSheet.tsx` — it's a design-validation tool, not a production feature.
- ❌ Port `prototype/src/shell/LeftRailStub.tsx` — the frontend `LeftRail` already handles the pre-auth chrome states.
- ❌ Rewrite any of the 24 frontend surfaces that already exist.

---

## Approval gate

Before implementing, please confirm the scope with a decision on each of these:

1. **Phase order**: A → B → C → D → E → F, or do you want a different priority?
2. **Phase D (EvaluationHarness)** is the largest single piece. Approve as one milestone, or split into two commits (data-viz first, run-controls second)?
3. **`Approvals.jsx` fate** after Phase B lands (delete the stub, or leave both routes?).
4. **`Strategies.jsx` fate** after Phase C lands (keep as list, keep as redirect, or delete?).
5. **Rollout cadence**: each phase merged + deployed independently, or batched into a single "OS refresh v1.1" deploy?

Once approved, I'll execute one phase per commit, with a validation report at the end of each phase before starting the next.
