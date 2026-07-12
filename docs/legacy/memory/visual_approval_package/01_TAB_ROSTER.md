# 01 · Tab Roster (LOCKED)

> Verbatim from the old 1-vCPU `src/App.js` LL 167–185 — the **only**
> source-of-truth for the tab structure. Code in the old codebase
> includes an explicit lock comment:
>
> ```
> 🔒  NAVBAR CONFIG — LOCKED  🔒
> Per product spec the CORE navbar must always carry these 11 items,
> in this order, and the set must NOT be mutated by role-based hiding,
> responsive breakpoints, or auto-relegation to "More".
> ```

## 1 · CORE_TABS (always-visible top bar — left to right)

| # | Tab ID (verbatim) | Label | Source ref |
|--:|---|---|---|
| 1 | `dashboard` | **Dashboard** | App.js L167 |
| 2 | `execution` | **Execution** | App.js L168 |
| 3 | `auto-factory` | **Auto Factory** | App.js L169 |
| 4 | `monitoring` | **Monitoring** | App.js L170 |
| 5 | `paper-exec` | **Paper Exec** | App.js L171 |
| 6 | `trade-runner` | **Trade Runner** | App.js L172 |
| 7 | `portfolio-builder` | **Portfolio** | App.js L173 |
| 8 | `explorer` | **Explorer** | App.js L174 |
| 9 | `data` | **Market Data** | App.js L175 |
| 10 | `auto-select` | **Auto Select** | App.js L176 |
| 11* | `admin-users` | **Admin** | App.js L189 (admin role only) |

`*` Admin is appended for admin role; never hidden, never moved to MORE.

## 2 · MORE_TABS (`More ▾` overflow popover — Binance-style)

| # | Tab ID | Label | Source ref |
|--:|---|---|---|
| 1 | `workspace` | **Workspace** | App.js L179 |
| 2 | `pipeline` | **Auto Factory (Legacy)** | App.js L180 |
| 3 | `prop-firms` | **Prop Firms** | App.js L181 |
| 4 | `live` | **Live Tracking** | App.js L182 |
| 5 | `optimization` | **Optimization** | App.js L183 |
| 6 | `saved` | **Library (N)** | App.js L184 (counter from `savedStrategies.length`) |

## 3 · Behavioural contract (do not break)

1. **Order is locked.** No conditional hiding by role / breakpoint / activity.
2. **No auto-relegation.** Items never silently move between CORE and MORE.
3. **Horizontal scroll fallback** at narrow viewports — `.navbar-menu` carries `overflow-x:auto`, vertical wheel is hijacked into horizontal scroll (App.js LL 130–140).
4. **`scrollIntoView({inline:'center', behavior:'smooth'})`** is fired on every `activeTab` change so the active tab is NEVER off-screen (App.js LL 144–151).
5. **Admin always appended for admin users** (App.js L189) — never hidden, never moved to MORE.
6. **MORE menu is `position:fixed`** popover anchored to its trigger's bounding rect (NavMoreMenu.js LL 23–28) — escapes the `overflow-x:auto` scroll container via z-60.

## 4 · Tab content map (high level)

| Tab | Renders | New capabilities folded in |
|---|---|---|
| `dashboard` | GovernanceCard + UniverseGovernancePanel + StrategyIngestionCard + AutoSchedulerControl + OrchestratorPanel + MultiCycleRunner + AutoMutationRunner + StrategyDashboard | + DeploymentReadinessCard + IngestionHealthCard + ParityCertificationCard + PipelineLogsPanel (live tail strip) |
| `execution` | ExecutionDashboard (3-step strip: Generate → Allocate → Execute) | unchanged |
| `auto-factory` | AutoFactoryPhase55 | + MasterBotCompilePanel (collapsed accordion) |
| `monitoring` | Monitoring | + SoakDiagnosticsPanel + CpuPoolStatePanel + ScalingPanel + FactorySupervisorPanel (4-tab sub-bar: Runtime · Soak · Compute · Cluster) |
| `paper-exec` | PaperExecution | unchanged |
| `trade-runner` | TradeRunner | unchanged |
| `portfolio-builder` | PortfolioBuilder | unchanged |
| `explorer` | StrategyExplorer | + StrategyDeepDivePanel (right side-pane) + StrategyDetailsPanel (drawer) |
| `data` | DataUpload + DataMaintenancePanel | + DataAvailability + DataBackupPanel (3 sub-tabs: Manual · Automated · Archive) |
| `auto-select` | AutoSelection | unchanged |
| `admin-users` | ReadinessPanel + AdminUsers | + AdminFlagGovernancePanel + AdminExecutionRealismPanel + Phase12TuningPanel + RulesReviewPanel + EnvPriorityPanel (5-tab sub-bar) |
| `workspace` | StrategyPanel + BacktestPanel + StrategyDescription + CbotPanel + OptimizationPanel + ValidationPanel + StrategyAnalysis + StrategyComparison (3-col 9-col grid) | unchanged |
| `pipeline` | AutoFactory (legacy) | unchanged |
| `prop-firms` | PropFirmsAdmin + FirmMatchPanel | + ChallengeMatching (sub-tab) |
| `live` | LiveTrackingPanel | unchanged |
| `optimization` | Optimization | unchanged |
| `saved` | SavedStrategies | unchanged |
| `portfolio` ¹ | PortfolioPanel + PortfolioIntelligence | NEW capability folded |

¹ `portfolio` is a child of `portfolio-builder` in the new layout — exposed via a 2-tab sub-bar **Builder · Panel & Intelligence**.

## 5 · Reverse census (zero capability loss)

Total current `modulesRegistry.js` sections: **41**. Total restored homes: **41**. Mapping enumerated in `04_COMPONENT_REHOUSING_MATRIX.md`.

— End of TAB ROSTER —
