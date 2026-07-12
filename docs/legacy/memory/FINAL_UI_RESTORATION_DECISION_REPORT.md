# FINAL_UI_RESTORATION_DECISION_REPORT.md

**Document class:** Executive decision report — the final consolidation gate before any implementation authorisation.
**Consolidates:** `UI_RESTORATION_MASTERPLAN.md` · `CAPABILITY_PLACEMENT_MATRIX.md` · `NAVIGATION_RECONSTRUCTION.md` · `OPERATOR_WORKFLOW_ALIGNMENT.md` · `IMPLEMENTATION_SEQUENCE.md` · `CAPABILITY_CATALOG.md` · `ROADMAP_RECONCILIATION.md`
**Status:** Read-only. No code modified. No surfaces mounted. No imports run. No feature flags flipped.
**Generated:** 2026-06-12

---

# 1. Executive summary

## 1.1 Current state

- **Backend:** 159 catalogued capabilities — ~100 Active, 6 UI-class Hidden, ~22 flag-gated Dormant, 5 Placeholder, 10 Orphan files, 0 Dead. 85 routers mounted, 89 feature flags (1 ON: `ENABLE_DYNAMIC_MARKET_UNIVERSE`). Factory Supervisor stack (22 engines, ~40 endpoints) dormant under the FS-P1.4 hard veto.
- **Frontend:** The hydrated COMMAND shell already carries the **locked 11 CORE + 6 MORE + Admin roster 1:1** from the old 1-vCPU navbar. 57 registry sections across 10 modules; 4 drawers, ribbons, rails, palette overlays — all new since 1-vCPU and all functioning.
- **The gap is not capability — it is landing experience.** Six workflow regressions exist versus the 1-vCPU UI (`OPERATOR_WORKFLOW_ALIGNMENT.md` §3):

| # | Regression | Severity |
|---|---|---|
| R-1 | Dashboard lost its 8 actionable stacked panels (read-only MissionBriefing only) | **HIGH** |
| R-2 | Challenge-template drill-down requires raw curl (panel exists, unmounted) | MEDIUM |
| R-3 | "Is data ready?" needs a second tab visit (BI5 health lives elsewhere) | LOW |
| R-4 | Reservation cards interrupt Explorer/Portfolio browse scroll | LOW |
| R-5 | Execution tab lands on broker chips only — no one-glance status | LOW |
| R-6 | Old nav a11y helpers (wheel hijack, scrollIntoView) not ported | COSMETIC |

## 1.2 Target state

The restored UI keeps the locked flat top-nav and re-establishes the 1-vCPU principle **"one click → see the work"**:

- **Dashboard** = MissionBriefing on top + the original 8-panel actionable stack below it, in one scroll.
- **Every CORE tab** lands on actionable content by default; sub-tabs become drill-down filters, never mandatory steps.
- **Challenge Matching** mounts at `propfirm#challenge` (the only Hidden→Visible promotion).
- **Reservation cards** (Phase 13/14/15, Strategy Score, Phase 14 scorecards) collapse into bottom accordions — present but out of the daily path.
- **All new-era surfaces stay**: LifecycleRail, StatusRail, DangerRibbon, 4 drawers, ⌘K palette, Monitoring 4-pane, Market Data 3-tab, BI5 Health, DSR Symbol Registry, Master Bot.
- **Nothing dormant activates.** FS veto, all 88 OFF flags, and the import gate remain untouched.

## 1.3 Benefits

1. **Closes all 6 workflow regressions** — including R-1, which affects the single most-used operator surface.
2. **Zero capability loss** — `CAPABILITY_PLACEMENT_MATRIX.md` roll-up: every one of 159 capabilities has a named final home (95 STAYS · 13 MOVES · 25 SURFACES-on-decree · 9 RESERVED · 10 RETIRES with mounted replacements).
3. **Better import experience** — Stage 4 (Re-Match) of the future post-import pipeline becomes fully drillable in-UI before the import is ever run.
4. **Cheap and reversible** — ~9–11 h, 100% frontend composition; the single biggest change (Dashboard) is a 1-line registry swap wrapping 9 existing components, revertible in seconds.
5. **Janitorial debt cleared** — 9 dead orphan files retired; codebase matches documentation.
6. **No future redesign debt created** — Phase 13/14/15 land into pre-booked, zero-reflow reservation slots (see §9).

## 1.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dashboard stack page-weight / jank (9 lazy panels, StrategyDashboard ≈ 2.4k LOC) | Medium | Medium | Keep `React.lazy` + Suspense skeletons; intersection-observer mount for below-fold panels if profiling shows jank; tablet accordions |
| ~8 simultaneous API calls on Dashboard mount | Medium | Low | All endpoints exist, auth-gated, read-only GETs; same load the old 1-vCPU UI carried |
| Accidental change to M2-locked reservation card visuals | Low | Medium | Accordion is a pure wrapper; card internals untouched (explicit step constraint) |
| Wheel-hijack capturing scroll outside the tab strip | Low | Low | Port the old guard exactly (only hijack when pointer over strip and overflow exists) |
| Orphan deletion removing something secretly referenced | Very low | Medium | Zero importers verified twice (catalog §11 + parity audit); `yarn build` is the proof gate; quarantine option to `_inventory/` |
| Scope creep into flags / backend / import | — | High | Hard rule in every step: frontend-only, no `.env`, no flags, GATE 3 untouched |

**Net risk posture: LOW.** No step touches the backend, persistence, flags, or the import pathway.

---

# 2. Before vs After navigation tree

## 2.1 Current hydrated UI (BEFORE)

```
TOP NAV (locked roster — already 1:1 with old 1-vCPU)
├── Dashboard ............ MissionBriefing ONLY (read-only synthesis)        ← R-1
├── Execution ............ lands on Broker Chips strip only                  ← R-5
│     #brokers · #paper · #runner · #live
├── Auto Factory ......... AutoFactoryPhase55 ✅ (1:1)
├── Monitoring ........... Runtime ✅ ▸ Soak · Compute · Cluster(Scaling)
├── Paper Exec ........... PaperExecution ✅ (1:1)
├── Trade Runner ......... TradeRunner ✅ (1:1)
├── Portfolio ............ Builder ✅ ▸ #panel · #intel
│                          + Phase 14 reservation card INLINE in scroll      ← R-4
├── Explorer ............. Browse ✅ ▸ #saved · #compare
│                          + 3 reservation cards INLINE in scroll            ← R-4
├── Market Data .......... Manual ✅ ▸ Automated · Archive
│                          (BI5 readiness lives in separate diag tab)        ← R-3
├── Auto Select .......... AutoSelection ✅ (1:1)
└── Admin* ............... Users ✅ ▸ Flags · Realism · Tuning
                           (Readiness split off to Governance)
MORE ▾
├── Workspace ............ WorkspaceComposite ✅ (P1.1 restored, 1:1)
├── Auto Factory (Legacy)  AutoFactory ✅ (1:1)
├── Prop Firms ........... Admin ✅ ▸ #match   — Challenge = CURL ONLY       ← R-2
├── Live Tracking ........ LiveTrackingPanel ✅ (1:1)
├── Optimization ......... OptimizationPanel ✅
└── Library (N) .......... SavedStrategies ✅ (count badge live)
OVERLAYS (new since 1-vCPU — all functioning)
└── LifecycleRail · StatusRail · DangerRibbon · EmergencyBanner ·
    Inbox / Notification / AsfNotification / Copilot drawers · ⌘K · Shortcuts
NAV BEHAVIOUR: wheel-hijack + active-tab scrollIntoView NOT ported            ← R-6
```

## 2.2 Proposed restored UI (AFTER)

```
TOP NAV (roster unchanged — locked)
├── Dashboard ............ RESTORED STACK (one scroll):
│     MissionBriefing → GovernanceCard → UniverseGovernance →
│     StrategyIngestion → AutoScheduler → Orchestrator →
│     MultiCycleRunner → AutoMutationRunner → StrategyDashboard      [fixes R-1]
├── Execution ............ NEW Execution Overview composite
│     (chips + paper KPIs + runner status + live summary)            [fixes R-5]
│     ▸ #brokers · #paper · #runner · #live  (· #runners future)
├── Auto Factory ......... unchanged ✅
├── Monitoring ........... unchanged ✅ (Cluster gains FS panel ONLY on veto lift)
├── Paper Exec ........... unchanged ✅
├── Trade Runner ......... unchanged ✅
├── Portfolio ............ Builder ▸ #panel · #intel
│     ⬩ Phase 14 Reservations — COLLAPSED accordion at bottom        [fixes R-4]
├── Explorer ............. Browse ▸ #saved · #compare
│     ⬩ Phase 13/14/15 Reservations — single COLLAPSED accordion     [fixes R-4]
├── Market Data .......... ⊤ BI5 readiness strip (1-line)            [fixes R-3]
│     Manual ▸ Automated · Archive   (+ "Backfill Now" button, P2)
├── Auto Select .......... unchanged ✅
└── Admin* ............... ⊤ "Readiness: GREEN · OPEN →" one-liner
      Users ▸ Flags(+History expander P2) · Realism · Tuning
MORE ▾
├── Workspace ............ unchanged ✅
├── Auto Factory (Legacy)  unchanged ✅
├── Prop Firms ........... Admin ▸ #match ▸ #challenge (MOUNTED)     [fixes R-2]
├── Live Tracking ........ unchanged ✅
├── Optimization ......... unchanged ✅ (506-LOC orphan retired)
└── Library (N) .......... unchanged ✅
OVERLAYS ................. all kept, unchanged
NAV BEHAVIOUR ............ wheel-hijack + scrollIntoView ported      [fixes R-6]
DEEP LINKS ............... all existing URLs preserved; only additions
```

---

# 3. Every capability placement (consolidated census)

Full per-item detail lives in `CAPABILITY_PLACEMENT_MATRIX.md`; this is the decision-level census of all 159 catalogued capabilities.

## 3.1 ACTIVE today (~100) — placement after restoration

| Group | Count | Placement |
|---|---|---|
| Pipeline engines (mutation, validation, ranking, IR, memory, lifecycle, backtest, optimization, codegen…) | ~35 | Engine-only by design — consumed by mounted surfaces; **no change** |
| Market-data engines (BID/BI5 ingest, aggregator, gap, spread, calendar, regime…) | ~18 | Engine-only; ingest UI at Market Data tab; **BI5 strip added on top** |
| Mounted operator panels (Factory, Mutate, Lab, Explorer, Portfolio, Exec, PropFirm, Monitoring, Governance, AI, Diag) | ~35 | **Stay at their homes**; 8 of them additionally dual-mount into the restored Dashboard stack |
| Shell overlays + design system (rails, ribbons, drawers, palette, ui-asf, shadcn) | ~15 | **Stay unchanged** |

## 3.2 HIDDEN today (6 UI-class) — what happens to each

| Capability | After restoration |
|---|---|
| **Challenge Matching Panel** | **BECOMES VISIBLE** at `propfirm#challenge` (the only promotion) |
| Factory Supervisor Panel | Stays hidden — mounts in Monitoring▸Cluster only on FS veto lift (P2) |
| Architect Dashboard (9 cards) | Stays hidden — rehouses to `ai#architect` only on FS veto lift (P2) |
| Recommendation Feed | Stays hidden — inside future `ai#architect` |
| Auto Learning Panel | Stays hidden — lifts to `ai#learning` only when `FS_ENABLE_AUTO_LEARNING=true` (P3) |
| Notification Center (backend ×6 endpoints) | Stays dormant — Inbox drawer rewires to it only when `ENABLE_NOTIFICATION_CENTER=true` |
| *(API-only, no panel class)* BI5 Certification · Runner Registry · Factory Runner Heartbeat · FS Scheduler control · DSR Audit Log · Activation Timeline · Widening History | Stay API-only — each has a named future slot (`diag#bi5-cert`, `exec#runners`, Cluster rows, Symbol-Registry sub-tab, `governance#activation`, Flags expander); mounted on the listed triggers, not during restoration |

## 3.3 DORMANT today (~22 flag-gated) — none activate

All ~22 flag-gated engines (FS worker/queue/routing/heartbeat/fleet/eligibility/FAG/telemetry, Copilot advanced, Auto Learning loop, Calibration, Risk-of-Ruin, Lifecycle Decay, Rotational, Cadence, Replay Priority, Event Continuation, Admission Control, Adaptive Concurrency, Anti-Correlation, Compute Probe, Multi-Account, Process-Pool Backtest) **remain exactly as they are**. The restoration flips **zero flags**. Their future UI slots are pre-named in the matrix so activation later is a mount, not a redesign.

## 3.4 FUTURE (9 reserved / not built) — slots pre-booked

| Future capability | Pre-booked slot |
|---|---|
| Phase 13 Dossier Engine | Populates the 12 reservation slots inside the Explorer accordion — no new tab |
| Phase 14 Valuation Engine | Populates the dual scorecard inside the Portfolio accordion — no new tab |
| Phase 15 Marketplace | Separate codebase; ASF-side touchpoint stays the Explorer accordion card |
| BI5 R2 auto-cert sweep | New `diag#bi5-cert` panel + extra column on BI5 Health table |
| BI5 R3 tick replay | Flips the existing `source=bi5` toggle defaults — no new surface |
| cTrader Demo / Live · Windows VPS · Broker Telemetry | Activate the reserved chips in `exec#brokers` — no new tab |

## 3.5 ORPHANS (10) — janitorial

9 retire with mounted replacements (`Optimization.js`, `NavMoreMenu.js`, `DensityToggle.js`, `TraderModeButton.js`, 5× `phase9/*`). `ArchitectDashboard.jsx` is rehouse-then-retire (it holds the only roadmap-aligned orphan IP — deferred to FS veto lift).

---

# 4. Features that become visible after restoration

Only **one** capability is promoted Hidden→Visible, plus five composition/affordance improvements of already-visible capabilities:

| # | Becomes visible | Class of change |
|---|---|---|
| 1 | **Challenge Matching Panel** (`propfirm#challenge`) — 4 live endpoints, panel already written | Hidden → Mounted (the only promotion) |
| 2 | Dashboard 8-panel actionable stack | Re-composition of 8 already-mounted components |
| 3 | Execution Overview (cross-cutting status glance) | New thin composite over existing read-only endpoints |
| 4 | BI5 readiness strip on Market Data | Existing `/api/diag/bi5/health` surfaced in context |
| 5 | Admin readiness one-liner | Existing readiness endpoint surfaced in context |
| 6 | (P2 within sequence, optional) "Backfill Now" button — wraps the existing CLI behaviour via existing API | Affordance |

**Nothing else surfaces.** No FS, no Architect, no Auto Learning, no Notification Center, no Copilot v2, no certification panel.

---

# 5. Features that remain hidden intentionally

| Feature | Why it stays hidden | Unhide trigger |
|---|---|---|
| Factory Supervisor stack (22 engines, ~40 endpoints, FS panel) | **FS-P1.4 operator hard veto** | Explicit operator decree post-stabilisation |
| Architect Dashboard / Advisor Stream / Recommendation Feed | Nested in FS veto scope | With FS activation (P2) |
| Auto Learning panel + loop | 3 FS flags OFF; feeds Phase 14 Trust Score later | `FS_ENABLE_AUTO_LEARNING=true` (P3) |
| Notification Center backend persistence | Flag OFF; UI-only Inbox is the interim | `ENABLE_NOTIFICATION_CENTER=true` |
| Copilot advanced (multi-provider) | Flag OFF | `FS_ENABLE_COPILOT_ADVANCED=true` |
| BI5 Certification panel | Pairs with BI5 R2 work | BI5 R2 lands |
| Runner Registry / Heartbeat / Multi-Account panels | No multi-account runners yet | Multi-account / remote runner go-live |
| ~17 latent flag-gated engines (calibration, RoR, decay, rotation, cadence, admission…) | Designed-to-be-dormant; evidence-gated activation | Per-flag activation governance |
| Deployment Center standalone | Intentional architecture — function distributed (Promote buttons + Readiness + Monitoring); rail label stays | Never (documented in OPERATOR_MANUAL) |
| Light theme | M0 dark-lock | Operator decree only |

---

# 6. Features deferred — by gate

## 6.1 Deferred until POST-IMPORT (GATE 3 → after import runs)

| Item | Note |
|---|---|
| 1-vCPU strategy import itself (6-stage pipeline) | Separate explicit authorisation; plan in `POST_IMPORT_PIPELINE.md`; **0 hidden surfaces block it** |
| Stage-4 challenge drill-down *usage* | Panel mounts during restoration (Step 3) so it is ready *before* import |
| `firm_match_imported` / imported-strategy verdict columns in Explorer | Data appears automatically post-import; no UI work |
| Import-result observability passes (lineage badges, imported-cohort filters) | Assess after Stage 1–6 evidence exists |

## 6.2 Deferred until PHASE 13 (Dossier Engine)

| Item | Slot |
|---|---|
| 12 dossier report slots become computed | Explorer accordion (Phase13ReservationsCard) — zero-reflow plug-in |
| Strategy Score (Quality · Evidence · Market · Trust) computed | Explorer accordion (StrategyScoreReservationCard) |
| BI5 R2 evidence feeds (cert sweep + ranker weights) | Prerequisite work, P0 roadmap |

## 6.3 Deferred until PHASE 14 (Valuation Engine)

| Item | Slot |
|---|---|
| Dual scorecards (Prop Firm + Investor) computed | Portfolio accordion (Phase14DualScorecardCard) |
| Automated Pricing Engine inputs | Same card — no manual pricing fields, per lock |
| Auto Learning → Trust Score longevity multiplier | Requires FS veto lift + `ai#learning` |

## 6.4 Deferred until PHASE 15 (Marketplace)

| Item | Slot |
|---|---|
| Marketplace site (3 product types · signed manifests) | **Separate codebase** — out of ASF scope |
| ASF-side touchpoint | Explorer accordion card remains the only ASF surface |

---

# 7. Implementation risk assessment (per step of `IMPLEMENTATION_SEQUENCE.md`)

| Step | Change | Risk | Failure mode | Containment |
|---|---|---|---|---|
| 1 Baseline freeze | screenshots + checkpoint | **None** | — | evidence only |
| 2 Dashboard stack | 1 new composite + 1 registry line | **MEDIUM** | jank / slow first paint | Suspense skeletons, below-fold lazy mount; 1-line revert |
| 3 Challenge Matching | 1 registry line + palette entry | **LOW** | none plausible (endpoints live, recipe pre-approved) | 1-line revert |
| 4 Landings + friction (Overview, accordions, strips) | 2 new thin components + additive JSX | **LOW-MED** | accordion wrapper visually disturbing M2-locked cards | wrapper-only constraint; per-item revert |
| 5 Nav polish | port 2 a11y helpers into TopTabBar | **LOW** | wheel capture outside strip | port old guard verbatim |
| 6 Janitorial | delete 9 orphan files | **LOW** | build break if hidden import existed | zero-importer verified ×2; build gate; quarantine option |
| 7 Verify + docs | testing agent + manual updates | **None** | — | — |

**Aggregate:** ~9–11 h, frontend-only, every step independently revertible. The riskiest single artefact (Dashboard stack) is also the most valuable and the most trivially reversible (1 registry line). Recommended execution batching: Steps 2+3 → test → Steps 4+5 → test → 6+7.

**What could force a plan change mid-flight:** only Step 2 performance. The fallback is pre-agreed (intersection-observer mount for panels 6–9) and does not alter the layout contract.

---

# 8. Recommendation

## Verdict: **PROCEED EXACTLY AS PLANNED** — with two optional refinements, no removals, no additions required.

### 8.1 Proceed as planned — justification

1. The plan closes all 6 identified regressions and promotes exactly one hidden surface — minimal blast radius.
2. It is 100% frontend composition: zero backend, zero flags, zero import exposure.
3. Every step has a named revert path; the platform auto-commits per step.
4. The 5 planning documents are mutually consistent (placement matrix ↔ nav tree ↔ workflow paths ↔ sequence steps cross-verified during this consolidation; no contradictions found).
5. It honours every standing lock: navbar roster lock, M0 dark-lock, M2 reservation visual locks, FS-P1.4 veto, GATE 3 import gate.

### 8.2 Optional refinements (operator's choice — neither blocks proceeding)

| # | Refinement | Trade-off |
|---|---|---|
| A | **Pilot batch first:** execute only Steps 1–3 (baseline + Dashboard stack + Challenge Matching, ~3.5 h), verify with testing agent, sign off, then authorise Steps 4–7. | Slightly longer wall-clock; materially lower one-shot risk; you see the biggest "1-vCPU feel" win before committing to the rest |
| B | **Quarantine instead of delete** in Step 6: move the 9 orphans to `_inventory/retired/` rather than deleting. | Keeps working tree marginally larger; makes recovery trivial without git archaeology |

### 8.3 Steps to remove

**None.** Every step traces to a named regression or pre-approved janitorial item. Step 5 (nav polish) is the only cosmetic one; it is 45 min and restores a documented behavioural contract of the locked navbar — keep it.

### 8.4 Steps to add

**None required.** Two were considered and deliberately rejected:
- *Top-level Challenge Matching chip in MORE* — rejected: the locked roster must not grow; the sub-tab + palette entry suffice.
- *Wiring the Inbox drawer to the Notification Center backend* — rejected: requires `ENABLE_NOTIFICATION_CENTER=true`, which violates the no-flag rule. Stays flag-gated.

---

# 9. Final answer to the decision question

> *"If we execute the restoration plan, will the resulting UI fully preserve the old 1-vCPU operator experience while also supporting all current and future roadmap capabilities without needing another major UI redesign later?"*

## **YES — with three explicitly bounded caveats.**

### Why yes

1. **1-vCPU experience preserved, verifiably.** The locked navbar roster is already 1:1; after restoration, all 17 tab landings match the old UI's "one click → see the work" contract (the masterplan's per-tab tables show 9 tabs already at parity and the remaining gaps closed by Steps 2–5). Every old workflow click-path is equal or better (`OPERATOR_WORKFLOW_ALIGNMENT.md` §2: no workflow gains a click; W1 and W7 lose friction). The old behavioural contract (scroll, wheel, Admin-append, MORE popover, Library count) is fully ported.
2. **All current capabilities supported.** The placement census assigns a final home to all 159 capabilities with zero losses; the ~100 active ones keep working homes; the restoration only adds composition.
3. **All future roadmap capabilities land without redesign.** This is the decisive structural point: every roadmap item has a **pre-booked, zero-reflow slot** —
   - Phase 13 → populates the Explorer accordion's 12 reservation slots in-place;
   - Phase 14 → populates the Portfolio accordion's dual scorecard in-place;
   - Phase 15 → separate codebase, ASF touchpoint already mounted;
   - BI5 R2/R3 → one new diag sub-section + existing toggle defaults;
   - cTrader/VPS/telemetry → activate reserved chips;
   - FS / Architect / Auto Learning / Copilot v2 / Notification Center → mount into named existing slots (`Cluster` stack, `ai#architect`, `ai#learning`, drawer toggle, drawer rewire) — **mounts, not redesigns**;
   - Runner Registry / multi-account → one new `exec#runners` sub-tab.
   In every case the change vector is "add a section / populate a card / flip a flag," never "re-shape navigation." The module+section registry and the hash-routing scheme absorb all of it.

### The three bounded caveats (what could still warrant *future* — not redesign-level — work)

1. **Dashboard stack performance** on low-resource pods may need the pre-agreed intersection-observer refinement. That is a tuning pass inside one component, not a redesign.
2. **FS-era density:** if the operator one day activates the *entire* FS stack plus Architect plus Auto Learning simultaneously, the AI Workforce module would carry 5 sections and Monitoring▸Cluster would get crowded. The remedy is a sub-tab strip inside those modules — the same pattern already used by MonitoringSuite — i.e., an afternoon of composition, not a redesign.
3. **Phase 15 is out of scope by design:** the marketplace is a separate public codebase. Nothing ASF-side changes, but the marketplace itself is a new build — that is roadmap scope, not UI-redesign debt.

**Bottom line:** the restored UI is the *final form* of the operator shell for the entire visible roadmap (import → BI5 R2/R3 → FS activation → Phase 13 → 14 → 15). No planned capability requires moving a tab, breaking a deep link, or re-teaching the operator. The flat 1-vCPU loop — Glance → Make → Prove → Choose → Bundle → Match → Run → Watch — remains the permanent spine.

---

# 10. Decision checklist for the operator

- [ ] Approve report → **GATE 0 opens** (authorise Steps 1–7, or Refinement A pilot batch Steps 1–3 first)
- [ ] Choose Step-6 mode: delete vs quarantine (Refinement B)
- [ ] After Step 7 sign-off → **GATE 2** (restored UI accepted)
- [ ] Separately, and only by explicit decree → **GATE 3** (1-vCPU strategy import)
- [ ] FS veto lift remains its own future decision — nothing here touches it

---

# 11. State of this document

* Read-only executive consolidation. **This is the final decision document before any implementation authorisation.**
* No code modified. No surfaces mounted. No imports run. No feature flags flipped.

**End of report.**
