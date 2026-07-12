# MISSING_FROM_UI.md

**Audit type:** Capabilities that exist in code (backend OR frontend OR both) but are NOT visible to an operator from the primary navigation.
**Status:** Read-only. No code modified. No surfaces mounted.
**Generated:** 2026-06-12 (companion to `CAPABILITY_CATALOG.md`)

**Filter criteria:** A capability is "missing from UI" when ANY of these holds:
1. **Engine + API live, but no operator panel** — operator must use raw curl / Mongo / Power-User route.
2. **Frontend component exists, but no section in `modulesRegistry.js` references it** — orphan UI.
3. **Frontend component is nested inside an unmounted parent** — reachable in source only.
4. **Frontend panel exists and is wired, but the backend that powers it is flag-gated dormant** — UI shows but is empty / error.

Active surfaces (visible & operational) are out of scope of this document — they live in `ROADMAP_PARITY_REPORT.md` / `CAPABILITY_CATALOG.md`.

---

## 1. Investigation summary by area (operator's checklist)

| # | Area | Backend code? | Frontend code? | Mounted? | Operator-visible? | Verdict |
|---|---|---|---|---|---|---|
| 1 | Copilot (basic) | Y (dormant flag) | Y (`shell/CopilotPanel.jsx`) | Y (mounted in `CommandShell`) | YES — togglable via Command Bar | **Visible (degrades if `/api/llm/call-log/recent` empty)** |
| 2 | Copilot (advanced multi-provider) | Y (`copilot_advanced.py` + API × 4) | N | N | NO | **Missing from UI** |
| 3 | AI Architect (Architect Dashboard) | Y (`architect_advisor.py` + API × 2) | Y (`ArchitectDashboard.jsx`) | N (zero importers) | NO | **Missing from UI** |
| 4 | Advisor Stream (inside ArchitectDashboard) | Y (`architect_advisor.py`) | Y (`ArchitectDashboard.jsx::NextRecommendedActionCard`) | N | NO | **Missing from UI** |
| 5 | Recommendation Feed | Y (`recommendation_engine.py` + API × 2) | Y (`ArchitectDashboard.jsx`) | N | NO | **Missing from UI** |
| 6 | Notification Center (backend-persisted) | Y (`notification_center.py` + API × 6) | Y (`ArchitectDashboard.jsx::NotificationsCard`) | N (parent unmounted) | NO | **Missing from UI** (Operator Inbox UI store mounted instead — runs UI-only) |
| 7 | Operator Inbox (UI-only) | N (event bus only) | Y (`OperatorInboxDrawer.jsx`) | Y | YES | **Visible** (UI-only; backend NC dormant) |
| 8 | Chat capabilities | **NONE** | **NONE** | N/A | NO | **Not built** — no chat code anywhere in the repo. The Operator Inbox is event cards + quick-action links (per M4 design brief); it is explicitly not a chat surface. Copilot is read-only advisory, not interactive chat. |
| 9 | Factory Supervisor (master shell) | Y (24 engines, 1 router, ~40 endpoints) | Y (`OperatorParityPanels::FactorySupervisorPanel`) | N | NO | **Missing from UI** |
| 10 | Factory Supervisor — Worker Runtime | Y (`worker_runtime.py`, `worker_scheduler.py`, `workload.py`) | N | N | NO (API only) | **Missing from UI** |
| 11 | Factory Supervisor — Defer Queue | Y (`defer_queue.py`, 5 endpoints) | N | N | NO (API only) | **Missing from UI** |
| 12 | Factory Supervisor — Routing Policy / Submission Dispatcher | Y (`routing_policy.py`, `submission_dispatcher.py`) | N | N | NO (API only) | **Missing from UI** |
| 13 | Factory Supervisor — Heartbeat / Lock / Events | Y (`supervisor_heartbeat.py`, `supervisor_lock.py`, `supervisor_events.py`) | N | N | NO (API only) | **Missing from UI** |
| 14 | Factory Supervisor — Fleet Registry | Y (`fleet_registry.py`) | Y (`ArchitectDashboard::FleetHealthCard`) | N | NO | **Missing from UI** |
| 15 | Factory Supervisor — Remote Transport | Y (`remote_transport.py`) | N | N | NO (API only) | **Missing from UI** |
| 16 | Factory Supervisor — System State View | Y (`system_state_view.py`) | N | N | NO (API only) | **Missing from UI** |
| 17 | Factory Supervisor — Eligibility Engine | Y (`eligibility_signals.py`, 2 endpoints) | N | N | NO (API only) | **Missing from UI** |
| 18 | Factory Supervisor — FAG (Flag Auto-Governance) Proposals | Y (`fag_proposals.py`, 8 endpoints) | N | N | NO (API only) | **Missing from UI** |
| 19 | Factory Supervisor — Scheduler control | Y (3 endpoints: status/start/stop) | N | N | NO (API only) | **Missing from UI** |
| 20 | Auto Learning loop | Y (`auto_learning.py`, 5 endpoints) | Y (`ArchitectDashboard::AutoLearningPanel`) | N (parent unmounted) | NO | **Missing from UI** |
| 21 | DSR (Symbol Registry) | Y | Y (`SymbolRegistryPanel.jsx`) | Y (`governance/symbol-registry`) | YES | **Visible** ✅ |
| 22 | DSR — Audit log (`market_universe_audit`) | Y (90-day TTL collection) | N | N | NO (Mongo only) | **Missing from UI** — no panel surfaces audit history |
| 23 | BI5 R1 health surface | Y (`/api/diag/bi5/health`) | Y (`BI5HealthPanel.jsx`) | Y (`diag/bi5-health`) | YES | **Visible** ✅ |
| 24 | BI5 R1 — one-shot backfill | Y (`scripts/bi5_one_shot_backfill.py`) | N | N | NO (CLI only) | **Missing from UI** — no "Backfill Now" button in MarketDataWorkbench |
| 25 | BI5 Certification (strategy + data) | Y (8 endpoints under `/api/bi5-cert/*`) | N | N | NO | **Missing from UI** — no `bi5_certifications` operator panel |
| 26 | BI5 R2 (auto-cert sweep B-4 / B-5 / B-8) | **N** (queued P0) | N | N | NO | **Not yet built** |
| 27 | BI5 R3 (tick replay B-3 / B-6 / B-7) | **N** (queued P0) | N | N | NO | **Not yet built** |
| 28 | Master Bot — Dashboard | Y | Y | Y (`mutate/master-bot`) | YES | **Visible** ✅ |
| 29 | Master Bot — Compile | Y | Y (`MutateMasterBotCompile.jsx`) | Y (`mutate/master-bot-compile`) | YES | **Visible** ✅ |
| 30 | Master Bot — Cluster sub-tab (planned in `04_COMPONENT_REHOUSING_MATRIX.md`) | Y | N | N | NO | **Missing from UI** — visual approval recommended secondary mount under Monitoring Cluster |
| 31 | Master Bot — Diff / Pack / Export / Deployment / Signer | Y (5 engines) | N (consumed by dashboard) | — | Partial | **Visible via dashboard** (engines are wired into the dashboard's actions) |
| 32 | Prop Firm — Admin | Y | Y (`PropFirmsAdmin.js` + `AddFirmModal.js`) | Y (`propfirm/admin`) | YES | **Visible** ✅ |
| 33 | Prop Firm — Firm Match | Y | Y (`FirmMatchPanel.js`) | Y (`propfirm/match`) | YES | **Visible** ✅ |
| 34 | Prop Firm — Challenge Matching | Y (`challenge_matching_engine.py` + API × 4) | Y (`ChallengeMatchingPanel` in `OperatorParityPanels.jsx`) | N (lazy-imported but no section reference) | NO | **Missing from UI** |
| 35 | Prop Firm — Prop Firm Analysis | Y (`prop_firm_panel.py` + API × 2) | N | N | NO (API only) | **Missing from UI** — no dedicated panel; consumed indirectly by Firm Match |
| 36 | Prop Firm — Prop Firm Intelligence | Y (`prop_firm_intelligence.py` + API) | N | N | NO (API only) | **Missing from UI** — consumed indirectly |
| 37 | Prop Firm — Challenge Simulator / Manager / Portfolio | Y (3 engines) | N | N | NO (engines only) | **Missing from UI** |
| 38 | Runner Registry / Router / Token Rotation / Account Migration | Y (4 engines + API) | N | N | NO | **Missing from UI** |
| 39 | Factory Runner Heartbeat | Y (engine + API) | N | N | NO | **Missing from UI** |
| 40 | Adaptive Concurrency / Pool Sizer / Cooldown | Y (3 engines) | N | N | NO | **Missing from UI** (flag-controlled only) |
| 41 | Admission Controller / Queue Pressure | Y (3 engines) | N | N | NO | **Missing from UI** (flag-controlled only) |
| 42 | Calibration Framework | Y (engine + API) | N | N | NO | **Missing from UI** |
| 43 | Risk of Ruin | Y (engine + API) | N | N | NO (API only) | **Missing from UI** (weight pinned 0.0; engine emits per-strategy RoR) |
| 44 | Lifecycle Decay / Aging | Y (engine + API) | N | N | NO | **Missing from UI** (engine emits aging metrics; weight=0) |
| 45 | Safe-to-Widen / Widening History | Y (2 engines + 2 APIs) | N | N | NO | **Missing from UI** (history not browsable; only widening proposal flow surfaces) |
| 46 | Rotational Orchestrator | Y (engine + API) | N | N | NO | **Missing from UI** |
| 47 | Compute Probe | Y (engine + API) | N | N | NO | **Missing from UI** |
| 48 | Event Continuation / Replay Priority / Cadence Scheduler | Y (3 engines) | N | N | NO | **Missing from UI** (flag-controlled only) |
| 49 | Activation Governance / Activation Timeline | Y (2 engines + 2 APIs) | N | N | NO (API only) | **Missing from UI** — no operator-facing activation history panel |
| 50 | Multi-Account Envelope | Y (engine) | N | N | NO | **Missing from UI** |
| 51 | Multi-Asset Portfolio | Y (engine) | N | N | NO | **Missing from UI** (consumed by Portfolio Builder indirectly) |
| 52 | Strategy Profiler / Ranking Engine / Refinement | Y (3 engines) | N | N | NO | **Engine-only by design** (consumed by Auto Selection + post-import pipeline) |
| 53 | Strategy IR (5 modules) | Y | N | N | NO | **Engine-only by design** |
| 54 | Spread Analyzer / Tick Validator / Gap Analyzer | Y (3 engines) | N | N | NO | **Engine-only by design** (consumed by ingestion pipeline) |
| 55 | Cbot Engine (5 modules) | Y | Y (via CbotPanel) | Y (`lab/cbot`) | YES | **Visible** ✅ |
| 56 | R5 Shadow Comparator | Y (engine) | N | N | NO | **Missing from UI** |

---

## 2. Specifically investigated areas (deep dive)

### 2.1 Copilot

| Subsystem | Backend | Frontend | Mounted | Verdict |
|---|---|---|---|---|
| `CopilotPanel.jsx` | Reads `/api/orchestrator/heartbeat` + `/api/llm/call-log/recent` | Y | Y (mounted in `CommandShell.jsx::357`) | **Visible** |
| `copilot_context.py` (FS-backed) | Live, gated by `FS_ENABLE_COPILOT` | — | — | **Dormant backend** |
| `copilot_operational.py` (canonical Q&A) | Live, 4 endpoints (`/copilot/context`, `/copilot/answers`, `/copilot/answer`) | — | — | **Hidden** |
| `copilot_advanced.py` (multi-provider) | Live, 4 endpoints (`/copilot/advanced/manifest`, `/providers`, `/invoke`) | — | — | **Hidden** |

**Net verdict:** Operator sees a Copilot panel, but it reads orchestrator heartbeat + LLM call log directly. The richer FS-backed Copilot (operational Q&A + advanced multi-provider) is hidden. **Missing UI:** a Copilot v2 panel that consumes `/api/factory-supervisor/copilot/*`.

### 2.2 AI Architect

| Subsystem | Backend | Frontend | Mounted | Verdict |
|---|---|---|---|---|
| `architect_advisor.py` | Live, 2 endpoints (`/architect/dashboard`, `/architect/recommended-action`) | Y (in `ArchitectDashboard.jsx`) | N (parent unmounted) | **Missing from UI** |
| `architect_scaling_view.py` | Live (consumed) | — | — | **Engine-only** |
| `agent_advisor.py` | Live (consumed by `latent/advanced_scaffolding`) | — | — | **Engine-only** |

**Net verdict:** The Architect Dashboard is the single most complete hidden operator surface (~940 LOC of UI + ~5 backend integration points). Reachable today only by direct file open. **Missing UI:** lift `ArchitectDashboard` (or its 9 cards) into the primary nav.

### 2.3 Advisor Stream

A SUBSURFACE inside `ArchitectDashboard.jsx`:
- `NextRecommendedActionCard` (L131) — recommendation from `architect_advisor.recommended_action()`
- `FleetHealthCard` (L198)
- `QueuePressureCard` (L225)
- `DeferQueueCard` (L248)
- `WorkerStatusCard` (L439)
- `RoutingCard` (L482)
- `AdmissionScalingEventsCard` (L501)
- `DeploymentReadinessSection` (L524)
- `GovernancePanel` (L556)

**All 9 cards are hidden via the parent.** None are individually mounted elsewhere. Each card maps cleanly to a Factory Supervisor endpoint.

### 2.4 Recommendation Feed

| Element | Status |
|---|---|
| `recommendation_engine.py` | Live, 2 endpoints (`/recommendations`, `/recommendations/top`) |
| `NextRecommendedActionCard` UI | Present inside `ArchitectDashboard.jsx`, hidden |

**Net verdict:** Hidden. **Missing UI:** dedicated recommendation feed panel.

### 2.5 Notification Center

| Element | Status |
|---|---|
| `engines/factory_supervisor/notification_center.py` | Live |
| 6 backend endpoints | Live (under `/api/factory-supervisor/notifications/*`) |
| `NotificationsCard` UI | Present inside `ArchitectDashboard.jsx`, hidden |
| `OperatorInboxDrawer.jsx` | **UI-only** event bus (`inboxEvents.js`) — does NOT consume the backend NC |

**Net verdict:** Operator sees an Inbox drawer, but it stores events in browser memory. Persistence + cross-session continuity require the backend NC. **Missing UI:** wire `OperatorInboxDrawer` to consume `/api/factory-supervisor/notifications/*` when `ENABLE_NOTIFICATION_CENTER=true`.

### 2.6 Inbox

| Element | Status |
|---|---|
| `OperatorInboxDrawer.jsx` (UI) | Mounted in `CommandShell.jsx::369` |
| `DangerRibbon.jsx` (UI) | Mounted in `CommandShell.jsx::273` |
| `inboxEvents.js` (UI event-bus) | Active |
| Backend persistence | NOT WIRED (see §2.5) |

**Net verdict:** Visible at the UI layer; **half-built end-to-end**.

### 2.7 Chat capabilities

**Searched terms:** "chat", "message", "thread", "conversation", "ChatPanel", "ChatWindow", "ChatInput", "websocket", "WebSocket".

**Findings:**
- **0 chat components.**
- **0 message-thread schemas.**
- **0 WebSocket handlers for operator chat.**
- The Operator Inbox is explicitly described as "not a chat system — no inputs, no message threads, only event cards + quick action links" (PRD §4 M4 entry).
- The Copilot panel is read-only advisory.

**Net verdict:** **Not built.** No chat-style interface exists in the repo.

### 2.8 Factory Supervisor

**Backend surface area:**
- 22 engines under `engines/factory_supervisor/`
- 1 router `api/factory_supervisor.py` exposing ~40 endpoints
- 17 `FS_*` feature flags (all default OFF)

**Frontend surface area:**
- `FactorySupervisorPanel` in `OperatorParityPanels.jsx::20` (lazy-imported, no section reference) — **Hidden**
- `ArchitectDashboard.jsx` containing 9 FS-consuming cards — **Orphan parent**
- `MonitoringSuite.jsx::113` Cluster sub-tab currently mounts `ScalingPanel` instead — operator decision per FS hard veto

**Operator-visible FS endpoints:** **0**. Every FS endpoint (40+) is reachable only via raw curl.

**Net verdict:** **The richest hidden surface in the entire repo.** Operator-deliberately dormant per FS-P1.4 veto.

### 2.9 Auto Learning

| Element | Status |
|---|---|
| `auto_learning.py` engine | Live |
| 5 backend endpoints | Live (under `/api/factory-supervisor/auto-learning/*`) |
| `AutoLearningPanel` UI | Inline at `ArchitectDashboard.jsx::689`, parent unmounted |
| Flag gates | `FS_ENABLE_AUTO_LEARNING=false`, `FS_ENABLE_AUTO_LEARNING_LOOP=false`, `FS_ENABLE_AUTO_LEARNING_WORKER=false` |

**Net verdict:** **Missing from UI** + **dormant backend**. Feeds Phase 14 Trust Score per PRD §6.

### 2.10 DSR (Dynamic Symbol Registry)

| Element | Status |
|---|---|
| Schema (`engines/market_universe.py`) | Active (DSR-1) |
| Adapter (`market_universe_adapter.py`) | Active |
| Audit log (`market_universe_audit.py` — 90-day TTL collection) | Active |
| Scheduler consumes registry (`auto_data_maintainer._ingestion_symbols`) | Active (DSR-2) |
| Operator panel (`SymbolRegistryPanel.jsx`) | Mounted at `governance/symbol-registry` |
| Flag `ENABLE_DYNAMIC_MARKET_UNIVERSE=1` | Active (DSR-3) |
| Audit history panel | **Missing from UI** — no panel surfaces the `market_universe_audit` collection |

**Net verdict:** Core registry **fully visible**; audit log is **missing from UI**.

### 2.11 BI5

| Element | Status |
|---|---|
| BI5 health endpoint | Active (`/api/diag/bi5/health`) |
| BI5 health panel | Mounted (`/c/diag/bi5-health`) |
| 30-day Dukascopy dispatch (B-1) | Active in `auto_data_maintainer._update_bi5_symbol` |
| BI5 source picker (B-2) | Mounted in `MarketDataWorkbench` Manual sub-tab |
| One-shot backfill CLI (B-9) | Active at `scripts/bi5_one_shot_backfill.py` |
| One-shot backfill UI button | **Missing from UI** — CLI only |
| BI5 Certification (8 endpoints under `/api/bi5-cert/*`) | Active; **NO operator panel** |
| BI5 R2 (auto-cert Sunday sweep) | **Not yet built** |
| BI5 R3 (tick replay default) | **Not yet built** |

**Net verdict:** R1 **fully visible**; certification panel + UI backfill button are **missing from UI**. R2/R3 are **not yet built**.

### 2.12 Master Bot

| Element | Status |
|---|---|
| Dashboard | Mounted (`mutate/master-bot`) |
| Compile flow | Mounted (`mutate/master-bot-compile`) |
| Diff / Pack / Export / Deployment / Signer engines | Active (consumed by dashboard) |
| Cluster sub-tab secondary mount | **Missing from UI** — planned in `04_COMPONENT_REHOUSING_MATRIX.md` per visual approval, not yet wired |

**Net verdict:** **Visible at primary home** ✅; planned secondary mount **missing from UI**.

### 2.13 Prop Firm systems

| Subsystem | Visible? | Verdict |
|---|---|---|
| Firms admin | YES | ✅ |
| Firm Match (Phase 4) | YES | ✅ |
| Challenge Matching | **NO** | **Missing from UI** |
| Prop Firm Analysis | NO (panel) | **Missing from UI** |
| Prop Firm Intelligence | NO (panel) | **Missing from UI** |
| Prop Firm Rules Review | YES (Governance · Rules) | ✅ |
| Challenge Simulator / Manager / Portfolio (engines) | NO | **Missing from UI** |

**Net verdict:** 2 of 7 prop-firm engines have dedicated panels; the rest are engine/API-only.

---

## 3. Quantitative roll-up

| Category | Count | Notes |
|---|---|---|
| Backend engines without ANY UI panel (engine-only by design — consumed by other surfaces) | **~50** | Profiler, Ranker, IR, Spread Analyzer, Tick Validator, Gap Analyzer, Slippage Model, etc. These are pipeline primitives; consuming surface IS the UI. Not a UX gap. |
| Backend APIs **with NO operator panel** (operator must use curl) | **~17** | FS Worker Runtime/Defer Queue/Routing/Heartbeat/Lock/Events/Fleet/Remote Transport/System State/Eligibility/FAG/Scheduler-control, Calibration, RoR, Lifecycle Decay, Safe-to-Widen, Widening History, Activation Timeline, Runner Registry, Factory Runner Heartbeat, BI5 Certification, Multi-Account, Compute Probe |
| Frontend components mounted **only as power-user/raw-API** (component exists but no primary-nav section) | **2** | Challenge Matching Panel, Factory Supervisor Panel |
| Frontend components **completely orphan** (zero importers) | **10** | `ArchitectDashboard.jsx`, `Optimization.js`, `NavMoreMenu.js`, `DensityToggle.js`, `TraderModeButton.js`, 5× `phase9/*` |
| Frontend panels nested inside an unmounted parent | **5** | Advisor Stream / Recommendation Feed / Auto Learning / Notification Center / Architect-side Governance — all inside `ArchitectDashboard.jsx` |
| Feature flags that gate hidden capabilities (default OFF) | **~30** | Of 89 total flags, ~30 gate currently-dormant capabilities. The rest are tunable parameters or active. |

---

## 4. Operator visibility verdict per investigation area (one-liner)

| Area | Status |
|---|---|
| Copilot | **Visible (basic only); advanced + operational APIs hidden** |
| AI Architect | **Missing from UI (orphan parent)** |
| Advisor Stream | **Missing from UI (nested in orphan)** |
| Recommendation Feed | **Missing from UI (nested in orphan)** |
| Notification Center | **Missing from UI (backend persistence dormant; UI-only Inbox visible)** |
| Inbox | **Visible (UI-only half)** |
| Chat capabilities | **Not built** |
| Factory Supervisor | **Missing from UI (operator FS hard veto)** |
| Auto Learning | **Missing from UI + dormant backend** |
| DSR | **Visible (audit history panel missing)** |
| BI5 | **R1 visible; certification panel + UI backfill button missing; R2/R3 not built** |
| Master Bot | **Visible (planned secondary Cluster mount missing)** |
| Prop Firm | **Admin + Firm Match visible; Challenge Matching + Analysis + Intelligence panels missing** |

---

## 5. State of this document

* Read-only audit.
* Companion to `CAPABILITY_CATALOG.md` (full inventory) and `ROADMAP_RECONCILIATION.md` (roadmap-phase view).
* No code modified. No surfaces mounted. No flags flipped.

**End of report.**
