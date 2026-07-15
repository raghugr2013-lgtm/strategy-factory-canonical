# Strategy Factory Canonical v1.1 — API Compatibility Recovery

## Original Problem Statement

Production stack at `strategy.coinnike.com` is healthy at the container / HTTP layer, but the frontend reports multiple 404s (`/api/challenge-firms`, `/api/strategies/explorer`, `/api/readiness`, `/api/library/list`, `/api/dashboard/generate`, `/api/rank-strategies`, `/api/monte-carlo`, etc.) even though the backend claims 82 legacy routers are mounted. Deliver a complete audit and code fix restoring full frontend/backend compatibility WITHOUT redesigning the app or removing legacy modules. Preserve the canonical v1.1 architecture.

## Architecture

- **Frontend**: React 19 + v01 Command OS (CommandShell, TopTabBar, LifecycleRail, StatusRail, AuthGate).
- **Backend**: FastAPI 0.116 + MongoDB 6. Phase-1 core (auth + admin + strategies CRUD + research + dashboard/summary + health) + 83 legacy v01 routers.
- **VIE (Vendor Independent Engine)**: Standalone gateway (6 providers: OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi).
- **Auth**: JWT + refresh-token rotation + 5-role RBAC + admin-approve signup.
- **Deploy**: Docker Compose (local + VPS overlay with Traefik).

## User Personas

- **Admin** — approves signups, manages users, monitors readiness, runs factory supervisor.
- **Developer / Operator / Researcher / Viewer** — 5-role RBAC on all endpoints.

## Core Requirements (static)

1. Preserve the canonical v1.1 architecture.
2. Do NOT redesign or remove any legacy module.
3. Every frontend `/api/*` call must reach a backend handler (no router-level 404s).
4. Backend must expose `/api/auth/signup` (v01-compatible pending-account flow).
5. Backend startup must not fail when optional dependencies (dukascopy_python) are absent.

## What's Been Implemented — 2026-02-15

### Routing surgery in `backend/app/main.py`
- Removed the `conflict_map` that stranded ~40 endpoints under `/api/legacy/*`.
- Introduced `_PRIORITY_STRATEGY_SCOPE_MODULES` (strategy_memory, market_intelligence, prop_firm_analysis, challenge_matching) mounted first so `/api/strategies/*` specific paths beat the Phase-1 core `/{strategy_id}` catch-all.
- Moved `_mount_legacy_routers()` to run BEFORE `include_router(strategies_router)` in `create_app()`.
- Fixed the `dashboard_route` / `phase4_route` side-effect timing AND module-identity bugs — side-effects now run immediately before strategies is mounted, and strategies is imported via the same `api.strategies` shim path the side-effects mutate.

### Signup added to Phase-1 core auth
- New `POST /api/auth/signup` — creates user with `status="pending"` and returns v01-shape `{message, email, status}`.
- Login endpoint hardened to reject `pending` / `rejected` accounts with 403 (v01 admin-approve-signup contract).

### Optional-dependency guardrail
- `legacy/data_engine/dukascopy_downloader.py` wraps the `dukascopy_python` import in try/except. The module imports cleanly without the SDK; `download_and_store()` raises a clean `RuntimeError` only when actually invoked. Startup log no longer prints the mount failure.

### Verification
- 35/35 backend regression tests pass (`/app/backend/tests/test_api_compatibility.py`).
- 89 legacy routers/attachers online (was 82 pre-fix).
- Every one of the 25 originally-404 GET endpoints returns 200 with a fresh JWT.
- Every previously-stranded POST endpoint returns 422/validation (route mounted) instead of 404.

## Files Changed

| File | Purpose |
|---|---|
| `backend/app/main.py` | Removed conflict_map, added _PRIORITY_STRATEGY_SCOPE_MODULES, reordered create_app, fixed dashboard_route/phase4_route mount |
| `backend/app/auth/routes.py` | Added POST /api/auth/signup; hardened login to reject pending accounts |
| `backend/legacy/data_engine/dukascopy_downloader.py` | Optional dukascopy_python import; RuntimeError only when actually invoked |
| `audit/*` | Full RCA, mismatch report, scanner scripts, backend & frontend route dumps, verification log |
| `backend/tests/test_api_compatibility.py` | 35 regression tests covering the full API-compat contract |
| `memory/test_credentials.md` | Admin credential reference for testing agent |

## Backlog / Next Priorities

- **P0 (done)**: Restore all previously-404 canonical `/api/*` paths.
- **P0 (done)**: Fix Phase-1 core `/api/strategies/{strategy_id}` shadow of Strategy Memory `/explorer`.
- **P0 (done)**: Restore `dashboard_route` + `phase4_route` side-effect endpoints.
- **P0 (done)**: Add `/api/auth/signup`.
- **P0 (done)**: v1.2.0-alpha2 Phase A — outcome-event ledger, AI Workforce telemetry, design doc.
- **P0 (done, 2026-02-15)**: v1.2.0-alpha2 Phase B — Continuous Learning Supervisor + Strategy Lineage + Outcome-conditioned Retrieval + AI Workforce Router. 29 Phase B tests + 32 Phase A tests + 35 baseline = **96/96 passing**. Router mount count unchanged at 92 (strictly additive).
- **P1**: Make `dukascopy_python` truly optional (done — startup clean).
- **P1 (alpha3)**: Dashboard Mosaic — `GET /api/dashboard/health-mosaic` + `MosaicRail` frontend consuming the new learning/ai-workforce metrics endpoints.
- **P1 (alpha3)**: Portfolio Intelligence injection block (`engines/knowledge/portfolio_block.py`) hooked into `strategy_engine._try_llm_generation` above the prior-knowledge block.
- **P1 (alpha3)**: Frontend Learning tab — event stream + lineage tree viewer.
- **P2**: Delete stale `/app/backend/tests/backend_test.py` which uses obsolete admin password.
- **P2**: Add pytest-based nightly regression run in CI targeting the same test files.
- **P3**: Consider a periodic cleanup job for `TEST_signup_*` users created by the compat test-suite.
- **P3**: Frontend UI smoke test (Playwright) covering Dashboard → Explorer → Prop Firm → Challenge Firms → Library → Portfolio Builder → Trade Runner navigation with the seeded admin.

## Phase B Files Added (2026-02-15)

| File | Purpose |
|---|---|
| `backend/legacy/engines/learning/config.py` | Env-driven thresholds (PF/DD/trades/WR/scheduler/retrieval/workforce) |
| `backend/legacy/engines/learning/supervisor.py` | Continuous Learning Supervisor + scheduler |
| `backend/legacy/engines/learning/lineage.py` | Strategy-lineage stamper across `strategies`+`strategy_library`+`archive` |
| `backend/legacy/engines/ai_workforce/router.py` | AI Workforce Router (opt-in failover) |
| `backend/legacy/engines/ai_workforce/scorer.py` | Per-provider quality scorer (60s cache) |
| `backend/legacy/engines/knowledge/outcome_conditioning.py` | Outcome-conditioned retrieval boost |
| `backend/tests/test_v1_2_0_alpha2_phase_b.py` | 29 regression tests |

## Phase B Files Modified (additive only)

| File | Change |
|---|---|
| `backend/legacy/engines/learning/__init__.py` | Export new modules |
| `backend/legacy/engines/ai_workforce/__init__.py` | Export router + scorer |
| `backend/legacy/engines/knowledge/retriever.py` | Call `apply_boosts` after TF-IDF pass |
| `backend/legacy/engines/llm_runner.py` | Delegate to router when `AI_WORKFORCE_FAILOVER=true` |
| `backend/legacy/api/learning.py` | 9 new endpoints (cycles/metrics/config/scheduler/lineage-detail) |
| `backend/legacy/api/ai_workforce.py` | 4 new endpoints (router-config/metrics/quality/route-test) |
| `backend/app/main.py` | Auto-start scheduler on boot when env flag set |
| `docs/V1.2.0_ALPHA2_DESIGN.md` | Section 10 — Phase B shipped |

## VPS Deployment Recovery Steps (for the user)

The GitHub repository has NOT been pushed automatically (per user request — "I will review and push"). To ship this fix to strategy.coinnike.com:

```bash
# 1. On your workstation
git fetch origin
git checkout main
git merge --ff-only <this branch's commit sha>
git push origin main

# 2. On the VPS
cd /opt/strategy-factory   # or wherever the checkout lives
git pull
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml build factory-backend
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml up -d factory-backend
./infra/scripts/health.sh
```

Post-deploy health check should show `legacy full-recovery mount: 89 routers/attachers online` in the backend container log.
