# Visual Signoff Pack

**Purpose:** Sealed operator baseline of all major workflows BEFORE the 1-vCPU strategy import.
**Captured:** 2026-06-11 (post-P1 recovery, pre-import).
**Pod state at capture:** hydration complete · DSR-3 active · BI5 R1 wired · 0 strategies in library · 0 market-data ticks (pre-bootstrap).

## Contents (12 JPEGs)

| # | File | Workflow | Route |
|---|---|---|---|
| 01 | `01_mission_control.jpg` | Mission Control · Dashboard | `/c/dashboard/briefing` |
| 02 | `02_workspace.jpg` | Workspace · Unified Lab (P1.1 restored) | `/c/lab/workspace` |
| 03 | `03_explorer.jpg` | Strategy Explorer | `/c/explorer/explorer` |
| 04 | `04_auto_factory.jpg` | Auto Factory · Phase 55 | `/c/mutate/factory-55` |
| 05 | `05_portfolio.jpg` | Portfolio Builder | `/c/portfolio/builder` |
| 06 | `06_master_bot.jpg` | Master Bot Dashboard | `/c/mutate/master-bot` |
| 07 | `07_prop_firm.jpg` | Prop Firm Admin | `/c/propfirm/admin` |
| 08 | `08_market_data.jpg` | Market Data Workbench | `/c/diag/market-data` |
| 09 | `09_diagnostics.jpg` | Diagnostics · Deployment Readiness | `/c/diag/readiness` |
| 10 | `10_bi5_health.jpg` | BI5 R1 · BI5 Health | `/c/diag/bi5-health` |
| 11 | `11_governance.jpg` | Governance | `/c/governance/gov` |
| 12 | `12_dsr_registry.jpg` | DSR · Symbol Registry | `/c/governance/symbol-registry` |

## Globals captured in every frame

* **TopTabBar (M0)** — 11 CORE tabs + More ▾
* **LifecycleRail (M1)** — 10 numbered stages
* **DangerRibbon** — top-of-screen demo alert "Master Bot compile failed · signing error"
* **"VIEW INBOX ▸"** affordance — Operator Inbox entry point (drawer opens on click)
* **CommandBar** — quick command (⌘K), focus mode, density, premium, notifications, user menu
* **StatusRail** — 6 chips (orch · ingest · sched · llm · govern · kill)

These global overlays serve as the visual signature of the hydrated shell — they appear on every operator surface and confirm that the chrome is consistently mounted.

## How to use this pack

* **Pre-migration baseline:** before importing the 1-vCPU strategies, the operator confirms each frame matches expectation.
* **Post-migration parity check:** after pipeline Stage 6 completes, re-capture the same 12 frames and diff. Expected differences: Explorer rows, Library count badge, Portfolio Builder candidates, Master Bot candidates, Governance survivor count.
* **Regression evidence:** if any future change unexpectedly alters operator chrome, this pack is the reference.

## Format

* 1920×1080 viewport
* JPEG quality 30 (operator-readable, ~55–62 KB per frame)
* Capture order matches the operator's prioritised list

## Total footprint

~688 KB across 12 files. Suitable to commit to the audit trail or zip + archive.

## Companion documents

* `IMPORT_READINESS_REPORT.md` — gate document referencing this pack.
* `POST_HYDRATION_VALIDATION_REPORT.md` — validation evidence from hydration.
* `P1_RECOVERY_REPORT.md` — Workspace + Library badge restoration evidence.

This pack is the seal between hydration phase and migration phase.
