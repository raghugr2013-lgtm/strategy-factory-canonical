# MISSING_OR_HIDDEN_FEATURES.md

**Audit type:** Companion to `ROADMAP_PARITY_REPORT.md` — exhaustive list of every Class **C** (implemented but hidden) and Class **D** (placeholder only) surface, plus orphan source files that are physically present in the repo but not referenced by `modulesRegistry.js`.
**Status:** Read-only. No code modified. No surfaces mounted.
**Audience:** Operator (pre-import gate review).
**Sources cross-referenced:**

1. `ROADMAP_PARITY_REPORT.md` §2.7, §2.14, §2.15, §2.16
2. `/app/frontend/src/command/shell/modulesRegistry.js` (1–362)
3. `/app/frontend/src/components/OperatorParityPanels.jsx` (FactorySupervisorPanel @ L20, ChallengeMatchingPanel @ L196)
4. `/app/frontend/src/components/MonitoringSuite.jsx` L113 (Cluster sub-tab mounts `ScalingPanel`, not `FactorySupervisorPanel`)
5. `/app/frontend/src/components/ArchitectDashboard.jsx` (AutoLearningPanel @ L689, ArchitectDashboard @ L820)
6. `/app/frontend/src/components/Optimization.js` (506 LOC, orphan)
7. `/app/frontend/src/components/phase9/ExecutionDashboard.js` (74 LOC, orphan)
8. `/app/backend/.env` (feature-flag posture)
9. `/app/backend/engines/factory_supervisor/*` (24 modules; dormant flag-gated)

---

## 1. Master inventory (sorted by class, then priority)

| # | Feature / Surface | Class | Location | Reason hidden / placeholder | Recovery effort | Priority | Import blocking? | Recommended action |
|---|---|---|---|---|---|---|---|---|
| 1 | **Challenge Matching primary nav** | **C** | Component: `components/OperatorParityPanels.jsx::ChallengeMatchingPanel` (L196). Lazy import: `modulesRegistry.js` L131. **No section references it.** | Visual approval (`01_TAB_ROSTER.md` MORE-3) called for `propfirm/challenge` sub-tab; current code embeds challenge endpoints inside `FirmMatchPanel` (`propfirm/match`) and leaves the dedicated panel orphaned. Comment at L257–259 explicitly states it is "reachable from `governance/admin` Power-User sub-tab for raw endpoint introspection." | ~30 min (add a 1-line section entry in `propfirm` module) | **P1** | **No** — `/api/challenge/*` + `/api/challenge-matching/*` endpoints are live (used by post-import Stage 4 directly via engine, not via UI) | **Expose** post-import (P1 backlog) |
| 2 | **Factory Supervisor primary nav** | **C** | Component: `components/OperatorParityPanels.jsx::FactorySupervisorPanel` (L20). Lazy import: `modulesRegistry.js` L122. **No section references it.** Engines: `backend/engines/factory_supervisor/*` (24 modules, ~6,500 LOC). | `04_COMPONENT_REHOUSING_MATRIX.md` planned Cluster sub-tab inside MonitoringSuite. `MonitoringSuite.jsx` L113 currently mounts `ScalingPanel` there, not `FactorySupervisorPanel`. Backend stack is gated dormant via `ENABLE_FACTORY_SUPERVISOR=false` + 12 `FS_ENABLE_*` flags OFF (operator hard veto). | ~30 min (swap or stack components in `MonitoringSuite.jsx` Cluster tab) | **P2** | **No** — FS stack is intentionally dormant by operator directive; post-import pipeline does not consume any FS engine | **Keep hidden** until operator explicitly authorises FS activation (post-stabilisation roadmap) |
| 3 | **Auto Learning primary nav** | **C** | Component: `components/ArchitectDashboard.jsx::AutoLearningPanel` (L689), parent `ArchitectDashboard` (L820). **Neither imported anywhere in `command/`.** Engine: `engines/factory_supervisor/auto_learning_aggregator.py`. | Component nested inside `ArchitectDashboard`, which itself is an orphan (no import statements outside the file). Backend gated dormant via `FS_ENABLE_AUTO_LEARNING=false` + `FS_ENABLE_AUTO_LEARNING_LOOP=false` (operator hard veto in FS-P1.4). | ~2 h (add a dedicated `ai/learning` section + lift `AutoLearningPanel` out of `ArchitectDashboard`, OR mount `ArchitectDashboard` as-is in `governance/admin` Power-User sub-tab) | **P3** | **No** — not consumed by the 6-stage post-import pipeline | **Keep hidden** until `FS_ENABLE_AUTO_LEARNING` activates (P3 backlog) |
| 4 | **Deployment Center (standalone)** | **D** | Label only: `LifecycleRail.jsx` L31 — `{ n: 10, label: 'Deployment', tabId: 'monitoring' }`. No dedicated `/api/deployment/*` router. | Function is absorbed by `diag/monitoring` (runtime/cluster) + `governance/readiness` (gate). Visual approval never defined a standalone Deployment Center; only a rail stage. | N/A — by design | **P3** | **No** — covered by Monitoring + Governance · Readiness | **Keep hidden** (intentional architecture decision; document in OPERATOR_MANUAL.md) |
| 5 | **ArchitectDashboard parent** | **C / orphan** | `components/ArchitectDashboard.jsx` (940 LOC). Contains `AutoLearningPanel` + 4 other operator-facing panels (advisor stream, recommendation feed, copilot ops, fleet registry view). **No import statements in `command/` or anywhere else.** | Pre-RC1 parity restoration split its constituent surfaces across `governance/admin` (Flag Gov · Realism · Tuning) and `diag/monitoring`. Parent shell never re-mounted. | ~2 h (audit which sub-panels are not yet rehoused elsewhere; either lift them or mount `ArchitectDashboard` as a Power-User section under `governance/admin`) | **P3** | **No** | **Keep hidden** until P3 review; some children may already be duplicated in other surfaces (audit needed) |
| 6 | **`Optimization.js` (legacy)** | **C / orphan** | `components/Optimization.js` (506 LOC). **Not imported anywhere.** | Superseded by `OptimizationPanel.jsx` which IS mounted at `lab/optim` (L182, registry; L69, TopTabBar). The legacy file was preserved during hydration but is dead code. | N/A | **P2** | **No** — `OptimizationPanel` covers the surface | **Retire** (delete or quarantine to `_inventory/`) after operator review |
| 7 | **`phase9/ExecutionDashboard.js` (legacy)** | **C / orphan** | `components/phase9/ExecutionDashboard.js` (74 LOC). **Not imported anywhere.** | Phase 9 prototype; superseded by the current `exec` module (Brokers · Paper · Runner · Live). | N/A | **P2** | **No** — `exec/*` sections cover the surface | **Retire** (delete or quarantine to `_inventory/`) after operator review |

**Total hidden/orphan surfaces:** 7 (3 active-but-unmounted, 1 placeholder, 3 orphan files)
**Class breakdown:** 5 × C · 1 × D · 1 × orphan-only (Optimization.js + phase9 grouped as "orphan files")
**Items blocking import:** **0**

---

## 2. Per-item deep dive

### 2.1 Challenge Matching primary nav (C — P1)

**What it is:**
A read-only operator panel that lets the operator request `POST /api/strategies/{hash}/match-challenges` and inspect the returned challenge-template scores. Companion to the `FirmMatchPanel` (which scores a strategy against firms in general); this panel narrows the analysis to specific challenge templates within those firms.

**Why it matters:**
Stage 4 of the post-import pipeline (`Re-Match`) writes `firm_match_imported` rows that carry `challenge_template` per match. Today the operator can see firm-level matches in `propfirm/match` but cannot drill into the challenge-template detail without using the raw `/api/challenge-matching/*` endpoints. Exposing the panel turns a backend-only flow into a discoverable operator workflow.

**Why it's currently hidden:**
The `01_TAB_ROSTER.md` row MORE-3 planned a `propfirm/challenge` sub-tab. The current `propfirm` module only declares two sections (`admin` + `match`). The lazy-import statement at `modulesRegistry.js` L131 was preserved during hydration but no section entry was added — the comment at L257–259 documents the conscious decision to defer the surface.

**Backend status:**
- `POST /api/strategies/{hash}/match-challenges` — live (`api/challenge_matching.py` L46)
- `GET /api/strategies/{hash}/challenge-match` — live (L60)
- `GET /api/challenge-matching/challenge-types` — live (L33)
- `GET /api/challenge-matching/challenge-types/by-firm` — live (L39)
- `engines/challenge_matching_engine.py` — live, consumed by Stage 4

**Exposure recipe (when authorised):**
```js
// In modulesRegistry.js, propfirm module sections array:
{ id: 'challenge', title: 'Challenge Matching', Component: ChallengeMatchingPanel, only: ['workstation', 'tablet'] },
```
Add `{ id: 'challenge-matching', label: 'Challenge Matching', module: 'propfirm', section: 'challenge' }` to `TopTabBar.jsx` MORE-tabs if a top-level chip is desired.

**Import blocking?** No. Stage 4 calls the engine directly; the panel is purely an operator-facing observability surface.

**Recommended action:** **Expose post-import** (P1). Add the section as soon as the post-import pipeline is authorised so the operator can drill into Stage 4 results immediately.

---

### 2.2 Factory Supervisor primary nav (C — P2)

**What it is:**
Operator-facing dashboard for the Factory Supervisor stack — the meta-orchestrator that schedules workloads across the worker pool (`worker_runtime.py` + `worker_scheduler.py`), routes work through policy (`routing_policy.py`), surfaces eligibility signals (`eligibility_signals.py`), drives the Copilot advisory stream (`copilot_*.py`), and emits supervisor events (`supervisor_events.py` + `supervisor_heartbeat.py`).

**Why it matters:**
On a 12-vCPU pod with `ENABLE_FACTORY_SUPERVISOR=true`, the FS stack is the difference between a single-threaded loop and a parallel, advisor-guided factory. It is roadmap-critical for **post-stabilisation** workloads (Phase 13 Dossier Engine + Phase 14 Valuation) but not for the immediate 1-vCPU import.

**Why it's currently hidden:**
- Backend: `ENABLE_FACTORY_SUPERVISOR` is NOT set in `backend/.env` (defaults false). 12 `FS_ENABLE_*` flags all OFF.
- Frontend: `FactorySupervisorPanel` is lazy-imported (`modulesRegistry.js` L122) but the Cluster sub-tab in `MonitoringSuite.jsx` L113 mounts `ScalingPanel` (the lighter-weight CPU-pool view). The panel itself is reachable only via direct component import.

**Operator veto status:**
The dormancy is per operator directive (`FS-P1.4` — explicit hard veto across all FS engines). This is **not** an oversight; the operator pinned FS dormancy until the 1-vCPU stabilisation + import are complete.

**Exposure recipe (when authorised):**
```jsx
// In MonitoringSuite.jsx, replace L113:
{tab === 'cluster' && (
  <>
    <ScalingPanel />
    <FactorySupervisorPanel />
  </>
)}
```
Then flip `ENABLE_FACTORY_SUPERVISOR=true` in `backend/.env` and the relevant `FS_ENABLE_*` flags for the desired subsystems (worker pool, copilot, recommendation engine).

**Import blocking?** No. The 6-stage post-import pipeline uses canonical engines (profiler, ranker, matcher, portfolio builder, master bot) and does NOT call any factory-supervisor engine.

**Recommended action:** **Keep hidden** until operator explicitly authorises FS activation (P2 — post 24h soak per PRD §6 P1 backlog).

---

### 2.3 Auto Learning primary nav (C — P3)

**What it is:**
A continuous-learning feedback loop that watches strategy outcomes, mutation results, and validator verdicts, then synthesises improvement recommendations for the operator. Powered by `engines/factory_supervisor/auto_learning.py` + `auto_learning_aggregator.py`.

**Why it matters:**
Phase 14 Valuation Engine ingests Auto Learning signals to compute the **Trust Score** longevity multiplier (PRD §4 — DSR-1 work-stream). Once `FS_ENABLE_AUTO_LEARNING` activates, the loop accumulates evidence that the dossier engine can quote.

**Why it's currently hidden:**
- Frontend: `AutoLearningPanel` is defined inline inside `ArchitectDashboard.jsx` (L689) but `ArchitectDashboard.jsx` itself is never imported (grep confirms 0 importers in `command/` or anywhere).
- Backend: `FS_ENABLE_AUTO_LEARNING=false` + `FS_ENABLE_AUTO_LEARNING_LOOP=false` — both behind the FS hard veto.

**Exposure recipe (when authorised):**
1. Lift `AutoLearningPanel` out of `ArchitectDashboard.jsx` into its own file `components/AutoLearningPanel.jsx`.
2. Add a section under the `ai` module: `{ id: 'learning', title: 'Auto Learning', Component: AutoLearningPanel, only: ['workstation'] }`.
3. Flip the two `FS_ENABLE_AUTO_LEARNING*` flags.

**Import blocking?** No. The post-import pipeline does not consume Auto Learning signals (Stage 2 uses `pass_probability.py` directly without the learning loop).

**Recommended action:** **Keep hidden** until `FS_ENABLE_AUTO_LEARNING` activates (P3 — concurrent with Phase 13 Dossier Engine work).

---

### 2.4 Deployment Center standalone (D — P3)

**What it is:**
A name on the LifecycleRail (`LifecycleRail.jsx` L31, stage 10) — operator clicks "Deployment" and the rail navigates to the `monitoring` tab.

**Why it's a placeholder:**
The function "deploy a strategy / portfolio / master-bot" is intentionally distributed:
- **Promotion** — Explorer / Portfolio Builder / Master Bot dashboards each have their own promote-to-active button (per `POST_IMPORT_PIPELINE.md` §8 deployment gate).
- **Readiness gate** — `governance/readiness` (`ReadinessPanel.jsx`) shows the green-light status.
- **Observability** — `diag/monitoring` (`MonitoringSuite.jsx`) shows the runtime fleet.

Consolidating these into a single "Deployment Center" was considered (visual approval package §10 future phases) but rejected: the surfaces are already operator-discoverable in their respective modules, and a fourth merged surface would duplicate state.

**Why it persists as a rail label:**
The LifecycleRail is a 10-step **journey** indicator (not a navigation menu in the strict sense). Keeping "Deployment" as stage 10 — even though clicking it lands on Monitoring — preserves the conceptual model that "deploy" is the final stage and provides a single-click affordance from any screen.

**Import blocking?** No. Stage 6 of the post-import pipeline does not deploy — it only **proposes** Master Bot candidates that the operator manually compiles + deploys via the existing Master Bot dashboard.

**Recommended action:** **Keep hidden** (intentional). Document the rail-label-only behaviour in `OPERATOR_MANUAL.md` to forestall operator confusion.

---

### 2.5 ArchitectDashboard parent (C — orphan — P3)

**What it is:**
A 940-LOC composite that bundles ~5 operator-facing panels — Architect Advisor stream, Recommendation Feed, Copilot Operational view, Fleet Registry view, and the embedded `AutoLearningPanel`. Built during the pre-RC1 advisor work-stream.

**Why it's currently hidden:**
Pre-RC1 parity restoration split the panel's children across:
- `governance/admin` (Flag Governance · Execution Realism · Phase 12 Tuning — via `GovernanceAdminSuite`)
- `diag/monitoring` (Runtime · Soak · Compute · Cluster — via `MonitoringSuite`)

Not all children were rehoused; the advisor stream and recommendation feed remain inside `ArchitectDashboard.jsx` with no external mount.

**Audit needed:**
| Child panel inside ArchitectDashboard | Re-housed? | Where |
|---|---|---|
| Architect Advisor stream | ❌ | Still inside ArchitectDashboard |
| Recommendation Feed | ❌ | Still inside ArchitectDashboard |
| Copilot Operational view | ❌ | Still inside ArchitectDashboard |
| Fleet Registry view | ❌ | Still inside ArchitectDashboard |
| AutoLearningPanel | ❌ | Still inside ArchitectDashboard (see §2.3) |

**Exposure recipe (when authorised):**
Two options:
- **Option A** (lift): create 5 standalone components, mount each in the appropriate module.
- **Option B** (mount as-is): add a Power-User section under `governance/admin` that mounts `ArchitectDashboard` whole.

**Import blocking?** No.

**Recommended action:** **Audit + Keep hidden** until P3. Confirm which child panels are already duplicated elsewhere (some may be — e.g. Fleet Registry overlap with Monitoring Cluster sub-tab) and retire the duplicates.

---

### 2.6 `Optimization.js` legacy (C / orphan — P2)

**What it is:**
A 506-LOC legacy optimization panel from a pre-RC1 iteration. Superseded by `OptimizationPanel.jsx` (mounted at `lab/optim`).

**Why it's orphan:**
Hydration preserved the file but no section references it. `grep -r "from.*Optimization'" /app/frontend/src` returns zero hits.

**Import blocking?** No.

**Recommended action:** **Retire**. After operator review, either delete the file or move to `_inventory/` to keep the working tree clean.

---

### 2.7 `phase9/ExecutionDashboard.js` legacy (C / orphan — P2)

**What it is:**
A 74-LOC Phase 9 prototype execution dashboard. Superseded by the current `exec` module sections (Brokers · Paper · Runner · Live).

**Why it's orphan:**
Same as §2.6 — preserved by hydration, no importers.

**Import blocking?** No.

**Recommended action:** **Retire**. Delete or quarantine.

---

## 3. Cross-source consistency check

| Cross-reference | Status |
|---|---|
| `ROADMAP_PARITY_REPORT.md` §2.7 (Deployment Center D) | ✅ matches §2.4 here |
| `ROADMAP_PARITY_REPORT.md` §2.14 (Challenge Matching C) | ✅ matches §2.1 here |
| `ROADMAP_PARITY_REPORT.md` §2.15 (Factory Supervisor C) | ✅ matches §2.2 here |
| `ROADMAP_PARITY_REPORT.md` §2.16 (Auto Learning C) | ✅ matches §2.3 here |
| Orphan files (Optimization.js, phase9/ExecutionDashboard.js, ArchitectDashboard.jsx) | ✅ newly catalogued here (not in parity report — operator's "review ExecutionDashboard placement" question from handoff is answered by §2.7) |

---

## 4. Pre-import verdict

**0 of 7 hidden/orphan surfaces gate the 1-vCPU strategy import or the 6-stage post-import pipeline.**

| Item | Class | Import blocking? |
|---|---|---|
| Challenge Matching primary nav | C | No (engine is live) |
| Factory Supervisor primary nav | C | No (intentionally dormant) |
| Auto Learning primary nav | C | No (intentionally dormant) |
| Deployment Center standalone | D | No (function distributed) |
| ArchitectDashboard parent | C / orphan | No |
| `Optimization.js` legacy | C / orphan | No (replacement mounted) |
| `phase9/ExecutionDashboard.js` legacy | C / orphan | No (replacement mounted) |

**Recommendation:** import is unblocked. The 7 items above are queued for post-import work according to the priority column. None of them is a regression; each is either:
- a deliberate visibility choice pinned to a future roadmap phase, OR
- a hydration artefact (orphan file) that will be retired during a janitorial pass.

---

## 5. Post-import recovery sequence (proposed — awaits operator authorisation)

| Order | Item | Effort | When |
|---|---|---|---|
| 1 | Expose Challenge Matching at `propfirm/challenge` | ~30 min | Immediately after Stage 4 (Re-Match) so operator can drill into challenge-template detail |
| 2 | Retire `Optimization.js` + `phase9/ExecutionDashboard.js` | ~10 min | Janitorial pass; bundle with first post-import frontend commit |
| 3 | Audit `ArchitectDashboard.jsx` children — retire duplicates | ~2 h | P3 — pairs with Auto Learning activation |
| 4 | Mount Factory Supervisor in MonitoringSuite Cluster sub-tab | ~30 min | P2 — after operator authorises FS activation |
| 5 | Lift `AutoLearningPanel` to standalone + mount at `ai/learning` | ~2 h | P3 — after `FS_ENABLE_AUTO_LEARNING=true` |
| 6 | Document Deployment-Center-is-a-rail-label in OPERATOR_MANUAL | ~10 min | Janitorial pass |

Total post-import UI work to close every hidden/orphan item: **~5 h spread across P1 / P2 / P3**.

---

## 6. State of this document

* No code modified.
* No surfaces mounted.
* All 7 items below the gate; importer is unblocked per `IMPORT_READINESS_REPORT.md`.
* Companion doc to be read alongside `POST_IMPORT_FEATURE_DEPENDENCY.md`.

**End of report.**
