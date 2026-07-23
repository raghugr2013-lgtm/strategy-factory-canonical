# Strategy Factory — Sprint 3 Phase 2 PRD (Product Requirements Document)

_Last updated · 2026-07-22 · Slice γ code head `e6ca966`_

## Original problem statement (Sprint 3 Phase 2 + Engineering follow-up)

Continue Sprint 3 Phase 2 under Backend Feature Freeze v1.1.0-stage4. First slice: Coverage · Market Data · Strategy Lab · Strategy Pipeline · role integration. Second slice (this update): Datasets · Optimization · Validation. All work is frontend-additive — no new backend endpoints, no schema or behaviour changes, no synthetic data, prefer LIVE/PARTIAL LIVE surfaces over placeholders.

## Architecture (unchanged from Sprint 2 · v1.1.0-stage4)
- **Backend** — FastAPI (`app.main:create_app`) on port 8001. Only pre-Phase-2 routers are mounted. Feature Freeze v1.1.0-stage4 is in effect.
- **Frontend** — CRA + craco, React 19, react-router 7, zustand. `src/os/*` = Operator OS.
- **Auth** — JWT via `/api/auth/login` + `/api/auth/me`. Roles: `viewer · operator · researcher · developer · admin`.
- **Mongo** — single primary + isolated `strategy_knowledge_base` DB (historical corpus).

## User personas
- **Admin operator** — full access. Sees Mission Control · Engineering · Admin groups. Approves risky actions.
- **Engineer** — Engineering-heavy operator. Composes drafts, sweeps parameters, promotes candidates.
- **Viewer** — Mission Control only. Read-only surfaces.

## Core requirements (static)
- Backend Feature Freeze v1.1.0-stage4 must not be broken — no new endpoints, no behavior changes.
- Every interactive element in `src/os/` carries a `data-testid`.
- No synthetic / demo data is ever rendered when a live endpoint exists.
- Empty payloads → real interface + `PARTIAL LIVE` badge + operator-legible reason.
- Every surface is composable from the existing tokens/primitives (no ad-hoc raw hex, no random fonts).

## What's been implemented — Sprint 3 Phase 2 (across two sessions)

### Slice 1 — foundational Phase-2 (pushed as `20af3df..2dad08b`)

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 1 | Foundational fix — `apiClient.js` runtime guard | `490d7c3` | (unblocked live mode for the whole app) |
| 2 | **Coverage** live surface | `490d7c3` | `GET /api/data/coverage` |
| 3 | **Market Data** PARTIAL LIVE surface | `925383d` | `GET /api/data/coverage` (provider.sources + verification_status + symbols) |
| 4 | **Strategy Lab** live authoring | `807be33` | `POST /api/strategies/generate`, `POST /api/strategies`, `POST /api/knowledge/nearest`, `GET /api/knowledge/statistics` |
| 5 | **Strategy Pipeline** new route + surface | `25902dc` | `GET /api/strategies`, `GET /api/knowledge/champions`, `GET /api/knowledge/statistics` |
| 6 | Real role integration | `2dad08b` | `GET /api/auth/me` (backgrounded refresh) |

### Slice 2 — Engineering follow-up (new · this session)

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 7 | **Datasets** live surface | `4bf7e70` | `GET /api/data/coverage` (summary + symbols + cache + gaps + health) |
| 8 | **Optimization** PARTIAL LIVE queue | `800f456` | `GET /api/strategies`, `GET /api/knowledge/statistics` |
| 9 | **Validation** PARTIAL LIVE ledger | `beaf597` | `GET /api/knowledge/health`, `/statistics`, `/champions`, `GET /api/strategies` |

### Slice α — Workspace context thread + SignalState (2026-07-22)

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 10 | Workspace context (`useWorkspaceContext`) + canonical SignalState (§7, §9) | `7aff84a` | (client-side URL-encoded state) |

### Slice β — Strategy Passport detail view (2026-07-22)

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 11 | Canonical Strategy Passport at `/c/strategies/:id` (§10, §4) | `a17dbe1` | `GET /api/strategies/{id}` · `POST /api/knowledge/nearest` |

### Slice γ — Approvals Modal + Timeline Event Shim (2026-07-22)

Integration wiring only — no new UI concepts, no new backend endpoints.

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 12 | `ApprovalsModal` (§12) + `timelineShim` (§13) canonical implementations | `05cb701` | client-side (sessionStorage zustand) |
| 13 | Shell mount + Passport PROMOTE wiring + Lineage hydration | `e6ca966` | reads §13 events back via `useTimelineEvents({ objectId })` |

**What Slice γ activates:**
- `<ApprovalsModal />` is mounted once at the shell root; any surface calls `openApproval(...)` without prop drill.
- Passport `PROMOTE` CTA is now enabled and opens the modal with the correct §13 event name and §12 consequences bullets per strategy state.
- Passport Lineage tab shows `_requested` + `_approved` rows verbatim per §13.2 (event · actor · reason · ts).
- Executor is `null` under freeze — no backend mutation occurs. Verified via preview smoke + `yarn build` (+2.53 kB) + testid coverage + testing agent (100% structural pass, zero mutations).

### Files added (across all slices this sprint)
```
frontend/src/os/adapters/coverageAdapter.js
frontend/src/os/adapters/strategyLabAdapter.js
frontend/src/os/adapters/timelineShim.js           ← Slice γ · §13
frontend/src/os/hooks/useWorkspaceContext.js
frontend/src/os/shell/ApprovalsModal.jsx           ← Slice γ · §12
frontend/src/os/shell/WorkspaceContextChip.jsx
frontend/src/os/surfaces/StrategyPassport.jsx
frontend/src/os/surfaces/engineering/LivenessBadge.jsx
frontend/src/os/surfaces/engineering/StrategyPipeline.jsx
```

### Files modified in Slice γ (three)
```
frontend/src/os/shell/AppShell.jsx                 ← mount <ApprovalsModal />
frontend/src/os/adapters/timelineShim.js           ← lint fix (comment)
frontend/src/os/surfaces/StrategyPassport.jsx      ← enable CTA + hydrate LineageTab
```

### Files modified (across both slices)
```
frontend/src/os/adapters/apiClient.js
frontend/src/os/routing/AppRouter.jsx
frontend/src/os/routing/navigation.js
frontend/src/os/shell/Header.jsx
frontend/src/os/shell/LeftRail.jsx
frontend/src/os/surfaces/engineering/Coverage.jsx
frontend/src/os/surfaces/engineering/Datasets.jsx
frontend/src/os/surfaces/engineering/MarketData.jsx
frontend/src/os/surfaces/engineering/Optimization.jsx
frontend/src/os/surfaces/engineering/StrategyLab.jsx
frontend/src/os/surfaces/engineering/Validation.jsx
frontend/src/os/workspace-state/authStore.js
```

## Engineering Workspace surface status matrix (post-slice-2)

| Surface | Route | Nav | Status | Live endpoints |
|---|---|---|---|---|
| Market Data       | `/c/engineering/market-data`       | ✅ | PARTIAL LIVE (composed from coverage) | `GET /api/data/coverage` |
| Coverage          | `/c/engineering/coverage`          | ✅ | LIVE / PARTIAL LIVE (data-dependent)  | `GET /api/data/coverage` |
| Datasets          | `/c/engineering/datasets`          | ✅ | LIVE / PARTIAL LIVE (data-dependent)  | `GET /api/data/coverage` |
| Strategy Lab      | `/c/engineering/strategy-lab`      | ✅ | LIVE (round-trip verified)            | `POST /api/strategies/generate` · `POST /api/strategies` · `POST /api/knowledge/nearest` · `GET /api/knowledge/statistics` |
| Strategy Pipeline | `/c/engineering/strategy-pipeline` | ✅ | LIVE / PARTIAL LIVE                   | `GET /api/strategies` · `GET /api/knowledge/champions/statistics` |
| Optimization      | `/c/engineering/optimization`      | ✅ | PARTIAL LIVE (launcher deferred)      | `GET /api/strategies` · `GET /api/knowledge/statistics` |
| Validation        | `/c/engineering/validation`        | ✅ | PARTIAL LIVE (corpus empty)           | `GET /api/knowledge/health` · `/statistics` · `/champions` · `GET /api/strategies` |
| Portfolio         | `/c/engineering/portfolio`         | ✅ | placeholder empty-state (no endpoint under freeze) | — |
| Prop Firms        | `/c/engineering/prop-firms`        | ✅ | placeholder empty-state (deferred)                 | — |
| Deployments       | `/c/engineering/deployments`       | ✅ | placeholder empty-state (deferred)                 | — |

## Prioritized backlog

### P0 (Phase 2 close-out) — DONE
- ~~Coverage · Market Data · Strategy Lab · Strategy Pipeline · Real role~~ ✅
- ~~Datasets · Optimization · Validation~~ ✅

### P1 (next, still under freeze — pending user direction)
- **Historical KB Compatibility & Migration Specification** — DRAFT delivered as `docs/KB_MIGRATION_SPEC.md` (2026-07-22). Planning-only document. Awaiting user review + answers to §11 open questions. No code, no data import, no backend changes.
- Add Strategy Pipeline to the CmdKPalette jump-to-surface list.
- Progress Portfolio surface using `/api/strategies` (aggregate by symbol/timeframe) — read-only.
- Command surface `Approvals inbox` — subscribe to `useTimelineEvents({ eventPrefix: 'operator_' })` and display pending `_requested` events without `_approved`. Zero backend work. (Slice δ · deferred at user direction.)

### P2 (post-freeze · post-Sprint 3)
- Broker Connections group (waits for freeze to be formally lifted).
- WSS `/stream/*` bindings for live tick / cycle / log tails.
- Timeline surface — real read of `POST /api/timeline/events` (swap shim persistence layer; consumers unchanged).
- Optimization launcher + Approvals bundle generation (`/api/optimize/*`).
- Prop Firms + Deployments live surfaces.

## Phase 1 Autonomous Factory Activation — 2026-07-23

Backward-compatible activation of the recovered sibling
factory-runner + Unified Autonomous Orchestration Engine, powered
100% by capabilities already present in the canonical repo. Zero new
engines. Zero new endpoints. Zero schema changes. Backend Feature
Freeze v1.1.0-stage4 preserved. OBSERVE mode preserved for every
mutating engine.

**Files modified (all reversible, all additive/dispatcher-only):**

- `backend/app/runner.py` — rewritten as a **backward-compatible
  dispatcher**. When `FACTORY_RUNNER_OWNS_SCHEDULERS=false` (default)
  it behaves byte-equivalently to the Phase-0 heartbeat stub. When
  true, it delegates to `legacy.factory_runner._main()` and starts a
  background thread that refreshes `/tmp/factory_runner.hb` every 30 s
  so the docker healthcheck stays green during the sibling's slower
  startup.
- `backend/legacy/factory_runner.py` — additive-only: refreshes
  `/tmp/factory_runner.hb` on start and on every audit-heartbeat tick.
  No logic path removed.
- `infra/compose/docker-compose.prod.yml` — propagates Phase-1
  activation env vars into both `factory-backend` and `factory-runner`
  `environment:` blocks. Every new flag defaults to `false`/`observe`,
  so `docker compose up -d` without an updated `.env` is byte-identical
  to prior behaviour.
- `.env.example` — extended with a well-commented Phase-1 activation
  block. All defaults OFF.

**Deliverables published:**

- `docs/PHASE_1_ACTIVATION_PLAN.md` — execution report (reused /
  refined / extended breakdown), production deployment steps, and
  three-tier rollback plan (env-only · code · ledger).
- `docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md` — full observability
  matrix for the eleven autonomous cycle stages (market data,
  knowledge, market intelligence, generation, validation, backtest,
  ranking, passport, persistence, meta-learning, factory-eval),
  including endpoints, ledgers, log-grep patterns, alert triggers,
  and a weekly ledger-reconciliation snippet.

**Production activation (operator work — VPS-side .env edits):**

```env
FACTORY_RUNNER_OWNS_SCHEDULERS=true
ORCHESTRATOR_ENABLED=true
BUDGET_PERSIST=true
MI_ENABLED=true

# Preserved OBSERVE defaults
LEARNING_SCHEDULER_ENABLED=false
LEARNING_CONTINUOUS_MODE=false
META_LEARNING_MODE=observe
FACTORY_EVAL_MODE=observe
EXEC_ENABLED=false
```

Followed by `./infra/scripts/deploy.sh && ./infra/scripts/health.sh`.

**What Phase 1 explicitly does NOT do:** no new engines, no
duplicate schedulers, no duplicate orchestrators, no duplicate
validators, no duplicate persistence, no API behaviour change, no
live trading, no autonomous promotions, no KB DB writes, no freeze
lift. All 100% Reuse plus two surgical Refine deltas.

## Next action items
1. **Operator applies the four env flags** to `/opt/strategy-factory/.env` and runs `./infra/scripts/deploy.sh`.
2. Verify the eight sign-off gates in `docs/PHASE_1_ACTIVATION_PLAN.md` §8.
3. Watch Tier-3 CI stay green for 7 consecutive nights before proceeding to Phase 2 items (embedding backend, UKIE domains, KB migration, Factory Supervisor activation, cTrader adapter).
4. Historical Knowledge Base Migration Phase M0 (dry-run mapper) may proceed in parallel once `docs/KB_MIGRATION_SPEC.md v0.1` §11 questions are answered.

## Deployment Operations pass — 2026-07-23

Documentation-only + one restored file. No application code, API,
schema, engine, or OBSERVE-mode change. Backend Feature Freeze
v1.1.0-stage4 fully preserved.

- Delivered `docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md` — as-is topology
  review, canonical Compose recommendation, six enumerated
  inconsistencies (HIGH → LOW).
- Delivered `docs/DEPLOYMENT_OPERATIONS.md` — single operational
  source of truth (architecture · Docker ops · Mongo backup/restore ·
  Caddy · logging · monitoring · disaster recovery · release ·
  security · eight runbooks · golden rules).
- Delivered `docs/DEPLOYMENT_MIGRATION_PLAN.md` — records that no
  structural migration is required; catalogues the four
  non-destructive actions and the four deferred follow-ups.
- Restored `.env.example` at the repo root (deleted in accidental
  auto-commit `f676526`, 2026-07-20). Every deploy script references
  it (`one_click_deploy.sh`, `factory-bootstrap.sh`,
  `docs/DEPLOYMENT.md`) — fresh clones can now bootstrap.
- Minor pointer update in `README.md` § Utility scripts to name the
  new operations doc + the `compose.sh` wrapper.

**Canonical production workflow (confirmed):**
- Compose file: `infra/compose/docker-compose.prod.yml`.
- Invocation: `./infra/scripts/deploy.sh` (full), `./infra/scripts/compose.sh <cmd>` (one-off), or the explicit `docker compose --env-file .env -f infra/compose/docker-compose.prod.yml` form from repo root.
- Env: `/opt/strategy-factory/.env` (chmod 600).
- Out-of-repo services: `factory-mongo` (`/opt/factory-mongo/`) and `caddy` (`/opt/caddy/`) — reference copies in `deploy-artifacts/`.
- All six containers on external `vqb-network`.

## Capability Inventory & Autonomous Factory Readiness pass — 2026-07-23

Analysis-only. Zero application code, API, schema, engine, or
OBSERVE-mode change. Backend Feature Freeze v1.1.0-stage4 fully
preserved. Deliverables published under `docs/`:

- `docs/CAPABILITY_INVENTORY.md` — 15 sections (Phase-1 core · KB ·
  Autonomous Orchestration · Strategy Generation · Backtest+Validation ·
  Data+Universe · Portfolio+Master Bot+Prop Firms · Paper Trading+
  Execution+Broker · Intelligence+Meta-Learning+Factory Eval+Brain ·
  Factory Supervisor · Governance+Safety+Observability · Infra
  Primitives · Frontend Surfaces · Tests · Roll-up). ~170 engines
  catalogued, each classified (PR/MC/NR/NE/LR/MG) with one action
  (Reuse/Refine/Extend/Replace/Build New).
- `docs/GAP_ANALYSIS.md` — 8 modules × requirements → existing
  support → delta → single recommendation. Consolidated ledger:
  10 Extend · 1 Refine · 1 Build New (deferred). Zero Replace, zero
  Missing critical subsystems.
- `docs/DEPENDENCY_MAP.md` — top-view lattice, per-module bindings,
  cross-module sharing, and dependency-safe bootstrap order. Six of
  eight future modules composable entirely from existing capabilities.
- `docs/AUTONOMOUS_FACTORY_READINESS.md` — Factory is ≈ 85 % ready
  for 24×7. Nothing to build at the subsystem level. Only 1 Refine
  (swap Phase-0 runner stub for recovered `legacy.factory_runner`) +
  1 Extend (activate `factory_supervisor` J1..J6 via the wired
  runner) + 3 small frontend extensions stand between the current
  stack and full autonomy. 17-verb task registry already covers every
  autonomous action.
- `docs/IMPLEMENTATION_ROADMAP.md` — Phases 0..5. Prioritises Reuse
  → Refine → Extend → Replace → Build New. Phase 1 (env-only
  activations: runner swap · orchestrator on · MI on) is a single
  afternoon; Phase 2 (embedding backend · UKIE domains · KB
  migration · Factory Supervisor activation · cTrader adapter) two
  to three focused sessions; Phase 3 (frontend extensions) is
  freeze-safe; Phase 4 (Timeline endpoint + Approvals executor
  wiring) is post-freeze-lift.

**Verdict:** the long-term vision needs zero new engines. Everything
is composition of what is already in the repo.

## Sprint FE-A — Autonomous Factory Sign-In + Live Status Rail — 2026-07-23

REFINEMENT-ONLY sprint. **3 files touched, 0 files created** in the
FE-A scope. Testing_agent iteration_2 verdict: **100 % pass on backend
+ frontend**, zero regressions, all acceptance criteria met.

**Deliverables:**

- `frontend/src/os/auth/LoginScreen.jsx` — removed the visible
  fixture-credentials block from the sign-in card.
- `frontend/src/os/shell/StatusRail.jsx` — `useStatusRailLive()` hook
  polls `/api/orchestrator/status`, `/api/data/coverage`,
  `/api/ai-workforce/health`, `/api/governance/ecosystem-maturity`
  every 15 s + on focus (only when authenticated). Preserves the
  exact visual contract (5 chips + kill posture, same `data-testid`s,
  same tone glyphs). Adds `data-live` attribute for automation.
- `frontend/src/os/routing/navigation.js` — reconciled 6 phase2Sources
  path mismatches against the real backend prefixes.
- `docs/FE_A_EXECUTION_REPORT.md` — execution report + coverage
  metrics + endpoint list.
- `docs/FE_B_PROPOSAL.md` — next sprint proposal (7 Autonomous
  Factory dashboards, extend-only, ~120 endpoints unlocked).
- `memory/test_credentials.md` — real backend admin
  (`admin@strategy-factory.local` / `admin123`) + fixture fallback
  documentation.
- Screenshots: `docs/screenshots/fe-a-00-signin.jpeg`,
  `fe-a-01-mission-live.jpeg`, `fe-a-02-statusrail-live.jpeg`.

**Live proof in the local dev environment:**

- Sign-in card fixture credentials block: **REMOVED** (verified via
  `[data-testid='login-fixture-credentials']` count = 0).
- Real backend sign-in: `admin@strategy-factory.local / admin123` →
  redirected to `/c/mission`.
- RBAC: `[data-testid='nav-group-admin']` present because
  `/api/auth/me` returned `role='admin'`. Badge `ADMIN · LIVE ·
  /API/AUTH/ME`.
- Status rail: `data-live='true'` attribute set post-auth.
  `status-chip-orchestrator` correctly renders `I · ORCHESTRATOR ·
  HALTED` from real backend query (proves live path reached).
- Path reconciliation: `grep` for 6 old paths in `navigation.js`
  returns zero matches.

**Coverage delta:** distinct `/api/*` endpoints reachable from the
UI rose from **8 → ~17** (+9). Frontend-vs-backend coverage rose from
~1.3 % → ~2.8 %.

**Constraint compliance:** ✅ No new backend engines · ✅ No new
backend endpoints · ✅ No database changes · ✅ No schema changes · ✅
Backend Feature Freeze v1.1.0-stage4 preserved · ✅ OBSERVE mode
preserved · ✅ Discover → Reuse → Refine → Extend → Build New order
honoured.

## Frontend Capability Audit — 2026-07-23

Repository-wide read-only audit of the operator UI. Zero code changes.
Zero backend changes. Backend Feature Freeze v1.1.0-stage4 preserved.

**Headline finding:** the local backend exposes **613 endpoints** in
`/api/openapi.json`; the frontend reaches only **8 of them** via
literal `/api/*` string references from adapters + surfaces. The
chrome (rail · top strip · status rail · walkthrough · palette · 21
routes · 12 wired surfaces) is production-grade, but the data layer
underneath is 90 % fixtures. Every one of the currently-missing
surfaces can be added by reusing the existing shell +
`EngineeringSurface` template + adapter pattern — no new backend
engines required.

**Deliverables published:**

- `docs/FRONTEND_CAPABILITY_AUDIT.md` (366 lines) — full route +
  component + adapter + hook inventory · reusable-component census ·
  22-surface capability matrix with per-column completion scores
  (chrome / route / component / fixtures / live-read / live-write /
  streaming / RBAC) · 21 live screenshots captured at
  `http://127.0.0.1:3000/` after signing in with the fixture
  credentials shown on the sign-in card
  (`operator@coinnike.com · prototype123`).
- `docs/FRONTEND_EXPOSURE_ROADMAP.md` (231 lines) — gap ledger
  (CRITICAL / HIGH / MEDIUM / LOW) mapping every un-exposed
  backend prefix to a host surface; six-sprint priority-ordered
  exposure plan (FE-A activation ~4h → FE-F admin+governance) that
  follows Discover → Reuse → Refine → Extend → Build New; 8-item
  sign-off checklist per sprint; explicit guardrails
  ("never build a second sign-in flow", "never duplicate the shell",
  "never invent new backend endpoints").
- `docs/screenshots/*.jpeg` (21 files, 760 KB total, JPEG q=25) —
  visual record of the current UI. Chrome captured cleanly on
  every route; the 30-second `FactoryWalkthrough` overlay is visible
  on most captures because it's the first-session welcome tour.

**Findings called out for immediate operator attention:**

1. **Sign-in is fixture-only.** The card shows
   `operator@coinnike.com · prototype123` in its own body and doesn't
   call `POST /api/auth/login`. The backend seed + JWT refresh
   rotation + admin approval pipeline are fully implemented and
   entirely unreached.
2. **The 8-pill Status Rail is fixture-only.** Every pill has a
   backend equivalent (`/api/health/system`, `/api/orchestrator/status`,
   `/api/data-maintenance/status`, `/api/ai-workforce/providers`,
   `/api/governance/summary`, `/api/coe/state`,
   `/api/factory-eval/kpis`). Wiring the rail is the single highest
   ROI first step.
3. **Endpoint path mismatches** exist between
   `navigation.js` `phase2Sources` metadata and actual backend
   prefixes (e.g. UI declares `/api/coverage/matrix`, backend serves
   `/api/data/coverage`). No backend endpoint has to move; the
   frontend metadata just needs reconciliation.
4. **Zero orchestrator UI.** The Unified Autonomous Orchestration
   Engine (Phase B.2) exposes 7 endpoints and has no operator
   surface. This is the single most important missing dashboard
   before Phase 1 VPS activation.
5. **`EngineeringSurface` template is a superpower.** Five pages
   (Deployments, PropFirms, Users, Integrations, Logs) already ship
   as coherent empty-state briefings. Extending any one of them to
   live data is a metadata + one adapter change, not a rewrite.

**Recommendation summary (Discover → Reuse → Refine → Extend → Build New):**

- Discover: 4 surfaces need path reconciliation only.
- Reuse: entire shell + template + adapter + `LivenessBadge` layer.
- Refine: 15 items (auth, RBAC, TopStrip, StatusRail, MissionControl,
  all 7 wired Engineering surfaces, MasterBot, Strategies, Passport,
  Settings, Timeline shim) → **~150 endpoints unlocked**.
- Extend: 13 items (new Factory group of 7 + 5 empty-state-to-live
  conversions + 1 Portfolio route) → **~250 endpoints unlocked**.
- Build New: 0 backend, 0 frontend components. Only new
  compositions of existing capabilities.

**Total operator reach after full roadmap: ~400 of 613 endpoints
(~65 %) with zero new backend engines.** The remaining ~200 endpoints
are internal / bookkeeping / diagnostic routes that don't belong on
the operator's daily path; they surface via `Timeline` filters and
deep-power `EngineeringSurface` pages when needed.

**User decision requested:** confirm whether we proceed with Sprint
FE-A (the 4-hour high-ROI real-auth + role-aware rail + live status
rail refinement) before ANY VPS activation, or a different sprint
order.

## Operational Readiness pass — 2026-07-23

Testing_agent regression on the runner dispatcher landed last session:
100 % backend success, all four core endpoint contracts unchanged,
dispatcher default-off preservation verified, every Phase-1 flag
present in both service env blocks with correct defaults,
interpolation guards intact. Applied one small symmetry improvement
flagged by the tester (added `FACTORY_RUNNER_OWNS_SCHEDULERS` to the
factory-backend env block too).

Published operator activation package:

- `infra/scripts/phase1_validate.sh` — read-only, idempotent
  one-shot probe that gathers every sign-off signal (repo state,
  env flags, compose parse + interpolation-guard fail-fast check,
  container inventory, docker healthchecks, vqb-network
  membership, backend health + readiness, all auth-scoped
  orchestrator / meta-learning / factory-eval endpoints, 24-h
  ledger reconciliation across 12 collections, log fingerprints,
  heartbeat freshness).
- `docs/PHASE_1_FACTORY_VALIDATION_REPORT.md` — template with
  placeholder blocks keyed to the script's section headers, plus a
  step-by-step restart-recovery drill.
- `docs/PHASE_1_FACTORY_KPI_REPORT.md` — 24-h KPI template
  covering cycle throughput across 12 ledger collections, top-15
  skip reasons, average cycle duration per task, budget burn,
  provider health, data-pipeline coverage, meta-learning +
  factory-eval OBSERVE signal, and free-form bottleneck section.

**Operator handoff:**

1. On the VPS: apply the four env flags from
   `PHASE_1_ACTIVATION_PLAN.md` §6.3, then
   `./infra/scripts/deploy.sh`.
2. Run `sudo -u <docker-user> /opt/strategy-factory/infra/scripts/phase1_validate.sh > /tmp/phase1.txt`.
3. Fill `docs/PHASE_1_FACTORY_VALIDATION_REPORT.md` from that output.
4. Execute the restart-recovery drill in §I of the report.
5. Fill `docs/PHASE_1_FACTORY_KPI_REPORT.md` at end of day 1 and again at end of week 1.
6. Report back so we can identify runtime-driven refinements before Phase 2 feature work begins.

## Confirmation
Backend Feature Freeze **v1.1.0-stage4** remains fully intact through Slice γ — every touched file lives under `frontend/src/os/` (`shell/AppShell.jsx`, `shell/ApprovalsModal.jsx`, `adapters/timelineShim.js`, `surfaces/StrategyPassport.jsx`). Zero backend source files modified across Slices α · β · γ. End-to-end preview verification confirmed zero backend mutations during the Approvals flow. The 2026-07-23 Deployment Operations, Capability Inventory, Phase 1 Activation, and Operational Readiness passes are documentation + a backward-compatible dispatcher + one restored template file — freeze fully preserved.

## Sprint FE-B Slice 1 — Orchestrator Dashboard — 2026-07-23

REFINEMENT + EXTEND sprint (frontend-additive only). Zero backend files
touched. Backend Feature Freeze v1.1.0-stage4 fully preserved.
Testing_agent iteration_3 verdict: **100 % pass on frontend**, no retest
required, main agent may self-test polish.

**Deliverables (this session):**

- `frontend/src/os/adapters/orchestratorAdapter.js` — new React Query
  hooks (`useOrchestratorStatus`, `useOrchestratorDecisions`,
  `useOrchestratorHistory`, `useOrchestratorHealthInputs`) polling six
  pre-existing endpoints every 15 s and on window focus, guarded by
  `isLiveMode()`.
- `frontend/src/os/surfaces/factory/OrchestratorDashboard.jsx` — new
  surface at `/c/factory/orchestrator`. Composition: Operator Summary
  Panel (8 cells — Factory State · Orchestrator Status · Active Tasks ·
  Scheduler Health · AI Provider Health · Last Successful Cycle ·
  Current Alerts · Mode) + 4-tile MetricBlock row (Ticks · Dispatched ·
  In-Flight · Alerts) + Recent Decisions table (last 20 ticks) + Task
  Registry table with per-task run/fail counters and fail-rate chips.
  Reuses `MetricBlock`, `Chip`, `StateTemplate`, `SignalStateBadge`,
  `FreezeCaption` — zero new UI primitives.
- `frontend/src/os/routing/AppRouter.jsx` — wired
  `<Route path='factory/orchestrator' element={<OrchestratorDashboard />} />`.
- `frontend/src/os/routing/navigation.js` — new `NAV_GROUPS` group
  `id: 'factory'` inserted between Mission Control and Engineering,
  visible to all authenticated operators. Contains one entry
  (`nav-orchestrator`).
- `frontend/src/os/shell/StatusRail.jsx` — bug fix in `inferLLMChip`:
  `/api/ai-workforce/health` returns `providers` as an object
  (`{}`), not an array. The previous FE-A code called `.filter` on it
  and threw `providers.filter is not a function` on every route.
  Fix: normalise object-shaped providers to array before filtering.

**Live proof in the local dev environment:**

- Real backend sign-in reaches `/c/mission` (fixture block gone).
- `[data-testid='nav-group-factory']` and `[data-testid='nav-orchestrator']`
  visible in the rail post-auth.
- `/c/factory/orchestrator` renders `orchestrator-dashboard`,
  `orchestrator-summary-panel` (all 8 cells), the 4 metric tiles, the
  decisions panel, and the registry panel — verified by
  testing_agent_v3 iteration_3.
- Zero `Uncaught runtime errors` overlay anywhere in the app after the
  StatusRail fix. All 5 status chips + kill posture render post-auth
  and `data-live='true'` remains set on the status rail wrapper.

**Endpoints unlocked (all pre-existing, read-only):**

- `GET /api/orchestrator/status`
- `GET /api/orchestrator/decisions?limit=20`
- `GET /api/orchestrator/history?limit=20`
- `GET /api/ai-workforce/health`
- `GET /api/factory-eval/config`
- `GET /api/meta-learning/config`

**Constraint compliance:** ✅ No new backend engines · ✅ No new
backend endpoints · ✅ No database changes · ✅ No schema changes · ✅
Backend Feature Freeze v1.1.0-stage4 preserved · ✅ OBSERVE mode
preserved · ✅ Discover → Reuse → Refine → Extend → Build New order
honoured · ✅ Zero fixture data introduced.

## Next action items (post Slice 1)

1. **FE-B Slice 2+** — remaining Factory-group dashboards per
   `docs/FE_B_PROPOSAL.md`: Meta-Learning · Factory Eval · Data
   Maintenance · Budget/Governance · Master Bot Deep Dive · Approvals
   Bundle Composer. Same pattern: adapter + surface + one nav entry.
2. **VPS Phase-1 activation** — operator applies the four env flags
   from `docs/PHASE_1_ACTIVATION_PLAN.md` §6.3 and runs
   `./infra/scripts/deploy.sh`. After activation, the Orchestrator
   Dashboard becomes the primary live-monitoring surface.
3. **Low-priority polish** — chip glyph spacing inside summary cells
   (single-character `I`/`P`/`A` prefix sits tight against the label);
   deferred, cosmetic only.

## Sprint FE-B Slices 2–5 — Meta-Learning · Factory Eval · Data & Governance · Cockpit — 2026-07-23

REFINEMENT + EXTEND sprint (frontend-additive only). Zero backend files
touched. Backend Feature Freeze v1.1.0-stage4 fully preserved.
Testing_agent iteration_4 verdict: **100 % pass on frontend**, no
retest required, one optional semantic tweak applied.

**Deliverables (this session):**

- `frontend/src/os/adapters/metaLearningAdapter.js` — 8 read-only
  hooks over `/api/meta-learning/*` (status, config, health,
  evaluations, recommendations, pending, applications, overrides).
- `frontend/src/os/adapters/factoryEvalAdapter.js` — 10 read-only
  hooks over `/api/factory-eval/*` (status, config, health, kpis,
  reports/latest, reports, insights, recommendations, pending,
  coverage-gaps).
- `frontend/src/os/adapters/dataGovernanceAdapter.js` — 12 read-only
  hooks over `/api/data/maintenance/*`, `/api/data/health`,
  `/api/data/coverage`, `/api/governance/*`, and `/api/coe/*`
  (state · metrics · dead-letter/depth).
- `frontend/src/os/surfaces/factory/factoryPrimitives.jsx` —
  dashboard-local composition helpers (SummaryPanel · SectionHeader ·
  asArray · modeToTone · **deriveHealth**). Zero new design primitives;
  everything reuses tokens + existing `Chip` / `SignalStateBadge`.
  `deriveHealth()` normalises the backend's four "not healthy"
  response shapes: `{detail:'... is off'}` → DORMANT/DISABLED,
  `{status:'empty'}` → DORMANT, `{error}` / `{status:'error'}` →
  CRITICAL, positive signals → HEALTHY. Fixes the false-CRITICAL that
  would otherwise land when Meta-Learning / Factory-Eval / COE
  health-provider flags are off in the preview env.
- `frontend/src/os/surfaces/factory/MetaLearningDashboard.jsx` —
  new surface at `/c/factory/meta-learning`. 8-cell operator summary
  panel · 4-tile metric row · Recommendations table · Evaluations
  table. Reuses `MetricBlock`, `Chip`, `StateTemplate`,
  `SignalStateBadge`, `FreezeCaption`.
- `frontend/src/os/surfaces/factory/FactoryEvalDashboard.jsx` —
  new surface at `/c/factory/evaluation`. 8-cell operator summary
  panel · 4-tile metric row · KPI grid · Insights table.
- `frontend/src/os/surfaces/factory/DataGovernanceDashboard.jsx` —
  new surface at `/c/factory/data-governance`. 8-cell operator
  summary panel · 4-tile metric row · Data-Maintenance recent-runs
  table · Governance promotion-ledger table.
- `frontend/src/os/surfaces/factory/FactoryCockpit.jsx` — unified
  operator landing page at `/c/factory`. Sections: **Overall Factory
  Health** (worst-signal-wins across 7 subsystems) · 7-tile subsystem
  grid (each tile a working `<Link>` to its own dashboard) ·
  **Current Alerts** (aggregated across all subsystems) · **Running
  Tasks** table (from orchestrator in-flight) · **Recent Decisions**
  table (from orchestrator decisions ledger). Post-iteration_4 tweak:
  halted orchestrator maps to `warn` so the aggregate chip surfaces
  ATTENTION instead of HEALTHY.
- `frontend/src/os/routing/AppRouter.jsx` — 4 new routes wired.
- `frontend/src/os/routing/navigation.js` — Factory group expanded
  to 5 entries with **Cockpit as first entry**.

**Endpoints unlocked (all pre-existing, read-only):**

- `/api/meta-learning/*` — 8 endpoints
- `/api/factory-eval/*` — 10 endpoints
- `/api/data/maintenance/*` — 3 endpoints
- `/api/data/health` · `/api/data/coverage`
- `/api/governance/*` — 6 endpoints
- `/api/coe/*` — 3 endpoints

**Constraint compliance:** ✅ No new backend engines · ✅ No new
backend endpoints · ✅ No database changes · ✅ No schema changes · ✅
Backend Feature Freeze v1.1.0-stage4 preserved · ✅ OBSERVE mode
preserved · ✅ Discover → Reuse → Refine → Extend → Build New order
honoured · ✅ Zero fixture data introduced · ✅ Zero writes from any
Factory-group surface (all GETs, guaranteed by adapter shape).

**Live proof (testing_agent iteration_4):**

- All 5 Factory nav entries present (`nav-factory-cockpit`,
  `nav-orchestrator`, `nav-meta-learning`, `nav-factory-eval`,
  `nav-data-governance`).
- `/c/factory` renders 14/14 required testids.
- Each of the 3 dashboards renders 16/16 required testids.
- All 6 cockpit tiles navigate to correct dashboards.
- deriveHealth() correctly classifies disabled backends: no false
  CRITICAL from Meta-Learning / Factory-Eval / COE feature-off
  responses.
- StatusRail regression green (no `providers.filter` crash).
- Zero uncaught runtime errors across every route.

## Next action items (post Slice 2–5)

1. **VPS Phase-1 activation** remains deferred per user direction —
   operator wants the Cockpit fully operational as the primary
   monitoring surface first.
2. **Optional FE-B slices** (from FE_B_PROPOSAL.md, all still
   frozen-safe):
   - Master Bot deep-dive dashboard.
   - Approvals Bundle Composer (client-side, uses the existing
     Timeline shim).
   - AI Provider deep dive (extend Cockpit tile → dedicated
     surface using `/api/ai-workforce/metrics · quality · scores ·
     recent`).
   - Budget / Risk Budget dashboard (`/api/orchestrator/budget` +
     `/api/brain/risk-budget`).
3. **Low-priority polish** (from iteration_4 note) — Chip glyph
   spacing inside summary cells; cosmetic only.

## Operator Acceptance Testing (OAT) — 2026-07-23

Validation-only pass ahead of VPS Phase-1 activation. Zero backend
files modified. Zero frontend files modified. Backend Feature Freeze
v1.1.0-stage4 fully preserved.

**Verdict: SIGN-OFF — READY FOR VPS PHASE-1 ACTIVATION.**

Testing_agent iteration_5 result: **100 % pass, zero blockers, zero
attention items, zero polish items** across four OAT dimensions:

1. Full operator journey (login → RBAC → Cockpit → each of 5 Factory
   dashboards → cross-navigation → sign-out).
2. Cockpit widget-by-widget verification against live backend payloads
   (13 widgets across 4 panels, 42+ testids).
3. Backend coverage audit — 646 total endpoints, 46 distinct paths
   exposed, ~53 % of operator-critical READ endpoints wired, 0 %
   WRITE endpoints wired (freeze compliance).
4. Freeze-proof — fetch-level instrumentation confirmed zero POST /
   PUT / PATCH / DELETE calls from any Factory-group surface.

**Deliverables published:**

- `docs/BACKEND_COVERAGE_REPORT.md` — full endpoint inventory, bucket
  coverage (critical / internal-engine / diagnostic), per-tag
  breakdown, frontend → backend adapter map.
- `docs/PRODUCTION_READINESS_REPORT.md` — 10-section sign-off with
  workflow validation matrix, cockpit widget matrix, blocker ledger
  (empty), risk register (four residual low-impact), operator readiness
  matrix, VPS Phase-1 activation runbook with expected Cockpit deltas,
  and the sign-off table.
- `docs/oat/openapi.json` + `docs/oat/endpoint_coverage.json` — raw
  inventory captured during the OAT run for reproducibility.
- `test_reports/iteration_5.json` — OAT test agent verdict.

**Deployment confidence score: 9 / 10.** Single reserved point is the
observed-vs-expected delta once the four VPS Phase-1 flags flip on.
Everything else has been validated end-to-end.

## Next action items (post OAT)

1. **VPS Phase-1 activation on operator command** — follow the runbook
   in `docs/PRODUCTION_READINESS_REPORT.md` §9 (or the more detailed
   `docs/PHASE_1_ACTIVATION_PLAN.md`).
2. **Post-activation validation** — run `phase1_validate.sh`, populate
   `PHASE_1_FACTORY_VALIDATION_REPORT.md`, monitor the Cockpit for
   ATTENTION → HEALTHY transition on all 7 subsystems.
3. **Optional post-Phase-1 FE-B extension slices** (all still
   freeze-safe): Master Bot deep-dive, Portfolio surface, AI Provider
   deep-dive, Budget / Risk-Budget dashboard, Approvals inbox.

## Historical Knowledge Base (HKB) Recovery — 2026-07-23

Analysis-only pass. Zero data imported into production. Backend Feature
Freeze v1.1.0-stage4 preserved. `strategy_factory_v1` production DB
untouched throughout.

**Bundle received:** `migration_bundle.tar.gz` (32 MB), sourced from the
1-vCPU AI Strategy Factory v10 pod on 2026-06-11. Contained
`mongo_full.gz` (33 MB mongodump), `files.tar.gz` (memory docs + 22
prop-firm PDFs), `llm_routing.env`, and `EXPORT_MANIFEST.md`.

**Actions performed (all safe, all reversible):**

1. SHA-256 integrity verified — 3/3 archives OK.
2. Bundle restored to isolated staging DB `hkb_staging_20260723`
   (production `strategy_factory_v1` untouched).
3. Full 6-phase audit executed — inventory, compatibility, quality,
   plan, dry-run, recommendation.
4. Dry-run through pre-existing `backend/scripts/migrate_strategy_recovery.py`
   confirmed 19,773 documents across 22 of 25 collections would upsert
   cleanly, zero conflicts, zero write errors.

**Headline findings:**

- 1,073,287 total documents restored to staging across 25 collections.
- 1,053,512 of those are `market_data` ticks (bulk deferred by default).
- Research corpus (non-market-data): **19,775 documents across 24
  collections** — mutation lineage (10,430 events), lifecycle history
  (878 rows), performance history (1,047 rows), library specimens
  (140), market profiles (792), ingestion trail (55 raw + 11 runs).
- All 140 library specimens carry `verdict=RISKY` — no funded/strong
  strategies yet, but the corpus is institutional research value: what
  was tried, what failed, and why. Meta-Learning will consume it as
  prior negative evidence.
- 2 conflict-managed collections (`users`, `governance_universe`) —
  operator policy decisions captured in the report.
- Migration Readiness Score: **8 / 10** — recommendation to PROCEED
  pending two explicit operator decisions.

**Deliverables published:**

- `docs/HKB_RECOVERY_REPORT.md` — full 6-phase report (executive
  summary, inventory, compatibility matrix, quality assessment,
  migration plan, dry-run report, final recommendation with two
  operator decisions).
- `hkb/reports/phase1_inventory.json` — machine-readable inventory.
- `hkb/reports/phase3_quality.json` — machine-readable quality classification.
- `hkb/bundle_files/` — extracted memory docs (25 files) + 22 prop-firm
  PDFs for reference only; no application-code change.
- Isolated staging DB `hkb_staging_20260723` remains in place for
  operator verification. Drop with `db.dropDatabase()` when done.

**What was NOT done (per user instruction):**

- No documents imported into production `strategy_factory_v1`.
- No `market_data` bulk import (deferred by default per §6.3.1).
- No legacy `users` row imported.
- No modification to prod `governance_universe`.
- No backend engines added / modified.
- No API contract change.

**Two operator decisions required before production migration:**

1. `market_data` — import 1,053,512 rows (200 MB) or defer / drop?
2. Legacy `governance_universe.audit_log` — archive to
   `governance_universe_legacy` for provenance, or discard?

Once the operator authorises the migration, execute per
`docs/HKB_RECOVERY_REPORT.md` §6.4.

## HKB Migration Executed — 2026-07-23

**Operator decisions received & applied:**
1. `market_data` → **IMPORT** (approved).
2. `governance_universe.audit_log` → **ARCHIVE** as
   `governance_universe_legacy` (approved).

## HKB UI Exposure Bug (2026-07-23) — FIXED

**Reported by operator:** After the HKB migration succeeded, the UI still
showed `KB 0 / 0 Families`, `Historical KB Size = 0`, and
`Champion Families = 0`. Bug testing agent iteration_7 verdict: **fixed,
100 % frontend pass, zero blockers**.

**Root cause:** The `/api/knowledge/*` endpoints read from a different
database + collection namespace (`strategy_knowledge_base.strategy_kb_view`
+ `strategy_knowledge_base.strategy_kb_champions`) than the migration
landed in (`strategy_factory_v1.strategy_library` +
`curated_strategy_library`). The API was healthy but had no data to
serve.

**Fix (freeze-safe, zero backend change):**

1. `hkb/scripts/build_kb_views.py` — pure ETL rebuilding the derived KB
   views from the imported HKB corpus. Populates
   `strategy_kb_view` (140 rows, tagged `learning_only:true` +
   `eligible_for_deploy:false`) and `strategy_kb_champions` (6
   categories) idempotently. Every row carries the migration
   provenance stamp.
2. Follow-up frontend fixes surfaced by bug-testing iteration_6 (all
   applied and re-verified in iteration_7):
   - `Strategies.jsx` — added `strategies-hkb-banner` linking to
     `/c/factory/curated`, plus refreshed empty-state copy that
     mentions the 140 legacy specimens.
   - `StrategyPipeline.jsx` — swapped the "Champion families" tile
     primary value to `canonical_families=132` (was flattened
     `championRows.length=34`); footnote retains the champion-row
     count for context.
   - `CuratedLibraryDashboard.jsx` — added a fixed `CATEGORY_ORDER`
     so all six champion panels always render (empty ones show a
     StateTemplate empty-state; the A-Elite panel carries the
     educational message explaining why the legacy HKB has zero
     A-Elite candidates).
3. New surface at `/c/factory/curated` (added when we authored the
   Curated Library dashboard) with adapter
   `curatedLibraryAdapter.js` consuming
   `/api/knowledge/{health,statistics,champions}`.

**Confirmed counts (bug-testing iteration_7):**

- `/api/knowledge/statistics` → `total_strategies=140`, `canonical_families=132`.
- `/api/knowledge/champions` → 6 categories populated.
- Strategy Lab (`/c/engineering/strategy-lab`) → `KB 140 / 132`.
- Strategy Pipeline (`/c/engineering/strategy-pipeline`) → Historical
  KB Size = 140, Champion Families = 132.
- Strategy Explorer (`/c/strategies`) → HKB banner shows
  `140 legacy` + `132 families` chips, links to `/c/factory/curated`.
- Curated Library (`/c/factory/curated`) → 140 corpus / 132 families /
  19 candidates; all six champion panels render (A-Elite empty state
  educational message present).


1. `market_data` → **IMPORT** (approved).
2. `governance_universe.audit_log` → **ARCHIVE** as
   `governance_universe_legacy` (approved).

**Deliverables:**

- `docs/HKB_MIGRATION_REPORT.md` — full final migration report with
  10 sections (executive summary, provenance metadata, migration
  details, post-import pipeline, referential integrity, count
  reconciliation, HKB conceptual model, freeze-preserved deferrals,
  rollback options, sign-off).
- `hkb/scripts/migrate_hkb.py` — idempotent migration driver, stamps
  the four operator-required provenance fields (`__migration_source`,
  `__migration_timestamp`, `__migration_version`, `__legacy=true`).
- `hkb/scripts/post_import_pipeline.py` — deterministic post-import
  pipeline covering Stage 0/1/3.5 + Curated Library seeding. No
  backend engine invocation (freeze preserved).
- `hkb/reports/migration_run_*.json` + `post_import_run_*.json` —
  machine-readable per-run reports.
- `hkb/backups/prod_pre_hkb_20260723_143620.archive` — pre-migration
  production backup (rollback point).

**Results:**

- Total documents imported: **1,073,286** across 23 collections in
  ~85 seconds.
- Total provenance-stamped documents in prod (imported + derived):
  **1,073,865**.
- Zero write errors, zero count mismatches, zero missing provenance
  stamps, zero orphans (except the 1 pre-migration mutation_events
  orphan documented in the source-of-truth history).
- 3 derived collections produced by the post-import pipeline:
  - `strategy_risk_profile` (140 docs — one per specimen).
  - `strategy_pass_analysis` (420 docs — 140 × 3 firms).
  - `curated_strategy_library` (19 unique clusters ranked by composite
    score; 3 B-Candidate + 16 C-Experimental; deduped from 140 with
    lineage preserved).
- `governance_universe_legacy` collection archived with legacy
  audit-log trail intact.

**HKB conceptual model realised:**

- **Historical Knowledge Base** (permanent memory) — 1,073,286 docs,
  every one carrying `__legacy=true`.
- **Curated Strategy Library** — 19 highest-quality unique candidates,
  initial portfolio for Demo Trading / Portfolio evaluation / Operator
  review.
- **Strategy Explorer** — existing surfaces (`/c/engineering/strategy-passports`,
  `/c/engineering/strategy-pipeline`, `/c/engineering/strategy-lab`)
  already return the imported data; `__legacy=true` enables clean
  filtering between HKB and post-Phase-1 rows.
- **Meta-Learning** — will consume the HKB as prior evidence
  (10,430 mutation-event outcomes, 1,042 stability decisions,
  878 lifecycle transitions).

**Freeze compliance:** Zero backend files modified. Zero API surface
changed. All post-import scoring performed by external Python drivers
against MongoDB directly. The 8-stage POST_IMPORT_PIPELINE completed
Stages 0/1/3.5 + Curated Library; Stages 2, 3.1-3.4, 4-8 (which invoke
backend scoring engines / portfolio-builder / master-bot-engine)
remain queued for post-freeze operator command — none of them are
blocking VPS Phase-1 activation.

## Operator Manual — 2026-07-23

Comprehensive Deployment & Operations Manual authored ahead of VPS
Phase-1 activation, per operator request.

**Deliverable:** `docs/OPERATOR_MANUAL.md` — 18 sections covering:

1. System architecture and module relationships (diagrammed)
2. Frontend modules & workflows (per surface, per group)
3. Daily operator workflow (morning · mid-day · end-of-day · weekly)
4. VPS Phase-1 activation procedure (env flags + expected Cockpit
   transitions per tile)
5. Environment variables & configuration
6. OBSERVE · Recommendation · Autonomous mode behaviour
7. Meta-Learning lifecycle (with HKB warm-up path)
8. Factory Evaluation lifecycle
9. Orchestrator lifecycle (60 s tick cadence)
10. Strategy lifecycle from ingested → deployed
11. HKB & Curated Library usage (permanent memory model)
12. Approval workflow (freeze-limited, executor null, timeline shim)
13. Validation workflow (five gates)
14. Monitoring & health checks (real-time signals + probes + logs +
    alerts)
15. Recovery & rollback procedures (three-tier + kill switch +
    backup schedule)
16. Expected behaviour first 24-72 hours after activation (hour-by-hour
    playbook + warning signs)
17. Known limitations under Feature Freeze (nine documented)
18. Phase-2 roadmap (freeze lift · WRITE wiring · POST_IMPORT_PIPELINE
    completion · new dashboards · post-freeze backend · operational
    hardening · marketplace)

The Manual is written from the operator's perspective and refers
back to the existing production-readiness and HKB migration reports
as appendices. Sign-off table at the end records every prior
milestone (FE-A + FE-B/1-5 + HKB migration + iteration 1-7 test
passes).

**No backend changes. No code changes. Documentation-only deliverable
per operator request.**

## Next action items

1. Operator reviews `docs/OPERATOR_MANUAL.md`.
2. On approval, proceed to VPS Phase-1 activation per §4 of the
   Manual (or the equivalent §9 of the Production Readiness Report).
2. **Optional post-Phase-1 FE-B extension** — a dedicated
   `/c/factory/curated` surface exposing the 19 curated candidates
   with drill-down to the full HKB lineage. ~1 FE-B slice of work,
   freeze-safe.
3. **Post-freeze re-scoring** — once the backend engines are unfrozen,
   run POST_IMPORT_PIPELINE Stages 2 + 3.1-3.4 + 4-8 (Quality v2 /
   Evidence / Market / Trust / Rank / Match / Portfolio /
   Marketplace).
4. **Meta-Learning warm-up** — feed HKB priors into the Meta-Learning
   engine on first run after Phase-1 activation to bootstrap the
   evaluator with 10,430 pre-computed variant outcomes.


