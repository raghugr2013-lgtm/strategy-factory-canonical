"""Challenge Type Matching Engine (Phase 2 — additive only).

Ranks each strategy against (firm × challenge_type) combinations and
persists the winner + alternatives to `strategy_challenge_match`.

Does NOT modify:
  * mutation_engine / scoring
  * ingestion pipeline
  * prop_firm_rule_engine (REUSED only)

Challenge types per firm live in the new collection
`firm_challenge_types`. On first use the collection is auto-seeded with
reasonable Standard / Aggressive variants for each firm found in
`challenge_rules`. Operators can add / edit types manually and they will
NOT be overwritten by re-seeding.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import prop_firm_rule_engine as pe

logger = logging.getLogger(__name__)

CHALLENGE_TYPES_COLL = "firm_challenge_types"
MATCH_COLL = "strategy_challenge_match"

# Eligibility gates (mirror Phase 17 market-intelligence)
MIN_PF = 1.2
MIN_RUNS = 3
MAX_PER_CYCLE = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Challenge type seeding + access ──────────────────────────────────

_DEFAULT_TYPES_BY_FIRM = {
    "ftmo": [
        {
            "name": "Standard",
            "profit_target": 10.0, "max_daily_dd": 5.0, "max_total_dd": 10.0,
            "min_trading_days": 4, "consistency_rule": False, "time_limit_days": 30,
            "initial_balance": 100000,
        },
        {
            "name": "Aggressive",
            "profit_target": 20.0, "max_daily_dd": 10.0, "max_total_dd": 20.0,
            "min_trading_days": 4, "consistency_rule": False, "time_limit_days": 60,
            "initial_balance": 100000,
        },
    ],
    "fundednext": [
        {
            "name": "Standard",
            "profit_target": 8.0, "max_daily_dd": 5.0, "max_total_dd": 10.0,
            "min_trading_days": 5, "consistency_rule": True, "time_limit_days": 30,
            "initial_balance": 100000,
        },
        {
            "name": "Stellar",
            "profit_target": 10.0, "max_daily_dd": 5.0, "max_total_dd": 10.0,
            "min_trading_days": 5, "consistency_rule": True, "time_limit_days": 45,
            "initial_balance": 100000,
        },
    ],
    "pipfarm": [
        {
            "name": "Evaluation",
            "profit_target": 10.0, "max_daily_dd": 4.0, "max_total_dd": 8.0,
            "min_trading_days": 3, "consistency_rule": False, "time_limit_days": 30,
            "initial_balance": 100000,
        },
        {
            "name": "Instant",
            "profit_target": 6.0, "max_daily_dd": 6.0, "max_total_dd": 12.0,
            "min_trading_days": 0, "consistency_rule": False, "time_limit_days": 45,
            "initial_balance": 100000,
        },
    ],
}


async def seed_challenge_types_if_empty() -> int:
    """Insert default challenge types per firm if the collection is empty.
    Idempotent — existing docs are left untouched."""
    db = get_db()
    inserted = 0
    async for fr in db.challenge_rules.find({}, {"_id": 0, "firm_slug": 1, "firm_name": 1}):
        slug = fr["firm_slug"]
        defaults = _DEFAULT_TYPES_BY_FIRM.get(slug)
        if not defaults:
            # Generic fallback: seed a single "Standard" type mirroring the
            # firm's normalised rule snapshot.
            norm = await pe.get_normalized_rules(slug)
            if not norm:
                continue
            defaults = [{
                "name": norm.get("phase") or "Standard",
                "profit_target": norm.get("profit_target_pct") or 10.0,
                "max_daily_dd": norm.get("max_daily_loss_pct") or 5.0,
                "max_total_dd": norm.get("max_total_loss_pct") or 10.0,
                "min_trading_days": norm.get("min_trading_days") or 4,
                "consistency_rule": bool(norm.get("consistency_rule")),
                "time_limit_days": norm.get("time_limit_days") or 30,
                "initial_balance": norm.get("initial_balance") or 100000,
            }]
        for ct in defaults:
            existing = await db[CHALLENGE_TYPES_COLL].find_one(
                {"firm_slug": slug, "name": ct["name"]}, {"_id": 0},
            )
            if existing:
                continue
            doc = {
                "firm_slug": slug,
                "firm_name": fr.get("firm_name") or slug.upper(),
                **ct,
                "seeded_at": _now_iso(),
            }
            await db[CHALLENGE_TYPES_COLL].insert_one({**doc})
            inserted += 1
    return inserted


async def list_challenge_types(*, only_approved: bool = False) -> List[Dict[str, Any]]:
    await seed_challenge_types_if_empty()
    db = get_db()
    cursor = db[CHALLENGE_TYPES_COLL].find({}, {"_id": 0}).sort([("firm_slug", 1), ("name", 1)])
    rows = [d async for d in cursor]
    if only_approved:
        approved: Dict[str, bool] = {}
        for r in rows:
            slug = r["firm_slug"]
            if slug not in approved:
                approved[slug] = await pe.is_firm_approved(slug)
        rows = [r for r in rows if approved.get(r["firm_slug"], False)]
    return rows


async def list_by_firm() -> Dict[str, Any]:
    """Return {firm_slug: {firm_name, challenges: [...]}} shape described in spec."""
    rows = await list_challenge_types()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        slot = out.setdefault(r["firm_slug"], {
            "firm_slug": r["firm_slug"],
            "firm_name": r.get("firm_name"),
            "challenges": [],
        })
        slot["challenges"].append({
            "name": r.get("name"),
            "profit_target": r.get("profit_target"),
            "max_daily_dd": r.get("max_daily_dd"),
            "max_total_dd": r.get("max_total_dd"),
            "min_trading_days": r.get("min_trading_days"),
            "consistency_rule": r.get("consistency_rule"),
            "time_limit_days": r.get("time_limit_days"),
            "initial_balance": r.get("initial_balance"),
        })
    return {"firms": list(out.values())}


# ── Rule synthesis (ChallengeType → flat rule dict) ─────────────────

def _rules_from_challenge(
    firm_slug: str, firm_name: Optional[str], ct: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a `prop_firm_rule_engine` compatible flat rules dict."""
    return {
        "firm_slug": firm_slug,
        "firm_name": firm_name or firm_slug.upper(),
        "phase": ct.get("name"),
        "initial_balance": ct.get("initial_balance") or 100000,
        "max_daily_loss_pct": ct.get("max_daily_dd"),
        "daily_loss_type": "equity",
        "max_total_loss_pct": ct.get("max_total_dd"),
        "trailing_drawdown": False,
        "trailing_type": None,
        "profit_target_pct": ct.get("profit_target"),
        "min_trading_days": ct.get("min_trading_days"),
        "max_trades_per_day": None,
        "consistency_rule": bool(ct.get("consistency_rule")),
        "time_limit_days": ct.get("time_limit_days") or 30,
    }


# ── Scoring (documented formula) ────────────────────────────────────

_PASS_WEIGHT = 1.0           # 0..1 * 1.0
_LOW_DD_WEIGHT = 0.30        # ratio of dd_headroom * 0.30
_STABILITY_WEIGHT = 0.20     # stability_component * 0.20
_VIOLATION_PENALTY = 0.40    # per CRITICAL violation
_WARNING_PENALTY = 0.05      # per warning
_TIME_LIMIT_PENALTY = 0.25   # if expected_days > time_limit


def _compute_match_score(
    validation: Dict[str, Any], simulation: Dict[str, Any],
) -> float:
    pass_component = (simulation.get("pass_probability") or 0.0) / 100.0
    comp = simulation.get("components") or {}
    dd_bonus = float(comp.get("dd_headroom") or 0.0)
    stability_bonus = float(comp.get("stability") or 0.0)
    n_critical = sum(
        1 for v in (validation.get("violations") or []) if v.get("severity") == "critical"
    )
    n_warnings = len(validation.get("warnings") or [])
    time_pen = _TIME_LIMIT_PENALTY if simulation.get("hits_time_limit") else 0.0
    raw = (
        _PASS_WEIGHT * pass_component
        + _LOW_DD_WEIGHT * dd_bonus
        + _STABILITY_WEIGHT * stability_bonus
        - _VIOLATION_PENALTY * n_critical
        - _WARNING_PENALTY * n_warnings
        - time_pen
    )
    return round(max(-1.0, min(2.0, raw)), 4)


# ── Core matcher ────────────────────────────────────────────────────

async def _build_stats_with_env(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Use Phase 17's best_environment metrics when available (more realistic
    than raw rollup stats for pass-probability estimation)."""
    stats = await pe.build_strategy_stats(strategy_hash)
    if not stats:
        return None
    env = stats.get("best_environment") or {}
    if env:
        # Overlay env-derived metrics — they reflect the pair/TF we'd deploy on.
        if isinstance(env.get("pf"), (int, float)):
            stats["pf"] = float(env["pf"])
        if isinstance(env.get("dd_pct"), (int, float)):
            stats["dd_pct"] = float(env["dd_pct"])
        if isinstance(env.get("trades"), (int, float)):
            stats["trades"] = int(env["trades"])
    return stats


async def _is_eligible(strategy_hash: str) -> bool:
    """Gate — PF ≥ 1.2 AND runs ≥ 3 against rollup."""
    from engines.strategy_memory import get_explorer_rollup
    rollups = await get_explorer_rollup(min_pf=MIN_PF, min_runs=MIN_RUNS, limit=500)
    return any(r["strategy_hash"] == strategy_hash for r in rollups)


async def match_strategy_to_challenges(
    strategy_hash: str, *, force: bool = False,
) -> Dict[str, Any]:
    """Core entry. Returns the persisted match document.
    Skips if already matched unless force=True."""
    db = get_db()
    if not force:
        existing = await db[MATCH_COLL].find_one(
            {"strategy_hash": strategy_hash}, {"_id": 0},
        )
        if existing:
            existing["skipped"] = True
            return existing

    if not await _is_eligible(strategy_hash):
        raise ValueError(
            "strategy is not eligible (requires best_pf>=1.2 AND runs>=3)"
        )

    stats = await _build_stats_with_env(strategy_hash)
    if not stats:
        raise ValueError(f"no history for strategy_hash: {strategy_hash}")

    await seed_challenge_types_if_empty()

    types = await list_challenge_types(only_approved=True)
    if not types:
        raise PermissionError("rules_not_verified")

    results: List[Dict[str, Any]] = []
    for ct in types:
        rules = _rules_from_challenge(ct["firm_slug"], ct.get("firm_name"), ct)
        validation = pe.validate_strategy_against_firm(stats, rules)
        simulation = pe.simulate_challenge(stats, rules)
        score = _compute_match_score(validation, simulation)
        results.append({
            "firm_slug": ct["firm_slug"],
            "firm_name": ct.get("firm_name"),
            "challenge": ct["name"],
            "pass_probability": simulation.get("pass_probability"),
            "expected_days": simulation.get("expected_days_to_pass"),
            "risk_level": simulation.get("risk_level"),
            "status": validation.get("status"),
            "violations": len(validation.get("violations") or []),
            "warnings": len(validation.get("warnings") or []),
            "hits_time_limit": bool(simulation.get("hits_time_limit")),
            "rules": rules,
            "score": score,
        })

    # Rank: highest score wins; tiebreak by pass_probability desc,
    # then lowest expected_days, then fewer violations.
    results.sort(
        key=lambda r: (
            -(r["score"] or 0.0),
            -(r["pass_probability"] or 0.0),
            r["expected_days"] if r["expected_days"] is not None else 9999,
            r["violations"],
        )
    )

    best = results[0]
    # Safe-risk from the winning firm (uses its rules)
    risk_profile = pe.compute_safe_risk(stats, best["rules"])

    alternatives = [
        {
            "firm": r["firm_slug"],
            "firm_name": r["firm_name"],
            "challenge": r["challenge"],
            "pass_probability": r["pass_probability"],
            "expected_days": r["expected_days"],
            "status": r["status"],
            "score": r["score"],
        }
        for r in results[1:6]  # top 5 alternatives
    ]

    doc = {
        "strategy_hash": strategy_hash,
        "strategy_name": stats.get("name"),
        "best_firm": best["firm_slug"],
        "best_firm_name": best["firm_name"],
        "best_challenge": best["challenge"],
        "pass_probability": best["pass_probability"],
        "expected_days": best["expected_days"],
        "risk_level": best["risk_level"],
        "status": best["status"],
        "safe_risk": risk_profile.get("recommended_risk_per_trade"),
        "score": best["score"],
        "environment_used": stats.get("best_environment"),
        "stats_used": {
            "pf": stats.get("pf"),
            "dd_pct": stats.get("dd_pct"),
            "trades": stats.get("trades"),
            "stability_score": stats.get("stability_score"),
        },
        "alternatives": alternatives,
        "evaluated_count": len(results),
        "matched_at": _now_iso(),
    }

    await db[MATCH_COLL].update_one(
        {"strategy_hash": strategy_hash}, {"$set": doc}, upsert=True,
    )
    doc["skipped"] = False
    return doc


async def get_match(strategy_hash: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[MATCH_COLL].find_one(
        {"strategy_hash": strategy_hash}, {"_id": 0},
    )


async def get_matches_map(hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Bulk lookup for Explorer enrichment."""
    if not hashes:
        return {}
    db = get_db()
    out: Dict[str, Dict[str, Any]] = {}
    async for d in db[MATCH_COLL].find(
        {"strategy_hash": {"$in": list(set(hashes))}},
        {
            "_id": 0, "strategy_hash": 1, "best_firm": 1, "best_firm_name": 1,
            "best_challenge": 1, "pass_probability": 1, "score": 1,
            "expected_days": 1, "safe_risk": 1, "status": 1,
        },
    ):
        out[d["strategy_hash"]] = {
            "best_firm": d.get("best_firm"),
            "best_firm_name": d.get("best_firm_name"),
            "best_challenge": d.get("best_challenge"),
            "pass_probability": d.get("pass_probability"),
            "expected_days": d.get("expected_days"),
            "safe_risk": d.get("safe_risk"),
            "score": d.get("score"),
            "status": d.get("status"),
        }
    return out


# ── Batch eligible ──────────────────────────────────────────────────

async def match_eligible(*, limit: int = MAX_PER_CYCLE, force: bool = False) -> Dict[str, Any]:
    from engines.strategy_memory import get_explorer_rollup
    limit = max(1, min(int(limit), 20))
    rollups = await get_explorer_rollup(min_pf=MIN_PF, min_runs=MIN_RUNS, limit=500)
    db = get_db()
    if not force:
        matched = set()
        async for d in db[MATCH_COLL].find({}, {"_id": 0, "strategy_hash": 1}):
            matched.add(d["strategy_hash"])
        rollups = [r for r in rollups if r["strategy_hash"] not in matched]
    rollups = rollups[:limit]

    summaries: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for r in rollups:
        h = r["strategy_hash"]
        try:
            doc = await match_strategy_to_challenges(h, force=force)
            summaries.append({
                "strategy_hash": h,
                "name": r.get("name"),
                "best_firm": doc.get("best_firm"),
                "best_challenge": doc.get("best_challenge"),
                "pass_probability": doc.get("pass_probability"),
                "score": doc.get("score"),
            })
        except Exception as e:
            logger.exception("match_eligible failed for %s", h)
            errors.append({"strategy_hash": h, "error": str(e)[:200]})
    return {
        "status": "ok",
        "considered": len(rollups),
        "matched": len(summaries),
        "errors": errors,
        "results": summaries,
    }
