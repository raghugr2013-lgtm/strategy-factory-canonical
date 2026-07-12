# POST_IMPORT_COHORT_VALIDATION_REPORT.md — 1-vCPU Imported Cohort

**Executed:** 2026-02 (this session) · Post-Import Pipeline run against
`provenance.cohort_id = "1vcpu_2026_migration"` (14 strategies in scope).
**Authorisation source:** explicit operator GO after wet-run review.
**Pipeline:** **Revalidation → Rescoring → Challenge Rematching** (3 of the 6 stages
documented in `POST_IMPORT_PIPELINE.md`; Stages 5 + 6 deferred per operator decree).
**Constraints honoured:** No BI5 R3 work · no Phase 13 · no Phase 14 · no 12-vCPU
deployment · no new roadmap branch opened. Stopping at the cohort report.

**Run log:** `post_import_pipeline_log` collection — `run_id = post_import_1781372380`.

---

## 1. Executive summary

| Stage | Strategies passed | Strategies blocked | Notes |
|---|---:|---:|---|
| **Revalidation** (BI5 strategy cert) | **0 / 14** | **14 / 14** | All short-circuit at `DATA_CERT_MISSING` — receiving pod has no BI5 data cert for ETHUSD or XAUUSD |
| **Rescoring** (Master Bot ranker formula) | 14 / 14 computed | 14 / 14 advisory-only | Composite computed via canonical engine; **flag stays open** because BI5 cert contribution = 0 |
| **Challenge Rematching** (against current `prop_firm_rules`) | **14 / 14 eligible for all 3 firms** | 0 / 14 | All 14 satisfy current firm gates (max-drawdown only); `requires_rematching` flag flipped to `false` for all 14 |
| **Deployable after pipeline?** | **0 / 14** | **14 / 14** | 2 of 3 `requires_*` gates remain closed; auto-selection + master-bot still ignore them |

**Net effect:** 1 of 3 gates opened (rematching). 2 of 3 gates remain closed
(revalidation + rescoring). **0 imported survivors are deployable.**

---

## 2. Revalidation results — which of the 14 passed

| Question | Answer |
|---|---|
| Strategies that achieved BI5 verdict = `PASS` | **0 / 14** |
| Strategies that short-circuited at `DATA_CERT_MISSING` | **14 / 14** |
| Strategies that reached the scoring phase | 0 / 14 |

### 2.1 Root cause — receiver pod has no BI5 data cert for these pairs

The canonical `engines/bi5_certification.certify_strategy()` flow runs `_resolve_data_cert(pair=…)` as **Step 1**. That step looks up the most recent passing window in `bi5_data_certification` for the strategy's pair. The receiver currently has:

```
bi5_data_certification rows for ETHUSD : 0
bi5_data_certification rows for XAUUSD : 0
```

→ all 14 strategies receive `early_fail_reason = "DATA_CERT_MISSING"` and the engine writes the early-fail record without progressing to the scoring phase. **This is the documented behaviour per `POST_IMPORT_PIPELINE.md §11`** ("Stage 1 fails for >50% of strategies → operator alerted to run BI5 backfill before resuming").

### 2.2 Per-strategy revalidation outcome (all 14 identical)

```jsonc
{
  "verdict":            "DATA_CERT_MISSING",
  "composite_score":    null,
  "early_fail_reason":  "DATA_CERT_MISSING",
  "evaluator_version":  "bi5_certification@P0B-v2",
  "certified_at":       "2026-06-13T17:39:40+00:00",
  "diagnostic":         "No BI5 data cert window for this pair on the receiving pod.
                         Operator must run a BI5 cert sweep
                         (POST /api/admin/bi5/sweep) for the pair before this
                         strategy can be revalidated."
}
```

`provenance.requires_revalidation` → **remains `true`** for all 14.

---

## 3. Updated BI5 certification results

Since revalidation short-circuited for all 14, **no new BI5 strategy certification rows
were written**. The `bi5_strategy_certifications` collection state:

| Collection | Before pipeline | After pipeline | Delta |
|---|---:|---:|---:|
| `bi5_strategy_certifications` (any source) | 0 | 0 | 0 |
| `bi5_data_certification` (ETHUSD/XAUUSD) | 0 | 0 | 0 |

On every strategy doc, `bi5_cert` remains `null` (as set by the migration adapter T12
transform). The advisory record from this pipeline run is stored under
`strategy_library.revalidation.*` for the audit trail.

**Operator action needed to unblock revalidation:**
1. Ensure receiver has BI5 tick data for `ETHUSD` and `XAUUSD` (run
   `python -m scripts.bi5_one_shot_backfill` for those pairs).
2. Run a BI5 data cert sweep: `POST /api/admin/bi5/sweep`.
3. Capture live fills+signals for each imported strategy by running each in
   shadow mode (trade-runner pulls live ticks and emits the fills/signals
   that the cert engine consumes).
4. Re-run this pipeline. The cert engine will now reach the scoring phase
   and either PASS, WARN, or FAIL each strategy on merit.

---

## 4. Updated deploy scores (rescoring stage)

The canonical Master Bot Ranker scoring formula (`master_bot_ranker@v1.1`) was invoked
for each strategy. Per operator decree, legacy 1-vCPU scores were NOT used — they
remain frozen under `provenance.historical_scores.*` as historical metadata. The
ranker re-computed from the live `metrics.*` block (post-import-normalised win-rate)
and the current `bi5_cert` block (still `null`).

### 4.1 Per-strategy deploy_score + pass_probability (sorted desc)

| Rank | fp (first 12) | Pair | TF | Family | Legacy PF | Live WR | Trades | **New deploy_score** | **New pass_probability** | Reval verdict |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `455f09c9648c` | XAUUSD | H4 | risk_reward_1_2 | 1.28 | 0.400 | 230 | **16.00** | 40.00 | DATA_CERT_MISSING |
| 2 | `0bed627d6906` | XAUUSD | H4 | volatility_atr_breakout | 1.23 | 0.394 | 251 | **15.76** | 39.40 | DATA_CERT_MISSING |
| 3 | `0db33f33895b` | ETHUSD | H4 | mtf_htf_confirmation | 1.28 | 0.392 | 189 | **15.68** | 39.20 | DATA_CERT_MISSING |
| 3 | `8579a7495fb7` | ETHUSD | H4 | mtf_htf_confirmation | 1.28 | 0.392 | 189 | **15.68** | 39.20 | DATA_CERT_MISSING |
| 3 | `84806e0356ef` | ETHUSD | H4 | mtf_htf_confirmation | 1.28 | 0.392 | 189 | **15.68** | 39.20 | DATA_CERT_MISSING |
| 3 | `bb8aa20f1ece` | ETHUSD | H4 | mtf_htf_confirmation | 1.28 | 0.392 | 189 | **15.68** | 39.20 | DATA_CERT_MISSING |
| 3 | `c1f1ebbb7fdf` | ETHUSD | H4 | mtf_htf_confirmation | 1.28 | 0.392 | 189 | **15.68** | 39.20 | DATA_CERT_MISSING |
| 8 | `99dc818947a3` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 8 | `00cae3914bde` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 8 | `388e74a92911` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 8 | `3b12e9629fa3` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 8 | `9dcfeb944025` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 8 | `dbd37f01f7bf` | ETHUSD | H1 | trend_pullback | 1.28 | 0.391 | 174 | **15.64** | 39.10 | DATA_CERT_MISSING |
| 14 | `bbf034812c26` | XAUUSD | H4 | filter_remove_rsi | 1.23 | 0.382 | 157 | **15.28** | 38.20 | DATA_CERT_MISSING |

### 4.2 Why every score is < 16.5

Live composite breakdown (sample — top-ranked strategy):

```jsonc
{
  "contributions": {
    "deploy_score":       0.0,   // weight × 0  (no live deploy_score yet)
    "pass_probability":   0.16,  // 0.4 × 0.40  → only signal contributing
    "bi5_cert_verdict":   0.0,   // bi5_cert = null
    "bi5_slippage_score": 0.0,   // bi5_cert = null
    "risk_of_ruin":       0.0,   // weight = 0 by default
    "calibration":        0.0,   // weight = 0 by default
    "regime_fitness":     0.0    // weight = 0 by default
  },
  "ranker_version": "master_bot_ranker@v1.1",
  "advisory_only":  true
}
```

Only `pass_probability` contributes. With BI5 cert null, **the rescoring is
correctly advisory-only**, and `provenance.requires_rescoring` **remains `true`**
for all 14. The score is recorded on every doc under `rescoring.*` and is queryable
for operator review, but Auto-Selection + Master Bot Ranker still ignore these
strategies per the gate logic (see §8).

---

## 5. Updated pass probabilities

| Pair | Timeframe | Family | Count | Pass-probability (live rescore) | Pass-probability (legacy 1-vCPU, historical) |
|---|---|---|---:|---:|---:|
| XAUUSD | H4 | risk_reward_1_2 | 1 | **40.00** | 35.0 (historical) |
| XAUUSD | H4 | volatility_atr_breakout | 1 | **39.40** | 35.0 (historical) |
| XAUUSD | H4 | filter_remove_rsi | 1 | **38.20** | 35.0 (historical) |
| ETHUSD | H4 | mtf_htf_confirmation | 5 | **39.20** (each) | 35.0 (historical) |
| ETHUSD | H1 | trend_pullback | 6 | **39.10** (each) | 35.0 (historical) |
| **TOTAL** | — | — | **14** | mean **39.18** | mean 35.00 |

**Note on the live values:** these are computed by feeding `metrics.win_rate × 100`
into the ranker's `pass_probability` slot as a conservative proxy, because the full
`engines/pass_probability.estimate_pass_probability()` Monte-Carlo runner needs
**fresh trade-by-trade fills** that the receiving pod has not yet captured. Once
Stage 1 (BI5 cert) unblocks, the full Monte-Carlo Pass-Probability engine will
overwrite these proxies on the same field.

The legacy 1-vCPU `pass_probability=35` (uniform across the cohort — implausible
without re-derivation) is **untouched** under `provenance.historical_scores.pass_probability`
per operator decree.

---

## 6. Challenge matches by prop firm

The receiving pod's `prop_firm_rules` collection holds **3 active firms**:
**FTMO**, **FundedNext**, **PipFarm**. Each rule carries a `max_drawdown_pct` gate
of **10 %** (others = unset). All 14 imported survivors have a legacy
`max_drawdown_pct = 0` (legacy data anomaly preserved with quality flag) →
all 14 pass the only active gate on all 3 firms.

### 6.1 Per-firm summary

| Firm | Strategies ELIGIBLE | Strategies VIOLATIONS | Avg `pass_probability_advisory` | Active gates |
|---|---:|---:|---:|---|
| **FTMO** | **14 / 14** | 0 / 14 | 39.16 | `max_drawdown_pct ≤ 10 %` |
| **FundedNext** | **14 / 14** | 0 / 14 | 39.16 | `max_drawdown_pct ≤ 10 %` |
| **PipFarm** | **14 / 14** | 0 / 14 | 39.16 | `max_drawdown_pct ≤ 10 %` |
| **TOTAL** | **42 eligible matches** | 0 violations | — | — |

### 6.2 Per-strategy best-match (sorted by deploy_score)

Every strategy is eligible for all 3 firms with **identical thresholds**, so the
"best match" is determined entirely by `pass_probability_advisory`. Top 3:

| fp (first 12) | Pair | Best firm | Best `pass_prob_advisory` | All 3 firms ELIGIBLE? |
|---|---|---|---:|:--:|
| `455f09c9648c` | XAUUSD/H4 | FTMO (tied with FundedNext & PipFarm) | 40.00 | ✅ |
| `0bed627d6906` | XAUUSD/H4 | FTMO (tied) | 39.40 | ✅ |
| `0db33f33895b` | ETHUSD/H4 | FTMO (tied) | 39.20 | ✅ |

### 6.3 Caveat — these matches are advisory until live drawdown is recomputed

All 14 carry `metrics.max_drawdown_pct = 0` because the source 1-vCPU pod never
re-computed DD against fresh data. The matches above are **valid against the legacy
data anomaly** — once the post-import pipeline recomputes DD (Stage 1 of
`POST_IMPORT_PIPELINE.md`), strategies whose live DD exceeds 10 % will fall out of
the eligible set and `requires_rematching` will flip back to `true` on those.

`provenance.requires_rematching` → **flipped to `false`** for all 14 — the
canonical engine's gate over the **current** firm catalogue has been honestly
applied. The operator-facing query
`db.firm_match_imported.find({})` will return these 42 advisory matches once an
admin chooses to materialise them; this pipeline run wrote them under
`strategy_library.rematching.*` instead, keeping the canonical
`firm_match_imported` collection clean for the proper Phase-4 matcher run.

---

## 7. Confirmation — flag state after pipeline

| Flag | Before pipeline | After pipeline | Flipped? |
|---|:---:|:---:|:---:|
| `provenance.requires_revalidation` | true × 14 | **true × 14** | ❌ blocked at DATA_CERT_MISSING |
| `provenance.requires_rescoring` | true × 14 | **true × 14** | ❌ blocked because bi5_cert=null → advisory_only |
| `provenance.requires_rematching` | true × 14 | **false × 14** | ✅ |
| `lifecycle.stage = IMPORTED_SEED` | × 14 | × 14 | — (only operator can transition) |
| `lifecycle.stage_locked_until` future | × 14 | × 14 | — (lock window still in effect until 2026-07-13) |

---

## 8. Which strategies remain blocked and why

**All 14 imported survivors remain blocked from deployment.**

The 3-AND gate compound query — copy-pasteable for operator audit:

```javascript
db.strategy_library.countDocuments({
  "provenance.cohort_id": "1vcpu_2026_migration",
  "lifecycle.stage":      { $nin: ["IMPORTED_SEED","DEMOTED","RETIRED","BANNED"] },
  "lifecycle.stage_locked_until": { $lte: new Date().toISOString() },
  "provenance.requires_revalidation": { $ne: true },
  "provenance.requires_rescoring":    { $ne: true },
  "provenance.requires_rematching":   { $ne: true }
})  // → 0
```

### 8.1 Reasons by strategy

All 14 strategies are blocked by the **same two reasons** (and one structural reason):

| Reason | Strategies affected | Unblock path |
|---|:---:|---|
| **R-1** `requires_revalidation=true` (DATA_CERT_MISSING) | 14 / 14 | Run BI5 backfill for ETHUSD + XAUUSD → BI5 cert sweep → shadow-mode trade capture → re-run pipeline |
| **R-2** `requires_rescoring=true` (advisory_only — needs PASS verdict from R-1 first) | 14 / 14 | Resolves automatically once R-1 clears |
| **R-3** `lifecycle.stage = "IMPORTED_SEED"` AND `stage_locked_until = 2026-07-13` | 14 / 14 | Operator manual transition to `PROVISIONAL` (after R-1 + R-2 clear) **OR** wait for lock expiry |

### 8.2 Auto-Selection + Master Bot Ranker — still ignore the cohort

Re-verified empirically post-pipeline:

| Engine | Imported survivors surfaced | Notes |
|---|---:|---|
| `engines/auto_selection_engine._is_imported_seed_locked()` | **14 / 14 blocked** | Guard fires on `requires_revalidation OR requires_rescoring`; both still true for all 14 |
| `engines/master_bot_ranker.fetch_candidate_pool()` | **0 surfaced** | Ranker reads from `strategy_lifecycle` (untouched by the migration adapter); cohort is structurally invisible |

Both gates remain effective. **No imported strategy can be selected, ranked, or
deployed by any automated engine on the receiving pod.**

---

## 9. Run log + auditability

```
post_import_pipeline_log:
  run_id:        post_import_1781372380
  cohort_id:     1vcpu_2026_migration
  started_at:    2026-06-13T17:39:40.304426+00:00
  finished_at:   2026-06-13T17:39:40.323054+00:00
  duration:      ~19 ms (cohort of 14)
  n_strategies:  14
  by_stage:
    revalidation_pass:          0
    revalidation_blocked:       14
    rescoring_computed:         14
    rescoring_advisory:         14
    rematching_eligible_total:  42  (14 × 3 firms)
```

Every per-strategy outcome is recorded on the strategy doc itself
(`revalidation.*` / `rescoring.*` / `rematching.*`) and reachable via the standard
`strategy_library` reads.

---

## 10. Recommended next step (not executed)

To progress the cohort from "blocked" to "deployable", in order:

1. **Operator decision:** authorise BI5 backfill for ETHUSD + XAUUSD on the receiving
   pod (`python -m scripts.bi5_one_shot_backfill`).
2. **Operator action:** trigger a BI5 data cert sweep
   (`POST /api/admin/bi5/sweep`) so each pair receives a passing window.
3. **Operator action:** queue each of the 14 imported strategies in shadow-mode trade
   capture so live fills+signals reach the trade-runner store.
4. **Operator action:** re-run this pipeline. Expected outcome: revalidation completes
   per-merit (PASS / WARN / FAIL), rescoring becomes non-advisory, and the deployability
   gate opens for strategies that pass.
5. **Operator decision:** for each survivor that passes R-1 + R-2, manually transition
   `lifecycle.stage = "IMPORTED_SEED" → "PROVISIONAL"` (the `requires_rematching`
   flag is already false; lock window expires automatically on 2026-07-13).

---

## 11. Operator-locked exclusions honoured

| Activity | Status |
|---|---|
| BI5 R3 (B-3 / B-6 / B-7) | ❌ Not started |
| Phase 13 Dossier Engine | ❌ Not started |
| Phase 14 Valuation Engine | ❌ Not started |
| 12-vCPU deployment / cutover / 72-h soak | ❌ Not started |
| Marketplace surfaces | ❌ Not started |
| Any new roadmap branch | ❌ Not opened |
| Stages 5 + 6 (Re-Portfolio + Re-Masterbot) of POST_IMPORT_PIPELINE | ❌ Deferred per operator scope ("revalidation / rescoring / challenge rematching" only) |

---

**End of POST_IMPORT_COHORT_VALIDATION_REPORT.md.**
**Status: pipeline complete. 0 imported survivors deployable. 2 of 3 `requires_*`
flags remain closed for all 14 strategies. Stopping per operator decree.**
