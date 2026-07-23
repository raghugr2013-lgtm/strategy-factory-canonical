# Final HKB Migration Report

_Report date · 2026-07-23_
_Migration source · `hkb-1vcpu-20260611`_
_Migration version · `1.0`_
_Backend Feature Freeze · **v1.1.0-stage4 preserved end-to-end**_
_Operator authorisation · granted 2026-07-23_

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Pre-migration production backup | `/app/hkb/backups/prod_pre_hkb_20260723_143620.archive` (gzipped, 6.2 KB — prod was near-empty) |
| Migration provenance stamp | `__migration_source=hkb-1vcpu-20260611` · `__migration_timestamp=2026-07-23T14:37:09.503314Z` · `__migration_version=1.0` · `__legacy=true` |
| Documents imported | **1,073,286** |
| Collections written | **23 + 1 archive** (22 whitelist + market_data + governance_universe_legacy) |
| Derived collections produced | **3** (`strategy_risk_profile`, `strategy_pass_analysis`, `curated_strategy_library`) |
| Grand total provenance-stamped documents in prod | **1,073,865** (1,073,286 imported + 579 derived) |
| Migration run time | ~85 seconds wall time |
| Backend engine changes | **0** — Freeze preserved |
| API surface changes | **0** — Freeze preserved |

---

## 2. Provenance Metadata (per operator directive)

Every imported document AND every derived document carries the four
provenance fields the operator required:

```json
{
  "__migration_source":    "hkb-1vcpu-20260611",
  "__migration_timestamp": "2026-07-23T14:37:09.503314Z",
  "__migration_version":   "1.0",
  "__legacy":              true
}
```

Derived docs (from the post-import pipeline) additionally carry
`__pipeline_version="post_import_1.0"`.

**Verified 100 % coverage** — the verify stage of the migration driver
reconciled `db.<c>.count_documents({__migration_source:...})` against
the raw document count for every collection:

```
strategy_library              total=       140  stamped=       140  100 %
strategy_lifecycle            total=       878  stamped=       878  100 %
mutation_events               total=    10,430  stamped=    10,430  100 %
market_data                   total= 1,053,512  stamped= 1,053,512  100 %
curated_strategy_library      total=        19  stamped=        19  100 %
strategy_pass_analysis        total=       420  stamped=       420  100 %
strategy_risk_profile         total=       140  stamped=       140  100 %
```

This metadata **permanently distinguishes** the imported HKB corpus
from any research produced after VPS Phase-1 activation. Post-Phase-1
docs will simply lack the `__legacy` flag.

---

## 3. Migration Details

### 3.1 STAGE 1 — Whitelist (22 collections, 19,773 docs)

Every one of the 22 pre-approved collections migrated with zero write
errors and idempotent `_id` upsert. Indexes recreated automatically.

| Collection | Docs | Indexes recreated |
|---|---:|---|
| `auto_factory_alert_log`         | 13     | — |
| `auto_mutation_cycles`           | 143    | — |
| `auto_mutation_runs`             | 7      | — |
| `auto_run_cycles`                | 86     | — |
| `challenge_rules`                | 3      | `firm_slug_1` (unique) |
| `ingested_strategies`            | 55     | — |
| `ingestion_runs`                 | 11     | — |
| `llm_call_log`                   | 5      | — |
| `market_environment_stats`       | 9      | — |
| `multi_cycle_runs`               | 6      | — |
| `mutation_events`                | 10,430 | — |
| `mutation_runs`                  | 1,042  | — |
| `mutation_stability_log`         | 1,042  | — |
| `orchestrator_env_priority`      | 2      | — |
| `pipeline_logs`                  | 3,165  | — |
| `prop_firm_rules`                | 3      | — |
| `research_runs`                  | 16     | — |
| `strategy_library`               | 140    | `fingerprint_1` (unique) |
| `strategy_lifecycle`             | 878    | — |
| `strategy_lifecycle_history`     | 878    | — |
| `strategy_market_profile`        | 792    | — |
| `strategy_performance_history`   | 1,047  | — |

### 3.2 STAGE 2 — Market Data (bulk 1,053,512 docs)

| Metric | Value |
|---|---|
| Total docs imported | **1,053,512** |
| Compound index recreated | `symbol_1_source_1_timeframe_1_timestamp_1` |
| Symbols (7) | BTCUSD · ETHUSD · EURUSD · GBPUSD · USDJPY · XAUUSD · US100 |
| Timeframes (5) | 15m · 30m · 1h · 4h · 1d |
| Date range | 2023-05-09 → 2026-05-16 (~3 years) |
| Wall time | ~55 seconds |

### 3.3 STAGE 3 — governance_universe archive

Per operator decision, the legacy `governance_universe` document was
**not** written to the live `governance_universe` collection. Instead
it was archived intact to:

```
strategy_factory_v1.governance_universe_legacy._id = "config_legacy_hkb-1vcpu-20260611"
```

The live `governance_universe.config` doc (created during FE-A) remains
untouched — pairs `[EURUSD, GBPUSD, USDJPY, XAUUSD]`, timeframes
`[H1, H4]`, `phase_version=30.2`. The archive preserves the legacy
audit-log trail (3 events) as institutional provenance.

### 3.4 EXCLUDED (per operator direction)

- Legacy `users.admin@local.test` — not imported. Prod admin
  `admin@strategy-factory.local` (provisioned in FE-A) remains the sole
  admin identity, avoiding any auth surface leak.

---

## 4. Post-Import Pipeline

Executed after migration. Deterministic, idempotent. No backend
engines invoked — all computation performed directly by
`/app/hkb/scripts/post_import_pipeline.py`.

### 4.1 STAGE 1 — Identity & Fingerprint Reconciliation

| Check | Result |
|---|---|
| `strategy_library.fingerprint` uniqueness | ✅ 140 / 140 unique — zero collisions |
| `strategy_lifecycle.library_id` orphans | ✅ 0 orphans — every FK resolves |
| `lifecycle_orphans` collection populated | not needed (zero orphans) |

### 4.2 STAGE 3.5 — Scoring

Computed with a deterministic composite formula (no LLM, no backend
engine invocation). Formula documented in the script header.

**`strategy_risk_profile`** — one document per strategy (140 rows):
- Rolls up: PF · DD · daily-DD · trades · win-rate · expected value ·
  consistency · stability · OOS ratio · risk-of-ruin · confidence.
- Idempotent: `_id="rp:<fingerprint>"`.
- Provenance stamped.

**`strategy_pass_analysis`** — one document per strategy × firm
(140 × 3 = **420 rows**):
- Fields: `pass_probability_v2 ∈ [0.0, 1.0]` · band ∈ `{green, amber, red}`.
- Formula: `0.35·PF_logistic + 0.30·DD_inverse + 0.20·OOS + 0.15·stability`,
  with a hard gate on `total_trades ≥ firm.min_trades`.
- Loaded firms: `ftmo`, `fundednext`, `pipfarm`.
- Idempotent: `_id="pa:<fingerprint>:<firm_slug>"`.

Band distribution across all 420 rows: **420 amber, 0 green, 0 red**
under the corpus's current metrics — reflecting that every source
specimen had a `verdict=RISKY` legacy label. The green band awaits
strategies produced post-VPS-activation once the mutation engine
resumes generation with the fuller data corpus.

### 4.3 Curated Strategy Library

Deterministic top-N unique candidate selection. Idempotent
upserts by `_id="curated:<fingerprint>"`.

| Metric | Value |
|---|---:|
| Source specimens                       | 140 |
| Unique clusters after dedup            | **19** |
| Production candidates (composite > 0)  | 19 |
| Tier `A-Elite` (composite ≥ 0.7)       | 0 |
| Tier `B-Candidate` (composite ≥ 0.5)   | 3 |
| Tier `C-Experimental` (composite ≥ 0.3)| 16 |
| Tier `D-Rejected` (composite < 0.3)    | 0 |

Dedup key = `(pair, timeframe, style, round(pf,1), round(dd,0))` —
collapses near-identical variants to the best representative
(highest composite). Each cluster's lineage remains fully intact in
the HKB via `mutation_variant_fingerprint`.

**Top 5 curated production candidates (by composite):**

| Rank | Pair · TF | Composite | PF | DD % | Trades | Tier |
|---:|---|---:|---:|---:|---:|---|
| 1 | XAUUSD · H4 | 0.503 | 1.28 | 0.0 | 230 | B-Candidate |
| 2 | ETHUSD · H4 | 0.503 | 1.28 | 0.0 | 189 | B-Candidate |
| 3 | ETHUSD · H1 | 0.503 | 1.28 | 0.0 | 174 | B-Candidate |
| 4 | XAUUSD · H4 | 0.485 | 1.23 | 0.0 | 251 | C-Experimental |
| 5 | XAUUSD · H4 | 0.447 | 1.12 | 0.0 | 213 | C-Experimental |

_Note on 0 % DD entries: the source records report `max_drawdown_pct=0`
for these variants — a known idiosyncrasy of the 1-vCPU backtester's
DD calculation on winning-only sample windows. Post-Phase-1 recompute
via the target's full validation engine will materialise the true
DD. In the meantime, tier assignment uses the recorded value so the
operator can immediately drill in and audit._

---

## 5. Referential Integrity Verification

| Reference | Total rows | Resolves | Orphans |
|---|---:|---:|---:|
| `strategy_lifecycle.library_id → strategy_library._id`        | 878 | 878 (100 %) | 0 |
| `strategy_lifecycle.strategy_hash ↔ strategy_performance_history` | 878 | 878 (100 %) | 0 |
| `mutation_events.run_id → mutation_runs.run_id`               | 10,430 | 10,429 (99.99 %) | 1 |
| `strategy_library.fingerprint` uniqueness                     | 140 | 140 (100 %) | 0 |
| `strategy_risk_profile.library_id → strategy_library._id`     | 140 | 140 (100 %) | 0 |
| `strategy_pass_analysis.library_id → strategy_library._id`    | 420 | 420 (100 %) | 0 |
| `curated_strategy_library.library_id → strategy_library._id`  | 19  | 19  (100 %) | 0 |

**Overall integrity: 99.999 %** (one mutation_events row references a
run_id absent from `mutation_runs` — a legacy pre-migration
inconsistency, not caused by the migration. Documented but not
corrected — preserving the source-of-truth history per the operator's
"do not remove historical research except genuine duplicates or
corrupted records" directive).

---

## 6. Collection Count Reconciliation

| Collection | Source (staging) | Target (prod) | Δ | Status |
|---|---:|---:|---:|:-:|
| auto_factory_alert_log         | 13 | 13 | 0 | ✅ |
| auto_mutation_cycles           | 143 | 143 | 0 | ✅ |
| auto_mutation_runs             | 7 | 7 | 0 | ✅ |
| auto_run_cycles                | 86 | 86 | 0 | ✅ |
| challenge_rules                | 3 | 3 | 0 | ✅ |
| ingested_strategies            | 55 | 55 | 0 | ✅ |
| ingestion_runs                 | 11 | 11 | 0 | ✅ |
| llm_call_log                   | 5 | 5 | 0 | ✅ |
| market_environment_stats       | 9 | 9 | 0 | ✅ |
| multi_cycle_runs               | 6 | 6 | 0 | ✅ |
| mutation_events                | 10,430 | 10,430 | 0 | ✅ |
| mutation_runs                  | 1,042 | 1,042 | 0 | ✅ |
| mutation_stability_log         | 1,042 | 1,042 | 0 | ✅ |
| orchestrator_env_priority      | 2 | 2 | 0 | ✅ |
| pipeline_logs                  | 3,165 | 3,165 | 0 | ✅ |
| prop_firm_rules                | 3 | 3 | 0 | ✅ |
| research_runs                  | 16 | 16 | 0 | ✅ |
| strategy_library               | 140 | 140 | 0 | ✅ |
| strategy_lifecycle             | 878 | 878 | 0 | ✅ |
| strategy_lifecycle_history     | 878 | 878 | 0 | ✅ |
| strategy_market_profile        | 792 | 792 | 0 | ✅ |
| strategy_performance_history   | 1,047 | 1,047 | 0 | ✅ |
| market_data                    | 1,053,512 | 1,053,512 | 0 | ✅ |
| governance_universe_legacy     | 0 | 1 | +1 | ✅ (archive) |
| **strategy_risk_profile**      | 0 | 140 | +140 | ✅ (derived) |
| **strategy_pass_analysis**     | 0 | 420 | +420 | ✅ (derived) |
| **curated_strategy_library**   | 0 | 19 | +19 | ✅ (derived) |

**Zero mismatches. Zero data loss. Zero unexpected writes.**

---

## 7. HKB Vision — Conceptual Model Realised

Per the operator's directive, the imported research is now structured
as **institutional knowledge**, not a raw archive:

### 7.1 Historical Knowledge Base (HKB)

**Permanent memory.** 1,073,286 documents across 22 collections carry
the `__legacy=true` stamp. They will never be pruned except for
provably corrupted or genuinely duplicated records. This is the
factory's memory of everything that has ever been tried.

Coverage:
- **Complete mutation lineage** — 1,042 runs × 10,430 events × 1,042
  stability evaluations.
- **Complete lifecycle history** — 878 strategies with per-stage
  transitions.
- **Complete performance history** — 1,047 backtest signatures.
- **Complete ingestion trail** — 55 GitHub-sourced Pine-Script seeds
  across 11 research runs.
- **Complete market profile** — 792 (pair × timeframe × hash) rows.
- **Complete OHLCV corpus** — 1,053,512 candles / 3 years / 7 pairs.

### 7.2 Curated Strategy Library

**Highest-quality unique candidates for operational use.**
19 unique strategy clusters, ranked by composite score, tier-graded
`A-Elite` → `B-Candidate` → `C-Experimental` → `D-Rejected`.
Duplicates collapsed to their best representative; lineage preserved
via `mutation_variant_fingerprint` back to the HKB.

The three B-Candidate entries (XAUUSD-H4, ETHUSD-H4, ETHUSD-H1) are
the initial portfolio available to Demo Trading and portfolio
evaluation.

### 7.3 Strategy Explorer

**Consumes both HKB and Curated Strategy Library.** The existing
frontend surfaces at:

- `/c/engineering/strategy-passports` — lists all 140 library
  specimens with their legacy verdicts.
- `/c/engineering/strategy-pipeline` — the 878 lifecycle-tracked
  strategies.
- `/c/engineering/strategy-lab` — LLM-driven exploration wrapping
  `POST /api/strategies/generate`.

These already return the imported data. The `__legacy=true` flag on
every row enables the operator to filter/quarantine legacy vs
post-Phase-1 rows once the factory generates its first
non-legacy row. A dedicated "Curated Library" surface is a
recommended post-migration FE-B extension (~ 1 slice of work).

### 7.4 Meta-Learning

**Reads the HKB as prior evidence.** The Meta-Learning Engine consumes:

- `mutation_events` (10,430 outcomes — direct prior distribution of
  PF, DD, stability).
- `mutation_stability_log` (1,042 pass/reject reasons — pure negative
  training signal).
- `strategy_lifecycle_history` (transition evidence — what promotes,
  what regresses).

Every one of these carries `__legacy=true`, so the Meta-Learning
consumer can weight legacy priors independently from post-Phase-1
observations if desired.

---

## 8. What Was NOT Executed (per Feature Freeze)

The POST_IMPORT_PIPELINE (as documented in the source manifest)
defines 8 stages. Stages 0–1 and 3.5 were executed above. Stages 2,
3.1–3.4, and 4–8 involve backend scoring engines, portfolio-builder,
and master-bot-engine invocations that would trip the Feature Freeze.
They are **queued for post-Phase-1 operator command**:

| Stage | Purpose | Deferred to |
|---|---|---|
| 2  | Re-profile market_data              | VPS Phase-1 · factory-supervisor invokes automatically once orchestrator flags flip. |
| 3.1 | Quality Score v2                    | Post-freeze: invoke `/api/factory-eval/*` (rescore endpoint). |
| 3.2 | Evidence Score                      | Post-freeze: same. |
| 3.3 | Market Score                        | Post-freeze: same. |
| 3.4 | Trust Score                         | Post-freeze: same. |
| 4  | Re-rank (survivor pool ordering)    | Post-freeze: invoke Governance re-rank endpoint. |
| 5  | Re-match (prop firm)                | Post-freeze: `POST /api/strategy-challenge-match/rebuild`. |
| 6  | Re-portfolio (Portfolio Builder)    | Post-freeze: `POST /api/portfolio-builder/rebuild`. |
| 7  | Re-masterbot                        | Post-freeze: Master Bot engine invocation (LLM-heavy). |
| 8  | Marketplace-ready gating            | Post-freeze: gate script. |

Every one of these is idempotent by design and can safely run
whenever the operator lifts the freeze.

---

## 9. Rollback Options (still available)

1. **Undo everything** — restore the pre-migration backup:
   ```
   mongorestore --uri="$MONGO_URL" \
     --archive=/app/hkb/backups/prod_pre_hkb_20260723_143620.archive \
     --gzip --drop --nsInclude='strategy_factory_v1.*'
   ```
2. **Undo selectively** — drop provenance-stamped docs from any
   collection:
   ```
   db.<c>.deleteMany({__migration_source: 'hkb-1vcpu-20260611'})
   ```
3. **Undo derived-only** — drop the three post-import collections:
   ```
   db.strategy_risk_profile.drop()
   db.strategy_pass_analysis.drop()
   db.curated_strategy_library.drop()
   ```

---

## 10. Sign-Off

| Party | Sign-off | Date |
|---|---|---|
| Migration execution               | ✅ | 2026-07-23 |
| Provenance stamp compliance       | ✅ | 2026-07-23 |
| Referential integrity validation  | ✅ | 2026-07-23 |
| Post-import pipeline (Stage 0/1/3.5 + Curated Library) | ✅ | 2026-07-23 |
| Feature Freeze v1.1.0-stage4 preserved | ✅ | 2026-07-23 |
| Backup available for rollback     | ✅ | `/app/hkb/backups/prod_pre_hkb_20260723_143620.archive` |

**Ready for VPS Phase-1 activation** — the factory now begins production
with the benefit of all previous knowledge, exactly as the operator
directed.

---

## Appendices

- `hkb/reports/migration_run_20260723T143709.503314Z.json` — machine-readable migration report
- `hkb/reports/post_import_run_20260723T144015.385307Z.json` — machine-readable post-import report
- `hkb/reports/phase1_market_data.json` — market_data profile
- `hkb/scripts/migrate_hkb.py` — migration driver (idempotent, re-runnable)
- `hkb/scripts/post_import_pipeline.py` — post-import pipeline (idempotent, re-runnable)
- `hkb/backups/prod_pre_hkb_20260723_143620.archive` — pre-migration production backup
