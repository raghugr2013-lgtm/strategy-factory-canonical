# Visual Approval Package — AI Strategy Factory Workstation Restoration

> **Phase 1 deliverable.** Visual mockups · wireframes · design system spec.
> **No code changes. No implementation. No deployment.** Approval gate before Phase 2.

---

## Purpose

Restore the **old 1-vCPU workstation workflow** while preserving **every capability added since**, finished in a **Binance / Bybit dark trading terminal aesthetic**.

The brief is:

```
OLD ASF WORKFLOW
+
CURRENT ASF CAPABILITIES
+
BINANCE / BYBIT VISUAL QUALITY
============================
FINAL ASF WORKSTATION
```

## Source-of-truth hierarchy (locked)

1. **PRIORITY 1** — Old 1-vCPU frontend source code (`_inventory/old1vcpu/`) ← extracted from `Frontend from old 1vcpu for reffrence.zip`. Anchors all tab IDs, tab order, dashboard composition, layout grids and design tokens.
2. **PRIORITY 2** — Old UI screenshots (`screenshots of old ui.docx`).
3. **PRIORITY 3** — `ASF_UI_Handoff_2026-06-08/` (functionality reference only).
4. **PRIORITY 4** — Current workstation codebase (`_inventory/app_extracted/frontend/`) ← for re-housing the new capabilities.

## Guardrails (binding)

- ⛔ **Zero backend changes.** `git diff --stat /app/backend` must be EMPTY at every phase boundary.
- ⛔ **Zero capability removal.** Every component currently mounted in `modulesRegistry.js` MUST have an explicit home in the restored UI.
- ⛔ **No new navigation concepts.** The tab roster is locked to the old 1-vCPU spec (verbatim from `App.js` LL 167–185).
- ⛔ **No invented workflows.** The flow Dashboard → Execution → Auto Factory → … → Admin is operator-mandated.
- ✅ Master Bot, Factory Supervisor, Auto Learning, Notification Drawer, Copilot, Governance, Scaling, Diagnostics, Challenge Matching, Readiness are all **explicitly re-housed** in §04 + §05.
- ✅ AUTH-FIX (`installAuthFetchInterceptor`), a11y fixes, theme tokens, density mode are preserved as in the current code.

## Package contents

| # | File | Purpose |
|---|---|---|
| 0 | `README.md` | This file — overview + sign-off matrix |
| 1 | `01_TAB_ROSTER.md` | Locked tab roster (11 CORE + 6 MORE + Admin). Source-line citations to old `App.js`. |
| 2 | `02_DESIGN_SYSTEM.md` | Binance/Bybit dark theme tokens · typography · density mode · component primitives. Extracted verbatim from old `src/index.css` + `src/styles/theme.js`. |
| 3 | `03_SCREEN_WIREFRAMES.md` | ASCII wireframes for all 17 screens (11 core + 6 more) + topbar + global overlays. |
| 4 | `04_COMPONENT_REHOUSING_MATRIX.md` | Every component in current codebase → its restored tab. Zero-loss proof. |
| 5 | `05_GLOBAL_OVERLAYS_AND_NEW_CAPABILITIES.md` | Where Master Bot, Factory Supervisor, Notification Drawer, Copilot, Auto Learning, Scaling, Challenge Matching live. |
| 6 | `06_MIGRATION_PLAN.md` | Phased M0 → M5 rollout. Risk class per phase. Operator impact per phase. ~9 dev-day total. |
| 7 | `07_SIGNOFF_CHECKLIST.md` | Original operator approval form (superseded by 08–11). |
| 8 | `08_ADDENDUM_OPERATOR_FEEDBACK.md` | Locks operator constraints C1–C5 (dark-only · preservation · BI5 separate · final review · cTrader-readiness). |
| 9 | `09_OPERATOR_LIFECYCLE.md` | Locks C6 — the 10-step operator lifecycle + Lifecycle Rail + 5-primary-screen hierarchy + per-screen Next-CTA. |
| 10 | `10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md` | Locks C7 — insertion points for Phase 13 (Strategy Dossier) + Phase 14 (Automated Valuation) + Phase 15 (Marketplace). |
| 11 | `11_THEMETOGGLE_REMOVAL.md` | Final confirmation of ThemeToggle removal. ASF is dark-only going forward. |

## Sign-off gate

Implementation cannot begin until **all 7 sign-off items in `07_SIGNOFF_CHECKLIST.md`** are explicitly approved by the operator. Per the brief:

> *Phase 1: Produce visual mockups and wireframes. Phase 2: Restore old workflow. Phase 3: Operator review. Phase 4: Implementation. Do not implement immediately.*

## What this package replaces

This package **supersedes** `/app/memory/ui_restoration/` (dated 2026-06-11) — that older package was derived from screenshots only (Priority 2). This package is anchored to the **actual old 1-vCPU source code** (Priority 1), so every tab ID, layout grid, and design token is a verbatim transcription, not an interpretation.

## What stays parked

- BI5 Recovery — separate workstream, sequenced AFTER UI Restoration per operator instruction.
- DEV-RC1 cut — Phase M0 (tokens) resolves the only outstanding RC1 BLOCKER (light-theme contrast); RC1 cut can land at the post-M5 HEAD.
- 24h soak · 12-vCPU deployment — gated behind DEV-RC1.

— End of README —
