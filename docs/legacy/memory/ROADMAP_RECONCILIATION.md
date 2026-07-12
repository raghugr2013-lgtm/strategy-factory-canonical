# ROADMAP_RECONCILIATION.md

**Audit type:** Reconciles the full capability discovery (`CAPABILITY_CATALOG.md` + `MISSING_FROM_UI.md`) against the roadmap (`PRD.md` §4–§6, `09_OPERATOR_LIFECYCLE.md`, `10_FUTURE_PHASES_*.md`) to answer ONE question per capability:
> *Is this capability where the roadmap expects it to be?*

**Status:** Read-only. No code modified.
**Generated:** 2026-06-12

---

## 1. Reconciliation key

| Verdict | Meaning |
|---|---|
| ✅ **On roadmap & delivered** | Roadmap says "shipped"; code agrees |
| 🟡 **On roadmap & in-progress** | Roadmap calls for it; partially shipped |
| 🟠 **On roadmap & dormant** | Roadmap reserves it; backend exists; UI hidden / flag-gated by design |
| 🔴 **On roadmap & not built** | Roadmap calls for it; no code |
| ⚪ **Off roadmap (engine-only)** | Engine exists; intentionally not surfaced |
| 🟣 **Off roadmap (orphan / dead)** | Code exists with no roadmap intent and no consumer |
| 🆕 **Discovered, no roadmap mention** | Code exists; roadmap doesn't reference it |

---

## 2. Per-area roadmap reconciliation

### 2.1 Pipeline / strategy lifecycle

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Auto Factory (Generate · Mutate · Validate · Select) | PRD §0 + roadmap Phase 55 | Active (4 stages mounted) | ✅ |
| Strategy Library (fingerprint + lifecycle) | PRD §0 + `MIGRATION_COMPATIBILITY_AUDIT.md` | Active | ✅ |
| Strategy Profiler / Ranking / Refinement / Memory / IR / Survivor Registry / Replacement / Decision / Evolution / Code Generator | Pipeline primitives — consumed by Auto Factory + post-import pipeline | Active engines | ⚪ (engine-only by design — consumed via Auto Factory + Explorer + Post-Import Stages 1–3) |

### 2.2 Market data + DSR

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| DSR-1 schema | PRD §4 line 62 | Active | ✅ |
| DSR-2 scheduler consumption | PRD §4 line 62 | Active | ✅ |
| DSR-3 (`ENABLE_DYNAMIC_MARKET_UNIVERSE=1`) | PRD §4 line 62 | Active | ✅ |
| DSR — Audit log (`market_universe_audit` 90-d TTL) | Implicit (operator audit) | Collection live; **no UI panel** | 🟠 — operator must use Mongo; minor gap |
| BID ingestion + scheduler | PRD §0 (data engine) | Active | ✅ |
| BI5 R1 — B-1 (30-d Dukascopy dispatch) | PRD §4 line 63 | Active | ✅ |
| BI5 R1 — B-2 (UI source picker audit) | PRD §4 line 63 | Active | ✅ |
| BI5 R1 — B-9 (one-shot backfill CLI) | PRD §4 line 63 | Active (CLI) | ✅ |
| BI5 R1 — per-symbol health panel | PRD §4 line 63 | Active | ✅ |
| BI5 R1 — UI "Backfill Now" button | Not on roadmap | None | 🆕 (UX nice-to-have; not blocking) |
| BI5 R2 (B-4 / B-5 / B-8 — auto-cert sweep + ranker weights + lifecycle) | PRD §6 P0 line 111 | Not built | 🔴 |
| BI5 R3 (B-3 / B-6 / B-7 — tick replay default) | PRD §6 P0 line 112 | Not built | 🔴 |
| BI5 Certification (data + strategy) | PRD §4 BI5 R1 entries | Engine + 8 endpoints live; **no operator panel** | 🟠 — visible only via API |
| Tick aggregator / archive / validator / spread analyzer / gap analyzer / Dukascopy downloader / market calendar | Pipeline primitives | Active engines | ⚪ |
| Regime Classifier / Performance / Signal Quality | Pipeline primitives | Active | ⚪ |

### 2.3 Auto Factory pipeline visibility

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Generate stage UI | `01_TAB_ROSTER.md` CORE-3 | Mounted (`lab/panel` + `lab/workspace`) | ✅ |
| Mutate stage UI (5 sub-flows) | CORE-3 | Mounted (`mutate/{auto,cycle,factory,factory-55,auto-select}`) | ✅ |
| Validate stage UI | CORE-3 | Mounted (`lab/validate`) | ✅ |
| Select stage UI | CORE-3 | Mounted (`mutate/auto-select`) | ✅ |
| Workspace Composite (legacy 1-vCPU MORE-1 surface) | `POST_HYDRATION_UI_RECOVERY.md` P1.1 | Mounted (`lab/workspace`) | ✅ |

### 2.4 Explorer + Library

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Explorer surface | `01_TAB_ROSTER.md` CORE-8 | Mounted | ✅ |
| Saved Strategies | `01_TAB_ROSTER.md` MORE | Mounted | ✅ |
| Library count badge | `POST_HYDRATION_UI_RECOVERY.md` P1.2 | Mounted | ✅ |
| Strategy Comparison | `01_TAB_ROSTER.md` GAP-P1-8 | Mounted | ✅ |
| Strategy Score Reservation (M3) | `01_TAB_ROSTER.md` M3 entry | Mounted (placeholder) | 🟠 (placeholder by design) |
| Phase 13 Strategy Dossier reservation | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 (placeholder) |
| Phase 15 Marketplace reservation | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 (placeholder) |
| Strategy Dossier Engine (Phase 13) | PRD §6 P2 line 113 | Not built | 🔴 |
| Strategy Ingestion surface | `01_TAB_ROSTER.md` (diag/ingest-src) | Mounted | ✅ |

### 2.5 Portfolio + Phase 14

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Portfolio Builder | CORE-7 | Mounted | ✅ |
| Portfolio Panel | CORE-7 | Mounted | ✅ |
| Portfolio Intelligence | CORE-7 | Mounted | ✅ |
| Anti-Correlation Filter | Implicit | Engine live; `ENABLE_ANTI_CORRELATION_FILTER=false` | 🟠 (dormant) |
| Multi-Asset Portfolio | Implicit (consumed by builder) | Active engine | ⚪ |
| Phase 14 Dual Scorecard reservation | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 (placeholder) |
| Phase 14 Automated Valuation Engine | PRD §6 P2 line 114 | Not built | 🔴 |

### 2.6 Execution + brokers

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Paper Execution | CORE-5 | Mounted (`exec/paper`) | ✅ |
| Trade Runner | CORE-6 | Mounted (`exec/runner`) | ✅ |
| Live Tracking | CORE | Mounted (`exec/live`) | ✅ |
| ExecutionBrokerChips (Track A + B + reserved cTrader Demo / Live / Windows VPS / Broker Telemetry) | M2 entry (PRD §4 line 58) | Mounted (reservation chips) | 🟠 (placeholder) |
| cTrader Live / Demo wiring | Reserved | Not built | 🔴 |
| Windows VPS | Reserved | Not built | 🔴 |
| Broker Telemetry | Reserved | Not built | 🔴 |
| Execution Engine / Manager / Simulator | Pipeline primitives | Active | ⚪ |
| Execution Realism Defaults | PRD §4 (R-series) | Mounted (`governance/admin` → Realism) | ✅ |
| Slippage Model | Pipeline primitive | Active engine | ⚪ |
| Multi-Account Envelope | Reserved | Active engine; `RUNNER_MULTI_ACCOUNT_ENABLED` dormant | 🟠 |
| Runner Registry / Router / Token Rotation / Account Migration | Not on roadmap; backend support | Active engines + API; **no UI** | 🆕 / 🟠 (engine + API only) |
| Factory Runner Heartbeat | Not on roadmap | Active engine + API; **no UI** | 🟠 |

### 2.7 Master Bot

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Master Bot Dashboard | R1 entry (PRD §4 — folded into Mutation Engine) | Mounted | ✅ |
| Master Bot Compile | R1 entry | Mounted | ✅ |
| Master Bot Diff / Pack / Export / Deployment / Signer / Definition / Ranker / Composer / Compiler / Runtime | Consumed by dashboard | Active engines | ⚪ |
| Secondary mount under Monitoring · Cluster | `04_COMPONENT_REHOUSING_MATRIX.md` row 19 | Not yet wired | 🟡 (P3 backlog) |

### 2.8 Prop Firm

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Prop Firms Admin | MORE-3 | Mounted | ✅ |
| Firm Match (Phase 4) | MORE-3 | Mounted | ✅ |
| Challenge Matching Panel | `01_TAB_ROSTER.md` plans `propfirm/challenge` | Component exists; **NOT mounted** | 🟠 (P1 backlog) |
| Prop Firm Analysis / Intelligence / Rules Review | Backend support | API live; rules surfaced; analysis/intelligence panels not built | 🟠 |
| Challenge Simulator / Manager / Portfolio | Not on roadmap | Active engines; **no UI** | 🆕 / 🟠 |

### 2.9 Monitoring + scaling + diagnostics

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Monitoring Suite (4-pane) | CORE-4 | Mounted (`diag/monitoring`) | ✅ |
| Cluster sub-tab — `ScalingPanel` | Today's wiring | Mounted | ✅ |
| Cluster sub-tab — `FactorySupervisorPanel` | `04_COMPONENT_REHOUSING_MATRIX.md` recommendation | Component exists; not mounted in Cluster | 🟠 (operator FS veto) |
| Soak Diagnostics | CORE-4 | Mounted | ✅ |
| CPU Pool State | CORE-4 | Mounted | ✅ |
| Adaptive Concurrency / Pool Sizer / Cooldown | Not on roadmap; backend support | Active engines; flag-gated | 🟠 (dormant) |
| Admission Controller / Queue Pressure | Not on roadmap; backend support | Active engines; flag-gated | 🟠 (dormant) |
| Alert Engine | Pipeline primitive | Active | ⚪ |
| Ingestion Health Aggregate | CORE-4 | Mounted | ✅ |
| Compute Probe | Backend support | Active engine + API; **no UI** | 🟠 (flag-dormant) |
| Deployment Readiness | CORE-4 + `governance/readiness` | Mounted | ✅ |
| Calibration Framework | Roadmap latent | Active engine + API; **no UI** | 🟠 (dormant) |
| Risk of Ruin | Roadmap latent | Active engine + API; weight=0.0 | 🟠 (dormant) |
| Lifecycle Decay | Roadmap latent | Active engine + API | 🟠 (dormant) |
| Safe-to-Widen / Widening History | Operator-flag flow | Active engines; widening proposals mounted; history not | 🟠 |
| Widening Proposal | `governance/admin` → Flags | Mounted | ✅ |
| Flag Governance | `governance/admin` → Flags | Mounted | ✅ |
| Env Priority | `governance/env` | Mounted | ✅ |
| Audit Log Writer | Cross-engine | Active | ⚪ |
| Activation Governance / Activation Timeline | Roadmap continuity | Active engines + API; **no UI** | 🟠 |
| Adaptive Rotation / Cadence / Replay Priority / Event Continuation | Roadmap latent | Active engines; flag-gated | 🟠 (dormant) |

### 2.10 AI Workforce

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| LLM Workforce Live River | `01_TAB_ROSTER.md` ai/river | Mounted | ✅ |
| Orchestrator | `01_TAB_ROSTER.md` ai/orch | Mounted | ✅ |
| Auto-Scheduler | `01_TAB_ROSTER.md` ai/sched | Mounted | ✅ |

### 2.11 Governance + auth

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Governance Card | CORE | Mounted | ✅ |
| Universe Governance | CORE | Mounted | ✅ |
| Symbol Registry (DSR) | DSR-1 | Mounted | ✅ |
| Rules Review | CORE | Mounted | ✅ |
| Env Priority | CORE | Mounted | ✅ |
| Readiness | CORE | Mounted | ✅ |
| Governance Admin Suite (Users · Flags · Realism · Tuning) | R1 entry | Mounted | ✅ |
| JWT auth + admin seed | PRD §2 | Active | ✅ |

### 2.12 Phase 13 / 14 / 15 reservations

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Strategy Score 4-metric scaffold | M3 entry | Reservation card mounted | 🟠 |
| Phase 13 Dossier scaffold | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 |
| Phase 14 Dual Scorecard scaffold | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 |
| Phase 15 Marketplace scaffold | `10_FUTURE_PHASES_*.md` | Reservation card mounted | 🟠 |
| Phase 13 engine | PRD §6 P2 | Not built | 🔴 |
| Phase 14 engine | PRD §6 P2 | Not built | 🔴 |
| Phase 15 marketplace site | Separate codebase | Not built (separate site) | 🔴 (out of scope) |
| Deployment label (LifecycleRail stage 10) | LifecycleRail spec | Mounted (label only) | 🟠 (intentional) |

### 2.13 Factory Supervisor stack

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| FS master `FactorySupervisorPanel` | `04_COMPONENT_REHOUSING_MATRIX.md` (Cluster recommendation) | Component exists, lazy-imported; not mounted | 🟠 (FS hard veto) |
| FS Worker Runtime / Scheduler / Defer Queue / Routing Policy / Submission Dispatcher | FS-P1.1–P1.3 | Engines + APIs live; flag-gated | 🟠 (dormant) |
| FS Heartbeat / Lock / Events / Fleet Registry / Remote Transport / System State View | FS-P1.x | Engines + APIs live; flag-gated | 🟠 (dormant) |
| **AI Architect (Architect Dashboard)** | FS-P1.4 | `ArchitectDashboard.jsx` orphan; backend live | 🟠 (parent unmounted; FS veto) |
| **Advisor Stream (NextRecommendedActionCard)** | FS-P1.4 | Nested in `ArchitectDashboard.jsx` | 🟠 |
| **Recommendation Engine** | FS-P1.4 | Backend + 2 endpoints live; UI nested | 🟠 |
| **Notification Center (backend)** | FS-P1.4 + M4 | Backend live; UI not wired (UI-only `inboxEvents.js` mounted instead) | 🟡 (half-built) |
| **Copilot (operational)** | FS-P1.4 | Backend live (4 endpoints); UI = `CopilotPanel.jsx` reads orchestrator instead of FS Copilot APIs | 🟡 (UI does not consume FS endpoints) |
| **Copilot (advanced)** | FS-P1.4 | Backend live (4 endpoints); UI not built | 🟠 |
| **Auto Learning** | FS-P1.4 | Backend live (5 endpoints); UI nested in orphan | 🟠 |
| **Eligibility Engine** | FS-P1.4 | Backend live (2 endpoints); no UI | 🟠 |
| **FAG Proposals** | FS-P1.4 | Backend live (8 endpoints); no UI | 🟠 |
| **FS Telemetry Worker** | FS-P1.4 | Backend live; flag-gated | 🟠 |
| **FS Scheduler control** | FS-P1.4 | Backend live (3 endpoints); no UI | 🟠 |

### 2.14 Operator Inbox / DangerRibbon / Notification Drawer / Copilot Panel (M4 + M5)

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Operator Inbox Drawer | M4 entry | Mounted (UI-only event bus) | ✅ (UI half) |
| Danger Ribbon | M4 entry | Mounted | ✅ |
| Notification Drawer (Phase R5 live overlay) | R5 milestone | Mounted | ✅ |
| AsfNotificationDrawer (Phase U-3 read-only digest) | Phase U-3 | Mounted | ✅ |
| Copilot Panel (basic) | Phase R5 | Mounted | ✅ |
| Command Palette / Shortcuts Overlay / Command Bar / Lineage Strip / Mobile Surfaces | Pre-RC1 shell | Mounted | ✅ |

### 2.15 Chat / messaging

| Capability | Roadmap reference | Code status | Verdict |
|---|---|---|---|
| Chat UI / WebSocket / thread schema | **NONE on roadmap** | **None in code** | 🆕 not present and not requested — operator brief explicitly excludes chat ("not a chat system") |

---

## 3. Status mapping against the 14 requested surfaces

| Surface | Status mapping (Completed · Ready-but-dormant · Placeholder · Not-yet-built) | Notes |
|---|---|---|
| **DSR** | Completed | DSR-1/2/3 active; audit-history UI is the only gap (engine live) |
| **BI5** | Completed (R1) · Not yet built (R2, R3) | R1 full E2E; certification panel hidden |
| **Auto Factory** | Completed | 4 stages mounted, readiness-gated |
| **Explorer** | Completed | 3 working sections + 3 placeholder cards |
| **Portfolio Builder** | Completed | 3 working sections + Phase 14 placeholder |
| **Master Bot** | Completed | Dashboard + Compile mounted; secondary Cluster mount on backlog |
| **Trade Runner** | Completed | + ExecutionBrokerChips placeholder for cTrader/VPS |
| **Monitoring** | Completed | 4-pane suite mounted; Cluster currently mounts ScalingPanel (FS veto) |
| **Deployment** | Placeholder | LifecycleRail label only; function distributed |
| **Strategy Dossier** | Not yet built | Phase 13 engine pending; reservation card mounted |
| **Auto Valuation** | Not yet built | Phase 14 engine pending; dual scorecard reservation mounted |
| **Marketplace** | Not yet built | Phase 15 separate codebase; reservation card mounted |
| **Factory Supervisor** | Ready but dormant | 22 engines + 40 endpoints; UI hidden by FS veto |
| **Auto Learning** | Ready but dormant | Engine + 5 endpoints live; UI nested in orphan; 3 flags OFF |

---

## 4. Orphans / dead code against roadmap

| Orphan | On roadmap? | Verdict |
|---|---|---|
| `Optimization.js` | No (replaced by `OptimizationPanel.js`) | 🟣 — **Retire** |
| `phase9/AutoFactoryCard.js` | No (replaced by `AutoFactoryPhase55.js`) | 🟣 — **Retire** |
| `phase9/ExecutionDashboard.js` | No (replaced by `exec/*`) | 🟣 — **Retire** |
| `phase9/LiveExecutionCard.js` | No (replaced by `LiveTrackingPanel.js`) | 🟣 — **Retire** |
| `phase9/PortfolioBuilderCard.js` | No (replaced by `PortfolioBuilder.js`) | 🟣 — **Retire** |
| `phase9/ui.js` | No (replaced by `components/ui/*` + `components/ui-asf/*`) | 🟣 — **Retire** |
| `NavMoreMenu.js` | No (replaced by `TopTabBar` MORE chips) | 🟣 — **Retire** |
| `DensityToggle.js` | No (absorbed by `useDensity.js` hook) | 🟣 — **Retire** |
| `TraderModeButton.js` | No (absorbed by posture model) | 🟣 — **Retire** |
| `ArchitectDashboard.jsx` | YES — FS-P1.4 roadmap calls for an architect surface | 🟠 — **Rehouse children, then retire shell.** The shell itself is orphan; the 9 cards inside are the recoverable assets |

---

## 5. Discovered-but-no-roadmap-mention items

| Item | Why it exists | Verdict |
|---|---|---|
| Runner Registry / Router / Token Rotation / Account Migration (+ 6 `RUNNER_*` flags) | Multi-account / multi-runner support for future deployment | 🆕 backend ready; UI not on roadmap yet |
| Factory Runner Heartbeat | Per-runner heartbeat | 🆕 backend ready; no UI |
| 17 latent-feature-flag-gated capabilities (Risk of Ruin · Lifecycle Decay · Aging Penalty · Calibration · Rotational · Cadence · Anti-Correlation · Event Continuation · Replay Priority · Admission Control · Process Pool × 2 · Compute-Aware · Adaptive Pool Sizing · Band-Based Routing · Auto Learning · AI Advisory) | Pre-RC1 latent-capability buildout | 🟠 designed-to-be-dormant; activation per evidence gates |

---

## 6. Cross-cutting verdicts

| Question | Answer |
|---|---|
| **Are there features on the roadmap with no code?** | YES, 3 large: Phase 13 Dossier · Phase 14 Valuation · Phase 15 Marketplace. Plus BI5 R2/R3 (queued P0). |
| **Are there features in code that nobody on the roadmap asked for?** | A few minor ones (Runner Registry UI, BI5 backfill UI button). None are dangerous; mostly nice-to-haves the operator can decide on. |
| **Are there features in code intentionally hidden by operator decree?** | YES — the entire Factory Supervisor stack (22 engines, 40 endpoints) is FS-P1.4 hard-veto dormant. |
| **Are there orphan files truly dead?** | 9 of 10 are dead (clear replacements). `ArchitectDashboard.jsx` is the only orphan that holds roadmap-aligned IP — its 9 cards need to be rehoused before retirement. |
| **Are any C/D items blocking the 1-vCPU import?** | NO — verified in `POST_IMPORT_FEATURE_DEPENDENCY.md`. |
| **Are any backend APIs missing operator panels in a way that risks pipeline correctness?** | NO. Every Stage-1-through-6 dependency has a panel. Hidden APIs are observability/audit/admin surfaces, not pipeline blockers. |

---

## 7. Net roadmap-reconciliation verdict

The codebase is **roadmap-aligned** with three categories of gap:

1. **Forward-roadmap (intentional):** Phase 13 / 14 / 15 + BI5 R2 / R3 — reservation cards mounted, engines queued. ~6 large items, all P0/P2.
2. **Operator-veto (intentional):** Factory Supervisor stack (22 engines, 40 endpoints) — hidden by FS-P1.4 directive. Activates post-stabilisation.
3. **Janitorial (unintentional):** 10 orphan files (9 retire, 1 rehouse-then-retire) — ~2 h to clean up.

**No roadmap-aligned capability is missing without an explicit deferral reason.**
**No surprise capability is silently active.**
**No orphan file is consuming runtime resources** (none are imported anywhere).

---

## 8. State of this document

* Read-only audit.
* Triplet with `CAPABILITY_CATALOG.md` (full inventory) + `MISSING_FROM_UI.md` (operator visibility view).
* No code modified. No surfaces mounted. No flags flipped. No imports run.

**End of report.**
