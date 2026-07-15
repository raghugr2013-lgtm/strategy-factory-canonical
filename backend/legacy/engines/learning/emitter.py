"""v1.2.0-alpha2 — Outcome-event ledger (P1 foundation).

Every stage in the strategy pipeline writes ONE structured row into
`outcome_events` via this emitter. Never raises — failures are logged
and swallowed so pipeline correctness is preserved. Idempotency on
`(learning_run_id, stage, strategy_hash)` is not enforced at the store
level (retries are legitimately additive events), but callers can
supply an explicit `_id` if they want dedup semantics.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLL = "outcome_events"
SCHEMA_VERSION = 1

VALID_STAGES = (
    "generate", "validate", "repair",
    "backtest", "optimize", "mutate",
    "forward_test", "approve", "reject",
)


def new_run_id() -> str:
    return uuid.uuid4().hex


def hash_context(*parts: str) -> str:
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:16]


@dataclass
class OutcomeEvent:
    learning_run_id: str
    stage: str
    status: str  # pass|fail|partial|skipped
    strategy_hash: Optional[str] = None
    parent_hash: Optional[str] = None
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    retrieval_context_hash: Optional[str] = None
    token_usage: Optional[Dict[str, int]] = None
    duration_ms: int = 0
    cost_usd: Optional[float] = None
    operator: Optional[Dict[str, Any]] = None
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> Dict[str, Any]:
        d = asdict(self)
        d["__v"] = SCHEMA_VERSION
        return d


async def emit(
    stage: str,
    *,
    learning_run_id: str,
    status: str,
    strategy_hash: Optional[str] = None,
    reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    retrieval_context_hash: Optional[str] = None,
    token_usage: Optional[Dict[str, int]] = None,
    duration_ms: int = 0,
    cost_usd: Optional[float] = None,
    operator: Optional[Dict[str, Any]] = None,
    parent_hash: Optional[str] = None,
) -> Optional[str]:
    """Write one row to `outcome_events`. Returns the inserted _id
    (stringified) or None on failure. Never raises."""
    if stage not in VALID_STAGES:
        logger.warning("learning.emit: invalid stage %r — skipping", stage)
        return None
    if status not in ("pass", "fail", "partial", "skipped"):
        logger.warning("learning.emit: invalid status %r — coercing to 'partial'", status)
        status = "partial"

    ev = OutcomeEvent(
        learning_run_id=learning_run_id,
        stage=stage,
        status=status,
        strategy_hash=strategy_hash,
        parent_hash=parent_hash,
        reason=(reason or "")[:512],
        metrics=metrics or {},
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        retrieval_context_hash=retrieval_context_hash,
        token_usage=token_usage,
        duration_ms=int(duration_ms),
        cost_usd=cost_usd,
        operator=operator,
    )
    try:
        db = get_db()
        res = await db[COLL].insert_one(ev.to_doc())
        return str(res.inserted_id)
    except Exception:  # noqa: BLE001
        logger.exception("learning.emit: insert failed (stage=%s)", stage)
        return None


async def ensure_indexes() -> None:
    """Best-effort index setup — safe to re-run."""
    try:
        db = get_db()
        await db[COLL].create_index([("learning_run_id", 1), ("ts", 1)], name="run_ts_1")
        await db[COLL].create_index([("strategy_hash", 1), ("stage", 1)], name="hash_stage_1")
        await db[COLL].create_index([("stage", 1), ("ts", -1)], name="stage_ts_1")
        await db[COLL].create_index([("provider", 1), ("ts", -1)], name="provider_ts_1", sparse=True)
    except Exception:  # noqa: BLE001
        logger.exception("learning.ensure_indexes failed (non-fatal)")


# ── Convenience helpers ────────────────────────────────────────────
async def emit_generate(
    run_id: str, strategy_hash: Optional[str], *,
    provider: str, model: str, prompt_version: str,
    retrieval_context_hash: Optional[str] = None,
    token_usage: Optional[Dict[str, int]] = None,
    duration_ms: int = 0, cost_usd: Optional[float] = None,
    status: str = "pass", reason: str = "",
) -> Optional[str]:
    return await emit(
        "generate", learning_run_id=run_id, status=status,
        strategy_hash=strategy_hash, provider=provider, model=model,
        prompt_version=prompt_version,
        retrieval_context_hash=retrieval_context_hash,
        token_usage=token_usage, duration_ms=duration_ms,
        cost_usd=cost_usd, reason=reason,
    )


async def emit_operator_decision(
    run_id: str, strategy_hash: str, *,
    approved: bool, rating: Optional[int] = None, comment: str = "",
) -> Optional[str]:
    return await emit(
        "approve" if approved else "reject",
        learning_run_id=run_id, status="pass" if approved else "fail",
        strategy_hash=strategy_hash,
        operator={"rating": rating, "comment": comment[:512]},
    )


# ── Decorator for endpoint handlers ────────────────────────────────
def emit_outcome(stage: str) -> Callable:
    """Decorator that wraps an async endpoint. The handler MUST return
    a dict with keys `{learning_run_id, strategy_hash, status, ...}`.
    Whatever it returns is passed straight through to FastAPI; the
    emitter fires as a side-effect."""
    def _wrap(fn):
        async def _inner(*args, **kwargs):
            import time as _t
            t0 = _t.time()
            result = await fn(*args, **kwargs)
            try:
                if isinstance(result, dict) and result.get("learning_run_id"):
                    await emit(
                        stage,
                        learning_run_id=str(result["learning_run_id"]),
                        status=str(result.get("status", "pass")),
                        strategy_hash=result.get("strategy_hash"),
                        reason=str(result.get("reason", "")),
                        metrics=result.get("metrics") or {},
                        provider=result.get("provider"),
                        model=result.get("model"),
                        prompt_version=result.get("prompt_version"),
                        retrieval_context_hash=result.get("retrieval_context_hash"),
                        token_usage=result.get("token_usage"),
                        duration_ms=int((_t.time() - t0) * 1000),
                    )
            except Exception:  # noqa: BLE001
                logger.exception("emit_outcome decorator failed for stage=%s", stage)
            return result
        _inner.__name__ = fn.__name__
        _inner.__doc__ = fn.__doc__
        return _inner
    return _wrap
