# Strategy Factory — Sprint 3 Phase 2 PRD (Product Requirements Document)

_Last updated · 2026-07-22 · code head `beaf597`_

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

### Files added (across both slices)
```
frontend/src/os/adapters/coverageAdapter.js
frontend/src/os/adapters/strategyLabAdapter.js
frontend/src/os/surfaces/engineering/LivenessBadge.jsx
frontend/src/os/surfaces/engineering/StrategyPipeline.jsx
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
- Historical KB corpus import (blocked pending compatibility / migration review).
- Add Strategy Pipeline to the CmdKPalette jump-to-surface list.
- Progress Portfolio surface using `/api/strategies` (aggregate by symbol/timeframe) — read-only.
- Passport detail view (`/c/strategies/{id}`) enrichment.

### P2 (post-freeze · post-Sprint 3)
- Broker Connections group (waits for freeze to be formally lifted).
- WSS `/stream/*` bindings for live tick / cycle / log tails.
- Optimization launcher + Approvals bundle generation (`/api/optimize/*`).
- Prop Firms + Deployments live surfaces.

## Next action items
1. **Review the compatibility and migration strategy** for the historical KB corpus import (deferred per user directive).
2. Confirm this Engineering slice-2 is accepted before starting the next slice.
3. Consider release tag `v1.1.0-stage4-p2` only after a longer soak on the preview.

## Confirmation
Backend Feature Freeze **v1.1.0-stage4** remains fully intact — this session touched only frontend files (`frontend/src/os/surfaces/engineering/*`, `frontend/src/os/routing/navigation.js`). Zero backend source files were modified.
