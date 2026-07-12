"""Prop Firm Rule Engine (Phase 1).

Fully ADDITIVE layer on top of the existing `challenge_rules` collection.
Provides a normalised flat schema, a strategy-level validator, a stat-
driven challenge simulator, and a safe-risk calculator. Persists results
to new collections so the Explorer can show PASS/FAIL/RISKY, pass
probability, and safe risk per trade without re-running heavy sims.

Does NOT modify:
  * mutation_engine / scoring
  * ingestion pipeline
  * existing rule_engine.py (read-only consumer)
  * existing challenge_simulator.py / pass_probability.py
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

RULES_COLL = "prop_firm_rules"                 # normalised snapshot + review state
PASS_ANALYSIS_COLL = "strategy_pass_analysis"  # per (hash, firm)
RISK_PROFILE_COLL = "strategy_risk_profile"    # per (hash, firm)

DEFAULT_FIRM = "ftmo"

# Review/approval status values
STATUS_PARSED = "parsed"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
_REVIEW_FIELDS = {
    "parsed_rules", "approved_rules", "status", "parser_confidence",
    "source_type", "source_url", "auto_approved",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 0. Migration / backfill ─────────────────────────────────────────

_BACKFILL_DONE = False


async def backfill_review_fields() -> int:
    """Auto-approve legacy docs that have no `status` field. Idempotent.
    Runs at most once per process."""
    global _BACKFILL_DONE
    if _BACKFILL_DONE:
        return 0
    db = get_db()
    count = 0
    async for d in db[RULES_COLL].find(
        {"status": {"$exists": False}}, {"_id": 0},
    ):
        flat_fields = {
            k: v for k, v in d.items()
            if k not in _REVIEW_FIELDS
            and k not in ("firm_slug", "firm_name", "normalized_at", "source", "phase", "initial_balance")
        }
        await db[RULES_COLL].update_one(
            {"firm_slug": d["firm_slug"]},
            {"$set": {
                "status": STATUS_APPROVED,
                "auto_approved": True,
                "approved_rules": flat_fields or None,
                "parsed_rules": flat_fields or None,
                "parser_confidence": None,
                "source_type": d.get("source") == "challenge_rules" and "legacy" or None,
                "source_url": None,
                "updated_at": _now_iso(),
            }},
        )
        count += 1
    _BACKFILL_DONE = True
    return count


# ── 1. Normalisation ────────────────────────────────────────────────

def _coalesce(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


async def normalize_rules(firm_slug: str) -> Optional[Dict[str, Any]]:
    """Read `challenge_rules` (nested schema) for `firm_slug` and return a
    FLAT normalised rule record. Also upserts into `prop_firm_rules`.
    Returns None if the firm is unknown."""
    db = get_db()
    doc = await db.challenge_rules.find_one({"firm_slug": firm_slug}, {"_id": 0})
    if not doc:
        return None
    r = doc.get("rules") or {}
    daily = r.get("daily_dd") or {}
    total = r.get("total_dd") or {}
    target = r.get("profit_target") or {}
    min_days = r.get("min_trading_days") or {}
    consistency = r.get("consistency") or {}
    restrictions = r.get("restrictions") or {}
    time_limit = r.get("time_limit") or {}

    # Back-fill at the top level if caller already flattened some fields
    flat = {
        "firm_slug": doc.get("firm_slug"),
        "firm_name": doc.get("firm_name"),
        "phase": doc.get("phase"),
        "initial_balance": doc.get("initial_balance"),
        "max_daily_loss_pct": _coalesce(doc.get("max_daily_loss_pct"), daily.get("max_pct")),
        "daily_loss_type": _coalesce(doc.get("daily_loss_type"), daily.get("type")),
        "max_total_loss_pct": _coalesce(doc.get("max_total_loss_pct"), total.get("max_pct")),
        "trailing_drawdown": _coalesce(
            doc.get("trailing_drawdown"),
            total.get("type") == "trailing" if total.get("type") else None,
        ),
        "trailing_type": (
            total.get("type") if total.get("type") in ("equity", "balance") else None
        ),
        "profit_target_pct": _coalesce(doc.get("profit_target_pct"), target.get("target_pct")),
        "min_trading_days": _coalesce(doc.get("min_trading_days"), min_days.get("days")),
        "max_trades_per_day": _coalesce(
            doc.get("max_trades_per_day"), restrictions.get("max_trades_per_day"),
        ),
        "consistency_rule": _coalesce(doc.get("consistency_rule"), consistency.get("enabled")) or False,
        "time_limit_days": _coalesce(doc.get("time_limit_days"), time_limit.get("calendar_days")),
        "normalized_at": _now_iso(),
        "source": "challenge_rules",
    }
    try:
        # Preserve any existing review state on upsert. If the doc is brand
        # new, default status="parsed" so it must be approved before use.
        prev = await db[RULES_COLL].find_one({"firm_slug": flat["firm_slug"]}, {"_id": 0})
        if prev and prev.get("status"):
            flat["status"] = prev.get("status")
            flat["auto_approved"] = prev.get("auto_approved", False)
            flat["approved_rules"] = prev.get("approved_rules")
            flat["parsed_rules"] = prev.get("parsed_rules")
            flat["parser_confidence"] = prev.get("parser_confidence")
            flat["source_type"] = prev.get("source_type")
            flat["source_url"] = prev.get("source_url")
        else:
            flat["status"] = STATUS_PARSED
            flat["auto_approved"] = False
            flat["approved_rules"] = None
            flat["parsed_rules"] = {
                k: v for k, v in flat.items()
                if k not in ("firm_slug", "firm_name", "phase", "normalized_at", "source")
            }
        flat["updated_at"] = _now_iso()
        await db[RULES_COLL].update_one(
            {"firm_slug": flat["firm_slug"]}, {"$set": flat}, upsert=True,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("normalize_rules upsert failed: %s", e)
    return flat


async def list_normalized_rules() -> List[Dict[str, Any]]:
    db = get_db()
    await backfill_review_fields()
    # Always re-normalise every known firm so this endpoint is self-healing.
    async for fr in db.challenge_rules.find({}, {"_id": 0, "firm_slug": 1}):
        try:
            await normalize_rules(fr["firm_slug"])
        except Exception as e:
            logger.debug("normalize %s failed: %s", fr.get("firm_slug"), e)
    cursor = db[RULES_COLL].find({}, {"_id": 0}).sort("firm_slug", 1)
    return [d async for d in cursor]


async def get_normalized_rules(
    firm_slug: str, *, require_approved: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return normalised rules doc. If `require_approved=True` (default),
    returns None when status != approved so the caller skips the firm.
    """
    db = get_db()
    await backfill_review_fields()
    doc = await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})
    if not doc:
        doc = await normalize_rules(firm_slug)
        if not doc:
            return None
    if require_approved and doc.get("status") != STATUS_APPROVED:
        return None
    # When approved, the approved_rules object is authoritative — overlay.
    if doc.get("status") == STATUS_APPROVED and isinstance(doc.get("approved_rules"), dict):
        for k, v in doc["approved_rules"].items():
            if v is not None:
                doc[k] = v
    return doc


async def is_firm_approved(firm_slug: str) -> bool:
    db = get_db()
    await backfill_review_fields()
    doc = await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0, "status": 1})
    return bool(doc and doc.get("status") == STATUS_APPROVED)


# ── Review / approval actions ───────────────────────────────────────

async def ingest_parsed_rules(
    firm_slug: str, *, firm_name: Optional[str] = None,
    parsed_rules: Dict[str, Any],
    parser_confidence: Optional[float] = None,
    source_type: Optional[str] = None,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a parser's output into prop_firm_rules WITHOUT approving it.
    Called from the Extract Rules flow. Idempotent per firm_slug."""
    db = get_db()
    await backfill_review_fields()
    now = _now_iso()
    prev = await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})
    doc: Dict[str, Any] = {
        "firm_slug": firm_slug,
        "firm_name": firm_name or (prev.get("firm_name") if prev else firm_slug.upper()),
        "parsed_rules": parsed_rules or {},
        "parser_confidence": parser_confidence,
        "source_type": source_type,
        "source_url": source_url,
        # A fresh parse flips the record back to `parsed` — caller must re-approve.
        "status": STATUS_PARSED,
        "auto_approved": False,
        "approved_rules": None,
        "updated_at": now,
        "normalized_at": now,
        "source": source_type or "extract",
    }
    # Preserve legacy flat fields if any (they're purely cosmetic — engines
    # rely on `approved_rules` once the record is approved).
    if prev:
        for k in (
            "max_daily_loss_pct", "daily_loss_type", "max_total_loss_pct",
            "trailing_drawdown", "trailing_type", "profit_target_pct",
            "min_trading_days", "max_trades_per_day", "consistency_rule",
            "time_limit_days", "initial_balance", "phase",
        ):
            if k not in doc and k in prev:
                doc[k] = prev[k]
    await db[RULES_COLL].update_one(
        {"firm_slug": firm_slug}, {"$set": doc}, upsert=True,
    )
    return doc


async def approve_rules(
    firm_slug: str, approved_rules: Dict[str, Any],
) -> Dict[str, Any]:
    db = get_db()
    await backfill_review_fields()
    prev = await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})
    if not prev:
        raise ValueError(f"no rules for firm_slug: {firm_slug}")
    # Copy editable fields onto the top-level so existing consumers see them
    flat = dict(approved_rules or {})
    flat["firm_slug"] = firm_slug
    if "firm_name" in prev and "firm_name" not in flat:
        flat["firm_name"] = prev["firm_name"]
    flat["status"] = STATUS_APPROVED
    flat["auto_approved"] = False
    flat["approved_rules"] = {k: v for k, v in approved_rules.items() if k not in ("firm_slug", "firm_name")}
    flat["updated_at"] = _now_iso()
    await db[RULES_COLL].update_one(
        {"firm_slug": firm_slug}, {"$set": flat},
    )
    return await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})


async def reject_rules(firm_slug: str) -> Dict[str, Any]:
    db = get_db()
    await backfill_review_fields()
    res = await db[RULES_COLL].update_one(
        {"firm_slug": firm_slug},
        {"$set": {
            "status": STATUS_REJECTED,
            "auto_approved": False,
            "updated_at": _now_iso(),
        }},
    )
    if res.matched_count == 0:
        raise ValueError(f"no rules for firm_slug: {firm_slug}")
    return await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})


async def reset_rules(firm_slug: str) -> Dict[str, Any]:
    db = get_db()
    await backfill_review_fields()
    res = await db[RULES_COLL].update_one(
        {"firm_slug": firm_slug},
        {"$set": {
            "status": STATUS_PARSED,
            "auto_approved": False,
            "approved_rules": None,
            "updated_at": _now_iso(),
        }},
    )
    if res.matched_count == 0:
        raise ValueError(f"no rules for firm_slug: {firm_slug}")
    return await db[RULES_COLL].find_one({"firm_slug": firm_slug}, {"_id": 0})


# ── 2. Validation ───────────────────────────────────────────────────

def validate_strategy_against_firm(
    stats: Dict[str, Any], rules: Dict[str, Any],
) -> Dict[str, Any]:
    """Fast, deterministic PASS / FAIL / RISKY verdict from strategy
    aggregate stats + flat rule record.

    `stats` keys used (all optional):
      * pf, dd_pct, win_rate, trades, stability_score,
        environment_confidence, avg_daily_return_pct
    """
    violations: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    pf = stats.get("pf")
    dd = stats.get("dd_pct")
    trades = stats.get("trades")
    stability = stats.get("stability_score")
    env_conf = stats.get("environment_confidence")

    max_total = rules.get("max_total_loss_pct")
    max_daily = rules.get("max_daily_loss_pct")
    min_days = rules.get("min_trading_days")
    target = rules.get("profit_target_pct")

    # Hard failures
    if isinstance(pf, (int, float)) and pf < 1.0:
        violations.append({
            "rule": "profit_factor_floor",
            "reason": f"PF {pf:.2f} < 1.0 — strategy is unprofitable.",
            "severity": "critical",
        })
    if isinstance(dd, (int, float)) and isinstance(max_total, (int, float)):
        if dd >= max_total:
            violations.append({
                "rule": "max_total_loss",
                "reason": f"Strategy DD {dd:.2f}% >= firm's {max_total}% max total loss.",
                "severity": "critical",
                "detail": {"strategy_dd": dd, "firm_max_total_loss": max_total},
            })
        elif dd >= max_total * 0.8:
            warnings.append({
                "rule": "max_total_loss_warning",
                "reason": f"DD {dd:.2f}% is within 80% of firm's {max_total}% cap.",
                "severity": "high",
            })

    # Daily loss heuristic — estimated daily loss = DD / sqrt(trade_days)
    est_daily_loss = None
    if isinstance(dd, (int, float)) and isinstance(trades, (int, float)) and trades > 0:
        # Very rough: treat DD as worst cumulative drop across ~trades/5 days
        est_days = max(1, int((trades or 0) / 5))
        est_daily_loss = dd / math.sqrt(est_days)
        if isinstance(max_daily, (int, float)) and est_daily_loss > max_daily:
            warnings.append({
                "rule": "daily_loss_estimate",
                "reason": (
                    f"Estimated worst-day loss ~{est_daily_loss:.2f}% may breach "
                    f"firm's {max_daily}% daily cap. Risk reduction recommended."
                ),
                "severity": "medium",
                "detail": {"est_daily_loss_pct": round(est_daily_loss, 2)},
            })

    if isinstance(min_days, (int, float)) and isinstance(trades, (int, float)):
        if trades < min_days:
            warnings.append({
                "rule": "min_trading_days",
                "reason": f"Strategy only generated {trades} trades — may not meet min_trading_days={min_days}.",
                "severity": "low",
            })

    if isinstance(stability, (int, float)) and stability < 0.5:
        warnings.append({
            "rule": "low_stability",
            "reason": f"Stability score {stability:.2f} is low — results may not generalise.",
            "severity": "medium",
        })

    if isinstance(env_conf, (int, float)) and env_conf < 0.6:
        warnings.append({
            "rule": "low_env_confidence",
            "reason": f"Best-environment confidence {env_conf:.2f} is low — prefer scanning more pairs.",
            "severity": "low",
        })

    # Classification
    if violations:
        status = "FAIL"
    elif warnings:
        status = "RISKY"
    else:
        status = "PASS"

    risk_adjustment_required = bool(
        violations or any(w.get("rule") in ("max_total_loss_warning", "daily_loss_estimate") for w in warnings),
    )

    return {
        "status": status,
        "violations": violations,
        "warnings": warnings,
        "risk_adjustment_required": risk_adjustment_required,
        "est_daily_loss_pct": round(est_daily_loss, 2) if est_daily_loss else None,
        "checked_against": {
            "firm_slug": rules.get("firm_slug"),
            "phase": rules.get("phase"),
            "max_total_loss_pct": max_total,
            "max_daily_loss_pct": max_daily,
            "profit_target_pct": target,
            "min_trading_days": min_days,
        },
    }


# ── 3. Challenge simulator (stat-driven) ─────────────────────────────

def simulate_challenge(
    stats: Dict[str, Any], rules: Dict[str, Any],
) -> Dict[str, Any]:
    """Analytic simulation derived from the strategy's aggregate stats.
    NOT a trade-by-trade Monte Carlo (the existing
    `engines.challenge_simulator` covers that path). Fast, deterministic,
    good enough for Explorer-level filtering.
    """
    pf = stats.get("pf")
    dd = stats.get("dd_pct")
    trades = stats.get("trades") or 0
    stability = stats.get("stability_score") or 0.5
    win_rate = stats.get("win_rate")
    avg_daily_return = stats.get("avg_daily_return_pct")

    target = rules.get("profit_target_pct") or 10.0
    max_total = rules.get("max_total_loss_pct") or 10.0
    min_days = rules.get("min_trading_days") or 4
    time_limit = rules.get("time_limit_days") or 30
    daily_cap = rules.get("max_daily_loss_pct") or (max_total / 2.0)

    # Estimate daily return %
    # Priority: caller-provided; else derive from pf + trade count + dd
    if isinstance(avg_daily_return, (int, float)) and avg_daily_return != 0:
        daily_ret = float(avg_daily_return)
    elif isinstance(pf, (int, float)) and isinstance(dd, (int, float)) and trades > 0:
        # PF>1 means net positive; assume return pct ~ (pf - 1) * dd * trades/50
        gross = max(0.0, (pf - 1.0)) * max(dd, 1.0) * max(1.0, trades / 50.0)
        # Spread it over an approximate trading window (trades/5 days)
        approx_days = max(1.0, trades / 5.0)
        daily_ret = gross / approx_days
    else:
        daily_ret = 0.1  # pessimistic default

    # Components of pass probability [0..1]:
    #   a) PF component — saturates at PF=1.5
    pf_component = 0.0
    if isinstance(pf, (int, float)) and pf > 0:
        pf_component = max(0.0, min(1.0, (pf - 1.0) / 0.5))
    #   b) DD headroom component — how much of the firm's DD cap is consumed
    dd_component = 1.0
    if isinstance(dd, (int, float)):
        consumed = min(1.0, max(0.0, dd / max(1e-6, max_total)))
        dd_component = 1.0 - consumed
    #   c) Daily-cap component — probability worst day stays under cap
    daily_component = 1.0
    if isinstance(dd, (int, float)) and trades > 0:
        approx_days = max(1, int(trades / 5))
        est_daily_loss = dd / math.sqrt(approx_days)
        daily_component = max(0.0, min(1.0, 1.0 - est_daily_loss / max(1e-6, daily_cap)))
    #   d) Stability
    stability_component = max(0.0, min(1.0, stability))
    #   e) Trade-count component — at least 2x min_trading_days
    trade_component = min(1.0, trades / max(1.0, min_days * 3))
    #   f) Win-rate — light bonus only
    wr_component = 0.5
    if isinstance(win_rate, (int, float)):
        wr_component = max(0.0, min(1.0, win_rate / 100.0 if win_rate > 1 else win_rate))

    weights = {
        "pf": 0.30,
        "dd": 0.25,
        "daily": 0.15,
        "stability": 0.15,
        "trades": 0.10,
        "win_rate": 0.05,
    }
    prob = (
        pf_component * weights["pf"] +
        dd_component * weights["dd"] +
        daily_component * weights["daily"] +
        stability_component * weights["stability"] +
        trade_component * weights["trades"] +
        wr_component * weights["win_rate"]
    )
    # Hard-gate: PF<1 or DD already over cap drives probability to near-zero.
    if isinstance(pf, (int, float)) and pf < 1.0:
        prob *= 0.1
    if isinstance(dd, (int, float)) and dd >= max_total:
        prob *= 0.05

    pass_probability = round(max(0.0, min(1.0, prob)) * 100.0, 1)

    # Expected days to pass
    if daily_ret > 0:
        expected_days = math.ceil(target / daily_ret)
    else:
        expected_days = None
    if expected_days is not None:
        expected_days = max(min_days, min(expected_days, 365))

    if pass_probability >= 70:
        risk_level = "low"
    elif pass_probability >= 40:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {
        "pass_probability": pass_probability,
        "expected_days_to_pass": expected_days,
        "hits_time_limit": bool(expected_days is not None and expected_days > time_limit),
        "risk_level": risk_level,
        "components": {
            "pf": round(pf_component, 3),
            "dd_headroom": round(dd_component, 3),
            "daily_cap_headroom": round(daily_component, 3),
            "stability": round(stability_component, 3),
            "trade_coverage": round(trade_component, 3),
            "win_rate": round(wr_component, 3),
        },
        "derived": {
            "daily_return_pct_used": round(daily_ret, 4),
            "est_worst_day_loss_pct": (
                round(dd / math.sqrt(max(1, int(trades / 5))), 2)
                if isinstance(dd, (int, float)) and trades else None
            ),
        },
    }


# ── 4. Safe risk calculator ──────────────────────────────────────────

def compute_safe_risk(
    stats: Dict[str, Any], rules: Dict[str, Any],
) -> Dict[str, Any]:
    """Recommend a max risk-per-trade % so the strategy's worst observed
    drawdown stays within the firm's daily + total caps with buffer.
    """
    dd = stats.get("dd_pct")
    trades = stats.get("trades") or 0
    max_total = rules.get("max_total_loss_pct") or 10.0
    max_daily = rules.get("max_daily_loss_pct") or 5.0

    # Baseline cap: 1% per trade
    candidates: List[float] = [1.0]
    # Scale by DD ratio (safety factor 0.5)
    if isinstance(dd, (int, float)) and dd > 0:
        dd_ratio = max_total / dd
        candidates.append(max(0.1, min(2.0, dd_ratio * 0.5)))
    # Daily cap: worst day ~= dd/sqrt(days); keep it below 60% of daily cap
    if isinstance(dd, (int, float)) and trades > 0:
        approx_days = max(1, int(trades / 5))
        est_daily_loss = dd / math.sqrt(approx_days)
        if est_daily_loss > 0:
            candidates.append(max(0.1, min(2.0, max_daily * 0.6 / est_daily_loss)))

    safe = round(min(candidates), 2)
    # Hard floor / ceiling so export templates are sensible
    safe = max(0.1, min(2.0, safe))

    return {
        "recommended_risk_per_trade": safe,
        "max_daily_loss_pct": max_daily,
        "max_total_loss_pct": max_total,
        "trailing_drawdown": bool(rules.get("trailing_drawdown")),
        "notes": (
            "Derived from strategy DD and firm caps. Reduce further in live "
            "trading if correlated positions are held."
        ),
    }


# ── 5. Persistence helpers ───────────────────────────────────────────

async def save_analysis(
    strategy_hash: str, firm_slug: str,
    validation: Dict[str, Any], simulation: Dict[str, Any],
) -> None:
    db = get_db()
    doc = {
        "strategy_hash": strategy_hash,
        "firm_slug": firm_slug,
        "status": validation.get("status"),
        "violations": validation.get("violations"),
        "warnings": validation.get("warnings"),
        "risk_adjustment_required": validation.get("risk_adjustment_required"),
        "pass_probability": simulation.get("pass_probability"),
        "expected_days_to_pass": simulation.get("expected_days_to_pass"),
        "hits_time_limit": simulation.get("hits_time_limit"),
        "risk_level": simulation.get("risk_level"),
        "components": simulation.get("components"),
        "derived": simulation.get("derived"),
        "analyzed_at": _now_iso(),
    }
    await db[PASS_ANALYSIS_COLL].update_one(
        {"strategy_hash": strategy_hash, "firm_slug": firm_slug},
        {"$set": doc}, upsert=True,
    )


async def save_risk_profile(
    strategy_hash: str, firm_slug: str, profile: Dict[str, Any],
) -> None:
    db = get_db()
    doc = {
        "strategy_hash": strategy_hash,
        "firm_slug": firm_slug,
        **profile,
        "updated_at": _now_iso(),
    }
    await db[RISK_PROFILE_COLL].update_one(
        {"strategy_hash": strategy_hash, "firm_slug": firm_slug},
        {"$set": doc}, upsert=True,
    )


# ── 6. Strategy stats builder ────────────────────────────────────────

async def build_strategy_stats(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Merge strategy_performance_history rollup + strategy_market_profile
    best into a flat stats dict understood by validator/simulator."""
    from engines.strategy_memory import get_explorer_rollup
    from engines.market_intelligence import get_profile as mi_get_profile

    rollups = await get_explorer_rollup(limit=1000)
    rollup = next((r for r in rollups if r["strategy_hash"] == strategy_hash), None)
    if not rollup:
        return None
    best_env = None
    try:
        mp = await mi_get_profile(strategy_hash)
        best_env = mp.get("best_environment")
    except Exception:
        pass
    return {
        "strategy_hash": strategy_hash,
        "name": rollup.get("name"),
        "type": rollup.get("type"),
        "pf": rollup.get("best_pf"),                 # use best over the rollup
        "avg_pf": rollup.get("avg_pf"),
        "dd_pct": rollup.get("best_dd"),             # conservative: smallest observed DD
        "trades": (
            int(rollup.get("avg_trades"))
            if isinstance(rollup.get("avg_trades"), (int, float))
            else None
        ),
        "win_rate": None,
        "stability_score": rollup.get("stability_score"),
        "environment_confidence": (best_env or {}).get("confidence"),
        "best_environment": best_env,
    }


# ── 7. End-to-end per-strategy analysis ─────────────────────────────

async def analyze_strategy(
    strategy_hash: str, firm_slug: str = DEFAULT_FIRM,
) -> Dict[str, Any]:
    rules = await get_normalized_rules(firm_slug, require_approved=True)
    if not rules:
        # Distinguish unknown firm vs un-approved firm.
        raw = await get_normalized_rules(firm_slug, require_approved=False)
        if not raw:
            raise ValueError(f"unknown firm_slug: {firm_slug}")
        raise PermissionError("rules_not_verified")
    stats = await build_strategy_stats(strategy_hash)
    if not stats:
        raise ValueError(f"no history for strategy_hash: {strategy_hash}")
    validation = validate_strategy_against_firm(stats, rules)
    simulation = simulate_challenge(stats, rules)
    risk_profile = compute_safe_risk(stats, rules)
    await save_analysis(strategy_hash, firm_slug, validation, simulation)
    await save_risk_profile(strategy_hash, firm_slug, risk_profile)
    return {
        "strategy_hash": strategy_hash,
        "firm_slug": firm_slug,
        "stats_used": stats,
        "rules": rules,
        "validation": validation,
        "simulation": simulation,
        "risk_profile": risk_profile,
    }


async def get_saved_analysis(
    strategy_hash: str, firm_slug: str = DEFAULT_FIRM,
) -> Optional[Dict[str, Any]]:
    db = get_db()
    analysis = await db[PASS_ANALYSIS_COLL].find_one(
        {"strategy_hash": strategy_hash, "firm_slug": firm_slug}, {"_id": 0},
    )
    if not analysis:
        return None
    risk = await db[RISK_PROFILE_COLL].find_one(
        {"strategy_hash": strategy_hash, "firm_slug": firm_slug}, {"_id": 0},
    )
    return {"analysis": analysis, "risk_profile": risk}


async def get_analyses_map(
    hashes: List[str], firm_slug: str = DEFAULT_FIRM,
) -> Dict[str, Dict[str, Any]]:
    """Bulk {hash -> {status, pass_probability, safe_risk}} — fed into
    the Explorer table."""
    if not hashes:
        return {}
    db = get_db()
    out: Dict[str, Dict[str, Any]] = {}
    async for d in db[PASS_ANALYSIS_COLL].find(
        {"firm_slug": firm_slug, "strategy_hash": {"$in": list(set(hashes))}},
        {"_id": 0, "strategy_hash": 1, "status": 1, "pass_probability": 1, "risk_level": 1},
    ):
        out[d["strategy_hash"]] = {
            "status": d.get("status"),
            "pass_probability": d.get("pass_probability"),
            "risk_level": d.get("risk_level"),
        }
    async for d in db[RISK_PROFILE_COLL].find(
        {"firm_slug": firm_slug, "strategy_hash": {"$in": list(set(hashes))}},
        {"_id": 0, "strategy_hash": 1, "recommended_risk_per_trade": 1},
    ):
        e = out.setdefault(d["strategy_hash"], {})
        e["recommended_risk_per_trade"] = d.get("recommended_risk_per_trade")
    return out


# ── 8. Batch analysis ───────────────────────────────────────────────

async def batch_analyze(
    *, firm_slug: str = DEFAULT_FIRM, limit: int = 50,
    min_runs: int = 1, force: bool = False,
) -> Dict[str, Any]:
    from engines.strategy_memory import get_explorer_rollup
    # Silently short-circuit if the firm isn't approved yet.
    if not await is_firm_approved(firm_slug):
        return {
            "status": "skipped_unverified",
            "firm_slug": firm_slug,
            "considered": 0, "analyzed": 0, "skipped": 0, "errors": [],
            "results": [],
            "reason": "rules_not_verified",
        }
    rollups = await get_explorer_rollup(min_runs=min_runs, limit=limit)
    processed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    skipped = 0
    db = get_db()
    for r in rollups:
        h = r["strategy_hash"]
        if not force:
            existing = await db[PASS_ANALYSIS_COLL].find_one(
                {"strategy_hash": h, "firm_slug": firm_slug}, {"_id": 0, "analyzed_at": 1},
            )
            if existing:
                skipped += 1
                continue
        try:
            result = await analyze_strategy(h, firm_slug=firm_slug)
            processed.append({
                "strategy_hash": h,
                "name": r.get("name"),
                "status": result["validation"]["status"],
                "pass_probability": result["simulation"]["pass_probability"],
                "safe_risk": result["risk_profile"]["recommended_risk_per_trade"],
            })
        except Exception as e:
            logger.exception("batch_analyze failed for %s", h)
            errors.append({"strategy_hash": h, "error": str(e)[:200]})
    return {
        "status": "ok",
        "firm_slug": firm_slug,
        "considered": len(rollups),
        "analyzed": len(processed),
        "skipped": skipped,
        "errors": errors,
        "results": processed,
    }
