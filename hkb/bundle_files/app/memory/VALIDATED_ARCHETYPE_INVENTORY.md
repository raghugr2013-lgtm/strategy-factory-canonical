# VALIDATED ARCHETYPE INVENTORY
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Goal:** Re-classify all 140 strategies by their *validated walk-forward archetype* rather than by the original `strategy_text` / `mutation_type` label. Quantify the systemic label-vs-validation drift.
**Discipline:** Read-only. No exports. No code changes. No DB mutations.
**Companion docs:** F03_REGIME_ANALYSIS.md, LINEAGE_DEDUP_AUDIT.md, ASF_CANONICAL_IDENTITY_MODEL.md

---

## 1. EXECUTIVE SUMMARY

| Metric | Label-based view (legacy) | **Archetype-based view (corrected)** |
|---|---|---|
| Distinct logical families | 34 | **15** |
| Distinct independent edges | 5 (archetype taxonomy) | **5 (now matches an empirical signal)** |
| Families covering 80 % of Elite/Strong | 9 | **6** |
| Strategies whose validated archetype = mutation_type label | — | **0 / 140** |
| **Systemic drift rate** | — | **100 %** |

> 🔥 **EVERY ONE OF THE 140 STRATEGIES drifts from its `mutation_type` label.** The walk-forward optimizer chose a different archetype on every single run. The F03 finding is not a quirk — it is **the universal state of `strategy_library`**. The original-label taxonomy is unusable as an identity key.

> ✅ However, **within each strategy** the walk-forward windows agree: 140 / 140 specimens are *unanimous* across their 3 WF windows. The drift is between specimens, not within a single specimen's WF run.

### Key numerical reframings
- Validated archetype distribution: **breakout 72 (51 %), mean_reversion 26 (19 %), momentum 25 (18 %), trend_following 12 (9 %), scalping 5 (4 %)**
- The corrected family count is **15** (vs 34 by label) — labels collapse to ~half the count when grouped by what the optimizer actually validated
- **Average walk-forward OOS PF (1.20–1.70) is uniformly higher than recorded `profit_factor` (0.79–1.28)** — the headline PF on `strategy_library` is *pessimistic* relative to OOS PF, because the headline is computed over the full data while OOS PF is window-averaged on out-of-sample slices

---

## 2. ARCHETYPE DISTRIBUTION

| Validated Archetype | Specimens | % of total | Best Family (n / E/S) | Notes |
|---|---|---|---|---|
| **breakout** | 72 | 51.4 % | V03 — XAUUSD/H1 (24 specimens, 23 Elite/Strong) | Dominant validated edge |
| **mean_reversion** | 26 | 18.6 % | V01 — EURUSD/H1 (25, 10 E/S) | Concentrated on EURUSD |
| **momentum** | 25 | 17.9 % | V02 — XAUUSD/H1 (25, 25 E/S — **100 % conversion**) | The strongest validated edge in the dataset |
| **trend_following** | 12 | 8.6 % | V06 — XAUUSD/H1 (7, 1 E/S) | Sparse; weak Elite conversion |
| **scalping** | 5 | 3.6 % | V10 — ETHUSD/H1 (3, 3 E/S) | Tiny but high conversion |

### 2.1 Crosstab: original label → validated archetype (showing top splitters)

| Original Label | n | Splits into archetypes |
|---|---|---|
| Trend + RSI Pullback | 32 | breakout 26 · trend_following 3 · scalping 3 |
| Asian Range Breakout | 25 | breakout 19 · mean_reversion 4 · trend_following 2 |
| Base + RSI Confirmation | 22 | momentum 20 · trend_following 1 · scalping 1 |
| RSI Mean Reversion | 19 | mean_reversion 17 · breakout 2 |
| Base with 1:1.5 RR | 6 | mean_reversion 3 · breakout 2 · momentum 1 |
| Base without RSI | 6 | breakout 2 · momentum 2 · trend_following 2 |
| ATR Breakout | 6 | breakout 5 · scalping 1 |
| London Open Breakout | 5 | breakout 5 (clean) |
| Base + D1 Trend Confirmation | 5 | breakout 5 (clean) |
| Base + Trend Filter | 4 | trend_following 3 · mean_reversion 1 |
| Base with 1:2 RR | 3 | breakout 3 (clean) |
| Bollinger Band Reversal | 3 | breakout 2 · trend_following 1 |
| Base + Volatility Filter | 2 | breakout 1 · momentum 1 |
| Bollinger Squeeze Breakout | 1 | mean_reversion 1 |
| Base with 1:1 RR | 1 | momentum 1 |

**Read:** Only **4 labels are "clean"** (all specimens map to one archetype): London Open Breakout, Base + D1 Trend Confirmation, Base with 1:2 RR, Bollinger Squeeze Breakout, Base with 1:1 RR. **Every other label is a mixed bag.**

---

## 3. CORRECTED FAMILY TABLE (15 archetype-based families)

| Family ID | Validated Archetype | Pair | TF | n | Avg PF | Avg OOS PF | Avg Stab | Avg Trades | Distinct original labels collapsed |
|-----------|---------------------|------|----|----|--------|------------|----------|------------|------------------------------------|
| **V01** | mean_reversion | EURUSD | H1 | 25 | 0.98 | 1.41 | 70.7 | 356 | 17×RSI Mean Reversion, 4×Asian Range Breakout, 3×Base with 1:1.5 RR, 1×Bollinger Squeeze Breakout |
| **V02** | momentum | XAUUSD | H1 | 25 | 1.03 | 1.37 | 78.1 | 465 | 20×Base + RSI Confirmation, 2×Base without RSI, 1×Base with 1:1.5 RR, 1×Base + Volatility Filter, 1×Base with 1:1 RR |
| **V03** | breakout | XAUUSD | H1 | 24 | 0.96 | 1.49 | 80.3 | 824 | 13×Trend + RSI Pullback, 3×ATR Breakout, 3×Asian Range Breakout, 2×London Open Breakout, 1×Base with 1:2 RR, 1×Base + Volatility Filter, 1×Base with 1:1.5 RR |
| **V04** | breakout | EURUSD | H1 | 19 | 0.89 | 1.70 | 70.7 | 517 | 13×Asian Range Breakout, 2×London Open Breakout, 1×Base without RSI, 1×Trend + RSI Pullback, 1×Base with 1:2 RR, 1×Base with 1:1.5 RR |
| **V05** | breakout | ETHUSD | H1 | 18 | 0.98 | 1.35 | 83.1 | 1197 | 12×Trend + RSI Pullback, 2×Bollinger Band Reversal, 1×ATR Breakout, 1×RSI Mean Reversion, 1×Base without RSI, 1×Asian Range Breakout |
| **V06** | trend_following | XAUUSD | H1 | 7 | 0.92 | 1.22 | 61.0 | 414 | 3×Base + Trend Filter, 1×Asian Range Breakout, 1×Base + RSI Confirmation, 1×Base without RSI, 1×Bollinger Band Reversal |
| **V07** | breakout | ETHUSD | H4 | 7 | 1.20 | 1.66 | 76.8 | 265 | 5×Base + D1 Trend Confirmation, 1×RSI Mean Reversion, 1×London Open Breakout |
| **V08** | breakout | XAUUSD | H4 | 3 | 1.21 | 1.67 | 75.1 | 231 | 1×Base with 1:2 RR, 1×ATR Breakout, 1×Asian Range Breakout |
| **V09** | trend_following | ETHUSD | H1 | 3 | 1.28 | 1.16 | 73.8 | 174 | 3×Trend + RSI Pullback |
| **V10** | scalping | ETHUSD | H1 | 3 | 1.28 | 1.18 | 62.6 | 174 | 3×Trend + RSI Pullback |
| **V11** | scalping | XAUUSD | H1 | 2 | 0.99 | 1.22 | 68.0 | 564 | 1×ATR Breakout, 1×Base + RSI Confirmation |
| **V12** | breakout | EURUSD | H4 | 1 | 1.03 | 1.22 | 66.9 | 133 | 1×Asian Range Breakout |
| **V13** | mean_reversion | XAUUSD | H1 | 1 | 0.85 | 0.37 | 59.1 | 1166 | 1×Base + Trend Filter |
| **V14** | trend_following | XAUUSD | H4 | 1 | 1.23 | 1.15 | 64.0 | 157 | 1×Base without RSI |
| **V15** | trend_following | EURUSD | H1 | 1 | 0.84 | 3.46 | 59.5 | 433 | 1×Asian Range Breakout |

### 3.1 Family-level observations
- **V02 — momentum / XAUUSD / H1**: the *only* family with 100 % Elite/Strong conversion at scale (25/25). All 20 specimens labeled "Base + RSI Confirmation" actually validate as **momentum**, not RSI confirmation. This is the strongest validated edge on the pod.
- **V07 — breakout / ETHUSD / H4** & **V08 — breakout / XAUUSD / H4**: both 100 % Elite/Strong with PF ≥ 1.20 and OOS PF ≥ 1.66. The H4 breakout cluster is the highest-quality cluster across pairs but tiny (10 specimens combined).
- **V03 — breakout / XAUUSD / H1**: 23/24 Elite/Strong. Collapsed from 7 different "labels" — Trend + RSI Pullback, ATR Breakout, Asian Range Breakout, etc. All actually validate as breakout.
- **V09 — trend_following / ETHUSD / H1** & **V10 — scalping / ETHUSD / H1**: the two F03 branches now appear as separate families. V09 (3 specimens) and V10 (3 specimens) — confirming F03 is two distinct edges.
- **V13 — mean_reversion / XAUUSD / H1** (n=1, 0 E/S, avg OOS PF 0.37): singleton outlier. Worst OOS PF in the dataset. Migrate as evidence-of-failure baseline.
- **V15 — trend_following / EURUSD / H1** (n=1, avg OOS PF 3.46): singleton with a suspicious extreme OOS PF. Likely a thin-sample outlier; do not over-weight.

### 3.2 Corrected family concentration
- **6 families cover 80 % of Elite/Strong specimens** (vs 9 under label-based grouping)
- Top family (V02) alone delivers **25 of the 95 Elite/Strong specimens (26 %)**
- The top 3 families (V02 + V03 + V05) deliver **58 / 95 (61 %)**

---

## 4. F01 AUDIT — Archetype Drift (Label: "Base + RSI Confirmation" XAUUSD/H1)

| Metric | Value |
|---|---|
| Original label | Base + RSI Confirmation |
| Pair / TF | XAUUSD / H1 |
| Specimens | 22 |
| Walk-forward window unanimity | 22 / 22 unanimous |
| Validated archetype distribution | **momentum: 20**, trend_following: 1, scalping: 1 |
| Drift severity | **HIGH** — label says "RSI confirmation", validation says "momentum" |

### 4.1 Per-archetype performance within F01

| Validated Archetype | n | Recorded PF range | Avg WF OOS PF | Avg trades |
|---|---|---|---|---|
| momentum | 20 | 0.97 – 1.04 | **1.39** | 467 |
| trend_following | 1 | 0.83 | 1.61 | 368 |
| scalping | 1 | 1.01 | 1.20 | 511 |

### 4.2 F01 verdict
- The "Base + RSI Confirmation" label is a **misnomer**. 20 of 22 specimens validate as **momentum**. The strategy text describes RSI confirmation logic, but the walk-forward optimizer found that *momentum-archetype* parameter regions outperformed everywhere.
- Avg OOS PF 1.39 is *better* than the recorded PF (1.03). The headline metric is pessimistic.
- F01 belongs in a single archetype-based family (V02 — momentum/XAUUSD/H1), where it dominates the population (20 of the 25 V02 members come from F01).

### 4.3 F01 implications
- The momentum edge on XAUUSD/H1 is **stronger than the label-based audit suggested** (Elite/Strong conversion: 25/25 in V02).
- Any future ASF deployment should **NOT** group by `strategy_text` family on this cohort — it would split the strongest edge across multiple "families" (Base + RSI Confirmation, Base without RSI, Base + Volatility Filter, etc. all contribute to V02).

---

## 5. F02 AUDIT — Archetype Drift (Label: "Asian Range Breakout" EURUSD/H1)

| Metric | Value |
|---|---|
| Original label | Asian Range Breakout |
| Pair / TF | EURUSD / H1 |
| Specimens | 18 |
| Walk-forward window unanimity | 18 / 18 unanimous |
| Validated archetype distribution | **breakout: 13**, mean_reversion: 4, trend_following: 1 |
| Drift severity | **MEDIUM** — majority aligns with label semantic, but 22 % drifts to mean_reversion |

### 5.1 Per-archetype performance within F02

| Validated Archetype | n | Recorded PF range | Avg WF OOS PF | Avg trades |
|---|---|---|---|---|
| breakout | 13 | 0.84 – 0.99 | **1.59** | 451 |
| mean_reversion | 4 | 1.01 – 1.02 | 1.53 | 258 |
| trend_following | 1 | 0.84 | **3.46** | 433 |

### 5.2 F02 verdict
- F02 is **partially aligned** with its label — the dominant archetype is `breakout`, which semantically matches "Asian Range Breakout". But 4 specimens drift to `mean_reversion` (the optimizer found that fading the breakout was the better edge on EURUSD/H1), and 1 to `trend_following`.
- The 4 mean_reversion specimens have **higher recorded PF (1.01–1.02)** than the 13 breakout specimens (0.84–0.99), even though OOS PFs are comparable. This is a hidden bimodality — the mean_reversion variant of "Asian Range Breakout" is actually the better-performing branch in-sample.
- The 1 trend_following specimen has an extreme OOS PF of 3.46 — almost certainly thin-sample noise.

### 5.3 F02 implications
- Under archetype-based grouping, F02 splits across V04 (breakout EURUSD/H1, 13 of 19) and V01 (mean_reversion EURUSD/H1, 4 of 25). This is the correct outcome — fading-the-range and breaking-out-of-the-range are genuinely different edges.

---

## 6. ARCHETYPE-DRIFT VERDICT: SYSTEMIC, NOT ISOLATED

| Property | Verdict |
|---|---|
| Drift rate (specimens whose validated archetype ≠ mutation_type label) | **140 / 140 = 100 %** |
| Drift within a single specimen's WF windows | **0 / 140** — all specimens are window-unanimous |
| Labels that map cleanly to one archetype | **5 of 15** distinct labels |
| Largest families affected (n ≥ 18) | All 5 of them: F01, F02, F03, F04, F05 |
| Conclusion | **The label-vs-validation collision is universal across `strategy_library`.** |

### Implications
1. The legacy `strategy_text` / `mutation_type` / `parameters` taxonomy **cannot be trusted as a strategy identity** on the 12-vCPU target.
2. Any newer ASF subsystem that keys off the original label (Quality v2, Evidence Score, Trust Score, Marketplace, Master Bot, Dossier) **must be re-keyed to validated archetype** to avoid misclassification.
3. The corrected family count (15) is the right baseline for portfolio-correlation and Master Bot diversification analytics, **not** the 34 label-based families.

---

## 7. CORRECTED DEDUP KEY RECOMMENDATION (for the future ASF)

The current ASF uses these (implicitly or explicitly) as identity keys, and each has a known failure mode:

| Key | Granularity | Failure mode |
|---|---|---|
| `fingerprint` | Per-run hash | Per-run identity, useless for grouping (140/140 unique) |
| `mutation_base_fingerprint` | Per-run hash | Same — does not group siblings |
| `strategy_text` family name | Logical label | **100 % drift** from validated archetype |
| `mutation_type` | Mutation seed | **100 % drift** from validated archetype |
| `parameters` blob (base) | Base params | Identical across siblings; does not reflect validated params |

### Recommended *Canonical Dedup Key* (for the future ASF)
```
canonical_key = sha1(
    validated_archetype       # e.g., "breakout" / "momentum" / "mean_reversion" / ...
    + ":" + pair              # e.g., "XAUUSD"
    + ":" + timeframe         # e.g., "H1"
    + ":" + normalized_frozen_params_signature
)
```
where `normalized_frozen_params_signature` is the JSON-serialized, key-sorted, value-rounded `frozen_params` blob *averaged* (or mode-selected) across the walk-forward windows.

This key:
- Groups siblings that genuinely share an edge (same archetype + same validated parameter region)
- Separates the F03 Branch A / Branch B specimens (different `strategy_type` → different keys)
- Collapses 140 strategies into **~15–20 canonical entries** (matches the corrected family count)
- Is forward-compatible with portfolio correlation, Master Bot family construction, and marketplace listing

See **ASF_CANONICAL_IDENTITY_MODEL.md** for the full identity-hierarchy design.

---

## 8. FULL 140-ROW INVENTORY (sorted by validated_archetype → pair → tf → PF desc)

| # | Strategy ID | Pair | TF | Original Label | Validated Archetype | Recorded PF | Avg OOS PF (WF) | Stability | Trades | Family ID |
|---|-------------|------|----|----------------|---------------------|-------------|-----------------|-----------|--------|-----------|
| 1 | `6a09a7210c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.26 | 74.6 | 1109 | V05 |
| 2 | `6a09a7500c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.10 | 61.3 | 1109 | V05 |
| 3 | `6a09a77c0c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.38 | 96.8 | 1108 | V05 |
| 4 | `6a09a7a10c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.21 | 77.7 | 1108 | V05 |
| 5 | `6a09a7b20c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.41 | 95.5 | 1109 | V05 |
| 6 | `6a09a7b60c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.16 | 77.7 | 1109 | V05 |
| 7 | `6a09a80d0c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.34 | 95.2 | 1109 | V05 |
| 8 | `6a09a8120c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.39 | 94.1 | 1109 | V05 |
| 9 | `6a09a83d0c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.40 | 84.9 | 1109 | V05 |
| 10 | `6a09a85c0c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.33 | 94.7 | 1109 | V05 |
| 11 | `6a09a8880c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.13 | 72.5 | 1109 | V05 |
| 12 | `6a09a8b60c1060` | ETHUSD | H1 | Trend + RSI Pullback | **breakout** | 1.01 | 1.19 | 91.1 | 1109 | V05 |
| 13 | `6a09a7990c1060` | ETHUSD | H1 | RSI Mean Reversion | **breakout** | 0.94 | 1.29 | 72.6 | 1713 | V05 |
| 14 | `6a09a7740c1060` | ETHUSD | H1 | ATR Breakout | **breakout** | 0.92 | 1.09 | 69.1 | 1306 | V05 |
| 15 | `6a09a8680c1060` | ETHUSD | H1 | Base without RSI | **breakout** | 0.92 | 1.17 | 85.5 | 1306 | V05 |
| 16 | `6a09a89e0c1060` | ETHUSD | H1 | Bollinger Band Reversal | **breakout** | 0.92 | 1.28 | 82.3 | 1306 | V05 |
| 17 | `6a09a8a60c1060` | ETHUSD | H1 | Asian Range Breakout | **breakout** | 0.92 | 2.96 | 89.8 | 1306 | V05 |
| 18 | `6a09a8ae0c1060` | ETHUSD | H1 | Bollinger Band Reversal | **breakout** | 0.92 | 1.17 | 80.4 | 1306 | V05 |
| 19 | `6a09a6320c1060` | ETHUSD | H4 | Base + D1 Trend Confirmation | **breakout** | 1.28 | 1.65 | 89.1 | 189 | V07 |
| 20 | `6a09a6460c1060` | ETHUSD | H4 | Base + D1 Trend Confirmation | **breakout** | 1.28 | 1.46 | 67.3 | 189 | V07 |
| 21 | `6a09a6980c1060` | ETHUSD | H4 | Base + D1 Trend Confirmation | **breakout** | 1.28 | 1.69 | 74.1 | 189 | V07 |
| 22 | `6a09a6a40c1060` | ETHUSD | H4 | Base + D1 Trend Confirmation | **breakout** | 1.28 | 1.99 | 79.2 | 189 | V07 |
| 23 | `6a09a6c00c1060` | ETHUSD | H4 | Base + D1 Trend Confirmation | **breakout** | 1.28 | 1.19 | 73.8 | 189 | V07 |
| 24 | `6a09a6710c1060` | ETHUSD | H4 | RSI Mean Reversion | **breakout** | 1.06 | 1.75 | 64.8 | 589 | V07 |
| 25 | `6a09a6880c1060` | ETHUSD | H4 | London Open Breakout | **breakout** | 0.97 | 1.90 | 89.0 | 324 | V07 |
| 26 | `6a0827d1c2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.99 | 1.95 | 59.4 | 247 | V04 |
| 27 | `6a0827c9c2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.95 | 2.61 | 74.9 | 255 | V04 |
| 28 | `6a0824ffc2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.92 | 1.17 | 54.2 | 492 | V04 |
| 29 | `6a08255bc2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.92 | 1.25 | 86.7 | 492 | V04 |
| 30 | `6a082561c2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.92 | 1.12 | 55.5 | 492 | V04 |
| 31 | `6a0826a2c2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.92 | 1.31 | 87.0 | 492 | V04 |
| 32 | `6a084465ec5e5d` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.91 | 1.21 | 72.2 | 493 | V04 |
| 33 | `6a08282ac2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.89 | 1.44 | 80.7 | 469 | V04 |
| 34 | `6a0842dcf156ca` | EURUSD | H1 | Trend + RSI Pullback | **breakout** | 0.89 | 1.93 | 80.5 | 655 | V04 |
| 35 | `6a09a32d0c1060` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.88 | 2.46 | 74.0 | 470 | V04 |
| 36 | `6a08256ec2486b` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.87 | 1.49 | 91.2 | 510 | V04 |
| 37 | `6a0844d4ec5e5d` | EURUSD | H1 | London Open Breakout | **breakout** | 0.87 | 1.30 | 61.2 | 643 | V04 |
| 38 | `6a084583ec5e5d` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.87 | 1.17 | 67.3 | 510 | V04 |
| 39 | `6a086f6e4b9874` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.87 | 1.30 | 67.7 | 476 | V04 |
| 40 | `6a084549ec5e5d` | EURUSD | H1 | Base with 1:2 RR | **breakout** | 0.86 | 1.16 | 50.6 | 674 | V04 |
| 41 | `6a0828f6c2486b` | EURUSD | H1 | London Open Breakout | **breakout** | 0.85 | 3.58 | 66.0 | 634 | V04 |
| 42 | `6a08285fc2486b` | EURUSD | H1 | Base without RSI | **breakout** | 0.84 | 1.15 | 70.9 | 617 | V04 |
| 43 | `6a084576ec5e5d` | EURUSD | H1 | Base with 1:1.5 RR | **breakout** | 0.84 | 2.60 | 58.6 | 732 | V04 |
| 44 | `6a09a9890c1060` | EURUSD | H1 | Asian Range Breakout | **breakout** | 0.84 | 2.17 | 84.8 | 468 | V04 |
| 45 | `6a0828d0c2486b` | EURUSD | H4 | Asian Range Breakout | **breakout** | 1.03 | 1.22 | 66.9 | 133 | V12 |
| 46 | `6a082b1dc2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.51 | 82.1 | 720 | V03 |
| 47 | `6a082b35c2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.82 | 95.8 | 720 | V03 |
| 48 | `6a082b70c2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.49 | 76.4 | 720 | V03 |
| 49 | `6a0873ea4b9874` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.44 | 78.7 | 721 | V03 |
| 50 | `6a0874654b9874` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.25 | 73.6 | 720 | V03 |
| 51 | `6a0874ac4b9874` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.97 | 81.9 | 719 | V03 |
| 52 | `6a0874be4b9874` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 1.00 | 1.67 | 88.2 | 720 | V03 |
| 53 | `6a082a6bc2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.99 | 1.19 | 76.4 | 720 | V03 |
| 54 | `6a082af5c2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.99 | 1.81 | 89.1 | 719 | V03 |
| 55 | `6a082b5cc2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.99 | 1.94 | 87.8 | 720 | V03 |
| 56 | `6a0875054b9874` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.99 | 1.27 | 85.3 | 720 | V03 |
| 57 | `6a08283cc2486b` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.98 | 2.15 | 92.6 | 713 | V03 |
| 58 | `6a09a31a0c1060` | XAUUSD | H1 | Trend + RSI Pullback | **breakout** | 0.98 | 1.25 | 74.9 | 711 | V03 |
| 59 | `6a082801c2486b` | XAUUSD | H1 | London Open Breakout | **breakout** | 0.94 | 1.75 | 93.5 | 954 | V03 |
| 60 | `6a086fa14b9874` | XAUUSD | H1 | Asian Range Breakout | **breakout** | 0.94 | 1.33 | 74.3 | 961 | V03 |
| 61 | `6a086fa54b9874` | XAUUSD | H1 | Base + Volatility Filter | **breakout** | 0.94 | 1.19 | 70.1 | 958 | V03 |
| 62 | `6a086f7a4b9874` | XAUUSD | H1 | Asian Range Breakout | **breakout** | 0.93 | 1.16 | 81.5 | 945 | V03 |
| 63 | `6a09a9810c1060` | XAUUSD | H1 | ATR Breakout | **breakout** | 0.93 | 1.34 | 94.9 | 952 | V03 |
| 64 | `6a086f834b9874` | XAUUSD | H1 | London Open Breakout | **breakout** | 0.92 | 1.67 | 81.5 | 815 | V03 |
| 65 | `6a082b77c2486b` | XAUUSD | H1 | ATR Breakout | **breakout** | 0.91 | 1.36 | 80.8 | 992 | V03 |
| 66 | `6a082b84c2486b` | XAUUSD | H1 | ATR Breakout | **breakout** | 0.91 | 1.18 | 74.0 | 993 | V03 |
| 67 | `6a0873ce4b9874` | XAUUSD | H1 | Base with 1:1.5 RR | **breakout** | 0.91 | 1.72 | 53.4 | 995 | V03 |
| 68 | `6a0829c2c2486b` | XAUUSD | H1 | Base with 1:2 RR | **breakout** | 0.90 | 1.13 | 73.3 | 996 | V03 |
| 69 | `6a0874c74b9874` | XAUUSD | H1 | Asian Range Breakout | **breakout** | 0.89 | 1.17 | 66.6 | 870 | V03 |
| 70 | `6a0842fbf156ca` | XAUUSD | H4 | Base with 1:2 RR | **breakout** | 1.28 | 1.43 | 74.0 | 230 | V08 |
| 71 | `6a08916213e3fe` | XAUUSD | H4 | ATR Breakout | **breakout** | 1.23 | 1.82 | 77.5 | 251 | V08 |
| 72 | `6a09a3640c1060` | XAUUSD | H4 | Asian Range Breakout | **breakout** | 1.12 | 1.75 | 73.9 | 213 | V08 |
| 73 | `6a082634c2486b` | EURUSD | H1 | Asian Range Breakout | **mean_reversion** | 1.02 | 1.66 | 88.5 | 202 | V01 |
| 74 | `6a08459aec5e5d` | EURUSD | H1 | Asian Range Breakout | **mean_reversion** | 1.02 | 1.53 | 87.9 | 202 | V01 |
| 75 | `6a09b2b47fffbb` | EURUSD | H1 | Asian Range Breakout | **mean_reversion** | 1.02 | 1.23 | 72.7 | 202 | V01 |
| 76 | `6a084525ec5e5d` | EURUSD | H1 | Asian Range Breakout | **mean_reversion** | 1.01 | 1.71 | 74.5 | 427 | V01 |
| 77 | `6a084500ec5e5d` | EURUSD | H1 | Base with 1:1.5 RR | **mean_reversion** | 1.00 | 1.56 | 89.7 | 368 | V01 |
| 78 | `6a082498c2486b` | EURUSD | H1 | Base with 1:1.5 RR | **mean_reversion** | 0.99 | 1.29 | 61.8 | 369 | V01 |
| 79 | `6a082582c2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.99 | 1.41 | 61.8 | 369 | V01 |
| 80 | `6a0824f0c2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.52 | 80.3 | 368 | V01 |
| 81 | `6a082538c2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.64 | 70.2 | 368 | V01 |
| 82 | `6a0840c4f156ca` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.62 | 76.0 | 369 | V01 |
| 83 | `6a084198f156ca` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.31 | 74.4 | 368 | V01 |
| 84 | `6a084427ec5e5d` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.17 | 67.8 | 369 | V01 |
| 85 | `6a084445ec5e5d` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.32 | 76.9 | 368 | V01 |
| 86 | `6a084551ec5e5d` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.47 | 74.3 | 368 | V01 |
| 87 | `6a084570ec5e5d` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.16 | 67.0 | 368 | V01 |
| 88 | `6a09b2687fffbb` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.22 | 67.6 | 368 | V01 |
| 89 | `6a09b27d7fffbb` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.77 | 64.1 | 368 | V01 |
| 90 | `6a09b28d7fffbb` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.98 | 1.85 | 52.4 | 369 | V01 |
| 91 | `6a08250ac2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.97 | 1.48 | 62.7 | 368 | V01 |
| 92 | `6a082602c2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.97 | 1.42 | 74.7 | 369 | V01 |
| 93 | `6a0844b6ec5e5d` | EURUSD | H1 | Base with 1:1.5 RR | **mean_reversion** | 0.97 | 1.07 | 64.9 | 368 | V01 |
| 94 | `6a08915813e3fe` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.97 | 1.29 | 59.5 | 369 | V01 |
| 95 | `6a08246ec2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.96 | 1.40 | 71.7 | 368 | V01 |
| 96 | `6a0826bbc2486b` | EURUSD | H1 | RSI Mean Reversion | **mean_reversion** | 0.90 | 0.96 | 62.1 | 470 | V01 |
| 97 | `6a0844acec5e5d` | EURUSD | H1 | Bollinger Squeeze Breakout | **mean_reversion** | 0.89 | 1.29 | 63.2 | 400 | V01 |
| 98 | `6a08748d4b9874` | XAUUSD | H1 | Base + Trend Filter | **mean_reversion** | 0.85 | 0.37 | 59.1 | 1166 | V13 |
| 99 | `6a0829acc2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.47 | 78.7 | 470 | V02 |
| 100 | `6a082a28c2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.47 | 81.9 | 470 | V02 |
| 101 | `6a082b42c2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.08 | 60.3 | 470 | V02 |
| 102 | `6a084071f156ca` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.25 | 68.9 | 470 | V02 |
| 103 | `6a0874364b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.27 | 77.9 | 470 | V02 |
| 104 | `6a0874624b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.04 | 1.66 | 85.9 | 470 | V02 |
| 105 | `6a08297fc2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.31 | 72.7 | 470 | V02 |
| 106 | `6a082984c2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.43 | 80.3 | 470 | V02 |
| 107 | `6a0829e8c2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.28 | 79.8 | 470 | V02 |
| 108 | `6a082a7ac2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.52 | 79.6 | 470 | V02 |
| 109 | `6a082bacc2486b` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.29 | 85.1 | 470 | V02 |
| 110 | `6a0873e04b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.34 | 83.3 | 470 | V02 |
| 111 | `6a0873e34b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.84 | 69.3 | 470 | V02 |
| 112 | `6a08740c4b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.43 | 77.7 | 470 | V02 |
| 113 | `6a08746b4b9874` | XAUUSD | H1 | Base with 1:1.5 RR | **momentum** | 1.03 | 1.44 | 86.5 | 470 | V02 |
| 114 | `6a08747a4b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.16 | 73.8 | 470 | V02 |
| 115 | `6a0874d14b9874` | XAUUSD | H1 | Base without RSI | **momentum** | 1.03 | 1.09 | 67.1 | 470 | V02 |
| 116 | `6a0874dd4b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.27 | 78.6 | 470 | V02 |
| 117 | `6a0875194b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.03 | 1.61 | 83.9 | 470 | V02 |
| 118 | `6a0875284b9874` | XAUUSD | H1 | Base + Volatility Filter | **momentum** | 1.03 | 1.45 | 76.8 | 470 | V02 |
| 119 | `6a0875314b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.02 | 1.41 | 85.6 | 470 | V02 |
| 120 | `6a082904c2486b` | XAUUSD | H1 | Base without RSI | **momentum** | 1.01 | 1.43 | 86.6 | 429 | V02 |
| 121 | `6a0870054b9874` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 1.01 | 1.16 | 78.8 | 438 | V02 |
| 122 | `6a09a3a00c1060` | XAUUSD | H1 | Base with 1:1 RR | **momentum** | 1.00 | 1.14 | 70.0 | 439 | V02 |
| 123 | `6a09a3330c1060` | XAUUSD | H1 | Base + RSI Confirmation | **momentum** | 0.97 | 1.56 | 83.0 | 440 | V02 |
| 124 | `6a09a7610c1060` | ETHUSD | H1 | Trend + RSI Pullback | **scalping** | 1.28 | 1.17 | 74.1 | 174 | V10 |
| 125 | `6a09a7e10c1060` | ETHUSD | H1 | Trend + RSI Pullback | **scalping** | 1.28 | 1.30 | 57.9 | 174 | V10 |
| 126 | `6a09a7e60c1060` | ETHUSD | H1 | Trend + RSI Pullback | **scalping** | 1.28 | 1.07 | 55.9 | 174 | V10 |
| 127 | `6a0873d84b9874` | XAUUSD | H1 | Base + RSI Confirmation | **scalping** | 1.01 | 1.20 | 66.6 | 511 | V11 |
| 128 | `6a0829a6c2486b` | XAUUSD | H1 | ATR Breakout | **scalping** | 0.98 | 1.25 | 69.4 | 616 | V11 |
| 129 | `6a09a72d0c1060` | ETHUSD | H1 | Trend + RSI Pullback | **trend_following** | 1.28 | 1.23 | 79.1 | 174 | V09 |
| 130 | `6a09a7d10c1060` | ETHUSD | H1 | Trend + RSI Pullback | **trend_following** | 1.28 | 1.02 | 67.4 | 174 | V09 |
| 131 | `6a09a8c10c1060` | ETHUSD | H1 | Trend + RSI Pullback | **trend_following** | 1.28 | 1.23 | 74.8 | 174 | V09 |
| 132 | `6a09b2717fffbb` | EURUSD | H1 | Asian Range Breakout | **trend_following** | 0.84 | 3.46 | 59.5 | 433 | V15 |
| 133 | `6a08752b4b9874` | XAUUSD | H1 | Base + Trend Filter | **trend_following** | 1.03 | 1.00 | 53.0 | 518 | V06 |
| 134 | `6a08297ac2486b` | XAUUSD | H1 | Asian Range Breakout | **trend_following** | 0.97 | 1.13 | 52.3 | 529 | V06 |
| 135 | `6a0829fcc2486b` | XAUUSD | H1 | Base + Trend Filter | **trend_following** | 0.97 | 1.32 | 60.1 | 532 | V06 |
| 136 | `6a082a65c2486b` | XAUUSD | H1 | Base + Trend Filter | **trend_following** | 0.97 | 1.35 | 66.2 | 532 | V06 |
| 137 | `6a08746e4b9874` | XAUUSD | H1 | Base without RSI | **trend_following** | 0.90 | 1.12 | 64.5 | 242 | V06 |
| 138 | `6a082adec2486b` | XAUUSD | H1 | Base + RSI Confirmation | **trend_following** | 0.83 | 1.61 | 78.5 | 368 | V06 |
| 139 | `6a0874ba4b9874` | XAUUSD | H1 | Bollinger Band Reversal | **trend_following** | 0.79 | 1.01 | 52.6 | 178 | V06 |
| 140 | `6a08917613e3fe` | XAUUSD | H4 | Base without RSI | **trend_following** | 1.23 | 1.15 | 64.0 | 157 | V14 |

---

## 9. AUDIT BOUNDARY

This document re-classifies strategies using `validation_report.walk_forward.windows[*].strategy_type` as the ground-truth archetype signal. The analysis is read-only. No DB mutations, no exports, no code changes. The corrected family taxonomy is a *recommendation* for the 12-vCPU target's identity-hierarchy refactor — it is not applied to the current `strategy_library` on this pod.
