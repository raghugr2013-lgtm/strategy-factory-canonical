# ROADMAP_SEQUENCE_DECISION.md

**Document class:** Read-only roadmap sequencing decision report — BI5-first vs Import-first, ahead of the GATE 3 authorization.
**Date:** 2026-06-12
**Discipline:** No code changes. No BI5 restore. No imports. No flag changes. No writes outside this documentation.
**Operator's stated goal:** *Maximize long-term system quality, not simply import as early as possible.*
**Grounding:** `IMPORT_DRYRUN_VALUE_REPORT.md` (pod state) · `POST_IMPORT_PIPELINE.md` (stage semantics) · `MIGRATION_PRIORITY.md` (tier policy) · PRD §6 (BI5 R2/R3 scope: R2 = B-4/B-5/B-8, ≈3–4 d; R3 = B-3/B-6/B-7, ≈5–7 d) · live DB/filesystem evidence gathered in the dry-run.

---

# 1. The decision in one paragraph

The import's value is realized **only through the 6-stage post-import pipeline**, and the pipeline's first stage (Re-Profile) consumes BI5 tick data that the pod currently has **none of** (0 ticks, 0% coverage). Stage 2 (Re-Score / pass-probability) and Stage 3 (Re-Rank) inherit whatever evidence Stage 1 produced, and BI5 R2 is precisely the machinery that turns raw ticks into **certification evidence + ranker weights**. Importing first therefore produces either (a) inert rows that wait for data anyway, or (b) scores computed on no/weak evidence that must be recomputed — and re-reviewed — later. Restoring data first costs hours; R2 costs 3–4 days; both are already on the roadmap. **Path A wins on every quality dimension and ties or wins on effort. The only thing Path B buys is earlier presence of un-scored rows in the library — which serves no operator workflow.**

---

# 2. Critical-path fact that frames everything

**The export package is operator-side.** Its delivery is independent of both paths and can proceed in parallel with all BI5 work. Choosing Path A does **not** delay the import by the BI5 duration — the package delivery + TRUE dry-run (read-only) can complete *during* the BI5 work. Path A's "delay" to the import is therefore largely an illusion: realistic GATE 3 date differs by only ~3–5 days between paths, while the quality difference is permanent.

---

# 3. Path A — BI5 first, then import

**Sequence:** restore 98 MB archive → ingest pass → (gap backfill as needed) → BI5 R2 (auto-cert sweep + ranker weights + lifecycle surfacing, ≈3–4 d) → import + single pipeline run. (R3 placement analysed in §5.)

| Dimension | Assessment |
|---|---|
| **Strategy quality** | ⭐ MAXIMAL. T1 seeds are profiled against real ticks on first pass; weak strategies are exposed immediately; survivors enter the library with credible, evidence-backed metrics. No score ever needs to be "walked back". |
| **Pass-probability accuracy** | ⭐ HIGH. `pass_probability.py` operates on a real current-market profile; with R2 in place, `certification_verdict` + `slippage_score` feed the deploy-score formula (B-5), so Stage 4 challenge matching (FTMO 5/10/10 · FundedNext 5/10/10 · PipFarm 4/8-trailing/12) is computed from grounded inputs. The probability you act on is the probability you keep. |
| **Profiling / scoring quality** | ⭐ HIGH and SINGLE-PASS. Stage 1 succeeds for every pair the data covers (EURUSD near-6-months, GBPUSD ~3.5 months, USDJPY/XAUUSD 1 month from the archive; gaps known *before* the run via the dry-run's pair distribution). Stages 2–3 run once, on full evidence. Operator reviews ONE trustworthy ranking. |
| **Future execution realism** | STRONG. The same restored ticks are the substrate R3 replays (B-3/B-6/B-7). Certification verdicts from R2 also feed Phase 13 Evidence Score and Phase 14 scorecards — the import's lineage lands in a system already wired for evidence. |
| **Engineering effort** | Archive restore + ingest: **~1–2 h**. R2: **≈3–4 d** (already-committed P0 roadmap work — not new cost, just re-ordered). Import code tasks (~200 LOC) unchanged. **No duplicated pipeline runs, no re-review cycles.** |
| **Risk** | LOW. Archive restore is additive disk + idempotent ingest (BI5 R1 machinery is built and verified). R2 is backend work testable on real data *before* the import depends on it. Failure modes surface pre-import instead of mid-pipeline. Residual risk: archive gaps for pairs the export needs (US100/BTCUSD/ETHUSD have zero data from any source) — mitigated because the TRUE dry-run reveals the export's pair distribution before the pipeline is scheduled, leaving time for targeted Dukascopy backfill. |

---

# 4. Path B — import first, BI5 afterwards

**Sequence:** import package → run (or hold) the pipeline → restore archive → R2/R3 → re-run affected stages.

| Dimension | Assessment |
|---|---|
| **Strategy quality** | DEGRADED-THEN-REPAIRED. Two sub-cases: **(B-hold)** import but don't run the pipeline → strategies sit as inert `IMPORTED_SEED` rows delivering zero workflow value until data exists — strictly dominated by Path A. **(B-run)** run the pipeline now → Stage 1 fails for ~100% of strategies (0% coverage) and the pipeline **auto-pauses by design** (>50% profile failures, `POST_IMPORT_PIPELINE.md` §11). Net: quality identical to Path A *eventually*, but only after a second full pass. |
| **Pass-probability accuracy** | POOR INITIALLY. Without tick-grounded profiles, Stage 2 falls back to legacy-metric heuristics → systematically over/under-confident probabilities. Any Stage 4 matching done on them propagates error into challenge recommendations. When R2 lands, every probability shifts — **ranks shuffle after the operator has already seen them**, eroding trust in the scoring system (an anchoring cost that persists even after numbers are corrected). |
| **Profiling / scoring quality** | DOUBLE-PASS. `profile_failed=true` flags across the set, then full re-profile + re-score + re-rank after data/R2 arrive. Compute cost is trivial (~17 min) but **operator review cost doubles** and the library's interim state is misleading. |
| **Future execution realism** | NEUTRAL-TO-NEGATIVE. Nothing about importing early advances R2/R3; it merely time-slices attention away from them. Worst case: pressure to "try" paper rehearsal of imported candidates before R3 → rehearsal evidence generated on bar-approximation instead of tick replay, polluting early forward-test history. |
| **Engineering effort** | Same code tasks (~200 LOC) + same BI5 work later + **extra**: re-run orchestration, re-review, and explaining interim-vs-final score discrepancies. Strictly ≥ Path A. |
| **Risk** | LOW data-loss risk (import is non-destructive, tier-tagged, reversible) but **MEDIUM decision-quality risk**: interim garbage scores visible in Explorer/Portfolio/Master-Bot surfaces; possibility of premature promotion judgments; double-review fatigue. The only mitigation is to hold the pipeline — which converts B into "import and wait", i.e. value-free early import. |

---

# 5. Where do R2 and R3 belong relative to the import?

| Item | Before import? | Reasoning |
|---|---|---|
| **Archive restore + ingest (new item)** | **YES — mandatory** | Stage 1 is non-functional without it. ~1–2 h. Highest leverage-per-hour action on the whole roadmap. |
| **BI5 R2 (B-4/B-5/B-8, ≈3–4 d)** | **YES — strongly recommended** | R2's outputs (`bi5_cert.certification_verdict`, `slippage_score` ranker weights, lifecycle surfacing) are direct inputs to the import's Stage 2/3 scoring. Running the import's scoring before R2 guarantees a full re-score later. R2 is also already-committed P0 work — this is a re-order, not an addition. |
| **BI5 R3 (B-3/B-6/B-7, ≈5–7 d)** | **NO — after import is fine** | R3 changes *execution-stage* realism (paper-exec tick replay, simulate_fills, Trade Runner consolidation). It does not feed Stages 1–6 scoring. Its hard deadline is: **before any imported candidate is promoted to paper rehearsal**. Scheduling it immediately after the import (or in parallel with the pipeline run) loses nothing. |

This yields the recommended **hybrid "A1"**: full Path A for data + R2, with R3 deliberately deferred to post-import — capturing all of Path A's quality with ~5–7 fewer days on the critical path.

---

# 6. Other roadmap items — should anything else move ahead of the import?

| Item | Move ahead? | Why |
|---|---|---|
| Export package delivery (operator-side) | **PARALLEL — start now** | The true critical path. Independent of all engineering. Enables the TRUE read-only dry-run (`IMPORT_DRYRUN_RESULTS.md` with real counts/yields) which should inform the final GATE 3 call and the backfill plan. |
| `EMERGENT_LLM_KEY` decision | **YES (a decision, not work)** | Determines whether Stage 2 runs full or heuristic-only. Deciding late risks a mid-pipeline pause. |
| Firm approval policy (3 firms currently `parsed`, 0 approved) | **YES (minutes)** | Stage 4 needs a confirmed matching policy; approving FTMO/FundedNext/PipFarm (or confirming `parsed`-is-matchable) is trivial and removes a known unknown. |
| T1 filter knob confirmation (`MIGRATION_PRIORITY.md` §8) | **YES (a decision)** | Four knobs (trade floor 30 · 365-d window · 30-d lock · 5-line guard) — confirm before importer is coded. |
| Targeted Dukascopy backfill (gap pairs/ranges) | **CONDITIONAL** | Decide *after* the TRUE dry-run reveals the export's pair × timeframe distribution. Backfill only what the T1 set actually needs. |
| Unique-fingerprint index pre-create | **Folded into importer** | One line; recorded in `IMPORT_DRYRUN_VALUE_REPORT.md` §2.3. |
| BI5 R3 | NO | §5 — post-import, pre-rehearsal. |
| P2 UI additive passes (Backfill-Now button, DSR Audit History, Activation Timeline, Widening History) | NO | Zero coupling to import quality. Note: the Backfill-Now button becomes *more* useful right after the archive restore — natural bundling with post-import UI work. |
| FS veto lift / Auto Learning / Notification Center / Copilot v2 | NO | Independent decrees; no interaction with import quality. |
| Phase 13/14/15 engines | NO | Downstream consumers of R2 + import evidence — sequence is already correct. |
| Quarantined-files architectural review | NO | Janitorial; no coupling. |

---

# 7. Side-by-side verdict

| Dimension | Path A (BI5 → import) | Path B (import → BI5) |
|---|---|---|
| Strategy quality | ⭐ single-pass, evidence-backed | interim-degraded, repaired later |
| Pass-probability accuracy | ⭐ grounded + R2 evidence from first run | heuristic-first, ranks shuffle later |
| Profiling/scoring quality | ⭐ one trustworthy pass | double-pass, misleading interim state |
| Future execution realism | ⭐ same ticks feed R3 + Phase 13/14 evidence | neutral at best |
| Engineering effort | restore ~1–2 h + R2 3–4 d (already-P0) | same + re-run + double review |
| Risk | LOW (pre-import failure surfacing) | LOW data-risk, MEDIUM decision-quality risk |
| Time to GATE 3 | ~4–5 days (package delivery runs in parallel) | ~0–1 day, but value-realization date is **the same or later** than A |

**RECOMMENDATION: PATH A — hybrid variant A1.**

```
NOW (parallel)   ── Operator: deliver export package → TRUE read-only dry-run
NOW (decisions)  ── LLM-key choice · firm approval policy · T1 knobs
STEP 1 (~1–2 h)  ── Restore 98 MB BI5 archive + ingest pass → BI5 Health green
                    for EURUSD/GBPUSD (+USDJPY/XAUUSD May)          [authorization needed]
STEP 2 (≈3–4 d)  ── BI5 R2: B-4 auto-cert sweep · B-5 ranker weights · B-8 surfacing
STEP 3 (cond.)   ── Targeted Dukascopy backfill for gaps the dry-run proves material
GATE 3           ── Import + single 6-stage pipeline run on full evidence
STEP 4 (≈5–7 d)  ── BI5 R3 (tick-replay execution) — BEFORE any imported candidate
                    is promoted to paper rehearsal
THEN             ── Resume roadmap (Phase 13 prerequisites now fed by R2 + import evidence)
```

This sequence makes every number the system ever shows you about an imported strategy **correct the first time it appears** — which is the literal definition of the stated goal: long-term system quality over import speed.

---

# 8. State of this document

* Read-only. No code changed, no BI5 restored, no import performed, no flags flipped, no writes outside `/app/memory/`.
* Awaiting operator decisions: Path choice · Step 1 authorization · LLM key · firm approval policy · T1 knobs · package delivery.

**End of report.**
