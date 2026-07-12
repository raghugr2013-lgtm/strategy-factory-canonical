"""Phase 3 — Auto Selection Engine.

End-to-end picker that, given optional filters, walks the existing
pipeline (strategy_performance_history → strategy_market_profile →
prop_firm_rules → strategy_challenge_match) and returns the best
deployment-ready combinations:

    Strategy  →  Pair × Timeframe  →  Firm × Challenge  →  Safe Risk

Additive only. Does NOT modify mutation / scoring / ingestion / Phase 18
rule engine / Phase 19 matcher / Phase 20 review layer. Re-uses the
existing `match_strategy_to_challenges` engine — this module is purely
a ranking & filtering facade over stored data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import strategy_memory as sm
from engines import challenge_matching_engine as cm
from engines import prop_firm_rule_engine as pe

logger = logging.getLogger(__name__)

SELECTION_COLL = "auto_selection_runs"

# Defaults tuned for "deployment-ready" surface
DEFAULT_MIN_PF = 1.2
DEFAULT_MIN_RUNS = 3
DEFAULT_MIN_STABILITY = 0.5
DEFAULT_MIN_PASS_PROB = 40.0
DEFAULT_MIN_MATCH_SCORE = 0.2
DEFAULT_MIN_ENV_CONFIDENCE = 0.4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── ASF Migration guard (GATE 3) ──────────────────────────────────────

async def _is_imported_seed_locked(strategy_hash: str) -> bool:
    """Return True iff the candidate strategy is an imported survivor
    that has not yet been re-certified / re-profiled / re-ranked. Per
    operator decree at GATE 3: imported scores are historical metadata
    only and must not flow to live deployment until the post-import
    pipeline flips the requires_* flags.

    Match path: strategy_library is keyed by `fingerprint` (SHA-1) but
    rollups arrive keyed by `strategy_hash` (SHA-256). The adapter
    populates BOTH on the strategy_library doc, so we OR on either.
    """
    if not strategy_hash:
        return False
    try:
        db = get_db()
        doc = await db["strategy_library"].find_one(
            {"$or": [{"fingerprint": strategy_hash},
                     {"strategy_hash": strategy_hash}]},
            {"lifecycle": 1, "provenance": 1, "_id": 0},
        )
        if not doc:
            return False
        lc = doc.get("lifecycle") or {}
        prov = doc.get("provenance") or {}
        if lc.get("stage") != "IMPORTED_SEED":
            return False
        if (lc.get("stage_locked_until") or "") > _now_iso():
            return True
        if prov.get("requires_revalidation") or prov.get("requires_rescoring") \
                or prov.get("requires_rematching"):
            return True
    except Exception:
        # Fail open — guard absence must not break ordinary candidates.
        return False
    return False


# ── Composite "deployment score" ─────────────────────────────────────

def _compute_deploy_score(*, rollup: Dict[str, Any], match: Dict[str, Any],
                          env: Dict[str, Any]) -> float:
    """Blend strategy-quality, firm-fit, and environment-confidence into a
    single 0-2 score for ranking. Higher is better."""
    pf_component = 0.0
    best_pf = rollup.get("best_pf")
    if isinstance(best_pf, (int, float)):
        pf_component = max(0.0, min(1.0, (best_pf - 1.0) / 0.5))   # saturates at PF 1.5
    stability = rollup.get("stability_score") or 0.0
    pass_prob = (match.get("pass_probability") or 0.0) / 100.0
    match_score = max(0.0, (match.get("score") or 0.0))
    env_conf = (env or {}).get("confidence") or 0.0
    raw = (
        pass_prob * 0.45
        + match_score * 0.25
        + pf_component * 0.15
        + stability * 0.10
        + env_conf * 0.05
    )
    # Penalise FAIL status
    if (match.get("status") or "").upper() == "FAIL":
        raw *= 0.2
    return round(max(0.0, min(2.0, raw)), 4)


# ── Core selection ──────────────────────────────────────────────────

async def _ensure_supporting_analysis(
    strategy_hash: str, *, run_missing: bool,
) -> Optional[Dict[str, Any]]:
    """Return (possibly recomputed) challenge_match doc for a hash.
    If `run_missing=True` and no match exists yet, trigger one."""
    existing = await cm.get_match(strategy_hash)
    if existing and not existing.get("skipped"):
        # Existing match — fine as-is.
        existing.pop("skipped", None)
        return existing
    if not run_missing:
        return None
    try:
        return await cm.match_strategy_to_challenges(strategy_hash, force=False)
    except (ValueError, PermissionError) as e:
        logger.debug("auto-select: cannot match %s: %s", strategy_hash, e)
        return None
    except Exception:
        logger.exception("auto-select: match failed for %s", strategy_hash)
        return None


async def _ensure_market_profile(strategy_hash: str) -> Optional[Dict[str, Any]]:
    from engines.market_intelligence import get_profile
    try:
        prof = await get_profile(strategy_hash)
        return prof.get("best_environment")
    except Exception:
        return None


async def run_auto_selection(
    *,
    top_n: int = 10,
    min_pf: float = DEFAULT_MIN_PF,
    min_runs: int = DEFAULT_MIN_RUNS,
    min_stability: float = DEFAULT_MIN_STABILITY,
    min_pass_probability: float = DEFAULT_MIN_PASS_PROB,
    min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    min_env_confidence: float = DEFAULT_MIN_ENV_CONFIDENCE,
    firm_slug: Optional[str] = None,
    pass_only: bool = False,
    run_missing_matches: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Return ranked deployment candidates. Persists the top-N snapshot
    into `auto_selection_runs` for history."""
    rollups = await sm.get_explorer_rollup(
        min_pf=min_pf, min_runs=min_runs, limit=500,
    )
    rollups = [
        r for r in rollups
        if isinstance(r.get("stability_score"), (int, float))
        and r["stability_score"] >= min_stability
    ]

    candidates: List[Dict[str, Any]] = []
    for r in rollups:
        h = r["strategy_hash"]
        # ASF Migration Guard (GATE 3): block imported survivors until
        # the post-import pipeline re-certifies + re-ranks them.
        if await _is_imported_seed_locked(h):
            continue
        match = await _ensure_supporting_analysis(h, run_missing=run_missing_matches)
        if not match:
            continue
        if firm_slug and (match.get("best_firm") or "").lower() != firm_slug.lower():
            continue
        if pass_only and (match.get("status") or "").upper() != "PASS":
            continue
        pass_prob = match.get("pass_probability") or 0.0
        if pass_prob < min_pass_probability:
            continue
        if (match.get("score") or 0.0) < min_match_score:
            continue
        env = match.get("environment_used") or await _ensure_market_profile(h)
        env = env or {}
        if (env.get("confidence") or 0.0) < min_env_confidence:
            # Environment confidence gate is soft — still include but flag it.
            env_flag = "low_confidence"
        else:
            env_flag = None

        # Firm must still be approved (otherwise the saved match is stale).
        approved = True
        try:
            approved = await pe.is_firm_approved(match.get("best_firm") or "")
        except Exception:
            approved = True
        if not approved:
            continue

        deploy_score = _compute_deploy_score(rollup=r, match=match, env=env)
        candidates.append({
            "strategy_hash": h,
            "strategy_name": r.get("name") or match.get("strategy_name"),
            "type": r.get("type"),
            "pair": env.get("pair"),
            "timeframe": env.get("timeframe"),
            "env_confidence": env.get("confidence"),
            "env_flag": env_flag,
            "firm_slug": match.get("best_firm"),
            "firm_name": match.get("best_firm_name"),
            "challenge": match.get("best_challenge"),
            "status": match.get("status"),
            "pass_probability": pass_prob,
            "expected_days": match.get("expected_days"),
            "match_score": match.get("score"),
            "safe_risk": match.get("safe_risk"),
            "strategy_best_pf": r.get("best_pf"),
            "strategy_stability": r.get("stability_score"),
            "deploy_score": deploy_score,
        })

    candidates.sort(
        key=lambda c: (
            -(c["deploy_score"] or 0.0),
            -(c["pass_probability"] or 0.0),
            -(c["match_score"] or 0.0),
            c["expected_days"] if c["expected_days"] is not None else 9999,
        )
    )
    top = candidates[: max(1, int(top_n))]

    run_doc: Optional[Dict[str, Any]] = None
    if persist and top:
        db = get_db()
        run_doc = {
            "run_id": _now_iso(),
            "ran_at": _now_iso(),
            "filters": {
                "top_n": top_n, "min_pf": min_pf, "min_runs": min_runs,
                "min_stability": min_stability,
                "min_pass_probability": min_pass_probability,
                "min_match_score": min_match_score,
                "min_env_confidence": min_env_confidence,
                "firm_slug": firm_slug, "pass_only": pass_only,
            },
            "count": len(top),
            "top": [{k: v for k, v in c.items()} for c in top],
        }
        await db[SELECTION_COLL].insert_one({**run_doc})

    return {
        "status": "ok",
        "considered": len(rollups),
        "eligible": len(candidates),
        "count": len(top),
        "top": top,
        "persisted": bool(run_doc),
        "ran_at": _now_iso(),
    }


async def get_recent_runs(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[SELECTION_COLL].find({}, {"_id": 0}).sort("ran_at", -1).limit(max(1, min(limit, 50)))
    return [d async for d in cursor]
