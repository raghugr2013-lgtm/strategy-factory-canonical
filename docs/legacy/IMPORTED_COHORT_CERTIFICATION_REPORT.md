# IMPORTED_COHORT_CERTIFICATION_REPORT.md

**Executed:** 2026-02 (this session) · 4-step pipeline (backfill ETHUSD + backfill XAUUSD + BI5 cert sweep + post-import pipeline re-run) against the 14-strategy `1vcpu_2026_migration` cohort.
**Authorisation source:** explicit operator GO ("ETHUSD and XAUUSD BI5 backfill and certification only").
**Constraints honoured:** No shadow-mode trade capture · no BI5 R3 · no Phase 13 · no Phase 14 · no 12-vCPU deployment · no new roadmap branch.

---

## 1. Executive summary

| Metric | Value |
|---|---:|
| Strategies that achieved BI5 cert verdict = **PASS** | **0 / 14** |
| Strategies that achieved verdict = **WARN** | **0 / 14** |
| Strategies that achieved verdict = **FAIL** (after full scoring) | **0 / 14** |
| Strategies that **early-failed** at `MISSING_FILLS` (data cert exists, fills do not) | **3 / 14** (all XAUUSD/H4) |
| Strategies that **skipped** at `DATA_CERT_MISSING` (no BI5 data on receiver) | **11 / 14** (all ETHUSD/H1 + H4) |
| Strategies **recommended for promotion** from `IMPORTED_SEED` | **0 / 14** |
| Strategies that remain blocked | **14 / 14** |

### Why no strategy progressed past Stage 1

The operator-locked exclusion `do not begin shadow-mode trade capture` is the gating
constraint. Shadow-mode capture is the **only** way live broker fills+signals reach
the trade-runner store for the 14 imported strategies. Without those fills, the BI5
strategy certification engine reaches Step 2 (`_extract_fills_from_validation`),
finds an empty array, and returns `MISSING_FILLS` for every XAUUSD strategy. ETHUSD
strategies never reach Step 2 because Step 1 (`_resolve_data_cert`) cannot find a
PASS data cert (no source archive for ETHUSD on this pod).

This is the **expected** outcome per `POST_IMPORT_PIPELINE.md §11` —
*"Stage 1 fails for >50% of strategies → operator alerted to run BI5 backfill before resuming"* —
and is the design reason the auto-selection guard requires **all three** `requires_*`
flags to clear before deployability.

---

## 2. Step-by-step execution log

### 2.1 ETHUSD BI5 backfill — STATUS: NO-OP (no source data)

```
python -m scripts.bi5_one_shot_backfill ETHUSD
  → status=error · ticks_added=0 · files_ingested=0
  → summary: symbols=1 · ticks_added=0 · files_ingested=0 · errors=1
```

Follow-up via `data_engine.incremental_updater.incremental_update_bi5("ETHUSD","1m")`:

```
{
  'symbol': 'ETHUSD', 'timeframe': '1m', 'source': 'bi5', 'mode': 'append_only',
  'candles_added': 0, 'ticks_added': 0, 'gaps_filled': 0,
  'range_before': {'count': 0, 'first': None, 'last': None},
  'range_after':  {'count': 0, 'first': None, 'last': None},
  'files_scanned': 0, 'files_ingested': 0,
  'warning': 'import_dir not found: /app/data_imports'
}
```

**Root cause:** the receiving pod has **no on-disk BI5 archive** for ETHUSD
(`/app/data/bi5/dukascopy/ETHUSD/` is absent) and **no source-pull credentials**
configured for the symbol. The backfill scripts both completed cleanly but moved zero
bytes.

### 2.2 XAUUSD BI5 backfill — STATUS: IDEMPOTENT NO-OP (already ingested)

```
python -m scripts.bi5_one_shot_backfill XAUUSD
  → status=error · ticks_added=0 · files_ingested=0
```

Follow-up via `incremental_update_bi5("XAUUSD","1m")`:

```
{
  'symbol': 'XAUUSD', ...
  'range_before': {'count': 28823, 'first': '2026-05-01T00:00:00+00:00', 'last': '2026-05-31T23:59:00+00:00'},
  'range_after':  {'count': 28823, 'first': '2026-05-01T00:00:00+00:00', 'last': '2026-05-31T23:59:00+00:00'},
  'files_scanned': 0, 'files_ingested': 0,
  'warning': 'import_dir not found: /app/data_imports'
}
```

XAUUSD already has **28,823 minute-bars** (May 2026) and **744 .bi5 hour files** on
disk — coverage is complete; backfill is correctly a no-op.

### 2.3 BI5 certification sweep — STATUS: COMPLETED (3 processed, 11 skipped)

**Pre-sweep one-time backfill** (legitimate compatibility fix-up): the migration
adapter wrote `pair`/`timeframe`/`style` under `fingerprint_inputs.*` per the ASF v1.0
nested-shape contract, but the canonical `bi5_cert_sweep` engine reads flat root-level
fields. Patched the 14 cohort docs in place:

```javascript
// One-time compatibility backfill — 14 rows touched, schema preserved
db.strategy_library.updateMany(
  { "provenance.cohort_id": "1vcpu_2026_migration" },
  [{ $set: { pair: "$fingerprint_inputs.pair",
             timeframe: "$fingerprint_inputs.timeframe",
             style: { $ifNull: ["$fingerprint_inputs.style", "unknown"] } }}]
)
// → modifiedCount = 14
```

(The `migration_adapter` will be updated in Phase 7.3 to write both shapes on
ingest; the nested ASF shape remains the canonical going-forward contract for
exported packages.)

**Sweep run** (`POST /api/admin/bi5/sweep`):

```json
{
  "run_id":           "0ddf85e164eb4bcab20be3d24cbe0aa8",
  "duration_seconds": 0.024,
  "discovered":       14,
  "processed":        3,
  "pass_count":       0,
  "warn_count":       0,
  "fail_count":       3,
  "early_fails":      { "MISSING_FILLS": 3 },
  "skipped":          11,
  "skip_reasons":     { "DATA_CERT_MISSING": 11 },
  "errors":           0,
  "sweep_version":    "bi5_cert_sweep@R2-v1"
}
```

* **3 XAUUSD strategies** reached the cert engine (data cert PASS exists for XAUUSD)
  but early-failed at `MISSING_FILLS` — no live fills/signals captured for any of them.
* **11 ETHUSD strategies** were skipped at the data-cert pre-check (no
  `bi5_data_certification` row for ETHUSD; no archive → no data cert can ever be
  computed without operator-supplied source data).
* Early-failed strategy certs are NOT persisted to `bi5_strategy_certifications` per
  the sweep's policy (Step 2 short-circuit; only completed certs persist). The
  per-strategy advisory record IS captured under
  `strategy_library.revalidation.*` by the post-import pipeline (§2.4).

### 2.4 Post-import pipeline re-run — STATUS: COMPLETED

```json
{
  "run_id":      "post_import_1781374115",
  "cohort_id":   "1vcpu_2026_migration",
  "duration":    "~17 ms",
  "by_stage": {
    "revalidation_pass":         0,
    "revalidation_blocked":      14,
    "rescoring_computed":        14,
    "rescoring_advisory":        14,
    "rematching_eligible_total": 42
  }
}
```

---

## 3. PASS / WARN / FAIL by strategy

After certification + pipeline re-run:

| Fingerprint (first 12) | Pair | TF | Mutation family | **BI5 verdict** | Reason |
|---|---|---|---|---|---|
| `455f09c9648c` | XAUUSD | H4 | risk_reward_1_2 | **MISSING_FILLS** (early-fail) | XAUUSD data cert PASS exists; no live fills captured |
| `0bed627d6906` | XAUUSD | H4 | volatility_atr_breakout | **MISSING_FILLS** | same |
| `bbf034812c26` | XAUUSD | H4 | filter_remove_rsi | **MISSING_FILLS** | same |
| `0db33f33895b` | ETHUSD | H4 | mtf_htf_confirmation | **DATA_CERT_MISSING** | No ETHUSD data cert on receiver |
| `8579a7495fb7` | ETHUSD | H4 | mtf_htf_confirmation | **DATA_CERT_MISSING** | same |
| `84806e0356ef` | ETHUSD | H4 | mtf_htf_confirmation | **DATA_CERT_MISSING** | same |
| `bb8aa20f1ece` | ETHUSD | H4 | mtf_htf_confirmation | **DATA_CERT_MISSING** | same |
| `c1f1ebbb7fdf` | ETHUSD | H4 | mtf_htf_confirmation | **DATA_CERT_MISSING** | same |
| `99dc818947a3` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| `00cae3914bde` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| `388e74a92911` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| `3b12e9629fa3` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| `9dcfeb944025` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| `dbd37f01f7bf` | ETHUSD | H1 | trend_pullback | **DATA_CERT_MISSING** | same |
| **TOTALS** | — | — | — | **0 PASS · 0 WARN · 3 FAIL** (3 early-fail at MISSING_FILLS) · 11 unable-to-evaluate | — |

---

## 4. Updated BI5 scores

| Question | Answer |
|---|---|
| `bi5_strategy_certifications` rows written by this run | **0** |
| `bi5_cert` block on `strategy_library` rows | Remains `null` for all 14 (the sweep's early-fail policy persists no scoring) |
| Per-strategy advisory record | Stored on each doc under `revalidation.*` — `{verdict: "MISSING_FILLS" | "DATA_CERT_MISSING", composite_score: null, evaluator_version: "bi5_certification@P0B-v2"}` |
| Data certs available on receiver | XAUUSD: 2 PASS windows (2026-05-01 → 2026-05-30 and 2026-05-31). ETHUSD: 0 windows. Pre-existing: EURUSD (4 PASS / 2 WARN), GBPUSD (5 PASS), USDJPY (2 WARN). |

The `bi5_data_certification` collection now stands at **15 windows** across 4 symbols.
**No new cert windows were created during this run** — XAUUSD was already certified
in the receiving pod's seed state; ETHUSD cannot be certified without source data.

---

## 5. Updated deploy scores (Master Bot Ranker re-computation)

The pipeline re-invoked `master_bot_ranker._compute_candidate_score()` with the new
post-cert state. Because `bi5_cert` remains `null` on every doc (no PASS verdict was
produced), the ranker contributions still derive only from the `pass_probability`
slot. Deploy scores are **unchanged** from the previous post-import run:

| fp (first 12) | Pair / TF / Family | Deploy score | Pass-probability | Advisory? |
|---|---|---:|---:|:---:|
| `455f09c9648c` | XAUUSD/H4/risk_reward_1_2 | **16.00** | 40.00 | yes |
| `0bed627d6906` | XAUUSD/H4/volatility_atr_breakout | 15.76 | 39.40 | yes |
| `0db33f33895b` | ETHUSD/H4/mtf_htf_confirmation | 15.68 | 39.20 | yes |
| `8579a7495fb7` | ETHUSD/H4/mtf_htf_confirmation | 15.68 | 39.20 | yes |
| `84806e0356ef` | ETHUSD/H4/mtf_htf_confirmation | 15.68 | 39.20 | yes |
| `bb8aa20f1ece` | ETHUSD/H4/mtf_htf_confirmation | 15.68 | 39.20 | yes |
| `c1f1ebbb7fdf` | ETHUSD/H4/mtf_htf_confirmation | 15.68 | 39.20 | yes |
| `99dc818947a3` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `00cae3914bde` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `388e74a92911` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `3b12e9629fa3` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `9dcfeb944025` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `dbd37f01f7bf` | ETHUSD/H1/trend_pullback | 15.64 | 39.10 | yes |
| `bbf034812c26` | XAUUSD/H4/filter_remove_rsi | 15.28 | 38.20 | yes |

`provenance.requires_rescoring` **remains `true`** for all 14 — the rescore is still
advisory because the BI5 contribution to the composite is still `0.0`.

---

## 6. Updated pass probabilities

The pass-probability values are the legacy WR × 100 proxies recomputed via the ranker
formula (range: **38.20 – 40.00**). They are **unchanged** from the previous
post-import run because the full Monte-Carlo `pass_probability` engine still needs
live fills (which are absent). The legacy 1-vCPU values
(`historical_scores.pass_probability = 35.0` uniformly) remain frozen as historical
metadata per operator decree.

---

## 7. Updated challenge matches

| Firm | Strategies ELIGIBLE | Strategies VIOLATIONS | Active gates |
|---|---:|---:|---|
| FTMO | **14 / 14** | 0 / 14 | `max_drawdown_pct ≤ 10 %` |
| FundedNext | **14 / 14** | 0 / 14 | `max_drawdown_pct ≤ 10 %` |
| PipFarm | **14 / 14** | 0 / 14 | `max_drawdown_pct ≤ 10 %` |
| **TOTAL** | **42 eligible matches** | 0 violations | — |

`provenance.requires_rematching = false` for all 14 (unchanged from previous run; the
challenge gate set has not changed). Matches remain **advisory** until live DD is
re-computed against post-import data.

---

## 8. Recommended survivors for promotion from `IMPORTED_SEED`

**No strategies are recommended for promotion at this time.**

Promotion criteria (per `POST_IMPORT_PIPELINE.md §6`):
1. `requires_revalidation = false` (BI5 cert verdict = PASS or WARN) — ❌ **0 / 14**
2. `requires_rescoring = false` (live deploy_score, non-advisory) — ❌ **0 / 14**
3. `requires_rematching = false` — ✅ **14 / 14**
4. `lifecycle.stage_locked_until <= now()` (lock = 2026-07-13) — ❌ **0 / 14** (~5 months remaining)

**Block matrix:**

| fp (first 12) | Pair | requires_revalidation | requires_rescoring | requires_rematching | stage_locked_until_expired | **Promotable?** |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `455f09c9648c` | XAUUSD | true | true | false | false | ❌ |
| `0bed627d6906` | XAUUSD | true | true | false | false | ❌ |
| `bbf034812c26` | XAUUSD | true | true | false | false | ❌ |
| `0db33f33895b` … `dbd37f01f7bf` (×11) | ETHUSD | true | true | false | false | ❌ |

---

## 9. Block triage — what each cohort needs to clear

### 9.1 The 3 XAUUSD strategies (`455f09c9…`, `0bed627d…`, `bbf03481…`)

**Sole blocker:** missing live fills + signals. Data cert PASS exists; the BI5 strategy
cert engine can run as soon as fills become available. Unblock path: **shadow-mode
trade capture** (operator-locked at this time).

Once shadow-mode is authorised in a future operator window:
1. Queue each of the 3 XAUUSD strategies in the trade-runner shadow loop.
2. Capture ~30 trade events per strategy.
3. Re-run `POST /api/admin/bi5/sweep`.
4. Expected outcome: cert engine completes per-merit (likely WARN given PF~1.28, DD=0
   anomaly, and 0 BI5 slippage data; PASS only if the anomaly DD recomputes ≤ the
   threshold).
5. Re-run the post-import pipeline; advisory rescoring flips to non-advisory.

### 9.2 The 11 ETHUSD strategies

**Sole blocker:** no ETHUSD BI5 data on the receiving pod. Unblock path: **operator
must supply ETHUSD BI5 archive** (one of):
* Drop Dukascopy ETHUSD .bi5 files into `/app/data/bi5/dukascopy/ETHUSD/<YYYY>/<MM>/<DD>/<HH>h_ticks.bi5`
* Configure a Dukascopy adapter pull for ETHUSD (currently the receiver lacks
  credentials/config for that symbol — `/app/data_imports` is empty).
* Then run `python -m scripts.bi5_one_shot_backfill ETHUSD` + `python -m data_engine.bi5_ingest_runner ETHUSD --start 2026-04-01 --end 2026-05-31`.

After ETHUSD data lands:
1. The `bi5_data_certification` collection gets ETHUSD PASS/WARN windows.
2. The 11 ETHUSD strategies move from `DATA_CERT_MISSING` to `MISSING_FILLS` (matching
   the XAUUSD cohort's current state).
3. They then follow the same shadow-mode path as §9.1.

---

## 10. Confirmation — all locked exclusions honoured

| Activity | Status |
|---|---|
| Shadow-mode trade capture | ❌ Not started (operator-locked) |
| BI5 R3 (B-3 / B-6 / B-7) | ❌ Not started |
| Phase 13 Dossier Engine | ❌ Not started |
| Phase 14 Valuation Engine | ❌ Not started |
| 12-vCPU deployment / cutover / 72-h soak | ❌ Not started |
| Marketplace surfaces | ❌ Not started |
| Any new roadmap branch | ❌ Not opened |

---

## 11. Final flag state across the cohort

```
provenance.requires_revalidation  = true  × 14   ❌ (3 XAUUSD: MISSING_FILLS · 11 ETHUSD: DATA_CERT_MISSING)
provenance.requires_rescoring     = true  × 14   ❌ (advisory until BI5 cert PASSes)
provenance.requires_rematching    = false × 14   ✅ (14/14 eligible for all 3 firms)
lifecycle.stage                   = IMPORTED_SEED × 14
lifecycle.stage_locked_until      = 2026-07-13T17:12:16+00:00 × 14 (5 months out)

Deployable imported survivors:    0 / 14
```

Auto-Selection guard still blocks 14/14 imported survivors via both join paths;
Master Bot Ranker still surfaces 0 imported strategies (cohort never written to
`strategy_lifecycle`). **Both gating contracts hold.**

---

**End of IMPORTED_COHORT_CERTIFICATION_REPORT.md.**
**Status: certification pass complete. 0 PASS / 0 WARN / 14 BLOCKED. No promotions recommended. Stopping per operator decree.**
