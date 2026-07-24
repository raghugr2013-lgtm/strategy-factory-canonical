# Strategy Factory Canonical — PRD

_Last updated: 2026-07-24_

## Original Problem Statement
Manage the deployment architecture of the "Strategy Factory Canonical" project
and expose existing backend capabilities through the frontend without
introducing new backend API functionality (Backend API is under a strict
**Feature Freeze**).

## Current State
- Phase-1b Factory Supervisor deployed to production (VPS) and validated:
  5 recurring jobs, orchestrator/mutation/factory_eval/meta_learning/governance.
- Phase-2 orchestration milestone completed (docs + supervisor refactor,
  NOT yet activated on the VPS).

## Milestone Log

### 2026-07-24 · Frontend Phase F — Workforce Explorer
Ported the prototype's Master-Bot-headed workforce surface into a new
additive surface at `/c/workforce/explorer` alongside legacy `Workforce`
(`/c/workforce`) and `MasterBot` (`/c/masterbot`). Reuses `factoryAdapter.fetchWorkers`
+ `masterBotAdapter.aggregateMasterBot` + `WorkerCard` primitive + `navigationStore.saveSurface`
for view memory + `useWorkspaceStore.killPostureArmed` for the danger
ribbon. Three-view toggle (org / purpose / status) with view memory persisted
across route changes. State-first table sorts errors and blocked workers to
the top (Bible §7.6 attention-first ordering).

Deliverables:
- `frontend/src/os/surfaces/WorkforceExplorer.jsx` (~370 lines)
- `frontend/src/os/surfaces/WorkforceExplorer.stories.jsx` (4 variants)
- `frontend/tests/e2e/workforce-explorer.spec.cjs` (9 tests)
- Route `/c/workforce/explorer` in `AppRouter.jsx` (additive only)
- Discovery links: `workforce-try-explorer` on Workforce, `masterbot-try-workforce-explorer` on MasterBot
- `docs/PHASE_F_ARCHITECTURE.md`
- Updated `docs/PROTOTYPE_MIGRATION_TRACKER.md`

Bug fixed mid-phase: view-memory mount race (iteration_13 flagged; fix
verified in iteration_14 → 13/13 pass). Replaced the async two-effect
pattern with a synchronous lazy `useState` initializer + `hydratedRef`-guarded
save effect so the persisted view is not stomped on first mount.

Bundle: 239.30 → 240.76 kB gzipped (+0.61% for this phase; +1.51%
cumulative since Phase D2). Backend Feature Freeze preserved.

### 2026-07-24 · Frontend Phase E — Timeline Explorer
Ported the prototype's chronological activity affordances into a new
additive surface at `/c/timeline/explorer` alongside legacy `Timeline` at
`/c/timeline`. Reuses `timelineAdapter.fetchTimeline`, `streamAdapter.useStream`,
`navigationStore` (actor facet + saveSurface + setCrumb), `useWorkspaceStore`
(`timeWindow`, `selectStrategy`), and existing primitives/features (SurfaceHeader,
SignatureFrame, ActivityRow, EvidenceDrawer, FacetBar, TimeWindowChip,
StreamPostmark). Also patched `StrategyPassport.jsx` to consume
`navigationStore.crumb` so both Phase C's `StrategyExplorer` and Phase E's
`TimelineExplorer` produce a visible "back to explorer / back to timeline"
return button (previously the crumb was written but never read).

Deliverables:
- `frontend/src/os/surfaces/TimelineExplorer.jsx` (~250 lines)
- `frontend/src/os/surfaces/TimelineExplorer.stories.jsx` (3 variants)
- `frontend/tests/e2e/timeline-explorer.spec.cjs` (8 tests)
- Route `/c/timeline/explorer` in `AppRouter.jsx` (additive only)
- Discovery link `timeline-try-explorer` on legacy Timeline
- Passport back-link now consumes `navigationStore.crumb`
- `docs/PHASE_E_ARCHITECTURE.md`, `docs/PROTOTYPE_MIGRATION_TRACKER.md`

Verified: iteration_11 (initial) → 89% pass (crumb rendering gap). Fix
verified in iteration_12 → 100% pass. Bundle: 237.18 → 239.30 kB gzipped
(+0.89%, within guardrail). Backend Feature Freeze preserved.

### 2026-07-24 · Frontend Phase D2 — Evaluation Harness interactions unlocked
Pure "unlock" commit on the surface shipped in D1. Wired the five pre-declared
store mutators to the UI:

- `setVerdict(criterionId, verdict)` — 96 verdict buttons (24 × 4)
- `setSession(str)` — session-label input
- `setNotes(str)` — walk-through notes textarea
- `clearAll()` — reset verdicts
- `markAllPass()` — diagnostic mark-all shortcut

Removed `disabled` / `readOnly` / `aria-disabled` attributes and the
"D2 unlock" tooltip. Layout, testids, and route are unchanged from D1
(surface anatomy verified against iteration_9 baseline).

Deliverables:
- `frontend/src/os/surfaces/EvaluationHarness.jsx` — mutator wiring
- `frontend/src/os/surfaces/MissionControl.jsx` — badge label `D1 preview` → `walkable checklist`
- `frontend/tests/e2e/evaluation-harness.spec.cjs` — replaced with 9 interaction tests
- `docs/PHASE_D2_ARCHITECTURE.md` — D2 unlock diff + interaction graph

Verified: `iteration_10.json` → 100% pass (12/12 checks). ZERO new `/api`
endpoints. Persistence via `localStorage['sf.eval.v1']` confirmed by
reload-restore test. Phase A/B/C regression clean.

### 2026-07-24 · Frontend Phase D1 — Evaluation Harness (read-only)
Ported the 24-criterion Interactive Prototype Gate (`prototype/src/surfaces/EvaluationHarness.tsx`)
into a **net-new additive route** `/c/evaluation`. Verdict buttons, session-label
input, notes textarea, and reset / mark-all controls are rendered in their final
positions but **disabled/read-only** so layout is pixel-stable across D1 → D2.

Deliverables:
- `frontend/src/os/surfaces/EvaluationHarness.jsx` — read-only surface (~500 lines)
- `frontend/src/os/surfaces/EvaluationHarness.stories.jsx` — 4 Storybook variants (Unstarted / InProgress / Blocked / Ready)
- `frontend/tests/e2e/evaluation-harness.spec.cjs` — 5-test Playwright spec
- `frontend/src/os/routing/AppRouter.jsx` — new `/c/evaluation` route
- `frontend/src/os/surfaces/MissionControl.jsx` — new discovery link `mc-open-evaluation`
- `docs/PHASE_D1_ARCHITECTURE.md` — component graph + state model diagram

Verified: `iteration_9.json` → 100% pass (10/10 checks). NO new `/api` endpoints
touched (backend freeze preserved). Bundle size after gzip: **237.18 kB** main.js
(within guardrail). Phase A/B/C regression clean.

### 2026-07-23 · Phase 2 — Orchestration audit + activation matrix (commit 64076c6)
Repository audit found that the codebase already has a production-ready
**Unified Orchestrator** at `legacy/engines/orchestrator/core.py` with 17
registered task adapters, auto-booted by `factory-backend` when
`ORCHESTRATOR_ENABLED=true`. The Factory Supervisor was refactored from
placeholder cron jobs into 5 read-only observability + governance hooks
so it complements the orchestrator instead of duplicating it.

Deliverables (all in `docs/`):
- `PHASE2_ORCHESTRATION_AUDIT.md` — repository audit + engine inventory (425 files)
- `PHASE2_ACTIVATION_MATRIX.md` — 17-task activation matrix, dependency + validation
  report, scheduler flow diagram, production-readiness assessment, VPS env-only
  activation procedure

Explicit non-changes (Feature Freeze preserved):
- No FastAPI routes / routers
- No engine logic
- No DB schema
- No docker-compose files
- `runner.py` dispatch order unchanged (Supervisor > Legacy > Phase-0 stub)

Activation profile designed but NOT applied on VPS:
```
ORCHESTRATOR_ENABLED=true
ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true
ORCH_TASK_BACKTEST_PASSIVE=true
ORCH_TASK_MUTATION_PASSIVE=true
ORCH_TASK_LEARNING_CYCLE_PASSIVE=true
```
(All engine-mode master switches keep their observational defaults:
`META_LEARNING_MODE=observe`, `FACTORY_EVAL_MODE=observe`, `MI_ENABLED=false`,
`EXEC_ENABLED=false`.)

### 2026-07-22 · Phase 1b — Factory Supervisor deployed (commit c27c3e6)
APScheduler-based cross-process scheduler wired into `runner.py` as third
dispatch mode (`FACTORY_SUPERVISOR_ENABLED=true`), preserving legacy sibling
and Phase-0 stub. Production-deployed via commits 5078fef (compose env
plumbing) + ca15f3f (requirements.txt cleanup).

### 2026-07-22 · HKB migration + Operator Manual (pre-Phase-1b)
HKB migration with provenance metadata, UI exposure fixes, Operator Manual
(`docs/OPERATOR_MANUAL.md`).

## Architecture — three schedulers, one dispatch authority

| Layer | Container | Trigger | Role |
| --- | --- | --- | --- |
| **Unified Orchestrator** (17 tasks) | `factory-backend` | `ORCHESTRATOR_ENABLED=true` | ⭐ SINGLE dispatch authority for the 17-task registry |
| **Factory Supervisor** (5 obs jobs) | `factory-runner` | `FACTORY_SUPERVISOR_ENABLED=true` ✅ *live* | Observability + governance + failsafe cross-process beacon |
| Legacy sibling scheduler | `factory-runner` (mode 2) | `FACTORY_RUNNER_OWNS_SCHEDULERS=true` | Restores persisted APScheduler jobs (BI5 sweep etc.) |
| Phase-0 stub | `factory-runner` (mode 3) | fallback default | Heartbeat only |

## Files of Reference
- `backend/app/factory_supervisor.py` — refactored observability layer (this milestone)
- `backend/app/runner.py` — three-mode dispatcher (Phase 1b, unchanged this milestone)
- `backend/legacy/engines/orchestrator/core.py` — Unified Orchestrator (unchanged)
- `backend/legacy/engines/orchestrator/tasks/` — 17 task adapters (unchanged)
- `docs/PHASE2_ACTIVATION_MATRIX.md` — activation matrix + validation + flow diagram
- `docs/PHASE2_ORCHESTRATION_AUDIT.md` — repo audit + engine inventory
- `docs/OPERATOR_MANUAL.md` — operator guide (prior milestone)

## Environment Variables (delta vs. Phase-1b)
Nothing added at the compose level. The Phase-2 milestone documents an
env activation profile that would be applied on the VPS via `.env` +
`compose.sh up -d --no-deps --force-recreate factory-backend factory-runner`.
See `docs/PHASE2_ACTIVATION_MATRIX.md` §"VPS activation procedure".

## Backlog
- **P1** — Phase G (**optional**) · Mission Control in-place polish. Skip if
  operator considers current Mission Control acceptable.
- **P2** — Deprecate legacy `Approvals.jsx`, `Strategies.jsx`, and optionally
  `Timeline.jsx` / `Workforce.jsx` / `MasterBot.jsx` once operators validate
  the Explorer variants.
- **P2** — Extend the return-crumb pattern to `ApprovalCenter →
  StrategyPassport` (post-migration polish; completes Bible §7.4a Predictable
  Return triad). Deferred per Phase F kickoff.
- **P2** — **Post-migration productivity phase** (after Explorer migration is
  signed off): productivity enhancements for the Evaluation Harness such as
  _Copy readiness summary to clipboard_, _Export report_ (Markdown / JSON),
  and _Share snapshot_ (URL-encoded state).
- **P1** — Operator applies Phase-2 activation profile on VPS (env-only,
  no rebuild needed for backend since app/main.py already boots orchestrator
  when `ORCHESTRATOR_ENABLED=true`; runner rebuild picks up the new
  supervisor observability code).
- **P1** — Post-activation: tail `factory-runner` logs and confirm the
  supervisor's `liveness_snapshot` shows `orchestrator_running: true`
  and `task_names` populated (visible after backend recreate).
- **P2** — Replace the 4 currently-passive autonomous writers
  (`strategy_generate`, `backtest`, `mutation`, `learning_cycle`) with
  operator-approved semi-autonomous flows if/when the observational
  phase concludes.
- **P2** — Wider testing: run `pytest legacy/tests/ -k orchestrator`
  on the VPS after activation.
- **P2** — Phase-3 roadmap.
