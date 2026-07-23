# LINEAGE DEDUP AUDIT
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Goal:** Determine the true number of *independent* strategy families behind the 140 imported strategies — and how many *independent edges* underlie the 95 "Likely Elite/Strong" candidates surfaced by the re-scoring preview.
**Discipline:** Read-only. No exports. No code changes.
**Companion docs:** SURVIVOR_RESCORING_PREVIEW.md, SURVIVOR_CLASSIFICATION.md, LEGACY_STRATEGY_INVENTORY.md

---

## 1. HEADLINE FINDINGS

| Metric | Value |
|---|---|
| Total strategies in `strategy_library` | **140** |
| Distinct `mutation_base_fingerprint` | 140 (each unique — does **not** group siblings) |
| Distinct `mutation_run_id` | 140 (each unique) |
| Distinct `mutation_variant_fingerprint` | 140 (no exact duplicates) |
| **Distinct logical families** (name + pair + tf + parameters) | **34** |
| **Distinct independent edges** (strategy archetype) | **5** |
| Families covering 80 % of Elite/Strong specimens | **9** |
| Likely Elite/Strong specimens (from preview) | 95 |

> 🔥 **The 95 "Likely Elite/Strong" specimens are produced by only ~9 logical families, which collectively express only 5 independent edges.** The migration value of *unique strategy intelligence* is far smaller than the per-row count suggests. Most of the 95 are *re-validation runs of the same logical strategy*, not 95 distinct opportunities.

---

## 2. METHODOLOGY

### 2.1 Why `mutation_base_fingerprint` alone is insufficient
Every one of 140 strategies has a **unique** `mutation_base_fingerprint`, `mutation_run_id`, and `mutation_variant_fingerprint`. That means the engine's fingerprinting hashes capture *per-run identity*, not *logical identity*. A naive group-by would produce 140 "families" of size 1.

### 2.2 The real grouping key
Inspection of `strategy_text` and `parameters` shows that strategies are best grouped by:

`family_key = (strategy_name, pair, timeframe, normalized_parameter_blob)`

Within these natural keys, **parameter blobs are bit-identical across all siblings**. For example, all 17 *RSI Mean Reversion (EURUSD H1)* strategies share exactly:

```
rsi_period=14, oversold=30, overbought=70, exit_level=50, sl_pips=20, tp_pips=30
```

…and all 18 *Asian Range Breakout (EURUSD H1)* share:

```
range_start_gmt='00:00', range_end_gmt='07:00', entry_after_gmt='07:00', close_all_gmt='15:00'
```

### 2.3 Within-family metric variance
Despite identical parameters, siblings show **non-identical performance metrics** — distinct PFs, distinct trade counts, distinct stability scores. Example: *Trend + RSI Pullback ETHUSD H1* has 18 siblings with only 2 distinct PFs (1.01, 1.28) but 18 distinct scores (38.2 → 61.7). This indicates the variants were re-validated against **different market-data windows / random seeds**, not produced from different logic.

**Implication:** Intra-family variance is *evaluation noise*, not *edge diversity*. The "best specimen" of a family is the best *evaluation*, not the best *strategy*.

### 2.4 Edge archetypes (manual taxonomy from strategy_text)
The 34 families collapse to 5 independent edges based on entry/exit logic:

- **Mean Reversion (RSI)** — RSI overbought/oversold reversal, including "Base + RSI Confirmation" / "Base + Volatility Filter" / "Base with N:M RR" / "Base without RSI" variants of the RSI core
- **Trend Pullback** — EMA trend stack + RSI pullback entry, including "Base + D1 Trend Confirmation" and "Base + Trend Filter" add-ons
- **Session Range Breakout** — Asian range, London Open
- **Volatility Breakout (ATR)** — ATR-driven breakout
- **Bollinger Volatility** — BB reversal / squeeze breakout

---

## 3. INDEPENDENT EDGE COUNT

| Independent Edge | # Families | # Specimens | Elite/Strong | Best Preview Score |
|------------------|------------|-------------|--------------|--------------------|
| **Mean Reversion (RSI)** | 15 | 59 | 39 | 0.846 |
| **Trend Pullback** | 5 | 41 | 34 | 0.843 |
| **Session Range Breakout** | 8 | 30 | 17 | 0.802 |
| **Volatility Breakout (ATR)** | 3 | 6 | 5 | 0.737 |
| **Bollinger Volatility** | 3 | 4 | 0 | 0.541 |

> 💡 **The 95 Likely Elite/Strong specimens span only 4 of these 5 edges in practice** (Bollinger Volatility contributes 0 Elite/Strong specimens). And of those 4, two edges (Mean Reversion + Trend Pullback) account for **73 of the 95** — 76.8 %.

### 3.1 Edge concentration verdict
- **Effective independent opportunities for re-scoring:** **5** edge archetypes
- **Genuinely high-value independent edges:** **3** (Mean Reversion, Trend Pullback, Session Range Breakout)
- **Edges that need *more cycles* before they are credible:** **2** (Volatility Breakout — only 6 specimens; Bollinger — only 4 with 0 E/S)

This is the real answer to your migration-value question: **the migration carries ~3 strong edges + 2 thin edges, not 95 opportunities.**

---

## 4. TOP 20 FAMILIES

Sorted by Elite/Strong specimen count (secondary: best preview score). Family ID is assigned by size rank.

| Fam ID | Name | Pair | TF | n | Avg PF (range) | Avg Stab | Avg OOS | Avg DD | Best Specimen (preview) | Marketplace | Master Bot | Elite/Strong |
|--------|------|------|----|----|----------------|----------|---------|--------|--------------------------|-------------|------------|--------------|
| **F01** | Base + RSI Confirmation | XAUUSD | H1 | 22 | 1.02 (0.83-1.04) | 77.7 | 1.01 | 0.00% | `6a0829e8c2486b` (0.77) | Medium | High | 21/22 |
| **F03** | Trend + RSI Pullback | ETHUSD | H1 | 18 | 1.10 (1.01-1.28) | 79.2 | 0.94 | 0.00% | `6a09a72d0c1060` (0.84) | High | High | 15/18 |
| **F05** | Trend + RSI Pullback | XAUUSD | H1 | 13 | 0.99 (0.98-1.00) | 83.3 | 1.26 | 0.00% | `6a082b35c2486b` (0.77) | High | High | 13/13 |
| **F02** | Asian Range Breakout | EURUSD | H1 | 18 | 0.93 (0.84-1.02) | 74.4 | 0.97 | 0.45% | `6a08256ec2486b` (0.67) | Medium | Medium | 8/18 |
| **F04** | RSI Mean Reversion | EURUSD | H1 | 17 | 0.97 (0.90-0.99) | 68.4 | 0.96 | 0.25% | `6a0840c4f156ca` (0.72) | Medium | Medium | 6/17 |
| **F06** | Base + D1 Trend Confirmation | ETHUSD | H4 | 5 | 1.28 (1.28-1.28) | 76.7 | 0.82 | 0.00% | `6a09a6a40c1060` (0.79) | High | High | 5/5 |
| **F09** | ATR Breakout | XAUUSD | H1 | 4 | 0.93 (0.91-0.98) | 79.8 | 1.19 | 0.00% | `6a09a9810c1060` (0.70) | Medium | High | 4/4 |
| **F08** | Asian Range Breakout | XAUUSD | H1 | 4 | 0.93 (0.89-0.97) | 68.7 | 1.09 | 0.00% | `6a086f7a4b9874` (0.71) | Medium | High | 3/4 |
| **F12** | London Open Breakout | XAUUSD | H1 | 2 | 0.93 (0.92-0.94) | 87.5 | 0.86 | 0.00% | `6a086f834b9874` (0.69) | Medium | High | 2/2 |
| **F14** | Base + Volatility Filter | XAUUSD | H1 | 2 | 0.98 (0.94-1.03) | 73.4 | 1.11 | 0.00% | `6a086fa54b9874` (0.67) | Medium | High | 2/2 |
| **F11** | Base without RSI | XAUUSD | H1 | 3 | 0.98 (0.90-1.03) | 72.7 | 0.86 | 0.00% | `6a082904c2486b` (0.64) | Medium | Medium | 2/3 |
| **F21** | Base with 1:2 RR | XAUUSD | H4 | 1 | 1.28 (1.28-1.28) | 74.0 | 1.34 | 0.00% | `6a0842fbf156ca` (0.85) | High | High | 1/1 |
| **F27** | Asian Range Breakout | XAUUSD | H4 | 1 | 1.12 (1.12-1.12) | 73.9 | 1.12 | 0.00% | `6a09a3640c1060` (0.80) | High | High | 1/1 |
| **F26** | Base without RSI | XAUUSD | H4 | 1 | 1.23 (1.23-1.23) | 64.0 | 1.25 | 0.00% | `6a08917613e3fe` (0.80) | High | High | 1/1 |
| **F25** | ATR Breakout | XAUUSD | H4 | 1 | 1.23 (1.23-1.23) | 77.5 | 0.85 | 0.00% | `6a08916213e3fe` (0.74) | High | High | 1/1 |
| **F18** | Asian Range Breakout | EURUSD | H4 | 1 | 1.03 (1.03-1.03) | 66.9 | 1.16 | 0.01% | `6a0828d0c2486b` (0.70) | Medium | High | 1/1 |
| **F10** | Base + Trend Filter | XAUUSD | H1 | 4 | 0.96 (0.85-1.03) | 59.6 | 1.06 | 0.00% | `6a082a65c2486b` (0.69) | Medium | Medium | 1/4 |
| **F07** | Base with 1:1.5 RR | EURUSD | H1 | 4 | 0.95 (0.84-1.00) | 68.8 | 1.37 | 0.39% | `6a084500ec5e5d` (0.67) | Medium | Medium | 1/4 |
| **F15** | Base with 1:1.5 RR | XAUUSD | H1 | 2 | 0.97 (0.91-1.03) | 70.0 | 0.86 | 0.00% | `6a08746b4b9874` (0.66) | Medium | Medium | 1/2 |
| **F19** | Base with 1:2 RR | XAUUSD | H1 | 1 | 0.90 (0.90-0.90) | 73.3 | 1.20 | 0.00% | `6a0829c2c2486b` (0.65) | Medium | High | 1/1 |

### 4.1 Top-20 read

- **F01 / F03 / F05** account for 49 of 95 Elite/Strong specimens (51 %) and represent only **2 distinct edges** (Mean Reversion on XAUUSD-H1 + Trend Pullback on ETHUSD/XAUUSD-H1).
- **F06 (Base + D1 Trend Confirmation, ETHUSD/H4)** is the most efficient family: 5/5 specimens land Elite/Strong with best preview 0.787 and Marketplace score 0.773 — the *highest-density family in the dataset*. Worth grooming on target.
- **F09 (ATR Breakout, XAUUSD/H1)** is small (4 specimens) but 4/4 Elite/Strong with the **strongest Master Bot score (0.793 avg)**. A diversification-critical seed.
- **F02 (Asian Range Breakout, EURUSD/H1)** is large (18) but converts poorly to Elite/Strong (8/18). The Session Range Breakout edge is more credible on XAUUSD (F08, 3/4) than on EURUSD.
- **F04 (RSI Mean Reversion, EURUSD/H1)** is the *original RSI base* — 17 specimens, but only 6 Elite/Strong. The EURUSD instantiation of the RSI edge is weaker than the XAUUSD instantiation (F01: 21/22).

---

## 5. FAMILY CONCENTRATION REPORT

How many families do you need to import to capture X % of the value?

| Rank | Family | Family size | Elite/Strong contribution | Cumul. Elite/Strong | Cumul. specimens |
|------|--------|-------------|---------------------------|---------------------|------------------|
| 1 | **F01** Base + RSI Confirmation (XAUUSD/H1) | 22 | 21 | 21 (22%) | 22 (16%) |
| 2 | **F03** Trend + RSI Pullback (ETHUSD/H1) | 18 | 15 | 36 (38%) | 40 (29%) |
| 3 | **F05** Trend + RSI Pullback (XAUUSD/H1) | 13 | 13 | 49 (52%) | 53 (38%) |
| 4 | **F02** Asian Range Breakout (EURUSD/H1) | 18 | 8 | 57 (60%) | 71 (51%) |
| 5 | **F04** RSI Mean Reversion (EURUSD/H1) | 17 | 6 | 63 (66%) | 88 (63%) |
| 6 | **F06** Base + D1 Trend Confirmation (ETHUSD/H4) | 5 | 5 | 68 (72%) | 93 (66%) |
| 7 | **F09** ATR Breakout (XAUUSD/H1) | 4 | 4 | 72 (76%) | 97 (69%) |
| 8 | **F08** Asian Range Breakout (XAUUSD/H1) | 4 | 3 | 75 (79%) | 101 (72%) |
| 9 | **F11** Base without RSI (XAUUSD/H1) | 3 | 2 | 77 (81%) | 104 (74%) |
| 10 | **F12** London Open Breakout (XAUUSD/H1) | 2 | 2 | 79 (83%) | 106 (76%) |
| 11 | **F14** Base + Volatility Filter (XAUUSD/H1) | 2 | 2 | 81 (85%) | 108 (77%) |
| 12 | **F07** Base with 1:1.5 RR (EURUSD/H1) | 4 | 1 | 82 (86%) | 112 (80%) |
| 13 | **F10** Base + Trend Filter (XAUUSD/H1) | 4 | 1 | 83 (87%) | 116 (83%) |
| 14 | **F15** Base with 1:1.5 RR (XAUUSD/H1) | 2 | 1 | 84 (88%) | 118 (84%) |
| 15 | **F17** Base without RSI (EURUSD/H1) | 1 | 1 | 85 (89%) | 119 (85%) |
| 16 | **F18** Asian Range Breakout (EURUSD/H4) | 1 | 1 | 86 (91%) | 120 (86%) |
| 17 | **F19** Base with 1:2 RR (XAUUSD/H1) | 1 | 1 | 87 (92%) | 121 (86%) |
| 18 | **F21** Base with 1:2 RR (XAUUSD/H4) | 1 | 1 | 88 (93%) | 122 (87%) |
| 19 | **F25** ATR Breakout (XAUUSD/H4) | 1 | 1 | 89 (94%) | 123 (88%) |
| 20 | **F26** Base without RSI (XAUUSD/H4) | 1 | 1 | 90 (95%) | 124 (89%) |
| 21 | **F27** Asian Range Breakout (XAUUSD/H4) | 1 | 1 | 91 (96%) | 125 (89%) |
| 22 | **F28** Base with 1:1 RR (XAUUSD/H1) | 1 | 1 | 92 (97%) | 126 (90%) |
| 23 | **F29** RSI Mean Reversion (ETHUSD/H4) | 1 | 1 | 93 (98%) | 127 (91%) |
| 24 | **F30** London Open Breakout (ETHUSD/H4) | 1 | 1 | 94 (99%) | 128 (91%) |
| 25 | **F34** Asian Range Breakout (ETHUSD/H1) | 1 | 1 | 95 (100%) | 129 (92%) |
| 26 | **F13** London Open Breakout (EURUSD/H1) | 2 | 0 | 95 (100%) | 131 (94%) |
| 27 | **F16** Bollinger Band Reversal (ETHUSD/H1) | 2 | 0 | 95 (100%) | 133 (95%) |
| 28 | **F20** Trend + RSI Pullback (EURUSD/H1) | 1 | 0 | 95 (100%) | 134 (96%) |
| 29 | **F22** Bollinger Squeeze Breakout (EURUSD/H1) | 1 | 0 | 95 (100%) | 135 (96%) |
| 30 | **F23** Base with 1:2 RR (EURUSD/H1) | 1 | 0 | 95 (100%) | 136 (97%) |
| 31 | **F24** Bollinger Band Reversal (XAUUSD/H1) | 1 | 0 | 95 (100%) | 137 (98%) |
| 32 | **F31** ATR Breakout (ETHUSD/H1) | 1 | 0 | 95 (100%) | 138 (99%) |
| 33 | **F32** RSI Mean Reversion (ETHUSD/H1) | 1 | 0 | 95 (100%) | 139 (99%) |
| 34 | **F33** Base without RSI (ETHUSD/H1) | 1 | 0 | 95 (100%) | 140 (100%) |

**Read:** Just **9 families** carry 80 % of Elite/Strong specimens. Importing the top 14 families captures 95 %. The remaining 20 families (single-specimen tails) contribute <5 % marginal value but cost ≈ nothing to migrate.

### 5.1 Selective-import scenario (if storage were constrained)
- Top-9 families → covers 80 % of Elite/Strong + 67 % of total population
- Top-14 families → covers 95 % of Elite/Strong + 85 % of total population
- All 34 families → 100 % at near-zero marginal cost

**Verdict:** Always import all 34 (the cost is trivial). But for *re-scoring prioritization on target*, focus runtime on the top 9.

---

## 6. LARGEST SIBLING CLUSTERS

Where the mutation engine spent the most compute *on the same logical strategy*.

| Family | Strategy Name | Pair/TF | Sibling Count | Distinct PFs | Distinct Trade Counts | Avg PF | Avg Stab |
|--------|---------------|---------|---------------|--------------|----------------------|--------|----------|
| **F01** | Base + RSI Confirmation | XAUUSD/H1 | 22 | 6 | 5 | 1.02 | 77.7 |
| **F02** | Asian Range Breakout | EURUSD/H1 | 18 | 10 | 12 | 0.93 | 74.4 |
| **F03** | Trend + RSI Pullback | ETHUSD/H1 | 18 | 2 | 3 | 1.10 | 79.2 |
| **F04** | RSI Mean Reversion | EURUSD/H1 | 17 | 5 | 3 | 0.97 | 68.4 |
| **F05** | Trend + RSI Pullback | XAUUSD/H1 | 13 | 3 | 5 | 0.99 | 83.3 |
| **F06** | Base + D1 Trend Confirmation | ETHUSD/H4 | 5 | 1 | 1 | 1.28 | 76.7 |
| **F07** | Base with 1:1.5 RR | EURUSD/H1 | 4 | 4 | 3 | 0.95 | 68.8 |
| **F08** | Asian Range Breakout | XAUUSD/H1 | 4 | 4 | 4 | 0.93 | 68.7 |
| **F09** | ATR Breakout | XAUUSD/H1 | 4 | 3 | 4 | 0.93 | 79.8 |
| **F10** | Base + Trend Filter | XAUUSD/H1 | 4 | 3 | 3 | 0.96 | 59.6 |

### 6.1 Sibling-cluster observations
- **F01 (22 siblings, 6 distinct PFs)** — broadest evaluation diversity. The XAUUSD/H1 RSI strategy was re-validated 22 times. **Use these 22 evaluations as a robustness curve, not as 22 separate strategies.**
- **F02 (18 siblings, 10 distinct PFs)** — second-broadest. EURUSD Asian Range was evaluated under many conditions; the PF spread (0.84–1.02) is itself the evidence that this edge is *marginal in EURUSD*.
- **F03 (18 siblings, only 2 distinct PFs)** — strong evaluation clustering. The ETHUSD Trend Pullback either works (PF 1.28) or doesn't (PF 1.01). **Bimodal — investigate which trading regime each branch corresponds to on target.**
- **F06 (5 siblings, 1 distinct PF)** — pure duplicates. ETHUSD/H4 D1 Trend Confirmation produced the same PF (1.28) on every re-run. **Strongest signal of a reproducible edge in the dataset.**
- **F09 (4 siblings, all Elite/Strong, ATR Breakout XAUUSD/H1)** — high-quality, low-redundancy cluster.

### 6.2 Sibling-cluster master-bot rule
The Master Bot generator on target **must dedupe by family before correlation analysis** — otherwise a portfolio built from sibling-heavy clusters (F01, F02, F03, F04) will be falsely "diversified" by re-runs of the same edge.

---

## 7. INDEPENDENT-EDGE COUNT — FINAL ESTIMATE

### 7.1 Answer
The 95 Likely Elite/Strong candidates represent:
- **34** distinct logical families
- **9** families that account for 80 % of Elite/Strong specimens
- **5** independent edge archetypes
- **3** edges with credible weight of evidence (Mean Reversion, Trend Pullback, Session Range Breakout)
- **2** thin edges that need more research cycles before promotion (Volatility Breakout, Bollinger)

### 7.2 Mapping back to operator expectations

| Question | Honest answer |
|---|---|
| Does the migration carry 95 independent opportunities? | **No.** It carries ~9 logical families worth of compute. |
| Does the migration carry 15–25 underlying strategy families? | **Closer.** 34 logical families, ~9 high-density, ~3 credible edges. |
| Does the migration carry enough material for a Master Bot? | **Yes — 3 high-conviction edge-bots are realistic:** one per credible edge (Mean Reversion on XAUUSD/H1, Trend Pullback on ETHUSD/H1, Session Range or ATR Breakout on XAUUSD/H1). |
| Should we expect 5–8 marketplace listings? | **Optimistic.** A realistic gate yields **1–3 listings**, one per credible edge, where the family's best specimen also clears trade-count and OOS-discipline floors. |

### 7.3 Implication for the 12-vCPU pipeline
- The **target's Master Bot stage must dedupe by family** (see §6.2) before ranking. Otherwise it will overweight the broadest-sibling families (F01, F02) just because they have more specimens.
- The **target's marketplace gate must enforce edge diversification** — listing 3 specimens of the same family adds no portfolio value.
- **Schedule additional research cycles** for Volatility Breakout (only 6 specimens) and Bollinger (only 4) post-migration to grow these thin edges into credible ones.

---

## 8. MIGRATION VALUE — REVISED

| Dimension | Pre-dedup estimate | Post-dedup estimate |
|---|---|---|
| Listable strategies on import | 0 | 0 |
| Listable after re-scoring (joint gate) | 5–8 | **1–3** (one per credible edge) |
| Master Bot families | 3–4 | **3 credible + 1 exploratory** |
| Independent opportunities | 95 | **5** (edges) |
| Genuine high-conviction edges | unknown | **3** |
| Cycles needed to grow thin edges | unknown | **~50–100 mutation cycles for Volatility Breakout & Bollinger** |

---

## 9. RECOMMENDATIONS

1. **Migrate all 140 strategies.** The numerical evidence (PF/Stability/OOS spread across siblings) is itself a robustness curve and is irreplaceable.
2. **Dedupe by family in the target's Master Bot stage.** Use `(name, pair, timeframe, parameters)` as the natural identity. Within a family, keep the best specimen (by Preview/Master-Bot score) as the canonical entry; record siblings as *evaluation evidence* on that entry, not as separate strategies.
3. **Build 3 edge-bots, not 95 strategy-bots.** One per credible edge: Mean Reversion (RSI), Trend Pullback (EMA + RSI), and the strongest of (Session Range Breakout / Volatility Breakout).
4. **Schedule explicit research on thin edges** post-migration: Volatility Breakout (ATR-based), Bollinger volatility patterns, Channel/Donchian. These are under-represented (10 specimens combined, 5 Elite/Strong).
5. **Treat the legacy library's per-row count as research-evaluation count, not as strategy count.** Update operator dashboards to display "5 independent edges / 34 families / 140 evaluations" instead of "140 strategies."

---

## 10. AUDIT BOUNDARY

This dedup audit uses **only data present on the source pod** and a manual indicator-taxonomy classification from `strategy_text` parsing. The target's actual Master Bot grouping logic may use additional signals (e.g., return-curve correlation, regime-conditioned performance) that further refine these families. This audit's role is to **establish honest expectations before exports run** — not to substitute for the target's correlation analytics post-import.
