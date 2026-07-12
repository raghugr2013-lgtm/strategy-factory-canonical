# SYSTEM_READINESS_REPORT.md

**Report type:** Post-hydration system readiness projection.
**Status:** Forecast only. Hydration has NOT yet occurred.
**Reference:** `HYDRATION_PLAN.md` (this report describes the state achieved by executing that plan).

This document answers the question: **"Once HYDRATION_PLAN.md is executed with the recommended Options (C/C), what is immediately usable, what stays dormant, what is reservation-only, and what is missing?"**

---

## 1. Assumptions

1. Hydration follows the recommended options in `HYDRATION_PLAN.md`:
   * **§5.1 Option C** — Honour `ENABLE_DYNAMIC_MARKET_UNIVERSE=1`; keep parity hard gates OFF; honour all other operator-set flags in App.zip `.env`.
   * **§5.3 Option C** — Hydrate `_inventory/asf_ui_handoff/` + `_inventory/old1vcpu/src/` only.
2. `frontend/.env` retains the current pod URL.
3. All required Python deps install successfully.
4. MongoDB is reachable at `MONGO_URL` (already wired in `/app/backend/.env`).
5. Admin user seeds successfully on first boot.

---

## 2. Immediately usable after hydration (Class A)

### 2.1 Operator UI shell (entire CommandShell — full M0–M5)

* CommandBar with palette button + status pill + LLM activity dot + density toggle + premium toggle + user menu + notification bell
* TopTabBar (M0) — 10 module tabs
* LifecycleRail (M1) — Generate → Mutate → Validate → Score → Master Bot → Deploy
* LeftRail with 10 module glyphs (Dashboard / Lab / Explorer / Mutate / Portfolio / Prop Firm / Exec / AI / Diag / Governance)
* StatusRail (bottom strip — chips for orchestrator, LLM, ingestion, schedulers)
* DangerRibbon (emergency banner; renders on small viewports)
* OperatorInboxDrawer (M4)
* Live NotificationDrawer (⌘⌥N) — reads `/api/monitoring/status` + `/api/admin/widening-proposals` + `/api/orchestrator/heartbeat`
* CopilotPanel (⌘J) — advisory-only (no LLM call until `FS_ENABLE_COPILOT_ADVANCED=true`)
* Inspector pane (⌘.) — posture-aware
* CommandPalette (⌘K) — module jumps + 12 commands
* ShortcutsOverlay (`?`)
* AriaLiveRegion (a11y)
* Mobile surfaces (ModuleDrawer + StatusSheet) for tablet / briefing posture
* JWT-based AuthGate (operator must log in once)

### 2.2 Backend — every operator-facing surface live and reachable

| Module | Sections immediately usable | Endpoints live |
|---|---|---|
| Dashboard | Mission Briefing | `/api/orchestrator/heartbeat`, `/api/monitoring/status`, `/api/readiness/snapshot` |
| Research Lab | Strategy Panel, Analysis, Backtest, cBot, Optimization, Validation | `/api/strategies/*`, `/api/cbot/*`, `/api/optimization/*`, `/api/dashboard/generate` |
| Strategy Explorer | Explorer, Saved, Compare | `/api/strategies?…`, `/api/strategy-memory/*`, `/api/research-lineage/*` |
| Mutation Engine | Auto Mutation Runner, Multi-Cycle, Auto Factory, Auto Factory Phase 55, Auto Selection, Master Bot, Master Bot Compile | `/api/auto-mutation/*`, `/api/multi-cycle/*`, `/api/auto-factory/*`, `/api/auto-selection/*`, `/api/master-bot/*` |
| Portfolio OS | Builder, Panel, Intelligence | `/api/portfolio-builder/*`, `/api/portfolio/*`, `/api/portfolio-intelligence/*` |
| Prop Firm | Prop Firms admin, Firm Match | `/api/prop-firms/*`, `/api/match-firms-phase4`, `/api/phase4-matching/*`, `/api/challenge-matching/*`, `/api/prop-firm-intelligence/*`, `/api/prop-firm-analysis/*` |
| Execution Center | Paper Execution, Trade Runner, Live Tracking | `/api/execution/*`, `/api/trade-runner/*`, `/api/live-tracking/*` |
| AI Workforce | Live River, Orchestrator, Auto-Scheduler | `/api/llm/*`, `/api/orchestrator/*`, `/api/auto-scheduler/*` (within auto-mutation) |
| Diagnostics | **Deployment Readiness, Parity, Ingestion Health, Strategy Ingestion, Pipeline Logs, Market Data Workbench (Manual + Automated + Archive), MonitoringSuite (Runtime + Soak + CPU Pool + Scaling), BI5 R1 Health** | `/api/readiness/*`, `/api/cbot-parity/*`, `/api/latent/*`, `/api/pipeline*`, `/api/data*`, `/api/monitoring/*`, `/api/cpu-pool/state`, `/api/scaling/*`, **`/api/diag/bi5/health`** |
| Governance | Governance card, **Universe Governance, Symbol Registry (DSR-1)**, Rules Review, Env Priority, Readiness, Admin composite | `/api/governance/*`, **`/api/admin/market-universe/*`, `/api/latent/market-universe`**, `/api/prop-firm-rules-review/*`, `/api/env-priority/*`, `/api/admin/*`, `/api/admin/flag-governance/*`, `/api/admin/execution-realism/*`, `/api/phase12-tuning/*` |

### 2.3 Schedulers running in the background

| Scheduler | Cadence | Effect |
|---|---|---|
| Auto Data Maintenance — BID | every 15 min | Pulls 1-minute bar increments per ingestion-eligible symbol |
| Auto Data Maintenance — BI5 | every 60 min | Calls `run_bi5_ingest(lookback_days=30)` per symbol (B-1) |
| Auto Discovery scheduler | configurable (UI sets) | Drives `auto_mutation_runner` |
| Orchestrator scheduler | configurable (UI sets) | Drives `ai_orchestrator` decisions |

### 2.4 Diagnostic / latent endpoints (≈30, all advisory)

Live and queryable: `/api/latent/feature-flags`, `…/activation-timeline`, `…/activation-governance`, `…/compute-probe`, `…/safe-to-widen`, `…/widening-history`, `…/observability`, `…/advanced-scaffolding`, `…/cbot-log-diagnostic`, `…/deployment-readiness`, `…/deployment-extras`, `…/factory-runner-heartbeat`, `…/ingestion-aggregate`, **`…/market-universe`**, `…/parity-certification`, `…/htf-parity`, `…/cbot-trade-parity`, `…/execution-realism-defaults`, `…/risk-of-ruin`, `…/lifecycle-decay`, `…/calibration`.

### 2.5 Newly active under Option C (DSR-3 ON)

| Capability | What changes |
|---|---|
| **`market_universe_symbols` is the runtime ingestion universe** | The 60-min BI5 ingest + 15-min BID maintenance pull symbols from the registry (where `eligibility.ingestion_enabled=true`), NOT from `config/symbols.py`. |
| **Adapter cache populated at boot** | Log line `[startup] market_universe adapter cache — loaded=N`. |
| **DSR-1 UI is authoritative** | Operator edits in Symbol Registry are reflected in the next scheduler cycle. |
| **Shadow-audit collection `market_universe_audit`** | Every CRUD write produces an audit row with 90-day TTL. |

### 2.6 BI5 R1 fully closed (B-1, B-2, B-9)

| BI5 R1 item | State after hydration |
|---|---|
| B-1: Scheduler dispatches `run_bi5_ingest()` | **Active** — every 60 min |
| B-2: UI BI5 source propagation (in DataUpload / DataMaintenance) | **Active** — operator picks BI5 source in Market Data Workbench |
| B-9: One-shot historical backfill | **Ready** — `python -m scripts.bi5_one_shot_backfill` (manual one-shot; recommended on first hydration to bootstrap historical coverage) |
| Per-symbol health surface | **Active** — `/api/diag/bi5/health` + `BI5HealthPanel` |
| `bi5_ingest_log` extended fields | Schema-ready but Evidence/Trust/Dossier/Marketplace fields stay null (consumers Phase 13/14 not yet built) |

---

## 3. Dormant behind flags (Class F)

These ship installed, idempotent, and observable — but produce no behaviour change until the operator explicitly flips the flag. Each row is a quick "next decree away" potential capability.

### 3.1 Factory Supervisor stack (FS-P1.0..1.4)

| Capability | Flag(s) | Why dormant by default |
|---|---|---|
| Supervisor heartbeat + events writes | `ENABLE_FACTORY_SUPERVISOR=false` | Awaits operator decree |
| Notification Center backend writes | `ENABLE_NOTIFICATION_CENTER=false` | Awaits operator decree |
| Notification API consumption gate | `FS_ENABLE_NOTIFICATION_API=false` | Awaits operator decree |
| Persistent worker scheduler | `FS_ENABLE_WORKER_SCHEDULER=false` | Awaits operator decree |
| System State View | `FS_ENABLE_SYSTEM_STATE_VIEW=false` | Awaits operator decree |
| Architect Dashboard advisor | `FS_ENABLE_ARCHITECT_DASHBOARD=false` | Awaits operator decree |
| Recommendation Engine | `FS_ENABLE_RECOMMENDATION_ENGINE=false` | Awaits operator decree |
| Eligibility Engine | `FS_ENABLE_ELIGIBILITY_ENGINE=false` | Awaits operator decree |
| Feature Activation Governance | `FS_ENABLE_FAG_ENGINE=false` | Awaits operator decree |
| Operational Copilot | `FS_ENABLE_COPILOT=false` | Awaits operator decree |
| Advanced Copilot (provider-agnostic) | `FS_ENABLE_COPILOT_ADVANCED=false`, `FS_COPILOT_PROVIDER=none` | Awaits operator decree + provider registration |
| Auto-Learning aggregator (read-only insights) | `FS_ENABLE_AUTO_LEARNING=false` | Awaits operator decree |
| Auto-Learning loop | `FS_ENABLE_AUTO_LEARNING_LOOP=false` — **operator hard-vetoed** (also gated by `ENABLE_AUTONOMOUS_DISCOVERY`) | Permanent — strict operator directive |

### 3.2 Scoring / lifecycle

| Capability | Flag(s) | Notes |
|---|---|---|
| Risk-of-Ruin in `deploy_score` | `ENABLE_RISK_OF_RUIN=false`, `RISK_OF_RUIN_WEIGHT=0.0` | RoR computed + persisted; weight is zero. |
| Aging penalty applied | `ENABLE_AGING_PENALTY=false` | Computed but not applied. |
| Aging auto-demotion | `ENABLE_AGING_AUTO_DEMOTION=false` | Requires `ENABLE_AGING_PENALTY` 30+ day soak first. |
| Pass-probability calibration | `ENABLE_CALIBRATION=false` | Calibration table built + persisted; identity transform applied. |

### 3.3 Mutation / orchestration

| Capability | Flag(s) |
|---|---|
| Adaptive env_priority rotation | `ENABLE_ADAPTIVE_ROTATION=false` |
| Anti-correlation filter on mutations | `ENABLE_ANTI_CORRELATION_FILTER=false` |
| AI advisory surface | `ENABLE_AI_ADVISORY=false` |
| Deployment throttle | `ENABLE_DEPLOYMENT_THROTTLE=false` |
| Autonomous discovery (RULE 12 trigger) | `ENABLE_AUTONOMOUS_DISCOVERY=false` |
| Cadence scheduler (per-cell min gap) | `ENABLE_CADENCE_SCHEDULER=false` |
| Adaptive cooldown | `ENABLE_ADAPTIVE_COOLDOWN=false` |
| Event continuation queue | `ENABLE_EVENT_CONTINUATION=false` |
| Replay priority sort | `ENABLE_REPLAY_PRIORITY=false` |
| Process pool — backtest hot path | `USE_PROCESS_POOL=false`, `ENABLE_PROCESS_POOL_BACKTEST=false` |
| Process pool — mutation hot path | `USE_PROCESS_POOL=false`, `ENABLE_PROCESS_POOL_MUTATION=false` |
| Compute-aware orchestration | `COMPUTE_AWARE_ORCHESTRATION=false` |
| Soak stability emitter | `ENABLE_SOAK_STABILITY_EMITTER=false` |
| Rotational orchestration would_execute | `ENABLE_ROTATIONAL_ORCHESTRATION=false` |
| Agent advisor LLM call | `ENABLE_AGENT_ADVISOR=false` |

### 3.4 Scaling / capacity

| Capability | Flag(s) | Notes |
|---|---|---|
| Band-based routing | `ENABLE_BAND_BASED_ROUTING=false` | Scaling router returns ACCEPT for all. |
| Adaptive pool sizing | `ENABLE_ADAPTIVE_POOL_SIZING=false`, `WORKLOAD_PROFILE=auto` | `cpu_pool.pool_size()` returns legacy value. |
| Admission control | `ENABLE_ADMISSION_CONTROL=false` | Gate always admits. |

### 3.5 Parity

Under Option C: **all four parity flags remain OFF** for safety.

| Capability | Flag(s) | Notes |
|---|---|---|
| cBot trade-lifecycle parity simulator | `ENABLE_CBOT_TRADE_PARITY=false` | Module callable either way. |
| HTF parity validator | `ENABLE_HTF_PARITY_VALIDATION=false` | Module callable either way. |
| Trade-parity hard gate | `ENABLE_TRADE_PARITY_HARD_GATE=false` | Awaits soak window of advisory sign-offs. |
| HTF-parity hard gate | `ENABLE_HTF_PARITY_HARD_GATE=false` | Awaits soak window. |

> If operator selects Option A (honour all canonical .env settings), §3.5 flips to active and the four parity flags become hard requirements on every cBot export. **Recommendation in HYDRATION_PLAN: Option C — keep OFF.**

### 3.6 Execution realism / multi-runner / DSR auto-ingest

| Capability | Flag(s) | Notes |
|---|---|---|
| Execution realism defaults registry consumption | `ENABLE_EXECUTION_REALISM_DEFAULTS=false` | CRUD live; no engine reads. |
| Master Bot runner auto-routing | `RUNNER_AUTO_ROUTE_AT_REGISTER=false` | Single-runner mode active. |
| Auto token rotation | `RUNNER_AUTO_ROTATE=false`; cadence 30d | Manual rotation always available. |
| Multi-account fan-out | `RUNNER_MULTI_ACCOUNT_ENABLED=false` | Synthetic single-account envelope. |
| Market universe auto-ingest hook | `MARKET_UNIVERSE_AUTO_INGEST=false` | Documentation-only today. |

---

## 4. Reservation-only (Class G — UI placeholders, no engine)

These render in the UI but have **no backend** and **no behaviour**. They exist to anchor navigation/layout for forthcoming phases.

| Surface | UI route | Phase | Backend status |
|---|---|---|---|
| **Strategy Score Architecture** (Quality · Evidence · Market · Trust) | `/c/explorer/score-rubric` | M3 | **Not built** |
| **Strategy Dossier — Passport + 12 reports** | `/c/explorer/passport-reservations` | Phase 13 | **Not built** |
| **Marketplace Layer** | `/c/explorer/marketplace-reservations` | Phase 15 | **Not built** |
| **Dual Scorecards + Auto Valuation** (Prop Firm + Investor + pricing inputs) | `/c/portfolio/scorecards-reservations` | Phase 14 | **Not built** |
| **Broker Accounts Chip Row** — cTrader Live + cTrader Demo + Windows VPS + Broker Telemetry | `/c/exec/brokers` | Future | **Not built** |
| `pages/Welcome/` directory (empty) | n/a | layout-only | — |

---

## 5. Missing (not built — gaps to close)

These items appear in the operator roadmap but **have no backend engine and no working UI** today. They are tracked as future development:

### 5.1 Strategy Dossier Engine (Phase 13)
**Needed:** persistence schema (`strategy_dossiers` collection), renderer pipeline (Passport + 12 reports), data lineage feeders from BI5 R1 / Evidence Score / Trust Score, dossier signing for marketplace export.
**Status:** UI reservation only (`Phase13ReservationsCard.jsx`).

### 5.2 Automated Valuation Engine (Phase 14)
**Needed:** dual scorecard inputs (Prop Firm scorecard + Investor scorecard derived from existing Pass Probability + RoR + Aging signals), pricing model (no manual price fields), Auto Valuation rules, valuation history.
**Status:** UI reservation only (`Phase14DualScorecardCard.jsx`). The underlying signals exist (Pass Probability is computed; RoR is computed; Aging is computed) — what is missing is the consumption + scoring + pricing surface.

### 5.3 Marketplace Layer (Phase 15)
**Needed:** signed-product packager (`strategy_pack` + `bundle_pack` + `masterbot_pack`), public read-API surface isolated from ASF private factory, customer-facing UI (separate codebase), payment + entitlement, telemetry isolation, marketplace ranking engine consumer.
**Status:** UI reservation only (`Phase15MarketplaceReservation.jsx`).
**Note:** Marketplace ranking is the FOURTH consumer of the Strategy Score architecture, after Dossier, Valuation, and Auto-Selection.

### 5.4 cTrader runtime integration
**Needed:** broker connector (account auth, market-data subscription, order routing), live broker telemetry feed into the existing `live_tracking_engine`, error/disconnect resilience, FIX or HTTPS implementation, position bookkeeping reconciliation.
**Status:** UI placeholder (`ExecutionBrokerChips.jsx`) only.

### 5.5 Windows Agent / VPS allocation runtime
**Needed:** agent binary that registers itself in the runner registry, capacity heartbeats, work polling, supervised execution of compiled cBot packages.
**Status:** Primitives exist (`engines/host_capability.py`, `engines/scaling_*.py`, `engines/runner_*.py`, `api/runner.py`, multi-account envelope). No agent shipped.

### 5.6 Strategy Score Architecture engines (M3)
**Needed:** four scoring sub-engines (Quality, Evidence, Market, Trust) that consume existing primitives (Pass Probability, RoR, BI5 coverage, parity sign-offs, aging) and produce a composite score persisted at the strategy level. Feeds 3.1 / 3.2 / 3.3.
**Status:** Reservation card only (`StrategyScoreReservationCard.jsx`).

### 5.7 Capacity-aware factory orchestration loop
**Needed:** consumption of `engines/compute_probe.py` + `engines/host_capability.py` + `engines/admission_controller.py` outputs at the `engines/auto_factory.py` entry point so the factory auto-throttles. The primitives are dormant; the wiring is the gap.
**Status:** Code paths exist; not connected end-to-end.

### 5.8 Master Bot V2 (auto-orchestration)
**Needed:** automatic re-rank + re-compose + capacity-aware deploy. Today operator triggers each Master Bot compile.
**Status:** V1 single-runner is shipped (MB-1, MB-2, MB-3, MB-9 P1/P2.B). V2 dormant flags exist.

### 5.9 BI5 R2 schema extension (Evidence Score · Trust Score · Strategy Dossier · Marketplace Quality)
**Needed:** extend `bi5_ingest_log` with these four scoring fields; produce them per cycle. Today they exist as nullable schema slots.
**Status:** Schema-ready, no producer.

### 5.10 Migration toolchain (the remaining 5 documents from the original brief)

These were deliberately deferred per the operator's "audit first" direction:
* `MIGRATION_EXPORT_PLAN.md`
* `DOWNLOAD_MANIFEST.md`
* `MIGRATION_PRIORITY.md`
* `MIGRATION_COMPATIBILITY_AUDIT.md`
* `POST_IMPORT_PIPELINE.md`

These will operate on the 1-vCPU deployment's hundreds of generated strategies. Out of scope for hydration; in scope after the hydrated pod is validated.

---

## 6. Readiness summary table

| Category | Count of subsystems | % of total roadmap value (rough operator weighting) |
|---|---|---|
| **A — Immediately usable** | ≈70 | 65% |
| **B — Mounted but palette-hidden** | 3 | 1% |
| **F — Dormant behind flag** | 30+ | 20% — usable in days/weeks via flag flips + soak |
| **G — Reservation only (UI placeholder)** | 6 | 8% — usable in months once Phase 13/14/15 engines land |
| **Missing — not yet built** | 10 distinct workstreams (§5) | 6% — measured in quarters |
| **Removed / deprecated / dead** | 3 minor items | 0% — intentional |

---

## 7. What this means in plain language

After hydration with the recommended options:

1. **The operator has a complete, working operator console.** Every primary surface (StrategyDashboard, Auto Factory, Validation, Portfolio, Master Bot, Paper Execution, Trade Runner, Live Tracking, BI5 Health, Symbol Registry) is reachable, authenticated, and responding to the canonical backend.

2. **The Dynamic Symbol Registry is live and authoritative** (DSR-1 UI + DSR-2 scheduler consumption + DSR-3 flag ON). The operator can add a new symbol via UI and see it appear in the next BI5/BID ingest cycle.

3. **BI5 R1 is fully closed.** Per-symbol health is observable; one-shot backfill is one CLI command away.

4. **No autonomous loops are running.** Every mutation/deployment requires an operator click. Auto-Learning is dormant. Factory Supervisor is dormant.

5. **Parity hard gates are NOT enforced** (per recommended Option C). cBot exports succeed using signal parity alone, with trade-parity + HTF-parity validators available as advisory probes.

6. **Phase 13/14/15 are visible-but-empty.** The reservation cards are deliberately stable layout anchors so when those engines land they slot in without UI re-flow.

7. **There is no cTrader broker integration today.** Live execution against a real broker is the largest gap.

The hydrated pod represents **the maximum capability of the existing codebase**, not a feature-complete product. The roadmap §3 priorities (DSR ✓ → BI5 ✓ → Dossier → Valuation → Marketplace → Deployment readiness) become the operator's natural next four work items.

---

## 8. Recommended first 24 hours after hydration

1. **Hour 0:** Execute `HYDRATION_PLAN.md` §2. Validate §9.
2. **Hour 0–1:** Run `python -m scripts.bi5_one_shot_backfill` to bootstrap historical BI5 coverage for the 7 seeded symbols.
3. **Hour 1–3:** Trigger one manual Auto Factory run from `/c/mutate/factory` to confirm end-to-end strategy generation works.
4. **Hour 3–6:** Register one **new** symbol via Symbol Registry UI (e.g. `XAUEUR`), confirm it appears in the next BI5/BID maintenance cycle (DSR-3 is ON).
5. **Hour 6–24:** Soak. Watch:
   * `/api/latent/deployment-readiness` stays green.
   * `/api/latent/feature-flags` reflects the chosen flag set.
   * `audit_log` accumulates ingest + scheduler rows.
   * `market_universe_audit` collection accumulates the test CRUDs.

After 24 hours of clean soak, you have the **real working baseline** the brief calls for. From there:

* Produce the 5 remaining migration docs (§5.10).
* Begin Phase 13 (Strategy Dossier Engine) — `MISSING ITEM #1`.
* Decide whether to flip parity hard gates after reviewing accumulated sign-offs (`/api/latent/parity-certification`).
