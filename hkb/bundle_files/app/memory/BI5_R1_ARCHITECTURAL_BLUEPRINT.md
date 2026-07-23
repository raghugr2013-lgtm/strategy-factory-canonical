# BI5 RECOVERY R1 — ARCHITECTURAL BLUEPRINT
**Title:** BI5 Recovery R1 — Scheduler-Driven BI5 Ingest, UI Source Propagation, and Historical Backfill
**Scope:** B-1 (scheduler dispatches `run_bi5_ingest`), B-2 (UI BI5 source propagation), B-9 (historical backfill).
**Plus approved baseline:** 30-day default lookback · all eligible symbols · extended `bi5_ingest_log` · per-symbol BI5 health tracking · BI5 Health monitoring surface.
**Discipline:** Architectural spec only. No code changes in this turn. Additive only — sealed surfaces (G2 scheduler, IR transpiler, lifecycle engine, governance_universe) are NOT modified.
**Companion docs:** DSR_ARCHITECTURAL_BLUEPRINT.md, BI5_EVOLUTION_ROADMAP.md, MIGRATION_COMPATIBILITY_AUDIT.md

---

## 0. CURRENT-STATE AUDIT (confirmed in pod)

| Component | Status | Location |
|---|---|---|
| `_bi5_track_job` (scheduler job, 60-min cadence) | EXISTS | `data_engine/auto_data_maintainer.py:270` |
| `incremental_update_bi5` | EXISTS | `data_engine/incremental_updater.py` |
| `bi5_ingest_log` collection | EXISTS (used by `incremental_updater`) | Mongo |
| Manual ingest endpoint `/api/data/bi5/ingest` | EXISTS | `api/data.py:419` |
| Per-symbol BI5 status (status row only) | EXISTS (via `_write_status(symbol, "bi5", ...)`) | `auto_data_maintainer.py:69` |
| Standalone `run_bi5_ingest` entry point (decoupled from auto-maintainer) | **MISSING** | — |
| BI5 source propagation in UI (per-symbol selection) | **MISSING** | — |
| Historical backfill orchestrator (>1 month lookback) | **MISSING** | — |
| Per-symbol BI5 health surface (UI) | **MISSING** | — |
| Extended `bi5_ingest_log` schema (per-symbol health metrics) | **MISSING** (current log records per-file ingests only) | — |
| 30-day default lookback configurable | **MISSING** | — |

> **Audit verdict:** the BI5 plumbing exists but is *wedged inside* the auto-maintainer's 60-min loop. R1 promotes it to a first-class subsystem with explicit dispatch, observability, and history.

---

## 1. DESIGN GOALS

1. **First-class BI5 ingest dispatch** — a discrete `run_bi5_ingest` API + scheduler job that can be invoked per symbol, per source, with explicit lookback.
2. **Source propagation** — operator chooses BI5 source (Dukascopy, manual CSV, future providers) per symbol; UI propagates that choice to scheduler + ingest runtime.
3. **Historical backfill** — operator can request a multi-month backfill for any registered symbol; orchestrated as a streaming job to avoid memory blowups.
4. **Per-symbol BI5 health** — Mongo-tracked health metrics (last successful ingest, coverage window, gap density, ingest errors) feeding a UI surface.
5. **Anti-drift** — sealed schedulers (G2) remain authoritative cadence owners. R1 emits *standalone jobs*, not a new scheduler.
6. **Bounded concurrency** — BI5 ingest is I/O-heavy; R1 introduces a semaphore to prevent the previously-seen `LiteLLM.RateLimit`-style cascades from being repeated on the provider side.

---

## 2. PHASE B-1 — Scheduler dispatches `run_bi5_ingest`

### 2.1 Scope
Decouple BI5 ingest from the auto-data-maintainer's 60-min loop. Introduce a discrete dispatchable unit: `run_bi5_ingest(symbol, source, lookback_days)`. The auto-maintainer continues to call it as one of many consumers.

### 2.2 New module — `data_engine/bi5_dispatcher.py` (NEW file)

```python
async def run_bi5_ingest(
    symbol: str,
    source: str = "dukascopy",
    lookback_days: int = 30,            # default 30 (per approval)
    triggered_by: str = "scheduler",
    job_id: Optional[str] = None,
) -> dict:
    """
    Dispatch a single-symbol BI5 ingest cycle.

    Returns a result dict with:
      - status: ok | partial | failed | skipped
      - files_scanned, files_ingested, bars_added
      - coverage_after: {first_ts, last_ts, count}
      - duration_sec
      - errors: [list]
      - bi5_ingest_log_run_id (foreign key)
    """
```

### 2.3 Concurrency & rate-limit safeguards (additive, NOT modifying sealed scheduler)
- Module-level `asyncio.Semaphore(N=4)` for concurrent BI5 ingests (configurable via `BI5_CONCURRENCY=4` in .env)
- Per-source token-bucket throttle (e.g., Dukascopy: max 1 request / 1.5 s); applied at the provider client level
- Exponential backoff with jitter on transient errors (3 retries, base=2s, jitter=±25%)

### 2.4 Auto-maintainer refactor (additive)
`_bi5_track_job` now becomes a thin wrapper:
```python
async def _bi5_track_job():
    if DSR_ENABLED:
        symbols = await symbol_registry.active_symbols("bi5_ingest")
    else:
        symbols = list(SYMBOL_CONFIG)
    for s in symbols:
        await run_bi5_ingest(s, source="dukascopy", lookback_days=BI5_TRACK_LOOKBACK_DAYS)
```

### 2.5 Acceptance criteria (B-1)
- `run_bi5_ingest("EURUSD")` returns within bounded time, records to `bi5_ingest_log`.
- Calling it twice within the same window is idempotent (existing dedup in `incremental_updater.py:426`).
- The 60-min scheduler loop now goes through this dispatch — same end-to-end behaviour, but observable per-job.
- Errors do NOT poison the loop (per-symbol `try/except` already exists; B-1 enhances with the new alert hook in §5).

---

## 3. PHASE B-2 — UI BI5 Source Propagation

### 3.1 Scope
Operator selects which BI5 source to use for each symbol; UI persists choice to `symbol_registry.provider.primary` (BI5 sub-field); scheduler honours the choice.

### 3.2 Data model extension (additive to `symbol_registry`)

```jsonc
{
  ...                                  // existing symbol_registry doc (DSR)
  "bi5": {
    "source": "dukascopy",             // dukascopy | manual_csv | api_x | disabled
    "lookback_days": 30,               // operator-tunable per symbol
    "instrument_code": "INSTRUMENT_FX_MAJORS_EUR_USD",
    "last_ingest_ts": ISODate,
    "next_scheduled_ts": ISODate,
    "enabled": true
  }
}
```

If DSR is not yet enabled, `bi5` config persists in a parallel collection `bi5_source_config` keyed by symbol — same shape, same migration target post-DSR-2.

### 3.3 API additions (additive)

| Endpoint | Method | Behaviour |
|---|---|---|
| `/api/bi5/source/{symbol}` | GET | Returns the symbol's BI5 source config |
| `/api/bi5/source/{symbol}` | PATCH | Update source / lookback / enabled. Audit-logged. |
| `/api/bi5/source/{symbol}/test` | POST | Dry-run: fetch the first chunk from the chosen source, validate parser, return preview. Does NOT write to `market_data`. |

### 3.4 UI additions
- New `BI5SourceConfig` modal accessible from `SymbolRegistryPanel` (DSR) row actions.
- Per-symbol "Test source" button calling `/test` endpoint, displays preview.
- Per-symbol "Ingest now" button calls `run_bi5_ingest` with operator-supplied lookback.
- `data-testid` on every control.

### 3.5 Scheduler consumption
`run_bi5_ingest(symbol)` now reads `bi5.source` / `bi5.lookback_days` from registry instead of hard-coding `source="dukascopy"`. This propagates operator intent into the scheduler without code changes.

### 3.6 Acceptance criteria (B-2)
- Operator can switch a symbol's BI5 source from Dukascopy to manual CSV (or disable) through the UI.
- The next scheduler tick respects the new source/lookback.
- The `bi5_source/test` endpoint provides a 30-second feedback loop for source-config validation.
- Audit log captures every change with actor + timestamp.

---

## 4. PHASE B-9 — Historical Backfill

### 4.1 Scope
Operator can request a multi-month backfill for any registered symbol. The backfill is orchestrated as a *streaming, resumable job* rather than a single mega-ingest. It runs out-of-band from the 60-min scheduler.

### 4.2 New job collection — `bi5_backfill_jobs`

```jsonc
{
  "_id": ObjectId,
  "job_id": "bi5_bf_<uuid>",
  "symbol": "XAUUSD",
  "source": "dukascopy",
  "requested_by": "admin@local.test",
  "requested_at": ISODate,
  "lookback_months": 12,
  "status": "queued",                          // queued | running | paused | completed | failed
  "windows": [                                  // chunked sub-intervals
    { "from_ts": ISODate, "to_ts": ISODate, "status": "pending", "files_ingested": 0, "errors": [] },
    ...
  ],
  "progress": { "windows_done": 0, "windows_total": 12, "bars_added": 0 },
  "started_at": null,
  "finished_at": null,
  "last_heartbeat": ISODate,                    // for stale-job detection
  "checkpoint": null                            // resumable state blob
}
```

### 4.3 Orchestration
- Chunk size: 1 month per window (configurable via `BI5_BACKFILL_WINDOW_MONTHS=1`).
- Concurrency: at most 2 backfill jobs running globally + the 60-min track job (semaphore enforced).
- Resumability: each window's status is persisted; on container restart, the orchestrator scans `bi5_backfill_jobs` for `status in (running, paused)` with stale `last_heartbeat` and resumes from the last completed window.
- Heartbeat: every 30 s while running.
- Throttling: same per-source token bucket as B-1; provider rate limits never violated.

### 4.4 API additions

| Endpoint | Method | Behaviour |
|---|---|---|
| `/api/bi5/backfill/start` | POST | Body: `{symbol, lookback_months, source}`. Creates a queued job, returns `job_id`. |
| `/api/bi5/backfill/{job_id}` | GET | Returns job status + progress + per-window detail |
| `/api/bi5/backfill/{job_id}/pause` | POST | Pause (idempotent) |
| `/api/bi5/backfill/{job_id}/resume` | POST | Resume |
| `/api/bi5/backfill/{job_id}/cancel` | POST | Cancel (terminal) |
| `/api/bi5/backfill` | GET | List jobs with filters |

### 4.5 UI additions
- "Historical backfill" tab in BI5 Health panel (B-Health below).
- Per-symbol "Start backfill" button → opens lookback selector (default 12 months).
- Job list with live progress bars (pull-poll every 5 s).
- Cancellation + pause controls.
- `data-testid` on all controls.

### 4.6 Acceptance criteria (B-9)
- Operator can start a 12-month backfill on a symbol.
- Job persists across container restarts (resumability verified via supervisor restart).
- Pause/resume/cancel work as expected.
- Token-bucket throttle prevents provider rate-limit errors.
- All backfilled rows land in `market_data` with the same upsert semantics as the live scheduler.

---

## 5. EXTENDED `bi5_ingest_log` & PER-SYMBOL BI5 HEALTH TRACKING

### 5.1 Extended schema (additive)
Current `bi5_ingest_log` records per-file ingest events. R1 adds a *per-run* entry:

```jsonc
// Existing per-file entries remain unchanged.
// NEW per-run summary documents:
{
  "_id": ObjectId,
  "kind": "run_summary",                       // distinguishes from per-file rows
  "run_id": "bi5_run_<uuid>",
  "symbol": "EURUSD",
  "source": "dukascopy",
  "triggered_by": "scheduler|operator|backfill",
  "started_at": ISODate,
  "finished_at": ISODate,
  "duration_sec": 8.4,
  "lookback_days_requested": 30,
  "lookback_days_effective": 27,
  "files_scanned": 30,
  "files_ingested": 24,
  "files_skipped_idempotent": 6,
  "bars_added": 51920,
  "errors": [],
  "warnings": [],
  "coverage_after": {"first_ts": ISODate, "last_ts": ISODate, "count": 7384216}
}
```

Index: `{ kind: 1, symbol: 1, started_at: -1 }`.

### 5.2 Per-symbol BI5 health doc
A separate collection `bi5_health` (or extend existing status doc):

```jsonc
{
  "_id": ObjectId,
  "symbol": "EURUSD",
  "source": "dukascopy",
  "status": "healthy",                         // healthy | degraded | failing | dormant
  "last_successful_ingest": ISODate,
  "last_attempt_ts": ISODate,
  "last_error": null,
  "consecutive_failures": 0,
  "coverage_window": { "first_ts": ISODate, "last_ts": ISODate, "days": 365 },
  "gap_density_pct": 0.4,                      // % of expected ticks missing within last 30 days
  "ingest_rate_24h": 2160,                     // bars/min average over 24h
  "alerts": [],                                // active alerts (cleared on next healthy run)
  "updated_at": ISODate
}
```

Status thresholds:
- `healthy` — last ingest within 2× scheduler interval, gap_density_pct < 1.0, consecutive_failures == 0
- `degraded` — gap_density_pct ≥ 1.0 OR consecutive_failures in [1,2]
- `failing` — consecutive_failures ≥ 3 OR no successful ingest in 24 h
- `dormant` — symbol's `bi5.enabled = false` or status = `paused`/`retired`

### 5.3 Alert integration
- When status transitions to `failing` → emit alert via `alert_engine` (existing webhook surface).
- Closes the auto-maintenance failure-observability gap noted in handoff §"Earlier issues found".

---

## 6. BI5 HEALTH MONITORING SURFACE (UI)

### 6.1 New panel — `BI5HealthPanel.jsx`
A dashboard tile sitting alongside `UniverseGovernancePanel` and the upcoming `SymbolRegistryPanel`. Shows:

| Column | Source |
|---|---|
| Symbol | `bi5_health.symbol` |
| Source | `bi5_health.source` |
| Status | `bi5_health.status` (green/amber/red badge) |
| Coverage | `coverage_window.first_ts` → `last_ts` |
| Gap density | `gap_density_pct` |
| Last ingest | `last_successful_ingest` (relative time) |
| Consecutive failures | `consecutive_failures` |
| Active backfill | from `bi5_backfill_jobs` join |
| Actions | "Ingest now" · "Start backfill" · "Configure source" |

### 6.2 Drill-down drawer
- Recent ingest runs (last 20 from `bi5_ingest_log.kind=run_summary`)
- Per-window backfill detail (when active)
- Historical gap analyzer output

### 6.3 Refresh cadence
- 30-second auto-poll
- Server-Sent Events optional (deferred unless cost-justified)

### 6.4 Acceptance criteria (BI5 Health)
- Operator can see at a glance which symbols are healthy / degraded / failing.
- Clicking a row reveals recent ingest history.
- Action buttons trigger the corresponding API.
- `data-testid` on all controls (e.g., `bi5-health-row-${symbol}`, `bi5-health-ingest-btn-${symbol}`).

---

## 7. ORDER OF OPERATIONS (post-blueprint approval)

1. **B-1 backend**: Create `bi5_dispatcher.py`, add semaphore + token bucket, refactor `_bi5_track_job` to call dispatcher.
2. **B-1 observability**: Add per-run summary to `bi5_ingest_log` (additive schema, no migration).
3. **B-1 acceptance check** — manually call `run_bi5_ingest("EURUSD")`, observe per-run entry in `bi5_ingest_log`, confirm scheduler still works.
4. **B-2 backend**: Add BI5 sub-config to symbol_registry (or `bi5_source_config` if DSR-1 not yet shipped); endpoints; test endpoint.
5. **B-2 frontend**: Per-symbol BI5 source config UI; "Ingest now" button.
6. **B-2 acceptance check** — switch a symbol's source via UI; observe scheduler honouring the change.
7. **B-9 backend**: Backfill job collection, orchestrator, resumability, throttle.
8. **B-9 frontend**: Backfill list + start dialog + live progress.
9. **B-9 acceptance check** — start a 3-month backfill, restart container mid-run, observe resumption.
10. **Health tracking**: Add `bi5_health` collection + updater hook in dispatcher; transitions and alerts.
11. **Health UI**: `BI5HealthPanel.jsx`; drill-down drawer; action buttons.
12. **Final acceptance check** — verify Status badge transitions across `healthy → degraded → failing → healthy`.

Each numbered item is independently shippable and additive.

---

## 8. INTERACTION WITH DSR

| DSR phase | Effect on BI5 R1 |
|---|---|
| DSR-1 (registry exists) | BI5 R1 can store `bi5.*` directly on the symbol_registry doc |
| DSR-2 (scheduler reads registry) | BI5 dispatcher iterates `symbol_registry.active_symbols("bi5_ingest")` |
| DSR-3 (shadow audit) | BI5 backfill becomes a *part* of the shadow audit's BI5 coverage check |

If DSR is delayed, BI5 R1 still works via the parallel `bi5_source_config` collection. The two roadmaps are *independent in implementation but converge in data model*.

---

## 9. ROLLBACK / SAFETY

- All R1 changes are additive: existing `bi5_ingest_log` per-file rows unaffected.
- Dispatcher is invoked by the same `_bi5_track_job`; if dispatcher disabled, scheduler falls back to direct call paths.
- Backfill jobs are isolated: cancellation does not affect live scheduler runs.
- Health doc is read-only for downstream subsystems; failure to compute health does not stop ingest.
- Semaphore default (N=4) can be tightened to 1 to fully serialize during stress.

---

## 10. ANTI-DRIFT INVARIANTS

- The 60-min cadence in the G2 scheduler is **NOT modified** by R1. The scheduler still triggers `_bi5_track_job` at the same interval; B-1 only refactors what that job *does*.
- `governance_universe` is **NOT modified** by R1. BI5 ingest is governed by `subsystem_flags.bi5_ingest` (DSR) or `bi5.enabled` (parallel config) — both additive flags.
- The `validation_engine`, `strategy_lifecycle`, `mutation_engine` are NOT touched.
- All BI5 data continues to land in the existing `market_data` collection with `source="bi5"`.

---

## 11. AUDIT BOUNDARY

This blueprint is a design document. No code, no schemas, no APIs, no UI have been modified or created by this audit pass. Implementation begins only after operator approval.
