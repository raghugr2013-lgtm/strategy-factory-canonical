"""P0B Phase 3 — BI5 Strategy Certification orchestrator (pure).

This module composes the four Phase-1 evaluators with the Phase-2
data-feed cert lookup and emits a strategy certification record into
the Phase-3 store.

BID ↔ BI5 firewall
──────────────────
This module imports ONLY:

    * stdlib + dataclasses + datetime + typing
    * Phase-1 evaluators (`tick_validator`, `spread_analyzer`,
      `slippage_model`, `execution_simulator`)
    * Phase-2 / Phase-3 persistence adapters
    * pymongo (transitively, via the adapters' calls — never
      imported directly here)

It does NOT import any BID-stage module
(discovery / mutation / validation / pass_probability /
challenge_matching / matching_engine / portfolio_* / phase30_*).

The single piece of BID-side information allowed in is
``StrategyCertRequest.stability_score`` (float). The orchestrator
records it; it never derives it.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from engines.execution_simulator import get_profile, simulate_fills
from engines.persistence_adapters.bi5_certification_store import (
    EVALUATOR_VERSION,
    FROZEN_WEIGHTS,
    StrategyCertRecord,
    upsert_certification,
)
from engines.persistence_adapters.bi5_data_certification_store import (
    get_data_certification,
    get_latest_data_certification,
)
from engines.slippage_model import slippage_score
from engines.spread_analyzer import spread_score_from_fills
from engines.tick_validator import PASS_THRESHOLD, WARN_THRESHOLD


logger = logging.getLogger(__name__)


# ── inputs ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WindowRef:
    window_start_utc: datetime
    window_end_utc:   datetime

    def as_dict(self, *, symbol: str) -> Dict[str, Any]:
        return {
            "symbol":           symbol,
            "window_start_utc": _to_utc(self.window_start_utc),
            "window_end_utc":   _to_utc(self.window_end_utc),
        }


@dataclass(frozen=True)
class StrategyCertRequest:
    strategy_id:        str
    pair:               str
    timeframe:          str
    style:              str

    # Either an explicit data-cert window OR ``None`` to use the
    # latest PASS data-cert for `pair`.
    data_cert_window:   Optional[WindowRef]

    # Inputs to Phase-1 evaluators (already gathered by the API seam).
    fills:              Sequence[Dict[str, Any]]
    signals:            Sequence[Dict[str, Any]]
    ticks:              Sequence[Any]
    venue_profile:      str

    # Stability arrives PRE-COMPUTED from validation / pass-probability.
    # The orchestrator does not derive it.
    stability_score:    float

    # Cost assumptions used by spread / slippage scoring. The API seam
    # passes them through from per-symbol calibration tables.
    assumed_cost_bps:       float = 1.0
    assumed_slippage_bps:   float = 1.0
    tolerance_bps:          Optional[float] = None

    adv_per_minute:     Optional[float] = None

    # Optional learning-system context.
    mutation_family:    Optional[str] = None
    parent_strategy_id: Optional[str] = None


# ── outputs ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StrategyCertReport:
    record:            StrategyCertRecord
    persist_result:    Dict[str, Any]
    early_fail_reason: Optional[str]


# ── helpers ──────────────────────────────────────────────────────────

def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _verdict_from_composite(composite: float) -> str:
    if composite >= PASS_THRESHOLD:
        return "PASS"
    if composite >= WARN_THRESHOLD:
        return "WARN"
    return "FAIL"


def compute_composite(
    *,
    integrity: float,
    spread: float,
    slippage: float,
    execution: float,
    stability: float,
    weights: Dict[str, float] = None,
) -> float:
    """Weighted geometric mean of the five sub-scores.

    Matches the BI5 "any zero collapses the score" pattern used by
    `engines.tick_validator.aggregate_window`.
    """
    w = dict(FROZEN_WEIGHTS) if weights is None else dict(weights)
    values = {
        "integrity": _clamp01(integrity),
        "spread":    _clamp01(spread),
        "slippage":  _clamp01(slippage),
        "execution": _clamp01(execution),
        "stability": _clamp01(stability),
    }
    # Any zero collapses to 0 (no log of zero).
    if any(v <= 0.0 for v in values.values()):
        return 0.0
    log_sum = sum(w[k] * math.log(v) for k, v in values.items())
    return _clamp01(math.exp(log_sum))


async def _resolve_data_cert(
    db: Any,
    *,
    pair: str,
    window: Optional[WindowRef],
) -> Optional[Dict[str, Any]]:
    if window is None:
        return await get_latest_data_certification(db, symbol=pair)
    return await get_data_certification(
        db,
        symbol=pair,
        window_start_utc=window.window_start_utc,
        window_end_utc=window.window_end_utc,
    )


def _early_fail_record(
    req: StrategyCertRequest,
    *,
    reason: str,
    now_dt: datetime,
    data_cert: Optional[Dict[str, Any]],
) -> StrategyCertRecord:
    """Build a verdict=FAIL record without running Phase-1 scorers."""
    data_cert_ref: Optional[Dict[str, Any]] = None
    if data_cert is not None:
        data_cert_ref = {
            "symbol":           data_cert.get("symbol"),
            "window_start_utc": data_cert.get("window_start_utc"),
            "window_end_utc":   data_cert.get("window_end_utc"),
            "data_cert_id":     str(data_cert.get("_id"))
                                if data_cert.get("_id") is not None else None,
        }
    elif req.data_cert_window is not None:
        data_cert_ref = req.data_cert_window.as_dict(symbol=req.pair)

    return StrategyCertRecord(
        strategy_id=req.strategy_id,
        pair=req.pair,
        timeframe=req.timeframe,
        style=req.style,
        certification_timestamp=now_dt,
        certification_verdict="FAIL",
        certification_version=EVALUATOR_VERSION,
        integrity_score=0.0,
        spread_score=0.0,
        slippage_score=0.0,
        execution_score=0.0,
        stability_score=_clamp01(req.stability_score),
        composite_score=0.0,
        data_cert_ref=data_cert_ref,
        mutation_family=req.mutation_family,
        parent_strategy_id=req.parent_strategy_id,
        reason=reason,
        venue_profile=req.venue_profile,
    )


# ── main entry point ─────────────────────────────────────────────────

async def certify_strategy(
    db: Any,
    req: StrategyCertRequest,
    *,
    now_dt: Optional[datetime] = None,
) -> StrategyCertReport:
    """Run the full certification pipeline for one strategy.

    Returns the persisted record + a flag indicating whether an early
    short-circuit fired (and the reason if so). Either way, an audit
    row is written so research/learning systems get a complete trail.
    """
    now_dt = _to_utc(now_dt or datetime.now(timezone.utc))

    # ── Step 1: data-cert lookup + short-circuits ──────────────────
    data_cert = await _resolve_data_cert(
        db, pair=req.pair, window=req.data_cert_window,
    )
    if data_cert is None:
        record = _early_fail_record(
            req, reason="DATA_CERT_MISSING", now_dt=now_dt, data_cert=None,
        )
        res = await upsert_certification(db, record)
        return StrategyCertReport(
            record=record, persist_result=res,
            early_fail_reason="DATA_CERT_MISSING",
        )

    if (data_cert.get("verdict") or "").upper() != "PASS":
        record = _early_fail_record(
            req, reason="DATA_CERT_NOT_PASS", now_dt=now_dt, data_cert=data_cert,
        )
        res = await upsert_certification(db, record)
        return StrategyCertReport(
            record=record, persist_result=res,
            early_fail_reason="DATA_CERT_NOT_PASS",
        )

    integrity_score = _clamp01(
        float((data_cert.get("subscores") or {}).get("integrity", 0.0))
    )

    # ── Step 2: missing-input short-circuits ───────────────────────
    if not req.fills:
        record = _early_fail_record(
            req, reason="MISSING_FILLS", now_dt=now_dt, data_cert=data_cert,
        )
        record = _with_integrity(record, integrity_score)
        res = await upsert_certification(db, record)
        return StrategyCertReport(
            record=record, persist_result=res,
            early_fail_reason="MISSING_FILLS",
        )

    if not req.signals:
        record = _early_fail_record(
            req, reason="MISSING_SIGNALS", now_dt=now_dt, data_cert=data_cert,
        )
        record = _with_integrity(record, integrity_score)
        res = await upsert_certification(db, record)
        return StrategyCertReport(
            record=record, persist_result=res,
            early_fail_reason="MISSING_SIGNALS",
        )

    # ── Step 3: Phase-1 scoring (pure) ─────────────────────────────
    spread_res = spread_score_from_fills(
        fills=req.fills,
        symbol=req.pair,
        assumed_cost_bps=req.assumed_cost_bps,
        tolerance_bps=req.tolerance_bps,
    )
    slip_res = slippage_score(
        fills=req.fills,
        assumed_slippage_bps=req.assumed_slippage_bps,
    )
    exec_rep = simulate_fills(
        list(req.signals),
        ticks=list(req.ticks),
        profile=get_profile(req.venue_profile),
        adv_per_minute=float(req.adv_per_minute or 1.0),
    )

    spread_s    = _clamp01(spread_res.spread_score)
    slippage_s  = _clamp01(slip_res.slippage_score)
    execution_s = _clamp01(exec_rep.execution_score)
    stability_s = _clamp01(req.stability_score)

    composite = compute_composite(
        integrity=integrity_score,
        spread=spread_s,
        slippage=slippage_s,
        execution=execution_s,
        stability=stability_s,
    )
    verdict = _verdict_from_composite(composite)
    reason: Optional[str] = (
        "LOW_COMPOSITE" if verdict == "FAIL" else None
    )

    # ── Step 4: persist ────────────────────────────────────────────
    data_cert_ref = {
        "symbol":           data_cert.get("symbol"),
        "window_start_utc": data_cert.get("window_start_utc"),
        "window_end_utc":   data_cert.get("window_end_utc"),
        "data_cert_id":     str(data_cert.get("_id"))
                            if data_cert.get("_id") is not None else None,
    }
    record = StrategyCertRecord(
        strategy_id=req.strategy_id,
        pair=req.pair,
        timeframe=req.timeframe,
        style=req.style,
        certification_timestamp=now_dt,
        certification_verdict=verdict,
        certification_version=EVALUATOR_VERSION,
        integrity_score=integrity_score,
        spread_score=spread_s,
        slippage_score=slippage_s,
        execution_score=execution_s,
        stability_score=stability_s,
        composite_score=composite,
        data_cert_ref=data_cert_ref,
        mutation_family=req.mutation_family,
        parent_strategy_id=req.parent_strategy_id,
        reason=reason,
        venue_profile=req.venue_profile,
    )
    res = await upsert_certification(db, record)
    return StrategyCertReport(
        record=record, persist_result=res, early_fail_reason=None,
    )


def _with_integrity(
    record: StrategyCertRecord, integrity_score: float,
) -> StrategyCertRecord:
    """Return a copy of `record` with `integrity_score` overwritten.

    Used to mirror the data-cert integrity onto an early-FAIL record
    that fired *after* the data-cert lookup succeeded — so the audit
    row still carries the data-side integrity number for research.
    """
    return StrategyCertRecord(
        strategy_id=record.strategy_id,
        pair=record.pair,
        timeframe=record.timeframe,
        style=record.style,
        certification_timestamp=record.certification_timestamp,
        certification_verdict=record.certification_verdict,
        certification_version=record.certification_version,
        integrity_score=integrity_score,
        spread_score=record.spread_score,
        slippage_score=record.slippage_score,
        execution_score=record.execution_score,
        stability_score=record.stability_score,
        composite_score=record.composite_score,
        data_cert_ref=record.data_cert_ref,
        mutation_family=record.mutation_family,
        parent_strategy_id=record.parent_strategy_id,
        reason=record.reason,
        venue_profile=record.venue_profile,
    )
