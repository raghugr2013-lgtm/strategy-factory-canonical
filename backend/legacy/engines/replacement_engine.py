"""Phase 30 — Replacement Engine (advisory only, automation OFF in v1).

Operator-decided constants:
    SURVIVOR_AUTO_REPLACE_ENABLED       = False    # OFF in 30.0
    REPLACEMENT_MIN_DEPLOY_SCORE_DELTA  = 5.0      # challenger must beat by ≥5 pts
    REPLACEMENT_COOLDOWN_DAYS           = 7        # min residency before replaceable

Discipline:
    • READ-ONLY in 30.0. Generates an advisory list of replacement candidates.
    • Manual execution endpoint exists (admin-only) for operator-approved replacements.
    • Demotion when applied: incumbent.current_stage → "prop_safe" (one step down),
      audit row written to `strategy_lifecycle_history`.
    • Auto-replacement requires explicit operator flip of feature flag (30.1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.survivor_registry import (
    SURVIVOR_ELIGIBLE_STAGES,
    SURVIVOR_TOP_N,
    _deploy_score_of,
)

SURVIVOR_AUTO_REPLACE_ENABLED = False
REPLACEMENT_MIN_DEPLOY_SCORE_DELTA = 5.0
REPLACEMENT_COOLDOWN_DAYS = 7
PHASE_VERSION = "30.0"

LIFECYCLE_COLL = "strategy_lifecycle"
LIFECYCLE_HISTORY_COLL = "strategy_lifecycle_history"
AUDIT_COLL = "audit_log"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _days_since(iso_ts: Optional[str]) -> Optional[float]:
    if not iso_ts:
        return None
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (_now() - ts).total_seconds() / 86400.0
    except Exception:
        return None


async def fetch_replacement_candidates() -> Dict[str, Any]:
    """Advisory list of replacement candidates.

    Algorithm:
      1. Read all lifecycle docs in SURVIVOR_ELIGIBLE_STAGES (the universe).
      2. Identify the bottom decile by deploy_score (incumbents).
      3. Read all candidate-eligible docs at `prop_safe` stage (challengers
         — strategies that are one rung below the universe).
      4. For each (incumbent, challenger) pair where
         challenger.deploy_score - incumbent.deploy_score >= MIN_DELTA
         AND incumbent has been in-universe >= COOLDOWN_DAYS:
            → recommend a replacement.

    The output is purely advisory. No writes anywhere.
    """
    db = get_db()
    eligible_docs: List[Dict[str, Any]] = []
    async for d in db[LIFECYCLE_COLL].find(
        {"current_stage": {"$in": list(SURVIVOR_ELIGIBLE_STAGES)}},
        {"_id": 0},
    ):
        eligible_docs.append(d)

    challengers: List[Dict[str, Any]] = []
    async for d in db[LIFECYCLE_COLL].find(
        {"current_stage": "prop_safe"},
        {"_id": 0},
    ):
        challengers.append(d)

    # Sort eligible by deploy_score asc — weakest first.
    eligible_docs.sort(key=lambda d: _deploy_score_of(d))
    # Sort challengers desc — strongest first.
    challengers.sort(key=lambda d: -_deploy_score_of(d))

    advisory: List[Dict[str, Any]] = []
    used_challengers: set = set()
    over_cap = len(eligible_docs) > SURVIVOR_TOP_N

    # Cap pairing — never pair the same challenger to multiple incumbents.
    for incumbent in eligible_docs[: max(1, len(eligible_docs) // 10)]:
        inc_score = _deploy_score_of(incumbent)
        inc_days = _days_since(incumbent.get("current_stage_since"))
        for challenger in challengers:
            chash = challenger.get("strategy_hash")
            if chash in used_challengers:
                continue
            ch_score = _deploy_score_of(challenger)
            if ch_score == float("-inf") or inc_score == float("-inf"):
                continue
            delta = ch_score - inc_score
            cooldown_ok = (inc_days is not None and inc_days >= REPLACEMENT_COOLDOWN_DAYS)
            delta_ok = delta >= REPLACEMENT_MIN_DEPLOY_SCORE_DELTA
            eligible_now = bool(cooldown_ok and delta_ok)
            advisory.append({
                "incumbent": {
                    "strategy_hash":  incumbent.get("strategy_hash"),
                    "deploy_score":   inc_score if inc_score > float("-inf") else None,
                    "current_stage":  incumbent.get("current_stage"),
                    "in_universe_days": round(inc_days, 2) if inc_days is not None else None,
                },
                "challenger": {
                    "strategy_hash":  chash,
                    "deploy_score":   ch_score if ch_score > float("-inf") else None,
                    "current_stage":  challenger.get("current_stage"),
                },
                "delta":              round(delta, 4),
                "min_delta":          REPLACEMENT_MIN_DEPLOY_SCORE_DELTA,
                "cooldown_ok":        cooldown_ok,
                "delta_ok":           delta_ok,
                "eligible":           eligible_now,
                "reason":             _explain(cooldown_ok, delta_ok, delta),
            })
            if eligible_now:
                used_challengers.add(chash)
                break  # one challenger per incumbent

    would_execute = [a for a in advisory if a["eligible"]]
    return {
        "active_count":            len(eligible_docs),
        "cap":                     SURVIVOR_TOP_N,
        "over_cap":                over_cap,
        "advisory_replacements":   advisory,
        "would_execute_if_enabled": would_execute,
        "auto_replace_enabled":    SURVIVOR_AUTO_REPLACE_ENABLED,
        "min_delta":               REPLACEMENT_MIN_DEPLOY_SCORE_DELTA,
        "cooldown_days":           REPLACEMENT_COOLDOWN_DAYS,
        "phase":                   PHASE_VERSION,
        "advisory_only":           True,
        "computed_at":             _now_iso(),
    }


def _explain(cooldown_ok: bool, delta_ok: bool, delta: float) -> str:
    if not cooldown_ok and not delta_ok:
        return f"cooldown_not_met AND delta_below_min ({delta:.2f} < {REPLACEMENT_MIN_DEPLOY_SCORE_DELTA})"
    if not cooldown_ok:
        return "cooldown_not_met"
    if not delta_ok:
        return f"delta_below_min ({delta:.2f} < {REPLACEMENT_MIN_DEPLOY_SCORE_DELTA})"
    return f"challenger_dominant (delta {delta:.2f} >= {REPLACEMENT_MIN_DEPLOY_SCORE_DELTA})"


async def execute_replacement(
    *,
    incumbent_hash: str,
    challenger_hash: str,
    admin_email: str,
    reason: str,
) -> Dict[str, Any]:
    """Apply a single operator-approved replacement.

    Effects:
      • incumbent.current_stage  → "prop_safe"  (one step down)
      • audit row in strategy_lifecycle_history (NOT a forced advance for the challenger;
        the challenger advances naturally on the next lifecycle eval tick)
      • audit row in audit_log collection (operator-traceable, permanent)
    """
    if not (incumbent_hash and challenger_hash and admin_email and reason):
        raise ValueError("incumbent_hash, challenger_hash, admin_email, reason required")
    db = get_db()
    inc = await db[LIFECYCLE_COLL].find_one(
        {"strategy_hash": incumbent_hash}, {"_id": 0},
    )
    if not inc:
        raise ValueError(f"incumbent {incumbent_hash} has no lifecycle doc")
    if inc.get("current_stage") not in SURVIVOR_ELIGIBLE_STAGES:
        raise ValueError(
            f"incumbent at stage={inc.get('current_stage')} is not in survivor universe"
        )
    ch = await db[LIFECYCLE_COLL].find_one(
        {"strategy_hash": challenger_hash}, {"_id": 0},
    )
    if not ch:
        raise ValueError(f"challenger {challenger_hash} has no lifecycle doc")

    new_stage = "prop_safe"
    transition_at = _now_iso()

    await db[LIFECYCLE_COLL].update_one(
        {"strategy_hash": incumbent_hash},
        {"$set": {
            "current_stage": new_stage,
            "stage_rank": 4,  # prop_safe rank
            "current_stage_since": transition_at,
            "phase30_demoted_by_replacement": True,
        }},
    )

    await db[LIFECYCLE_HISTORY_COLL].insert_one({
        "strategy_hash": incumbent_hash,
        "from_stage":    inc.get("current_stage"),
        "to_stage":      new_stage,
        "transition_at": transition_at,
        "reason":        "phase30_replacement_demotion",
        "phase30_replaced_by": challenger_hash,
        "admin_email":   admin_email,
        "operator_reason": reason,
    })

    await db[AUDIT_COLL].insert_one({
        "event":         "phase30_replacement",
        "incumbent":     incumbent_hash,
        "challenger":    challenger_hash,
        "incumbent_from_stage": inc.get("current_stage"),
        "incumbent_to_stage":   new_stage,
        "admin_email":   admin_email,
        "reason":        reason,
        "phase":         PHASE_VERSION,
        "ts":            transition_at,
    })

    # ── Phase 30.1 · Δ2 — Institutional event (subordinate-only) ──
    try:
        from engines.alert_engine import emit_event as _emit
        await _emit(
            "REPLACEMENT_EXECUTED",
            incumbent_hash,
            {
                "incumbent_from_stage": inc.get("current_stage"),
                "incumbent_to_stage":   new_stage,
                "challenger_hash":      challenger_hash,
                "admin_email":          admin_email,
                "reason":               reason,
            },
        )
    except Exception:                                       # pragma: no cover
        pass

    return {
        "executed":          True,
        "incumbent_hash":    incumbent_hash,
        "incumbent_new_stage": new_stage,
        "challenger_hash":   challenger_hash,
        "admin_email":       admin_email,
        "ts":                transition_at,
        "phase":             PHASE_VERSION,
    }
