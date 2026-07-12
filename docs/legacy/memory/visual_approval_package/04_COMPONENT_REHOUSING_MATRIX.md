# 04 · Component Re-housing Matrix (Zero-loss proof)

> Every component currently mounted in the workstation gets an **explicit home** in the restored tab structure. This document is the audit trail proving zero capability loss.

---

## 1 · Master matrix

| # | Component (current codebase) | Current path in `modulesRegistry.js` | Restored tab | Restored sub-location |
|--:|---|---|---|---|
| 1 | `GovernanceCard.jsx` | dashboard | **dashboard** | dashboard stack |
| 2 | `UniverseGovernancePanel.jsx` | dashboard | **dashboard** | dashboard stack |
| 3 | `StrategyIngestionCard.js` | dashboard | **dashboard** | dashboard stack |
| 4 | `AutoSchedulerControl.js` | ai/sched | **dashboard** | dashboard stack |
| 5 | `OrchestratorPanel.js` | ai/orch | **dashboard** | dashboard stack |
| 6 | `MultiCycleRunner.js` | mutate/cycle | **dashboard** | dashboard stack |
| 7 | `AutoMutationRunner.js` | mutate/auto | **dashboard** | dashboard stack |
| 8 | `StrategyDashboard.js` | dashboard | **dashboard** | dashboard stack (table) |
| 9 | `DeploymentReadinessCard.jsx` | diag/readiness | **dashboard** | NEW right-rail card |
| 10 | `IngestionHealthCard.jsx` | diag/ingestion | **dashboard** | NEW right-rail card |
| 11 | `ParityCertificationCard.jsx` | diag/parity | **dashboard** | NEW right-rail card |
| 12 | `PipelineLogsPanel.js` | diag/pipeline | **dashboard** | bottom log-tail strip |
| 13 | `phase9/ExecutionDashboard.js` | (not in current rail) | **execution** | sole content |
| 14 | `phase9/AutoFactoryCard.js` | composed inside ExecutionDashboard | **execution** | step ① |
| 15 | `phase9/PortfolioBuilderCard.js` | composed inside ExecutionDashboard | **execution** | step ② |
| 16 | `phase9/LiveExecutionCard.js` | composed inside ExecutionDashboard | **execution** | step ③ |
| 17 | `AutoFactoryPhase55.js` | mutate/factory-55 | **auto-factory** | hero |
| 18 | `MasterBotCompilePanel.jsx` | mutate/master-bot-compile | **auto-factory** | collapsed accordion below |
| 19 | `MasterBotDashboard.jsx` | mutate/master-bot | **monitoring** (Cluster sub-tab — via FactorySupervisorPanel composition) ¹ | Cluster tab |
| 20 | `MutateMasterBotCompile.jsx` | mutate/master-bot-compile | **auto-factory** | (same as 18) |
| 21 | `Monitoring.js` | diag/monitoring (Runtime) | **monitoring** | Runtime sub-tab |
| 22 | `MonitoringSuite.jsx` | diag/monitoring (composite) | **monitoring** | sub-tab bar host |
| 23 | `SoakDiagnosticsPanel` (via OperatorParityPanels) | diag/monitoring (Soak) | **monitoring** | Soak sub-tab |
| 24 | `CpuPoolStatePanel` (via OperatorParityPanels) | diag/monitoring (Compute) | **monitoring** | Compute sub-tab |
| 25 | `ScalingPanel` (via OperatorParityPanels) | diag/monitoring (Cluster) | **monitoring** | Cluster sub-tab |
| 26 | `FactorySupervisorPanel` (via OperatorParityPanels) | diag/monitoring (Cluster) | **monitoring** | Cluster sub-tab |
| 27 | `PaperExecution.js` | exec/paper | **paper-exec** | sole content |
| 28 | `TradeRunner.js` | exec/runner | **trade-runner** | sole content |
| 29 | `PortfolioBuilder.js` | portfolio/builder | **portfolio-builder** | Builder sub-tab |
| 30 | `PortfolioPanel.js` | portfolio/panel | **portfolio-builder** | Panel sub-tab |
| 31 | `PortfolioIntelligence.js` | portfolio/intel | **portfolio-builder** | Panel sub-tab (lower section) |
| 32 | `StrategyExplorer.js` | explorer/explorer | **explorer** | left list |
| 33 | `SavedStrategies.js` | explorer/saved | **saved** (More ▾) | sole content + count badge |
| 34 | `StrategyComparison.js` | explorer/compare | **workspace** | bottom (when ranked ≥ 1) |
| 35 | `StrategyDeepDivePanel.js` | (drilldown overlay) | **explorer** | right pane |
| 36 | `StrategyDetailsPanel.js` | (drilldown overlay) | **explorer** | global `AsfDetailDrawer` |
| 37 | `DataUpload.js` | diag/market-data (Manual) | **data** | Manual sub-tab |
| 38 | `DataMaintenancePanel.js` | diag/market-data (Automated) | **data** | Automated sub-tab |
| 39 | `DataAvailability.js` | (composed inside Manual today) | **data** | Manual sub-tab (below DataUpload) |
| 40 | `DataBackupPanel` (via OperatorParityPanels) | diag/market-data (Archive) | **data** | Archive sub-tab |
| 41 | `MarketDataWorkbench.jsx` | diag/market-data (composite) | **data** | sub-tab bar host |
| 42 | `AutoSelection.js` | mutate/auto-select | **auto-select** | sole content |
| 43 | `ReadinessPanel.js` | governance/readiness | **admin-users** | top-pinned strip (Users sub-tab) |
| 44 | `AdminUsers.js` | governance/admin (Users) | **admin-users** | Users sub-tab |
| 45 | `AdminFlagGovernancePanel` (via OperatorParityPanels) | governance/admin (Flags) | **admin-users** | Flags sub-tab |
| 46 | `AdminExecutionRealismPanel` (via OperatorParityPanels) | governance/admin (Realism) | **admin-users** | Realism sub-tab |
| 47 | `Phase12TuningPanel` (via OperatorParityPanels) | governance/admin (Tuning) | **admin-users** | Tuning sub-tab |
| 48 | `GovernanceAdminSuite.jsx` | governance/admin (host) | **admin-users** | sub-tab bar host |
| 49 | `RulesReviewPanel.js` | governance/rules | **admin-users** | Rules sub-tab |
| 50 | `EnvPriorityPanel.js` | governance/env | **admin-users** | (inside Rules sub-tab footer) |
| 51 | `StrategyPanel.js` | lab/panel | **workspace** | left col |
| 52 | `StrategyAnalysis.js` | lab/analysis | **workspace** | left col (below) |
| 53 | `BacktestPanel.js` | lab/backtest | **workspace** | right col top |
| 54 | `StrategyDescription.js` | (rendered by workspace) | **workspace** | right col (after backtest) |
| 55 | `CbotPanel.js` | lab/cbot | **workspace** | right col (after description) |
| 56 | `OptimizationPanel.js` | lab/optim | **workspace** | right col (2-col with Validation) |
| 57 | `ValidationPanel.js` | lab/validate | **workspace** | right col (2-col with Optimization) |
| 58 | `Optimization.js` | (standalone) | **optimization** (More ▾) | sole content |
| 59 | `AutoFactory.js` (legacy) | (none in current rail) | **pipeline** (More ▾) | sole content |
| 60 | `PropFirmsAdmin.js` | propfirm/admin | **prop-firms** (More ▾) | Admin sub-tab |
| 61 | `FirmMatchPanel.js` | propfirm/match | **prop-firms** (More ▾) | Match sub-tab |
| 62 | `AddFirmModal.js` | (modal — invoked from PropFirmsAdmin) | **prop-firms** (More ▾) | Admin sub-tab modal |
| 63 | `ChallengeMatchingPanel` (via OperatorParityPanels) | (challenge embedded) | **prop-firms** (More ▾) | Challenge sub-tab |
| 64 | `LiveTrackingPanel.js` | exec/live | **live** (More ▾) | sole content |
| 65 | `StrategyChartView.js` | (drilldown overlay) | (rendered inside StrategyDeepDivePanel) | — |
| 66 | `ArchitectDashboard.jsx` | (not in primary rail today) | **monitoring** | Cluster sub-tab footer |
| 67 | `OperatorEndpointPanel.jsx` | (not in primary rail today) | **admin-users** | Rules sub-tab (system endpoints reference) |
| 68 | `GemFactoryPanel` (via OperatorParityPanels) | (latent / observability) | **auto-factory** | bottom debug strip (admin-only) |

¹ `MasterBotDashboard.jsx` is currently *also* at `mutate/master-bot`. The restored UI keeps Master Bot **administration** under Monitoring → Cluster (where the fleet lives), while **compilation** stays under Auto Factory. This matches old operator muscle memory ("Master Bot is a deployment / monitoring concept; compile is part of factory output").

---

## 2 · Sections in current rail (41 total) — all accounted for

```
dashboard (1):                            → S-01 ✓
lab (6):       panel/analysis/backtest/cbot/optim/validate          → S-12 (Workspace, More) ✓
explorer (3): explorer/saved/compare                                → S-08 + S-17 (saved) + S-12 (compare) ✓
mutate (7):   auto/cycle/factory/factory-55/auto-select/master-bot/master-bot-compile
              → cycle+auto+master-bot-compile → S-01 dashboard
              → factory+factory-55+master-bot-compile → S-03 auto-factory
              → auto-select → S-10
              → master-bot → S-04 Cluster ✓
portfolio (3): builder/panel/intel                                   → S-07 ✓
propfirm (2): admin/match (+ challenge embedded)                     → S-14 ✓
exec (3): paper/runner/live                                          → S-05 + S-06 + S-15 ✓
ai (3): river/orch/sched                                             → orch+sched → S-01 dashboard
                                                                       river → S-01 dashboard log strip ✓
diag (7): readiness/parity/ingestion/ingest-src/pipeline/market-data/monitoring
                                                                     → readiness+parity+ingestion → S-01 cards
                                                                       ingest-src → S-09 Manual sub-tab inline
                                                                       pipeline → S-01 log-tail strip
                                                                       market-data → S-09 ✓
                                                                       monitoring → S-04 ✓
governance (6): gov/universe/rules/env/readiness/admin               → S-01 + S-11 ✓
```

Total: **10 modules · 41 sections** → all routed.

---

## 3 · Cross-check against operator preference list (verbatim from brief)

| Operator preference | Restored as | Status |
|---|---|---|
| Dashboard | S-01 | ✓ |
| Execution | S-02 | ✓ |
| Auto Factory | S-03 | ✓ |
| Monitoring | S-04 | ✓ |
| Paper Execution | S-05 | ✓ |
| Trade Runner | S-06 | ✓ |
| Portfolio | S-07 | ✓ |
| Explorer | S-08 | ✓ |
| Market Data | S-09 | ✓ |
| Auto Select | S-10 | ✓ |
| Admin | S-11 | ✓ |

**Result: 11/11 operator preference items match S-IDs exactly.**

— End of REHOUSING MATRIX —
