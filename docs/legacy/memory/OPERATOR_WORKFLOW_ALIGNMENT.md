# OPERATOR_WORKFLOW_ALIGNMENT.md

**Audit type:** Read-only workflow alignment. Proves that every operator workflow from the 1-vCPU era — plus the new workflows added since — maps onto the restored UI with equal-or-fewer clicks, and that the 10-step lifecycle remains the spine of the experience.
**Sources:** old 1-vCPU `App.js` + `screenshots of old ui.docx` (18 frames), `OPERATOR_MANUAL.md`, `POST_IMPORT_PIPELINE.md`, `UI_RESTORATION_MASTERPLAN.md`, `NAVIGATION_RECONSTRUCTION.md`.
**Status:** Read-only. No code modified.
**Generated:** 2026-06-12

---

## 0. The operator's mental model (what we are protecting)

The 1-vCPU operator worked in **one flat loop**:

> **Glance (Dashboard) → Make (Workspace / Auto Factory) → Prove (Validation / Paper) → Choose (Auto Select / Explorer) → Bundle (Portfolio) → Match (Prop Firms) → Run (Trade Runner / Live) → Watch (Monitoring) — repeat.**

Each verb was one tab. Each tab was one scroll. The restoration preserves this loop verbatim and slots the new capabilities (BI5, DSR, Master Bot, reservations, drawers) into the loop *without adding mandatory steps*.

---

## 1. The 10-step lifecycle ↔ tab alignment

The current `LifecycleRail` (10-step operator GPS) already encodes the loop. Restored alignment:

| Stage | LifecycleRail label | Restored tab home | Workflow verb |
|---|---|---|---|
| 1 | Data | Market Data | prepare |
| 2 | Generate | Auto Factory (+ Workspace for manual) | make |
| 3 | Mutate | Auto Factory ▸ #auto / #cycle | evolve |
| 4 | Validate | Workspace ▸ Validation (and Auto Factory pipeline auto-validate) | prove |
| 5 | Select | Auto Select | choose |
| 6 | Portfolio | Portfolio | bundle |
| 7 | Match | Prop Firms (▸ Firm Match ▸ Challenge Matching P1) | match |
| 8 | Paper | Paper Exec | rehearse |
| 9 | Live | Trade Runner + Live Tracking | run |
| 10 | Deployment | Monitoring (rail label routes here — intentional) | watch |

✅ Every stage has exactly one primary tab. The rail remains a *journey indicator*, never a second navigation system.

---

## 2. Workflow-by-workflow click-path comparison

Legend: **Old** = 1-vCPU UI · **Current** = hydrated shell today · **Restored** = post-restoration target.

### W1 — Morning glance ("is the factory healthy, what needs me?")

| | Path | Clicks | Notes |
|---|---|---|---|
| Old | Dashboard → scroll 8 panels | 1 | everything visible, but no synthesis |
| Current | Dashboard (MissionBriefing) → then visit 6+ tabs to act | 1 + N | synthesis good; actions far away |
| **Restored** | Dashboard → MissionBriefing first, 8 actionable panels below in the same scroll | **1** | best of both: synthesis + work surface |

### W2 — Generate a strategy manually (the lab loop)

| | Path | Clicks |
|---|---|---|
| Old | MORE → Workspace → generate → backtest → describe → cbot → optimize/validate → compare (one scroll) | 2 |
| Current | MORE → Workspace (`WorkspaceComposite`, P1.1-restored) | 2 |
| **Restored** | unchanged | **2** ✅ already at parity |

### W3 — Run the autonomous pipeline

| | Path | Clicks |
|---|---|---|
| Old | Auto Factory tab (Phase 55 live status) | 1 |
| Current | Auto Factory tab → `mutate#factory-55` | 1 |
| **Restored** | unchanged | **1** ✅ |

### W4 — Check & fix market data

| | Path | Clicks |
|---|---|---|
| Old | Market Data → DataUpload + DataMaintenance stacked | 1 |
| Current | Market Data → Manual sub-tab default; "is data ready?" answer requires separate visit to `diag#bi5-health` | 1–2 |
| **Restored** | Market Data → BI5 readiness strip on top + Manual default; Backfill Now button inline (P2) | **1** |

### W5 — Browse / compare / pick strategies

| | Path | Clicks |
|---|---|---|
| Old | Explorer (browse); MORE → Library for saved | 1–2 |
| Current | same, but 3 reservation cards interleave the browse scroll | 1–2 + scroll friction |
| **Restored** | Explorer browse clean; reservations in one collapsed accordion at bottom | **1–2**, friction removed |

### W6 — Build & inspect a portfolio

| | Path | Clicks |
|---|---|---|
| Old | Portfolio tab (builder); MORE → Portfolio for panel | 1–2 |
| Current | Portfolio → builder default ▸ #panel ▸ #intel | 1–2 |
| **Restored** | unchanged + Phase 14 card collapsed at bottom | **1–2** ✅ |

### W7 — Match strategies to prop firms / challenges

| | Path | Clicks |
|---|---|---|
| Old | MORE → Prop Firms (admin CRUD; match embedded) | 2 |
| Current | MORE → Prop Firms ▸ #match; challenge-template detail = **raw curl only** | 2 (+ terminal for challenges) |
| **Restored** | MORE → Prop Firms ▸ #match ▸ #challenge (P1 mount) | **2–3**, zero terminal ✅ closes the only workflow regression |

### W8 — Rehearse (paper) then run (live)

| | Path | Clicks |
|---|---|---|
| Old | Paper Exec tab → Trade Runner tab → MORE → Live Tracking | 1 each |
| Current | identical deep-links (`exec#paper`, `exec#runner`, `exec#live`) | 1 each |
| **Restored** | identical + Execution tab gains an Overview composite for the cross-cutting glance | **1 each** ✅ |

### W9 — Watch & intervene (runtime control)

| | Path | Clicks |
|---|---|---|
| Old | Monitoring tab (stop-all / resume / thresholds / breach log / fleet) | 1 |
| Current | Monitoring → Runtime default (same controls) ▸ Soak/Compute/Cluster extras | 1 |
| **Restored** | unchanged | **1** ✅ |

### W10 — Admin (users, flags, realism, tuning, readiness)

| | Path | Clicks |
|---|---|---|
| Old | Admin tab → ReadinessPanel + AdminUsers stacked | 1 |
| Current | Admin tab → Users default ▸ Flags/Realism/Tuning; Readiness in Governance | 1–2 |
| **Restored** | Admin tab → Readiness one-liner on top + Users default | **1** for the common case |

### W11 — NEW (post-1-vCPU): symbol onboarding (DSR)

| | Path | Clicks |
|---|---|---|
| Current | `governance#symbol-registry` (palette or Governance rail) | 2 |
| **Restored** | unchanged + Audit History sub-tab (P2) | 2 — new workflow, no old equivalent |

### W12 — NEW: attention triage (drawers)

| | Path | Clicks |
|---|---|---|
| Current | DangerRibbon always visible; Inbox / Notification / Copilot drawers from any tab | 0–1 |
| **Restored** | unchanged — drawers are pure-overlay additions to the old loop | **0–1** ✅ |

---

## 3. Workflow regressions found → restoration answer

| # | Regression vs 1-vCPU | Severity | Restoration answer |
|---|---|---|---|
| R-1 | Dashboard lost its 8 actionable panels (read-only briefing only) | **HIGH** — breaks W1, the most-used workflow | Restored stacked Dashboard (masterplan §1.1) — `IMPLEMENTATION_SEQUENCE.md` Step 2 |
| R-2 | Challenge-template drill-down requires curl | MEDIUM — breaks W7 tail | Mount `propfirm#challenge` (Step 3) |
| R-3 | "Is data ready?" needs a second tab visit | LOW | BI5 strip on Market Data (Step 4) |
| R-4 | Reservation cards interrupt Explorer/Portfolio scroll | LOW (friction) | Collapse to bottom accordions (Step 4) |
| R-5 | Execution tab lands on chips only — no one-glance status (old ExecutionDashboard) | LOW | Execution Overview composite (Step 4) |
| R-6 | Nav a11y helpers (wheel hijack, scrollIntoView) not ported | COSMETIC | TopTabBar polish (Step 5) |

No other workflow regressed. W2, W3, W6, W8, W9 are already at full parity.

---

## 4. Post-import workflows (future — after the 1-vCPU strategy import is authorized)

The import (strictly gated on operator authorization, AFTER UI restoration) introduces 6 pipeline stages. Where the operator will *watch and act* on each:

| Import stage | Operator surface in restored UI |
|---|---|
| Stage 1 — Ingest + fingerprint | Dashboard → StrategyIngestionCard (restored stack) + `diag#ingest-src` |
| Stage 2 — Re-validate (pass probability) | Explorer (verdict columns) + Workspace Validation |
| Stage 3 — Re-rank | Explorer browse (rank order) + Auto Select |
| Stage 4 — Re-match firms/challenges | Prop Firms ▸ #match ▸ **#challenge (this is why the P1 mount precedes import)** |
| Stage 5 — Portfolio candidacy | Portfolio ▸ builder + intel |
| Stage 6 — Master Bot proposals | Auto Factory ▸ #master-bot (+ compile) |

**Dependency:** `POST_IMPORT_FEATURE_DEPENDENCY.md` confirms 0 hidden surfaces block the import; but the *operator experience* of Stage 4 is materially better with `#challenge` mounted first. Hence the sequence: restore UI → verify → then (and only on explicit decree) import.

---

## 5. Dormant-capability workflows (no operator action until decree)

| Future workflow | Trigger | Where it will live |
|---|---|---|
| FS-supervised parallel factory | `ENABLE_FACTORY_SUPERVISOR=true` | Monitoring ▸ Cluster (FS panel) + `ai#architect` |
| Advisor-guided operation | FS activation | `ai#architect` (recommendation feed + advisor stream) |
| Continuous learning review | `FS_ENABLE_AUTO_LEARNING=true` | `ai#learning` |
| Persistent cross-session inbox | `ENABLE_NOTIFICATION_CENTER=true` | existing Inbox drawer (rewired to backend) |
| Copilot v2 Q&A | `FS_ENABLE_COPILOT_ADVANCED=true` | existing Copilot drawer (v2 toggle) |
| BI5 certification review | BI5 R2 lands | `diag#bi5-cert` |

Each future workflow *adds a destination* without changing any existing click-path — the flat loop is never re-shaped.

---

## 6. Alignment scorecard

| Principle (from masterplan §0) | After restoration |
|---|---|
| Flat top-nav roster preserved | ✅ 1:1 locked roster |
| One click → see the work | ✅ all 11 CORE tabs land on actionable content |
| Stacked-panel Dashboard | ✅ restored (R-1 closed) |
| Single-page lab (Workspace) | ✅ already restored (P1.1) |
| New surfaces never block the loop | ✅ drawers/overlays + collapsed accordions |
| Lifecycle rail = GPS, not nav | ✅ unchanged |
| Zero workflow needs a terminal | ✅ after `#challenge` mount (R-2 closed) |
| Zero capability lost | ✅ per `CAPABILITY_PLACEMENT_MATRIX.md` roll-up |

---

## 7. State of this document

* Read-only alignment audit — companion to `UI_RESTORATION_MASTERPLAN.md`, `CAPABILITY_PLACEMENT_MATRIX.md`, `NAVIGATION_RECONSTRUCTION.md`, `IMPLEMENTATION_SEQUENCE.md`.
* No code modified. No surfaces mounted. No flags flipped.

**End of report.**
