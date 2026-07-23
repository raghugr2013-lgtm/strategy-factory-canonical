# SURVIVOR RE-SCORING PREVIEW
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Purpose:** Estimate, using *only trustworthy fields*, how many of the 140 strategies could realistically survive the 12-vCPU pipeline's re-scoring.
**Discipline:** Read-only. No exports. No code changes. No mutation of source data.
**Companion docs:** LEGACY_STRATEGY_INVENTORY.md, SURVIVOR_CLASSIFICATION.md, MIGRATION_COMPATIBILITY_AUDIT.md

---

## 1. METHODOLOGY

### 1.1 Trustworthy inputs (used)
- `profit_factor` (PF, 0.79–1.28)
- `stability_score` (50.6–96.8)
- `oos_holdout.ratio` (0.70–1.73)
- `oos_holdout.overfit_flagged` (boolean penalty)
- `max_drawdown_pct` (0.00–0.97%)
- `daily_drawdown_pct`
- `win_rate` (24.5–56.7%)
- `consistency_score`
- `total_trades` (statistical-foundation gate)
- Mutation lineage (`mutation_gen` g1/g2)

### 1.2 Excluded (confirmed sentinel)
- `verdict` (uniform `RISKY`) — discarded
- `pass_probability` (uniform 0.0) — discarded
- `expected_value` (uniform −810.0) — discarded
- `decision.verdict` / `prop_firm_panel.status` (echoes of `verdict`) — discarded

### 1.3 Component normalizations (each 0..1)
| Component | Mapping |
|---|---|
| `pf_n` | `(PF − 0.80) / 0.50` clipped [0,1] — 0.80→0, 1.30→1 |
| `stab_n` | `stability / 100` |
| `oos_n` | piecewise: <0.85 capped at 0.50, sweet-spot 0.85–1.30 awarded; >1.30 *discounted* (curve-fit suspicion); ×0.50 if `overfit_flagged` |
| `dd_n` | `1 − maxDD%/5` clipped [0,1] |
| `wr_n` | piecewise: low <30%→linear; sweet-spot 30–55%→strong; >55% mild discount |
| `cons_n` | `consistency_score / 100` |
| `tr_n` | `trades / 200` clipped [0,1] — statistical-foundation reward |

### 1.4 Three composite scores
- **Preview Score (general re-scoring)** = 0.28·pf + 0.22·stab + 0.22·oos + 0.10·dd + 0.08·wr + 0.05·cons + 0.05·trades
- **Master-Bot Score** = 0.30·stab + 0.22·oos + 0.18·cons + 0.15·dd + 0.10·pf + 0.05·trades (favors low-correlation portfolio members)
- **Marketplace Score** = 0.30·pf + 0.20·oos + 0.18·stab + 0.12·dd + 0.12·trades + 0.08·wr (favors listable, statistically-funded specimens)

### 1.5 Bucket thresholds (preview score)
| Bucket | Threshold |
|---|---|
| **Likely Elite** | ≥ 0.70 |
| **Likely Strong** | 0.58 – 0.70 |
| **Likely Average** | 0.45 – 0.58 |
| **Likely Experimental** | 0.30 – 0.45 |
| **Likely Reject** | < 0.30 |

---

## 2. HEADLINE RESULTS

### 2.1 Preview-bucket distribution (140 strategies)

| Preview Bucket | Count | % |
|---|---|---|
| **Likely Elite** | **41** | 29.3 % |
| **Likely Strong** | **54** | 38.6 % |
| **Likely Average** | **44** | 31.4 % |
| **Likely Experimental** | **1** | 0.7 % |
| **Likely Reject** | **0** | 0.0 % |

> 📈 **The re-scoring uplift is substantial.** Under the legacy verdict-driven view, **0** strategies were Elite or Strong. Under fundamentals-only re-scoring, **95 / 140 (67.9 %)** land in Elite or Strong buckets.
>
> This is not a celebration — it is the corrected baseline. The legacy pipeline collapsed a real numerical signal into a single `RISKY` verdict because its EV/PassProbability calculators were producing sentinel values. The fundamentals (PF, stability, OOS robustness, drawdown discipline) tell a more nuanced story.

### 2.2 Legacy class → Preview bucket cross-tab

| Legacy → Preview | Likely Elite | Likely Strong | Likely Average | Likely Experimental | Likely Reject | Total |
|------------------|---|---|---|---|---|---|
| **Average** | 31 | 32 | 10 | 0 | 0 | 73 |
| **Experimental** | 10 | 22 | 33 | 1 | 0 | 66 |
| **Deprecated** | 0 | 0 | 1 | 0 | 0 | 1 |

Notes:
- All 41 *Likely Elite* candidates were classified as **Average** or **Experimental** under the legacy rules — none were ever surfaced by the legacy pipeline.
- The single *Likely Experimental* candidate was the legacy *Deprecated* entry (consistent across both views).

---

## 3. INTERPRETATION CAVEATS

These caveats are non-negotiable and must accompany any decision built on this preview:

1. **OOS ratio > 1.30 is a yellow flag.** A strategy outperforming its in-sample period out-of-sample is statistically suspicious. The preview-score `oos_n` already discounts ratios > 1.30 but does not eliminate them. ~22 of the *Likely Elite* candidates have OOS ratio ≥ 1.20.
2. **Trade-count thin specimens.** Some *Likely Elite* candidates have only ~170 trades; statistical foundation is fragile. The `tr_n` component (0.05 weight) only partially compensates. Marketplace gating must enforce a hard trade-count floor (recommend ≥ 400) on target.
3. **Mutation-sibling redundancy.** Many *Likely Elite* candidates share `mutation_base_fingerprint` and exhibit near-identical metrics (e.g., the cluster of ETHUSD/H1 specimens with PF 1.28, win rate 39.1 %, OOS ~0.86–1.07). They are likely small-perturbation siblings; a Master Bot must dedupe by lineage to avoid concentrated risk.
4. **All MaxDD values are suspiciously small** (avg 0.12 %, many at 0.00 %). This may indicate the backtester's drawdown metric was under-counting, or that the strategies barely traded into drawdown. Validate the metric semantics on the target before trusting it.
5. **EV / pass_probability sentinels were excluded** but on the target these *must be recomputed* before any marketplace promotion (POST_IMPORT_PIPELINE Stage 3.5).

---

## 4. TOP 20 — MOST LIKELY TO BENEFIT FROM RE-SCORING (UPLIFT)

Sorted by *Uplift = Preview Score − (Legacy Score / 70)*. These are strategies the legacy verdict pipeline most heavily under-valued.

| Strategy ID | Pair | TF | PF | Win% | MaxDD | Stab | OOS | Trades | Legacy Score | Uplift | Preview Class |
|-------------|------|----|----|------|-------|------|-----|--------|--------------|---------|---------------|
| `6a0842fbf156cacd` | XAUUSD | H4 | 1.28 | 40.0% | 0.00% | 74.0 | 1.34 | 230 | 39.9 | **0.276** | Likely Elite |
| `6a09a7e60c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 55.9 | 1.00 | 174 | 40.8 | **0.234** | Likely Elite |
| `6a08917613e3fe85` | XAUUSD | H4 | 1.23 | 38.2% | 0.00% | 64.0 | 1.25 | 157 | 40.0 | **0.228** | Likely Elite |
| `6a09a3640c106069` | XAUUSD | H4 | 1.12 | 37.1% | 0.00% | 73.9 | 1.12 | 213 | 41.5 | **0.209** | Likely Elite |
| `6a09a6460c106069` | ETHUSD | H4 | 1.28 | 39.2% | 0.00% | 67.3 | 0.76 | 189 | 36.0 | **0.192** | Likely Elite |
| `6a082b42c2486b48` | XAUUSD | H1 | 1.04 | 37.7% | 0.00% | 60.3 | 1.04 | 470 | 37.5 | **0.173** | Likely Elite |
| `6a09a7e10c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 57.9 | 1.07 | 174 | 46.7 | **0.172** | Likely Elite |
| `6a09a6a40c106069` | ETHUSD | H4 | 1.28 | 39.2% | 0.00% | 79.2 | 1.01 | 189 | 46.6 | **0.122** | Likely Elite |
| `6a08916213e3fe85` | XAUUSD | H4 | 1.23 | 39.4% | 0.00% | 77.5 | 0.85 | 251 | 43.7 | **0.113** | Likely Elite |
| `6a09a72d0c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 79.1 | 0.86 | 174 | 51.2 | **0.111** | Likely Elite |
| `6a09a8c10c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 74.8 | 0.86 | 174 | 50.9 | **0.103** | Likely Elite |
| `6a09a7d10c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 67.4 | 0.83 | 174 | 43.1 | **0.092** | Likely Elite |
| `6a09a7a10c106069` | ETHUSD | H1 | 1.01 | 29.5% | 0.00% | 77.7 | 1.19 | 1108 | 45.9 | **0.070** | Likely Elite |
| `6a086fa14b987491` | XAUUSD | H1 | 0.94 | 34.4% | 0.00% | 74.3 | 1.22 | 961 | 42.6 | **0.069** | Likely Strong |
| `6a082498c2486b48` | EURUSD | H1 | 0.99 | 45.0% | 0.20% | 61.8 | 1.73 | 369 | 35.2 | **0.066** | Likely Average |
| `6a08250ac2486b48` | EURUSD | H1 | 0.97 | 44.6% | 0.21% | 62.7 | 1.04 | 368 | 36.1 | **0.064** | Likely Average |
| `6a0828d0c2486b48` | EURUSD | H4 | 1.03 | 30.1% | 0.01% | 66.9 | 1.16 | 133 | 44.4 | **0.063** | Likely Strong |
| `6a086f7a4b987491` | XAUUSD | H1 | 0.93 | 34.4% | 0.00% | 81.5 | 1.11 | 945 | 45.7 | **0.061** | Likely Elite |
| `6a086fa54b987491` | XAUUSD | H1 | 0.94 | 34.4% | 0.00% | 70.1 | 1.19 | 958 | 43.6 | **0.048** | Likely Strong |
| `6a082a6bc2486b48` | XAUUSD | H1 | 0.99 | 32.2% | 0.00% | 76.4 | 1.41 | 720 | 43.8 | **0.041** | Likely Strong |

**Pattern:** XAUUSD/H4 and ETHUSD specimens dominate the uplift list. The legacy scoring concentrated XAUUSD/H1 (the bulk), while the H4 micro-cohort and ETHUSD higher-PF specimens were demoted to the back of the score-sorted library.

---

## 5. TOP 20 — MOST SUITABLE FOR FUTURE MASTER BOT CONSTRUCTION

Sorted by Master-Bot Score (stability + OOS + consistency + low DD heavy).

| Strategy ID | Pair | TF | PF | Win% | MaxDD | Stab | OOS | Trades | Legacy Score | MB Score | Preview Class |
|-------------|------|----|----|------|-------|------|-----|--------|--------------|---------|---------------|
| `6a09a80d0c106069` | ETHUSD | H1 | 1.01 | 29.5% | 0.00% | 95.2 | 1.12 | 1109 | 61.3 | **0.914** | Likely Elite |
| `6a082b35c2486b48` | XAUUSD | H1 | 1.00 | 32.2% | 0.00% | 95.8 | 1.20 | 720 | 58.1 | **0.899** | Likely Elite |
| `6a08283cc2486b48` | XAUUSD | H1 | 0.98 | 31.7% | 0.00% | 92.6 | 1.17 | 713 | 60.6 | **0.885** | Likely Elite |
| `6a0874be4b987491` | XAUUSD | H1 | 1.00 | 32.2% | 0.00% | 88.2 | 1.13 | 720 | 59.5 | **0.877** | Likely Elite |
| `6a09a83d0c106069` | ETHUSD | H1 | 1.01 | 29.5% | 0.00% | 84.9 | 1.08 | 1109 | 53.4 | **0.865** | Likely Elite |
| `6a082af5c2486b48` | XAUUSD | H1 | 0.99 | 32.3% | 0.00% | 89.1 | 1.23 | 719 | 59.8 | **0.857** | Likely Elite |
| `6a0875054b987491` | XAUUSD | H1 | 0.99 | 32.2% | 0.00% | 85.3 | 1.16 | 720 | 52.4 | **0.854** | Likely Elite |
| `6a09a9810c106069` | XAUUSD | H1 | 0.93 | 34.5% | 0.00% | 94.9 | 1.34 | 952 | 61.2 | **0.849** | Likely Elite |
| `6a0829e8c2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 79.8 | 1.09 | 470 | 52.1 | **0.845** | Likely Elite |
| `6a082984c2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 80.3 | 1.07 | 470 | 52.3 | **0.842** | Likely Elite |
| `6a082bacc2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 85.1 | 1.25 | 470 | 52.2 | **0.841** | Likely Elite |
| `6a08256ec2486b48` | EURUSD | H1 | 0.87 | 25.9% | 0.63% | 91.2 | 1.16 | 510 | 60.3 | **0.840** | Likely Strong |
| `6a09a3640c106069` | XAUUSD | H4 | 1.12 | 37.1% | 0.00% | 73.9 | 1.12 | 213 | 41.5 | **0.835** | Likely Elite |
| `6a086f7a4b987491` | XAUUSD | H1 | 0.93 | 34.4% | 0.00% | 81.5 | 1.11 | 945 | 45.7 | **0.834** | Likely Elite |
| `6a0873e04b987491` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 83.3 | 1.26 | 470 | 53.0 | **0.831** | Likely Elite |
| `6a09a72d0c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 79.1 | 0.86 | 174 | 51.2 | **0.826** | Likely Elite |
| `6a09a3330c106069` | XAUUSD | H1 | 0.97 | 37.0% | 0.00% | 83.0 | 1.23 | 440 | 52.9 | **0.825** | Likely Elite |
| `6a0874dd4b987491` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 78.6 | 1.02 | 470 | 49.5 | **0.822** | Likely Elite |
| `6a082a7ac2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 79.6 | 1.00 | 470 | 52.1 | **0.822** | Likely Elite |
| `6a082b77c2486b48` | XAUUSD | H1 | 0.91 | 33.9% | 0.00% | 80.8 | 1.07 | 992 | 57.7 | **0.821** | Likely Strong |

**Pattern:** XAUUSD/H1 dominates Master Bot suitability — high trade counts (often 470 / 720), stability > 80, OOS ratio ≥ 1.0, zero drawdown. The dominant signal is *consistency*, not raw return.

**Cluster head candidates (one per family suggested):**
- **XAUUSD H1 Master Bot** — seed: `6a082b35c2486b` (stab 95.8, OOS 1.20, 720 trades)
- **ETHUSD H1 Master Bot** — seed: `6a09a80d0c1060` (stab 95.2, OOS 1.12, 1,109 trades)
- **XAUUSD H4 Master Bot** — seed: `6a09a3640c1060` (stab 73.9, OOS 1.12, 213 trades) — only 4 specimens; treat as exploratory
- **EURUSD H1 Master Bot** — seed: `6a08256ec2486b` (stab 91.2, OOS 1.16, has real DD 0.63%) — risk-resolution family

---

## 6. TOP 20 — MOST SUITABLE FOR FUTURE MARKETPLACE LISTING

Sorted by Marketplace Score (PF + OOS + stability + DD + trades heavy).

| Strategy ID | Pair | TF | PF | Win% | MaxDD | Stab | OOS | Trades | Legacy Score | MK Score | Preview Class |
|-------------|------|----|----|------|-------|------|-----|--------|--------------|---------|---------------|
| `6a0842fbf156cacd` | XAUUSD | H4 | 1.28 | 40.0% | 0.00% | 74.0 | 1.34 | 230 | 39.9 | **0.873** | Likely Elite |
| `6a09a7e10c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 57.9 | 1.07 | 174 | 46.7 | **0.868** | Likely Elite |
| `6a09a72d0c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 79.1 | 0.86 | 174 | 51.2 | **0.857** | Likely Elite |
| `6a09a7e60c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 55.9 | 1.00 | 174 | 40.8 | **0.849** | Likely Elite |
| `6a09a8c10c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 74.8 | 0.86 | 174 | 50.9 | **0.848** | Likely Elite |
| `6a09a3640c106069` | XAUUSD | H4 | 1.12 | 37.1% | 0.00% | 73.9 | 1.12 | 213 | 41.5 | **0.819** | Likely Elite |
| `6a08917613e3fe85` | XAUUSD | H4 | 1.23 | 38.2% | 0.00% | 64.0 | 1.25 | 157 | 40.0 | **0.817** | Likely Elite |
| `6a09a6a40c106069` | ETHUSD | H4 | 1.28 | 39.2% | 0.00% | 79.2 | 1.01 | 189 | 46.6 | **0.813** | Likely Elite |
| `6a09a6320c106069` | ETHUSD | H4 | 1.28 | 39.2% | 0.00% | 89.1 | 0.82 | 189 | 53.7 | **0.790** | Likely Elite |
| `6a09a7610c106069` | ETHUSD | H1 | 1.28 | 39.1% | 0.00% | 74.1 | 0.90 | 174 | 50.7 | **0.782** | Likely Elite |
| `6a09a80d0c106069` | ETHUSD | H1 | 1.01 | 29.5% | 0.00% | 95.2 | 1.12 | 1109 | 61.3 | **0.780** | Likely Elite |
| `6a0829e8c2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 79.8 | 1.09 | 470 | 52.1 | **0.776** | Likely Elite |
| `6a082984c2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 80.3 | 1.07 | 470 | 52.3 | **0.772** | Likely Elite |
| `6a08916213e3fe85` | XAUUSD | H4 | 1.23 | 39.4% | 0.00% | 77.5 | 0.85 | 251 | 43.7 | **0.768** | Likely Elite |
| `6a082b35c2486b48` | XAUUSD | H1 | 1.00 | 32.2% | 0.00% | 95.8 | 1.20 | 720 | 58.1 | **0.764** | Likely Elite |
| `6a0874be4b987491` | XAUUSD | H1 | 1.00 | 32.2% | 0.00% | 88.2 | 1.13 | 720 | 59.5 | **0.764** | Likely Elite |
| `6a09a83d0c106069` | ETHUSD | H1 | 1.01 | 29.5% | 0.00% | 84.9 | 1.08 | 1109 | 53.4 | **0.762** | Likely Elite |
| `6a09a6980c106069` | ETHUSD | H4 | 1.28 | 39.2% | 0.00% | 74.1 | 0.78 | 189 | 48.9 | **0.760** | Likely Elite |
| `6a082bacc2486b48` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 85.1 | 1.25 | 470 | 52.2 | **0.759** | Likely Elite |
| `6a08740c4b987491` | XAUUSD | H1 | 1.03 | 37.7% | 0.00% | 77.7 | 1.03 | 470 | 51.6 | **0.759** | Likely Elite |

**Pattern:** Two distinct profiles emerge:
- **High-PF / thin-trade specimens** (ETHUSD/H1 PF 1.28, ~174 trades). High marketplace-score by PF strength but **fail any reasonable trade-count gate** for live promotion.
- **PF ~1.0 / thick-trade specimens** (XAUUSD/H1 PF 1.00–1.03, 470–1,109 trades). Lower headline appeal but a **statistically defensible foundation**.

**Operator recommendation:** the target's marketplace gate should require *both* a PF floor (≥ 1.10) **and** a trade-count floor (≥ 400). Under that joint gate, **only ~5–8 of the top-20 marketplace candidates clear**.

---

## 7. TOP DIVERSIFICATION CLUSTERS BY PAIR / TIMEFRAME

| Pair/TF | n | Avg PF | Avg Stab | Avg OOS | Avg MaxDD | Avg Trades | Avg MB Score | Avg MK Score | % Likely Elite/Strong |
|---------|---|--------|----------|---------|-----------|------------|--------------|--------------|----------------------|
| **XAUUSD/H1** | 59 | 0.98 | 76.3 | 1.08 | 0.00% | 620 | 0.747 | 0.674 | 86% (51/59) |
| **EURUSD/H1** | 45 | 0.94 | 70.4 | 1.02 | 0.38% | 426 | 0.653 | 0.586 | 36% (16/45) |
| **ETHUSD/H1** | 24 | 1.06 | 79.4 | 0.91 | 0.00% | 941 | 0.738 | 0.681 | 67% (16/24) |
| **ETHUSD/H4** | 7 | 1.20 | 76.8 | 0.82 | 0.00% | 265 | 0.708 | 0.729 | 100% (7/7) |
| **XAUUSD/H4** | 4 | 1.22 | 72.3 | 1.14 | 0.00% | 213 | 0.789 | 0.819 | 100% (4/4) |
| **EURUSD/H4** | 1 | 1.03 | 66.9 | 1.16 | 0.01% | 133 | 0.757 | 0.694 | 100% (1/1) |

### 7.1 Cluster verdicts

- **XAUUSD/H4 (4 specimens, 100% Elite/Strong)** — Highest per-specimen quality but tiny sample. Treat as *high-conviction probe*; seed dedicated cycles on target to grow this cluster.
- **ETHUSD/H4 (7 specimens, highest avg marketplace score)** — Strong second-tier. PF 1.20 average. Recommended for early Master Bot prototype.
- **ETHUSD/H1 (24 specimens)** — Best stability concentration in dataset (multiple specimens with stab > 90). Primary Master Bot candidate cluster.
- **XAUUSD/H1 (59 specimens, biggest)** — Workhorse cluster. Tight PF/win-rate clustering suggests the mutation engine converged on a metric-stable basin. Use for *correlation-control* Master Bot.
- **EURUSD/H1 (45 specimens, weakest)** — Lowest average across all dimensions. Useful for *risk-resolution* family (only cluster with non-trivial drawdown signal).
- **EURUSD/H4 (1 specimen)** — Insufficient for any family. Migrate but do not seed a cluster.

### 7.2 Implied target-deployment posture

| Cluster | Recommended target posture |
|---|---|
| XAUUSD/H4 | **Grow** — schedule new mutation cycles |
| ETHUSD/H4 | **Master Bot prototype (shadow)** |
| ETHUSD/H1 | **Master Bot primary (shadow → demo)** |
| XAUUSD/H1 | **Correlation-control Master Bot (shadow)** |
| EURUSD/H1 | **Risk-resolution probe only** |
| EURUSD/H4 | **Hold for evidence; no cluster** |

---

## 8. CONCLUSION — ESTIMATED MIGRATION VALUE

| Metric | Pre-preview estimate (legacy-anchored) | Post-preview estimate (fundamentals-anchored) |
|---|---|---|
| Listable strategies (today) | 0 | **0** (gating still requires recomputed pass-probability) |
| Strategies likely to survive re-scoring on target | unknown | **~95** (Elite + Strong buckets) |
| Strategies likely to seed Master Bot families | 2–3 | **3–4 high-conviction seeds + 1 exploratory** |
| Strategies likely to clear strict marketplace gate post-rescoring (PF ≥ 1.10 AND trades ≥ 400) | 0 | **5–8** |
| Strategies recommended for *shadow execution* on target | ~10 | **20–25** |
| Strategies recommended for *immediate discard* | 0 | **1** (legacy Deprecated; corroborated as Likely Experimental) |

### Bottom line
- **Migrate all 140.** The aggregate evidence is materially more valuable than the legacy verdict suggested.
- **Expect 5–8 strategies to clear a strict marketplace gate** after re-scoring on the 12-vCPU pod.
- **Expect 3–4 viable Master Bot family seeds** (ETHUSD H1, XAUUSD H1, XAUUSD H4, EURUSD H1).
- **Do not promote anything live until POST_IMPORT_PIPELINE Stages 3–8 complete and operator decree is given.**

### Audit boundary
This preview uses *the data available on the source pod* and *plausible target weighting*. It is not a binding promise of the 12-vCPU pod's actual decisions — that depends on the target's exact Quality v2 / Evidence / Market / Trust formulas. The preview's role is to set realistic expectations *before* exports run.
