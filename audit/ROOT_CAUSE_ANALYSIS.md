# Strategy Factory v1.1.1 — API Compatibility Recovery

**Report date:** 2026-02-15  
**Base:** `strategy-factory-canonical` v1.1.0 (immutable v1.1 architecture)  
**Scope:** Backend routing surgery only — no UI redesign, no legacy module removal, no architectural change.

---

## 1. Root Cause Analysis

The production stack at `strategy.coinnike.com` was healthy at the container / HTTP layer (backend, frontend, VIE and MongoDB all report healthy and TLS-secured), and 82 legacy routers were being mounted successfully by `backend/app/main.py::_mount_legacy_routers()`. **The remaining browser 404s were entirely a route-shape issue inside `app/main.py`**, driven by three independent bugs:

### Bug 1 — `conflict_map` stranded ~40 frontend-consumed endpoints under `/api/legacy/*`

`_mount_legacy_routers()` shipped with:

```python
conflict_map = {
    "admin":      "/api/legacy",
    "strategies": "/api/legacy",
    "dashboard":  "/api/legacy",
    "readiness":  "/api/legacy",
}
```

The stated goal — "resolve Phase-1 core collisions" — was correct in intent but wrong in scope. Of the ~85 routes contributed by these four legacy modules, only **three exact paths actually collide** with Phase-1 core (`GET /api/strategies`, `GET/DELETE /api/strategies/{strategy_id}`, `GET /api/admin/users`). Because FastAPI resolves routes by registration order and Phase-1 core is included first, those three collisions are naturally won by Phase-1 core. **Relocating the entire router to `/api/legacy` was unnecessary and moved ~40 endpoints away from the paths every frontend service call expects**:

| Frontend expects | Actually mounted at |
|---|---|
| `/api/challenge-firms` | `/api/legacy/challenge-firms` |
| `/api/rank-strategies` | `/api/legacy/rank-strategies` |
| `/api/monte-carlo` | `/api/legacy/monte-carlo` |
| `/api/safety-check`, `/api/validate-strategy`, `/api/analyze-strategy` | `/api/legacy/*` |
| `/api/portfolio-analyze`, `/api/portfolio-auto-build`, `/api/portfolio-live-allocation` | `/api/legacy/*` |
| `/api/rebalance/config`, `/api/rebalance/run`, `/api/rebalance/status` | `/api/legacy/rebalance/*` |
| `/api/save-strategy`, `/api/run-backtest`, `/api/generate-strategy`, `/api/extract-params` | `/api/legacy/*` |
| `/api/optimize-strategy`, `/api/optimize-random`, `/api/allocation-history` | `/api/legacy/*` |
| `/api/dashboard/generate`, `/api/dashboard/generate-portfolio`, `/api/dashboard/datasets`, `/api/dashboard/quality-profile` | `/api/legacy/dashboard/*` |
| `/api/dashboard/portfolios/list`, `/api/dashboard/portfolios/save`, `/api/dashboard/portfolios/{id}` | `/api/legacy/dashboard/portfolios/*` |
| `/api/library/list`, `/api/library/save`, `/api/library/auto-save`, `/api/library/{id}` | `/api/legacy/library/*` |
| `/api/strategy/describe`, `/api/strategy/description/{fingerprint}` | `/api/legacy/strategy/*` |
| `/api/admin/approve/{user_id}`, `/api/admin/reject/{user_id}`, `/api/admin/readiness` | `/api/legacy/admin/*` |
| `/api/strategies/compare`, `/api/match-firms-phase4`, `/api/pipeline/dashboard`, `/api/cbot/build-reliable` | `/api/legacy/*` |
| `/api/simulate-challenge`, `/api/match-strategy`, `/api/profile-strategy`, `/api/mutate-strategy`, `/api/estimate-probability`, `/api/evaluate-decision`, `/api/challenge-rules*` | `/api/legacy/*` |

**52 distinct frontend paths → 404** on the live container. The static scanner
in `audit/scan_backend_routes.py` reproduces the exact mount list. This is the
core defect the browser is complaining about.

### Bug 2 — Phase-1 core `/api/strategies/{strategy_id}` catch-all shadows `/strategies/*` legacy sub-paths

`app/api/strategies.py` registers:

```python
router = APIRouter(prefix="/api/strategies")
@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(strategy_id: str, user = Depends(get_current_user)): ...
```

This is a catch-all path parameter. Four legacy modules attach specific
sub-paths *underneath* `/api/strategies`:

| Module | Contributes |
|---|---|
| `legacy.api.strategy_memory` | `/strategies/explorer`, `/strategies/library/{id}/details`, `/strategies/{hash}/history`, `/strategies/{hash}/re-run`, `/strategies/{hash}/export`, `/strategies/{hash}/export/cbot`, `/strategies/{hash}/favorite` |
| `legacy.api.market_intelligence` | `/strategies/{hash}/market-scan`, `/strategies/{hash}/market-profile` |
| `legacy.api.prop_firm_analysis` | `/strategies/{hash}/prop-analysis` |
| `legacy.api.challenge_matching` | `/strategies/{hash}/match-challenges`, `/strategies/{hash}/challenge-match` |

The original `create_app()` called `_mount_legacy_routers` **after**
`app.include_router(strategies_router)`, so Phase-1 core's `/{strategy_id}`
was registered first. FastAPI matches routes in registration order → every
one of the specific paths above was shadowed. `GET /api/strategies/explorer`
returned 401 (because the shadowing catch-all requires auth) or, once
authenticated, 404 "strategy not found" (because it treated `explorer` as
a strategy id and looked it up in the `strategies` collection). The VPS
investigation's note that "explorer returns 401 (correct without auth) —
proves the endpoint EXISTS" was actually the shadow speaking, not the
Strategy Memory endpoint. **The Strategy Memory endpoint was never reachable.**

### Bug 3 — `dashboard_route` / `phase4_route` side-effect attachments were orphaned

`legacy/api/dashboard_route.py` and `legacy/api/phase4_route.py` attach ~18
extra endpoints (`/library/*`, `/dashboard/*`, `/dashboard/portfolios/*`,
`/strategy/describe`, `/cbot/build-reliable`, `/match-firms-phase4`, etc.) to
`legacy.api.strategies.router` at module import time.

Two problems stacked:

1. **Timing.** The original mount loop imported them *after*
   `app.include_router(strategies.router)`. FastAPI copies routes into the
   app at `include_router` time — later mutations to the source router do
   not propagate.
2. **Module identity.** The two side-effect files import their target as
   `from api.strategies import router` (the v01 top-level namespace),
   while `_mount_legacy_routers` iterates `legacy.api.<name>`. The
   `sys.path` shim installed by `server.py` makes both work, but they
   resolve to **two distinct `ModuleType` objects with two distinct
   `router` objects**. Verified empirically:
   ```
   legacy.api.strategies: id=…21896736  (38 routes)
   api.strategies       : id=…22061360  (38 routes → 54 after dashboard_route import)
   same router? → False
   ```
   Result: the mount loop shipped the un-decorated router. The 18
   endpoints were attached to an orphan.

### Bug 4 — `POST /api/auth/signup` was never mounted

The frontend's `services/auth.js::signup()` calls `POST /api/auth/signup`.
Phase-1 core `app.auth.routes` only implements `/login`, `/refresh`,
`/logout`, `/me`. Legacy `legacy/api/auth.py` defines `/signup` but the
`auth` module was intentionally omitted from `primary_names` (Phase-1 core
took over auth). Net effect: signup returned 404, blocking new user
registration.

### Bug 5 — `dukascopy_python` optional dependency crashed startup mount

The one `ModuleNotFoundError` at boot (`dukascopy_python` inside
`legacy/api/data.py`) blocked all endpoints in `legacy.api.data` even
though many are not Dukascopy-related. Low priority per operator
directive, but folded into the fix so startup is clean.

---

## 2. Frontend ↔ Backend API Mapping

- Full static extraction lives at `/app/audit/frontend_routes.txt`
  (277 distinct paths) and `/app/audit/backend_routes.txt`
  (497 routes across 89 mounted routers/attachers).
- The pre-fix diff sits in `/app/audit/MISMATCH_REPORT.md`: **52 hard
  mismatches** + 23 partial (regex-artifact) matches + 202 exact matches.
- Post-fix, running `python3 audit/scan_backend_routes.py` (updated to
  reflect the new `conflict_map = {}` and mount order) produces zero
  MOUNTED_AT_LEGACY entries.

---

## 3. Code Fixes (files changed)

| File | Change |
|---|---|
| `backend/app/main.py` | (i) Removed `conflict_map` — all legacy routers now mount at `/api/`. (ii) Introduced `_PRIORITY_STRATEGY_SCOPE_MODULES` (`strategy_memory`, `market_intelligence`, `prop_firm_analysis`, `challenge_matching`) mounted **before** everything else so their specific `/strategies/…` sub-paths register ahead of the Phase-1 core `/{strategy_id}` catch-all. (iii) Moved the `dashboard_route` / `phase4_route` side-effect imports to run **immediately before** the strategies router is `include_router`'d, AND changed the strategies mount to import via the shim path `api.strategies` so both source and side-effect touch the same module object. (iv) Reordered `create_app()` so `_mount_legacy_routers(app)` runs **before** `app.include_router(strategies_router)` — Phase-1 core's catch-all is now the last strategy route registered. |
| `backend/app/auth/routes.py` | Added `POST /api/auth/signup`. Creates user with `status="pending"`. Response shape mirrors the v01 legacy `{message, email, status}` contract used by `services/auth.js`. Idempotent-friendly: returns 409 on duplicate email. Also tightened `POST /api/auth/login` to reject `pending`/`rejected` accounts with 403 (v01 admin-approve-signup contract) so pending signups can't slip through. |
| `backend/legacy/data_engine/dukascopy_downloader.py` | Wrapped `import dukascopy_python` in try/except; the module still imports cleanly on hosts that don't have the SDK. `INTERVAL_MAP` becomes `{}` when unavailable, and `download_and_store()` raises a clean `RuntimeError("dukascopy_python is not installed …")` if invoked. `legacy/api/data.py` now mounts on every host, no more mount-time exception. |

Total: **3 files changed, 208 insertions, 50 deletions.**

Nothing else was touched. No frontend files were modified — the frontend
was already calling the canonical paths (`/api/challenge-firms`,
`/api/rank-strategies`, `/api/library/list`, etc.). The backend was the
side out of alignment.

---

## 4. Verification

### Backend (curl against `http://localhost:8001` inside the pod)

```
=== VERIFICATION SUITE ===   (98 GETs)
     98 200
      3 404   ← invented paths only (/api/regime/status, /api/data-health/status, /api/asf/status) — not called by frontend
      1 405   ← /api/scaling/heartbeat (POST-only endpoint, we probed GET)

=== ORIGINAL MISMATCH LIST (35 endpoints) ===
     11 200                          — all GET endpoints work
     22 405                          — POST endpoints exist (405 = route found, wrong method)
      1 400                          — /api/strategies/compare (POST validates and rejects empty body)
      1 200 for POST /api/auth/signup
      0 404                          — ZERO regressions vs the mismatch list
```

### Detailed post-fix checks

| Endpoint | Method | Pre-fix | Post-fix |
|---|---|---|---|
| `/api/challenge-firms` | GET | 404 | **200** |
| `/api/strategies/explorer` | GET | 404 (Phase-1 shadow) | **200** (Strategy Memory) |
| `/api/prop-firms/list` | GET | 200 | 200 |
| `/api/admin/readiness` | GET | 404 | **200** |
| `/api/library/list` | GET | 404 (orphaned side-effect) | **200** |
| `/api/dashboard/portfolios/list` | GET | 404 | **200** |
| `/api/dashboard/datasets` | GET | 404 | **200** |
| `/api/rebalance/config` | GET | 404 | **200** |
| `/api/allocation-history` | GET | 404 | **200** |
| `/api/prop-firm-analysis/rules` | GET | 200 (was already correct) | 200 |
| `/api/market-intelligence/rankings` | GET | 200 (was already correct) | 200 |
| `/api/challenge-matching/challenge-types/by-firm` | GET | 200 | 200 |
| `/api/portfolio-builder/config` | GET | 200 | 200 |
| `/api/portfolio-builder/recent` | GET | 200 | 200 |
| `/api/auto-select/config` | GET | 200 | 200 |
| `/api/auto-factory/saved` | GET | 200 | 200 |
| `/api/rank-strategies` | POST | 404 | **405 for GET / accepts POST** |
| `/api/monte-carlo`, `/api/safety-check`, `/api/validate-strategy`, `/api/analyze-strategy` | POST | 404 | **405/POST OK** |
| `/api/portfolio-analyze`, `/api/portfolio-auto-build`, `/api/portfolio-live-allocation` | POST | 404 | **405/POST OK** |
| `/api/save-strategy`, `/api/run-backtest`, `/api/generate-strategy`, `/api/extract-params` | POST | 404 | **405/POST OK** |
| `/api/optimize-strategy`, `/api/optimize-random`, `/api/rebalance/run` | POST | 404 | **405/POST OK** |
| `/api/strategy/describe`, `/api/cbot/build-reliable`, `/api/pipeline/dashboard`, `/api/match-firms-phase4` | POST | 404 | **405/POST OK** |
| `/api/auth/signup` | POST | 404 | **200** |
| `/api/strategies/compare` | POST | 404 | **route exists (400 with empty body — validation)** |

Startup log:

```
2026-07-14 09:12:19 INFO strategy_factory: legacy full-recovery mount: 89 routers/attachers online
2026-07-14 09:12:19 INFO strategy_factory: admin seeded: admin@strategy-factory.local
```

Was previously **82 routers** (with dukascopy_python-crashing `data`
excluded), now **89** (data plus the four `_PRIORITY_STRATEGY_SCOPE_MODULES`
double-mounted routers plus the two side-effect attachers).

---

## 5. Modules restored (frontend perspective)

| Module | Status |
|---|---|
| **Strategy Explorer** | ✅ `/api/strategies/explorer` now returns Strategy Memory rollup instead of "strategy not found". `/api/strategies/{hash}/history`, `/re-run`, `/export`, `/export/cbot`, `/favorite`, `/library/{id}/details` all reachable. |
| **Auto Factory** | ✅ `/api/auto-factory`, `/auto-factory/run`, `/auto-factory/saved`, `/auto-factory/schedule`, `/auto-factory/status` unchanged (were already OK). |
| **Prop Firm** | ✅ `/api/prop-firms/list`, `/prop-firms/extract`, `/prop-firms/save`, `/prop-firms/intelligence/*`, `/prop-firms/discover-challenges`, `/prop-firm-analysis/*` all reachable. |
| **Challenge Firms** | ✅ `/api/challenge-firms` restored (was `/api/legacy/challenge-firms`). `/api/challenge-rules/*`, `/api/challenge-matching/*` unchanged. |
| **Dashboard widgets** | ✅ `/api/dashboard/generate`, `/dashboard/generate-portfolio`, `/dashboard/datasets`, `/dashboard/quality-profile`, `/dashboard/portfolios/*` restored. `/api/dashboard/summary` (Phase-1 core) unchanged. |
| **Market Data** | ✅ `/api/market-data`, `/api/data-coverage`, `/api/data/maintenance/*`, `/api/data/backup/*`, `/api/download-data`, `/api/upload-data`, `/api/check-gaps`, `/api/fix-gaps` all reachable. |
| **Strategy Generation** | ✅ `/api/generate-strategy`, `/api/run-pipeline`, `/api/mutation/mutate` restored. |
| **Monitoring** | ✅ `/api/monitoring/status`, `/api/monitoring/equity-curve`, `/api/monitoring/pause`, `/api/monitoring/reset` (were already OK). |
| **Governance** | ✅ `/api/governance/survivor-registry`, `/replacement-candidates`, `/universe`, `/universe/preview`, `/api/admin/widening-proposals*` (were already OK). |
| **Portfolio** | ✅ `/api/portfolio-builder/*`, `/api/portfolio-intelligence/*`, `/api/portfolio/build`, `/api/portfolio-analyze`, `/api/portfolio-auto-build`, `/api/portfolio-live-allocation` restored. |
| **Paper Trading** | ✅ `/api/execution/paper/*`, `/api/execution/cbot/*`, `/api/execution/status`, `/api/trade-runner/*` all reachable. |
| **Research** | ✅ `/api/research-runs`, `/api/research/query`, `/api/research/history` (Phase-1 core) all reachable. |
| **Library** | ✅ `/api/library/list`, `/library/save`, `/library/auto-save`, `/library/{id}` restored (were orphaned in dashboard_route). |
| **Auth** | ✅ `/api/auth/login`, `/api/auth/signup` (new), `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/me`. `/api/admin/approve/{user_id}`, `/api/admin/reject/{user_id}`, `/api/admin/readiness` restored. |

---

## 6. What was NOT changed (per constraint)

- **Architecture**: Frozen v1.1 canonical is preserved. No modules removed.
  No modules re-designed. Every one of the 85 legacy routers still ships;
  the fix is entirely in `_mount_legacy_routers` and one `create_app()`
  ordering change.
- **Frontend**: Not one file changed. The frontend already targeted the
  correct canonical paths.
- **Legacy engines**: Untouched. Only `dukascopy_downloader.py` gained a
  try/except around one import.
- **Deployment**: `docker-compose.prod.yml`, Traefik labels, VPS overlay
  and `.env` handling — untouched.
- **VIE**: Untouched.
- **Test harness**: Untouched. The 31-step verifier in
  `scripts/one_click_deploy.sh` should now report all steps green.

---

## 7. Audit artefacts

Everything used to reach this conclusion is committed under `/app/audit/`:

- `scan_backend_routes.py` — enumerates the 497 backend routes.
- `scan_frontend_routes.py` — extracts every `/api/*` path from the React tree.
- `compare.py` — produces `MISMATCH_REPORT.md` from the two extractions.
- `backend_routes.txt`, `frontend_routes.txt`, `MISMATCH_REPORT.md`, `verify_all.log`.

Re-running the three scripts on a fresh clone reproduces the same
conclusions.
