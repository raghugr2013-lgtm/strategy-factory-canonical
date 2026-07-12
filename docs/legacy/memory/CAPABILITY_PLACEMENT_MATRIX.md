# CAPABILITY_PLACEMENT_MATRIX.md

**Audit type:** Read-only placement matrix. Maps EVERY capability discovered in `CAPABILITY_CATALOG.md` (159 items) to its **final home** in the restored 1-vCPU-style operator UI.
**Sources:** `CAPABILITY_CATALOG.md`, `MISSING_FROM_UI.md`, `ROADMAP_RECONCILIATION.md`, `UI_RESTORATION_MASTERPLAN.md`, old 1-vCPU `App.js` (locked navbar LL 168–187), current `modulesRegistry.js` + `TopTabBar.jsx`.
**Status:** Read-only. No code modified. No surfaces mounted. No flags flipped.
**Generated:** 2026-06-12

---

## 0. How to read this matrix

Every capability is assigned exactly ONE of five placement verdicts:

| Verdict | Meaning |
|---|---|
| **STAYS** | Already mounted at its final home — no movement in the restoration |
| **MOVES** | Mounted today but relocates / re-stacks in the restored layout |
| **SURFACES** | Hidden/dormant today; the matrix names its future home (mounts only on operator decree) |
| **RESERVED** | Placeholder card / future engine; placement slot is pre-booked, zero-reflow when it lands |
| **RETIRES** | Orphan file with a mounted replacement; removed in the janitorial pass |

Placement notation: `Tab → sub-tab` refers to the restored top-nav roster (11 CORE + 6 MORE + Admin). `Drawer` / `Overlay` = shell-level surfaces reachable from any tab.

---

## 1. CORE — Dashboard (restored stacked workbench)

| Capability (catalog #) | Today | Final placement | Verdict |
|---|---|---|---|
| Mission Briefing (#102) | `dashboard/briefing` (sole section) | **Dashboard → top of stack** (read-only synthesis stays first) | STAYS |
| Governance Card (#104) | `governance/gov` | **Dashboard → stack pos 2** (also keeps Governance home — dual mount, identical component) | MOVES |
| Universe Governance (#105) | `governance/universe` | **Dashboard → stack pos 3** (dual mount with Governance home) | MOVES |
| Strategy Ingestion (#108) | `diag/ingest-src` | **Dashboard → stack pos 4** (dual mount with Diagnostics home) | MOVES |
| Auto Scheduler (#99) | `ai/sched` | **Dashboard → stack pos 5** (dual mount with AI Workforce home) | MOVES |
| Orchestrator (#100) | `ai/orch` | **Dashboard → stack pos 6** (dual mount with AI Workforce home) | MOVES |
| Multi-Cycle Runner (#3) | `mutate/cycle` | **Dashboard → stack pos 7** (dual mount with Mutation home) | MOVES |
| Auto Mutation Runner (#2) | `mutate/auto` | **Dashboard → stack pos 8** (dual mount with Mutation home) | MOVES |
| Strategy Dashboard (#33 catalog L33) | lazy-imported; consumed by registry | **Dashboard → stack pos 9** (bottom — the heavy KPI table) | MOVES |
| Briefing Print (#103) | print mode | **Dashboard → print affordance** (unchanged) | STAYS |

> **Note on dual mounts:** the 1-vCPU Dashboard was a *composition*, not a relocation. Components keep their canonical module homes (Governance / AI / Mutation / Diag); the Dashboard re-renders the same lazy components in a stacked scroll. Zero new code per component — only a `DashboardComposite` wrapper (see `IMPLEMENTATION_SEQUENCE.md` Step 2).

---

## 2. CORE — Execution

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Execution Broker Chips (#51) | `exec/brokers` (first section) | **Execution → top strip** (reservation chips stay first) | STAYS |
| Paper Execution (#48) | `exec/paper` | **Execution → Paper sub-tab** + CORE tab "Paper Exec" deep-links here | STAYS |
| Trade Runner (#49) | `exec/runner` | **Execution → Runner sub-tab** + CORE tab "Trade Runner" deep-links here | STAYS |
| Live Tracking (#50) | `exec/live` | **Execution → Live sub-tab** + MORE chip "Live Tracking" deep-links here | STAYS |
| NEW: Execution Overview composite | — (doesn't exist) | **Execution → default landing** (condensed KPI strip: broker chips + paper KPIs + runner status + live summary) | SURFACES (new thin composite per masterplan §1.2) |
| Execution Engine / Manager / Simulator (#52) | engine-only | Consumed by Paper/Runner — **no panel** (by design) | STAYS (engine) |
| Slippage Model (#54) | engine-only | Consumed — no panel | STAYS (engine) |
| Execution Realism Defaults (#53) | `governance/admin → Realism` | **Admin → Realism sub-tab** (unchanged) | STAYS |
| Runner Registry + Router + Token Rotation + Migration (#56) | API only, hidden | **Execution → Runners sub-tab** (`exec/runners`) — mounts when multi-account/remote runners activate | SURFACES (future) |
| Factory Runner Heartbeat (#57) | API only, hidden | Folded into the future `exec/runners` panel (heartbeat column) | SURFACES (future) |
| Multi-Account Envelope (#55) | dormant flag | Backend-only; surfaces as rows inside `exec/runners` when `RUNNER_MULTI_ACCOUNT_ENABLED` | SURFACES (future) |
| cTrader Demo / Live wiring | not built | Activates reserved chips inside `exec/brokers` — no new tab | RESERVED |
| Windows VPS | not built | Activates reserved chip — no new tab | RESERVED |
| Broker Telemetry | not built | Activates reserved chip; optional `exec/telemetry` sub-tab if depth needed | RESERVED |
| `phase9/ExecutionDashboard.js` (#156) | orphan (74 LOC) | Superseded by `exec/*` | RETIRES |
| `phase9/LiveExecutionCard.js` (#157) | orphan | Superseded by `LiveTrackingPanel` | RETIRES |

---

## 3. CORE — Auto Factory (+ MORE — Auto Factory Legacy)

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Auto Factory Phase 55 (#1) | `mutate/factory-55` | **Auto Factory tab → default** (1:1 with old UI) | STAYS |
| Auto Factory legacy (#1) | `mutate/factory` | **MORE → Auto Factory (Legacy)** (unchanged) | STAYS |
| Auto Mutation Runner (#2) | `mutate/auto` | Sub-tab drill-down (+ Dashboard stack dual mount) | STAYS |
| Multi-Cycle Runner (#3) | `mutate/cycle` | Sub-tab drill-down (+ Dashboard stack dual mount) | STAYS |
| Master Bot Dashboard (#73) | `mutate/master-bot` | Sub-tab drill-down (unchanged) | STAYS |
| Master Bot Compile (#73) | `mutate/master-bot-compile` | Sub-tab drill-down (unchanged) | STAYS |
| Master Bot Ranker / Diff / Pack / Export / Deploy / Signer (#73–74) | engines consumed by dashboard | No panel (by design) | STAYS (engine) |
| Master Bot secondary Cluster mount | planned, not wired | **Monitoring → Cluster sub-tab** (stacked under ScalingPanel) — P3 backlog | SURFACES (P3) |
| Strategy Mutation / Evolution / Decision / Replacement / Survivor Registry (#8, #13–16) | engines | Pipeline primitives — no panel | STAYS (engine) |
| Strategy IR ×6 (#17) | engines | No panel (by design) | STAYS (engine) |
| Code Generator / Compile Engine (#20) | engines | Consumed by cBot + Master Bot | STAYS (engine) |
| `phase9/AutoFactoryCard.js` (#155) | orphan | Superseded by AutoFactoryPhase55 | RETIRES |

---

## 4. CORE — Monitoring

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Monitoring Suite — Runtime (#75) | `diag/monitoring` Runtime sub-tab | **Monitoring → default landing** (old `Monitoring.js` content) | STAYS |
| Soak Diagnostics (#76) | Soak sub-tab | Sub-tab drill-down | STAYS |
| CPU Pool State (#77) | Compute sub-tab | Sub-tab drill-down | STAYS |
| Scaling Engine (#78) | Cluster sub-tab (`ScalingPanel`) | Sub-tab drill-down | STAYS |
| Factory Supervisor Panel (#114) | hidden (lazy-imported, no section) | **Monitoring → Cluster sub-tab, stacked BELOW ScalingPanel** — only when operator authorises `ENABLE_FACTORY_SUPERVISOR=true` | SURFACES (P2, veto-gated) |
| Alert Engine (#81) | engine | Feeds DangerRibbon / drawers — no panel | STAYS (engine) |
| Adaptive Concurrency / Pool Sizer / Cooldown (#79) | dormant flags | Backend-only; status visible via Cluster sub-tab once FS surfaces | SURFACES (with FS) |
| Admission Controller / Queue Pressure (#80) | dormant flags | Same — Cluster sub-tab telemetry rows | SURFACES (with FS) |
| Compute Probe (#83) | dormant API | Same — Compute sub-tab extra card (only when `COMPUTE_AWARE_ORCHESTRATION` flips) | SURFACES (future) |

---

## 5. CORE — Paper Exec · Trade Runner · Auto Select (1:1 tabs)

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Paper Execution (#48) | `exec/paper` | **Paper Exec tab** (deep-link, 1:1 old UI) | STAYS |
| Trade Runner (#49) | `exec/runner` | **Trade Runner tab** (deep-link, 1:1) | STAYS |
| Auto Selection (#5) | `mutate/auto-select` | **Auto Select tab** (deep-link, 1:1) | STAYS |
| BI5 R3 tick-replay default | not built | Flips default `source=bi5` toggle inside PaperExecution + TradeRunner — no new surface | RESERVED |

---

## 6. CORE — Portfolio

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Portfolio Builder (#42) | `portfolio/builder` | **Portfolio tab → default landing** | STAYS |
| Portfolio Panel (#43) | `portfolio/panel` | Sub-tab drill-down (old MORE→Portfolio behaviour) | STAYS |
| Portfolio Intelligence (#44) | `portfolio/intel` | Sub-tab drill-down | STAYS |
| Phase 14 Dual Scorecard reservation (#47/#111) | `portfolio/scorecards-reservations` | **Bottom of Portfolio tab, collapsed** ("Phase 14 Reservations" accordion per masterplan §5) | MOVES |
| Phase 14 Automated Valuation Engine | not built | Populates the dual scorecard in-place — no new tab | RESERVED |
| Anti-Correlation Filter (#44 flag) | dormant | Activates inside Portfolio Intelligence — no new surface | SURFACES (flag-gated) |
| Multi-Asset Portfolio (#45) | engine | Consumed by Builder — no panel | STAYS (engine) |
| Optimization × Portfolio Bridge (#46) | engine | No panel | STAYS (engine) |
| `phase9/PortfolioBuilderCard.js` (#158) | orphan | Superseded | RETIRES |

---

## 7. CORE — Explorer (+ MORE — Library)

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Strategy Explorer (#12 via UI) | `explorer/explorer` | **Explorer tab → default landing** (browse) | STAYS |
| Saved Strategies | `explorer/saved` | **MORE → Library (N)** deep-link (count badge stays) | STAYS |
| Strategy Comparison (GAP-P1-8) | `explorer/compare` | Sub-tab drill-down | STAYS |
| Strategy Score reservation (#109) | `explorer/score-rubric` | **Bottom of Explorer, collapsed** ("Phase 13/14/15 Reservations" accordion) | MOVES |
| Phase 13 Dossier reservation (#110) | `explorer/passport-reservations` | Same collapsed accordion | MOVES |
| Phase 15 Marketplace reservation (#112) | `explorer/marketplace-reservations` | Same collapsed accordion | MOVES |
| Phase 13 Dossier Engine | not built | Populates the 12 reservation slots in-place | RESERVED |
| Phase 15 Marketplace site | separate codebase | Reservation card is the only ASF touchpoint | RESERVED |
| Strategy Memory / Library / Lifecycle / Profiler / Ranking / Refinement (#6–12) | engines | Consumed by Explorer + pipeline — no panels | STAYS (engine) |

---

## 8. CORE — Market Data

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Data Upload — Manual (#23 UI) | `diag/market-data` Manual sub-tab | **Market Data tab → default landing** (upload control first, per old UI) | STAYS |
| Data Maintenance — Automated (#37) | Automated sub-tab | Sub-tab drill-down | STAYS |
| Data Backup — Archive (#36) | Archive sub-tab | Sub-tab drill-down | STAYS |
| BI5 Health Panel (#25) | `diag/bi5-health` (separate section) | **Keeps its diag home** + a 1-line "data readiness" strip ABOVE Market Data sub-tabs (masterplan §1.9) | MOVES (strip added) |
| BI5 source picker (B-2) | Manual sub-tab | Unchanged | STAYS |
| One-shot BI5 backfill (#31) | CLI only | **Market Data → Manual sub-tab "Backfill Now" button** (UX nice-to-have, P2) | SURFACES (P2) |
| BI5 Certification (#28) | API only (8 endpoints) | **Diagnostics → new `bi5-cert` sub-section** (mirrors bi5-health) — lands with BI5 R2 | SURFACES (with R2) |
| BI5 R2 auto-cert sweep | not built (P0) | New `diag/bi5-cert` panel + extra column on BI5 Health table | RESERVED |
| BI5 Maturity / Realism (#26–27) | engines | Consumed by certification — no panel | STAYS (engine) |
| Tick Aggregator / Archive / Validator, Dukascopy Downloader, Gap Analyzer, Incremental Updater, Market Calendar, Spread Analyzer (#32–39) | engines | Pipeline primitives — no panels | STAYS (engine) |
| Regime Classifier / Performance, Signal Quality (#40–41) | engines | Consumed by validation — no panels | STAYS (engine) |

---

## 9. CORE — Admin (admin role) + Governance module

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Admin Users (#107) | `governance/admin` Users sub-tab | **Admin tab → default landing** (matches old primary panel) | STAYS |
| Flag Governance (#91) | Flags sub-tab | Sub-tab drill-down | STAYS |
| Execution Realism (#53) | Realism sub-tab | Sub-tab drill-down | STAYS |
| Phase 12 Tuning (#106) | Tuning sub-tab | Sub-tab drill-down | STAYS |
| Readiness Panel (#84) | `governance/readiness` | Keeps Governance home + 1-line "Readiness: GREEN · OPEN" link at top of Admin tab | STAYS (link added) |
| DSR Symbol Registry (#22) | `governance/symbol-registry` | Unchanged | STAYS |
| DSR Audit Log (§2.10 missing) | Mongo only | **Symbol Registry → "Audit History" sub-tab** (purely additive, anytime) | SURFACES (P2) |
| Rules Review (#66–67) | `governance/rules` | Unchanged (single source of truth) | STAYS |
| Env Priority (#92) | `governance/env` | Unchanged | STAYS |
| Widening Proposal (#90) | Flags sub-tab | Unchanged | STAYS |
| Safe-to-Widen / Widening History (#88–89) | API only | **Flags sub-tab → "History" expander** consuming `/api/latent/widening-history` | SURFACES (P2) |
| Activation Governance / Timeline (#94) | API only | **Governance → new `activation` section** (read-only timeline) | SURFACES (P2) |
| Calibration / Risk-of-Ruin / Lifecycle Decay (#85–87) | dormant APIs | Backend-only until activation; verdicts then surface inside Explorer score columns (no dedicated panels) | SURFACES (flag-gated) |
| Audit Log Writer (#93) | engine | Cross-engine — no panel | STAYS (engine) |
| Auth + AuthGate (#107) | wraps shell | Unchanged | STAYS |

---

## 10. MORE — Workspace · Prop Firms · Optimization

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| Workspace Composite (P1.1) | `lab/workspace` | **MORE → Workspace** (1:1 restored single-page lab) | STAYS |
| Strategy Panel / Analysis / Backtest / cBot / Optimization / Validation (#4, #18–19, #21, #58) | `lab/*` sections | Sub-tab drill-downs (also composed inside Workspace) | STAYS |
| Prop Firms Admin (#62) | `propfirm/admin` | **MORE → Prop Firms → default landing** | STAYS |
| Firm Match (#63) | `propfirm/match` | Sub-tab drill-down | STAYS |
| **Challenge Matching (#70)** | hidden (lazy-imported, no section) | **Prop Firms → new `challenge` sub-tab** — P1, ~30 min, first restoration mount | SURFACES (P1) |
| Prop Firm Intelligence / Analysis (#64–65) | API only | Consumed by Firm Match; no dedicated panels unless operator asks | STAYS (engine) |
| Challenge Simulator / Manager / Portfolio (#69, #71–72) | engines | Consumed by Challenge Matching — no panels | STAYS (engine) |
| Prop Firm Config Engine (#68) | engine | Consumed by Admin — no panel | STAYS (engine) |
| OptimizationPanel (96 LOC) | `lab/optim` | **MORE → Optimization** deep-link (unchanged) | STAYS |
| `Optimization.js` 506-LOC legacy (#150) | orphan | Visual parity check, then retire | RETIRES |
| R5 Shadow Comparator (#59) | engine | No panel | STAYS (engine) |
| HTF Parity (#60) | API, gate dormant | Verdict rows inside Parity Certification card | STAYS |
| Parity Certification (#61) | `diag/parity` | Unchanged | STAYS |
| cBot autofix / parity engines (#58) | engines | Consumed by cBot panel | STAYS (engine) |

---

## 11. AI Workforce module + Factory Supervisor stack

| Capability | Today | Final placement | Verdict |
|---|---|---|---|
| LLM Call River (#101) | `ai/river` | Unchanged (not in old UI; valuable new surface) | STAYS |
| Orchestrator (#100) | `ai/orch` | Unchanged (+ Dashboard dual mount) | STAYS |
| Auto Scheduler (#99) | `ai/sched` | Unchanged (+ Dashboard dual mount) | STAYS |
| **Architect Dashboard (#122)** | orphan (940 LOC) | **AI Workforce → new `architect` section** (lift the 9 cards) — only on FS activation | SURFACES (P2, veto-gated) |
| Advisor Stream / NextRecommendedAction (#122) | nested in orphan | Inside `ai/architect` | SURFACES (with Architect) |
| Recommendation Feed (#123) | nested in orphan | Dedicated sub-card inside `ai/architect` | SURFACES (with Architect) |
| Auto Learning (#132) | nested in orphan, flags OFF | **AI Workforce → new `learning` section** (lifted standalone) — when `FS_ENABLE_AUTO_LEARNING=true` | SURFACES (P3) |
| Notification Center backend (#124) | dormant API ×6 | Wire `OperatorInboxDrawer` to `/api/factory-supervisor/notifications/*` when `ENABLE_NOTIFICATION_CENTER=true` (UI-only `inboxEvents.js` is interim) | SURFACES (flag-gated) |
| Copilot basic (#126) | drawer, mounted | Unchanged | STAYS |
| Copilot advanced (#127) | dormant API ×4 | **"v2" toggle inside the existing Copilot drawer** when `FS_ENABLE_COPILOT_ADVANCED=true` | SURFACES (flag-gated) |
| FS Worker / Defer Queue / Routing / Heartbeat / Lock / Fleet / Remote / SystemState / Eligibility / FAG / Scheduler / Telemetry (#115–121, #130–134) | dormant APIs | Telemetry rows inside `FactorySupervisorPanel` (Monitoring Cluster) + `ai/architect` cards — never standalone tabs | SURFACES (with FS) |

---

## 12. Shell overlays (cross-tab layer — all STAY)

| Capability | Placement | Verdict |
|---|---|---|
| TopTabBar 11 CORE + 6 MORE (#135) | Top nav — locked roster | STAYS |
| LifecycleRail 10-step (#136) | Strip above content, every tab | STAYS |
| StatusRail 6 chips (#137) | Bottom of rail strip | STAYS |
| DangerRibbon (#139) / EmergencyBanner (#140) | Top of shell | STAYS |
| Operator Inbox Drawer (#125) / NotificationDrawer (#128) / AsfNotificationDrawer (#129) / CopilotPanel (#126) | Right-slide drawers | STAYS |
| CommandPalette ⌘K (#141) / CommandBar (#142) / ShortcutsOverlay (#143) | Modals / top bar | STAYS |
| LeftRail (#138) | Collapsed (legacy) — superseded by TopTabBar | STAYS (collapsed) |
| Lineage Strip / Mobile Surfaces / ModuleSurface / AriaLive / ui-asf kit / shadcn kit (#144–149) | Infrastructure | STAYS |
| Deployment rail label (#113) | LifecycleRail stage 10 → routes to Monitoring (intentional, documented) | STAYS (label) |

---

## 13. Orphan retirement roster (janitorial pass — needs authorization)

| File | LOC | Replacement | Action |
|---|---|---|---|
| `components/Optimization.js` | 506 | `OptimizationPanel.js` @ `lab/optim` | RETIRE (after visual parity check) |
| `components/ArchitectDashboard.jsx` | 940 | 9 cards rehoused to `ai/architect` + `ai/learning` | REHOUSE children → then RETIRE shell |
| `components/NavMoreMenu.js` | — | `TopTabBar.jsx` MORE menu | RETIRE |
| `components/DensityToggle.js` | — | `useDensity.js` hook | RETIRE |
| `components/TraderModeButton.js` | — | posture model | RETIRE |
| `components/phase9/AutoFactoryCard.js` | — | `AutoFactoryPhase55.js` | RETIRE |
| `components/phase9/ExecutionDashboard.js` | 74 | `exec/*` sections | RETIRE |
| `components/phase9/LiveExecutionCard.js` | — | `LiveTrackingPanel.js` | RETIRE |
| `components/phase9/PortfolioBuilderCard.js` | — | `PortfolioBuilder.js` | RETIRE |
| `components/phase9/ui.js` | — | `ui/*` + `ui-asf/*` | RETIRE |

---

## 14. Roll-up

| Verdict | Count | Notes |
|---|---|---|
| STAYS | **~95** | Engines-by-design + already-correctly-mounted surfaces + all shell overlays |
| MOVES | **13** | 8 Dashboard-stack dual mounts + 4 reservation cards collapsing + BI5 strip |
| SURFACES | **~25** | 1 × P1 (Challenge Matching) · ~8 × P2 (FS mount, audit log, backfill button, history expanders, activation timeline, bi5-cert) · rest flag-gated on operator decree |
| RESERVED | **9** | Phase 13/14/15 engines, BI5 R2/R3, cTrader ×2, VPS, telemetry |
| RETIRES | **10** | Orphan files; ~2 h janitorial |

**Zero capabilities lose a home. Zero hidden capabilities surface without an explicit operator gate.**

---

## 15. State of this document

* Read-only placement plan — companion to `UI_RESTORATION_MASTERPLAN.md`, `NAVIGATION_RECONSTRUCTION.md`, `OPERATOR_WORKFLOW_ALIGNMENT.md`, `IMPLEMENTATION_SEQUENCE.md`.
* No code modified. No surfaces mounted. No flags flipped.

**End of report.**
