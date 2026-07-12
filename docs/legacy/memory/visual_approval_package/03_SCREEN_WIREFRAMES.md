# 03 · Screen Wireframes

> ASCII wireframes for the 11 CORE + 6 MORE + Workspace screens.
> Layout grids match the old 1-vCPU `src/App.js` (composition) and `src/index.css` (geometry).
> Annotations note where NEW capabilities fold in.

---

## TOPBAR (every screen)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⚡ AI Strategy Factory  [v10]   ●Dashboard │ Execution │ Auto Factory │ Monitoring │ Paper Exec     │
│                                  Trade Runner │ Portfolio │ Explorer │ Market Data │ Auto Select   │
│                                  Admin │ More ▾                                                    │
│                                                       [Trader] [☾Theme] [↕Density] [admin@…] [⎋ Sign out]  ● Online │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Status rail (bottom, every screen):

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ orch:idle · ingest:ok · sched:on · llm:off · gov:ok · kill:OK            ⌘K  ⌘J  ⌘⌥N  ⌘.  ?       │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-01 · DASHBOARD (`tab=dashboard`)

> Composition matches old `App.js` LL 286–296 verbatim, with three NEW capability cards inserted (deployment readiness · ingestion health · parity certification) above the legacy stack, and a live `PipelineLogsPanel` strip at the bottom.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ┌── GOVERNANCE BAR ─────────────────────────────────────┐  ┌── NEW ──────────────┐  │
│  │  Universe: 7 symbols  · Routing: round-robin · Lock 🔒│  │ DeploymentReadiness │  │
│  │  Pending widening: 0 · Approved: 12 · Last sweep: ✓   │  │  • R6.6 pass  ✓     │  │
│  └───────────────────────────────────────────────────────┘  │  • R6.7 pass  ✓     │  │
│                                                              │  • R6.9 pass  ✓     │  │
│  ┌── UNIVERSE GOVERNANCE ────────────────────────────────┐  └─────────────────────┘  │
│  │  EURUSD GBPUSD USDJPY XAUUSD AUDUSD USDCAD USDCHF      │  ┌── NEW ──────────────┐ │
│  │   [enabled]   [enabled]   [enabled]   [enabled]   …    │  │ IngestionHealthCard │ │
│  └────────────────────────────────────────────────────────┘  │  • BID: 104,389 ✓   │ │
│                                                              │  • BI5: 0       ✗   │ │
│  ┌── STRATEGY INGESTION ─────────────────────────────────┐  │  • spread: 0    ✗   │ │
│  │  Sources: 3 · Queued: 7 · Validated: 42 · Last run: …  │  └─────────────────────┘ │
│  └────────────────────────────────────────────────────────┘  ┌── NEW ──────────────┐ │
│                                                              │ ParityCertCard       │ │
│  ┌── AUTO SCHEDULER CONTROL ─────────────────────────────┐  │ HTF: ✓  Trade: ✓     │ │
│  │  Status: ● ON  · Cadence: 15 min · Next: 03:47 UTC     │  │ Cert window: …       │ │
│  │  [Start] [Stop] [Run now] [View logs]                  │  └─────────────────────┘ │
│  └────────────────────────────────────────────────────────┘                          │
│                                                                                       │
│  ┌── ORCHESTRATOR ───────────────────────────────────────┐                          │
│  │  Heartbeat: 02:13s ago · Leader: factory-runner-A     │                          │
│  │  Generation: ● · Validation: ● · Selection: ●         │                          │
│  └────────────────────────────────────────────────────────┘                          │
│                                                                                       │
│  ┌── MULTI-CYCLE RUNNER ─────────────────────────────────┐                          │
│  │  Cycle 4 / 12 · Survivors: 18 · Promoted: 3            │                          │
│  │  [Promote selected] [Reset] [Settings]                 │                          │
│  └────────────────────────────────────────────────────────┘                          │
│                                                                                       │
│  ┌── AUTO MUTATION RUNNER ───────────────────────────────┐                          │
│  │  Default pair: EURUSD · TF: H1 · Pool: 64              │                          │
│  └────────────────────────────────────────────────────────┘                          │
│                                                                                       │
│  ┌── STRATEGY DASHBOARD (table) ─────────────────────────────────────────────────┐  │
│  │ ID    PAIR   TF    PF     WIN%   TRADES  SHARPE  STATUS         AGE    ▸     │  │
│  │ s_021 EURUSD H1    1.41   58.2%  742     1.32    deployment_ok  3d     ▸     │  │
│  │ s_011 GBPUSD M15   1.28   55.4%  1188    1.07    portfolio_w.   1d     ▸     │  │
│  │ …                                                                              │  │
│  └────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                       │
│  ┌── PIPELINE LOG TAIL (NEW) ────────────────────────────────────────────────────┐  │
│  │ 03:42:11  ✓  ingest_runner  GBPUSD M15 → 144 new bars                          │  │
│  │ 03:42:09  ✓  scheduler      bi5_track tick                                     │  │
│  │ 03:41:58  ✓  validator      s_021 → htf_parity PASS                            │  │
│  └────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-02 · EXECUTION (`tab=execution`) — 3-step flow

> ExecutionDashboard.js (phase9) — preserved exactly. The hero of the workstation.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ┌─① Generate──┐ ━━━━ ┌─② Allocate─┐ ━━━━ ┌─③ Execute──┐                            │
│  │ Auto Factory│      │ Portfolio  │      │ Live Exec  │                            │
│  └─────────────┘      └────────────┘      └────────────┘                            │
│                                                                                       │
│  ┌── AUTO FACTORY CARD ──────────────────────────────────────────────────────────┐  │
│  │  Run: [Start ▶]  Cancel: [✕]                                                    │  │
│  │  Cycles:  ████████░░  4/12                                                      │  │
│  │  Survivors: 18 · Pool: 64 · CPU: 78%                                            │  │
│  │  Recent: s_021 PF=1.41  win=58.2  →  promoted                                   │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                       │
│  ┌── PORTFOLIO BUILDER CARD ────────────────────────────────────────────────────┐    │
│  │  Selected: 6 strategies · Avg PF: 1.34 · Combined Sharpe: 1.18                │    │
│  │  [Build bundle]  [Inspect]  [Export]                                          │    │
│  └───────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                       │
│  ┌── LIVE EXECUTION CARD ───────────────────────────────────────────────────────┐    │
│  │  Status: ● running · Account: paper-001 · Equity: 10,247.31  +247.31 (2.5%)  │    │
│  │  Open positions: 3 · Today's PnL: +47.20                                      │    │
│  │  [▶ Resume]  [⏸ Pause]  [⏹ Stop]                                              │    │
│  └───────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-03 · AUTO FACTORY (`tab=auto-factory`)

> AutoFactoryPhase55 + (NEW collapsed) MasterBotCompilePanel below.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  AUTO FACTORY · PHASE 55         [Settings ⚙]                                          │
│  ──────────────────────────────────────────────────                                    │
│  Cohort: alpha-2026-06 · Strategies in flight: 12 · Selection budget: 24h             │
│                                                                                        │
│  ┌── COHORT KPI TILES (6-up grid, 12px gap) ──────────────────────────────────────┐  │
│  │ ┌─PF─────┐ ┌─WIN%───┐ ┌─SHARPE─┐ ┌─MAR──┐ ┌─DEPLOY─┐ ┌─REJECTED─┐              │  │
│  │ │ 1.41   │ │ 58.2%  │ │ 1.32   │ │ 22.4 │ │ 7      │ │ 31       │              │  │
│  │ │ avg    │ │ avg    │ │ avg    │ │ avg  │ │ this w.│ │ this w.  │              │  │
│  │ └────────┘ └────────┘ └────────┘ └──────┘ └────────┘ └──────────┘              │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                        │
│  ┌── COHORT TABLE (dense, sticky-header) ────────────────────────────────────────┐    │
│  │ ID      PAIR   TF   GEN  PF    WIN%  SHARPE  STATUS         ACTIONS            │    │
│  │ s_021α  EURUSD H1   3    1.41  58.2  1.32   deployment_ok  [view] [reject]    │    │
│  │ s_011α  GBPUSD M15  3    1.28  55.4  1.07   portfolio_w    [view] [reject]    │    │
│  │ …                                                                              │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ▶ Master Bot Compile (collapsed accordion — click to expand)                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-04 · MONITORING (`tab=monitoring`) — 4 sub-tabs

> Folds in NEW: Soak · CPU pool · Scaling · Factory Supervisor. Sub-bar matches the existing `MonitoringSuite.jsx` composite. Default sub-tab: **Runtime**.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  MONITORING & CONTROL                                                                  │
│  ── Runtime · Soak · Compute · Cluster ──                                              │
│                                                                                        │
│  [Runtime] (active gold-underline)                                                     │
│                                                                                        │
│  ┌── RUNTIME STATE ──────────────────────────────────────────────────────────────┐    │
│  │  Orchestrator: ● healthy   Scheduler: ● on   LLM: ○ off                        │    │
│  │  Ingest: ● ok (last 17s)   Validator: ● ok   Selector: ● ok                    │    │
│  │  [Restart scheduler] [Drain queue] [Kill switch (admin only)]                  │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── ALERT STREAM ────────────────────────────────────────────────────────────────┐    │
│  │ 03:42:11 INFO   ingest_runner GBPUSD M15 → 144 new bars                         │    │
│  │ 03:41:58 INFO   validator s_021 → htf_parity PASS                               │    │
│  │ 03:40:14 WARN   queue_pressure_p95 = 1.8s (threshold 2.0s)                      │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── KPI TILE STRIP (8-up) ──────────────────────────────────────────────────────┐    │
│  │ uptime  CPU%  RSS  in/sec  out/sec  queue  errors  alerts                      │    │
│  │ 14:22h  47%   1.8G 12.4    11.7     3      0       0                            │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Sub-tab variations (only the content area changes):
* **Soak** → SoakDiagnosticsPanel (R0/R5 evidence table + windows)
* **Compute** → CpuPoolStatePanel (worker count, queue, throughput)
* **Cluster** → ScalingPanel + FactorySupervisorPanel (leader, fleet, NC)

---

## S-05 · PAPER EXEC (`tab=paper-exec`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  PAPER EXECUTION · BID / BI5 replay                                                    │
│  Strategy: [s_021 EURUSD H1 ▼]   Window: [2025-01-01 → 2025-06-30]   Source: ●BID ○BI5│
│  [Run replay ▶]   [Cancel]                                                             │
│                                                                                        │
│  ┌── KPI TILES (6-up) ───────────────────────────────────────────────────────────┐    │
│  │ PF  WIN%  TRADES  AVG-PnL  MAX-DD  SLIPPAGE-BPS                                 │    │
│  │ 1.34 56.1 312     +12.4    -47.10  4.1                                          │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── EQUITY CURVE (chart) ───────────────────────────────────────────────────────┐    │
│  │   ▁▂▂▃▃▄▄▅▅▅▆▆▇▇█████                                                          │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── TRADE LEDGER (table, sticky header, 28px rows) ────────────────────────────┐    │
│  │ #   TS               SIDE  ENTRY    EXIT     SIZE   PnL      DUR    NOTES      │    │
│  │ 1   2025-01-02 09:15 long  1.0432   1.0451   0.10   +19.00   1h22m  TP         │    │
│  │ 2   2025-01-02 10:48 short 1.0455   1.0438   0.10   +17.00   38m    TP         │    │
│  │ …                                                                              │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-06 · TRADE RUNNER (`tab=trade-runner`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  TRADE RUNNER · live paper / live broker                                               │
│  Account: [paper-001 ▼]   Mode: ●Paper ○Live   Equity: 10,247.31  +247.31 (2.5%)      │
│  [Start ▶]  [Pause ⏸]  [Stop ⏹]  [Flatten all positions]                              │
│                                                                                        │
│  ┌── OPEN POSITIONS ────────────────────────────────────────────────────────────┐    │
│  │ #   SYM    SIDE  SIZE  ENTRY    NOW       UNREAL    DUR     CLOSE             │    │
│  │ 1   EURUSD long  0.10  1.0432   1.0447    +15.00    14m     [✕]               │    │
│  │ 2   GBPUSD short 0.10  1.2611   1.2607    + 4.00    2m      [✕]               │    │
│  │ 3   XAUUSD long  0.01  2018.41  2020.10   +16.90    32m     [✕]               │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── TODAY'S ACTIVITY ───────────────────────────────────────────────────────────┐    │
│  │ #   TS         SYM    SIDE  PnL     STATUS                                     │    │
│  │ 12  09:15      EURUSD long  +19.00  closed-TP                                  │    │
│  │ 11  09:08      GBPUSD short +17.00  closed-TP                                  │    │
│  │ …                                                                              │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── KPI STRIP ─────────────────────────────────────────────────────────────────┐    │
│  │ TodayPnL  WeekPnL  MonthPnL  WinRate  MaxDD  Sharpe                            │    │
│  │ +47.20    +312.50  +812.40   58.3%    -47.10 1.32                              │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-07 · PORTFOLIO (`tab=portfolio-builder`) — 2 sub-tabs

> Sub-bar: **Builder** (default) · **Panel & Intelligence** (PortfolioPanel + PortfolioIntelligence).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO · Builder · Panel & Intelligence                                            │
│  [Builder] (active gold-underline)                                                     │
│                                                                                        │
│  ┌── CANDIDATES (sticky-header table) ───────────────────────────────────────────┐    │
│  │ ☑ ID     PAIR   TF   PF    SHARPE  CORR_TO_SELECTED                            │    │
│  │ ☑ s_021  EURUSD H1   1.41  1.32    ─                                           │    │
│  │ ☑ s_011  GBPUSD M15  1.28  1.07    0.14                                        │    │
│  │ ☐ s_044  USDJPY H4   1.18  0.94    0.32                                        │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── SELECTED BUNDLE ───────────────────────────────────────────────────────────┐    │
│  │ s_021  EURUSD H1  alloc 35%  ━━━━━━━━━━━━░░░░░░░░░░░  weight: 0.35            │    │
│  │ s_011  GBPUSD M15 alloc 25%  ━━━━━━━━░░░░░░░░░░░░░░░░  weight: 0.25            │    │
│  │ s_044  USDJPY H4  alloc 40%  ━━━━━━━━━━━━━━━━░░░░░░░░  weight: 0.40            │    │
│  │ ───────────────────────────────────────────────────────────────────────────    │    │
│  │ Bundle PF: 1.34   Combined Sharpe: 1.18   Max correlation: 0.32                │    │
│  │ [Build]  [Save as portfolio]  [Promote]                                        │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-08 · EXPLORER (`tab=explorer`) — Strategy Memory + Deep Dive

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  STRATEGY EXPLORER · Memory                                                            │
│  [Filter pair ▼]  [TF ▼]  [Status ▼]  [Search…]                  Saved: 142          │
│                                                                                        │
│  ┌────────────────────────────────────────────────────┐  ┌── DEEP DIVE (right pane) ─┐│
│  │ ☑ s_021  EURUSD H1  PF 1.41  deployment_ok  3d     │  │ s_021 EURUSD H1            ││
│  │ ☐ s_011  GBPUSD M15 PF 1.28  portfolio_w    1d     │  │ ──────────────────────     ││
│  │ ☐ s_044  USDJPY H4  PF 1.18  validated      8h     │  │ Lineage: parent s_018      ││
│  │ ☐ s_032  XAUUSD M15 PF 1.55  validated      4h     │  │  • mutation: take_profit↑  ││
│  │ ☐ s_017  AUDUSD H1  PF 0.98  rejected       2d     │  │  • generation 3            ││
│  │ ☐ …                                                  │  │                            ││
│  │                                                      │  │ Backtest summary:          ││
│  │                                                      │  │  PF 1.41 · WIN 58.2%       ││
│  │                                                      │  │  trades 742 · Sharpe 1.32  ││
│  │                                                      │  │                            ││
│  │                                                      │  │ Description:               ││
│  │                                                      │  │ • Trend-following MA cross ││
│  │                                                      │  │   with ATR-scaled stops    ││
│  │                                                      │  │                            ││
│  │                                                      │  │ [View details ▸ Drawer]    ││
│  └──────────────────────────────────────────────────────┘  └────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────────────┘
```

`[View details ▸ Drawer]` opens **`AsfDetailDrawer`** as a global right-side overlay with the full StrategyDetailsPanel.

---

## S-09 · MARKET DATA (`tab=data`) — 3 sub-tabs

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  MARKET DATA                                                                            │
│  [Manual] [Automated] [Archive]                                                         │
│                                                                                        │
│  [Manual] (active gold-underline)                                                       │
│  ┌── DATAUPLOAD COMPONENT ──────────────────────────────────────────────────────┐    │
│  │ Source: ●BID ○BI5 ○CSV ○ServerImport                                          │    │
│  │ Pairs: [EURUSD ▼]   TFs: ☑ M1 ☑ M5 ☑ M15 ☑ H1 ☑ H4 ☑ D1                       │    │
│  │ Date range: [2024-01-01] → [2025-12-31]                                       │    │
│  │ [Download ▶]   [Cancel]                                                       │    │
│  │ ──────────────────────────────────────────                                    │    │
│  │ Progress:  ████████████░░░░░  62%   (EURUSD H1 1242/2003)                     │    │
│  │ Last gap-fix: 2025-12-15 03:00 — fixed 14 gaps                                 │    │
│  │ [Check gaps]  [Fix gaps]                                                       │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                        │
│  ┌── DATA AVAILABILITY (NEW grid) ──────────────────────────────────────────────┐    │
│  │  PAIR     M1    M5    M15   H1    H4    D1     COVERAGE                       │    │
│  │  EURUSD   ✓     ✓     ✓     ✓     ✓     ✓      ━━━━━━━━━━ 100%                │    │
│  │  GBPUSD   ✓     ✓     ✓     ✓     ✓     ✓      ━━━━━━━━━━ 100%                │    │
│  │  USDJPY   ─     ─     ─     ✓     ✓     ✓      ━━━━━━░░░░ 60%                 │    │
│  │  XAUUSD   ─     ─     ─     ✓     ✓     ✓      ━━━━━━░░░░ 60%                 │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

`Automated` sub-tab → DataMaintenancePanel (scheduler view).
`Archive` sub-tab → DataBackupPanel.

---

## S-10 · AUTO SELECT (`tab=auto-select`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  AUTO SELECT · deployment picker                                                        │
│  Pool: 142 candidates · Filter: [Status ▼ portfolio_w] · Window: [last 30 d]          │
│                                                                                        │
│  ┌── RANKED TABLE (sticky header, 28px rows) ─────────────────────────────────┐      │
│  │ RANK  ID     PAIR   TF   PF    WIN%   SHARPE  CORR   PASS-P  PICK           │      │
│  │ 1     s_021  EURUSD H1   1.41  58.2%  1.32    0.32   0.81    ☑              │      │
│  │ 2     s_011  GBPUSD M15  1.28  55.4%  1.07    0.18   0.74    ☑              │      │
│  │ 3     s_044  USDJPY H4   1.18  53.7%  0.94    0.41   0.62    ☐              │      │
│  │ …                                                                            │      │
│  └──────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                        │
│  ┌── SELECTION KPIs ──────────────────────────────────────────────────────────┐      │
│  │ Selected: 2 / N  · Sum-weight: 60% · Diversity: 0.31 · Expected Sharpe: 1.20│      │
│  │ [Promote selection] [Reset]                                                  │      │
│  └──────────────────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-11 · ADMIN (`tab=admin-users`, admin role only) — 5 sub-tabs

> Composes ReadinessPanel + AdminUsers (old) plus the four NEW governance panels. Default sub-tab: **Users**.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  ADMIN                                                                                  │
│  [Users] [Flags] [Realism] [Tuning] [Rules]                                            │
│                                                                                        │
│  [Users] (active gold-underline)                                                       │
│  ┌── READINESS PANEL (always pinned top) ───────────────────────────────────────┐    │
│  │ Backend: ● healthy   API: ● 200 OK   Mongo: ● 104,389 docs                    │    │
│  │ Auth: ● Bearer attached 48/49   Scheduler: ● on   Pool: ● 4 workers           │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
│  ┌── ADMIN USERS ─────────────────────────────────────────────────────────────┐      │
│  │  EMAIL                            ROLE     CREATED         ACTIONS           │      │
│  │  admin@strategyfactory.dev       admin    2025-12-01     [reset pw]         │      │
│  │  operator@strategyfactory.dev    user     2026-01-14     [reset] [revoke]   │      │
│  │  [+ Add user]                                                                │      │
│  └──────────────────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Sub-tab variations:
* **Flags** → AdminFlagGovernancePanel (feature-flag table · enable/disable).
* **Realism** → AdminExecutionRealismPanel (slippage / latency defaults per symbol).
* **Tuning** → Phase12TuningPanel (Master Bot ranker weights).
* **Rules** → RulesReviewPanel (PropFirm rule sets · pinned reference docs).

---

## S-12 · WORKSPACE (`More ▾ → workspace`) — 3/9 column grid

> Verbatim from old `App.js` LL 305–360.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  WORKSPACE · individual strategy lab                                                    │
│  ┌── LEFT (3 cols) ─────┐  ┌── RIGHT (9 cols) ────────────────────────────────────┐  │
│  │  STRATEGY PANEL      │  │ BACKTEST PANEL                                        │  │
│  │  - prompt            │  │  PF · WIN% · Sharpe · MaxDD                           │  │
│  │  - generate          │  │  Equity curve                                          │  │
│  │  - pair / TF         │  │  Trade ledger                                          │  │
│  │  ─────────────       │  │  [Save to library]  [Run backtest]                    │  │
│  │  STRATEGY ANALYSIS   │  ├───────────────────────────────────────────────────────┤  │
│  │  - profiler          │  │ STRATEGY DESCRIPTION (auto-narrated)                  │  │
│  │  - distribution      │  ├───────────────────────────────────────────────────────┤  │
│  │  - regime fit        │  │ CBOT PANEL  (codegen · compile · download)            │  │
│  │                      │  ├───────────────────────────────────────────────────────┤  │
│  │                      │  │ ┌── OPTIMIZATION ──┐  ┌── VALIDATION ──┐              │  │
│  │                      │  │ │ search grid       │  │ walk-forward    │              │  │
│  │                      │  │ │ Pareto front      │  │ OOS holdout     │              │  │
│  │                      │  │ │ best params       │  │ Monte Carlo     │              │  │
│  │                      │  │ └───────────────────┘  └─────────────────┘              │  │
│  │                      │  ├───────────────────────────────────────────────────────┤  │
│  │                      │  │ STRATEGY COMPARISON (when ranked ≥ 1)                  │  │
│  └──────────────────────┘  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## S-13 · AUTO FACTORY (Legacy) (`More ▾ → pipeline`)

Renders the original `AutoFactory.js` component (no composition changes). Provided as a fallback / legacy reference path.

## S-14 · PROP FIRMS (`More ▾ → prop-firms`)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  PROP FIRMS                                                                             │
│  [Admin] [Match] [Challenge]                                                            │
│                                                                                        │
│  [Admin] (active)                                                                       │
│  ┌── FIRM CATALOGUE ─────────────────────────────────────────────────────────────┐    │
│  │ FIRM            ACCOUNT    LEVERAGE  DD%   RULES SET           DOCS            │    │
│  │ FTMO            100k      1:30      5/10  ftmo-v3              [pdf]           │    │
│  │ MyForexFunds    50k       1:50      6/12  mff-v2               [pdf]           │    │
│  │ The5%ers        25k       1:30      4/8   5pct-v1              [pdf]           │    │
│  │ [+ Add firm]                                                                    │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Sub-tabs:
* **Match** → FirmMatchPanel (filter portfolio against firm rules).
* **Challenge** → ChallengeMatching (challenge-phase simulator).

## S-15 · LIVE TRACKING (`More ▾ → live`)

LiveTrackingPanel — live positions feed across deployed master bots. Single panel, no sub-tabs.

## S-16 · OPTIMIZATION (`More ▾ → optimization`)

Optimization (standalone, full-screen) — search & Pareto front for any saved strategy. Single panel.

## S-17 · LIBRARY (`More ▾ → saved`)

SavedStrategies — all saved-to-library strategies with quick filter + bulk delete. Counter `(N)` on the More menu reflects this.

— End of WIREFRAMES —
