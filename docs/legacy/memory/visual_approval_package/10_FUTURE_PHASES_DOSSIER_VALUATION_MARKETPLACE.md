# 10 · Future Phases — Insertion Points (Phase 13 / 14 / 15)

> **Binding architecture lock.** Operator-mandated 2026-06-11.
> **No implementation now.** This document reserves natural insertion points
> in the restored workstation so that future phases drop in without re-flow.

---

## 1 · Future-phase definitions (verbatim from operator brief)

### Phase 13 — Strategy Dossier Engine

Comprehensive per-strategy intelligence package. Each strategy becomes a **dossier**
with a single canonical document ("Strategy Passport") + a stack of attached reports:

| Surface | Description |
|---|---|
| **Strategy Passport** | The canonical 1-page identity document per strategy. ID · lineage · regime fit · signed PF/Sharpe/Win/DD · seed · cohort · status · provenance hash. |
| **Backtest Reports** | Static historical-window result archive. Indexed by date-range + dataset version. |
| **Walk-Forward Reports** | Rolling re-fit + out-of-fit windows. WFA score, parameter drift visualisation. |
| **OOS Reports** | Hold-out evidence (e.g. last 20 % of data never seen during selection). |
| **Monte-Carlo Reports** | Trade-sequence randomisation, parameter perturbation, bootstrap resampling. |
| **Regime Reports** | Performance by regime cluster (trend · range · high-vol · low-vol · news-driven · weekend). |
| **Pair / Timeframe Compatibility Reports** | Cross-symbol + cross-TF transfer evidence (e.g. how does the strategy survive on USDCAD when fitted on EURUSD?). |
| **BI5 Realism Reports** | Slippage / spread / latency-attached fills (ties into BI5 7-stage pipeline). |
| **Forward Test Reports** | Live or paper forward evidence post-promotion. |

### Phase 14 — Automated Valuation Engine

Per-strategy + per-master-bot price signal. Drives Phase 15 (Marketplace).

| Surface | Description |
|---|---|
| **Prop Firm Scorecards** | Fitness verdict against each prop firm's rule book (FTMO · MFF · The5%ers · 21+ others). Per-firm pass/warn/fail with rationale. |
| **Investor Scorecards** | Long-term investor-grade summary: risk-adjusted return, drawdown, capacity, story narrative. |
| **Automated Pricing Engine** | Auto-derived monthly subscription / one-shot price from track record, capacity, prop-firm fit and exclusivity. |

### Phase 15 — Marketplace Layer

Public-facing exposure of certified strategies + master bots.

| Surface | Description |
|---|---|
| **Strategy Marketplace** | Browsable catalogue of operator-published strategies. Each card = Strategy Passport thumb + price + verdicts. |
| **Master Bot Marketplace** | Pre-compiled, signed `.cbotpack` distribution. Buyers download to their own cTrader instance. |

---

## 2 · Lifecycle insertion (locked between Step ⑤ and Step ⑥)

The current lifecycle is 10 explicit steps. Phase 13/14/15 land **between Select and Portfolio**, fed by **Explorer** as the per-strategy research entry point.

```
Current   ①Market Data → ②Generate → ③Mutate → ④Validate → ⑤Select →                                        ⑥Portfolio → ⑦Master Bot → ⑧Trade Runner → ⑨Monitoring → ⑩Deployment
                                                                  ↑                                          ↑
                                                                  └── Explorer (research)                    │
                                                                                                              │
Future    ① → ② → ③ → ④ → ⑤Select →  ⑤a Dossier  →  ⑤b Valuation  →  ⑤c Marketplace  →  ⑥Portfolio → …
                                       Phase 13       Phase 14         Phase 15
```

- **⑤a Strategy Dossier (Phase 13)** — operator opens a strategy from Explorer or Auto Select → lands in the Dossier console → all 9 report kinds available as drill-down tabs.
- **⑤b Automated Valuation (Phase 14)** — Dossier-driven pricing + Prop Firm + Investor scorecards computed and surfaced.
- **⑤c Marketplace (Phase 15)** — publish flow: select dossier-certified strategies → assign pricing → publish to marketplace.

This means **post-Phase-15 the lifecycle rail grows to 13 steps** (`⑤a · ⑤b · ⑤c` inserted) — but the existing 10 steps stay locked in order and meaning. No refactor of the rail logic is required; the rail simply gains 3 new pill entries.

---

## 3 · UI insertion points reserved in the current restoration

### 3.1 Top tab roster (no new top tabs required for now)

Per C2/C3 (no new top-tab concepts), Phase 13/14/15 do **NOT** add new entries to the CORE 11 + MORE 6 roster. They surface via:

| Future surface | Reserved home in CURRENT restoration |
|---|---|
| Strategy Passport | **Explorer right pane** — the Deep-Dive pane (currently shows backtest summary + lineage + description) is the Strategy Passport in miniature. A `[Full Dossier ▸]` link is reserved at the bottom of the pane → opens the full Dossier overlay (Phase 13). |
| Backtest Reports | Workspace (More ▾) **BacktestPanel** stays the live report; Phase 13 archives every run into the Dossier. |
| Walk-Forward Reports | Workspace **ValidationPanel** already produces this output; Phase 13 indexes them per-strategy. |
| OOS Reports | Workspace **ValidationPanel**; Phase 13 stores. |
| Monte-Carlo Reports | Workspace **ValidationPanel**; Phase 13 stores. |
| Regime Reports | Workspace **StrategyAnalysis**; Phase 13 stores. |
| Pair/TF Compatibility | (NEW) — Explorer right pane "Compatibility" section reserves space; Phase 13 backs it. |
| BI5 Realism Reports | Tied to BI5 Phase R2 (Certification) + Phase 13 indexer. |
| Forward Test Reports | Trade Runner → activity history; Phase 13 promotes the rows into a per-strategy report. |
| **Prop Firm Scorecards** | **Portfolio screen → Prop-firm fitness section** (already present as a 3-row chip table). Phase 14 swaps the simple chips for full scorecards. |
| **Investor Scorecards** | Reserved as a `[Investor view ▸]` button beside `Prop-firm fitness` on Portfolio screen. |
| **Automated Pricing Engine** | Reserved as a `[Compute price ▸]` button on the Strategy Passport / Dossier surface. |
| **Strategy Marketplace** | New tab in **More ▾** menu — currently NOT mounted; slot will be added in Phase 15. Tab ID reserved: `marketplace-strategies`. |
| **Master Bot Marketplace** | New tab in **More ▾** menu — currently NOT mounted; slot will be added in Phase 15. Tab ID reserved: `marketplace-masterbots`. |

### 3.2 Explorer right-pane upgrade path (zero re-flow on Phase 13 landing)

Current Explorer right pane stack (top-to-bottom):

```
┌── Strategy header + [Open detail drawer ▸] ──┐
├── 8-up backtest KPI grid ─────────────────────┤
├── Lineage (3 generations) ────────────────────┤
├── Description (auto-narrated) ────────────────┤
└── View cBot source · Run paper-exec · Add to Portfolio
```

Future (Phase 13) right pane stack:

```
┌── Strategy Passport header + [Full Dossier ▸] ┐    ← NEW: dossier link replaces "Open detail drawer"
├── Backtest KPI grid (unchanged) ──────────────┤
├── Lineage (unchanged) ────────────────────────┤
├── Pair/TF Compatibility heatmap (NEW slot) ───┤    ← Phase 13 fills
├── Walk-Forward · OOS · Monte-Carlo card row ──┤    ← Phase 13 fills
├── Regime fit chart (NEW slot) ────────────────┤    ← Phase 13 fills
├── BI5 Realism chip + verdict ─────────────────┤    ← Phase 13 + BI5 R2 fill
├── Description (unchanged) ────────────────────┤
└── View cBot · Paper-exec · Add to Portfolio · [Compute price ▸] · [Publish ▸]    ← Phase 14/15 add 2 buttons
```

The current layout is **explicitly designed to accept these inserts without re-flow** — same column width, same card geometry, same scroll behaviour.

### 3.3 Portfolio screen upgrade path (zero re-flow on Phase 14 landing)

Current Portfolio screen has a `Prop-firm fitness` section with 3 rows. Phase 14 replaces those rows with full scorecards (multi-row card per firm + verdict + rationale link). The container height grows downward; nothing above re-flows.

### 3.4 More ▾ menu reserves 2 future slots

Phase 15 adds:

```
More ▾
├── Workspace
├── Auto Factory (Legacy)
├── Prop Firms
├── Live Tracking
├── Optimization
├── Library (N)
├── ─── divider (Phase 15+) ───       ← reserved slot
├── Strategy Marketplace               ← Phase 15
└── Master Bot Marketplace             ← Phase 15
```

The MORE menu component (`NavMoreMenu.js`) already supports arbitrary append + dividers, so this requires zero refactor — only data add.

### 3.5 Status rail reserves 1 future cluster

The bottom status rail currently has 6 dots (`orch · ingest · sched · llm · gov · kill`). Reserve **2 future positions** for `dossier:idx-N · pricing:N` (Phase 13 indexer health + Phase 14 valuation engine state).

---

## 4 · Tab-ID reservation table (Phase 15)

When Phase 15 mounts the marketplaces, these tab IDs become live:

| Tab ID | Label | Lifecycle step |
|---|---|---|
| `dossier` | Strategy Dossier (Phase 13) | ⑤a |
| `valuation` | Automated Valuation (Phase 14) | ⑤b |
| `marketplace-strategies` | Strategy Marketplace (Phase 15) | ⑤c |
| `marketplace-masterbots` | Master Bot Marketplace (Phase 15) | ⑤c |

`modulesRegistry.js` will not be edited now — but the **shape of its entries is preserved** so that the 3 future modules append cleanly.

---

## 5 · Data-model insertion points (for backend awareness)

This is operator-readable only — backend remains untouched. The future phases will introduce these collections:

| Phase | Collection (proposed) | Owner |
|---|---|---|
| 13 | `strategy_passport` | per-strategy canonical record |
| 13 | `strategy_dossier_index` | links Passport to N report blobs |
| 13 | `report_walk_forward` / `report_oos` / `report_monte_carlo` / `report_regime` / `report_compatibility` / `report_bi5_realism` / `report_forward_test` | per-strategy report stores (immutable, time-indexed) |
| 14 | `valuation_pricing` | auto-derived price per strategy / master bot |
| 14 | `propfirm_scorecard` | per (strategy, firm) tuple verdict |
| 14 | `investor_scorecard` | per (strategy) investor-grade summary |
| 15 | `marketplace_listing` | publish-state per (strategy or master bot) |
| 15 | `marketplace_purchase` | purchase / download events |

**No backend work happens now.** This is reservation only.

---

## 6 · Acceptance gate for the restoration

During M0 → M5 execution:

* The **Lifecycle Rail** keeps using 10 visible pills.
* `09_OPERATOR_LIFECYCLE.md` §3.3 (per-screen state map) carries a footnote that `⑤a · ⑤b · ⑤c` are reserved for Phase 13/14/15 — no rendering during the restoration.
* The Explorer right pane and Portfolio "Prop-firm fitness" section preserve their geometry exactly per §3.2 and §3.3 above, so Phase 13/14 inserts are zero-reflow.
* The MORE ▾ menu data list ends with a comment indicating where Phase-15 marketplaces will be appended.
* The bottom status rail leaves room for two future cluster items.

These guard-rails are enforced in the M5 smoke-probe checklist.

---

## 7 · Closure rule

After Phase 13/14/15 ship (post-RC1, post-BI5 recovery), the lifecycle reads:

```
①Market Data → ②Generate → ③Mutate → ④Validate → ⑤Select →
⑤a Strategy Dossier → ⑤b Automated Valuation → ⑤c Marketplace →
⑥Portfolio → ⑦Master Bot → ⑧Trade Runner → ⑨Monitoring → ⑩Deployment
```

…and the strategy lifecycle closes:

```
Market Data (refreshed)   →   Generation   →   …   →   Marketplace (price discovery + sale)   →   …
                                                              ↓
                                                       Trader purchase
                                                              ↓
                                                       Master Bot deployment to buyer's broker
                                                              ↓
                                                       Forward Test feedback → updates Dossier → updates Valuation
                                                              ↓
                                                       Next Generation cohort prioritises high-marketplace-yield templates
```

This is the closed-loop research → publish → trade → learn product surface the brief describes.

— End of FUTURE PHASES LOCK —
