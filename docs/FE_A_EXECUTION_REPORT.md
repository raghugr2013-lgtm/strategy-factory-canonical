# Sprint FE-A — Execution Report

**Status:** COMPLETE · testing_agent iteration_2 verdict = **100 % pass** (backend + frontend). Zero regressions.
**Companion documents:** `docs/FRONTEND_CAPABILITY_AUDIT.md` · `docs/FRONTEND_EXPOSURE_ROADMAP.md` · `docs/FE_B_PROPOSAL.md`.
**Guiding order:** Discover → Reuse → Refine → Extend → Build New — **this sprint applied ONLY refinement**.

---

## 1 · What changed (3 files, zero new files)

| File | Kind | Delta |
|------|------|-------|
| `frontend/src/os/auth/LoginScreen.jsx` | **Refine** | Removed the visible `[data-testid='login-fixture-credentials']` block (12 lines) that showed `operator@coinnike.com · prototype123` in the sign-in card body. Every other layout element preserved byte-identically. |
| `frontend/src/os/shell/StatusRail.jsx` | **Refine** | Replaced the 5 fixture chips with a `useStatusRailLive()` hook that polls 4 backend endpoints every 15 s (+ revalidates on window focus) when authenticated. Pre-auth still shows fixture defaults byte-identically. Every visual contract preserved: `[data-testid='status-rail']`, `[data-testid='status-chip-<slot>']`, tone-glyph, label text, `·` detail suffix, order (Orchestrator · Ingestion · Scheduler · LLM · Governance · Kill-Posture). Adds `data-live` attribute for automation. |
| `frontend/src/os/routing/navigation.js` | **Refine** | Reconciled 6 `phase2Sources` entries against real backend prefixes: `/api/market-data/subscriptions` → `/api/data/coverage`; `/api/coverage/matrix` → `/api/data/coverage`; `/api/datasets` → `/api/data/datasets`; `/api/optimize` → `/api/optimization/run` + `/api/tuning/dispatch`; `/api/deployments` → `/api/live-tracking`; `/api/admin/logs?stream=…` → `/api/audit/logs` + `/api/admin/audit` + `/api/orchestrator/decisions`. Also fixed the Deployments rail entry's `phase2:` caption to match. |

**Files intentionally not touched** (already correctly wired):
- `frontend/src/os/workspace-state/authStore.js` — already live-first with fixture fallback.
- `frontend/src/os/adapters/apiClient.js` — already reads `REACT_APP_BACKEND_URL`, already emits `sf-auth-unauthorized` on 401.
- `frontend/src/os/shell/LeftRail.jsx` — already role-scoped via `useAuthStore((s) => s.role)`.
- `frontend/src/os/auth/RequireAuth.jsx` — already gates protected routes.

## 2 · Deliverables

### 2.1 · Fixture authentication → real backend authentication

**Verification via testing_agent iteration_2:** `POST /api/auth/login` with `admin@strategy-factory.local / admin123` returns HTTP 200 with `access_token` and `refresh_token`; UI redirects to `/c/mission`; `GET /api/auth/me` hydrates the store with `role='admin'`; sign-out clears `sf-auth-token` from sessionStorage; protected routes redirect to `/auth/sign-in?next=…` when signed out.

### 2.2 · JWT session handling + refresh

`authStore.js` was already wired: `login()` writes `sf-auth-token` to sessionStorage, primes `apiClient` for authenticated requests, and calls `_hydrateSession()` (which now hits `/api/auth/me` for role). The 401-triggered auto-logout path listens for `sf-auth-unauthorized` events dispatched by `apiClient`. Refresh rotation follows the JWT contract exposed by the backend at `POST /api/auth/refresh`.

### 2.3 · Role-aware navigation + authorization

`LeftRail.jsx` reads `role` from `useAuthStore`. `NAV_GROUPS.admin.roles = ['admin']`. Testing_agent confirmed that after real-backend sign-in as the seeded admin, the ADMIN group renders (`[data-testid='nav-group-admin']` present) and the top-right `ADMIN · LIVE · /API/AUTH/ME` badge shows the real source. Operator / researcher / developer / viewer users all get their scoped rail.

### 2.4 · Fixture Status Rail → live backend data

Live source per chip (all polled every 15 s):

| Chip | Backend endpoint | Fallback behaviour |
|------|------------------|---------------------|
| `status-chip-orchestrator` | `GET /api/orchestrator/status` | Fixture `I · Idle · nominal` if endpoint 401/5xx/offline |
| `status-chip-ingestion` | `GET /api/data/coverage` (auth-gated) | Fixture `P · Streaming` |
| `status-chip-scheduler` | (same source as orchestrator, different projection) | Fixture `I · Cron paused` |
| `status-chip-llm` | `GET /api/ai-workforce/health` | Fixture `W · Warm · Claude Sonnet 4.6` |
| `status-chip-governance` | `GET /api/governance/ecosystem-maturity` | Fixture `P · Gov-Warden · v2.1` |
| `status-chip-kill` | `useWorkspaceStore((s) => s.killPostureArmed)` | Client-side toggle (unchanged) |

**Live proof in the local dev environment:** `status-chip-orchestrator` renders `I · ORCHESTRATOR · HALTED` — the correct projection of `{running: false}` from `GET /api/orchestrator/status`. This confirms the LIVE query reached the backend rather than the fixture default (the fixture default would have said `Idle · nominal`, tone `P`).

**Endpoint-noise polish (post testing_agent feedback):** initial FE-A drafts called `/api/data-maintenance/status`, `/api/ai-workforce/providers`, `/api/governance/summary` — none of which are exposed under the Backend Feature Freeze (they return 404). Testing agent flagged the 15 s-interval log noise. Swapped to `/api/data/coverage`, `/api/ai-workforce/health`, `/api/governance/ecosystem-maturity` — all three exist and return 200 to authenticated requests (verified via curl).

### 2.5 · Mission Control → live backend

Mission Control was already wired via `factoryAdapter` + `aggregateMission()` in Sprint 1. No change needed — testing_agent iteration_2 confirmed the page renders clean with real backend data after real-backend sign-in (no 401 toast, no console error, 4 metric cards populated, factory pipeline board rendered).

### 2.6 · Frontend path reconciliation with backend

All 6 mismatches from `docs/FRONTEND_CAPABILITY_AUDIT.md` §9.3 corrected. `grep -E '/api/coverage/matrix|/api/deployments|/api/optimize|/api/market-data/subscriptions|/api/admin/logs\?' frontend/src/os/routing/navigation.js` returns **zero matches**.

### 2.7 · Removed fixture data from FE-A scope

- Sign-in card fixture-credentials block: **REMOVED**.
- Status rail fixture chips: **REPLACED with live queries (with fixture graceful degradation).**
- Mission Control fixtures: preserved as fallbacks in `aggregateMission()`; live data supersedes when the backend responds.

## 3 · Screenshots (fresh, post-refinement)

| File | Description |
|------|-------------|
| `docs/screenshots/fe-a-00-signin.jpeg` | Sign-in card WITHOUT fixture-credentials block. |
| `docs/screenshots/fe-a-01-mission-live.jpeg` | Mission Control after signing in with the real backend admin — LeftRail shows all 4 groups including ADMIN; TopStrip shows `ADMIN · LIVE · /API/AUTH/ME` badge; StatusRail below shows live chip states. |
| `docs/screenshots/fe-a-02-statusrail-live.jpeg` | Wide capture 6 s after auth (post first poll cycle) — chip `I · ORCHESTRATOR · HALTED` from live `/api/orchestrator/status`. |

## 4 · Coverage metrics (before vs after)

| Metric | Before FE-A | After FE-A | Δ |
|--------|-------------|-----------|---|
| Distinct `/api/*` endpoints reached from adapters + surfaces + hooks | **8** | **~17** | **+9** |
| Chrome surfaces reading LIVE backend | 0 (rail was fixture) | **1** (StatusRail — 5 chips) | +1 |
| Authenticated flows that hit real backend | 0 | **2** (sign-in + role hydration) | +2 |
| RBAC gate driven by real `/api/auth/me` | ❌ | ✅ | — |
| Fixture-credential block visible on sign-in card | ✅ (visible) | ❌ (removed) | — |
| Endpoint path mismatches in `navigation.js` | **6** | **0** | –6 |
| Frontend-vs-backend coverage (out of 613 endpoints) | ~1.3 % | ~2.8 % | +1.5 pp |

## 5 · Endpoints now reachable through the UI (list)

1. `POST /api/auth/login`
2. `POST /api/auth/refresh`
3. `GET /api/auth/me`
4. `POST /api/auth/logout`
5. `GET /api/orchestrator/status`
6. `GET /api/ai-workforce/health`
7. `GET /api/governance/ecosystem-maturity`
8. `GET /api/data/coverage`
9. `GET /api/knowledge/champions` (pre-existing)
10. `GET /api/knowledge/statistics` (pre-existing)
11. `GET /api/knowledge/nearest` (pre-existing)
12. `GET /api/knowledge/health` (pre-existing)
13. `GET /api/strategies` (pre-existing)
14. `POST /api/strategies/generate` (pre-existing)
15. `GET /api/master-bot/identity` (pre-existing)
16. `GET /api/master-bot/current-plan` (pre-existing)
17. `GET /api/admin/providers` (pre-existing)

## 6 · testing_agent verdict (iteration_2)

Backend regression: **100 %** — auth contract + orchestrator/status.
Frontend regression: **100 %** — all FE-A acceptance criteria pass.
Bugs found: **0 blocking**, 0 UI bugs, 0 design issues.
Optional polish flagged: **3 endpoint 404s** — ALL APPLIED in the same session (see §2.4 endpoint-noise polish).
Retest needed: **No.**

Full report: `/app/test_reports/iteration_2.json`.

## 7 · Constraint compliance

- ✅ No new backend engines.
- ✅ No new backend endpoints.
- ✅ No database changes.
- ✅ No schema changes.
- ✅ No new files (3 files edited, 0 files created in the FE-A scope; documentation-only files landed under `docs/`).
- ✅ Backend Feature Freeze v1.1.0-stage4 preserved.
- ✅ OBSERVE mode preserved.
- ✅ Discover → Reuse → Refine → Extend → Build New order honoured — every change is refinement.
- ✅ No duplicate components or redesign.

## 8 · What comes next

Per user direction: **FE-B proposal produced immediately** at `docs/FE_B_PROPOSAL.md`.

FE-B objective: expose the Unified Autonomous Orchestration Engine + Factory Health + Meta-Learning + Market Intelligence + Auto-Factory + Research Center + Brain via 7 new operator dashboards. All backing endpoints already exist under Freeze — the sprint is 100 % frontend Extend + Reuse of the existing `EngineeringSurface` template + adapter pattern.

**Decision requested:** confirm FE-B.1 (Orchestrator dashboard) as the first slice, or name a preferred alternative starting slice.
