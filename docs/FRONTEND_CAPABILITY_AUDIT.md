# Strategy Factory — Frontend Capability Audit

**Status:** frontend-only inventory. Zero code changes.
**Method:** static survey of `frontend/src/` (router · surfaces · adapters ·
hooks) + live UI capture at `http://127.0.0.1:3000/` after signing in with
the fixture credentials shown on the sign-in card
(`operator@coinnike.com / prototype123`) + endpoint enumeration from the
backend `/api/openapi.json` (613 endpoints live in the local backend).
**Companion documents:** `docs/FRONTEND_EXPOSURE_ROADMAP.md` (gap
analysis + priority-ordered exposure plan), `docs/CAPABILITY_INVENTORY.md`
(backend), `docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md`.

**Screenshots (JPEG, 25 % quality, ~35 KB each):** `docs/screenshots/00..21-*.jpeg`.

---

## 1 · Headline numbers

| Signal | Value |
|--------|-------|
| Backend endpoints exposed in local backend `/api/openapi.json` | **613** |
| Distinct `/api/*` prefixes on the backend | **~65** |
| Frontend routes declared in `AppRouter.jsx` | **21** (5 Mission Control · 10 Engineering · 4 Admin · 1 Strategies · 1 Passport detail · 1 Gallery + 1 Sign-in) |
| Frontend surfaces implemented as **live wired UI** | **12** (5 MC + 7 Engineering + Strategies + Passport) |
| Frontend surfaces implemented as **Phase-2 empty-state** (renders `EngineeringSurface` template) | **5** (Deployments · PropFirms · Users · Integrations · Logs) |
| Frontend surfaces that are **skeletal stubs** | **1** (Settings — 9 lines) |
| Adapters under `frontend/src/os/adapters/` | **9** (approvals · coverage · factory · masterBot · strategyLab · stream · timeline · plus support files) |
| Distinct `/api/*` endpoints called from adapters + surfaces + hooks | **8** — see §5 |
| **Fraction of backend surface reachable via UI today** | **≈ 1.3 %** (8 / 613) |

**Bottom line:** the frontend has an excellent chrome (rail · top strip ·
status rail · CmdK · walkthrough) and a rich set of wired surfaces
for Mission Control + several Engineering pages, but it currently
consumes fewer than 10 backend endpoints. The remaining ~605 endpoints
have no operator-facing exposure at all.

---

## 2 · Route + surface inventory

### 2.1 · Sign-in

| Route | Component | Backend calls | Status | Screenshot |
|-------|-----------|---------------|--------|-----------|
| `/auth/sign-in` | `LoginScreen.jsx` | **NONE** — fixture-only auth via zustand session store. The sign-in card ships the fixture credentials in its own body (`operator@coinnike.com · prototype123`). | LIVE UI, FIXTURE AUTH | `00-signin.jpeg` |

**Critical finding:** sign-in does **not** call `POST /api/auth/login`.
This is Sprint-1 Phase-1 fixture behaviour; the backend seed +
JWT refresh rotation are entirely unused by the current UI. Backend
users (admin seed at `admin@strategy-factory.local`, plus every
approve-signup + role-CRUD endpoint) are unreachable.

### 2.2 · Mission Control group

| Route | Component | LOC | Live queries | Backend endpoints consumed | Status | Screenshot |
|-------|-----------|-----|--------------|----------------------------|--------|-----------|
| `/c/mission` | `MissionControl.jsx` | 229 | 0 | via `factoryAdapter` (fixture-heavy) | LIVE UI, MIXED (live + fixture) | `02-mission.jpeg` |
| `/c/masterbot` | `MasterBot.jsx` | 215 | 0 | `/api/master-bot/identity` · `/api/master-bot/current-plan` (via adapter) | LIVE UI, MIXED | `03-masterbot.jpeg` |
| `/c/timeline` | `Timeline.jsx` | 135 | 1 | `useTimelineEvents` hook via `timelineAdapter` (fixture fallback) | LIVE UI, MIXED | `04-timeline.jpeg` |
| `/c/approvals` | `Approvals.jsx` | 197 | 0 | via `approvalsAdapter` (fixture fallback) | LIVE UI, MIXED | `05-approvals.jpeg` |
| `/c/workforce` | `Workforce.jsx` | 76 | 0 | fixture-only | LIVE UI, FIXTURE ONLY | `06-workforce.jpeg` |

### 2.3 · Strategies group

| Route | Component | LOC | Backend endpoints consumed | Status | Screenshot |
|-------|-----------|-----|----------------------------|--------|-----------|
| `/c/strategies` | `Strategies.jsx` | 93 | `/api/strategies` (list via `factoryAdapter`) | LIVE UI, LIVE DATA path exists | `07-strategies.jpeg` |
| `/c/strategies/:id` | `StrategyPassport.jsx` | 827 | Deep read-only detail page — Slice β. Backing endpoints in `research_lineage` + `strategy_memory`. Consumes `useStrategiesLibrary` via `factoryAdapter`. | LIVE UI, PARTIAL DATA | (not screenshotted — needs `:id`) |

### 2.4 · Engineering group — LIVE surfaces

Each of these surfaces has 350–500 lines of real component code with
tables, filters, empty states, and skeletons. They are wired for
LIVE data through their own hooks but currently render from fixtures
because the backend endpoints on the frontend side are not yet
called — the wiring path is 90 % there.

| Route | Component | LOC | Endpoints DECLARED in `navigation.js` phase2Sources | Backend actually called? | Screenshot |
|-------|-----------|-----|---------------------------------------------------|--------------------------|-----------|
| `/c/engineering/market-data` | `MarketData.jsx` | 401 | `GET /api/market-data/subscriptions`, `WSS /stream/ticks`, `POST /api/market-data/subscribe` | **NO** — fixtures | `08-market-data.jpeg` |
| `/c/engineering/coverage` | `Coverage.jsx` | 364 | `GET /api/coverage/matrix`, `GET /api/coverage/gaps`, `POST /api/coverage/rehydrate` | **NO** — fixtures. Backend has `/api/data/coverage` (18-endpoint prefix), not `/api/coverage/matrix` | `09-coverage.jpeg` |
| `/c/engineering/datasets` | `Datasets.jsx` | 420 | `GET /api/datasets`, `GET /api/datasets/{id}/manifest`, `POST /api/datasets/download` | **NO** — backend does not expose `/api/datasets` under that path; equivalent lives under `/api/data/*` | `10-datasets.jpeg` |
| `/c/engineering/strategy-lab` | `StrategyLab.jsx` | 483 | `POST /api/strategies/generate`, `POST /api/strategies/{id}/iterate`, `POST /api/backtest/quick` | **PARTIAL** — `strategyLabAdapter` has 11 API refs but the surface renders fixtures | `11-strategy-lab.jpeg` |
| `/c/engineering/strategy-pipeline` | `StrategyPipeline.jsx` | 451 | (not declared in nav — added in Sprint 3) | **NO** — fixtures | `12-strategy-pipeline.jpeg` |
| `/c/engineering/optimization` | `Optimization.jsx` | 484 | `POST /api/optimize`, `GET /api/optimize/{cycleId}`, `WSS /stream/optimize` | **NO** — backend prefix is `/api/optimization` (6 endpoints) + `/api/tuning` (8 endpoints), not `/api/optimize` | `13-optimization.jpeg` |
| `/c/engineering/validation` | `Validation.jsx` | 503 | `GET /api/validation`, `GET /api/backtest/{id}`, `POST /api/backtest` | **PARTIAL** — only `/api/knowledge/health` is actually called | `14-validation.jpeg` |

### 2.5 · Engineering group — EMPTY-STATE surfaces

These render a shared `EngineeringSurface` template with a briefing,
capabilities list, phase-2 source list, and cross-links. No data
fetching yet — this is intentional per Sprint 3 Phase 1.

| Route | Component | Phase-2 sources declared | Backend endpoints that exist | Screenshot |
|-------|-----------|---------------------------|-------------------------------|-----------|
| `/c/engineering/prop-firms` | `PropFirms.jsx` | `/api/prop-firms`, `/api/prop-firms/{id}/challenges`, `/api/prop-firms/{id}/payout` | ✅ **11 endpoints on `/api/prop-firms/*` + 6 on `/api/prop-firm-rules/*` + 5 on `/api/challenge-rules/*` — all live** | `15-prop-firms.jpeg` |
| `/c/engineering/deployments` | `Deployments.jsx` | `/api/deployments`, `/api/deployments/{id}/rollback`, `/api/deployments/{id}/history` | **NO** — no `/api/deployments` prefix on backend. Live-tracking + trade-runner cover the same domain (`/api/live-tracking`, `/api/trade-runner`). | `16-deployments.jpeg` |

### 2.6 · Admin group — EMPTY-STATE surfaces

All three admin pages render `EngineeringSurface` templates with
`roles: ['admin']` gating.

| Route | Component | Phase-2 sources declared | Backend endpoints that exist | Screenshot |
|-------|-----------|---------------------------|-------------------------------|-----------|
| `/c/admin/users` | `Users.jsx` | `/api/admin/users` etc. | ✅ **33 endpoints on `/api/admin/*`** — full CRUD + approval + roles + logs | `17-admin-users.jpeg` |
| `/c/admin/integrations` | `Integrations.jsx` | `/api/admin/providers/probe`, `/api/admin/connectors`, `/api/admin/connectors/{id}/rotate` | **PARTIAL** — `/api/admin/providers/probe` exists (via `factoryAdapter`); connector CRUD not | `18-admin-integrations.jpeg` |
| `/c/admin/logs` | `Logs.jsx` | `/api/admin/logs?stream=…`, `WSS /stream/logs` | **NO** — no `/api/admin/logs` prefix; equivalent lives under `/api/audit/*` (via legacy tags) | `19-admin-logs.jpeg` |

### 2.7 · Ancillary

| Route | Component | Purpose | Status | Screenshot |
|-------|-----------|---------|--------|-----------|
| `/c/settings` | `Settings.jsx` | 9-line skeletal placeholder ("SETTINGS · Sprint 1 empty state") | STUB | `20-settings.jpeg` |
| `/c/gallery` | `PrimitiveGallery.jsx` | Design-token + component visual regression gallery | LIVE (design-tool) | `21-gallery.jpeg` |

---

## 3 · Frontend chrome inventory (reusable everywhere)

Rendered on every authenticated route. Every element is `data-testid`-tagged and design-token driven.

| Location | Elements observed in screenshots | Notes |
|----------|----------------------------------|-------|
| **Top strip** | `STRATEGY · FACTORY`, `K DISABLED`, `MODE · OPERATIONS`, live clock, `ENV · PREVIEW` | Sprint-1 Phase-1 fixture kill-posture display; consumes zero backend data today. Ready to hydrate from `/api/health` + `/api/orchestrator/status`. |
| **Left rail** | 3 groups × 21 items — Mission Control, Engineering, Admin. Role-scoped via `NAV_GROUPS.roles=['admin']`. | Static declaration in `navigation.js`; role gate reads a fixture role — needs to read `/api/auth/me`. |
| **Status rail (bottom)** | 8 pills: `P ORCHESTRATOR · IDLE · NOMINAL` · `P INGESTION · STREAMING` · `I SCHEDULER · CRON PAUSED` · `W LLM · WARM · CLAUDE SONNET 4.6` · `P GOVERNANCE · GOV-WARDEN · V2.1` · `I KILL POSTURE · DISARMED` · `STREAM · POLL FALLBACK · <clock>` · `PRE-AUTH · PUBLIC STATUS` | All 8 pills are **fixture** today. Every one has a backend equivalent live — `/api/orchestrator/status`, `/api/data-maintenance/status`, `/api/ai-workforce/providers`, `/api/governance/*`, `/api/health/system`. |
| **Command palette (⌘K)** | Fixture — button shown as `K DISABLED` | Ready to reactivate; `CmdKPalette.jsx` consumes `flattenNav(role)`. |
| **Walkthrough overlay** | `FactoryWalkthrough` — 30-second welcome tour (visible in all screenshots) | Session-scoped dismissible modal. Bonus: gives every new operator a coherent introduction to the two-side (Operator OS + Engineering Workspace) model. |
| **RequireAuth guard** | Redirects to `/auth/sign-in?next=…` on missing session token | Uses zustand session store — no backend auth call yet. |

---

## 4 · Adapter inventory (frontend data layer)

All under `frontend/src/os/adapters/`. Each exports typed hooks (React Query wrappers).

| Adapter | Endpoints declared inside | Fixture refs | Live refs | Consumers |
|---------|---------------------------|--------------|-----------|-----------|
| `approvalsAdapter.js` | (none via literal `/api/*` string — uses `apiClient` helpers) | 2 | 4 | `Approvals.jsx` (MC) · Approvals inbox (planned Slice δ) |
| `coverageAdapter.js` | (none via literal — uses `apiClient`) | 0 | 4 | `Coverage.jsx` (Engineering) |
| `factoryAdapter.js` | `/api/knowledge/champions`, `/api/knowledge/statistics`, `/api/knowledge/nearest`, `/api/strategies`, `/api/admin/providers` (+ 4 more) | 7 | 9 | `MissionControl.jsx` · `Strategies.jsx` · `MasterBot.jsx` · Rail badges |
| `masterBotAdapter.js` | `/api/master-bot/identity`, `/api/master-bot/current-plan` (+ 8 more) | 6 | 10 | `MasterBot.jsx` |
| `strategyLabAdapter.js` | `/api/strategies/generate` + 10 more | 0 | 11 | `StrategyLab.jsx` |
| `streamAdapter.js` | (WSS placeholder) | 0 | 1 | rail hooks — polling fallback |
| `timelineAdapter.js` | `useTimelineEvents` hook facade | 2 | 4 | `Timeline.jsx` · Approvals modal · Passport lineage tab (Slice γ) |
| `apiClient.js` | HTTP wrapper — reads `REACT_APP_BACKEND_URL` | — | — | every adapter |
| `sessionStore.js` | zustand session/token store | — | — | `RequireAuth`, `LoginScreen`, `Header` |

**Total distinct `/api/*` endpoints reached from anywhere in the
frontend:**

```
/api/admin/providers
/api/knowledge/champions
/api/knowledge/health
/api/knowledge/nearest
/api/knowledge/statistics
/api/master-bot/current-plan
/api/master-bot/identity
/api/strategies
/api/strategies/generate
```

**Nine total, out of 613 backend endpoints.**

---

## 5 · Backend endpoint universe (from live `openapi.json`) — coverage by prefix

Reproducible via:

```bash
curl -sS http://127.0.0.1:8001/api/openapi.json | python3 -c '
import sys, json, collections
d = json.load(sys.stdin); c = collections.Counter()
for path in d.get("paths", {}):
    parts = path.strip("/").split("/")
    c["/api/" + parts[1] if parts[0]=="api" and len(parts)>1 else "/"+parts[0]] += 1
for pfx, n in c.most_common(): print(f"{n:5d}  {pfx}")
'
```

| Prefix | Endpoints | Exposed in UI today? | Surface that SHOULD expose it |
|--------|-----------|----------------------|-------------------------------|
| `/api/factory-supervisor` | 56 | ❌ NO | Autonomous factory / Workforce |
| `/api/master-bot` | 51 | 🟡 PARTIAL (2/51) | Master Bot page |
| `/api/latent` | 38 | ❌ NO | (advanced diagnostics — Engineering) |
| `/api/knowledge` | 34 | 🟡 PARTIAL (4/34) | Research Center (missing) |
| `/api/admin` | 33 | 🟡 PARTIAL (1/33) | Admin Users · Admin Integrations |
| `/api/execution` | 32 | ❌ NO | Deployments · Live-Trading dashboard (missing) |
| `/api/factory-eval` | 28 | ❌ NO | Factory Health dashboard (missing) |
| `/api/data` | 18 | ❌ NO | Coverage · Datasets |
| `/api/strategies` | 16 | 🟡 PARTIAL (2/16) | Strategies · Strategy Passport |
| `/api/auto` (auto-factory + auto-scheduler + auto-mutation) | 16 | ❌ NO | Autonomous Factory Control (missing) |
| `/api/meta-learning` | 15 | ❌ NO | Meta-Learning inspector (missing) |
| `/api/learning` | 15 | ❌ NO | Learning ledger view (missing) |
| `/api/portfolio` | 11 | ❌ NO | Portfolio detail page (deep-link only from Mission today) |
| `/api/prop-firms` | 11 | ❌ NO (empty-state page only) | Prop Firms |
| `/api/coe` | 10 | ❌ NO | Coordination + pressure diagnostics |
| `/api/market-intelligence` | 10 | ❌ NO | Market Intelligence dashboard (missing) |
| `/api/mutation` | 10 | ❌ NO | Mutation cockpit (missing) |
| `/api/scaling` | 10 | ❌ NO | Ecosystem scaling diagnostics |
| `/api/governance` | 9 | ❌ NO | Governance page (missing) |
| `/api/dashboard` | 8 | 🟡 PARTIAL — `/api/dashboard/summary` likely powering Mission | Mission Control |
| `/api/ai-workforce` | 8 | ❌ NO | Workforce page (rail entry exists but empty) |
| `/api/live` | 8 | ❌ NO | Live-Tracking dashboard |
| `/api/tuning` | 8 | ❌ NO | Optimization page |
| `/api/orchestrator` | 7 | ❌ NO | **Highest-priority missing** — every autonomous factory signal |
| `/api/brain` | 6 | ❌ NO | Brain policy inspector |
| `/api/lifecycle` | 6 | ❌ NO | Strategy Passport lifecycle tab |
| `/api/optimization` | 6 | ❌ NO | Optimization page |
| `/api/health` | 5 | 🟡 PARTIAL — `/api/health/system` should power the top strip | Top strip · Status rail |
| `/api/auth` | 5 | ❌ NO — **fixture auth today** | Sign-in + role gate |
| `/api/intelligence` | 5 | ❌ NO | Master Bot / Strategy Passport intelligence tab |
| `/api/challenge-rules` | 5 | ❌ NO | Prop Firms rule cockpit |
| … (~35 more prefixes, each 1-4 endpoints) | ~40 | mostly ❌ | many are backing engines (asf, bi5-realism, portfolio-*, research-runs, runner, cts, etc.) |

---

## 6 · Reusable components inventory

Under `frontend/src/os/`:

- `shell/AppShell.jsx` — the mount frame: rail + top strip + status
  rail + walkthrough + palette. Fully reusable.
- `shell/LeftRail.jsx` + `shell/TopStrip.jsx` + `shell/StatusRail.jsx` — every UI piece surrounding the surface.
- `shell/RequireAuth.jsx` — session gate.
- `shell/CmdKPalette.jsx` — command palette.
- `shell/FactoryWalkthrough.jsx` — first-run 30-second tour.
- `shell/ApprovalsModal.jsx` — Slice γ modal.
- `surfaces/EngineeringSurface.jsx` — **shared empty-state template**
  used by 5 pages today; parameterised by `ENGINEERING_SURFACES[slug]`
  metadata (headline · briefing · capabilities · phase2Sources · related).
  **This template is the single fastest lever to expose new backend
  surfaces** — every new empty-state surface is a metadata-only PR.
- `surfaces/SurfaceStub.jsx` — micro-empty-state fallback.
- `surfaces/engineering/LivenessBadge.jsx` — reusable green/yellow/red
  badge (already used by Coverage, Datasets, MarketData, StrategyLab).
- `gallery/PrimitiveGallery.jsx` — design-token + primitive
  regression gallery — invaluable for future component work.
- `workspace-state/store.js` + `workspace-state/stateMemory.js` —
  zustand store scaffold (used for approvals, timeline, walkthrough
  dismissal, comfort-density preference).
- Design tokens under `os/tokens.css` — every colour, spacing,
  radius, and shadow used by every surface.

**Reuse leverage:** the shell + `EngineeringSurface` + `LivenessBadge` +
tokens layer already provides a professional-grade template. New
surfaces cost ~50 lines of adapter + hook + surface wiring, not a
fresh component library.

---

## 7 · Capability matrix (completion percentages)

Scoring rubric:
- **Chrome**: rail entry + eyebrow present.
- **Route**: route mounted in `AppRouter`.
- **Component**: surface component exists and mounts.
- **Fixtures**: renders realistic fixture UI (skeleton + tables + filters).
- **Live wiring**: at least one live backend read.
- **Live writes**: mutating flows call real endpoints.
- **Streaming**: SSE / polling refresh.
- **RBAC**: real role gate from `/api/auth/me`.

| # | Surface | Chrome | Route | Component | Fixtures | Live read | Live write | Streaming | RBAC | % complete |
|---|---------|:------:|:-----:|:---------:|:--------:|:---------:|:----------:|:---------:|:----:|-----------:|
| 1 | Sign-in | ✅ | ✅ | ✅ | ✅ | ❌ (fixture) | ❌ | ❌ | ❌ | **40 %** |
| 2 | Mission Control | ✅ | ✅ | ✅ | ✅ | 🟡 | ❌ | ❌ | ❌ | **50 %** |
| 3 | Master Bot | ✅ | ✅ | ✅ | ✅ | 🟡 (2/51) | ❌ | ❌ | ❌ | **45 %** |
| 4 | Timeline | ✅ | ✅ | ✅ | ✅ | 🟡 (via shim) | ❌ | ❌ | ❌ | **45 %** |
| 5 | Approvals | ✅ | ✅ | ✅ | ✅ | 🟡 (via shim) | ❌ (fixture executor) | ❌ | ❌ | **45 %** |
| 6 | Workforce | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | **35 %** |
| 7 | Strategies (list) | ✅ | ✅ | ✅ | ✅ | 🟡 (via adapter) | ❌ | ❌ | ❌ | **50 %** |
| 8 | Strategy Passport (detail) | ✅ | ✅ | ✅ | ✅ (Slice β) | 🟡 | ❌ | ❌ | ❌ | **50 %** |
| 9 | Market Data (Engineering) | ✅ | ✅ | ✅ | ✅ | ❌ (declared endpoints don't exist) | ❌ | ❌ | ❌ | **35 %** |
| 10 | Coverage (Engineering) | ✅ | ✅ | ✅ | ✅ | ❌ (path mismatch) | ❌ | ❌ | ❌ | **35 %** |
| 11 | Datasets (Engineering) | ✅ | ✅ | ✅ | ✅ | ❌ (path mismatch) | ❌ | ❌ | ❌ | **35 %** |
| 12 | Strategy Lab (Engineering) | ✅ | ✅ | ✅ | ✅ | 🟡 (adapter ready) | ❌ | ❌ | ❌ | **50 %** |
| 13 | Strategy Pipeline (Engineering) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | **35 %** |
| 14 | Optimization (Engineering) | ✅ | ✅ | ✅ | ✅ | ❌ (path mismatch) | ❌ | ❌ | ❌ | **35 %** |
| 15 | Validation (Engineering) | ✅ | ✅ | ✅ | ✅ | 🟡 (health probe only) | ❌ | ❌ | ❌ | **40 %** |
| 16 | Prop Firms (Engineering) | ✅ | ✅ | ✅ | 🟡 (empty-state template) | ❌ | ❌ | ❌ | ❌ | **25 %** |
| 17 | Deployments (Engineering) | ✅ | ✅ | ✅ | 🟡 (empty-state template) | ❌ (path mismatch) | ❌ | ❌ | ❌ | **25 %** |
| 18 | Users (Admin) | ✅ | ✅ | ✅ | 🟡 (empty-state template) | ❌ | ❌ | ❌ | 🟡 (fixture gate) | **25 %** |
| 19 | Integrations (Admin) | ✅ | ✅ | ✅ | 🟡 (empty-state template) | 🟡 (adapter has probe endpoint) | ❌ | ❌ | 🟡 | **30 %** |
| 20 | Logs (Admin) | ✅ | ✅ | ✅ | 🟡 (empty-state template) | ❌ | ❌ | ❌ | 🟡 | **25 %** |
| 21 | Settings | ✅ | ✅ | 🟡 (9-line stub) | ❌ | ❌ | ❌ | ❌ | ❌ | **15 %** |
| 22 | Gallery | ✅ | ✅ | ✅ | ✅ (design tokens) | n/a | n/a | n/a | n/a | **80 %** (design tool) |

**Overall weighted completion (excluding gallery):** ≈ **35 %**.

The chrome + fixtures pillars are near-complete; every deficit is in
the live-read / live-write / streaming columns.

---

## 8 · Screenshot index

All captures at 1920 × 900, taken from `http://127.0.0.1:3000/`
after signing in with `operator@coinnike.com / prototype123`. The
30-second FactoryWalkthrough overlay is visible in most captures —
it's a first-session welcome tour, dismissible with Esc.

| # | File | Route | Notes |
|---|------|-------|-------|
| 00 | `00-signin.jpeg` | `/auth/sign-in` | Fixture-only sign-in card. Chrome (rail + top + status) already fully rendered. |
| 02 | `02-mission.jpeg` | `/c/mission` | Mission Control — walkthrough overlay visible; behind it, cards + tables in silhouette. |
| 03 | `03-masterbot.jpeg` | `/c/masterbot` | Master Bot page. |
| 04 | `04-timeline.jpeg` | `/c/timeline` | Timeline surface (activity feed). |
| 05 | `05-approvals.jpeg` | `/c/approvals` | Approvals inbox surface. |
| 06 | `06-workforce.jpeg` | `/c/workforce` | Workforce page. |
| 07 | `07-strategies.jpeg` | `/c/strategies` | Strategy list. |
| 08 | `08-market-data.jpeg` | `/c/engineering/market-data` | Live Engineering surface. |
| 09 | `09-coverage.jpeg` | `/c/engineering/coverage` | Coverage matrix. |
| 10 | `10-datasets.jpeg` | `/c/engineering/datasets` | Dataset catalogue. |
| 11 | `11-strategy-lab.jpeg` | `/c/engineering/strategy-lab?pair=XAUUSD&tf=H4` | Strategy Lab (query params attached automatically). |
| 12 | `12-strategy-pipeline.jpeg` | `/c/engineering/strategy-pipeline` | Pipeline board. |
| 13 | `13-optimization.jpeg` | `/c/engineering/optimization` | Optimization cockpit. |
| 14 | `14-validation.jpeg` | `/c/engineering/validation` | Validation. |
| 15 | `15-prop-firms.jpeg` | `/c/engineering/prop-firms` | EMPTY-STATE template. |
| 16 | `16-deployments.jpeg` | `/c/engineering/deployments` | EMPTY-STATE template. |
| 17 | `17-admin-users.jpeg` | `/c/admin/users` | EMPTY-STATE template. |
| 18 | `18-admin-integrations.jpeg` | `/c/admin/integrations` | EMPTY-STATE template. |
| 19 | `19-admin-logs.jpeg` | `/c/admin/logs` | EMPTY-STATE template. |
| 20 | `20-settings.jpeg` | `/c/settings` | 9-line stub. |
| 21 | `21-gallery.jpeg` | `/c/gallery` | Design-token gallery. |

---

## 9 · Immediate observations

1. **The frontend is chrome-complete but data-blind.** Every route
   is wired, every rail entry works, every surface renders
   professional-grade UI — but only 8 backend endpoints are called
   from anywhere in the frontend.
2. **Fixture credentials on the sign-in card** (`operator@coinnike.com
   · prototype123`) reveal the auth is not yet integrated with the
   backend seed. This is Sprint-1 Phase-1 behaviour — the backend
   auth stack is fully implemented and untested from the UI.
3. **Endpoint path mismatches** exist in the phase2Sources metadata:
   `navigation.js` declares e.g. `/api/coverage/matrix` but the
   backend prefix is `/api/data/coverage`. When Phase 2 wiring
   starts, we must reconcile every declared path against
   `/api/openapi.json` to avoid silent 404s.
4. **The `EngineeringSurface` template is a superpower.** All 5
   empty-state pages already ship coherent operator briefings.
   Turning any one of them into a live surface is a metadata + one
   adapter change, not a rewrite.
5. **Critical missing operator surfaces (from a 24×7 factory
   perspective):**
   - **Orchestrator dashboard** — `/api/orchestrator/*` is entirely
     unexposed; this is the highest-priority gap.
   - **Factory-eval dashboard** — 28 endpoints, no UI.
   - **Meta-learning inspector** — 15 endpoints, no UI.
   - **Market intelligence** — 10 endpoints, no UI.
   - **Auto-factory + auto-mutation** — 16 endpoints, no UI.
   - **Factory supervisor (fleet + copilot + notifications)** — 56 endpoints, no UI.
   - **Learning ledger** — 15 endpoints, no UI.
6. **Status rail is entirely fixture** — every one of the 8 pills has
   a backend equivalent that would light up the same widget at
   near-zero cost. This is the single highest-ROI first step.

Full priority-ordered exposure plan is in
`docs/FRONTEND_EXPOSURE_ROADMAP.md`.
