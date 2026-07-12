# FINAL_NAVIGATION_MAP.md

**Status:** AS-BUILT navigation map of the restored operator UI — restoration Steps 1–7 complete (2026-06-12). This supersedes the *proposed* tree in `NAVIGATION_RECONSTRUCTION.md` §2 (which it matches, minus future-gated items).
**Verified by:** testing agent `/app/test_reports/iteration_8.json` + `iteration_9.json` (both 100%).

---

## 1. Top navigation (locked roster — verified 1:1 with old 1-vCPU navbar)

```
TOP NAV ──────────────────────────────────────────────────────────────────────
│
├── Dashboard ........................ /c/dashboard
│     ① MISSION CONTROL (DashboardComposite, restored stack — one scroll):
│        1 MissionBriefing (read-only synthesis)
│        2 GovernanceCard            3 UniverseGovernancePanel
│        4 StrategyIngestionCard     5 AutoSchedulerControl
│        6 OrchestratorPanel         7 MultiCycleRunner
│        8 AutoMutationRunner        9 StrategyDashboard
│     postures: workstation=stack · tablet=accordions · briefing=briefing-only
│
├── Execution ........................ /c/exec
│     ① Execution Overview (read-only KPI strip: Paper · Runner · Live)
│     ▸ #brokers  Broker chips (Track A/B + reserved cTrader/VPS/telemetry)
│     ▸ #paper    PaperExecution        ▸ #runner  TradeRunner
│     ▸ #live     LiveTrackingPanel
│
├── Auto Factory ..................... /c/mutate#factory-55   ① AutoFactoryPhase55
│     ▸ #auto · #cycle · #factory · #auto-select · #master-bot · #master-bot-compile
│
├── Monitoring ....................... /c/diag#monitoring     ① Runtime
│     ▸ Soak · Compute · Cluster (internal strip)
│
├── Paper Exec ....................... /c/exec#paper          ① PaperExecution
├── Trade Runner ..................... /c/exec#runner         ① TradeRunner
│
├── Portfolio ........................ /c/portfolio#builder   ① PortfolioBuilder
│     ▸ #panel · #intel
│     ⬩ #scorecards-reservations — Phase 14 accordion (collapsed)
│
├── Explorer ......................... /c/explorer#explorer   ① StrategyExplorer
│     ▸ #saved · #compare
│     ⬩ #reservations — Phase 13·14·15 + Strategy Score accordion (collapsed)
│
├── Market Data ...................... /c/diag#market-data
│     ⊤ BI5 readiness strip (READY / PARTIAL / NOT READY)
│     ① Manual (DataUpload) ▸ Automated · Archive
│
├── Auto Select ...................... /c/mutate#auto-select  ① AutoSelection
│
└── Admin (admin role) ............... /c/governance#admin
      ⊤ READINESS one-liner + "open readiness →" jump
      ① Users ▸ Flags · Realism · Tuning

MORE ▾ ───────────────────────────────────────────────────────────────────────
├── Workspace ........................ /c/lab#workspace       ① WorkspaceComposite
├── Auto Factory (Legacy) ............ /c/mutate#factory      ① AutoFactory
├── Prop Firms ....................... /c/propfirm#admin      ① PropFirmsAdmin
│     ▸ #match  FirmMatchPanel
│     ▸ #challenge  ChallengeMatchingPanel        ← surfaced in restoration
├── Live Tracking .................... /c/exec#live           ① LiveTrackingPanel
├── Optimization ..................... /c/lab#optim           ① OptimizationPanel
└── Library (N) ...................... /c/explorer#saved      ① SavedStrategies
```

## 2. Module rail / palette / deep-link surfaces (not top-nav chips)

```
├── Research Lab .......... /c/lab#{workspace,panel,analysis,backtest,cbot,optim,validate}
├── AI Workforce .......... /c/ai#{river,orch,sched}
├── Diagnostics ........... /c/diag#{readiness,parity,ingestion,ingest-src,pipeline,
│                                    market-data,bi5-health,monitoring}
└── Governance ............ /c/governance#{gov,universe,symbol-registry,rules,env,
                                           readiness,admin}
```

## 3. Overlay layer (every tab)

DangerRibbon · EmergencyBanner · LifecycleRail (10-step GPS) + StatusRail (6 chips) · CommandBar · Operator Inbox Drawer · NotificationDrawer · AsfNotificationDrawer · CopilotPanel · CommandPalette ⌘K (Modules / **Sections** / Workflow / Posture / Legacy) · ShortcutsOverlay.

## 4. Navigation behaviours (restored 1-vCPU contract)

| Behaviour | Status |
|---|---|
| CORE order locked, no role/breakpoint hiding (Admin append only) | ✅ |
| No auto-relegation CORE↔MORE | ✅ |
| Vertical wheel → horizontal scroll over the tab strip | ✅ (Step 5) |
| Active tab `scrollIntoView({inline:'center'})` on change | ✅ (Step 5) |
| MORE popover escapes scroll container | ✅ |
| Library chip live count | ✅ |
| One click → see the work (all 17 landings actionable) | ✅ |

## 5. Reserved future destinations (named, not yet mounted — by design)

`exec#runners` (multi-account runner registry) · `diag#bi5-cert` (with BI5 R2) · `governance#activation` (activation timeline, P2) · `ai#architect` + `ai#learning` (FS veto lift) · Symbol-Registry "Audit History" sub-tab (P2) · Admin Flags "Widening History" expander (P2).

**End of map.**
