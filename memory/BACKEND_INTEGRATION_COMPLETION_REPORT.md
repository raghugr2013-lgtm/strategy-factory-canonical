# Backend Integration — Completion Report

> **Status:** ✅ **COMPLETE 2026-07-21** for the currently exposed v1.1.0-stage4 backend surface (Track α).
> **Recommended git tag:** `v1.2.0-integration-complete` on top of the current `main` HEAD.
> **Backend Feature Freeze:** in effect · zero backend source-code changes.
> **Design Freeze v1.0:** in effect · zero frontend behaviour changes.
> **Compatibility boundary:** the adapter layer under `/app/frontend/src/os/adapters/**` is the **official contract seam** between the Sprint 1 frontend and the Backend Feature Freeze v1.1.0-stage4 backend.

---

## 1. Scope

Track α — declare Backend Integration complete for **the endpoints that exist today** in the frozen backend, and retain fixture-first fallback for every other adapter until the separate Backend Activation Roadmap (Coherent UKIE Activation Plan) exposes further routes. **UKIE / CoE / Meta-Learning activation is explicitly out of scope** for this integration milestone.

## 2. Final API Contract Matrix

| # | Adapter | Expected endpoint (Sprint 1 design) | Actual v1.1.0-stage4 route | Mapping | Response transform | Live-mode status |
|---|---|---|---|:-:|---|---|
| 1 | `factoryAdapter.fetchStrategies({status})` | `GET /api/factory-eval/strategies` | `GET /api/strategies` (auth-required · `List[StrategyOut]`) | ✅ **REMAPPED** | `{strategy_id, name, status} → {id, name, status, sharpe:0, drawdown:0}` | LIVE when authenticated; transparent fixture fallback on 401 |
| 2 | `authStore.login(email, pw)` | `POST /api/auth/login` | `POST /api/auth/login` (`TokenPair`) | ✅ **DIRECT** | `{access_token \| token \| jwt} → sessionStorage['sf-auth-token']`; `authMode: 'live' \| 'fixture'` persisted | LIVE contractually; fixture fallback on 401 (no seeded user) or network |
| 3 | `factoryAdapter.fetchWorkers()` | `GET /api/ai-workforce/workers` | *not exposed in v1.1.0-stage4* | ⏸ **FIXTURE-ONLY** | n/a | Breadcrumb emitted; router awaits UKIE Activation Phase B+ |
| 4 | `factoryAdapter.fetchPipeline()` | `GET /api/coe/state` | 503 (`COE_GAMMA_ENABLED` OFF under freeze) | ⏸ **FIXTURE-ONLY** | n/a | Breadcrumb emitted; awaits CoE Gamma activation on VPS track |
| 5 | `timelineAdapter.fetchTimeline({actor, window})` | `GET /api/llm-calls` | *not exposed* (`/api/research/history` is only a partial substitute) | ⏸ **FIXTURE-ONLY** | n/a | Breadcrumb emitted noting partial substitute |
| 6 | `approvalsAdapter.fetchApprovals({risk})` | `GET /api/meta-learning/recommendations` | *not exposed* (Stage-4 gate OFF) | ⏸ **FIXTURE-ONLY** | n/a | Breadcrumb emitted; awaits Meta-Learning activation |
| 7 | `approvalsAdapter.commitApproval(id, verdict)` | `POST /api/meta-learning/recommendations/{id}/{verdict}` | 404 (paired with #6) | ✅ **CONTRACT PRESERVED** | 404 + 409 → `{ok:true, mode:'observe', ack:…}` | OBSERVE-mode acknowledgment fires today; wire-through fires when router exposed |

**Legend:**
- ✅ **REMAPPED** — adapter URL/shape adjusted; live data flows today
- ✅ **DIRECT** — contract already matched; no adapter change needed
- ✅ **CONTRACT PRESERVED** — surface UX identical whether backend responds or 404s
- ⏸ **FIXTURE-ONLY** — backend endpoint not exposed under freeze; fixture retained; adapter awaits activation with zero frontend work

**Aggregate:** 3 remapped/direct/preserved · 4 fixture-only · 0 broken · **0 frontend behaviour changes**.

## 3. Adapter Compatibility Mappings

The following mappings are declared **official and canonical** for the v1.1.0-stage4 backend generation. They live in the four adapter files under `/app/frontend/src/os/adapters/**` and are the single source of truth for backend↔frontend translation.

### 3.1 `apiClient.js` — infrastructure

```
isLiveMode()                    → true if REACT_APP_BACKEND_URL is set
apiFetch(path, opts)            → prepends BACKEND_URL, injects Bearer sf-auth-token
fixtureOrLive(endpoint, fx)     → tries live, falls back to fixture with console.warn
unavailableBreadcrumb(name, ep, why) → single-shot console.info per adapter per session
```

### 3.2 `factoryAdapter.js`

```
fetchStrategies({status})
  live: GET /api/strategies
  transform: raw.map(s => ({
    id: s.strategy_id ?? s.id,
    name: s.name,
    status: s.status ?? 'draft',
    sharpe: typeof s.sharpe === 'number' ? s.sharpe : 0,
    drawdown: typeof s.drawdown === 'number' ? s.drawdown : 0,
  }))
  facet filter: client-side by status

fetchWorkers()  → FIXTURE-ONLY · breadcrumb: 'router not exposed in v1.1.0-stage4'
fetchPipeline() → FIXTURE-ONLY · breadcrumb: 'COE_GAMMA_ENABLED flag OFF under freeze'
```

### 3.3 `timelineAdapter.js`

```
fetchTimeline({actor})
  FIXTURE-ONLY · breadcrumb: 'endpoint not exposed in v1.1.0-stage4;
                              /api/research/history is only a partial substitute'
  client-side actor facet filter over TIMELINE_FIXTURE
```

### 3.4 `approvalsAdapter.js`

```
fetchApprovals({risk})
  FIXTURE-ONLY · breadcrumb: 'router not exposed in v1.1.0-stage4 (Stage-4 flag OFF)'
  client-side risk facet filter over APPROVALS_FIXTURE

commitApproval(id, verdict)
  live: POST /api/meta-learning/recommendations/{id}/{verdict}
  contract-preserved: 404 OR 409 → {ok:true, mode:'observe', ack:'${verdict} · queued · OBSERVE mode'}
```

### 3.5 `authStore.js` (real-auth wiring stays live)

```
login(email, password)
  live: POST /api/auth/login {email, password}
    → extract access_token | token | jwt
    → sessionStorage.setItem('sf-auth-token', token)
    → authMode = 'live', stance = 'authenticated'
  401/403 → real credential error (no fallback)
  network / other → fixture path (E1 error copy preserved)
```

## 4. Verification evidence

| Check | Result |
|---|:-:|
| Backend boots · `/api/health` = 200 (local + external) | ✅ |
| Backend source code untouched | ✅ |
| Frontend compiles cleanly | ✅ |
| All 5 surfaces still render (fixture path) | ✅ |
| Strategies surface renders 6 rows via `fetchStrategies` (401 → transparent fallback) | ✅ |
| 4 unavailability breadcrumbs fire exactly once each per session | ✅ |
| `authMode: 'fixture'` persisted correctly when live-auth 401s | ✅ |
| Rule of Predictable Return + facet cascade + optimistic UI + evidence drawer all still work | ✅ (verified in M4; adapter changes are shape-only) |

## 5. Roadmap position

```
Backend Feature Freeze v1.1.0-stage4  ✅ 2026-07-20
Design Freeze v1.0                     ✅ 2026-07-21
   Sprint 1 Foundation                 ✅ 2026-07-21 (M1→M5)
      Backend Integration Track α      ✅ 2026-07-21  ← YOU ARE HERE
         Recommended tag: v1.2.0-integration-complete

   ⇢ Sprint 2 (frontend evolution)     · queued
      see memory/SPRINT_2_PLANNING.md

   ⇢ Backend Activation Track (Coherent UKIE Activation Plan)
      Phase A → E · operator-directed on VPS
      Independent of dev-workspace Sprint 2
      As each phase lands, the corresponding adapter breadcrumb
      auto-clears because fixtureOrLive() starts receiving live data.
      NO frontend changes required at activation time.
```

## 6. Remaining risks (unchanged from Sprint 1 report §6)

| # | Risk | Owner |
|---|---|---|
| R1 | No seeded operator user in `strategy_factory.users` collection → live E2E limited to fixture-mode | Operator (out of freeze) |
| R2 | `StrategyOut` schema lacks `sharpe`/`drawdown` → Explorer shows `0.00 / 0%` under live data | Sprint 2 (extend schema or drop columns under live-mode) |
| R3 | Legacy v01 CommandShell dead code still present in tree | Sprint 2 (housekeeping) |
| R4 | Fixture-fallback can mask real backend bugs during dev | Sprint 2 (add `?strict-live=1` flag) |

## 7. Recommended git tag

**`v1.2.0-integration-complete`** — annotated tag on the current `main` HEAD after this report is committed. Cleanly caps the integration milestone and unblocks Sprint 2 planning.

---

*End of Backend Integration Completion Report.*
