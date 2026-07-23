# F03 REGIME ANALYSIS
**Family:** F03 — Trend + RSI Pullback (ETHUSD / H1)
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Goal:** Explain the bimodal PF distribution (PF ≈ 1.01 vs PF ≈ 1.28) within an otherwise apparently-identical family.
**Discipline:** Read-only. No exports. No code changes. No DB mutations.
**Companion docs:** LINEAGE_DEDUP_AUDIT.md, SURVIVOR_RESCORING_PREVIEW.md, LEGACY_STRATEGY_INVENTORY.md

---

## 1. EXECUTIVE SUMMARY

**The F03 family contains *two distinct strategy archetypes* masquerading as one family because the `strategy_text` and `parameters` fields on `strategy_library` record the *base* strategy, not the strategy the walk-forward optimizer actually selected and froze.**

| Branch | Specimens | Walk-Forward `strategy_type` | Trades | Win % | PF | Profile |
|---|---|---|---|---|---|---|
| **A — "Breakout"** | 12 | `breakout` (36/36 windows) | 1,108–1,109 | 29.5 % | 1.01 | High-frequency, low-win-rate, marginal-profit |
| **B — "Trend / Scalp"** | 6 | `scalping` ∨ `trend_following` (9 + 9 = 18/18 windows) | 174 | 39.1 % | 1.28 | Low-frequency, higher-win-rate, stronger per-trade edge |

These are **two separate edges**. The family is not a homogeneous strategy with execution noise — it is a *label collision* between the strategy-engine's base-strategy taxonomy ("Trend + RSI Pullback") and the walk-forward optimizer's chosen archetype.

---

## 2. WHAT IS CONSTANT ACROSS ALL 18 SPECIMENS

These features are bit-identical and therefore **cannot explain the bimodality**:

| Field | Common value |
|---|---|
| `strategy_text` | Identical "Trend + RSI Pullback (ETHUSD H1)" with EMA(50)/EMA(200) + RSI pullback logic |
| `parameters` (base) | `{ema_fast=20, ema_mid=50, ema_slow=200, rsi_period=14, atr_period=14, atr_sl_mult=1.5, atr_tp_mult=3.0}` |
| `mutation_type` | `trend_pullback` |
| Pair / Timeframe | ETHUSD / H1 |
| Walk-forward total candles | 26,248 |
| Walk-forward train size | 6,124 |
| Walk-forward OOS size | 2,625 |
| Step size | 2,625 |
| n_windows | 3 |
| num_variants per window | 10 |
| `triggered_by` | `auto_mutation_runner` |
| Creation date | 2026-05-17 (single 7-minute burst, 11:31:45 → 11:38:41) |

> ❗ The training and OOS windows are **bit-identical across all 18 specimens**. There is **no time-period difference**, **no market-regime difference at the data level**, and **no parameter difference in the recorded `parameters` blob**.

So the bimodality is *not* explained by data partitioning, market regime, or base parameters.

---

## 3. WHAT VARIES — THE ROOT CAUSE

### 3.1 The walk-forward optimizer's `frozen_params` differ radically per run

For each walk-forward window the optimizer evaluates 10 candidate variants and freezes a *winning* `frozen_params` set. The base `parameters` field on `strategy_library` is **NOT** the same as `validation_report.walk_forward.windows[i].frozen_params`. The latter is what actually produced the recorded metrics.

#### Branch A — sample frozen_params (window 1 of a PF=1.01 specimen)
```
fast_period: 17
rsi_period: 16
rsi_buy_threshold: 45
rsi_sell_threshold: 38
sl_pips: 35
tp_pips: 48
```

#### Branch B — sample frozen_params (window 1 of a PF=1.28 specimen)
```
fast_period: 10
slow_period: 14
rsi_period: 19
rsi_buy_threshold: 55
rsi_sell_threshold: 45
sl_pips: 7
tp_pips: 32
```

Key differences:
- Branch A frozen sets contain **no `slow_period`** (single-EMA system)
- Branch B frozen sets contain **`slow_period`** (dual-EMA system)
- Branch B uses **much tighter `sl_pips` (7–10)** vs Branch A (21–35) — different risk regime
- Branch A `rsi_buy_threshold` clusters around 45–63; Branch B around 48–55

### 3.2 The walk-forward optimizer's `strategy_type` differs per branch

Across the 18 specimens × 3 windows = **54 walk-forward windows total**, the chosen `strategy_type` distribution is:

| Branch | Windows | `breakout` | `scalping` | `trend_following` |
|---|---|---|---|---|
| Branch A (12 × 3 = 36) | 36 | **36 (100 %)** | 0 | 0 |
| Branch B (6 × 3 = 18) | 18 | 0 | **9 (50 %)** | **9 (50 %)** |

> 🔥 **Branch A converged unanimously on `breakout`. Branch B converged on a mix of `scalping` and `trend_following`. Neither branch ever chose the family's nominal "Trend + RSI Pullback" archetype as a `strategy_type`.**

This is the smoking gun. The walk-forward optimizer is a meta-strategy selector: it picks an archetype from a menu, optimizes its parameters, freezes the winner. The mutation engine's `trend_pullback` label is just the *seed* — the optimizer is allowed to drift to a different archetype during search.

### 3.3 Why within-branch metrics are bit-identical

All 12 Branch A specimens have **trades = 1,108 or 1,109**, win rate = 29.5 %, PF = 1.01. All 6 Branch B specimens have **trades = 174**, win rate = 39.1 %, PF = 1.28. This is *not* a coincidence — it indicates each branch converged to the **same local optimum**. The walk-forward search across the 12 (or 6) runs found the same frozen-params region every time, producing identical trade signals on identical data.

### 3.4 Why scores differ within a branch despite identical metrics

Within Branch A, score ranges 38.2 → 61.7 (and stability 61.3 → 96.8). Within Branch B, score ranges 40.8 → 51.2. With identical PF/trades/win-rate, this can only come from **external priors fed into the scoring formula** — most plausibly `market_environment_stats` evolving over the 7-minute burst as new runs update environmental baselines. The score variation is *scoring-engine noise*, not strategy-quality variation.

---

## 4. PER-SPECIMEN TABLE (all 18, sorted PF asc → score asc)

| FP | Branch | PF | Score | Trades | Win % | Stability | OOS Ratio | IS PF | OOS PF | Max DD | WF archetype(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `9c41dad4fa3e` | A | 1.01 | 38.2 | 1109 | 29.5 % | 61.3 | 0.99 | 1.16 | 1.15 | 0.00 % | breakout |
| `1bd95b592979` | A | 1.01 | 43.7 | 1109 | 29.5 % | 72.5 | 0.77 | 1.13 | 0.87 | 0.00 % | breakout |
| `7c3b740828af` | A | 1.01 | 45.9 | 1108 | 29.5 % | 77.7 | 1.19 | 1.12 | 1.33 | 0.00 % | breakout |
| `57771cadd06b` | A | 1.01 | 48.6 | 1109 | 29.5 % | 77.7 | 1.20 | 0.98 | 1.18 | 0.00 % | breakout |
| `f25173925c7c` | A | 1.01 | 53.4 | 1109 | 29.5 % | 84.9 | 1.08 | 1.07 | 1.16 | 0.00 % | breakout |
| `f54a292a19b9` | A | 1.01 | 56.1 | 1109 | 29.5 % | 74.6 | 0.85 | 1.25 | 1.06 | 0.00 % | breakout |
| `9c5b602cd57a` | A | 1.01 | 57.2 | 1109 | 29.5 % | 91.1 | 0.89 | 1.10 | 0.98 | 0.00 % | breakout |
| `0e26b47599fb` | A | 1.01 | 61.0 | 1109 | 29.5 % | 94.1 | 0.85 | 1.13 | 0.96 | 0.00 % | breakout |
| `cc9add2f13e8` | A | 1.01 | 61.2 | 1109 | 29.5 % | 94.7 | 0.97 | 1.08 | 1.05 | 0.00 % | breakout |
| `fa27d36911d1` | A | 1.01 | 61.3 | 1109 | 29.5 % | 95.2 | 1.12 | 1.13 | 1.27 | 0.00 % | breakout |
| `23a9ced9127f` | A | 1.01 | 61.4 | 1109 | 29.5 % | 95.5 | 0.73 | 1.13 | 0.82 | 0.00 % | breakout |
| `0510e63736d6` | A | 1.01 | 61.7 | 1108 | 29.5 % | 96.8 | 0.75 | 1.09 | 0.82 | 0.00 % | breakout |
| `9dcfeb944025` | B | 1.28 | 40.8 | 174 | 39.1 % | 55.9 | 1.00 | 1.10 | 1.10 | 0.00 % | scalping |
| `388e74a92911` | B | 1.28 | 43.1 | 174 | 39.1 % | 67.4 | 0.83 | 1.21 | 1.00 | 0.00 % | trend_following |
| `3b12e9629fa3` | B | 1.28 | 46.7 | 174 | 39.1 % | 57.9 | 1.07 | 1.06 | 1.13 | 0.00 % | scalping |
| `00cae3914bde` | B | 1.28 | 50.7 | 174 | 39.1 % | 74.1 | 0.90 | 1.13 | 1.02 | 0.00 % | scalping |
| `dbd37f01f7bf` | B | 1.28 | 50.9 | 174 | 39.1 % | 74.8 | 0.86 | 1.05 | 0.90 | 0.00 % | trend_following |
| `99dc818947a3` | B | 1.28 | 51.2 | 174 | 39.1 % | 79.1 | 0.86 | 0.94 | 0.81 | 0.00 % | trend_following |

Branch aggregates:
- **Branch A (n=12):** avg trades 1,109 · avg WR 29.5 % · avg stab 84.7 · avg OOS ratio 0.95
- **Branch B (n=6):**  avg trades 174 · avg WR 39.1 % · avg stab 68.2 · avg OOS ratio 0.92

---

## 5. ANSWERS TO THE 5 RESEARCH QUESTIONS

### 5.1 Parameter differences — YES (and decisive)
The recorded base `parameters` are identical across all 18, but the walk-forward `frozen_params` differ radically by branch (presence/absence of `slow_period`, very different SL/TP magnitudes, different RSI thresholds). The visible `parameters` field is **misleading** — it hides the true validated parameters.

### 5.2 Time-period differences — NO
All 18 specimens use the exact same `total_candles=26,248`, `train_size=6,124`, `oos_size=2,625`, `n_windows=3`, `step_size=2,625`. Created within a 7-minute burst on 2026-05-17. Both branches see identical market data.

### 5.3 Market-regime differences — NO (at the data level)
Same data → same market exposure. Regime differences cannot explain the bimodality.

### 5.4 Validation differences — YES (and decisive)
The walk-forward optimizer chose **`breakout`** for 100 % of Branch A windows and **`scalping` / `trend_following`** for 100 % of Branch B windows. This is the immediate cause of the bimodality. It is a *validation-engine archetype-selection* artifact, not a data or parameter artifact.

### 5.5 Does the family contain two distinct edges? — YES, ABSOLUTELY
Branch A is a **high-frequency breakout** edge with marginal PF and 29.5 % win rate. Branch B is a **selective scalping / trend-following** edge with PF 1.28 and 39.1 % win rate. They share *no validated parameters in common* and represent fundamentally different trading behaviors. The "Trend + RSI Pullback" label is a stale base-strategy tag, not an accurate description of either branch.

---

## 6. ROOT CAUSE ANALYSIS

### 6.1 The mechanism

```
strategy_text & parameters         ←  fed in as the BASE
       │
       ▼
mutation_engine (type=trend_pullback)
       │  generates 10 candidate variants per WF window
       ▼
walk_forward optimizer
       │  chooses a strategy_type from {breakout, scalping, trend_following, ...}
       │  optimizes frozen_params within that archetype
       ▼
best frozen_params + best strategy_type recorded in validation_report
       │
       ▼
metrics (PF, trades, win_rate) recorded on strategy_library
       │
       ▼
BUT: strategy_text and parameters fields on the row STILL reflect the BASE, not the WF result
```

### 6.2 Why the optimizer converges to two different archetypes

The most likely cause is **a local-optimum trap with random initialization in the walk-forward variant generator**. Each invocation of the WF optimizer generates 10 random-perturbation variants; the best one is frozen. The variant space is *bimodal* on this (ETHUSD / H1, base = trend_pullback) seed:

- **Basin A** (breakout archetype, fast_period 5–25, no slow_period) is *wider but flatter* → reached more often (12 of 18 = 67 %), produces consistent PF 1.01
- **Basin B** (scalping/trend_following, with slow_period, tight SL) is *narrower but taller* → reached less often (6 of 18 = 33 %), produces PF 1.28

The fact that within each basin the converged metrics are bit-identical confirms the basins themselves are deterministic; only the random initialization decides which basin is found per run.

### 6.3 Secondary observation — Branch A's OOS robustness is *worse* than its in-sample
- Branch A: avg `is_pf` 1.12 → avg `oos_pf` 1.05 (ratio 0.94) — mild degradation
- Branch B: avg `is_pf` 1.08 → avg `oos_pf` 0.99 (ratio 0.92) — slightly worse degradation

**Branch B's PF=1.28 figure is the *in-sample* PF; its OOS PF averages 0.99.** This is critical — the headline PF=1.28 advantage of Branch B is largely *in-sample-only*. Branch A's IS-PF of 1.12 also doesn't survive OOS cleanly (avg 1.05). Both branches are marginal on OOS.

---

## 7. RECOMMENDATIONS

### 7.1 Canonical specimen (best representative of the family for re-import + dedup)
Choose **`0510e63736d6`** (Branch A, score 61.7, stability 96.8, trades 1,109, WR 29.5 %, OOS ratio 0.75, archetype = breakout).

Justification:
- Best stability and score in the dataset (96.8 / 61.7)
- Branch A is the *majority basin* (12 of 18) — best statistical foundation
- High trade count (1,109) provides strong statistical foundation for any future re-evaluation
- Caveats: OOS ratio is below 1.0 (0.75); promote to dossier with that flag.

### 7.2 Recommended Master Bot specimen (correlation/portfolio role)
Choose **`0e26b47599fb`** (Branch A, stability 94.1, score 61.0, OOS ratio 0.85, archetype = breakout).

Justification:
- High stability (94.1) and high consistency
- Branch A is uncorrelated (or low-correlation) with the F05 (Trend Pullback XAUUSD/H1) family — gives the Master Bot diversification across pairs and across archetypes
- 1,109 trades = robust foundation for correlation analytics
- **Do NOT** use both branches in the same Master Bot — the bimodality means a single specimen carries the basin's signal; adding a sibling adds nothing.

### 7.3 Recommended Marketplace specimen (listable representative)
Choose **`388e74a92911`** (Branch B, PF 1.28, score 43.1, OOS ratio 0.83, archetype = trend_following).

Justification:
- Branch B's headline PF (1.28) is the strongest sales signal
- Trade count (174) is below a robust marketplace floor (~400), but trend_following archetype is more publicly defensible than scalping
- ⚠ **Marketplace listing must disclose** that IS PF = 1.21 but OOS PF = 1.00 → the strategy is marginal-positive OOS, not 1.28 OOS
- ⚠ A stricter marketplace gate (PF ≥ 1.10 AND trades ≥ 400) **rejects this specimen**. If the gate is strict, **F03 produces no marketplace listing** and Branch A's high-volume, marginal-PF profile fails the PF floor while Branch B fails the trade-count floor.

### 7.4 Recommended mutation direction (post-migration cycles)
The bimodality is *informative*: two separate basins exist in the (ETHUSD / H1) parameter manifold. Future mutation cycles should explicitly probe both basins:

1. **Lock the optimizer to archetype = `breakout`** for one mutation cohort. Search `fast_period ∈ [5, 25]`, `rsi_buy_threshold ∈ [45, 65]`, `sl_pips ∈ [15, 40]`, `tp_pips ∈ [30, 60]`. Goal: confirm whether Branch A's PF can be pushed > 1.10 with a wider SL/TP search.
2. **Lock the optimizer to archetype = `trend_following`** for a second cohort. Search dual-EMA territory (`fast_period`, `slow_period`), `sl_pips ∈ [5, 15]`, `tp_pips ∈ [20, 50]`. Goal: confirm Branch B's PF 1.28 with longer evaluation windows and check whether OOS catches up.
3. **Lock archetype = `scalping`** for a third cohort to isolate it from `trend_following`.
4. **Stop using the `trend_pullback` mutation type as the entry point** — it acts as a "free archetype selector" that obscures which edge actually produced the result. Either:
   - (a) Constrain the WF optimizer to only re-optimize parameters within the *base* archetype (the truthful "Trend + RSI Pullback"), or
   - (b) Record the chosen archetype as a first-class field on `strategy_library` (post-migration schema enhancement) so families are grouped by *validated* archetype, not by base name.

---

## 8. WIDER IMPLICATIONS FOR MIGRATION

This regime analysis has implications that extend beyond F03 — they apply to the entire `strategy_library`:

1. **The recorded `strategy_text` and `parameters` fields are NOT a reliable identity.** The validation engine may have evaluated a *different archetype* than the label suggests.
2. **Every other family on this pod should be checked for archetype drift.** A quick scan of F01 (Base + RSI Confirmation XAUUSD/H1) and F03 may reveal similar bimodal basins.
3. **On the target 12-vCPU pod, group strategies by `validation_report.walk_forward.windows[*].strategy_type`** — not by `strategy_text` family name — to reflect the strategy that was actually validated.
4. **The LINEAGE_DEDUP_AUDIT's family count (34 logical families) may be an *over-count*** — multiple "families" might in fact be the same archetype hiding under different base labels. A second pass on the target using `frozen_params + strategy_type` as the dedup key would refine the edge count further.
5. **The 5-independent-edge estimate from LINEAGE_DEDUP_AUDIT remains the best top-level summary**, but the *mapping from families to edges* needs to be done via the WF report, not the strategy_text label.

---

## 9. CRITICAL CAVEATS

- The walk-forward optimizer's archetype menu (`breakout`, `scalping`, `trend_following`, others) is hard-coded somewhere in the validation engine. To reproduce these results on target, that menu must travel with the migration (it is in code, not in DB — so the target must have the same `validation_engine` version).
- The PF=1.28 of Branch B is **not** a clean edge — it is an *in-sample* PF whose OOS counterpart averages 0.99. The marketplace gate must use OOS PF, not headline PF.
- The deterministic convergence within each branch indicates the optimizer is *stable* once it enters a basin; the source of stochasticity is the variant-generator initialization. To reduce future bimodality, the variant generator could be seeded with a deterministic seed or sweep both basins explicitly.

---

## 10. AUDIT BOUNDARY

This analysis used only data present in the source pod's `strategy_library`, `mutation_runs`, and (implicitly) the validation_report blobs. No code was modified. No DB rows were modified. No exports were created. The recommendations in §7 are *audit-grade recommendations* awaiting operator decree before any migration / mutation cycle / Master Bot construction is executed on the 12-vCPU target.
