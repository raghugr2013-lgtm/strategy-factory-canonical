# PILOT_RESTORATION_REPORT.md

**Scope executed:** GATE 0 pilot — Steps 1–3 of `IMPLEMENTATION_SEQUENCE.md` ONLY.
**Date:** 2026-06-12
**Testing:** Testing agent full frontend pass — `/app/test_reports/iteration_8.json` — **100% pass, zero issues, zero fixes needed.**

---

## 1. What was executed

| Step | Change | Files |
|---|---|---|
| 1 — Baseline freeze | Before-screenshots captured (Dashboard, Prop Firms); git checkpoint confirmed | none |
| 2 — Mission Control restored | NEW `command/shell/dashboard/DashboardComposite.jsx` — MissionBriefing + 8 legacy panels in locked 1-vCPU order (Governance → Universe → Ingestion → Scheduler → Orchestrator → Multi-Cycle → Auto-Mutation → StrategyDashboard); each panel lazy + own Suspense skeleton + own error boundary. Posture contract: workstation = full stack, tablet = collapsed accordions, briefing = MissionBriefing only. Registry section swapped (id `briefing` kept; title → "Mission Control") | NEW `DashboardComposite.jsx` · EDIT `modulesRegistry.js` |
| 3 — Challenge Matching surfaced | Section `{ id: 'challenge' }` added to `propfirm` module (recipe from `MISSING_OR_HIDDEN_FEATURES.md` §2.1). Palette gains a "Sections" group with deep-link item `section:propfirm:challenge`; `CommandShell.handlePaletteSelect` handles the `section:` prefix (navigate module → set #hash → scroll) | EDIT `modulesRegistry.js` · `CommandPalette.jsx` · `CommandShell.jsx` |

**Constraints honoured:** no backend changes · no flags flipped · no FS/Auto-Learning activation · no strategy import · no orphan files retired · Phase 13/14/15 reservation cards untouched.

## 2. Navigation comparison

| Surface | BEFORE | AFTER |
|---|---|---|
| Top nav roster | 11 CORE + 6 MORE + Admin (locked) | **unchanged** (verified by testing agent) |
| Dashboard landing | MissionBriefing only ("1 SECTION", read-only) | "Mission Control" — MissionBriefing + 8 actionable panels, one scroll |
| Prop Firm module | 2 sections (Prop Firms · Firm Match) | 3 sections (+ Challenge Matching) |
| Palette | Modules · Workflow · Posture · Legacy | + "Sections" group (Challenge Matching deep-link → `/c/propfirm#challenge`) |
| All other tabs / deep links | — | **unchanged** (Execution, Auto Factory, Monitoring, Explorer, Market Data, Admin regression-clicked clean) |

## 3. Capability visibility comparison

| Capability | BEFORE | AFTER |
|---|---|---|
| Challenge Matching (catalog #70) | Hidden (API-only, curl) | **VISIBLE** at `propfirm/challenge` — only Hidden→Visible promotion in pilot |
| 8 Dashboard-stack panels | Visible at scattered homes only | Visible at homes **+ composed on Dashboard** (dual mount; canonical homes unchanged) |
| Factory Supervisor / Architect / Auto Learning / Notification Center / Copilot v2 | Hidden/dormant | **unchanged — still hidden** (veto honoured) |
| Phase 13/14/15 + Strategy Score reservations | Mounted inline | **unchanged** (accordion move deferred to Step 4) |
| Everything else (159-item census) | per `CAPABILITY_PLACEMENT_MATRIX.md` | **unchanged** |

## 4. Regressions discovered

**None.** Testing agent: 0 backend issues, 0 UI bugs, 0 integration issues, 0 console errors, no `section-error` / `dashboard-stack-error-*` states. Two low-priority observations (not bugs): ① test-side Esc-close detection heuristic for the palette could use a `data-state` attribute; ② testid naming map (`top-tab-admin-users`, `top-tab-data`) worth documenting for testers. Pre-existing known states (LLM key missing chip, Master Bot signing-error ribbon) unchanged and unrelated.

## 5. Remaining restoration steps (NOT executed — awaiting operator review)

- Step 4 — Execution Overview composite · reservation accordions · BI5 strip on Market Data · Admin readiness one-liner (closes R-3, R-4, R-5)
- Step 5 — Nav a11y polish: wheel hijack + active-tab scrollIntoView (closes R-6)
- Step 6 — Orphan janitorial (explicitly excluded from pilot; needs authorization, delete vs quarantine choice)
- Step 7 — Final verification + OPERATOR_MANUAL/PRD updates

**Status: STOPPED at operator review checkpoint per GATE 0 pilot instruction.**
