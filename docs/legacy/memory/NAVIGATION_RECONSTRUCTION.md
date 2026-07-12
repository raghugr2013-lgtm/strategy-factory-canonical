# NAVIGATION_RECONSTRUCTION.md

**Audit type:** Read-only navigation blueprint. Specifies the exact navigation tree, routing scheme, default landings, and behavioural contract for the restored 1-vCPU-style operator UI — down to the file + line where each change will land *when authorized*.
**Sources:** old 1-vCPU `App.js` (🔒 NAVBAR CONFIG — LOCKED 🔒, LL 168–187), `01_TAB_ROSTER.md`, current `TopTabBar.jsx` + `modulesRegistry.js` + `router.js`, `UI_RESTORATION_MASTERPLAN.md`, `CAPABILITY_PLACEMENT_MATRIX.md`.
**Status:** Read-only. No code modified.
**Generated:** 2026-06-12

---

## 1. Verdict on the current top-nav: ALREADY CORRECT

The current `TopTabBar.jsx` (LL 50–71) reproduces the locked roster 1:1:

```
CORE  : Dashboard · Execution · Auto Factory · Monitoring · Paper Exec ·
        Trade Runner · Portfolio · Explorer · Market Data · Auto Select · [Admin]*
MORE ▾: Workspace · Auto Factory (Legacy) · Prop Firms · Live Tracking ·
        Optimization · Library (N)
```
`*` Admin appended for admin role only, never hidden, never relegated — same contract as old `App.js` L189.

**No roster changes are required.** The restoration is about what each tab *lands on*, not which tabs exist.

---

## 2. Full navigation tree (restored final state)

Notation: `①` = default landing when the tab is clicked. `▸` = sub-tab (hash drill-down). `⬩` = collapsed accordion at page bottom. `(P1/P2/P3)` = mounts later per `IMPLEMENTATION_SEQUENCE.md`. `(flag)` = mounts only when operator flips the named flag.

```
TOP NAV ──────────────────────────────────────────────────────────────────────
│
├── Dashboard ........................ /c/dashboard
│     ① RESTORED STACK (single scroll):
│        1. MissionBriefing            (keep — read-only synthesis)
│        2. GovernanceCard
│        3. UniverseGovernancePanel
│        4. StrategyIngestionCard
│        5. AutoSchedulerControl
│        6. OrchestratorPanel
│        7. MultiCycleRunner
│        8. AutoMutationRunner
│        9. StrategyDashboard
│
├── Execution ........................ /c/exec
│     ① Execution Overview composite (NEW thin panel):
│        broker chips strip · paper KPI strip · runner status row · live summary
│     ▸ #brokers  ExecutionBrokerChips (Track A/B + reserved cTrader/VPS)
│     ▸ #paper    PaperExecution
│     ▸ #runner   TradeRunner
│     ▸ #live     LiveTrackingPanel
│     ▸ #runners  RunnerRegistryPanel               (future — multi-account)
│
├── Auto Factory ..................... /c/mutate#factory-55
│     ① AutoFactoryPhase55 (1:1 old UI)
│     ▸ #auto / #cycle / #factory / #auto-select / #master-bot / #master-bot-compile
│
├── Monitoring ....................... /c/diag#monitoring
│     ① Runtime sub-tab (old Monitoring.js content)
│     ▸ Soak · Compute · Cluster (internal sub-tab strip of MonitoringSuite)
│        Cluster = ScalingPanel  [+ FactorySupervisorPanel stacked below] (P2, flag)
│
├── Paper Exec ....................... /c/exec#paper        ① PaperExecution
├── Trade Runner ..................... /c/exec#runner       ① TradeRunner
│
├── Portfolio ........................ /c/portfolio#builder
│     ① PortfolioBuilder
│     ▸ #panel   PortfolioPanel
│     ▸ #intel   PortfolioIntelligence
│     ⬩ Phase 14 Reservations (collapsed accordion at bottom)
│
├── Explorer ......................... /c/explorer#explorer
│     ① StrategyExplorer (browse)
│     ▸ #saved    SavedStrategies
│     ▸ #compare  StrategyComparison
│     ⬩ Phase 13/14/15 Reservations (single collapsed accordion at bottom:
│        StrategyScore + Phase13Dossier + Phase15Marketplace cards)
│
├── Market Data ...................... /c/diag#market-data
│     ⊤ BI5 readiness strip (1-line summary from /api/diag/bi5/health)
│     ① Manual sub-tab (DataUpload — upload control first, per old UI)
│     ▸ Automated (DataMaintenancePanel) · Archive (DataBackupPanel)
│        Manual gains "Backfill Now" button (P2)
│
├── Auto Select ...................... /c/mutate#auto-select  ① AutoSelection
│
└── Admin (admin role) ............... /c/governance#admin
      ⊤ "Readiness: GREEN · OPEN →" one-line link (jumps to governance/readiness)
      ① Users sub-tab (AdminUsers — old primary panel)
      ▸ Flags (+ Widening History expander, P2) · Realism · Tuning

MORE ▾ ───────────────────────────────────────────────────────────────────────
│
├── Workspace ........................ /c/lab#workspace      ① WorkspaceComposite (P1.1, restored)
├── Auto Factory (Legacy) ............ /c/mutate#factory     ① AutoFactory
├── Prop Firms ....................... /c/propfirm#admin
│     ① PropFirmsAdmin
│     ▸ #match      FirmMatchPanel
│     ▸ #challenge  ChallengeMatchingPanel            (P1 — first restoration mount)
├── Live Tracking .................... /c/exec#live          ① LiveTrackingPanel
├── Optimization ..................... /c/lab#optim          ① OptimizationPanel
└── Library (N) ...................... /c/explorer#saved     ① SavedStrategies

NOT IN TOP NAV (module rail / palette / deep-link only) ──────────────────────
│
├── Research Lab sections ............ /c/lab#{panel,analysis,backtest,cbot,validate}
├── AI Workforce ..................... /c/ai#{river,orch,sched}
│     ▸ #architect  ArchitectDashboard cards          (P2, FS flag)
│     ▸ #learning   AutoLearningPanel                 (P3, FS flag)
├── Diagnostics extras ............... /c/diag#{readiness,parity,ingestion,ingest-src,pipeline,bi5-health}
│     ▸ #bi5-cert   BI5 Certification panel           (with BI5 R2)
└── Governance extras ................ /c/governance#{gov,universe,symbol-registry,rules,env,readiness}
      ▸ symbol-registry gains "Audit History" sub-tab (P2)
      ▸ #activation  Activation Timeline panel        (P2)

OVERLAY LAYER (reachable from every tab) ─────────────────────────────────────
│
├── DangerRibbon (top, critical alerts)        ├── EmergencyBanner (top)
├── LifecycleRail (10-step GPS) + StatusRail   ├── CommandBar (right controls)
├── Operator Inbox Drawer (right slide)        ├── NotificationDrawer (live overlay)
├── AsfNotificationDrawer (daily digest)       ├── CopilotPanel (advisory drawer)
└── CommandPalette ⌘K + ShortcutsOverlay (modals)
```

---

## 3. Routing scheme (unchanged mechanics, explicit defaults)

| Mechanism | Today | Restored |
|---|---|---|
| Path | `/c/{moduleId}` via `router.js` pushState | unchanged |
| Section | `#hash` resolved by `resolveActiveTabId()` (`TopTabBar.jsx` L78) + scroll-into-view of `[data-testid="cmd-section-{module}-{section}"]` | unchanged |
| Tab→(module,section) map | `CORE_TABS` / `MORE_TABS` constants | unchanged — only 1 addition: nothing (Challenge Matching reachable via Prop Firms sub-tab, no top chip needed) |
| Default landing | first *visible* section of the module (implicit) | **explicit** per-tab defaults (see §2 ①) — requires only section *ordering* in `modulesRegistry.js`, no router change |

### Default-landing deltas (the actual restoration work)

| Tab | Current first render | Restored first render | Change vector |
|---|---|---|---|
| Dashboard | MissionBriefing only | MissionBriefing + 8-panel stack | New `DashboardComposite` wrapping 9 existing lazy components; replaces single `briefing` section component |
| Execution | first section = `brokers` chips only | Execution Overview composite | New thin `ExecutionOverview` component; becomes section #1 |
| Explorer | `explorer` (already correct) | unchanged | Reservation cards move into bottom accordion |
| Portfolio | `builder` (already correct) | unchanged | Phase 14 card moves into bottom accordion |
| Market Data | Manual sub-tab (already correct) | unchanged | BI5 strip added above sub-tab strip |
| Monitoring | Runtime (already correct) | unchanged | none |
| Admin | Users (already correct) | unchanged | Readiness one-liner added |
| Prop Firms | `admin` (already correct) | unchanged | `challenge` sub-tab added |
| All 1:1 tabs (Auto Factory, Paper Exec, Trade Runner, Auto Select, Workspace, Legacy Factory, Live, Optimization, Library) | already 1:1 | unchanged | none |

---

## 4. Behavioural contract (carried over from the locked old UI)

| # | Contract | Old source | Current status | Restoration action |
|---|---|---|---|---|
| 1 | CORE order locked; no role/breakpoint hiding (except Admin append) | App.js LL 150–167 | ✅ honoured in `TopTabBar.jsx` | none |
| 2 | No auto-relegation between CORE and MORE | App.js comment | ✅ static arrays | none |
| 3 | Horizontal scroll fallback + vertical-wheel hijack on narrow viewports | App.js LL 128–136 | ⚠️ `cmd-toptabs` uses CSS overflow; wheel hijack NOT ported | Port `handleNavWheel` into `TopTabBar.jsx` (P2 polish, ~15 min) |
| 4 | `scrollIntoView({inline:'center'})` on active-tab change | App.js LL 139–145 | ⚠️ not ported | Port per-tab refs + effect (P2 polish, ~15 min) |
| 5 | Admin always appended for admin users | App.js L189 | ✅ `adminOnly` filter | none |
| 6 | MORE popover escapes scroll container (fixed positioning, z-60) | NavMoreMenu.js LL 23–28 | ✅ `cmd-toptabs__menu` | none |
| 7 | Library chip shows live count | App.js L186 | ✅ `useLibraryCount()` | none |
| 8 | One click → see the work (no forced sub-navigation) | whole old App.js | ⚠️ partial | The §3 default-landing deltas close this |

---

## 5. Posture + role matrix

| Surface class | Workstation | Tablet | Briefing posture | Non-admin |
|---|---|---|---|---|
| Dashboard restored stack | full 9-panel scroll | accordion-folded (masterplan §1.1) | MissionBriefing only (read-only) | visible |
| Sub-tab strips | full | full where `only` allows | hidden (briefing modules only) | visible |
| Admin tab + governance/admin | full | per `only: ['workstation']` | hidden | **hidden** |
| Reservation accordions | collapsed by default | collapsed | hidden | visible |
| Drawers / palette / ribbons | full | full | minimal (DangerRibbon stays) | visible |

Posture mechanics (`usePosture.js`, `only:` filters in `modulesRegistry.js`) are untouched — the restoration only adds/reorders sections within the existing system.

---

## 6. Command Palette (⌘K) coverage

Every navigation target in §2 must remain palette-reachable. Additions required when each surface mounts:

| New surface | Palette entry |
|---|---|
| Prop Firms → Challenge Matching | "Challenge Matching" → `propfirm#challenge` (P1) |
| Execution Overview | "Execution Overview" → `exec` (P1) |
| BI5 Certification | "BI5 Certification" → `diag#bi5-cert` (with R2) |
| DSR Audit History | "Symbol Audit History" → `governance#symbol-registry` (P2) |
| Activation Timeline | "Activation Timeline" → `governance#activation` (P2) |
| Architect / Auto Learning | "AI Architect" / "Auto Learning" → `ai#architect` / `ai#learning` (P2/P3, flag) |
| Factory Supervisor | already palette-listed as Power-User entry — keeps working when Cluster mount lands |

---

## 7. Deep-link inventory (operator bookmarks that must never break)

All existing URLs remain valid — restoration is additive:

```
/c/dashboard                  /c/exec#paper            /c/mutate#factory-55
/c/diag#monitoring            /c/exec#runner           /c/portfolio#builder
/c/explorer#explorer          /c/diag#market-data      /c/mutate#auto-select
/c/governance#admin           /c/lab#workspace         /c/mutate#factory
/c/propfirm#admin             /c/exec#live             /c/lab#optim
/c/explorer#saved             /c/diag#bi5-health       /c/governance#symbol-registry
/c/diag#readiness             /c/governance#readiness  /c/ai#river …
```

New links added (none removed): `/c/propfirm#challenge` (P1) · `/c/diag#bi5-cert` (R2) · `/c/governance#activation` (P2) · `/c/ai#architect` (P2) · `/c/ai#learning` (P3) · `/c/exec#runners` (future).

---

## 8. Files touched per change (for the future implementation — NOT executed now)

| Change | Files | Nature |
|---|---|---|
| Dashboard stack | NEW `components/DashboardComposite.jsx`; `modulesRegistry.js` dashboard section swap | compose existing lazy components |
| Execution Overview | NEW `components/ExecutionOverview.jsx`; `modulesRegistry.js` exec section #1 | thin composite |
| Reservation accordions | `modulesRegistry.js` (explorer + portfolio section regroup) + small accordion wrapper | reorder + wrap |
| Challenge Matching | `modulesRegistry.js` 1-line section add (recipe in `MISSING_OR_HIDDEN_FEATURES.md` §2.1) | mount existing panel |
| BI5 strip + Backfill button | `MarketDataWorkbench.jsx` | additive |
| Admin readiness one-liner | `GovernanceAdminSuite.jsx` | additive |
| Nav wheel + scrollIntoView polish | `TopTabBar.jsx` | port old a11y helpers |
| Orphan retirement | delete 9 files + rehouse `ArchitectDashboard.jsx` children | janitorial |

**No file in `backend/` is touched by any navigation change. No feature flag is flipped by any navigation change.**

---

## 9. State of this document

* Read-only blueprint — companion to `UI_RESTORATION_MASTERPLAN.md`, `CAPABILITY_PLACEMENT_MATRIX.md`, `OPERATOR_WORKFLOW_ALIGNMENT.md`, `IMPLEMENTATION_SEQUENCE.md`.
* No code modified. No surfaces mounted. No flags flipped.

**End of report.**
