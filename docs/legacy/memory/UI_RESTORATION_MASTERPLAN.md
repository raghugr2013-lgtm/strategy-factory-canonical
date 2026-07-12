# UI_RESTORATION_MASTERPLAN.md

**Audit type:** Read-only restoration plan. The final operator experience preserves every implemented capability AND restores the simplicity / direct-access workflow of the 1-vCPU UI (`_inventory/old1vcpu/src/App.js` LL 168–187 — `🔒 NAVBAR CONFIG — LOCKED 🔒`).
**Sources:** old 1-vCPU `App.js` (canonical), `screenshots of old ui.docx` (18 frames), `visual_approval_package/01_TAB_ROSTER.md`, `CAPABILITY_CATALOG.md`, `MISSING_FROM_UI.md`, `ROADMAP_RECONCILIATION.md`, current hydrated `modulesRegistry.js`.
**Status:** Read-only. No code modified. No surfaces mounted.
**Generated:** 2026-06-12

---

## 0. Restoration philosophy

> The 1-vCPU UI's strength was **flat, direct, stacked-panel access**: each tab loads one or more panels in a single vertical scroll. The current shell adds genuine value (Phase 13/14/15 reservations · DangerRibbon · LifecycleRail · MissionBriefing synthesis · 4-pane composites) but it lost some of the old UX simplicity by adding a module + section hierarchy.

Three principles:

1. **Preserve the flat top-nav roster.** The 11 CORE + 6 MORE + Admin chip is already preserved 1:1 from the locked navbar config.
2. **Restore the "one click → see the work" feel.** Where the new shell splits a tab into 3 sub-sections, the default landing inside that tab should be the legacy stacked layout. The sub-tabs remain as quick filters, not as required navigation steps.
3. **Integrate the new + future surfaces into the old workflow naturally.** Lifecycle stages → tabs. Reservations → either inline placeholders (Explorer / Portfolio) or post-import deep-links. Drawers → operator-attention overlays (Inbox / Copilot / DangerRibbon), invoked from any tab.

---

## 1. Per-tab restoration table

For every old 1-vCPU tab (11 CORE + 6 MORE) the table answers four questions: original purpose · current equivalent · gap · recommended final version.

### 1.1 CORE — Dashboard

| Field | Detail |
|---|---|
| Old 1-vCPU | Single tab; renders 8 stacked panels (`GovernanceCard` → `UniverseGovernancePanel` → `StrategyIngestionCard` → `AutoSchedulerControl` → `OrchestratorPanel` → `MultiCycleRunner` → `AutoMutationRunner` → `StrategyDashboard`) |
| Original purpose | Single-scroll operator workbench — every operator-attention surface in one place |
| Current equivalent | `/c/dashboard/briefing` = `MissionBriefing.jsx` (single synthesised KPI card with 4 tiles + Attention + Audit + Priorities) |
| Gap | The 8 stacked actionable panels were removed; replaced by a read-only briefing. Operator must now traverse 8+ other tabs to perform the work that used to live on Dashboard. |
| Recommended final | **Stacked composite Dashboard.** Top: `MissionBriefing` (keep — read-only synthesis). Below: a restored stack — `GovernanceCard` → `UniverseGovernancePanel` → `StrategyIngestionCard` → `AutoSchedulerControl` → `OrchestratorPanel` → `MultiCycleRunner` → `AutoMutationRunner` → `StrategyDashboard`. Cap the stack at a single vertical scroll on workstation posture; on tablet, fold into accordions. Estimated work: rewire 8 existing components into `dashboard` module's `briefing` section as a composite. **No new code; all components already in repo.** |

### 1.2 CORE — Execution

| Field | Detail |
|---|---|
| Old 1-vCPU | `ExecutionDashboard` (Phase 9, single panel: `phase9/ExecutionDashboard.js`) |
| Original purpose | One-page operator execution status (KPIs · positions · alerts) |
| Current equivalent | `/c/exec` (no section default → renders first available) with sister sections `brokers`, `paper`, `runner`, `live` |
| Gap | The old `ExecutionDashboard` is orphan (74 LOC, retire candidate). Operator now lands on whichever sub-section is first. |
| Recommended final | **Sub-tab strip stays.** Default landing = a new composite "Execution Overview" that stacks: `ExecutionBrokerChips` (already mounted) + a condensed Paper KPI strip + Trade Runner status row + Live Tracking summary card. The 4 sub-sections remain as drill-down filters. Retire the orphan `phase9/ExecutionDashboard.js`. |

### 1.3 CORE — Auto Factory

| Field | Detail |
|---|---|
| Old 1-vCPU | `AutoFactoryPhase55` (single panel — Phase 55 LIVE STATUS) |
| Original purpose | The pinned active-pipeline view |
| Current equivalent | `/c/mutate/factory-55` (= `AutoFactoryPhase55`) — identical |
| Gap | None. ✅ |
| Recommended final | **Keep as-is.** Already a 1:1 restoration. Sub-sections `auto`, `cycle`, `factory`, `factory-55`, `auto-select`, `master-bot`, `master-bot-compile` continue as drill-downs. |

### 1.4 CORE — Monitoring

| Field | Detail |
|---|---|
| Old 1-vCPU | `Monitoring.js` (single panel: Stop-all / Resume / Save Thresholds / Breach Log / Fleet) |
| Original purpose | One-screen runtime control |
| Current equivalent | `/c/diag/monitoring` = `MonitoringSuite.jsx` (4 sub-tabs: Runtime · Soak · Compute · Cluster) |
| Gap | Soak / Compute / Cluster sub-tabs are NEW operator surfaces added during pre-RC1 — the old UI had no equivalents. |
| Recommended final | **Sub-tab strip stays.** Default landing = Runtime (the old `Monitoring.js` content). Soak · Compute · Cluster remain as drill-downs. **No change.** |

### 1.5 CORE — Paper Exec

| Field | Detail |
|---|---|
| Old 1-vCPU | `PaperExecution` (single panel — BID/BI5 replay) |
| Original purpose | Operator-controlled paper-trade simulator |
| Current equivalent | `/c/exec/paper` (= `PaperExecution`) — identical |
| Gap | None. ✅ |
| Recommended final | **Keep as-is.** |

### 1.6 CORE — Trade Runner

| Field | Detail |
|---|---|
| Old 1-vCPU | `TradeRunner` (Phase 5 single panel) |
| Original purpose | Live-trade dispatcher |
| Current equivalent | `/c/exec/runner` (= `TradeRunner`) — identical |
| Gap | None. ✅ |
| Recommended final | **Keep as-is.** |

### 1.7 CORE — Portfolio Builder

| Field | Detail |
|---|---|
| Old 1-vCPU | `PortfolioBuilder` (Phase 4 single panel) |
| Original purpose | Diversified-bundle composer |
| Current equivalent | `/c/portfolio/builder` (= `PortfolioBuilder`) + 3 sister sections (panel · intel · scorecards-reservations) |
| Gap | Old UI had a SEPARATE Portfolio tab (`/portfolio` → `PortfolioPanel`) in MORE. Current shell folds both under `portfolio` module. The Phase 14 reservation card is a NEW surface. |
| Recommended final | **Keep sub-sections.** Default landing = `builder`. Sister sections `panel` + `intel` available as drill-downs (matching old UI's MORE→Portfolio behaviour). `scorecards-reservations` stays inline as a placeholder. |

### 1.8 CORE — Explorer

| Field | Detail |
|---|---|
| Old 1-vCPU | `StrategyExplorer` (Phase 16 Strategy Memory — single panel) |
| Original purpose | Browse / search / compare strategies |
| Current equivalent | `/c/explorer/{explorer,saved,compare,score-rubric,passport-reservations,marketplace-reservations}` — 3 working + 3 reservation cards |
| Gap | Strategy Score + Phase 13 Dossier + Phase 15 Marketplace cards are all NEW reservations. They interrupt the operator's flow when looking for strategies. |
| Recommended final | **Default landing = `explorer` (browse).** `saved` + `compare` stay as sister sub-sections (matches old UI MORE→Library + GAP-P1-8 promotion). Move the 3 reservation cards into a single collapsible "Phase 13/14/15 Reservations" section at the BOTTOM of the explorer page (operator can expand when curious; doesn't block daily browsing). |

### 1.9 CORE — Market Data

| Field | Detail |
|---|---|
| Old 1-vCPU | `DataUpload` + `DataMaintenancePanel` stacked vertically |
| Original purpose | Manual upload + automated maintenance status, in one scroll |
| Current equivalent | `/c/diag/market-data` = `MarketDataWorkbench` (3 sub-tabs: Manual · Automated · Archive) |
| Gap | Old UI had 2 panels stacked; new UI splits into 3 sub-tabs and forces a click to switch context. The Archive sub-tab (DataBackupPanel) is NEW. |
| Recommended final | **Sub-tab strip stays.** Default landing = Manual (DataUpload) so operator sees the upload control immediately. Sub-tabs Automated + Archive remain as drill-downs. Consider adding the BI5HealthPanel summary as a strip ABOVE the sub-tabs (operator's first question is always "is data ready?"). |

### 1.10 CORE — Auto Select

| Field | Detail |
|---|---|
| Old 1-vCPU | `AutoSelection` (Phase 3 single panel) |
| Original purpose | Multi-criteria strategy selection |
| Current equivalent | `/c/mutate/auto-select` (= `AutoSelection`) — identical |
| Gap | None. ✅ |
| Recommended final | **Keep as-is.** |

### 1.11 CORE — Admin (admin role only)

| Field | Detail |
|---|---|
| Old 1-vCPU | `ReadinessPanel` + `AdminUsers` stacked |
| Original purpose | Single-scroll admin surface |
| Current equivalent | `/c/governance/admin` = `GovernanceAdminSuite` (4 sub-tabs: Users · Flags · Realism · Tuning). ReadinessPanel split off to `/c/governance/readiness`. |
| Gap | Old UI had Readiness + AdminUsers in one scroll. Current shell separates Readiness into Governance, and adds Flags/Realism/Tuning sub-tabs. |
| Recommended final | **Sub-tab strip stays.** Default landing = Users (matches old UI's primary panel). Sister sub-tabs available as drill-downs. Readiness has its own dedicated sub-section in Governance — keep. Optionally surface a single-line "Readiness status: GREEN · OPEN" link at the top of the Admin tab so admin can jump there without navigating. |

### 1.12 MORE — Workspace

| Field | Detail |
|---|---|
| Old 1-vCPU | 3-col left (StrategyPanel + StrategyAnalysis) + 9-col right (BacktestPanel + StrategyDescription + CbotPanel + Optimization+Validation grid + StrategyComparison) — the "single-page lab" |
| Original purpose | Generate → Backtest → Describe → cBot → Optimize/Validate → Compare, all in one scroll |
| Current equivalent | `/c/lab/workspace` = `WorkspaceComposite` (P1.1 restored) |
| Gap | Already restored. ✅ |
| Recommended final | **Keep as-is.** This is the most operator-loved surface; it was deliberately re-mounted in P1 recovery. |

### 1.13 MORE — Auto Factory (Legacy)

| Field | Detail |
|---|---|
| Old 1-vCPU | `AutoFactory` (pre-Phase-55 legacy) |
| Original purpose | Legacy operator alias for the pipeline |
| Current equivalent | `/c/mutate/factory` (= `AutoFactory`) |
| Gap | None. ✅ |
| Recommended final | **Keep as-is.** |

### 1.14 MORE — Prop Firms

| Field | Detail |
|---|---|
| Old 1-vCPU | `PropFirmsAdmin` (Phase 20 — Review & Approval) |
| Original purpose | Firm catalogue CRUD |
| Current equivalent | `/c/propfirm/admin` (= `PropFirmsAdmin`) + sister `propfirm/match` (= `FirmMatchPanel`) |
| Gap | Firm Match was NOT a separate tab in old UI — it lived inside `PropFirmsAdmin`. Challenge Matching is missing entirely from the UI. |
| Recommended final | **Default landing = `admin`** (matches old behaviour). Sister sub-section `match` stays as drill-down. **Add `challenge` sub-section** mounting `ChallengeMatchingPanel` (P1 — `MISSING_OR_HIDDEN_FEATURES.md` §2.1; ~30 min) — this surface was planned in `01_TAB_ROSTER.md` MORE-3 and is operator-deliberately deferred. |

### 1.15 MORE — Live Tracking

| Field | Detail |
|---|---|
| Old 1-vCPU | `LiveTrackingPanel` (single) |
| Original purpose | Live position tracker |
| Current equivalent | `/c/exec/live` (= `LiveTrackingPanel`) — identical |
| Gap | Old UI had Live in MORE; new shell folded it into `exec`. The MORE-chip still routes to `exec/live`, preserving the path. |
| Recommended final | **Keep as-is.** |

### 1.16 MORE — Optimization

| Field | Detail |
|---|---|
| Old 1-vCPU | `Optimization.js` (separate top-level Phase 8 Strategy Refinement panel — 506 LOC) |
| Original purpose | Bulk-optimization workflow at top level |
| Current equivalent | `/c/lab/optim` (= `OptimizationPanel.js`) — different file (96-LOC version that supersedes the 506-LOC orphan) |
| Gap | The old 506-LOC `Optimization.js` is now orphan. `OptimizationPanel.js` is the replacement (mounted). |
| Recommended final | **Keep `OptimizationPanel.js` mounted at `lab/optim`.** Retire `Optimization.js` after operator confirms feature parity (visually inspect to verify nothing was lost). |

### 1.17 MORE — Library (Saved)

| Field | Detail |
|---|---|
| Old 1-vCPU | `SavedStrategies` (single) |
| Original purpose | Saved-strategy browser |
| Current equivalent | `/c/explorer/saved` (= `SavedStrategies`) — folded under `explorer` module |
| Gap | None — already routed to the same component; the Library count badge was P1-restored. ✅ |
| Recommended final | **Keep as-is.** Library count badge stays in `TopTabBar.jsx`. |

---

## 2. New non-old-UI surfaces — where they live

These surfaces did not exist in 1-vCPU. The masterplan answers: keep / fold / hide.

| Surface | Verdict | Placement |
|---|---|---|
| **MissionBriefing** | Keep — it's a valuable read-only synthesis | Top of restored stacked Dashboard (see §1.1) |
| **LifecycleRail (10-step)** | Keep — operator GPS | Top strip of every tab (already there) |
| **StatusRail (6 chips)** | Keep — live posture | Bottom of LifecycleRail strip (already there) |
| **DangerRibbon** | Keep — critical alert visibility | Top of shell (already there) |
| **Operator Inbox Drawer** | Keep | Right-slide drawer (already there) |
| **NotificationDrawer (live overlay)** | Keep | Drawer (already there) |
| **AsfNotificationDrawer (read-only digest)** | Keep | Drawer (already there) |
| **CopilotPanel** | Keep | Drawer (already there) |
| **CommandPalette ⌘K** | Keep | Modal (already there) |
| **ShortcutsOverlay** | Keep | Modal (already there) |
| **EmergencyBanner** | Keep | Top of shell (already there) |
| **BI5HealthPanel** | NEW — keep | `/c/diag/bi5-health` (already mounted); also surface a 1-line strip on Market Data tab (§1.9) |
| **DSR SymbolRegistryPanel** | NEW — keep | `/c/governance/symbol-registry` (already mounted) |
| **Strategy Score Reservation** | Keep | Inline at bottom of Explorer (§1.8) |
| **Phase 13 Dossier Reservation** | Keep | Inline at bottom of Explorer (§1.8) |
| **Phase 14 Dual Scorecard Reservation** | Keep | Inline at bottom of Portfolio (§1.7) |
| **Phase 15 Marketplace Reservation** | Keep | Inline at bottom of Explorer (§1.8) |
| **ExecutionBrokerChips** | Keep | Top strip of Execution tab (§1.2) |

---

## 3. Hidden / dormant surfaces — where they belong

| Hidden surface | Recommended placement | When to activate |
|---|---|---|
| **Challenge Matching Panel** | New section `propfirm/challenge` (§1.14) | P1 — immediately when Stage 4 of post-import pipeline writes `firm_match_imported` |
| **Factory Supervisor Panel** | Mount alongside ScalingPanel in `diag/monitoring` Cluster sub-tab (stacked, not replaced) | P2 — when operator authorises `ENABLE_FACTORY_SUPERVISOR=true` |
| **Architect Dashboard** (`ArchitectDashboard.jsx` parent) | Lift 9 cards out; mount as a new tab `ai/architect` under AI Workforce module (alongside river/orch/sched) | P2 — when FS activation begins |
| **Advisor Stream** (sub-card) | Lives inside `ai/architect` once Architect mounts | with Architect |
| **Recommendation Feed** | Mount as a dedicated sub-section under `ai/architect` | with Architect |
| **Notification Center backend** | Wire `OperatorInboxDrawer` to consume `/api/factory-supervisor/notifications/*` instead of UI-only `inboxEvents.js` | when `ENABLE_NOTIFICATION_CENTER=true` |
| **Advanced Copilot** | New "v2" panel in CopilotPanel (toggle inside the existing drawer) | when `FS_ENABLE_COPILOT_ADVANCED=true` |
| **Auto Learning Panel** | Lift out of ArchitectDashboard; mount as `ai/learning` section | when `FS_ENABLE_AUTO_LEARNING=true` (FS-P1.4 hard veto release) |
| **BI5 Certification Panel** | New section `diag/bi5-cert` (mirrors `diag/bi5-health`) | After BI5 R2 lands |
| **Runner Registry Panel** | New section `exec/runners` (alongside paper/runner/live/brokers) | When multi-account or remote runners go live |
| **DSR Audit Log** | Add a sub-tab inside `governance/symbol-registry` ("Audit History") | Anytime — purely additive |
| **Activation Timeline Panel** | New section `governance/activation` | Anytime — surfaces existing `/api/latent/activation-timeline` |

---

## 4. Future capabilities — placement plan

| Future capability | Roadmap phase | Restoration placement |
|---|---|---|
| **Phase 13 Strategy Dossier Engine** | PRD §6 P2 | The 12 reservation slots inside `explorer/passport-reservations` become populated; no new tab needed |
| **Phase 14 Automated Valuation Engine** | PRD §6 P2 | The dual scorecard inside `portfolio/scorecards-reservations` becomes computed; no new tab needed |
| **Phase 15 Marketplace** | PRD §6 P2 (separate codebase) | ASF stays private; the reservation card in `explorer/marketplace-reservations` is the only ASF-side touchpoint |
| **BI5 R2 (auto-cert sweep)** | PRD §6 P0 | New `diag/bi5-cert` sub-section (see §3); plus an extra column on the existing BI5 Health table |
| **BI5 R3 (tick replay default)** | PRD §6 P0 | No new surface — flips the default `source=bi5` toggle in PaperExecution + TradeRunner |
| **cTrader Demo / Live wiring** | M2 reservation | Activates the reserved chips inside `ExecutionBrokerChips` (`exec/brokers`); no new tab |
| **Windows VPS** | M2 reservation | Activates the reserved chip; no new tab |
| **Broker Telemetry** | M2 reservation | Activates the reserved chip; optionally adds a new `exec/telemetry` sub-section |

---

## 5. The "1-vCPU feel" — quantified

What operators loved about the 1-vCPU UI:

| Quality | Old (1-vCPU) | Current (hydrated) | Restoration recommendation |
|---|---|---|---|
| Flat top-nav | 11 CORE + 6 MORE | 11 CORE + 6 MORE | ✅ Already preserved |
| One click → see the work | Yes (each tab = 1 panel render) | Mostly Yes (some tabs land on a sub-section default) | Set explicit defaults per §1 |
| Stacked-panel Dashboard | 8 panels in 1 scroll | 1 read-only briefing | **Restore** — see §1.1 |
| Workspace single-page lab | 3+9 col layout | `WorkspaceComposite` (P1.1) | ✅ Already restored |
| No drawers / overlays | None | 4 drawers (Inbox · Notification · AsfNotification · Copilot) + DangerRibbon + LifecycleRail + StatusRail + EmergencyBanner | **Keep** — these are pure-overlay additions; do not obstruct the flat-nav feel. Operators can ignore them and never notice. |
| Reservations in the way | None | 3 cards inline in Explorer + 1 in Portfolio + 1 in Execution | **Collapse** — move reservation cards to the bottom of their parent tab as a single collapsible section (§1.7, §1.8) |
| Light/Dark toggle | Both themes | Dark only (M0 lock) | Honour M0 lock (no restoration) |

---

## 6. State of this document

* Read-only restoration plan.
* Companion to `CAPABILITY_PLACEMENT_MATRIX.md`, `NAVIGATION_RECONSTRUCTION.md`, `OPERATOR_WORKFLOW_ALIGNMENT.md`, `IMPLEMENTATION_SEQUENCE.md`.
* No code modified. No surfaces mounted. No flags flipped.

**End of report.**
