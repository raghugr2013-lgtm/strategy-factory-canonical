# POST_HYDRATION_UI_RECOVERY.md

**Plan type:** Post-hydration UI polish backlog.
**Trigger:** Runs ONLY after the post-hydration validation report is green.
**Status:** Plan only. Operator authorisation required before each block.

This is the prioritised follow-up list derived from `LEGACY_UI_RECONCILIATION_AUDIT.md` §6.1 and `LEGACY_TO_NEW_MAPPING.md` §6. **None of these block hydration.** All are frontend-only changes (no backend, no engine, no schema).

---

## P1 — Operator-critical legacy workflow restoration

### P1.1 — Mount Workspace Composite (legacy MORE-1 unified lab surface)

**Why:** Legacy operator daily flow was "open Workspace → generate → see Backtest + Description + cBot + Optim + Validate + Comparison all on one screen." The new shell splits this across 6 separate `/c/lab/*` sections. Daily-driver muscle memory is gone.

**Scope:** Add ONE new section to `modulesRegistry.js` that composites the existing 8 components in a 3-col / 9-col grid (matching legacy `App.js` LL 320–365).

**Implementation:**

1. Create `frontend/src/components/WorkspaceComposite.jsx` — pure layout file:
   * Left column (`lg:col-span-3`): `<StrategyPanel />` + `<StrategyAnalysis />`
   * Right column (`lg:col-span-9`):
     * `<BacktestPanel />`
     * `<StrategyDescription />` (if strategy)
     * `<CbotPanel />`
     * `<OptimizationPanel /> | <ValidationPanel />` (side-by-side grid)
     * `<StrategyComparison />` (when `rankedStrategies.length >= 1`)
   * Lift the legacy `useState` for `strategy / backtestResults / currentPair / currentTimeframe / rankedStrategies` to component scope.
2. Add new section to MODULES.lab.sections in `frontend/src/command/shell/modulesRegistry.js`:
   ```js
   { id: 'workspace', label: 'Workspace', component: 'WorkspaceComposite' }
   ```
3. Optionally surface it as a quick deep-link button in MissionBriefing.

**Files touched:** 2 (`WorkspaceComposite.jsx` new + `modulesRegistry.js` edit).
**Backend impact:** ZERO.
**Effort:** ~2 h including manual operator smoke.
**Acceptance:**
* Navigating to `/c/lab/workspace` renders the 8 components in one viewport.
* Generating a strategy in `StrategyPanel` populates the other panels.
* No console errors.

---

### P1.2 — Restore `Library (N)` count badge in TopTabBar

**Why:** Legacy MORE-tab label was `Library (${savedStrategies.length})` — the count was a constant operator confidence signal.

**Implementation:**
1. In `frontend/src/command/shell/TopTabBar.jsx`, find the `saved` / Library tab entry.
2. Subscribe to `savedStrategiesStore` (or call `useSavedStrategiesCount()` hook).
3. Append `(${count})` to the label when `count > 0`.

**Files touched:** 1 (`TopTabBar.jsx`).
**Backend impact:** ZERO.
**Effort:** < 30 min.
**Acceptance:**
* Tab label shows `Library (12)` (or whatever current count) when navigating to `/c/explorer/saved`.
* Count updates after saving / deleting a strategy.

---

### P1.3 — Verify Auto Factory workflow end-to-end

**Why:** Auto Factory was a CORE-tab in legacy and is the production strategy-generation engine. Confirm the workflow still works after hydration.

**Scope (verification only — no code change unless a bug surfaces):**
1. Navigate `/c/mutate/factory-55`. Trigger one small Auto Factory run (3 strategies, EURUSD, M15, 1 cycle).
2. Confirm strategies appear in `/c/explorer/explorer`.
3. Confirm Phase 55 evolution timeline renders.
4. Confirm `auto_factory_phase55_runs` collection in Mongo has 1 new row.
5. Spot-check `engines/auto_factory_phase55.py` log lines in `/var/log/supervisor/backend.*.log`.

**Files touched:** 0 (verification only).
**Effort:** ~30 min.
**Acceptance:**
* Strategies generated end-to-end.
* No 500 errors.
* No frontend regression vs legacy behaviour.

---

## P2 — Discoverability fixes

### P2.1 — Mount Challenge Matching surface at `propfirm/challenge`

**Why:** Legacy embedded Challenge Profiles inside Prop Firms. Current shell parks `ChallengeMatchingPanel` at `OperatorParityPanels.jsx` (Governance Admin Power-User sub-tab) — far from operator expectations.

**Implementation:**
1. Import `ChallengeMatchingPanel` into `modulesRegistry.js`.
2. Add to `MODULES.propfirm.sections`:
   ```js
   { id: 'challenge', label: 'Challenge', component: 'ChallengeMatchingPanel' }
   ```
3. Visual approval `01_TAB_ROSTER.md` row MORE-3 already plans this.

**Files touched:** 1 (`modulesRegistry.js`).
**Backend impact:** ZERO (endpoint `/api/challenge-matching/*` already live).
**Effort:** ~30 min.
**Acceptance:**
* `/c/propfirm/challenge` renders ChallengeMatchingPanel.
* Endpoint introspection works.

---

### P2.2 — Review ExecutionDashboard placement (wire or retire)

**Why:** `phase9/ExecutionDashboard` (legacy CORE-2 "Execution" 3-step Generate→Allocate→Execute strip) is NOT imported by `modulesRegistry.js`. Either:
* **(a) Wire** it as `dashboard/exec-strip` next to MissionBriefing, OR
* **(b) Retire** it formally — visual approval implies Mission Briefing supersedes.

**Recommended evidence-gathering (no code change yet):**
1. Operator inspects MissionBriefing post-hydration — does it cover the same operator intent?
2. If yes → mark ExecutionDashboard formally retired in PRD and consider deleting `frontend/src/components/phase9/*` in a future cleanup pass.
3. If no → wire it.

**If wiring chosen, implementation:**
1. Add `{ id: 'exec-strip', label: 'Quick Execute', component: 'ExecutionDashboard' }` to `MODULES.dashboard.sections`.
2. Acceptance: `/c/dashboard/exec-strip` renders the 3-step strip.

**Files touched:** 1 (`modulesRegistry.js`) if wiring; 0 if retiring.
**Effort:** ~30 min wiring, or 5 min documentation if retiring.

---

### P2.3 — Review Optimization placement (wire or leave hidden)

**Why:** Legacy MORE-5 standalone `Optimization` page (Phase 8 Strategy Refinement) — `Optimization.js` exists in repo but no MODULES section imports it.

**Recommended evidence-gathering:**
1. Operator confirms per-strategy `lab/optim` covers the legacy use case.
2. If yes → mark standalone Optimization deprecated in PRD.
3. If no → wire at `lab/optim-standalone`.

**If wiring chosen, implementation:**
1. Add `{ id: 'optim-standalone', label: 'Standalone Optimizer', component: 'Optimization' }` to `MODULES.lab.sections`.

**Files touched:** 1 (`modulesRegistry.js`) if wiring; 0 if retiring.
**Effort:** ~30 min wiring, or 5 min documentation if retiring.

---

## P3 — Optional surface promotions

### P3.1 — Review Master Bot visibility and navigation

**Why:** Master Bot is a critical subsystem post-1-vCPU; today it lives at `/c/mutate/master-bot` (Dashboard) + `/c/mutate/master-bot-compile` (Compile). Visual approval `04_COMPONENT_REHOUSING_MATRIX.md` row 19 footnote recommends ALSO surfacing `MasterBotDashboard` as a Cluster sub-tab inside `MonitoringSuite`.

**Decision required:** Single home (current) OR dual home (Mutation + Monitoring Cluster)?

**If dual home chosen, implementation:**
1. Inside `MonitoringSuite.jsx`, add a Cluster sub-tab that hosts `MasterBotDashboard` (already imported elsewhere).
2. No `modulesRegistry.js` change needed.

**Files touched:** 1 (`MonitoringSuite.jsx`).
**Effort:** ~30 min.

---

### P3.2 — Review Factory Supervisor visibility

**Why:** Factory Supervisor is currently dormant (`ENABLE_FACTORY_SUPERVISOR=false`). UI exists at `OperatorParityPanels.jsx::FactorySupervisorPanel` (Cluster sub-tab) and `ArchitectDashboard.jsx` (palette only). When the flag activates, the operator will need primary-nav discoverability.

**Decision required:** Status dot in LeftRail when flag ON? Dedicated tab? Inspector status chip?

**Recommended (when activated):**
1. Add a status dot to LeftRail "Diagnostics" glyph (green/amber/red driven by `/api/factory-supervisor/heartbeat`).
2. Confirm Cluster sub-tab inside `MonitoringSuite` renders `FactorySupervisorPanel` (already wired).
3. Keep `ArchitectDashboard` as the deep-dive surface, reachable via palette + Cluster footer.

**Files touched (when activated):** 2 (`LeftRail.jsx` + `MonitoringSuite.jsx`).
**Effort:** ~1 h.

---

### P3.3 — Review Auto Learning visibility

**Why:** Auto Learning Infrastructure is currently dormant (`FS_ENABLE_AUTO_LEARNING=false`, `FS_ENABLE_AUTO_LEARNING_LOOP` hard-vetoed). No dedicated panel today; insights would surface via Recommendation Engine + Architect Dashboard when ON.

**Decision required:** Create dedicated `ai/learning` section vs leave embedded inside Architect / Copilot?

**Recommended (when activated):**
1. Create `frontend/src/components/AutoLearningPanel.jsx` reading from `/api/factory-supervisor/auto-learning/insights`.
2. Add to `MODULES.ai.sections`:
   ```js
   { id: 'learning', label: 'Auto Learning', component: 'AutoLearningPanel' }
   ```

**Files touched (when activated):** 2 (new panel + `modulesRegistry.js`).
**Effort:** ~2 h.

---

## Optional later — P3 Bonus

### P3.4 — Pass Probability lineage view

**Why:** Pass Probability is computed per strategy but no dedicated explanation surface exists. When `ENABLE_CALIBRATION=true` activates, the calibration table + per-decile bins become consumable.

**Implementation (when activated):**
1. Create `frontend/src/components/PassProbabilityLineagePanel.jsx` reading from `/api/latent/calibration` + per-strategy `/api/strategies/<id>` (already returns the value).
2. Add to `MODULES.lab.sections`:
   ```js
   { id: 'pass-probability', label: 'Pass Probability', component: 'PassProbabilityLineagePanel' }
   ```

**Effort:** ~2 h.

---

## Execution discipline

| Rule | Why |
|---|---|
| All P1/P2/P3 changes are FRONTEND-ONLY. | Hydration delivers a working backend; backend stays stable. |
| Each change touches at most 2 files. | Low blast radius; trivial rollback (`git diff` reverse). |
| Each change includes a manual smoke + console-error check. | No regression. |
| `testing_agent_v3` invoked once after P1.1 + P1.2 land. | Validate Workspace + count badge end-to-end. |
| No new endpoints. No new env vars. No schema changes. | Strict scope. |
| Operator approval required before each block (P1 → P2 → P3). | Operator stays in control. |

---

## Estimated total effort

| Block | Effort | Cumulative |
|---|---|---|
| P1 (3 items) | ~3 h | 3 h |
| P2 (3 items, depending on operator decisions) | ~1.5 h | 4.5 h |
| P3 (3 items, conditional on flags activating) | ~3.5 h (when triggered) | 8 h |
| **TOTAL non-flag-gated work** | **~4.5 h** | — |
| **TOTAL including conditional P3** | **~8 h** | — |

All numbers exclude operator review time between blocks.

---

## Sequencing relative to hydration

1. **Hydration EXECUTE** → 12–20 min
2. **Boot validation** → 5–8 min (covered by `POST_HYDRATION_VALIDATION_REPORT.md`)
3. **Operator review of validation report** → operator decision
4. **P1 block** → ~3 h on operator authorisation
5. **`testing_agent_v3` invocation** → after P1.1 + P1.2 land
6. **P2 block** → operator decisions + ~1.5 h
7. **P3 block** → only when associated flags activate

Until hydration validation is green and operator approves the P1 block, **no new feature development is permitted** — per operator directive.
