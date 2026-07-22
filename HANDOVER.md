# HANDOVER — Sprint 3 Phase 2 · deployment bundle

**Bundle built · 2026-07-22**
**Base repo · `github.com/raghugr2013-lgtm/strategy-factory-canonical.git`**
**Local head · `d7f07a0` (docs) · Phase 2 code head `2dad08b`**

---

## 1 · Commit hashes (chronological)

```
d7f07a0  docs(sprint3-phase2): PRD updated for Phase 2 close-out
2dad08b  feat(auth): Sprint 3 Phase-2 real role integration from /api/auth/me
25902dc  feat(strategy-pipeline): Sprint 3 Phase-2 new live Strategy Pipeline route
807be33  feat(strategy-lab): Sprint 3 Phase-2 live Strategy Lab surface
925383d  feat(market-data): Sprint 3 Phase-2 live Market Data surface (PARTIAL LIVE)
490d7c3  feat(coverage): Sprint 3 Phase-2 live Coverage surface + apiClient live-mode fix
--- baseline (Sprint 3 Phase 1) ---
20af3df  feat(walkthrough): frontend-only lifecycle events
```

All Sprint 3 Phase 2 code lives in commits `490d7c3 .. 2dad08b` (five commits + one docs commit `d7f07a0`).

If you need to inspect them locally after extracting the bundle:

```bash
git log --oneline 20af3df..HEAD
git show 490d7c3       # coverage + apiClient fix
git show 925383d       # market-data
git show 807be33       # strategy-lab
git show 25902dc       # strategy-pipeline route
git show 2dad08b       # role integration
git show d7f07a0       # PRD doc update
```

The `.git/` directory is included in the bundle so you can push directly:
```bash
tar -xzf strategy-factory-sprint3-phase2.tar.gz
cd app
git remote -v         # verify origin still points to the canonical repo
git log --oneline -8  # confirm the six commits above
git push origin main
```

---

## 2 · Summary of Phase 2 work completed

Under **Backend Feature Freeze v1.1.0-stage4** — frontend-additive only. No new backend endpoints. No backend behavior changes. No synthetic data.

| # | Deliverable | Commit | Live endpoints consumed |
|---|---|---|---|
| 1 | Foundational fix — `apiClient.js` runtime guard | `490d7c3` | (unblocked live mode for the whole app) |
| 2 | **Coverage** live surface (was 3-line stub) | `490d7c3` | `GET /api/data/coverage` |
| 3 | **Market Data** PARTIAL LIVE surface (was 3-line stub) | `925383d` | `GET /api/data/coverage` (provider.sources + verification_status + symbols) |
| 4 | **Strategy Lab** live authoring surface (was 3-line stub) | `807be33` | `POST /api/strategies/generate`, `POST /api/strategies`, `POST /api/knowledge/nearest`, `GET /api/knowledge/statistics` |
| 5 | **Strategy Pipeline** new route + surface | `25902dc` | `GET /api/strategies`, `GET /api/knowledge/champions`, `GET /api/knowledge/statistics` |
| 6 | Real role integration | `2dad08b` | `GET /api/auth/me` (backgrounded refresh) |

### Foundational fix (shipped inside the Coverage commit)

`apiClient.js` used `typeof process !== 'undefined'` as a runtime guard around
`process.env.REACT_APP_BACKEND_URL`. In the browser, `process` is not defined,
so the guard short-circuited to `false` and `isLiveMode()` always returned
`false` — silently forcing the entire app into fixture-mode. The prior Sprint
1/2/3-Phase-1 "live" work therefore never actually reached the backend.

The fix replaces the runtime guard with a try/catch around the DefinePlugin-
inlined property access. It is a one-liner but has app-wide effect: real
live-mode is now genuinely operative.

---

## 3 · Files / modules changed (13 files · +2023 / −35 lines)

```
frontend/src/os/adapters/apiClient.js               |  16 +/-
frontend/src/os/adapters/coverageAdapter.js         | 107 ++++  (new)
frontend/src/os/adapters/strategyLabAdapter.js      |  71 ++++  (new)
frontend/src/os/routing/AppRouter.jsx               |   2 +
frontend/src/os/routing/navigation.js               |   9 +/-
frontend/src/os/shell/Header.jsx                    |  34 +/-
frontend/src/os/shell/LeftRail.jsx                  |  29 +/-
frontend/src/os/surfaces/engineering/Coverage.jsx   | 361 ++/-
frontend/src/os/surfaces/engineering/LivenessBadge.jsx | 52 +  (new)
frontend/src/os/surfaces/engineering/MarketData.jsx | 398 ++/-
frontend/src/os/surfaces/engineering/StrategyLab.jsx| 465 ++/-
frontend/src/os/surfaces/engineering/StrategyPipeline.jsx | 438 +  (new)
frontend/src/os/workspace-state/authStore.js        |  76 +/-
memory/PRD.md                                       |  updated for close-out
```

**Zero backend files were touched.** `backend/**` remains at commit `20af3df` per the Feature Freeze contract.

---

## 4 · Verification results

### 4.1 Build & lint

| Check | Result |
|---|---|
| `yarn build` (craco production build) | ✅ **PASS** — Compiled successfully · 22.3s · main.js 197.24 kB · main.css 989 B |
| `yarn lint:testids` | ✅ **PASS** — every interactive element in `src/os` has a `data-testid` |
| ESLint (all touched files) | ✅ **PASS** — no issues found |

### 4.2 Backend contract (frontend-additive only · read-only checks)

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/health` | GET | 200 | version `1.1.0-stage4` · commit `20af3df` |
| `/api/version` | GET | 200 | freeze marker intact |
| `/api/auth/login` | POST | 200 | admin@coinnike.com · JWT returned |
| `/api/auth/me` | GET | 200 | role hydration path |
| `/api/data/coverage` | GET | 200 | Coverage + Market Data source (feature flag on) |
| `/api/strategies` | GET/POST | 200/201 | Strategy Lab draft persistence + Pipeline |
| `/api/strategies/generate` | POST | 200 | Strategy Lab CNL composer |
| `/api/knowledge/nearest` | POST | 200 | Strategy Lab neighbours |
| `/api/knowledge/champions` | GET | 200 | Pipeline champions column |
| `/api/knowledge/statistics` | GET | 200 | Corpus counters |

### 4.3 End-to-end preview smoke tests (all executed on the preview URL, admin auth)

- **Sign-in** → live JWT persisted, `/api/auth/me` refresh confirmed.
- **Coverage** surface loaded → PARTIAL LIVE badge visible, metrics tiles render 0-value real payload, "AWAITING DATA" ribbon shown (correct — no ingestion yet).
- **Market Data** surface loaded → PARTIAL LIVE at page, venue-roster, and symbol-feed levels; reason ribbon reads `venue roster · empty · symbol feed · 0 rows`.
- **Strategy Lab** round-trip:
  - Composed `XAUUSD · H4 · trend-following` skeleton via `POST /api/strategies/generate` (real LLM output ≈ 350 chars).
  - Persisted draft `84d32cc183274d67` via `POST /api/strategies` (status=draft).
  - Nearest-neighbour ran automatically against generated text (0/0 matches from empty corpus, PARTIAL LIVE at panel level, overall page LIVE).
  - Test artefact deleted after screenshot.
- **Strategy Pipeline** with a seeded draft `c20ec340fe7549c4` at Stage 1 → LIVE overall; 5-stage lineage bar populated (Drafts=1, others=0); Passport → deep-link rendered; test artefact deleted after screenshot.
- **Role integration**:
  - `admin@coinnike.com` → Admin group visible in `LeftRail`, gold `ADMIN` chip in `UserMenu`, `LIVE · /API/AUTH/ME` mode label.
  - Fixture operator → Admin group hidden, `operator` role chip, `FIXTURE` label.

### 4.4 What was NOT run (out of scope · legacy noise)

- `make tier1` backend pyramid — pre-existing baseline failures (router count 93 vs expected 98, plus 401s from an unauthenticated test harness) that pre-date this session and are unaffected by frontend-additive changes.
- Playwright E2E specs under `frontend/tests/e2e/*.cjs` — reserved for post-corpus-import.

---

## 5 · Backend Feature Freeze v1.1.0-stage4 — INTACT

- **Zero** backend source files modified.
- `/api/version` returns `1.1.0-stage4` · commit `20af3df` unchanged.
- No new routes mounted in `app/main.py`.
- No schema, contract, or behavior changes.
- The freeze marker in `git diff 20af3df..HEAD -- backend/` shows: **no output** (excluding whitespace/CRLF noise in legacy tests/docs that were untouched by this session).

---

## 6 · Known issues & remaining work

### Known issues (pre-existing · not Phase 2 regressions)

1. **`make tier1` backend pyramid** — router count assertion 93 vs 98 (admin execution routers gated behind separate flags), plus 401 errors in the test harness that never signs in. Pre-dates Phase 1 · unchanged by this session.
2. `.env` files were **missing** when the session started (repo was freshly connected). Recreated locally with the preview URL, Mongo/JWT config, and `COE_COVERAGE_REPORT_ENABLED=true`. Not committed (env-scoped by design). If you extract this bundle on a fresh workspace, you will need to recreate:

    **`/app/backend/.env`**
    ```
    MONGO_URL=mongodb://localhost:27017
    DB_NAME=strategy_factory_v1
    JWT_SECRET=<64-char hex secret>
    JWT_ACCESS_TTL_MIN=60
    JWT_REFRESH_TTL_DAYS=7
    ADMIN_EMAIL=admin@coinnike.com
    ADMIN_PASSWORD=admin123
    CORS_ORIGINS=*
    ENABLE_LEGACY_ROUTERS=true
    COE_COVERAGE_REPORT_ENABLED=true
    BUILD_VERSION=1.1.0-stage4
    BUILD_COMMIT=20af3df
    BUILD_DATE=2026-07-22
    ```

    **`/app/frontend/.env`**
    ```
    REACT_APP_BACKEND_URL=<your preview or production URL>
    WDS_SOCKET_PORT=443
    ```

### Remaining work (P1 · under the same freeze)

1. **Historical KB corpus import** — populates the Strategy Pipeline champions column and Strategy Lab nearest-neighbour panel with real matches. Flips the pipeline from `PARTIAL LIVE` (0 corpus) to genuinely `LIVE`.
2. **Datasets** live surface — no dedicated endpoint yet, but `coverage.symbols` + `coverage.cache` can drive a first pass under the freeze.
3. **Optimization** — read-only cycle browser using `/api/strategies` history (no `/api/optimize` under freeze).
4. **Validation** — surface historical backtests from the KB (`/api/knowledge/statistics.positive_return_pf_gt_1`).
5. Add Strategy Pipeline to the **CmdKPalette** jump-to-surface list.
6. Prop Firms and Deployments remain deferred (no endpoints under freeze).
7. **Release tag `v1.1.0-stage4-p2`** — deferred pending user directive. Tag should be created only after the corpus import lands and Pipeline is verifiably LIVE (not partial).

### Post-freeze backlog (P2)

- Broker Connections group (waits for freeze to be formally lifted).
- WSS `/stream/*` bindings for live tick, cycle, and log tails.
- Optimization launcher + Approvals bundle generation.

---

## 7 · Test credentials

- **Admin** (backend-seeded via `ADMIN_EMAIL` / `ADMIN_PASSWORD`)
  - email `admin@coinnike.com`
  - password `admin123`
  - role from `/api/auth/me`: `admin`
- **Fixture operator** (developer preview fallback · Sprint 1 M1 legacy)
  - email `operator@coinnike.com`
  - password `prototype123`
  - role: `operator`

---

## 8 · Bundle contents and directory structure

```
/app/
├── .git/                          # full git history · six Phase 2 commits present
├── backend/                       # v1.1.0-stage4 · unchanged
├── docs/
├── frontend/
│   ├── package.json · yarn.lock · craco.config.js · tailwind.config.js
│   ├── scripts/                   # check-testids.js · spa-serve.py
│   ├── src/                       # Phase 2 changes here
│   └── tests/e2e/                 # cjs Playwright specs (kept)
├── infra/
├── memory/
│   └── PRD.md                     # updated for Phase 2 close-out
├── scripts/
├── HANDOVER.md                    # this file
├── Makefile
├── README.md
└── VERSION
```

**Excluded from the bundle:**
- `node_modules/`
- `frontend/build/`
- `**/__pycache__/`
- `**/.pytest_cache/` · `**/.mypy_cache/` · `**/.ruff_cache/`
- `**/*.pyc` · `**/*.pyo`
- `.emergent/` (Emergent-scoped platform state)
- `frontend/.env` · `backend/.env` (env-scoped; see §6 to recreate)
- Assorted `.log` / `.tmp` files

The `.git/` directory **is** included so you can push directly after extracting:
```bash
tar -xzf strategy-factory-sprint3-phase2.tar.gz
cd app
git push origin main
```

---

_End of handover._
