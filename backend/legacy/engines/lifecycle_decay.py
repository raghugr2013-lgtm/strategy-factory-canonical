"""
Phase 4 P4.15 latent-capability — Lifecycle decay / aging framework.

Purpose
-------
Compute an `aging_penalty` for every lifecycle row based on time since
last revalidation. Persist the value into `strategy_lifecycle.evidence`
so the operator + future governance layers have continuous visibility.

DIAGNOSTIC-ONLY initially (per operator decree):
  * `ENABLE_AGING_PENALTY=false` — survivor_registry.deploy_score is
    NOT modified.
  * `ENABLE_AGING_AUTO_DEMOTION=false` — no automatic stage demotion.

When the operator activates these gates (after a 30+ day soak per the
plan), the same persisted values become the active signal — no schema
change required at activation.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.feature_flags import flag

logger = logging.getLogger(__name__)

LIFECYCLE_COLL = "strategy_lifecycle"


# ─────────────────────────────────────────────────────────────────────
# 1. Pure math.
# ─────────────────────────────────────────────────────────────────────

def compute_aging_penalty(
    last_revalidation_at: Optional[str],
    *,
    tau_days: Optional[float] = None,
    now: Optional[datetime] = None,
) -> float:
    """Penalty = 1 - exp(-Δt_days / TAU).

    Returns 0.0 when `last_revalidation_at` is missing or unparseable
    (treat unknown as fresh — operator can flip later).

    Args
    ----
    last_revalidation_at : ISO string (timezone-aware preferred).
    tau_days : decay time constant in DAYS. Defaults to
               feature flag `AGING_TAU_DAYS` (60.0).
    now : injectable for tests.

    Returns
    -------
    Float in [0, 1).
    """
    if not last_revalidation_at:
        return 0.0
    tau = float(tau_days if tau_days is not None else flag("AGING_TAU_DAYS"))
    if tau <= 0:
        return 0.0
    now = now or datetime.now(timezone.utc)

    try:
        # Tolerate Z-suffixed ISO strings.
        s = str(last_revalidation_at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0.0

    dt_days = (now - dt).total_seconds() / 86400.0
    if dt_days <= 0:
        return 0.0
    try:
        return float(1.0 - math.exp(-dt_days / tau))
    except (OverflowError, ValueError):                  # pragma: no cover
        return 1.0


def is_stale(
    aging_penalty: float,
    last_revalidation_at: Optional[str],
    *,
    now: Optional[datetime] = None,
    min_age_days: float = 90.0,
) -> bool:
    """Mirror of EXECUTION_PLAN §P4.15 demotion criterion:
        aging_penalty > AGING_AUTO_DEMOTION_THRESHOLD
        AND last_revalidation_at older than `min_age_days`.

    Returns True only if BOTH conditions hold. Caller decides whether
    to act on this (gated by `ENABLE_AGING_AUTO_DEMOTION`).
    """
    if aging_penalty <= float(flag("AGING_AUTO_DEMOTION_THRESHOLD")):
        return False
    if not last_revalidation_at:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        s = str(last_revalidation_at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return (now - dt).total_seconds() / 86400.0 >= float(min_age_days)


# ─────────────────────────────────────────────────────────────────────
# 2. Persistence — idempotent + additive.
# ─────────────────────────────────────────────────────────────────────

async def seed_evidence_fields() -> Dict[str, Any]:
    """Idempotent backfill — for every lifecycle doc lacking
    `evidence.last_revalidation_at`, seed it from
    `evidence.current_stage_since` (the existing analogue) and set
    `aging_penalty=0.0`, `revalidation_count=1`.

    Safe to run repeatedly — only touches docs missing the field.
    Returns a summary {seeded: int, total: int}.
    """
    db = get_db()
    coll = db[LIFECYCLE_COLL]

    total = await coll.estimated_document_count()
    seeded = 0
    # Process in small batches to avoid loading everything.
    cur = coll.find(
        {"evidence.last_revalidation_at": {"$exists": False}},
        {"_id": 1, "evidence": 1},
    )
    async for doc in cur:
        ev = doc.get("evidence") or {}
        seed_ts = ev.get("current_stage_since") or ev.get("last_observed_at")
        update = {
            "evidence.last_revalidation_at": seed_ts,
            "evidence.aging_penalty":         0.0,
            "evidence.revalidation_count":    int(ev.get("revalidation_count") or 1),
        }
        try:
            await coll.update_one({"_id": doc["_id"]}, {"$set": update})
            seeded += 1
        except Exception as e:                              # pragma: no cover
            logger.warning("[lifecycle_decay] seed update failed: %s", e)

    return {"seeded": seeded, "total_lifecycle_rows": total}


async def recompute_all() -> Dict[str, Any]:
    """Re-evaluate aging_penalty for every lifecycle doc and persist.

    Diagnostic-only — never modifies `current_stage` or `deploy_score`.
    Returns a distribution summary suitable for the diagnostic endpoint.
    """
    db = get_db()
    coll = db[LIFECYCLE_COLL]
    now = datetime.now(timezone.utc)

    distribution_buckets = {
        "fresh_(0-0.1)":      0,
        "moderate_(0.1-0.3)": 0,
        "aged_(0.3-0.6)":     0,
        "stale_(0.6+)":       0,
    }
    stale_demotion_candidates: List[Dict[str, Any]] = []
    updated = 0
    untouched = 0

    cur = coll.find(
        {},
        {"_id": 1, "strategy_hash": 1, "current_stage": 1, "evidence": 1},
    )
    async for doc in cur:
        ev = doc.get("evidence") or {}
        last_rev = ev.get("last_revalidation_at") or ev.get("current_stage_since")
        penalty = compute_aging_penalty(last_rev, now=now)

        if penalty < 0.1:
            distribution_buckets["fresh_(0-0.1)"] += 1
        elif penalty < 0.3:
            distribution_buckets["moderate_(0.1-0.3)"] += 1
        elif penalty < 0.6:
            distribution_buckets["aged_(0.3-0.6)"] += 1
        else:
            distribution_buckets["stale_(0.6+)"] += 1

        if is_stale(penalty, last_rev, now=now):
            stale_demotion_candidates.append({
                "strategy_hash":    doc.get("strategy_hash"),
                "current_stage":    doc.get("current_stage"),
                "aging_penalty":    round(penalty, 4),
                "last_revalidation_at": last_rev,
            })

        # Persist the recomputed penalty (so external dashboards can
        # query without recomputing).
        try:
            await coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "evidence.aging_penalty":      round(penalty, 6),
                    "evidence.aging_evaluated_at": now.isoformat(),
                }},
            )
            updated += 1
        except Exception as e:                              # pragma: no cover
            logger.debug("[lifecycle_decay] update %s failed: %s",
                         doc.get("strategy_hash"), e)
            untouched += 1

    return {
        "updated":                     updated,
        "untouched":                   untouched,
        "evaluated_at":                now.isoformat(),
        "distribution":                distribution_buckets,
        "stale_demotion_candidates":   stale_demotion_candidates,
        "stale_count":                 len(stale_demotion_candidates),
        "flags": {
            "ENABLE_AGING_PENALTY":         bool(flag("ENABLE_AGING_PENALTY")),
            "ENABLE_AGING_AUTO_DEMOTION":   bool(flag("ENABLE_AGING_AUTO_DEMOTION")),
            "AGING_TAU_DAYS":               float(flag("AGING_TAU_DAYS")),
            "AGING_AUTO_DEMOTION_THRESHOLD":float(flag("AGING_AUTO_DEMOTION_THRESHOLD")),
        },
    }


async def get_distribution() -> Dict[str, Any]:
    """Read-only — return the cached aging-penalty distribution without
    triggering a recompute. Suitable for the diagnostic endpoint."""
    db = get_db()
    pipeline = [
        {"$project": {
            "_id": 0,
            "strategy_hash": 1,
            "current_stage": 1,
            "aging_penalty": "$evidence.aging_penalty",
            "last_revalidation_at": "$evidence.last_revalidation_at",
        }},
    ]
    rows: List[Dict[str, Any]] = []
    async for d in db[LIFECYCLE_COLL].aggregate(pipeline):
        rows.append(d)
    return {
        "count": len(rows),
        "rows":  rows[:200],   # cap response size
        "flags_active": {
            "ENABLE_AGING_PENALTY":       bool(flag("ENABLE_AGING_PENALTY")),
            "ENABLE_AGING_AUTO_DEMOTION": bool(flag("ENABLE_AGING_AUTO_DEMOTION")),
        },
    }


def is_active() -> bool:
    """Convenience — is the aging-penalty signal ACTIVE for deploy_score?"""
    return bool(flag("ENABLE_AGING_PENALTY"))
