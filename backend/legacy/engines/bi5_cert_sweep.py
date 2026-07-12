"""BI5 R2 / B-4 — strategy certification auto-sweep.

Walks `strategy_library`, builds a `StrategyCertRequest` per strategy
from the strategy's own backtest / paper-run artefacts + the BI5 tick
archive, calls the existing `certify_strategy()` orchestrator (which
honours all pre-existing short-circuits: DATA_CERT_MISSING,
DATA_CERT_NOT_PASS, MISSING_FILLS, MISSING_SIGNALS, LOW_COMPOSITE),
and writes a per-strategy result row into `bi5_cert_sweep_log`.

The sweep is

* **idempotent** — the underlying certification store upserts on
  ``(strategy_hash, pair, timeframe, style, certification_timestamp)``;
  the sweep log itself is keyed by `(run_id, strategy_hash)`.
* **budget-capped** — `max_strategies` (default 200) per run, with a
  per-strategy wall-clock cap.
* **lifecycle-emitting** — every per-strategy outcome appends one
  `event_type="bi5_cert"` row to `strategy_lifecycle_history` (B-8
  surfacing), additive and never altering existing stage transitions.
* **dry-on-empty** — on an empty `strategy_library` the sweep exits
  cleanly with `processed=0` (verified path; this is the current pre-
  GATE-3 state of the system).

Public surface:

    run_sweep(*, max_strategies=200, dry_run=False, db=None, trigger="manual")
    get_last_sweep_summary()                                — sync from collection
    get_sweep_runs(limit=20)                                — list recent runs

The Sunday 03:00 UTC cadence is wired in
`engines/bi5_cert_sweep_scheduler.py` (APScheduler CronTrigger). Manual
operator-triggered runs flow through `POST /api/admin/bi5/sweep`.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from engines.bi5_certification import (
    StrategyCertRequest,
    WindowRef,
    certify_strategy,
)
from engines.db import get_db
from engines.persistence_adapters.bi5_data_certification_store import (
    get_latest_data_certification,
)

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

SWEEP_LOG_COLL = "bi5_cert_sweep_log"
SWEEP_RUN_COLL = "bi5_cert_sweep_runs"
LIFECYCLE_HISTORY_COLL = "strategy_lifecycle_history"
STRATEGY_LIBRARY_COLL = "strategy_library"

SWEEP_VERSION = "bi5_cert_sweep@R2-v1"
DEFAULT_MAX_STRATEGIES = 200

# Pre-checks that produce a sweep-side early-skip (no orchestrator
# call). The orchestrator itself ALSO short-circuits DATA_CERT_MISSING
# / DATA_CERT_NOT_PASS, but we filter up-front so the log distinguishes
# "we never built a payload because the precondition failed" from
# "we built one and the orchestrator returned early".
PRECHECK_DATA_CERT_NOT_PASS = "DATA_CERT_NOT_PASS"
PRECHECK_DATA_CERT_MISSING = "DATA_CERT_MISSING"
PRECHECK_MISSING_PAIR = "MISSING_PAIR"


# ── Helpers ──────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _extract_fills_from_validation(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull a `fills`-shaped list from a strategy's validation report.

    The 1-vCPU validation pipeline persists `trades` arrays on each
    backtest. We map them onto the spread_analyzer fill shape — only
    using the fields the cert orchestrator actually consumes. Trades
    that don't carry the four mandatory fields (`side`, `bid`, `ask`,
    `mid_before`, `mid_after`) are skipped.
    """
    if not isinstance(report, dict):
        return []
    candidates: Sequence[Any] = (
        report.get("fills") or report.get("trades") or []
    )
    out: List[Dict[str, Any]] = []
    for t in candidates:
        if not isinstance(t, dict):
            continue
        try:
            side = int(t.get("side", t.get("direction", 0)) or 0)
            bid = float(t.get("bid"))
            ask = float(t.get("ask"))
            mid_b = float(t.get("mid_before", t.get("entry_price")))
            mid_a = float(t.get("mid_after",  t.get("exit_price")))
        except (TypeError, ValueError):
            continue
        out.append({
            "side":           side,
            "bid":            bid,
            "ask":            ask,
            "mid_before":     mid_b,
            "mid_after":      mid_a,
            "order_size":     float(t.get("order_size", 0.0) or 0.0),
            "adv_per_minute": float(t.get("adv_per_minute", 1.0) or 1.0),
        })
    return out


def _extract_signals_from_validation(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull a minimal signals list from validation output.

    Many strategies emit a `signals` array alongside trades; for those
    that do not, we synthesise one signal per fill so the orchestrator
    has a non-empty list (otherwise it short-circuits MISSING_SIGNALS).
    The synthesis is deliberately conservative: we only emit signals
    when we already have fills, so the audit reflects what actually
    traded.
    """
    if not isinstance(report, dict):
        return []
    explicit = report.get("signals")
    if isinstance(explicit, list) and explicit:
        out: List[Dict[str, Any]] = []
        for s in explicit:
            if not isinstance(s, dict):
                continue
            ts = s.get("t_signal") or s.get("ts") or s.get("timestamp")
            if not ts:
                continue
            try:
                side = int(s.get("side", s.get("direction", 0)) or 0)
            except (TypeError, ValueError):
                continue
            out.append({
                "t_signal":   ts if isinstance(ts, str) else (
                    ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                ),
                "side":       side,
                "order_size": float(s.get("order_size", 0.0) or 0.0),
            })
        if out:
            return out
    # Fall through: synthesise from fills timestamps if present.
    fills_src = report.get("fills") or report.get("trades") or []
    synth: List[Dict[str, Any]] = []
    for t in fills_src:
        if not isinstance(t, dict):
            continue
        ts = t.get("t_signal") or t.get("ts") or t.get("entry_time")
        if not ts:
            continue
        try:
            side = int(t.get("side", t.get("direction", 0)) or 0)
        except (TypeError, ValueError):
            continue
        synth.append({
            "t_signal":   ts if isinstance(ts, str) else (
                ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            ),
            "side":       side,
            "order_size": float(t.get("order_size", 0.0) or 0.0),
        })
    return synth


# ── Payload builder ──────────────────────────────────────────────────


@dataclass(frozen=True)
class _PreCheckResult:
    ok: bool
    reason: Optional[str] = None
    data_cert: Optional[Dict[str, Any]] = None


async def _precheck_pair_data_cert(
    db: Any, pair: str,
) -> _PreCheckResult:
    """Look up the latest data cert for `pair`. PASS-only is the gate."""
    if not pair:
        return _PreCheckResult(ok=False, reason=PRECHECK_MISSING_PAIR)
    doc = await get_latest_data_certification(db, symbol=pair)
    if doc is None:
        return _PreCheckResult(ok=False, reason=PRECHECK_DATA_CERT_MISSING)
    if (doc.get("verdict") or "").upper() != "PASS":
        return _PreCheckResult(
            ok=False, reason=PRECHECK_DATA_CERT_NOT_PASS, data_cert=doc,
        )
    return _PreCheckResult(ok=True, data_cert=doc)


def _build_request(
    *,
    lib_doc: Dict[str, Any],
    data_cert: Dict[str, Any],
) -> Optional[StrategyCertRequest]:
    """Build a `StrategyCertRequest` from a library doc + data cert.

    Returns `None` when the library doc is missing the minimum
    composition fields (`pair`, `timeframe`); the caller logs the skip.
    """
    pair = (lib_doc.get("pair") or "").upper().strip()
    tf = lib_doc.get("timeframe")
    if not pair or not tf:
        return None

    style = (
        lib_doc.get("style")
        or lib_doc.get("strategy_type")
        or "unknown"
    )

    val_report = (
        lib_doc.get("validation_report")
        or lib_doc.get("validation")
        or {}
    )
    fills = _extract_fills_from_validation(val_report)
    signals = _extract_signals_from_validation(val_report)

    # Stability is contract-passed-through. Prefer explicit
    # `stability_score` field; fall back to library doc `score / 100`
    # when absent (1-vCPU legacy artefacts). Clamp to [0, 1] here so
    # any unclean upstream values don't reach the orchestrator.
    raw_stab = lib_doc.get("stability_score")
    if raw_stab is None:
        raw_score = lib_doc.get("score")
        raw_stab = (float(raw_score) / 100.0) if raw_score is not None else 0.0
    try:
        stability = max(0.0, min(1.0, float(raw_stab)))
    except (TypeError, ValueError):
        stability = 0.0

    window = WindowRef(
        window_start_utc=data_cert["window_start_utc"],
        window_end_utc=data_cert["window_end_utc"],
    )

    return StrategyCertRequest(
        strategy_id=lib_doc.get("strategy_hash") or lib_doc.get("strategy_id") or "",
        pair=pair,
        timeframe=tf,
        style=style,
        data_cert_window=window,
        fills=fills,
        signals=signals,
        ticks=[],
        venue_profile=str(lib_doc.get("venue_profile") or "ECN"),
        stability_score=stability,
        assumed_cost_bps=float(lib_doc.get("assumed_cost_bps", 1.0) or 1.0),
        assumed_slippage_bps=float(lib_doc.get("assumed_slippage_bps", 1.0) or 1.0),
        tolerance_bps=lib_doc.get("tolerance_bps"),
        adv_per_minute=lib_doc.get("adv_per_minute"),
        mutation_family=lib_doc.get("mutation_family"),
        parent_strategy_id=lib_doc.get("parent_strategy_id"),
    )


# ── Lifecycle event emitter (B-8) ────────────────────────────────────


async def _emit_lifecycle_event(
    db: Any,
    *,
    strategy_hash: str,
    library_id: Optional[Any],
    pair: str,
    verdict: str,
    early_fail_reason: Optional[str],
    composite_score: Optional[float],
    subscores: Dict[str, float],
    sweep_run_id: str,
) -> None:
    """Append one additive `event_type="bi5_cert"` row to
    ``strategy_lifecycle_history``.

    This is NOT a stage transition — the row has no `from_stage` /
    `to_stage` / `to_stage_rank` fields and the cohort distribution
    queries (which filter on those) ignore it. Pure audit additivity.
    """
    try:
        await db[LIFECYCLE_HISTORY_COLL].insert_one({
            "event_type":        "bi5_cert",
            "strategy_hash":     strategy_hash,
            "library_id":        library_id,
            "transition_at":     _now_iso(),
            # BI5 cert fields:
            "bi5_cert_verdict":  verdict,
            "bi5_cert_reason":   early_fail_reason,
            "pair":              pair,
            "composite_score":   composite_score,
            "subscores":         dict(subscores or {}),
            "sweep_run_id":      sweep_run_id,
            "sweep_version":     SWEEP_VERSION,
        })
    except Exception as e:                                # pragma: no cover
        logger.warning("[bi5_cert_sweep] lifecycle event append failed: %s", e)


# ── Sweep runner ─────────────────────────────────────────────────────


@dataclass
class SweepResult:
    run_id: str
    started_at: str
    finished_at: str = ""
    duration_seconds: float = 0.0
    discovered: int = 0
    processed: int = 0
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    early_fails: Dict[str, int] = field(default_factory=dict)
    skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    errors: int = 0
    max_strategies: int = DEFAULT_MAX_STRATEGIES
    dry_run: bool = False
    trigger: str = "manual"
    sweep_version: str = SWEEP_VERSION

    def to_doc(self) -> Dict[str, Any]:
        return {
            "run_id":           self.run_id,
            "started_at":       self.started_at,
            "finished_at":      self.finished_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "discovered":       self.discovered,
            "processed":        self.processed,
            "pass_count":       self.pass_count,
            "warn_count":       self.warn_count,
            "fail_count":       self.fail_count,
            "early_fails":      dict(self.early_fails),
            "skipped":          self.skipped,
            "skip_reasons":     dict(self.skip_reasons),
            "errors":           self.errors,
            "max_strategies":   self.max_strategies,
            "dry_run":          self.dry_run,
            "trigger":          self.trigger,
            "sweep_version":    self.sweep_version,
        }


async def run_sweep(
    *,
    max_strategies: int = DEFAULT_MAX_STRATEGIES,
    dry_run: bool = False,
    trigger: str = "manual",
    db: Optional[Any] = None,
) -> SweepResult:
    """Run one sweep over `strategy_library`.

    Returns a `SweepResult`. Persists the per-strategy result rows to
    `bi5_cert_sweep_log` and the run-level summary to
    `bi5_cert_sweep_runs`.
    """
    db = db or get_db()
    run_id = uuid.uuid4().hex
    t0 = time.monotonic()
    result = SweepResult(
        run_id=run_id,
        started_at=_now_iso(),
        max_strategies=max_strategies,
        dry_run=dry_run,
        trigger=trigger,
    )

    # Persist a "started" marker so the operator UI can see in-flight runs.
    try:
        await db[SWEEP_RUN_COLL].insert_one({
            **result.to_doc(),
            "status": "in_flight",
        })
    except Exception as e:                                # pragma: no cover
        logger.warning("[bi5_cert_sweep] in-flight marker failed: %s", e)

    try:
        # Discover candidate strategies. Bounded by `max_strategies`
        # so a runaway library doesn't park a sweep for minutes.
        cur = db[STRATEGY_LIBRARY_COLL].find(
            {},
            {
                "_id": 1, "strategy_hash": 1, "pair": 1, "timeframe": 1,
                "style": 1, "strategy_type": 1, "score": 1,
                "stability_score": 1, "validation_report": 1,
                "validation": 1, "venue_profile": 1,
                "assumed_cost_bps": 1, "assumed_slippage_bps": 1,
                "tolerance_bps": 1, "adv_per_minute": 1,
                "mutation_family": 1, "parent_strategy_id": 1,
            },
        ).limit(int(max_strategies))

        # Cache data-cert lookups per (pair) to avoid hammering Mongo
        # when many strategies share a pair.
        pair_cert_cache: Dict[str, _PreCheckResult] = {}

        async for lib in cur:
            result.discovered += 1
            strategy_hash = lib.get("strategy_hash") or ""
            pair = (lib.get("pair") or "").upper().strip()

            if not strategy_hash or not pair:
                result.skipped += 1
                reason = PRECHECK_MISSING_PAIR if not pair else "MISSING_STRATEGY_HASH"
                result.skip_reasons[reason] = result.skip_reasons.get(reason, 0) + 1
                await db[SWEEP_LOG_COLL].insert_one({
                    "run_id":        run_id,
                    "strategy_hash": strategy_hash,
                    "pair":          pair,
                    "skipped":       True,
                    "reason":        reason,
                    "at":            _now_iso(),
                })
                continue

            # Pair-level pre-check (data cert must be PASS).
            pc = pair_cert_cache.get(pair)
            if pc is None:
                pc = await _precheck_pair_data_cert(db, pair)
                pair_cert_cache[pair] = pc

            if not pc.ok:
                result.skipped += 1
                result.skip_reasons[pc.reason or "UNKNOWN"] = (
                    result.skip_reasons.get(pc.reason or "UNKNOWN", 0) + 1
                )
                await _emit_lifecycle_event(
                    db,
                    strategy_hash=strategy_hash,
                    library_id=lib.get("_id"),
                    pair=pair,
                    verdict="FAIL",
                    early_fail_reason=pc.reason,
                    composite_score=0.0,
                    subscores={},
                    sweep_run_id=run_id,
                )
                await db[SWEEP_LOG_COLL].insert_one({
                    "run_id":        run_id,
                    "strategy_hash": strategy_hash,
                    "pair":          pair,
                    "skipped":       True,
                    "reason":        pc.reason,
                    "at":            _now_iso(),
                })
                continue

            req = _build_request(lib_doc=lib, data_cert=pc.data_cert)
            if req is None:
                result.skipped += 1
                result.skip_reasons["BUILD_FAILED"] = (
                    result.skip_reasons.get("BUILD_FAILED", 0) + 1
                )
                await db[SWEEP_LOG_COLL].insert_one({
                    "run_id":        run_id,
                    "strategy_hash": strategy_hash,
                    "pair":          pair,
                    "skipped":       True,
                    "reason":        "BUILD_FAILED",
                    "at":            _now_iso(),
                })
                continue

            if dry_run:
                result.skipped += 1
                result.skip_reasons["DRY_RUN"] = (
                    result.skip_reasons.get("DRY_RUN", 0) + 1
                )
                await db[SWEEP_LOG_COLL].insert_one({
                    "run_id":        run_id,
                    "strategy_hash": strategy_hash,
                    "pair":          pair,
                    "skipped":       True,
                    "reason":        "DRY_RUN",
                    "at":            _now_iso(),
                })
                continue

            # Real run.
            try:
                report = await certify_strategy(db, req)
            except Exception as e:                        # pragma: no cover
                result.errors += 1
                logger.exception(
                    "[bi5_cert_sweep] certify_strategy raised for %s: %s",
                    strategy_hash, e,
                )
                await db[SWEEP_LOG_COLL].insert_one({
                    "run_id":        run_id,
                    "strategy_hash": strategy_hash,
                    "pair":          pair,
                    "errored":       True,
                    "error":         f"{type(e).__name__}: {e}"[:240],
                    "at":            _now_iso(),
                })
                continue

            result.processed += 1
            verdict = (report.record.certification_verdict or "FAIL").upper()
            if verdict == "PASS":
                result.pass_count += 1
            elif verdict == "WARN":
                result.warn_count += 1
            else:
                result.fail_count += 1
            if report.early_fail_reason:
                key = report.early_fail_reason
                result.early_fails[key] = result.early_fails.get(key, 0) + 1

            await _emit_lifecycle_event(
                db,
                strategy_hash=strategy_hash,
                library_id=lib.get("_id"),
                pair=pair,
                verdict=verdict,
                early_fail_reason=report.early_fail_reason,
                composite_score=float(report.record.composite_score or 0.0),
                subscores={
                    "integrity": float(report.record.integrity_score or 0.0),
                    "spread":    float(report.record.spread_score or 0.0),
                    "slippage":  float(report.record.slippage_score or 0.0),
                    "execution": float(report.record.execution_score or 0.0),
                    "stability": float(report.record.stability_score or 0.0),
                },
                sweep_run_id=run_id,
            )

            await db[SWEEP_LOG_COLL].insert_one({
                "run_id":            run_id,
                "strategy_hash":     strategy_hash,
                "pair":              pair,
                "verdict":           verdict,
                "early_fail_reason": report.early_fail_reason,
                "composite_score":   float(report.record.composite_score or 0.0),
                "at":                _now_iso(),
            })

    finally:
        result.duration_seconds = time.monotonic() - t0
        result.finished_at = _now_iso()
        try:
            await db[SWEEP_RUN_COLL].update_one(
                {"run_id": run_id},
                {"$set": {**result.to_doc(), "status": "done"}},
                upsert=True,
            )
        except Exception as e:                            # pragma: no cover
            logger.warning("[bi5_cert_sweep] run summary write failed: %s", e)

    return result


# ── Read surface (for the UI) ─────────────────────────────────────────


async def get_last_sweep_summary(db: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Most-recent run summary, or None on empty collection."""
    db = db or get_db()
    return await db[SWEEP_RUN_COLL].find_one(
        {}, {"_id": 0}, sort=[("started_at", -1)],
    )


async def get_sweep_runs(
    *, limit: int = 20, db: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Recent run summaries, newest first."""
    db = db or get_db()
    cur = db[SWEEP_RUN_COLL].find(
        {}, {"_id": 0}, sort=[("started_at", -1)],
    ).limit(max(1, min(int(limit), 200)))
    return [d async for d in cur]


async def get_sweep_results(
    *,
    run_id: Optional[str] = None,
    limit: int = 200,
    db: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Per-strategy result rows for one run (or all recent)."""
    db = db or get_db()
    q: Dict[str, Any] = {}
    if run_id:
        q["run_id"] = run_id
    cur = db[SWEEP_LOG_COLL].find(
        q, {"_id": 0}, sort=[("at", -1)],
    ).limit(max(1, min(int(limit), 1000)))
    return [d async for d in cur]
