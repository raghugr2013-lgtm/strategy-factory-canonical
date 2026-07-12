# RESTORATION_STEPS_4_5_REPORT.md

**Scope executed:** GATE 0 follow-up — Steps 4 + 5 of `IMPLEMENTATION_SEQUENCE.md` (operator-approved after pilot review).
**Date:** 2026-06-12
**Testing:** Testing agent full frontend pass — `/app/test_reports/iteration_9.json` — **100% (8/8 flows), zero issues, zero fixes needed.** Pilot regression (Steps 1–3) re-verified in the same run.

---

## 1. What was executed

| Item | Change | Files |
|---|---|---|
| 4a — Execution Overview | NEW read-only KPI strip (Paper runs · Trade Runner runs · Live tracked + needs-attention) mounted as FIRST section of `exec`; detail panels stay stacked below. Reads existing GETs: `/api/execution/paper/runs`, `/api/trade-runner/runs`, `/api/live/strategies`. Manual Refresh; partial-failure tolerant | NEW `components/ExecutionOverview.jsx` · EDIT `modulesRegistry.js` |
| 4b — Reservation accordions | Explorer's 3 reservation cards (Strategy Score · Phase 13 Dossier · Phase 15 Marketplace) collapsed into ONE bottom accordion; Portfolio's Phase 14 card likewise. **Cards untouched (M2/M3 locks)** — pure `<details>` wrappers | NEW `command/reservations/ReservationsAccordion.jsx` · EDIT `modulesRegistry.js` (explorer section ids `score-rubric`/`passport-reservations`/`marketplace-reservations` → single `reservations`; portfolio `scorecards-reservations` id kept, component wrapped) |
| 4c — BI5 readiness strip | One-line "is data ready?" strip above Market Data sub-tabs reading `/api/diag/bi5/health` (READY / PARTIAL / NOT READY + symbols ok/tracked + coverage + ticks). Fails silent — never blocks the tab | EDIT `components/MarketDataWorkbench.jsx` |
| 4d — Admin readiness one-liner | "READINESS · {GREEN/AMBER/RED}" line at top of Admin suite reading `/api/admin/readiness` + "open readiness →" hash-jump to `governance#readiness` | EDIT `components/GovernanceAdminSuite.jsx` |
| 5 — Nav a11y polish | Ported from locked 1-vCPU `App.js` LL 126–145: vertical-wheel→horizontal-scroll on the tab strip + active-tab `scrollIntoView({inline:'center'})` (MORE tabs scroll the More trigger) | EDIT `command/shell/TopTabBar.jsx` |

**Constraints honoured:** no backend changes · no flags flipped · no FS / Auto Learning / Notification Center activation · no strategy import · no orphan files touched · reservation card internals unchanged.

## 2. Navigation comparison (vs post-pilot state)

| Surface | Before Steps 4+5 | After |
|---|---|---|
| Execution landing | Broker chips first | **Execution Overview KPI strip first**, chips + Paper/Runner/Live below (closes R-5) |
| Explorer scroll | 3 reservation cards inline interrupting browse | Clean browse; ONE collapsed accordion at bottom (closes R-4) |
| Portfolio scroll | Phase 14 card inline | Collapsed accordion at bottom (closes R-4) |
| Market Data | Data-readiness required a trip to `diag#bi5-health` | One-line BI5 verdict above sub-tabs (closes R-3) |
| Admin | Readiness verdict required a trip to `governance#readiness` | One-line verdict + jump button (old 1-vCPU Admin parity) |
| Top nav behaviour | No wheel hijack / no active-tab auto-scroll | 1-vCPU behavioural contract restored (closes R-6) |
| Top-nav roster, all deep links, all other tabs | — | **unchanged** (regression-verified) |

## 3. Capability visibility delta

**Zero Hidden→Visible promotions in Steps 4+5.** Deltas are presentation-only:
- 3 read-only data affordances added (Exec Overview, BI5 strip, Readiness line) — all over pre-existing endpoints.
- 4 reservation cards moved from inline → collapsed accordions (still mounted, still expandable, content identical).
- FS / Auto Learning / Notification Center / Copilot v2 / all 88 OFF flags: **untouched**.

## 4. Regressions discovered

**None.** iteration_9: 0 bugs, 0 integration issues, 8/8 flows green incl. full pilot regression (Dashboard 8-panel stack, Challenge Matching, palette deep-link) and CORE/MORE tab sweep. Two pre-existing low-priority observations (not caused by restoration): occasional HTTP 429 rate-limit responses during rapid automated navigation, and WebGL/console noise on `/c/saved` — both environment/pre-existing artefacts.

## 5. Workflow-regression scoreboard (from OPERATOR_WORKFLOW_ALIGNMENT.md §3)

| # | Regression | Status |
|---|---|---|
| R-1 | Dashboard lost actionable stack | ✅ closed (pilot Step 2) |
| R-2 | Challenge drill-down = curl only | ✅ closed (pilot Step 3) |
| R-3 | "Is data ready?" second-tab trip | ✅ closed (Step 4c) |
| R-4 | Reservations interrupt browse | ✅ closed (Step 4b) |
| R-5 | Execution lands without one-glance status | ✅ closed (Step 4a) |
| R-6 | Nav a11y helpers not ported | ✅ closed (Step 5) |

**All 6 identified 1-vCPU workflow regressions are now closed.**

## 6. Remaining (NOT executed — per operator instruction)

- **Step 6 (policy updated by operator):** orphan files get **quarantine/inventory-only** treatment — NO deletion. Move the 9 zero-importer files + (eventually) `ArchitectDashboard.jsx` to `_inventory/retired/` pending a later architectural review.
- **Step 7:** final verification sweep + `OPERATOR_MANUAL.md` updates + sign-off package.
- Strategy import (GATE 3), FS veto lift, Auto Learning, Notification Center — all untouched, all awaiting separate decrees.

**Status: STOPPED at operator review checkpoint.**
