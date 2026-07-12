# IMPLEMENTATION_SEQUENCE.md

**Audit type:** Read-only execution plan. The ordered, risk-assessed sequence for performing the UI restoration — each step independently shippable, testable, and reversible. **Nothing in this document is executed until the operator explicitly authorizes it.**
**Sources:** `UI_RESTORATION_MASTERPLAN.md`, `CAPABILITY_PLACEMENT_MATRIX.md`, `NAVIGATION_RECONSTRUCTION.md`, `OPERATOR_WORKFLOW_ALIGNMENT.md`, `MISSING_OR_HIDDEN_FEATURES.md` §5.
**Status:** Read-only. No code modified.
**Generated:** 2026-06-12

---

## 0. Hard gates (non-negotiable ordering)

```
GATE 0  Operator authorizes UI restoration       ──► Steps 1–5 may begin
GATE 1  Steps 1–4 verified (testing agent pass)  ──► Step 5 polish + Step 6 janitorial
GATE 2  Operator signs off restored UI           ──► nothing else happens automatically
GATE 3  Operator EXPLICITLY authorizes import    ──► 1-vCPU strategy import (separate plan:
                                                     POST_IMPORT_PIPELINE.md)
GATE 4  Post-import Stage 4 verified             ──► P2/P3 surfacing items (§4) on demand
FS VETO Factory Supervisor stack stays dormant until a separate explicit decree.
        No step below flips ANY feature flag.
```

Principles for every step:
- **Frontend-only.** Zero backend files touched; zero `.env` changes; zero flag flips.
- **Additive or compositional.** Existing components are re-used as-is; no component internals are edited (exceptions listed per-step).
- **Each step ends green.** Build passes, services healthy, smoke screenshot, then testing agent at the phase boundary.

---

## 1. Step-by-step sequence

### STEP 1 — Baseline freeze + safety net  *(~20 min · risk: none)*

| | |
|---|---|
| Work | Capture pre-change screenshots of all 17 tab landings; record current `modulesRegistry.js` section order in a scratch note; confirm `git log` checkpoint exists (platform auto-commits). |
| Files | none modified |
| Test | n/a (evidence collection) |
| Rollback | n/a |

### STEP 2 — Restore the stacked Dashboard  *(~2–3 h · risk: MEDIUM · closes regression R-1, the highest-value change)*

| | |
|---|---|
| Work | Create `components/DashboardComposite.jsx`: renders `MissionBriefing` on top, then the 8 legacy panels in locked order (GovernanceCard → UniverseGovernancePanel → StrategyIngestionCard → AutoSchedulerControl → OrchestratorPanel → MultiCycleRunner → AutoMutationRunner → StrategyDashboard). Swap `dashboard.sections[0].Component` from `MissionBriefing` to `DashboardComposite` in `modulesRegistry.js`. Tablet posture: fold panels 2–9 into accordions. Briefing posture: render MissionBriefing only (preserve read-only contract). |
| Files | NEW `DashboardComposite.jsx` · EDIT `modulesRegistry.js` (1 line) |
| Risks | ① Page weight — 9 lazy components on one scroll (StrategyDashboard ≈ 2.4k LOC). Mitigate: keep `React.lazy` + render below-fold panels inside `<Suspense>` with skeletons; consider intersection-observer mount for panels 6–9 only if profiling shows jank. ② Old panels fire ~8 API calls on mount — all already exist and are auth-gated; no backend change. ③ MissionBriefing deep-link buttons must keep working (they navigate away — fine). |
| Test | Screenshot Dashboard (workstation + tablet); verify all 9 `data-testid` panel roots render; verify no 401/console errors; verify briefing posture unchanged. |
| Rollback | Revert the 1-line registry swap → MissionBriefing-only Dashboard returns instantly. |

### STEP 3 — Mount Challenge Matching  *(~30 min · risk: LOW · closes regression R-2; prerequisite for good Stage-4 import UX)*

| | |
|---|---|
| Work | Add 1 section line to `propfirm` module per the recipe already locked in `MISSING_OR_HIDDEN_FEATURES.md` §2.1: `{ id: 'challenge', title: 'Challenge Matching', Component: ChallengeMatchingPanel, only: ['workstation','tablet'] }`. Add palette entry. |
| Files | EDIT `modulesRegistry.js` (1 line) · EDIT `CommandPalette.jsx` (1 entry) |
| Risks | None — component + 4 backend endpoints already live; this is the exact P1 recipe pre-approved in the parity audit. |
| Test | Navigate `propfirm#challenge`; panel renders; challenge-types endpoint returns data. |
| Rollback | Remove the line. |

### STEP 4 — Default-landing + friction fixes (batched)  *(~3–4 h · risk: LOW-MEDIUM · closes R-3, R-4, R-5)*

4a. **Execution Overview composite** — NEW thin `ExecutionOverview.jsx` (broker chips + paper KPI strip + runner status row + live summary card, read-only, reusing each panel's existing fetch endpoints); insert as `exec` section #1.
4b. **Reservation accordions** — wrap the 3 Explorer reservation cards + 1 Portfolio card in a collapsed `<details>`-style ASF accordion at the bottom of their modules (visual move only; components untouched).
4c. **BI5 readiness strip** — 1-line summary (symbols green/total, last sync) above `MarketDataWorkbench` sub-tabs, reading the existing `/api/diag/bi5/health`.
4d. **Admin readiness one-liner** — "Readiness: {status} →" link at top of `GovernanceAdminSuite`, reading existing readiness endpoint, deep-linking `governance#readiness`.

| | |
|---|---|
| Files | NEW `ExecutionOverview.jsx` + small `ReservationAccordion` wrapper · EDIT `modulesRegistry.js` (section regroup) · EDIT `MarketDataWorkbench.jsx` (strip) · EDIT `GovernanceAdminSuite.jsx` (one-liner) |
| Risks | ① 4a duplicates fetches if operator opens Overview then drills into Paper — acceptable (read-only GETs). ② 4b must not change reservation card internals (M2 visual lock) — wrapper only. |
| Test | One smoke screenshot per changed tab; then **testing agent run covering Steps 2–4** (frontend flows: dashboard stack, challenge panel, exec overview, accordions, strips). |
| Rollback | Each sub-item independently revertible (registry lines / additive JSX blocks). |

### STEP 5 — Nav behaviour polish (1-vCPU a11y contract)  *(~45 min · risk: LOW · closes R-6)*

| | |
|---|---|
| Work | Port from old `App.js` LL 126–145 into `TopTabBar.jsx`: vertical-wheel→horizontal-scroll hijack on the tab strip + per-tab refs with `scrollIntoView({inline:'center'})` on active change. |
| Files | EDIT `TopTabBar.jsx` |
| Risks | Wheel hijack must not capture wheel events outside the strip (guard exactly as the old code did). |
| Test | Screenshot at narrow viewport; verify Admin tab scrolls into view when activated. |
| Rollback | Remove the two hooks. |

### STEP 6 — Janitorial: orphan retirement  *(~1 h + 2 h rehousing-audit deferred · risk: LOW · explicitly authorized deletions only)*

6a. Visual parity check `Optimization.js` (506 LOC) vs mounted `OptimizationPanel.js` — present findings to operator, then delete (or quarantine to `_inventory/`).
6b. Delete clear-replacement orphans: `NavMoreMenu.js`, `DensityToggle.js`, `TraderModeButton.js`, `phase9/*` (5 files).
6c. **Defer** `ArchitectDashboard.jsx` — it holds the only roadmap-aligned orphan IP (9 FS cards). Retire only after its children are rehoused (P2 item §4 below, FS-veto-gated).

| | |
|---|---|
| Files | DELETE 9 files (after 6a sign-off) |
| Risks | None at runtime (zero importers, verified twice). Build is the only proof needed. |
| Test | `yarn build` green; full-tab smoke pass. |
| Rollback | Platform git history (or `_inventory/` quarantine). |

### STEP 7 — Verification + sign-off package  *(~1 h)*

- Full testing-agent regression across all 17 tab landings + drawers + palette.
- Post-change screenshot set mirroring Step 1 baseline.
- Update `OPERATOR_MANUAL.md` (Dashboard stack, Challenge Matching, Deployment-is-a-rail-label note) and `PRD.md` changelog.
- **STOP at GATE 2.** Present to operator. No import. No flags.

---

## 2. Effort & risk roll-up

| Step | Effort | Risk | Regression closed | Gate |
|---|---|---|---|---|
| 1 Baseline | 20 min | — | — | GATE 0 opens |
| 2 Dashboard stack | 2–3 h | MEDIUM | R-1 (HIGH) | |
| 3 Challenge Matching | 30 min | LOW | R-2 | |
| 4 Landings + friction | 3–4 h | LOW-MED | R-3 R-4 R-5 | testing agent |
| 5 Nav polish | 45 min | LOW | R-6 | |
| 6 Janitorial | 1 h | LOW | — | GATE 1 |
| 7 Verify + docs | 1 h | — | — | GATE 2 |
| **Total** | **~9–11 h** | | all 6 regressions | |

Recommended batching: Steps 2+3 in one session (test together), Steps 4+5 in the next, Step 6+7 last.

---

## 3. What this sequence deliberately does NOT do

| Excluded | Why |
|---|---|
| 1-vCPU strategy import | GATE 3 — separate explicit authorization; plan lives in `POST_IMPORT_PIPELINE.md` |
| Any feature-flag flip | FS hard veto + code-freeze discipline; all 89 flags untouched |
| Factory Supervisor / Architect / Auto Learning mounts | Veto-gated P2/P3 (see §4) |
| Notification Center rewiring | Requires `ENABLE_NOTIFICATION_CENTER` — flag-gated |
| Backend changes of any kind | Restoration is 100% frontend composition |
| Light theme restoration | M0 dark-lock honoured (masterplan §5) |
| Reservation card redesign | M2 visual locks honoured — cards move, never change |

---

## 4. Post-restoration backlog (kept for visibility; each item awaits its own trigger)

| Item | Trigger | Effort | Ref |
|---|---|---|---|
| P0 — 1-vCPU strategy import (6 stages) | GATE 3 operator decree | per import plan | `POST_IMPORT_PIPELINE.md` |
| P1 — BI5 R2 (auto-cert sweep) + `diag#bi5-cert` panel | roadmap P0 authorization | backend + panel | PRD §6 |
| P1 — BI5 R3 (tick replay default) | roadmap P0 authorization | backend toggle | PRD §6 |
| P2 — "Backfill Now" button (Market Data) | bundled with next frontend pass | 30 min | `MISSING_FROM_UI.md` §2.11 |
| P2 — DSR Audit History sub-tab | anytime (additive) | 1 h | `MISSING_FROM_UI.md` §2.10 |
| P2 — Activation Timeline panel (`governance#activation`) | anytime (additive) | 1 h | catalog #94 |
| P2 — Widening History expander (Admin Flags) | anytime (additive) | 1 h | catalog #89 |
| P2 — FS panel in Monitoring Cluster + `ai#architect` rehousing | **FS veto lift only** | 30 min + 2 h | `MISSING_OR_HIDDEN_FEATURES.md` §2.2 / §2.5 |
| P3 — Auto Learning standalone at `ai#learning` | `FS_ENABLE_AUTO_LEARNING=true` | 2 h | §2.3 |
| P3 — Retire `ArchitectDashboard.jsx` shell | after children rehoused | 15 min | catalog #151 |
| P3 — Master Bot secondary Cluster mount | operator request | 30 min | catalog row |
| Future — `exec#runners` Runner Registry panel | multi-account go-live | 2–3 h | catalog #56 |
| Future — cTrader/VPS/telemetry chip activation | M2 reservations | per integration | masterplan §4 |

---

## 5. State of this document

* Read-only plan. **Awaiting GATE 0 operator authorization — no step has been executed.**
* Completes the 5-document planning set: `UI_RESTORATION_MASTERPLAN.md` · `CAPABILITY_PLACEMENT_MATRIX.md` · `NAVIGATION_RECONSTRUCTION.md` · `OPERATOR_WORKFLOW_ALIGNMENT.md` · `IMPLEMENTATION_SEQUENCE.md`.
* No code modified. No surfaces mounted. No flags flipped. No import performed.

**End of report.**
