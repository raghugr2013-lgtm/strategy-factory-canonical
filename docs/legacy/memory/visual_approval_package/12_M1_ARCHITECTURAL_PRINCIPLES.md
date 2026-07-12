# 12 · M1 Architectural Principles (Pre-Implementation Lock)

> Operator-locked 2026-06-11. These principles are binding for **M1 and every
> subsequent phase**. They cannot be silently relaxed by any future implementation.

---

## P1 — All post-1vCPU capabilities preserved (re-affirmation of C2)

The following capabilities MUST remain reachable, functional, and visible:

| Capability | Restored home (M1+) | Backend routes |
|---|---|---|
| **Master Bot** | Monitoring → Cluster (Fleet) · Auto Factory → Compile accordion | `/api/master-bot/*` · `/api/runner/*` |
| **Auto Learning** | Monitoring → Runtime stream · Admin → Tuning · Copilot advisory | `engines/factory_supervisor/auto_learning.py` |
| **Factory Supervisor** | Monitoring → Cluster | `/api/factory-supervisor/*` · `/api/orchestrator/*` |
| **Governance** | Dashboard top · Admin → Flags · Notification Drawer (widening) | `/api/governance/*` · `/api/admin/widening-proposals` |
| **Copilot** | Global overlay (⌘J) + 💬 topbar | `/api/llm/call-log/recent` · `/api/orchestrator/heartbeat` |
| **Notifications** | Global overlay (⌘⌥N) + 🔔 topbar | `/api/monitoring/status` · `/api/admin/widening-proposals` |
| **Diagnostics** | Dashboard right-rail · Monitoring sub-tabs | `/api/monitoring/*` · `/api/latent/parity-certification/*` · `/api/latent/deployment-readiness/*` |
| **BI5 (future architecture)** | Locked 7-stage flow (Raw Ticks → Tick Archive → **Spread** → Slippage → Execution Realism → Certification → Deployment Influence) — kept architecturally separate from BID at all times | `/api/admin/bi5/*` · `/api/bi5-certification/*` |
| **cTrader (future architecture)** | Reserved layout slots in Trade Runner · Monitoring → Cluster · Portfolio · Auto Factory (Compile) | (post-RC1) |

**Rule:** any future code change that drops a capability — by removing a route, deleting an engine, hiding a UI surface, or breaking a flow — is **rejected** at PR review. The post-1vCPU recovery work is sacred.

---

## P2 — Two-customer-track model (NEW — locked TODAY)

The workstation MUST serve **both** of the following operator personas without one being a second-class citizen:

| Track A — Prop Firm Trader | Track B — Personal Capital Trader |
|---|---|
| Primary constraint: pass a prop-firm challenge | Primary constraint: long-term risk-adjusted return |
| Drawdown rules dominate (5 % daily / 10 % total) | Drawdown rules are personal (operator-set) |
| Strategy fitness measured against firm rule books | Strategy fitness measured against operator's investor mandate |
| Score surface: **Prop Firm Scorecard** | Score surface: **Investor Scorecard** |
| Deployment target: FTMO / MFF / 5%ers / 20+ firms (paper or live) | Deployment target: personal cTrader account (live or demo) |
| Lifecycle step ⑥ Portfolio → step ⑦ Master Bot configured for **firm-account** broker | Lifecycle step ⑥ Portfolio → step ⑦ Master Bot configured for **personal cTrader** broker |

### Implementation reservations in M1+

- **Portfolio screen** — the "Prop-firm fitness" section already exists; M3+ also mounts an "Investor fitness" section beside it (zero-reflow).
- **Trade Runner** — the Execution-backend chip row already includes cTrader Live + cTrader Demo placeholders; Track-B operator → personal account; Track-A operator → firm account.
- **Strategy Passport (Phase 13)** — carries BOTH a Prop-Firm Scorecard AND an Investor Scorecard.
- **Auto Pricing (Phase 14)** — produces TWO prices: prop-firm subscription pricing and retail investor pricing.
- **Marketplace (Phase 15)** — filters/tags strategies as `prop-firm-suitable`, `personal-capital-suitable`, or `both`.

### Rule

ASF is **NOT a prop-firm-only platform.** Any product decision (UI, scoring, ranking, pricing, marketplace) that silently optimises only for prop firms at the expense of personal-capital traders is a **violation of P2**.

---

## P3 — Future-phase insertion points (re-affirmation of C7)

`/app/memory/visual_approval_package/10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md` is the source of truth. M1 implementation must not foreclose:

- Strategy Dossier Engine (Phase 13) → Explorer right-pane upgrade reserved
- Automated Valuation Engine (Phase 14) → Portfolio scorecard + Compute-Price button reserved
- Strategy Marketplace (Phase 15) → MORE-menu slot reserved (`marketplace-strategies`)
- Master Bot Marketplace (Phase 15) → MORE-menu slot reserved (`marketplace-masterbots`)

**Lifecycle Rail (built in M1) ships with 10 pills.** The rail's data is a simple array — Phase 13 lands 3 new pills (⑤a · ⑤b · ⑤c) by appending to that array. No rail refactor required.

---

## P4 — Explorer → Strategy Passport evolution (NEW — locked TODAY)

Explorer is currently a research lookup tool. It MUST evolve (by Phase 13 landing) into a **commercial-grade Strategy Passport** carrying the following evidence per strategy:

| Section | Source | Surface |
|---|---|---|
| **Backtest evidence** | `backtest_engine.py` runs · archived per cohort | top KPI grid + equity curve thumb |
| **Walk-forward evidence** | `walk_forward_engine.py` · per-fold table | dedicated WF card |
| **OOS evidence** | `oos_holdout.py` · last-20% never-seen | OOS verdict chip + delta-to-IS |
| **Monte Carlo evidence** | `monte_carlo_engine.py` · 1k+ trade-resampling runs | distribution histogram + 5/50/95-pct chips |
| **Regime analysis** | `regime_classifier.py` · per-regime PnL | regime fit heatmap |
| **Pair compatibility** | cross-symbol transfer matrix | compatibility heatmap (7×7) |
| **Timeframe compatibility** | cross-TF transfer matrix | compatibility heatmap (6×6) |
| **BI5 realism certification** | (post BI5 R2) — slippage / spread / latency-attached verdict | verdict chip + slippage histogram |
| **Forward-test history** | paper-execution + tradeRunner trail post-promotion | per-day PnL series + drawdown thumb |
| **Live deployment history** | Master Bot runner ledger | per-deployment timeline + capital at risk |
| **Risk profile** | computed from MaxDD + tail-loss + Sharpe + Calmar | 5-axis radar chart |
| **Expected monthly return range** | bootstrap from full history · 5/50/95-pct envelope | numeric range + range-bar visualisation |

### Implementation reservations

In M1: Explorer's current right pane (deep-dive) layout MUST be preserved exactly. M2–M3 add the Strategy Passport sections incrementally **without re-layout** so Phase 13 plugs in cleanly.

### Reverse compatibility

A Strategy Passport is **operator-visible at every lifecycle step from ⑤ Select onwards.** Future Marketplace listings render the Passport as the canonical strategy detail page. Phase 13 ships the indexer; the workstation surfaces are reserved now.

---

## P5 — Automated Pricing = quality-score-driven (NEW — locked TODAY)

The Phase 14 **Automated Pricing Engine** computes prices from **system-generated quality scores**, not operator-set markups.

| Input signal | Weight tier |
|---|---|
| Sharpe (30/90/365 d) | T1 — primary |
| Calmar / MAR | T1 — primary |
| Max drawdown (historical + Monte Carlo p99) | T1 — primary |
| Trade count + statistical significance | T1 — primary |
| BI5 realism certification verdict | T1 — primary |
| Walk-forward score | T2 — secondary |
| Pair / TF compatibility breadth | T2 — secondary |
| Regime robustness | T2 — secondary |
| Capacity (price-impact-aware) | T2 — secondary |
| Forward-test history match to backtest | T1 — primary |
| Live deployment history (longevity + survivor bias correction) | T1 — primary |
| Prop-firm fitness (per major firm) | T3 — modifier |
| Investor fitness | T3 — modifier |
| Exclusivity / scarcity | T3 — modifier |

Operator can NUDGE pricing (e.g., +/- 20 % override) but the canonical price is **computed**.

### Why this matters now

- M1 wires `modulesRegistry.js` such that the future `valuation` module slot is reserved.
- M2/M3 lay out Portfolio screen so the "compute price" button has a docked location.
- No manual-pricing fields are introduced anywhere in the restoration — even as placeholders — to prevent muscle-memory drift.

---

## P6 — Continue dark-only (re-affirmation of C1)

`/app/memory/visual_approval_package/11_THEMETOGGLE_REMOVAL.md` is final.

- No light theme.
- No ThemeToggle.
- No `[data-theme]` attribute on `<html>` other than `"dark"` (M0 ensures this; M5 smoke probe verifies).
- All future code must NOT re-introduce conditional theme paths.

---

## Acceptance gate for M1

M1 implementation is acceptable only if:

1. ✅ All 9 capabilities in P1 reach their declared homes (or reserved homes pending M2-M3).
2. ✅ Lifecycle Rail data array has exactly 10 entries (no Phase-13/14/15 hardcoding).
3. ✅ Portfolio screen layout reserves the **two scorecard slots** (Prop Firm + Investor).
4. ✅ Trade Runner layout reserves the **personal cTrader broker chip** alongside the prop-firm/paper chips.
5. ✅ Explorer right pane layout reserved EXACTLY per `09_OPERATOR_LIFECYCLE.md` (no shrinkage; no breakup).
6. ✅ No manual-pricing fields introduced anywhere.
7. ✅ No light-theme code path re-introduced. `data-theme` attribute is `"dark"` post-boot.

If any gate fails → roll back M1, re-plan.

— End of M1 PRINCIPLES LOCK —
