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

## Next action items
1. **Review `docs/KB_MIGRATION_SPEC.md` v0.1** and answer the 10 open questions in §11 so the spec can move to accepted status.
2. Once accepted, Phase M0 (dry-run mapper — frontend-only preview) is the first execution slice. Phases M1–M3 wait for the freeze to lift on schema additions + Timeline endpoint.
3. Execution Workspace group (Broker Connections · Paper Trading · Live Deployments) remains **DEFERRED** until the migration specification is reviewed and approved.

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

## Confirmation
Backend Feature Freeze **v1.1.0-stage4** remains fully intact through Slice γ — every touched file lives under `frontend/src/os/` (`shell/AppShell.jsx`, `shell/ApprovalsModal.jsx`, `adapters/timelineShim.js`, `surfaces/StrategyPassport.jsx`). Zero backend source files modified across Slices α · β · γ. End-to-end preview verification confirmed zero backend mutations during the Approvals flow. The 2026-07-23 Deployment Operations pass is documentation-only + one restored template file — freeze fully preserved.
