# SURVIVOR CLASSIFICATION
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Scope:** Classification + migration / marketplace / master-bot value estimates for all 140 strategies in `strategy_library`.
**Discipline:** Read-only assessment. No exports.
**Companion:** LEGACY_STRATEGY_INVENTORY.md (per-strategy table).

---

## 1. CLASSIFICATION SCHEME

Every strategy is placed in exactly one bucket based on hard thresholds applied to the actual fields present on this deployment. Thresholds were chosen against the empirical distribution (score 35–61.7, PF 0.79–1.28, OOS ratio 0.70–1.73, stability 50.6–96.8).

| Bucket | Threshold (all must hold) |
|---|---|
| **Elite** | `score ≥ 60` AND `PF ≥ 1.20` AND `stability ≥ 70` AND `OOS_ratio ≥ 0.85` AND `EV ≥ 0` AND `verdict ≠ REJECTED` |
| **Strong** | `score ≥ 55` AND `PF ≥ 1.10` AND `stability ≥ 65` AND `OOS_ratio ≥ 0.75` |
| **Average** | `score ≥ 45` AND `PF ≥ 0.95` |
| **Experimental** | `score ≥ 35` AND `PF ≥ 0.80` |
| **Deprecated** | everything else (PF < 0.80 OR score < 35) |

Verdict (`RISKY`) and `pass_probability` (0.0) are *not* used as elimination criteria because they are uniform across the dataset (see LEGACY_STRATEGY_INVENTORY §1) — using them would collapse the entire population to a single bucket.

---

## 2. DISTRIBUTION

| Class | Count | % of total | Pairs | TFs |
|---|---|---|---|---|
| **Elite** | **0** | 0.0 % | — | — |
| **Strong** | **0** | 0.0 % | — | — |
| **Average** | **73** | 52.1 % | XAUUSD 37, ETHUSD 20, EURUSD 16 | H1 = 67, H4 = 6 |
| **Experimental** | **66** | 47.1 % | EURUSD 30, XAUUSD 25, ETHUSD 11 | H1 = 60, H4 = 6 |
| **Deprecated** | **1** | 0.7 % | XAUUSD 1 | H1 = 1 |

**Bottom line:** This deployment has produced **zero deploy-grade survivors**. The entire population is research-grade. That does **not** make the inventory worthless — it makes it *evidence*, not *inventory*.

---

## 3. PER-CLASS METRICS

| Class | n | Avg Score | Avg PF | Avg Win% | Avg MaxDD | Avg Stability | Avg OOS Ratio |
|---|---|---|---|---|---|---|---|
| Elite | 0 | — | — | — | — | — | — |
| Strong | 0 | — | — | — | — | — | — |
| Average | 73 | 52.2 | 1.04 | 37.2 % | 0.06 % | 78.8 | 0.99 |
| Experimental | 66 | 45.2 | 0.96 | 33.7 % | 0.19 % | 70.7 | 1.05 |
| Deprecated | 1 | 45.3 | 0.79 | 33.7 % | 0.00 % | 52.6 | 1.21 |

---

## 4. EXPECTED MIGRATION VALUE

"Migration value" = the worth of bringing this strategy across to the 12-vCPU pod, expressed on a 0–5 scale.

| Class | Migration Value | Justification |
|---|---|---|
| Elite | — | None present |
| Strong | — | None present |
| **Average (73)** | **3 / 5** | Migrate. Provides 73 specimens for the new Quality v2 / Evidence / Market / Trust pipelines to re-score against. Their stability scores (avg 78.8) and OOS ratios (~1.0) are real evidence the newer scoring engine can use as input. None are dropped because they are the strongest research signal we possess. |
| **Experimental (66)** | **2 / 5** | Migrate. Lower PF (0.96 avg) but still inside the population the mutation engine deemed worth recording. Useful for *negative-evidence* anchors when training the newer scoring composites. |
| **Deprecated (1)** | **1 / 5** | Migrate (cost = 1 KB). Single specimen `6a0874ba4b98749132` (XAUUSD/H1, PF 0.79, stability 52.6). Preserves provenance of the worst-survivor floor — useful for setting deprecation thresholds on target. |

**Aggregate:** Migrate **140 / 140**. Total cost is trivial (~1 MB compressed). Discarding any of them would discard evolutionary search evidence that cannot be cheaply recreated.

> 🟢 **Mutation lineage and event corpus (10,430 events / 1,042 runs / 1,047 perf-history rows) are higher-value than the library itself** — they capture *how* these survivors were arrived at. All must migrate (Tier 1).

---

## 5. EXPECTED MARKETPLACE VALUE

"Marketplace value" = the probability that the strategy, *as-is on import*, can be listed on the target Marketplace gate.

| Class | Marketplace Value | Justification |
|---|---|---|
| Elite | — | None present |
| Strong | — | None present |
| **Average (73)** | **0 / 5 (NOT MARKETPLACE-READY)** | Every row has `verdict=RISKY`, `pass_probability=0`, `EV=−810`, `prop_firm_panel.status=RISKY`, FTMO `challenge_status=fail`. None meets a credible Marketplace gate. |
| **Experimental (66)** | **0 / 5** | Same as Average, plus lower PF (avg 0.96). Definitely not listable. |
| **Deprecated (1)** | **0 / 5** | Sub-1.0 PF, low stability — explicitly not listable. |

**Aggregate marketplace value of this deployment, today: ZERO listable strategies.**

This is **not a migration failure** — it is the truthful state of the search. Post-migration, after the 12-vCPU re-scoring pipeline (POST_IMPORT_PIPELINE Stages 3 → 8), some of the Average bucket *may* clear the gate if:
- the new Quality v2 metric weighs stability differently
- the new Pass Probability v2 (per firm) finds the EURUSD specimens (which actually have non-zero drawdown data) pass relaxed phase 2 / live rules
- the new Market Score rewards the H4 / XAUUSD cluster that shows higher PF concentration

**Realistic expectation after re-scoring:** 3–10 Average-bucket strategies may achieve marketplace-pending status. None will be listed without operator review.

---

## 6. EXPECTED MASTER-BOT SUITABILITY

"Master-bot suitability" = whether the strategy can join a Master Bot family (correlated cluster forming a portfolio-grade composite).

| Class | Master-Bot Suitability | Justification |
|---|---|---|
| Elite | — | None present |
| Strong | — | None present |
| **Average (73)** | **2 / 5** — *Conditional inclusion* | Best candidates for grouping. Many Average rows show clustered metrics (e.g., 25+ XAUUSD H1 specimens with PF 1.02–1.04, win% ~37.7) — indicates the mutation engine found a metric-stable but mediocre region. A Master Bot built from these would be a **diversification stress-test bot**, not a profit-driver. Useful for shadow-deployment / correlation analysis on target. |
| **Experimental (66)** | **1 / 5** — *Negative cohort* | Lower-PF outliers; include only in a "negative ensemble" Master Bot (a deliberate counter-correlated grouping for stress-testing). |
| **Deprecated (1)** | **0 / 5** | Exclude. Single sample, sub-1.0 PF, lowest stability in dataset. |

### 6.1 Recommended Master-Bot family seeds (post re-scoring)

After Stage 4 (Re-rank) and Stage 6 (Re-portfolio) on the 12-vCPU pod, attempt family construction in this order:

1. **ETHUSD H1 cluster** — 20 specimens, PF cluster around 1.01, stability strongest in the dataset (sample 96.8 observed). Best chance of producing a coherent Master Bot family.
2. **XAUUSD H1 cluster** — 37 specimens, PF cluster around 1.00–1.04. Use for **correlation control** family.
3. **EURUSD H1 cluster** — 16 specimens, only group showing real drawdown data (avg 0.3%). Use for **risk-resolution** family.
4. **H4 micro-cohort (12 specimens total across pairs)** — too small for its own family; absorb into the appropriate pair-level family.

**Realistic expectation:** the 12-vCPU pipeline produces **2–3 Master Bots**, all flagged for **shadow execution only** until the target's online-promotion gates accept them.

---

## 7. AGGREGATED VALUE SCORECARD

| Dimension | Score (0–5) | Verdict |
|---|---|---|
| **Migration value** | **3.0** | Migrate all 140. Cost ≈ 1 MB. Loss-if-skipped ≈ irrecoverable evolutionary evidence. |
| **Marketplace value** | **0.0** | Zero listable strategies as-is. Possibly 3–10 after re-scoring. |
| **Master-bot suitability** | **1.5** | 2–3 shadow-only Master Bots realistic after Stages 6–7. |
| **Re-scoring uplift potential** | **3.5** | High. Newer composite scoring may surface latent value that the current `RISKY`-only verdict pipeline missed. |

---

## 8. CRITICAL CAVEATS

1. **All classifications assume the empirical thresholds in §1.** If the 12-vCPU pod uses different bands, re-bucketing post-import is trivial — but the *underlying numerical evidence* is what travels.
2. **`pass_probability` and `EV` are sentinel-only on source** (uniformly 0.0 and −810 respectively). These fields **must not** be used by the target as authoritative inputs. The target must recompute them (POST_IMPORT_PIPELINE §3.5).
3. **`strategy_library` does not link to `strategy_lifecycle` by fingerprint** on this pod (0 / 140 overlap). Lifecycle stage cannot be carried over per-strategy; it must be re-derived from history.
4. **Mutation depth is shallow.** 139 / 140 strategies are at `g1`. The evolutionary tree is broad, not deep. Implication: there is no "old champion" lineage to preserve — every specimen is one generation away from a base it shares with many siblings.
5. **No organic ingestion survivors exist in library.** Even though `ingested_strategies` has 55 rows, none of them made it into `strategy_library` (source field = `mutation_engine` for all 140). This is a real funnel finding — the ingestion → validation pipeline is not promoting candidates.

---

## 9. RECOMMENDATIONS FOR OPERATOR

1. **Migrate all 140 strategies + lineage + history** — they are the only evolutionary evidence on this pod.
2. **Do not rely on `verdict`, `pass_probability`, or `expected_value` post-import.** Treat them as legacy fields and recompute via Stage 3.
3. **Treat Marketplace listing as a *target-side outcome*, not a migration target** — none will list on import.
4. **Plan for shadow-only Master Bots initially.** Live promotion requires the target's gating logic to accept the re-scored inventory.
5. **Investigate the ingestion → library funnel collapse separately.** 55 ingested strategies producing 0 library entries is a pre-deployment audit issue, distinct from migration.
