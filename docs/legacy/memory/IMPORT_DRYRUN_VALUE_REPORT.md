# IMPORT_DRYRUN_VALUE_REPORT.md

**Document class:** Read-only dry-run import preview + comprehensive value assessment for the GATE 3 decision.
**Date:** 2026-06-12
**Discipline honoured:** ZERO writes — no DB inserts, no collections created, no files placed in `/app`, no flags flipped, no importer code written, no import executed. All evidence below was gathered via read-only queries, in-memory function calls, and inspection of the operator's uploaded archives.

---

# 1. THE HEADLINE FINDING — the dry-run cannot reach the strategies, because the export package is not on the pod

| Evidence | Result |
|---|---|
| `/app/_migration_inbox/` (the contracted delivery path, `MIGRATION_EXPORT_PLAN.md` §7) | **Does not exist — no package ever delivered** |
| Full filesystem sweep for `.bson` / `mongodump` / `strategy_export*` / JSON strategy dumps | **None found** |
| Canonical `strategy_library` collection | **0 documents** |
| Uploaded asset `App.zip` (137.4 MB) — fully inspected | Code + BI5 tick archive only. **No Mongo dump, no strategy export** |
| Uploaded asset `App backup.zip` (125.6 MB) — fully inspected | Same: code + the same BI5 archive. **No strategy data** |
| Uploaded assets `Frontend.zip`, `Frontend from old 1vcpu…zip`, `screenshots…docx` | UI artefacts only |

**Conclusion:** The 1-vCPU strategies live in the old pod's MongoDB, which was never exported into any artefact this pod has received. `DOWNLOAD_MANIFEST.md` has been "⏳ awaiting operator drop" since it was written; that remains the true state. **A quantitative dry-run (real counts, real T1 yield, real dedupe rate, real pass-probability distribution) is impossible until the export package lands.** Everything else in this report is the maximum analysis the pod permits today — and it is substantial.

---

# 2. What the dry-run DID verify (read-only, on real machinery)

## 2.1 Identity / dedupe engine — LIVE SMOKE TEST PASSED ✅

Executed `engines/strategy_library._fingerprint()` in-memory (no DB):

| Property | Test | Result |
|---|---|---|
| Param-order + whitespace + case invariance | same strategy, shuffled params, padded text | **identical SHA1** ✅ |
| Param bucketing tolerance | `sl_pips: 50` vs `52` | **identical SHA1** ✅ (near-duplicates collapse by design) |
| Key sensitivity | EURUSD vs GBPUSD, same everything else | **different SHA1** ✅ |

Matches `MIGRATION_COMPATIBILITY_AUDIT.md` §1 — 1-vCPU fingerprints will reproduce bit-identically on this pod. **No re-fingerprinting needed; dedupe semantics sound.**

## 2.2 Collision baseline — ZERO ✅

`strategy_library` = 0 docs → T1 filter #8 ("fingerprint already in canonical seed") will skip **nothing**. Every imported strategy is net-new. Best possible import window: no merge logic exercised, rollback is a clean `deleteMany`.

## 2.3 ⚠ Index finding (correction to `IMPORT_READINESS_REPORT.md` §2.5)

The readiness report claimed the unique `fingerprint` index is "hardened at boot". **Live inspection shows otherwise:** `strategy_library` currently carries only `_id_`, `ix_lib_hash` (on `strategy_hash`), `ix_lib_created_at`. The unique fingerprint index is created **lazily inside the save path** (`strategy_library.py` L326) — it doesn't exist yet because the collection has never been written.
**Impact:** none for normal operation, but a bulk importer must `create_index("fingerprint", unique=True)` **before** inserting (one line in the importer, already implied by the conflict-handling design). Recorded so the future importer task includes it explicitly.

## 2.4 💎 DISCOVERY — a 98 MB BI5 tick archive is already in your possession

Both `App.zip` and `App backup.zip` contain `_inventory/app_extracted/data/bi5/dukascopy/` — **7,462 real `.bi5` tick files (~98 MB)** from the 1-vCPU pod, never restored onto this pod (`/app/data/` holds only `host_id`; live BI5 coverage = 0%, 0 ticks):

| Symbol | Coverage in archive |
|---|---|
| EURUSD | **Jan–Jun 2026, near-complete (~3,766 hourly files)** |
| GBPUSD | Jan, Feb, partial Mar, May 2026 (~2,208 files) |
| USDJPY | May 2026 (744 files) |
| XAUUSD | May 2026 (744 files) |
| US100 · BTCUSD · ETHUSD | **absent** |

**Why this matters for import value:** Stage 1 (Re-Profile) of the post-import pipeline is currently the single hardest blocker (it fails for any pair with no market data — and today ALL pairs have none). Restoring this archive into `/app/data/bi5/` + one ingest pass would give Stage 1 real data for EURUSD/GBPUSD immediately, without re-downloading from Dukascopy. If the 1-vCPU strategy set is EURUSD/GBPUSD-heavy (likely, given the archive's shape mirrors what that pod traded), the pipeline's data prerequisite is already ~80% solved. *(Restoring it is a write — NOT done; flagged as a pre-pipeline option for your authorization.)*

---

# 3. Stage-by-stage pipeline readiness (dry assessment against live pod state)

| Stage | Engine present | Data/config prerequisite — live state today | Verdict if run today |
|---|---|---|---|
| Import (T1/T2/T3 tiering) | importer NOT yet written (~120 LOC, held back per your directive) | package absent | **BLOCKED — no package** |
| 1 · Re-Profile | `strategy_profiler.py` ✅ | BI5 coverage **0.0%**, 0 ticks (archive recoverable per §2.4) | would fail 100% → auto-pause |
| 2 · Re-Score | `pass_probability.py` + RoR + decay ✅ | `EMERGENT_LLM_KEY` **absent** → heuristic-only (`llm_optional=true`) mode available | degraded-but-viable |
| 3 · Re-Rank | ranking engines ✅ | pure compute | **READY** |
| 4 · Re-Match | `phase4_matcher.py` + challenge engine ✅ | 3 firms in catalogue (FTMO · FundedNext · PipFarm), **all status=`parsed`, 0 approved**; 3 fully-parameterised challenge rule sets verified live (FTMO 5%/10%/10% · FundedNext 5%/10%/10% no-time-limit · PipFarm 4%/8%-trailing/12%) | READY — **operator should confirm whether `parsed` firms need approval before matching** |
| 5 · Re-Portfolio | portfolio engines ✅ | depends on Stage 4 | READY (chained) |
| 6 · Re-Masterbot | master bot engines ✅ | depends on Stage 5 | READY (chained) |

**Bonus since the plans were written:** the UI restoration mounted `propfirm#challenge` — Stage 4 outputs are now fully drillable in-UI (this was a planned gap; it's closed).

---

# 4. Expected value model (scenario-based — real numbers require the package)

Operator-reported source size: **"hundreds"** of strategies. Applying the locked T1 filter (`MIGRATION_PRIORITY.md` §2: trades ≥ 30 · PF ≥ 1.30 · WR ≥ 0.40 · maxDD ≤ 20% · not DEMOTED/RETIRED/BANNED · ≤ 365 d old):

| Scenario | Source rows | Plausible T1 yield* | T2 archive | Import runtime | Pipeline runtime (single-thread) |
|---|---|---|---|---|---|
| Conservative | 200 | ~30–60 seeds | ~140–170 | < 2 min | ~7 min |
| Mid (operator range) | 500 | ~75–150 seeds | ~350–425 | < 3 min | ~17 min |
| Upper | 2,000 | ~300–600 seeds | ~1,400–1,700 | < 10 min | ~1–2 h (or ~⅓ with process pool) |

\* Yield band assumes a typical evolved-survivor distribution; the true number is one of the first outputs of the real dry-run once the package lands. Strategies on US100/BTCUSD/ETHUSD will import fine but sit `profile_failed` until those pairs get data (Dukascopy backfill).

**What the import buys (per the locked plans, all verified still-true):**
1. **Survivor seeds** — T1 strategies become re-scored, re-ranked, firm-matched candidates the factory does NOT have to re-discover (each survivor historically costs hours of generate→mutate→validate compute + LLM budget).
2. **Mutation lineage** — `mutation_events` parent/child DNA enables re-mutation from known-good seeds.
3. **Evidence history** — performance/lifecycle history feeds aging, stability, and (later) Phase 13 dossiers + Trust Score.
4. **Immediate pipeline content** — Portfolio Builder and Master Bot get real candidates; today every one of those surfaces shows zeros.

**What it costs:** ~200 LOC of held-back code (importer + validation script + pipeline router + 5-line auto-selection guard), < 3 min import, ~17 min pipeline, ≤ 100 MB disk (pod has plenty). **Risk:** LOW — every tier write is provenance-tagged, rollback is a clean tier-boundary delete, deployment is quadruple-locked (`IMPORTED_SEED` stage + 30-day lock + revalidation flag + operator-only promotion).

---

# 5. Updated risk register (deltas vs `IMPORT_READINESS_REPORT.md` §4)

| Risk | Then | Now | Movement |
|---|---|---|---|
| Export package absent | implied "secured externally" | **confirmed absent from pod, both 130 MB archives exhaustively ruled out** | ⚠ hardened into THE blocker |
| BI5 coverage 0% at Stage 1 | MED | MED → **LOW-MED** (98 MB archive recoverable from your own zips for EURUSD/GBPUSD/USDJPY/XAUUSD) | ✅ improved |
| LLM key missing at Stage 2 | HIGH | unchanged (heuristic mode remains the fallback) | = |
| Fingerprint index assumption | "hardened at boot" | actually lazy-on-first-write; importer must pre-create | new, trivially fixed |
| Firm catalogue staleness | "operator confirms" | 3 firms live but all `parsed`/0 approved — confirm matcher policy | new, decision needed |
| Strategy pairs outside seeded universe | MED | unchanged (US100/BTCUSD/ETHUSD have zero data from any source) | = |

---

# 6. Recommendation

**GATE 3 should NOT open yet — not because the import lacks value (it is high-value, low-cost, low-risk), but because the single input it needs is not on the pod.**

Recommended sequence (each step awaits your go):

1. **You deliver the export package** to `/app/_migration_inbox/` (Format A/B/C per `MIGRATION_EXPORT_PLAN.md` §3 — `mongodump --archive --gzip` of the 7 collections is preferred; the §3 command is ready to copy-paste on the old pod). If the old 1-vCPU pod is still reachable, this is ~5 minutes of work.
2. **I run the TRUE read-only dry-run** against the delivered package (decode in `/tmp`, zero DB writes): integrity + manifest check, per-collection counts, fingerprint format scan, T1/T2/T3 classification simulation with the locked filters, dedupe + lineage-orphan rates, per-pair coverage cross-check against available data, and a final quantified value verdict → `IMPORT_DRYRUN_RESULTS.md`.
3. **You review the real numbers** → GATE 3 decision.
4. Only then: the 3 held-back code tasks (~200 LOC), tiered import, 6-stage pipeline.

**Decisions you can make now (none executed without your word):**
- a) Restore the 98 MB BI5 archive from your zips into `/app/data/bi5/` (pre-pipeline data win — independent of import).
- b) Set `EMERGENT_LLM_KEY` (full Stage 2) or accept heuristic-only re-scoring.
- c) Confirm Stage 4 firm policy: match against `parsed` firms, or approve FTMO/FundedNext/PipFarm first.
- d) Confirm the four T1 filter knobs (`MIGRATION_PRIORITY.md` §8) — trade floor 30, 365-day window, 30-day lock, 5-line guard.

---

# 7. State of this document

* Read-only preview. No package imported, nothing persisted, no code written, no flags flipped.
* Companion to: `MIGRATION_EXPORT_PLAN.md` · `MIGRATION_PRIORITY.md` · `MIGRATION_COMPATIBILITY_AUDIT.md` · `DOWNLOAD_MANIFEST.md` · `IMPORT_READINESS_REPORT.md` · `POST_IMPORT_PIPELINE.md`.

**End of report.**
