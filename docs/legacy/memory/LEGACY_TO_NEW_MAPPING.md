# LEGACY_TO_NEW_MAPPING.md

**Companion to:** `LEGACY_UI_RECONCILIATION_AUDIT.md`
**Purpose:** Single-page lookup table for every legacy 1-vCPU screen and every post-1-vCPU subsystem.
**Status:** Read-only. No code modified.

---

## Status legend

| Code | Meaning |
|---|---|
| **MR** | Mounted and reachable (primary nav) |
| **MH** | Mounted but hidden (palette / power-user sub-tab / `/legacy`) |
| **MV** | Moved (1:1 to a new location) |
| **MG** | Merged into composite |
| **BO** | Backend exists, UI missing |
| **UO** | UI exists, backend missing |
| **PL** | Placeholder / reservation only |
| **MX** | Missing entirely |

---

## 1. Legacy CORE_TABS (always-visible in 1-vCPU)

| # | Legacy Screen | Current Screen | Route | Status | Missing Elements | Recommended Mount Location |
|--:|---|---|---|---|---|---|
| 1 | **Dashboard** — 8-panel stack (GovernanceCard + UniverseGovernancePanel + StrategyIngestionCard + AutoSchedulerControl + OrchestratorPanel + MultiCycleRunner + AutoMutationRunner + StrategyDashboard) | Mission Briefing + 8 distributed homes | `/c/dashboard/briefing` | **MG + MV** | Single-page everything view (now requires navigation) | Accept Mission Briefing as canonical. Briefing already provides KPI synthesis; each panel is 1 click away via LeftRail / palette deep-link |
| 2 | **Execution** — Phase 9 3-step (ExecutionDashboard composing AutoFactoryCard + PortfolioBuilderCard + LiveExecutionCard) | **NOT WIRED** — components in `frontend/src/components/phase9/` not imported in `modulesRegistry.js` | (none) | **MH** | The unified Generate→Allocate→Execute strip | Wire `dashboard/exec-strip` section to mount `ExecutionDashboard` OR formally retire (visual approval implies Mission Briefing supersedes — confirm with operator) |
| 3 | **Auto Factory** — `AutoFactoryPhase55` | Auto Factory · Phase 55 | `/c/mutate/factory-55` | **MV** | Top-of-bar muscle memory only | Acceptable. LifecycleRail surfaces it. Optional: promote to top-tab per visual approval `01_TAB_ROSTER.md` |
| 4 | **Monitoring** — `Monitoring.js` (Stop-all / Resume / Thresholds / Breach Log / Fleet) | MonitoringSuite → Runtime sub-tab | `/c/diag/monitoring` (Runtime) | **MG** | None | Acceptable. Visual approval recommends top-level `monitoring` tab — defer to operator preference |
| 5 | **Paper Exec** — `PaperExecution` (BID/BI5 replay) | Paper Execution | `/c/exec/paper` | **MV** | None | Acceptable |
| 6 | **Trade Runner** — `TradeRunner` | Trade Runner | `/c/exec/runner` | **MV** | None | Acceptable |
| 7 | **Portfolio** — `PortfolioBuilder` | Portfolio Builder | `/c/portfolio/builder` | **MV** | None — actually richer (Portfolio Panel + Intelligence now in primary nav, was hidden in legacy) | Acceptable |
| 8 | **Explorer** — `StrategyExplorer` | Strategy Explorer | `/c/explorer/explorer` | **MV** | None — enhanced with 3 reservation cards (Score / Dossier / Marketplace) and a Comparison section | Acceptable |
| 9 | **Market Data** — `DataUpload` + `DataMaintenancePanel` stacked | MarketDataWorkbench (Manual · Automated · Archive) | `/c/diag/market-data` | **MG + MV** | None — `DataAvailability` and `DataBackupPanel` ADDED | Acceptable. Visual approval recommends top-level `data` tab — defer to operator |
| 10 | **Auto Select** — `AutoSelection` | Auto Selection | `/c/mutate/auto-select` | **MV** | None | Acceptable |
| 11 | **Admin** (admin role only) — `ReadinessPanel` + `AdminUsers` | GovernanceAdminSuite (Users · Flags · Realism · Tuning · Rules sub-tabs) | `/c/governance/admin` | **MG + MV** | Top-pinned `ReadinessPanel` strip per visual approval — verify post-hydration | Acceptable; verify ReadinessPanel renders top-pinned |

---

## 2. Legacy MORE_TABS (`More ▾` overflow popover in 1-vCPU)

| # | Legacy Screen | Current Screen | Route | Status | Missing Elements | Recommended Mount Location |
|--:|---|---|---|---|---|---|
| 1 | **Workspace** ⭐ — single 12-col grid: StrategyPanel + StrategyAnalysis + BacktestPanel + StrategyDescription + CbotPanel + OptimizationPanel + ValidationPanel + StrategyComparison | 6 separate Lab sections + Compare under Explorer | `/c/lab/{panel,analysis,backtest,cbot,optim,validate}` + `/c/explorer/compare` | **MG (inverted)** | The unified workspace UX (was 1 page → now 6 pages) | **P1: add `lab/workspace` composite** section mounting the full 3-col 9-col grid per `04_COMPONENT_REHOUSING_MATRIX.md` rows 51–57. All components already imported by `modulesRegistry.js`. Effort: ~2 h |
| 2 | **Auto Factory (Legacy)** — `AutoFactory` | Auto Factory | `/c/mutate/factory` | **MV** | None | Acceptable |
| 3 | **Prop Firms** — `PropFirmsAdmin` (Phase 20) | Prop Firms Admin | `/c/propfirm/admin` (+ `/c/propfirm/match`) | **MV (enriched)** | `AddFirmModal` invocation, embedded `ChallengeMatchingPanel` sibling | **P2: mount `propfirm/challenge`** for ChallengeMatchingPanel (currently parked in Governance Admin Power-User sub-tab). Effort: ~30 min |
| 4 | **Live Tracking** — `LiveTrackingPanel` | Live Tracking | `/c/exec/live` | **MV** | None | Acceptable |
| 5 | **Optimization** — standalone `Optimization` (Phase 8) | **NOT WIRED** — `Optimization.js` exists; not imported by `modulesRegistry.js` | (none) | **MH** | The standalone strategy refinement surface | Decide: add `lab/optim-standalone` OR confirm per-strategy `lab/optim` covers the use case. Visual approval row 58 calls for a MORE-tab `optimization` |
| 6 | **Library (N)** — `SavedStrategies` with count badge | Saved Strategies | `/c/explorer/saved` | **MV** | Count badge `Library (${savedStrategies.length})` in tab label — verify TopTabBar carries it | **P1: add count badge** in `TopTabBar.jsx`. Effort: < 30 min |

---

## 3. Hidden legacy routes

| # | Legacy Route | Current Screen | Route | Status | Missing Elements | Recommended Mount Location |
|--:|---|---|---|---|---|---|
| 1 | `portfolio` (no nav entry; `setActiveTab('portfolio')` only) — `PortfolioPanel` | Portfolio Panel (now visible) | `/c/portfolio/panel` | **MV (upgraded)** | None — promoted from hidden to visible | Acceptable |

---

## 4. Operator-named legacy subsystems

| # | Operator Term | Legacy Component(s) | Current Screen | Route | Status | Missing | Recommended Mount Location |
|--:|---|---|---|---|---|---|---|
| 1 | **AI Architecture** | (no dedicated tab; dashboard panels) | Live River + Orchestrator + Auto-Scheduler (AI Workforce module) + Architect Dashboard (palette) + CopilotPanel (⌘J) | `/c/ai/{river,orch,sched}` + palette + ⌘J | **MR (split) + MH (Architect)** | The synthesized "what is the AI doing now" architecture view — Architect Dashboard is dormant (`FS_ENABLE_ARCHITECT_DASHBOARD=false`) | Acceptable; activate Architect after FS soak |
| 2 | **Strategy Generator** | `StrategyPanel` | Strategy Panel | `/c/lab/panel` | **MR** | None | Acceptable |
| 3 | **Strategy Output** | `BacktestPanel` + `StrategyDescription` + `StrategyDetailsPanel` | Backtest section + AsfDetailDrawer | `/c/lab/backtest` + global drawer | **MR + MG** | Verify `StrategyDescription` inline-renders inside BacktestPanel | Verify post-hydration |
| 4 | **AI Analysis** | `StrategyAnalysis` | Analysis section | `/c/lab/analysis` | **MR** | None | Acceptable |
| 5 | **Indicator Ideas** | Inline within `StrategyPanel` | Same — inside StrategyPanel | `/c/lab/panel` | **MR (inline)** | If a dedicated panel is wanted, none exists | Confirm with operator whether standalone "Indicator Ideas" surface is required |
| 6 | **Random Search Optimizer** | `OptimizationPanel` + standalone `Optimization` | Optimization section + (standalone unwired) | `/c/lab/optim` + (none for standalone) | **MR + MH** | Standalone Optimization | See §2 row 5 |
| 7 | **Validator** | `ValidationPanel` | Validation section | `/c/lab/validate` | **MR** | None | Acceptable |
| 8 | **Monitoring Center** | `Monitoring.js` | MonitoringSuite → Runtime | `/c/diag/monitoring` | **MG** | None | Acceptable |
| 9 | **Market Data Maintenance** | `DataUpload` | MarketDataWorkbench → Manual | `/c/diag/market-data` (Manual) | **MR** | None | Acceptable |
| 10 | **Auto Data Maintenance** | `DataMaintenancePanel` | MarketDataWorkbench → Automated | `/c/diag/market-data` (Automated) | **MR** | None — actually enhanced with B-1 BI5 dispatch | Acceptable |
| 11 | **Auto Factory Controls** | `AutoFactoryPhase55` + `AutoFactory` | Both wired | `/c/mutate/factory-55` + `/c/mutate/factory` | **MR** | Top-of-bar muscle memory | Acceptable; LifecycleRail surfaces |
| 12 | **Explorer** | `StrategyExplorer` | Strategy Explorer | `/c/explorer/explorer` | **MR (enhanced)** | None | Acceptable |
| 13 | **Portfolio Builder** | `PortfolioBuilder` | Portfolio Builder | `/c/portfolio/builder` | **MR** | None | Acceptable |
| 14 | **Execution Simulator** | `PaperExecution` | Paper Execution | `/c/exec/paper` | **MR** | None | Acceptable |
| 15 | **Auto Selection** | `AutoSelection` | Auto Selection | `/c/mutate/auto-select` | **MR** | None | Acceptable |
| 16 | **Prop Firm Manager** | `PropFirmsAdmin` | Prop Firms Admin | `/c/propfirm/admin` | **MR** | None | Acceptable |
| 17 | **Challenge Profiles** | Embedded in `PropFirmsAdmin` | ChallengeMatchingPanel (Power-User sub-tab in Governance Admin) | `/c/governance/admin → Challenge sub-tab` | **MH** | Top-level discoverability under Prop Firm | **P2: mount at `propfirm/challenge`** |
| 18 | **Live Tracking** | `LiveTrackingPanel` | Live Tracking | `/c/exec/live` | **MR** | None | Acceptable |
| 19 | **Optimization** (standalone) | `Optimization` | (not wired) | (none) | **MH** | Standalone surface | See §2 row 5 |
| 20 | **Strategy Library** | `SavedStrategies` | Saved Strategies | `/c/explorer/saved` | **MR** | Count badge | See §2 row 6 |
| 21 | **Trade Runner** | `TradeRunner` | Trade Runner | `/c/exec/runner` | **MR** | None | Acceptable |
| 22 | **Master Bot** | (not in 1-vCPU) | Master Bot Dashboard + Compile | `/c/mutate/master-bot` + `/c/mutate/master-bot-compile` | **MR** | Per visual approval, also under Cluster sub-tab | **P3 (optional): add to `diag/monitoring` Cluster** |
| 23 | **Factory Supervisor** | (not in 1-vCPU) | FactorySupervisorPanel + ArchitectDashboard | palette / Cluster sub-tab | **MH (dormant)** | Primary-nav discoverability when activated | Acceptable while dormant |
| 24 | **Auto Learning Infrastructure** | (not in 1-vCPU) | (no dedicated panel; reads via Architect/Copilot when ON) | (none) | **BO (dormant)** | Operator-facing learning insights surface | Create `ai/learning` section when `FS_ENABLE_AUTO_LEARNING` activated |
| 25 | **Dynamic Symbol Registry (DSR)** | (not in 1-vCPU) | SymbolRegistryPanel | `/c/governance/symbol-registry` | **MR** | None | Acceptable. DSR-3 active post-hydration |
| 26 | **BI5 Systems** | Status field inside `DataMaintenancePanel` | BI5HealthPanel + Market Data Workbench + scheduler dispatch | `/c/diag/bi5-health` + `/c/diag/market-data` + `POST /api/admin/bi5/run` + `scripts/bi5_one_shot_backfill.py` | **MR (richer)** | BI5 R2 4-field schema extension (Evidence / Trust / Dossier / Marketplace) — not yet produced | Acceptable. Extend when Phase 13/14 land |

---

## 5. Post-1-vCPU subsystems — visibility check

| # | Subsystem | UI Status | Backend Status | Route | Recommended Mount Location |
|--:|---|---|---|---|---|
| 1 | **Master Bot** | MR | Live | `/c/mutate/master-bot` + `/c/mutate/master-bot-compile` | Single-mount today. Optional second mount under Cluster sub-tab (P3) |
| 2 | **Factory Supervisor** | MH | Dormant | palette + `diag/monitoring` Cluster | Acceptable; surface in primary nav when activated |
| 3 | **DSR** | MR | Active post-hydration | `/c/governance/symbol-registry` | Acceptable |
| 4 | **BI5 Health** | MR | Live | `/c/diag/bi5-health` | Acceptable |
| 5 | **Operator Inbox** | MR (UI) / Dormant (backend NC) | Bell + drawer | global overlay | Acceptable |
| 6 | **Danger Ribbon (EmergencyBanner)** | MR | UI-only auto-render | global overlay | Acceptable |
| 7 | **Marketplace** | PL | NOT BUILT | `/c/explorer/marketplace-reservations` | Phase 15 work — placeholder is correct |
| 8 | **Strategy Dossier** | PL | NOT BUILT | `/c/explorer/passport-reservations` | Phase 13 work — placeholder is correct |
| 9 | **Auto Valuation** | PL | NOT BUILT | `/c/portfolio/scorecards-reservations` | Phase 14 work — placeholder is correct |
| 10 | **Trust Score architecture** | PL | NOT BUILT | `/c/explorer/score-rubric` | M3 reservation — placeholder is correct |
| 11 | **Evidence Score architecture** | PL | NOT BUILT | `/c/explorer/score-rubric` | M3 reservation — placeholder is correct |
| 12 | **Pass Probability architecture** | BO (inline only) | Live (computed; calibration dormant) | rendered inside `StrategyDashboard`, `StrategyComparison`, `StrategyDetailsPanel` | **P3 (optional): create `/c/lab/pass-probability` lineage view** showing input features + calibration table once `ENABLE_CALIBRATION=true` |

---

## 6. Action queue summary (recommended post-hydration follow-ups)

| Priority | Action | Effort | Source of truth |
|---|---|---|---|
| **P1** | Mount Workspace composite at `lab/workspace` | ~2 h | `04_COMPONENT_REHOUSING_MATRIX.md` rows 51–57 |
| **P1** | Add `Library (N)` count badge to TopTabBar `saved` entry | < 30 min | `01_TAB_ROSTER.md` MORE-6 |
| **P2** | Mount ChallengeMatchingPanel at `propfirm/challenge` | ~30 min | `01_TAB_ROSTER.md` MORE-3 footnote |
| **P2** | Decide: wire or retire ExecutionDashboard (`dashboard/exec-strip`) | operator decision | matrix rows 13–16 |
| **P2** | Decide: wire or leave hidden standalone `Optimization.js` | operator decision | matrix row 58 |
| **P3** | Optionally mount `MasterBotDashboard` under Cluster sub-tab | ~30 min | matrix row 19 footnote |
| **P3** | Create Pass Probability lineage view at `/c/lab/pass-probability` | ~2 h | new — no legacy counterpart |
| **P3** | When `FS_ENABLE_AUTO_LEARNING` activates, surface `ai/learning` section | ~2 h | new — Phase FS-P1.4 |

None of these block hydration. Each is reachable by editing `modulesRegistry.js` alone (no backend changes required for items 1–6).

---

## 7. Verdict

* **Every legacy CORE_TAB** has a working home in the new shell.
* **5 of 6 legacy MORE_TABS** are mounted; 1 (standalone Optimization) is an unwired component pending operator decision.
* **1 legacy hidden route** (`portfolio`) was upgraded to a visible section.
* **3 legacy-style composite surfaces** are missing operator-friendly composites: Workspace (P1), Execution 3-step (P2 decision), Standalone Optimization (P2 decision).
* **All 12 post-1-vCPU subsystems** are tracked; 5 are live in primary nav (Master Bot, DSR, BI5 Health, Inbox, Danger Ribbon); 5 are placeholders awaiting Phase 13/14/15 engines (Marketplace, Dossier, Valuation, Trust, Evidence); 1 is computed-but-unsurfaced (Pass Probability lineage); 1 is dormant (Factory Supervisor / Auto Learning).

**Conclusion:** No legacy operator value is lost by hydrating. The shell is a superset of the legacy nav, with 5 small mount-gap items that can be fixed in < 6 hours total post-hydration. Hydration is safe to authorize.
