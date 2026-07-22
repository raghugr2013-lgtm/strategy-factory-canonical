# Strategy Factory — Sprint 3 Phase 2 PRD (Product Requirements Document)

_Last updated · 2026-07-22 · commit `2dad08b`_

## Original problem statement (Sprint 3 Phase 2)

Continue Sprint 3 Phase 2 from a session that ran out of credits before its Coverage / Strategy Lab / Strategy Pipeline swaps could be pushed. Inspect the repo, verify what is present, run the frontend build + verification suite, then complete Phase 2 under Backend Feature Freeze v1.1.0-stage4 (frontend-additive only · no new backend endpoints · no synthetic data · PARTIAL LIVE badges over placeholders whenever a live endpoint is connected).

## Scope of this document
Sprint 3 Phase 2 is the second frontend-additive slice on top of Sprint 3 Phase 1 (Engineering Workspace shell). Its goal is to progressively replace Engineering placeholders with live surfaces consuming pre-existing backend endpoints — no backend changes.

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

## What's been implemented — Sprint 3 Phase 2 (this session)

| # | Deliverable | Commit | Live endpoints |
|---|---|---|---|
| 1 | Foundational fix — `apiClient.js` runtime guard | `490d7c3` | (unblocked live mode for the whole app) |
| 2 | **Coverage** live surface | `490d7c3` | `GET /api/data/coverage` |
| 3 | **Market Data** PARTIAL LIVE surface | `925383d` | `GET /api/data/coverage` (provider.sources + verification_status + symbols) |
| 4 | **Strategy Lab** live authoring | `807be33` | `POST /api/strategies/generate`, `POST /api/strategies`, `POST /api/knowledge/nearest`, `GET /api/knowledge/statistics` |
| 5 | **Strategy Pipeline** new route + surface | `25902dc` | `GET /api/strategies`, `GET /api/knowledge/champions`, `GET /api/knowledge/statistics` |
| 6 | Real role integration | `2dad08b` | `GET /api/auth/me` (backgrounded refresh) |

### Foundational fix (also shipped this session)
- `apiClient.js` used `typeof process !== 'undefined'` as a runtime guard around `process.env.REACT_APP_BACKEND_URL`. In the browser `process` is `undefined`, so the guard short-circuited and forced the entire app into fixture-mode — silently. Replacing the guard with a try/catch around the DefinePlugin-inlined property access restores true live mode. This was the root cause preventing any prior Phase-1 "live" work from actually being live.

### Files added
```
frontend/src/os/adapters/coverageAdapter.js
frontend/src/os/adapters/strategyLabAdapter.js
frontend/src/os/surfaces/engineering/LivenessBadge.jsx
frontend/src/os/surfaces/engineering/StrategyPipeline.jsx
```

### Files modified
```
frontend/src/os/adapters/apiClient.js
frontend/src/os/routing/AppRouter.jsx
frontend/src/os/routing/navigation.js
frontend/src/os/shell/Header.jsx
frontend/src/os/shell/LeftRail.jsx
frontend/src/os/surfaces/engineering/Coverage.jsx
frontend/src/os/surfaces/engineering/MarketData.jsx
frontend/src/os/surfaces/engineering/StrategyLab.jsx
frontend/src/os/workspace-state/authStore.js
```
Totals: **13 files changed · +2023 / −35 lines**.

### Verification results (final)
- `yarn build` → **PASS** (Compiled successfully · 22.3s)
- `yarn lint:testids` → **PASS** (every interactive element has a data-testid)
- `curl /api/health` → **200 OK** · version `1.1.0-stage4`
- `curl /api/version` → **200 OK**
- E2E round-trip smoke via preview URL:
  - Coverage → PARTIAL LIVE badge · real payload rendered · 0 symbols (correct)
  - Market Data → PARTIAL LIVE at page + venue + feed levels · reason ribbon
  - Strategy Lab → Compose returned a real LLM skeleton · draft persisted as `84d32cc183274d67` · nearest ran (0/0 corpus) · overall LIVE
  - Strategy Pipeline → seeded draft appeared at Stage 1 · LIVE overall
  - Role integration → admin sees Admin group + gold ADMIN chip + `LIVE · /API/AUTH/ME` label
- Backend Feature Freeze v1.1.0-stage4 — **INTACT**. Zero backend files changed in this session.

## Prioritized backlog (P0/P1/P2)

### P0 (Phase 2 close-out)
- ~~Coverage live~~ ✅
- ~~Market Data PARTIAL LIVE~~ ✅
- ~~Strategy Lab live~~ ✅
- ~~Strategy Pipeline new route~~ ✅
- ~~Real role integration~~ ✅

### P1 (next Engineering slice, still under freeze)
- **Datasets** live surface — no dedicated endpoint yet, but `coverage.symbols` + `coverage.cache` can drive a first pass.
- **Optimization** — read-only cycle browser using `/api/strategies` history (no `/api/optimize` under freeze).
- **Validation** — surface historical backtests from the KB (`/api/knowledge/statistics.positive_return_pf_gt_1`).
- **Prop Firms** and **Deployments** remain deferred (no endpoints under freeze).
- Historical **KB corpus import** — populates Strategy Pipeline champions and nearest-neighbour panel with real matches.
- Extend the CmdKPalette to include Strategy Pipeline in the jump-to-surface list.

### P2 (post-freeze · post-Sprint 3)
- Broker Connections group (waits for the backend freeze to be formally lifted).
- WSS `/stream/*` bindings for live tick, cycle, and log tails.
- Optimization launcher + Approvals bundle generation.

## Next action items
1. Import the historical KB corpus so Strategy Pipeline champions and Lab nearest-neighbour become genuinely LIVE (currently PARTIAL LIVE with zero corpus).
2. Wire Datasets, Optimization, and Validation surfaces using the coverage / strategies / knowledge endpoints that already exist.
3. Add the Strategy Pipeline route to the CmdKPalette jump list.
4. Consider a release tag `v1.1.0-stage4-p2` after the corpus import lands and the pipeline is verifiably LIVE (not partial).

## Confirmation
Backend Feature Freeze **v1.1.0-stage4** remains fully intact — this session touched only frontend files and one `.env` scaffold that was missing at session start.
