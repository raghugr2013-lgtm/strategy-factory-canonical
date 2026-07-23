# Strategy Factory — Frontend Exposure Gap Analysis & Roadmap

**Companion to:** `docs/FRONTEND_CAPABILITY_AUDIT.md` ·
`docs/CAPABILITY_INVENTORY.md` ·
`docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md`.
**Guiding order (non-negotiable):**
**Discover → Reuse → Refine → Extend → Build New.**

**Objective:** expose the ~605 backend endpoints that have no UI
today, using the existing shell + `EngineeringSurface` template +
adapter pattern. Zero new engines, zero new backend endpoints, zero
schema changes.

---

## 1 · Gap ledger — every backend capability without a UI

Ranked by operational value for a 24×7 factory. Each row identifies
the recommended host surface (existing or new), the specific backend
endpoints to bind, and the recommendation.

### 1.1 · CRITICAL — required to operate the factory 24×7

| # | Missing UI | Backend endpoints ready to bind | Host surface | Recommendation |
|---|-----------|-------------------------------|--------------|-----------------|
| 1 | **Real Sign-in** (backend auth) | `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`, `POST /api/auth/logout` (5 endpoints) | `LoginScreen.jsx` + `sessionStore.js` | **Refine** — swap fixture logic for real API calls |
| 2 | **Role-aware rail + Approvals gate** | `GET /api/auth/me` → `role`, `/api/admin/pending`, `/api/admin/users` | `RequireAuth.jsx` + `LeftRail.jsx` + `Approvals.jsx` | **Refine** — read role from `/api/auth/me`; filter `NAV_GROUPS` accordingly |
| 3 | **Autonomous Factory Orchestrator dashboard** | `GET /api/orchestrator/status`, `GET /api/orchestrator/decisions`, `POST /api/orchestrator/start`, `POST /api/orchestrator/stop`, `POST /api/orchestrator/tasks/{name}/dispatch`, `GET /api/orchestrator/history` (7 endpoints) | **NEW** surface `/c/factory/orchestrator` (extend nav) | **Extend** — reuse `EngineeringSurface` template; add live cards for tick/dispatched/in_flight/last_error |
| 4 | **Live Status Rail (right-most 8 pills)** | `/api/health/system`, `/api/orchestrator/status`, `/api/data-maintenance/status`, `/api/ai-workforce/providers`, `/api/governance/summary`, `/api/coe/state`, `/api/factory-eval/kpis` | `shell/StatusRail.jsx` | **Refine** — one hook per pill, 30s polling. Highest ROI: operator instantly sees factory state on every page. |
| 5 | **Approvals inbox executor wiring** | `POST /api/strategies/{id}/promote`, `POST /api/strategies/{id}/retire`, `POST /api/deployments/{id}/rollback`, `POST /api/orchestrator/tasks/{name}/dispatch` (state-transition endpoints) | `ApprovalsModal.jsx` (Slice γ shim) | **Extend** — wire `executor:` callback per approval type. Currently `executor=null`. |
| 6 | **Timeline persistence (`POST /api/timeline/events`)** | `POST /api/timeline/events`, `GET /api/timeline/events?...` | `adapters/timelineShim.js` | **Extend** — swap sessionStorage for real endpoint (Slice γ handover §4). Post-freeze-lift. |
| 7 | **Health + Readiness top-strip binding** | `GET /api/health`, `/api/readiness`, `/api/health/subsystems` | `shell/TopStrip.jsx` | **Refine** — replace fixture `MODE · OPERATIONS` string with live mode + readiness lamp |

### 1.2 · HIGH — required to explore/validate the factory

| # | Missing UI | Backend endpoints | Host surface | Recommendation |
|---|-----------|-------------------|--------------|----------------|
| 8 | **Factory Health / KPI dashboard** | `/api/factory-eval/kpis` (28 endpoints total under `/api/factory-eval/*`) — reports, insights, recommendations, providers/leaderboard, strategies/top-contributors | **NEW** `/c/factory/health` — reuse `EngineeringSurface` template + `LivenessBadge` | **Extend** |
| 9 | **Meta-Learning inspector (OBSERVE-mode)** | 15 endpoints under `/api/meta-learning/*` — config, evaluations, recommendations, pending, applications, overrides, refresh | **NEW** `/c/factory/meta-learning` | **Extend** |
| 10 | **Market Intelligence dashboard** | 10 endpoints under `/api/market-intelligence/*` — state, changes, intelligence, refresh, observers | **NEW** `/c/factory/market-intelligence` | **Extend** |
| 11 | **Auto-Factory + Auto-Mutation control** | 16 endpoints under `/api/auto/*`, 10 under `/api/mutation/*` | **NEW** `/c/factory/auto-factory` | **Extend** |
| 12 | **Learning ledger + lineage view** | 15 endpoints under `/api/learning/*` + `/api/research-lineage/*` | Enrich existing `Timeline.jsx` — add filter by actor/task_name/outcome | **Refine** — extend timeline shim rather than build a new surface |
| 13 | **Research Center** | `/api/knowledge/*` (34 endpoints — nearest, champions, statistics, families, health, evaluate, similarity) + `/api/research/*` + `/api/research-runs/*` (4 endpoints) + `/api/research-lineage/*` | **NEW** `/c/factory/research` — champions table, families explorer, similarity playground | **Extend** — reuse the 4 knowledge endpoints already partially bound |
| 14 | **Strategy Explorer full breadth** | `/api/strategies/*` (16 endpoints — CRUD, filters, cold-insert, promote), `/api/strategy-memory/*`, `/api/lifecycle/*`, `/api/library/*` | Enrich `Strategies.jsx` — add filters, re-insert-as-cold CTA, lifecycle state visualiser | **Refine** — the surface already renders; add controls + wiring |

### 1.3 · MEDIUM — completes operator power

| # | Missing UI | Backend endpoints | Host surface | Recommendation |
|---|-----------|-------------------|--------------|----------------|
| 15 | **Prop-Firms full workflow** | 11 endpoints under `/api/prop-firms/*` + 6 under `/api/prop-firm-rules/*` + 5 under `/api/challenge-rules/*` + 4 under `/api/portfolio-builder/*` challenge-matching + `/api/challenge-*` (~10 endpoints across challenge_manager, challenge_matching_engine, challenge_simulator, challenge_portfolio) | `PropFirms.jsx` — currently empty-state | **Extend** — replace `EngineeringSurface` placeholder with real content |
| 16 | **Live Trading / Deployments dashboard** | 32 endpoints under `/api/execution/*` (dormant when `EXEC_ENABLED=false` — still exposable read-only), 8 under `/api/live/*`, 6 under `/api/trade-runner/*`, `/api/live-tracking/*` | `Deployments.jsx` — currently empty-state | **Extend** — replace empty-state with read-only dashboard; live-write behind `EXEC_ENABLED` gate |
| 17 | **Portfolio detail page** | 11 endpoints under `/api/portfolio/*`, 4 under `/api/portfolio-builder/*`, 4 under `/api/portfolio-intelligence/*` | `/c/portfolio` (rail entry is deep-link to `/c/mission?focus=portfolio` — insufficient) | **Extend** — dedicated route + surface |
| 18 | **Admin Users CRUD** | 33 endpoints under `/api/admin/*` — users, pending, approve, revoke, roles, sessions | `Users.jsx` — currently empty-state | **Extend** — replace `EngineeringSurface` with grid + invite flow |
| 19 | **Admin Integrations (provider probes, connector rotation)** | `/api/admin/providers/probe` (partially bound), `/api/ai-workforce/providers`, `/api/llm-diagnostics/*`, `/api/llm-health/*` | `Integrations.jsx` — currently empty-state | **Extend** |
| 20 | **Admin Logs (audit + access + orchestrator)** | Audit + activation-journal + operator-action tables via `/api/admin/*` and `/api/audit/*` | `Logs.jsx` — currently empty-state | **Extend** |
| 21 | **Master Bot full binding (49 of 51 endpoints unused)** | 49 additional `/api/master-bot/*` endpoints — definitions, diff, pack, export, ranker, deployment | `MasterBot.jsx` | **Refine** — extend the two live queries to full binding |
| 22 | **Strategy Lab full binding (11 endpoints prepared, none surfaced)** | `/api/strategies/generate`, `/api/strategies/{id}/iterate`, `/api/backtest/quick`, plus optimization + validation triggers | `StrategyLab.jsx` | **Refine** — wire `strategyLabAdapter` outputs into the surface |
| 23 | **Coverage / Datasets / Market Data path reconciliation** | Reconcile `navigation.js` `phase2Sources` against backend `openapi.json` — declared paths (`/api/coverage/matrix`, `/api/datasets`, `/api/market-data/*`) don't match backend prefixes (`/api/data/coverage`, `/api/data`, no `market-data` prefix). Endpoints exist under different roots. | The three existing surfaces | **Refine** — update metadata + adapter paths (no backend change) |
| 24 | **Optimization live wiring** | `/api/optimization/*` (6 endpoints) + `/api/tuning/*` (8 endpoints) | `Optimization.jsx` | **Refine** — path reconciliation (declared `/api/optimize`, actual `/api/optimization`) + adapter wiring |
| 25 | **Governance + Safety cockpit** | 9 endpoints under `/api/governance/*` + rule-engine + activation-governance endpoints | **NEW** `/c/admin/governance` | **Extend** |
| 26 | **Ecosystem scaling diagnostics** | 10 endpoints under `/api/scaling/*` + `/api/coe/*` + `/api/coe-gamma/*` + `/api/coe-metrics/*` | **NEW** `/c/admin/coe` | **Extend** |
| 27 | **Brain policy inspector** | 6 endpoints under `/api/brain/*` | **NEW** `/c/factory/brain` | **Extend** |
| 28 | **AI Workforce provider board** | 8 endpoints under `/api/ai-workforce/*` | `Workforce.jsx` (currently fixture-only) | **Refine** |

### 1.4 · LOW — nice-to-have, deep power-user

| # | Missing UI | Backend endpoints | Recommendation |
|---|-----------|-------------------|----------------|
| 29 | Latent-space diagnostics (advanced) | 38 endpoints under `/api/latent/*` | **Extend** — deep-power-user surface, not on operator's daily path |
| 30 | ASF / BI5-realism / rank-strategies etc. | ~30 sundry endpoints across ~20 minor prefixes | **Extend** — surfacing them through Timeline / Passport tabs is enough |
| 31 | Runner registry / token rotator / account migration | `/api/runner/*` (4 endpoints) | **Extend** — folds into `Admin Integrations` |
| 32 | Settings page | Settings ledger + user preferences | **Refine** — replace 9-line stub with a real preferences panel + a "reset walkthrough" toggle |

---

## 2 · Priority-ordered exposure roadmap

### Sprint FE-A · The 4-hour high-ROI sprint (Reuse + Refine)

**Objective:** turn the frontend from "chrome only" to "the operator
can see if the factory is alive". Every change is refinement of an
existing component — no new files.

1. **Refine `LoginScreen.jsx` + `sessionStore.js`** → real `POST /api/auth/login` + refresh + `GET /api/auth/me`. Drop the fixture-credentials block from the sign-in card once real auth works.
2. **Refine `RequireAuth.jsx` + `LeftRail.jsx`** → filter `NAV_GROUPS` by the role returned from `/api/auth/me`.
3. **Refine `TopStrip.jsx`** → `MODE` reads from `/api/health/system.mode`; kill-posture reads from a real endpoint; clock is already fine.
4. **Refine `StatusRail.jsx`** → wire the 8 pills to their existing backend endpoints (30s polling each).
5. **Refine `MissionControl.jsx`** → replace fixture cards with `factoryAdapter` + `orchestrator/status` + `dashboard/summary` calls (endpoints already exist).

**Endpoints newly reached:** ~14. **Effort:** ~4h. **Effect:** the operator can sign in with the seeded admin, see real factory state on every page, and browse role-scoped rail.

### Sprint FE-B · The Autonomous Factory Dashboard (Extend)

**Objective:** add the single most important missing surface — the Orchestrator dashboard — so the operator can watch continuous autonomous work.

1. Add rail group `Factory` (between Mission Control and Engineering). Metadata-only change to `navigation.js`.
2. Add routes `/c/factory/orchestrator`, `/c/factory/health`, `/c/factory/meta-learning`, `/c/factory/market-intelligence`, `/c/factory/auto-factory`, `/c/factory/research`, `/c/factory/brain` under a single `Factory` group. Each renders `EngineeringSurface` template initially — no coding beyond metadata for the first commit.
3. For each Factory route: implement an adapter (`orchestratorAdapter.js`, `factoryEvalAdapter.js`, `metaLearningAdapter.js`, `marketIntelligenceAdapter.js`, `autoFactoryAdapter.js`, `knowledgeAdapter.js`, `brainAdapter.js`) — one file per surface, calling the existing backend endpoints.
4. Replace each surface's `EngineeringSurface` render with a real component built on the same design tokens + `LivenessBadge` + tables.

**Endpoints newly reached:** ~100 (7 orchestrator + 28 factory-eval + 15 meta-learning + 10 market-intelligence + 16 auto/mutation + 34 knowledge + 6 brain). **Effort:** ~2 focused days per surface = 2 weeks total.
**Effect:** the operator can operate the autonomous factory end-to-end from the UI.

### Sprint FE-C · The Empty-State-to-Live Conversion (Extend)

**Objective:** turn every existing empty-state surface into a live surface.

1. `PropFirms.jsx` — extend against the 22 endpoints that back the prop-firm domain.
2. `Deployments.jsx` — extend against `/api/execution/*` (read-only when EXEC off) + `/api/live-tracking/*` + `/api/trade-runner/*`.
3. `Users.jsx` — extend against the 33 admin endpoints.
4. `Integrations.jsx` — extend against provider probes + connector CRUD.
5. `Logs.jsx` — extend against audit + activation-journal endpoints.

**Endpoints newly reached:** ~90. **Effort:** ~1 focused day per surface = 1 week total.
**Effect:** every rail entry is a live surface. No more empty-state pages except intentional deep-power ones (Latent Space, Governance).

### Sprint FE-D · Refine existing Engineering surfaces (Refine)

**Objective:** convert the fixture-driven Engineering surfaces (MarketData, Coverage, Datasets, StrategyLab, StrategyPipeline, Optimization, Validation) to live data.

1. Path reconciliation: update `phase2Sources` metadata + adapter paths to match actual backend prefixes (`/api/data/*`, `/api/optimization/*`, `/api/validation` via `strategies/*`).
2. Bind each surface to its adapter's live query. All 7 surfaces already have realistic fixture UIs — refinement is fetch + render.
3. Wire the actions (dispatch backtest, generate strategy, promote parameter set) to the corresponding mutating endpoints.

**Endpoints newly reached:** ~40. **Effort:** ~1 focused day per surface = 1 week total.
**Effect:** the Engineering Workspace becomes a real research cockpit.

### Sprint FE-E · Strategy Explorer + Portfolio depth (Refine + Extend)

**Objective:** make Strategy Passport + Strategies list production-worthy.

1. **Refine** `Strategies.jsx` — add filters (regime · pair · TF · lifecycle), re-insert-as-cold CTA, lifecycle-state visualiser.
2. **Refine** `StrategyPassport.jsx` — bind every tab (history, market-scan, prop-analysis, match-challenges, lineage, intelligence) to its already-existing endpoint.
3. **Extend** — add dedicated `/c/portfolio` route + surface (currently deep-link only).
4. Wire the timeline shim's real endpoint swap (Slice γ handover §4).

**Endpoints newly reached:** ~40. **Effort:** ~1 focused week.
**Effect:** the operator can drive the strategy lifecycle end-to-end.

### Sprint FE-F · Admin + Governance (Extend)

**Objective:** complete the operator's control surface.

1. **Refine** `Settings.jsx` (currently 9 lines) — real preferences panel.
2. **Extend** admin surfaces (Users, Integrations, Logs) from FE-C.
3. **Extend** — Governance + Safety cockpit + Coordinated Ops Engine dashboard.

**Endpoints newly reached:** ~40. **Effort:** ~1 focused week.

### Sprint FE-Z · Deep-power surfaces (Build New only if demanded)

- Latent-space diagnostics (`/api/latent/*` — 38 endpoints).
- Scaling + COE + capability-probe cockpits.
- Runner-registry + token rotator + account migration surfaces.

**Recommendation:** hold until an operator asks. Every one of these
lives happily as a well-crafted `EngineeringSurface` empty-state
until then.

---

## 3 · Recommendation summary (Discover → Reuse → Refine → Extend → Build New)

| Recommendation | Count of items | Total endpoints unlocked |
|----------------|:-------------:|:------------------------:|
| **Discover** — reconcile declared paths vs actual backend prefixes | 4 surfaces (Coverage · Datasets · Market Data · Optimization) | metadata-only, unlocks pre-existing fixture wiring |
| **Reuse** — leverage existing chrome + `EngineeringSurface` + adapter pattern + `LivenessBadge` | all sprints | — |
| **Refine** — extend existing components to reach existing endpoints | 15 items (auth, RBAC, TopStrip, StatusRail, MissionControl, all 7 Engineering surfaces, MasterBot, Strategies, Passport, Settings, Timeline shim) | ~150 endpoints |
| **Extend** — new surfaces built from the template (no new backend) | 13 items (Factory group of 7 + 5 admin/engineering conversions + 1 portfolio route) | ~250 endpoints |
| **Build New** — new backend engines | 0 | 0 |

The frontend can reach **~400 of the 613 backend endpoints** without
a single new backend engine, only through disciplined reuse of the
existing shell + template + adapter layer. The remaining ~200
endpoints are either bookkeeping / diagnostic / internal-orchestrator
routes that don't belong on the operator's daily path (they belong
on a deep-power engineering diagnostics page — Sprint FE-Z).

---

## 4 · What NOT to do (guardrails)

1. **Do not create a second sign-in flow.** `LoginScreen.jsx` +
   `sessionStore.js` are the canonical pair. Real auth is a
   refinement, not a rewrite.
2. **Do not duplicate the shell.** Every surface must mount under
   `AppShell` — same TopStrip, LeftRail, StatusRail, walkthrough.
3. **Do not build a second empty-state template.**
   `EngineeringSurface.jsx` is the template. Every new empty-state is
   a metadata entry in `navigation.js` + `ENGINEERING_SURFACES`.
4. **Do not invent new backend endpoints during frontend work.** If
   an operator needs a signal that isn't served today, first check
   `/api/openapi.json` for a matching one; only then propose a
   backend extension (Phase 2 roadmap item).
5. **Do not modify design tokens without design-freeze sign-off.**
   `os/tokens.css` is the contract; extension is fine, edit isn't.
6. **Preserve `data-testid` on every interactive element** — the
   `scripts/check-testids.js` invariant is a merge gate.
7. **Do not remove the walkthrough.** It's the operator's first
   30-second orientation and dismissible per-session.

---

## 5 · Sign-off checklist (per sprint)

- [ ] Every new surface reuses `AppShell` + design tokens + `LivenessBadge`.
- [ ] Every new adapter uses `apiClient.js` (no new HTTP client).
- [ ] Every mutating action passes through `ApprovalsModal.jsx` when the
      operation is HIGH-risk (promote / retire / rollback / deploy-live).
- [ ] Every new route has a corresponding entry in `navigation.js`.
- [ ] `scripts/check-testids.js` passes.
- [ ] No new backend endpoint added.
- [ ] No design-token variable renamed or deleted.
- [ ] `docs/FRONTEND_CAPABILITY_AUDIT.md` §7 completion percentages
      updated for every surface touched.

---

## 6 · Bottom line

The Strategy Factory backend already exposes 613 endpoints; the
frontend reaches 8 of them. Closing that gap is **90 % refinement +
10 % extension** — no new backend engines, no new design language,
no new shell. The Discover → Reuse → Refine → Extend → Build New
principle applies cleanly at every step, and the entire operator
workspace can be brought to full coverage in ~5 focused weeks of
frontend-only work.

Once the frontend can operate and observe the factory end-to-end, we
can safely activate Phase 1 on the VPS with a rich operational
surface behind it.
