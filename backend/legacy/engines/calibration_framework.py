"""
Phase 4 P4.16 latent-capability — Confidence calibration framework.

Purpose
-------
Persist (predicted_pass_probability, realized_outcome) pairs so a
calibration table can later transform raw model predictions into
realistic operator confidence values.

DIAGNOSTIC-ONLY initially (per operator decree):
  * `ENABLE_CALIBRATION=false` — `apply_calibration` returns the raw
    prediction unchanged (identity transform).
  * Even when enabled, bins with `n < CALIBRATION_MIN_OUTCOMES` return
    raw (we never fake calibration maturity).

Collections (additive)
----------------------
  * `calibration_outcomes` — one row per (prediction → outcome) pair.
      {strategy_hash, prediction_at, predicted_pp, realized_outcome ∈
       {pass, fail, in_progress}, realized_at, source}
  * `calibration_tables` — one row per recompute; the LATEST is the
     active table.
      {built_at, deciles: [{bin_lo, bin_hi, n, pass_rate, ...}],
       total_outcomes}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from engines.db import get_db
from engines.feature_flags import flag

logger = logging.getLogger(__name__)

OUTCOMES_COLL = "calibration_outcomes"
TABLES_COLL = "calibration_tables"

# Allowed outcome values — anything else is rejected by record_outcome.
_VALID_OUTCOMES = {"pass", "fail", "in_progress"}


# ─────────────────────────────────────────────────────────────────────
# 1. Prediction + outcome persistence.
# ─────────────────────────────────────────────────────────────────────

async def record_prediction(
    *,
    strategy_hash: str,
    predicted_pp: float,
    predicted_pp_ci: Optional[Sequence[float]] = None,
    source: str = "pass_probability",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write a calibration row in the `in_progress` state. Best-effort.
    Returns the row dict (without `_id`)."""
    pp = max(0.0, min(1.0, float(predicted_pp)))
    now = datetime.now(timezone.utc)
    doc = {
        "strategy_hash":       strategy_hash,
        "prediction_at":       now.isoformat(),
        "prediction_at_dt":    now,
        "predicted_pp":        pp,
        "predicted_pp_ci":     (
            [float(predicted_pp_ci[0]), float(predicted_pp_ci[1])]
            if predicted_pp_ci and len(predicted_pp_ci) == 2 else None
        ),
        "realized_outcome":    "in_progress",
        "realized_at":         None,
        "source":              source,
        "metadata":            metadata or {},
    }
    try:
        await get_db()[OUTCOMES_COLL].insert_one({**doc})
        doc.pop("_id", None)
    except Exception as e:                                  # pragma: no cover
        logger.warning("[calibration] record_prediction failed: %s", e)
        doc["_persist_error"] = str(e)[:200]
    return doc


async def record_outcome(
    *,
    strategy_hash: str,
    realized_outcome: str,
    source: str = "manual_admin",
    realized_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Update the LATEST in_progress prediction for this strategy with
    a realized outcome. Returns {matched: bool, updated_count: int}."""
    if realized_outcome not in _VALID_OUTCOMES:
        return {
            "matched": False,
            "error": f"invalid outcome {realized_outcome!r}; allowed: {sorted(_VALID_OUTCOMES)}",
        }
    now_iso = realized_at or datetime.now(timezone.utc).isoformat()
    db = get_db()
    # Find the most recent in_progress prediction for this hash.
    row = await db[OUTCOMES_COLL].find_one(
        {"strategy_hash": strategy_hash, "realized_outcome": "in_progress"},
        sort=[("prediction_at_dt", -1)],
    )
    if not row:
        return {"matched": False, "updated_count": 0,
                "note": "no in_progress prediction for this strategy_hash"}
    res = await db[OUTCOMES_COLL].update_one(
        {"_id": row["_id"]},
        {"$set": {
            "realized_outcome": realized_outcome,
            "realized_at":      now_iso,
            "outcome_source":   source,
        }},
    )
    return {
        "matched":       True,
        "updated_count": int(res.modified_count),
        "row_predicted_at": row.get("prediction_at"),
        "predicted_pp":  row.get("predicted_pp"),
    }


# ─────────────────────────────────────────────────────────────────────
# 2. Calibration table builder.
# ─────────────────────────────────────────────────────────────────────

async def build_calibration_table(*, save: bool = True) -> Dict[str, Any]:
    """Bin predicted_pp into N deciles, compute realized pass-rate per
    bin, persist as a calibration_tables row. Returns the table.

    Identity-safe: bins with < CALIBRATION_MIN_OUTCOMES use raw (i.e.
    the midpoint of the bin) — we never extrapolate confidence from
    sparse evidence.
    """
    n_bins = int(flag("CALIBRATION_DECILE_COUNT"))
    n_bins = max(2, min(n_bins, 50))
    min_outcomes = int(flag("CALIBRATION_MIN_OUTCOMES"))
    db = get_db()

    bins: List[Dict[str, Any]] = []
    total_outcomes = 0
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        # outcomes resolved AND fall inside the bin
        q = {
            "predicted_pp":     {"$gte": lo, "$lt": hi if i < n_bins - 1 else hi + 1e-9},
            "realized_outcome": {"$in": ["pass", "fail"]},
        }
        # We use small aggregation rather than two count queries.
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": "$realized_outcome",
                "n":   {"$sum": 1},
            }},
        ]
        counts = {"pass": 0, "fail": 0}
        async for d in db[OUTCOMES_COLL].aggregate(pipeline):
            counts[d["_id"]] = int(d["n"])
        n = counts["pass"] + counts["fail"]
        midpoint = (lo + hi) / 2.0
        if n >= min_outcomes:
            pass_rate = counts["pass"] / n
        else:
            pass_rate = midpoint  # identity fallback
        bins.append({
            "bin_lo":     round(lo, 4),
            "bin_hi":     round(hi, 4),
            "n":          n,
            "pass":       counts["pass"],
            "fail":       counts["fail"],
            "pass_rate":  round(pass_rate, 4),
            "is_calibrated": n >= min_outcomes,
        })
        total_outcomes += n

    now = datetime.now(timezone.utc)
    table = {
        "built_at":             now.isoformat(),
        "built_at_dt":          now,
        "n_bins":               n_bins,
        "min_outcomes_per_bin": min_outcomes,
        "total_outcomes":       total_outcomes,
        "bins":                 bins,
        "is_active":            bool(flag("ENABLE_CALIBRATION")),
    }

    if save:
        try:
            await db[TABLES_COLL].insert_one({**table})
            table.pop("_id", None)
        except Exception as e:                              # pragma: no cover
            logger.warning("[calibration] build_table persist failed: %s", e)
            table["_persist_error"] = str(e)[:200]
    return table


async def get_active_table() -> Optional[Dict[str, Any]]:
    """Return the most recent calibration_tables row, or None."""
    db = get_db()
    row = await db[TABLES_COLL].find_one(
        {}, {"_id": 0}, sort=[("built_at_dt", -1)],
    )
    return row


# ─────────────────────────────────────────────────────────────────────
# 3. Apply calibration.
# ─────────────────────────────────────────────────────────────────────

def apply_calibration(
    raw_pp: float,
    table: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Map a raw predicted_pp through the calibration table.

    Returns {raw, calibrated, source}. When the feature flag is off
    OR the table is missing OR the matching bin is uncalibrated, the
    `calibrated` value equals `raw` and `source` reports the reason.
    """
    raw = max(0.0, min(1.0, float(raw_pp)))
    if not flag("ENABLE_CALIBRATION"):
        return {"raw": raw, "calibrated": raw, "source": "identity_flag_off"}
    if not table or not table.get("bins"):
        return {"raw": raw, "calibrated": raw, "source": "identity_no_table"}

    # Find the bin.
    for b in table["bins"]:
        lo = float(b["bin_lo"])
        hi = float(b["bin_hi"])
        if lo <= raw < hi or (b is table["bins"][-1] and raw <= hi):
            if b.get("is_calibrated"):
                return {
                    "raw":        raw,
                    "calibrated": float(b["pass_rate"]),
                    "source":     "calibrated",
                    "bin_n":      int(b["n"]),
                }
            return {
                "raw":        raw,
                "calibrated": raw,
                "source":     "identity_sparse_bin",
                "bin_n":      int(b["n"]),
            }
    # Fall-through (shouldn't reach here).
    return {"raw": raw, "calibrated": raw, "source": "identity_no_bin_match"}


# ─────────────────────────────────────────────────────────────────────
# 4. Diagnostics.
# ─────────────────────────────────────────────────────────────────────

async def diagnostics() -> Dict[str, Any]:
    """Single-shot status summary for the latent diagnostic endpoint."""
    db = get_db()
    total_outcomes = await db[OUTCOMES_COLL].estimated_document_count()
    in_progress = await db[OUTCOMES_COLL].count_documents(
        {"realized_outcome": "in_progress"},
    )
    resolved = await db[OUTCOMES_COLL].count_documents(
        {"realized_outcome": {"$in": ["pass", "fail"]}},
    )
    table = await get_active_table()
    return {
        "is_active":            bool(flag("ENABLE_CALIBRATION")),
        "outcomes_total":       int(total_outcomes),
        "outcomes_in_progress": int(in_progress),
        "outcomes_resolved":    int(resolved),
        "active_table": (
            {k: v for k, v in table.items() if k != "built_at_dt"}
            if table else None
        ),
        "flags": {
            "ENABLE_CALIBRATION":       bool(flag("ENABLE_CALIBRATION")),
            "CALIBRATION_MIN_OUTCOMES": int(flag("CALIBRATION_MIN_OUTCOMES")),
            "CALIBRATION_DECILE_COUNT": int(flag("CALIBRATION_DECILE_COUNT")),
        },
    }
