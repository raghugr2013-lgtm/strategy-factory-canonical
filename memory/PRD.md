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
