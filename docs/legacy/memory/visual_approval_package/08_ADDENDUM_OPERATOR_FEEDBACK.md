# 08 · Addendum — Operator feedback (2026-06-11)

> Operator approved the overall direction with 5 binding clarifications. This file captures them as immutable design constraints. All subsequent mockups, implementation phases, and acceptance criteria MUST honour them.

---

## C1 — Dark mode only

- Dark mode is the **sole** operator-facing theme.
- The previous light-theme variant is **deleted** from the design system (`02_DESIGN_SYSTEM.md`).
- `ThemeToggle` is **removed from the topbar** in M0.
- Reference quality bar: **Binance · Bybit · TradingView · Quantower · cTrader.**
- All future contrast / accessibility / hierarchy / depth / motion effort is consolidated on a single canvas.
- DEV-RC1 blockers RC1-1 and RC1-2 **cannot recur** — they presume two themes.

## C2 — Preserve all post-1vCPU features

Verbatim list. Every item below has at least one explicit home documented in `04_COMPONENT_REHOUSING_MATRIX.md` + `05_GLOBAL_OVERLAYS_AND_NEW_CAPABILITIES.md`:

* Master Bot → Auto Factory (compile) + Monitoring → Cluster (fleet)
* Factory Supervisor → Monitoring → Cluster
* Auto Learning → Monitoring → Runtime stream + Admin → Tuning + Copilot
* Copilot → Global overlay ⌘J
* Notification Drawer → Global overlay ⌘⌥N + 🔔 topbar
* Governance → Dashboard top + Admin → Flags + Notification Drawer (widening)
* Scaling → Monitoring → Cluster
* Diagnostics → Dashboard right-rail + Monitoring sub-tabs
* Prop Firm workflows → Prop Firms (More ▾) + Portfolio (fitness)
* Deployment Readiness → Dashboard right-rail + Admin → Users strip
* Monitoring → Monitoring screen
* Portfolio Builder → Portfolio screen
* Trade Runner → Trade Runner screen

The mandate is **familiarity + capability, not rollback.**

## C3 — BI5 architecturally separate (7-stage flow)

BI5 must continue to be represented as **its own pipeline**, not a BID variant.

The locked 7-stage flow:

```
1. Raw Ticks
   → 2. Tick Archive
       → 3. Spread
           → 4. Slippage
               → 5. Execution Realism
                   → 6. Certification
                       → 7. Deployment Influence
```

- Stage 3 (Spread) is **explicitly separated** from Stage 4 (Slippage) and Stage 5 (Execution Realism). They are conceptually distinct.
- `bi5_architecture.html` mockup updated accordingly (rendered).
- BI5 remains a **separate workstream**, sequenced AFTER UI Restoration (per the brief).
- The Market Data screen's BI5 callout points operators at this dedicated architecture screen rather than treating the BI5 download button as another BID source.

## C4 — Final visual review (this pass)

7 screens re-rendered at **1920 × 1080** workstation viewport:

* `dashboard.html`
* `auto_factory.html`
* `trade_runner.html`
* `monitoring.html`
* `market_data.html`
* `portfolio.html`
* `explorer.html`

Plus the BI5 architecture mockup (`bi5_architecture.html`) carrying the locked 7-stage flow.

Each screen now incorporates: dark-only token refinement, accent-borders on hero KPIs, sub-tab underline + raised treatment, gradient card heads, and `.future-slot` placeholders for cTrader (where applicable). Screenshots embedded in chat for inline operator review.

## C5 — Future cTrader readiness

Layout space is **reserved** in the following screens. No connection logic is implemented — placeholders only — but the geometry will not re-flow when cTrader integration lands post-RC1.

| Screen | Reserved slot |
|---|---|
| **Trade Runner** | Account header carries a 3-chip *Execution backend* row (`PAPER active` · `cTrader Live · coming` · `cTrader Demo · coming`). Activity ledger has a `Broker` column. Bottom of screen carries a full-width `.future-slot` reserved for "cTrader live execution telemetry — broker fills, real spread, depth-of-market, cTrader account balance, margin used, free margin." |
| **Monitoring** | Cluster sub-tab includes an **Execution Backends** card listing all 3 backends (PAPER active, cTrader Live future, cTrader Demo future) with Connect buttons disabled until post-RC1. Master Bot Fleet card has a `Broker` column per bot + a `.future-slot` for cTrader-connected bot rows. |
| **Portfolio** | KPI strip's 6th tile is `Target broker`. Builder composer has a "Target deployment broker" chip row (`PAPER active` · `cTrader Live FUTURE` · `cTrader Demo FUTURE`). |
| **Master Bot** (Auto Factory → compile accordion) | Deploy-to-runner card has a `Broker target` row + a `.future-slot` reserved for cTrader account credentials / leverage policy / margin rules. |

The `.future-slot` styling (cyan dashed border + diagonal hatch + "RESERVED" tag) makes it visually obvious that these zones are placeholders and will be filled by the post-RC1 cTrader workstream.

---

## How these constraints flow into the package

| Constraint | Files updated |
|---|---|
| **C1 dark-only** | `02_DESIGN_SYSTEM.md` rewrites the token block, deletes light-theme variant. `06_MIGRATION_PLAN.md` M0 + M5 updated. `mockups/styles.css` removes `[data-theme]` selector. All HTML mockups have `data-theme` attribute stripped. |
| **C2 preservation** | `04_COMPONENT_REHOUSING_MATRIX.md` + `05_GLOBAL_OVERLAYS_AND_NEW_CAPABILITIES.md` already enumerate every feature. This addendum re-states the contract. |
| **C3 BI5 7-stage** | `mockups/bi5_architecture.html` rewritten with explicit Spread stage. This addendum locks the order. |
| **C4 final review** | All 8 mockups re-screenshotted at 1920×1080 (see chat). |
| **C5 cTrader readiness** | `mockups/trade_runner.html` + `mockups/monitoring.html` + `mockups/portfolio.html` + `mockups/auto_factory.html` carry `.future-slot` + `.broker-chip.future` placeholders. `mockups/styles.css` defines the future-slot + broker-chip styles. |

## Operator authorization (sign-off addendum)

```
Constraints C1–C5 acknowledged and approved:

Approved by:    ________________________

Date:           ________________________
```

— End of ADDENDUM —
