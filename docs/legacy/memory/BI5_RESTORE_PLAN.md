# BI5_RESTORE_PLAN.md

**Document class:** Step 1 implementation plan (Path A1) — BI5 archive restore + ingest. **AWAITING OPERATOR REVIEW — nothing executed.**
**Date:** 2026-06-12
**Constraints honoured in this plan:** no FS / Auto Learning / Notification Center / dormant-system activation · no strategy import · no Phase 13/14/15 reordering · no feature-flag changes.

---

## 1. Exactly what will be restored

| Item | Detail |
|---|---|
| Source | Operator asset `App.zip` (137.4 MB, platform asset store) → internal path `App/_inventory/app_extracted/data/bi5/dukascopy/` (the identical tree also exists in `App backup.zip` as a redundant copy) |
| Payload | **7,462 `.bi5` LZMA-compressed Dukascopy tick files, ~98 MB** — file contents untouched, byte-for-byte copy |
| Destination | `/app/data/bi5/dukascopy/{SYMBOL}/{YYYY}/{MM}/{DD}/{HH}h_ticks.bi5` — **exactly** the layout the canonical `data_engine/tick_archive.py` contract expects (`DEFAULT_ARCHIVE_PATH = /app/data/bi5`); zero path translation needed |
| Then | One run of the existing, already-shipped **B-9 script**: `python -m scripts.bi5_one_shot_backfill` (background, logged). It walks the local archive and registers coverage into the `market_data` collection via `incremental_update_bi5()`; **downloads nothing** |
| Idempotency | Per-file hash check in `bi5_ingest_log` — re-running N times produces zero duplicate rows (verified in script header + R1 sign-off). Partial failure is resumable by re-running |
| Symbol resolution | Script reads the DSR registry (flag ON) — all 7 seeded symbols are checked; only the 4 with archive data will ingest |
| Disk / DB budget | ~98 MB on `/app` (7.5 GB free → trivial). Mongo growth modest (`market_data` stores registered coverage/candles + ingest log rows, not raw tick blobs) |

**No code changes required** — every component (archive reader, ingest runner, backfill script, health endpoint) already exists and was verified in BI5 R1.

## 2. Symbols and date ranges covered

| Symbol | Archive coverage (hourly files) | Approx. span |
|---|---|---|
| **EURUSD** | Jan 744 · Feb 672 · Mar 742 · Apr 720 · May 744 · Jun 144 = **3,766 h** | **2026-01-01 → ~2026-06-06, near-complete (~157 days)** |
| **GBPUSD** | Jan 743 · Feb 671 · Mar 50 (partial) · May 744 = **2,208 h** | Jan–Feb full · early-Mar sliver · May full (~92 days, gap: most of Mar + all Apr) |
| **USDJPY** | May 744 = **744 h** | 2026-05 only (~31 days) |
| **XAUUSD** | May 744 = **744 h** | 2026-05 only (~31 days) |
| US100 · BTCUSD · ETHUSD | **0 files** | none — remain empty until a targeted Dukascopy backfill (decided after the import dry-run reveals whether the export needs them) |

## 3. Expected BI5 Health changes (`/api/diag/bi5/health` + UI)

| Indicator | Before (live now) | Expected after |
|---|---|---|
| `summary.symbols_ok` | 0 / 7 | **4 / 7** (EURUSD · GBPUSD · USDJPY · XAUUSD) |
| `summary.total_ticks_stored` | 0 | millions (registered from 7,462 files) |
| `summary.avg_coverage_pct` | 0.0% | rises materially; exact % depends on the engine's per-symbol expectation window — EURUSD strongest, May-only symbols lower |
| Per-symbol rows | all "no data" | coverage % + `last_bi5_sync` populated (note: archive ends ~2026-06-06, so "freshness" indicators may show ~1-week staleness until the hourly scheduler resumes live ingest) |
| Market Data tab strip | `BI5 DATA · NOT READY 0/7` | **`PARTIAL 4/7`** (strip goes amber — by design; READY requires all 7) |
| Readiness (`/api/admin/readiness`) | RED (blockers: `market_data` + `llm_budget`) | `market_data` blocker clears/downgrades for covered pairs; overall likely AMBER while `llm_budget` persists (see recommendation a) |

## 4. Expected impact on profiling · scoring · pass-probability · validation

| Capability | Impact |
|---|---|
| **Profiling** (`strategy_profiler`, pipeline Stage 1) | Goes from non-functional (100% `profile_failed`) to **fully viable for 4 symbols** — current-market signatures computable against real ticks |
| **Scoring / deploy-score** (Stage 2–3 + ranker) | Grounded inputs instead of empty; after R2 (next step) `certification_verdict` + `slippage_score` join the formula — scores carry evidence on first computation |
| **Pass-probability** | Computed from real current-market profiles → credible Stage 4 challenge matching against the FTMO/FundedNext/PipFarm rule sets |
| **Validation / backtests** | Workspace + Auto Factory validation gain real bars/ticks for the 4 covered pairs; `bi5_realism` stops returning `BI5_DATA_MISSING` for them |
| **BI5 R2 (Step 2)** | The cert sweep finally has data to certify — R2 can be built AND validated against reality instead of fixtures |
| **Auto Factory readiness gate** | `market_data` blocker addressed for covered pairs — the factory moves one gate closer to a real run |

## 5. Rollback procedure

The restore is **purely additive** on both layers; rollback is two bounded operations:

```
1. Filesystem:  rm -rf /app/data/bi5/dukascopy        (returns /app/data to host_id-only state)
2. Mongo:       delete the rows the ingest registered —
                bi5_ingest_log rows written by this run (each carries file path + hash + ts), and
                the market_data coverage rows they registered (tagged by symbol + source on insert).
                The exact filter is taken from bi5_ingest_log itself, making reversal precise.
3. Verify:      /api/diag/bi5/health returns to 0/7 · strip returns to NOT READY.
```

Safety properties: no canonical row is modified in-place (insert-only); the operator UI degrades gracefully to the current "no data" state; re-running the restore after a rollback is the same idempotent operation. A pre-run snapshot of `market_data` + `bi5_ingest_log` counts will be recorded in the execution log for before/after audit.

## 6. Execution outline (~1–2 h, on your go)

```
1. Download App.zip from the asset store → extract ONLY data/bi5 subtree to /tmp
2. Copy subtree → /app/data/bi5/dukascopy/   (rsync-style, additive)
3. Record pre-run Mongo counts (market_data, bi5_ingest_log)
4. Run: python -m scripts.bi5_one_shot_backfill   (background, logged; ~minutes)
5. Verify: health endpoint 4/7 · UI strip PARTIAL · BI5 Health panel rows · readiness delta
6. Report before/after evidence + update memory docs
```

---

## 7. Recommendations on the three open decisions

### a) LLM key policy — **RECOMMEND: set `EMERGENT_LLM_KEY` now (before R2 validation)**
- It clears the second standing readiness blocker (`llm_budget`), letting Auto Factory readiness go green alongside the data fix — meaning R2 and the future pipeline get validated against a *fully* unblocked factory.
- Stage 2 of the future import then runs in full mode (LLM-assisted steps) rather than heuristic-only; heuristic mode remains the documented fallback if budget is a concern.
- Zero code: one `.env` entry + backend restart (I fetch the universal key via the platform; you only need to keep budget topped up — Profile → Universal Key → Add Balance / auto top-up).

### b) Firm approval policy — **RECOMMEND: approve all 3 firms via the UI before Stage 4 ever runs**
- FTMO, FundedNext, PipFarm sit at `status=parsed` (0 approved). Their challenge rule sets are fully parameterised and look correct (verified live in the dry-run).
- Approving them (minutes, `/c/propfirm#admin` → review → approve) puts the catalogue in its intended reviewed state and eliminates the "does the matcher accept parsed firms?" ambiguity *by policy* instead of by code archaeology. No engineering needed.

### c) T1 filter settings — **RECOMMEND: keep the locked defaults; make the age window evidence-driven**
- Keep: `total_trades ≥ 30` · `PF ≥ 1.30` · `WR ≥ 0.40` · `maxDD ≤ 20%` · 30-day `stage_locked_until` · the 5-line auto-selection guard. These are conservative, industry-sane, and anything they exclude still lands in the T2 archive (nothing is lost).
- Adjust ONE knob procedurally: the **365-day `created_at` window**. The 1-vCPU strategies' ages are unknown until the export lands. Proposal: the TRUE dry-run reports the age distribution, and **if > 20% of otherwise-T1-qualifying rows fail only on age, the window is extended to cover the export's actual range** (your sign-off at that point). This keeps the filter honest without guessing today.

---

## 8. Sequence after your review (Path A1, restated)

```
Step 1  BI5 archive restore + ingest          ← THIS PLAN, awaiting your go
Step 2  BI5 R2 (B-4 cert sweep · B-5 ranker weights · B-8 surfacing) + validation
Step 3  (parallel, no-import prep) import readiness package: importer/validation
        script design finalisation + index pre-create note + operator decision log
Gate    Export package arrives → TRUE read-only dry-run → your GATE 3 decision
Later   BI5 R3 (post-import, pre-rehearsal) · targeted Dukascopy backfill as evidence dictates
```

**Status: PLAN ONLY. Awaiting operator review before executing Step 1.**
