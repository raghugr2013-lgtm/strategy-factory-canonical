# FINAL_CAPABILITY_MAP.md

**Status:** AS-BUILT capability visibility census after restoration Steps 1–7 (2026-06-12). Supersedes the *planned* verdicts in `CAPABILITY_PLACEMENT_MATRIX.md` — every verdict below is the implemented reality. Full per-item detail remains in `CAPABILITY_CATALOG.md` (159 items).

---

## 1. Census roll-up (delta vs pre-restoration)

| Class | Pre-restoration | Post-restoration | Delta |
|---|---|---|---|
| ACTIVE — mounted operator surfaces | ~35 panels | ~37 panels | +2 NEW thin composites (DashboardComposite, ExecutionOverview) + 3 inline affordances (BI5 strip, readiness line, palette Sections) |
| ACTIVE — engines by design (no panel) | ~65 | ~65 | unchanged |
| HIDDEN (UI exists, unmounted) | 6 | **5** | −1: Challenge Matching promoted to `propfirm#challenge` |
| DORMANT (flag-gated engines) | ~22 | ~22 | unchanged — **zero flags flipped** |
| PLACEHOLDER (reservations) | 5 | 5 | unchanged content; 4 cards now inside collapsed bottom accordions |
| FUTURE (not built, slot pre-booked) | 9 | 9 | unchanged |
| ORPHAN files in working tree | 10 | **1** | 9 quarantined to `/app/_inventory/retired_frontend_2026-06/` (NO deletion); `ArchitectDashboard.jsx` intentionally kept (rehousing IP source) |

**Zero capability was lost. Zero hidden system was activated.**

## 2. Visible operator surfaces (post-restoration)

| Module | Sections (all mounted) |
|---|---|
| dashboard | Mission Control composite (MissionBriefing + 8-panel stack) |
| exec | **Overview (NEW)** · brokers · paper · runner · live |
| mutate | factory-55 · auto · cycle · factory · auto-select · master-bot · master-bot-compile |
| diag | readiness · parity · ingestion · ingest-src · pipeline · market-data (+ **BI5 strip**) · bi5-health · monitoring (Runtime/Soak/Compute/Cluster) |
| lab | workspace · panel · analysis · backtest · cbot · optim · validate |
| explorer | explorer · saved · compare · **reservations accordion** |
| portfolio | builder · panel · intel · **Phase-14 accordion** |
| propfirm | admin · match · **challenge (NEW — surfaced)** |
| ai | river · orch · sched |
| governance | gov · universe · symbol-registry · rules · env · readiness · admin (+ **readiness one-liner**) |
| shell overlays | rails · ribbons · 4 drawers · palette (+ **Sections group**) · shortcuts |

## 3. Still hidden — intentionally (with unhide triggers)

| Capability | Trigger | Future home (pre-named) |
|---|---|---|
| Factory Supervisor Panel + FS stack (22 engines, ~40 endpoints) | FS-P1.4 veto lift decree | Monitoring ▸ Cluster (stacked) |
| Architect Dashboard 9 cards (Advisor Stream · Recommendation Feed …) | FS veto lift | `ai#architect` (rehouse from `ArchitectDashboard.jsx`) |
| Auto Learning panel + loop | `FS_ENABLE_AUTO_LEARNING=true` | `ai#learning` |
| Notification Center persistence (6 endpoints) | `ENABLE_NOTIFICATION_CENTER=true` | rewire existing Inbox drawer |
| Copilot advanced (multi-provider) | `FS_ENABLE_COPILOT_ADVANCED=true` | v2 toggle in existing Copilot drawer |
| BI5 Certification (8 endpoints) | BI5 R2 lands | `diag#bi5-cert` |
| Runner Registry / Heartbeat / Multi-Account | multi-account go-live | `exec#runners` |
| DSR Audit Log · Activation Timeline · Widening History | P2 additive passes | Symbol-Registry sub-tab · `governance#activation` · Flags expander |
| ~17 latent flag-gated engines (calibration, RoR, decay, admission, …) | per-flag evidence gates | verdict columns / telemetry rows — no standalone panels |

## 4. Deferred by gate (unchanged by restoration)

| Gate | Items |
|---|---|
| GATE 3 — strategy import (separate operator decision) | 1-vCPU import 6-stage pipeline (`POST_IMPORT_PIPELINE.md`); imported-cohort columns appear automatically post-import |
| Phase 13 | Dossier engine → populates Explorer accordion slots in-place |
| Phase 14 | Valuation engine → populates Portfolio accordion scorecards in-place |
| Phase 15 | Marketplace (separate codebase); ASF touchpoint = Explorer accordion card |
| BI5 R2/R3 (roadmap P0) | auto-cert sweep + `diag#bi5-cert`; tick-replay default toggle |
| Broker reservations | cTrader Demo/Live · Windows VPS · telemetry → activate chips in `exec#brokers` |

## 5. Quarantined (Step 6 — recoverable, never deleted)

`/app/_inventory/retired_frontend_2026-06/` — `Optimization.js`, `NavMoreMenu.js`, `DensityToggle.js`, `TraderModeButton.js`, `phase9/` (5 files). Zero importers verified pre-move; production build green post-move. Permanent removal requires a later architectural review. `ArchitectDashboard.jsx` remains in `components/` by design.

**End of map.**
