"""
Prop Firm Rule Engine — Versioned, DB-backed, dynamic rules (Phase 2).

Stores challenge rules in MongoDB with:
  - Structured schema supporting multiple rule types
  - Version tracking with changelog
  - Confidence scoring and manual override
  - Dynamic loading for the simulator (no hardcoded presets)

Rule Types:
  - daily_dd:        equity-based or balance-based max daily drawdown
  - total_dd:        type ∈ {static, trailing_balance, trailing_equity}
                     (legacy "trailing" is normalized to "trailing_equity"
                     inside the simulator via rule_enforcement.normalize_dd_type)
  - consistency:     min trading days, min lots per day (structure only)
  - restrictions:    news blackout, overnight hold limits (structure only)
  - position_sizing: Phase 2 — {enabled, max_lot_per_trade, max_total_exposure}

Each rule set is a complete firm config that the simulator can consume directly.
"""

import logging
from datetime import datetime, timezone
from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "challenge_rules"

# ═══════════════════════════════════════════════════════
# Seed Data — initial firm configs (migrated from hardcoded presets)
# ═══════════════════════════════════════════════════════

SEED_RULES = [
    {
        "firm_slug": "ftmo",
        "firm_name": "FTMO",
        "phase": "Challenge",
        "version": 1,
        "initial_balance": 100000,
        "rules": {
            "daily_dd": {
                "enabled": True,
                "type": "equity",
                "max_pct": 5.0,
                "description": "Max 5% daily drawdown based on equity (including floating PnL)",
            },
            "total_dd": {
                "enabled": True,
                "type": "static",
                "max_pct": 10.0,
                "description": "Max 10% total drawdown from initial balance",
            },
            "profit_target": {
                "enabled": True,
                "target_pct": 10.0,
                "description": "10% profit target to pass the challenge",
            },
            "min_trading_days": {
                "enabled": True,
                "days": 4,
                "description": "Minimum 4 calendar days with at least 1 trade",
            },
            "time_limit": {
                "enabled": True,
                "calendar_days": 30,
                "description": "Must pass within 30 calendar days",
            },
            "consistency": {
                "enabled": False,
                "min_lots_per_day": None,
                "max_daily_profit_pct": None,
                "description": "No consistency rule for FTMO Challenge",
            },
            "restrictions": {
                "news_blackout_minutes": None,
                "max_overnight_lots": None,
                "weekend_hold_allowed": True,
                "description": "No specific restrictions for FTMO Challenge",
            },
            "position_sizing": {
                "enabled": True,
                "max_lot_per_trade": 20.0,
                "max_total_exposure": 30.0,
                "description": "Max 20 lots per trade, 30 lots aggregate exposure (Phase 2)",
            },
            "scaling_rule": {
                "enabled": False,
                "type": "risk_reduction",
                "threshold_dd_pct": 5.0,
                "risk_multiplier": 0.5,
                "description": "OPTIONAL safety: halve risk once cumulative DD >= 5%",
            },
        },
        "confidence_score": 95,
        "confidence_notes": "Rules verified from FTMO official website Jan 2026",
        "validated": True,
        "validated_at": "2026-01-15T00:00:00+00:00",
        "manual_override": False,
        "changelog": [
            {"version": 1, "date": "2026-01-15T00:00:00+00:00", "changes": "Initial rule set from FTMO official terms"},
        ],
    },
    {
        "firm_slug": "fundednext",
        "firm_name": "FundedNext",
        "phase": "Challenge Phase 1",
        "version": 1,
        "initial_balance": 100000,
        "rules": {
            "daily_dd": {
                "enabled": True,
                "type": "equity",
                "max_pct": 5.0,
                "description": "Max 5% daily drawdown based on equity",
            },
            "total_dd": {
                "enabled": True,
                "type": "static",
                "max_pct": 10.0,
                "description": "Max 10% total drawdown from initial balance",
            },
            "profit_target": {
                "enabled": True,
                "target_pct": 10.0,
                "description": "10% profit target",
            },
            "min_trading_days": {
                "enabled": True,
                "days": 5,
                "description": "Minimum 5 trading days",
            },
            "time_limit": {
                "enabled": False,
                "calendar_days": 0,
                "description": "No time limit",
            },
            "consistency": {
                "enabled": False,
                "min_lots_per_day": None,
                "max_daily_profit_pct": None,
                "description": "No consistency rule",
            },
            "restrictions": {
                "news_blackout_minutes": None,
                "max_overnight_lots": None,
                "weekend_hold_allowed": True,
                "description": "No specific restrictions",
            },
            "position_sizing": {
                "enabled": True,
                "max_lot_per_trade": 20.0,
                "max_total_exposure": 30.0,
                "description": "Max 20 lots per trade, 30 lots aggregate exposure (Phase 2)",
            },
            "scaling_rule": {
                "enabled": False,
                "type": "risk_reduction",
                "threshold_dd_pct": 5.0,
                "risk_multiplier": 0.5,
                "description": "OPTIONAL safety: halve risk once cumulative DD >= 5%",
            },
        },
        "confidence_score": 90,
        "confidence_notes": "Rules verified from FundedNext website Jan 2026",
        "validated": True,
        "validated_at": "2026-01-15T00:00:00+00:00",
        "manual_override": False,
        "changelog": [
            {"version": 1, "date": "2026-01-15T00:00:00+00:00", "changes": "Initial rule set"},
        ],
    },
    {
        "firm_slug": "pipfarm",
        "firm_name": "PipFarm",
        "phase": "Evaluation",
        "version": 1,
        "initial_balance": 100000,
        "rules": {
            "daily_dd": {
                "enabled": True,
                "type": "equity",
                "max_pct": 4.0,
                "description": "Max 4% daily drawdown based on equity",
            },
            "total_dd": {
                "enabled": True,
                "type": "trailing_equity",
                "max_pct": 8.0,
                "description": "Max 8% trailing drawdown from peak floating equity",
            },
            "profit_target": {
                "enabled": True,
                "target_pct": 12.0,
                "description": "12% profit target",
            },
            "min_trading_days": {
                "enabled": True,
                "days": 3,
                "description": "Minimum 3 trading days",
            },
            "time_limit": {
                "enabled": False,
                "calendar_days": 0,
                "description": "No time limit",
            },
            "consistency": {
                "enabled": False,
                "min_lots_per_day": None,
                "max_daily_profit_pct": None,
                "description": "No consistency rule for PipFarm evaluation",
            },
            "restrictions": {
                "news_blackout_minutes": None,
                "max_overnight_lots": None,
                "weekend_hold_allowed": True,
                "description": "No specific restrictions",
            },
            "position_sizing": {
                "enabled": True,
                "max_lot_per_trade": 10.0,
                "max_total_exposure": 15.0,
                "description": "Max 10 lots per trade, 15 lots aggregate exposure (Phase 2, stricter)",
            },
            "scaling_rule": {
                "enabled": False,
                "type": "risk_reduction",
                "threshold_dd_pct": 4.0,
                "risk_multiplier": 0.5,
                "description": "OPTIONAL safety: halve risk once cumulative DD >= 4%",
            },
        },
        "confidence_score": 85,
        "confidence_notes": "Rules from PipFarm evaluation terms. Trailing DD confirmed.",
        "validated": True,
        "validated_at": "2026-01-15T00:00:00+00:00",
        "manual_override": False,
        "changelog": [
            {"version": 1, "date": "2026-01-15T00:00:00+00:00", "changes": "Initial rule set with trailing drawdown"},
        ],
    },
]


# ═══════════════════════════════════════════════════════
# DB Operations
# ═══════════════════════════════════════════════════════

async def _backfill_phase2_fields():
    """
    Idempotently upgrade pre-seeded rule docs to the Phase 2 schema.

    Only ADDITIVE: adds `rules.position_sizing` when missing. Does NOT rewrite
    the legacy `total_dd.type == "trailing"` value — the simulator's
    `rule_enforcement.normalize_dd_type` maps it to `"trailing_equity"` at
    runtime, preserving backward compatibility for callers that read the raw
    stored string.

    Safe to run on every startup: only updates docs missing the field.
    """
    db = get_db()
    for seed in SEED_RULES:
        slug = seed["firm_slug"]
        doc = await db[COLLECTION].find_one({"firm_slug": slug})
        if not doc:
            continue

        rules = doc.get("rules", {}) or {}
        if "position_sizing" in rules:
            continue
        seed_ps = seed.get("rules", {}).get("position_sizing")
        if not seed_ps:
            continue

        await db[COLLECTION].update_one(
            {"firm_slug": slug},
            {"$set": {"rules.position_sizing": seed_ps}},
        )
        logger.info(f"[Phase 2 backfill] added position_sizing to {slug}")


async def seed_rules_if_empty():
    """Seed initial firm rules into DB if the collection is empty.

    Also runs an idempotent Phase 2 field backfill on existing rows so
    docs seeded before Phase 2 gain the new fields without a migration.
    """
    db = get_db()
    count = await db[COLLECTION].count_documents({})
    if count > 0:
        await _backfill_phase2_fields()
        return {"seeded": False, "existing": count}
    docs = []
    now = datetime.now(timezone.utc).isoformat()
    for rule in SEED_RULES:
        doc = {**rule, "created_at": now, "updated_at": now}
        docs.append(doc)
    await db[COLLECTION].insert_many(docs)
    await db[COLLECTION].create_index("firm_slug", unique=True)
    logger.info(f"Seeded {len(docs)} firm rule sets into {COLLECTION}")
    return {"seeded": True, "count": len(docs)}


async def get_all_rules() -> list:
    """Return all rule sets from DB."""
    db = get_db()
    await seed_rules_if_empty()
    cursor = db[COLLECTION].find({}, {"_id": 0})
    results = []
    async for doc in cursor:
        results.append(doc)
    return results


async def get_rules_by_slug(firm_slug: str) -> dict:
    """Fetch a single firm's rules by slug. Returns None if not found."""
    db = get_db()
    await seed_rules_if_empty()
    doc = await db[COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})
    return doc


async def rules_to_sim_config(rule_doc: dict) -> dict:
    """
    Convert a stored rule document into the flat config dict
    the simulator expects. This is the bridge between the
    structured rule schema and the simulator's input format.

    CORE rules (always enforced): daily_dd, total_dd, profit_target, reset_time.
    OPTIONAL rules (toggle-based, enforced only when `enabled`):
      - min_trading_days
      - consistency (consistency_rule)
      - news_restriction (STORE ONLY — no engine enforcement yet)
      - position_sizing (lot_size_limit)
      - scaling_rule (risk reduction when cumulative DD >= threshold)
    """
    rules = rule_doc.get("rules", {})
    daily = rules.get("daily_dd", {})
    total = rules.get("total_dd", {})
    profit = rules.get("profit_target", {})
    min_days = rules.get("min_trading_days", {})
    time_lim = rules.get("time_limit", {})

    return {
        "name": rule_doc.get("firm_name", "Custom"),
        "phase": rule_doc.get("phase", ""),
        "initial_balance": rule_doc.get("initial_balance", 100000),
        # CORE
        "profit_target_pct": profit.get("target_pct", 10.0) if profit.get("enabled", True) else 0,
        "max_daily_dd_pct": daily.get("max_pct", 5.0) if daily.get("enabled", True) else 100.0,
        "max_total_dd_pct": total.get("max_pct", 10.0) if total.get("enabled", True) else 100.0,
        "drawdown_type": total.get("type", "static") if total.get("enabled", True) else "static",
        "daily_dd_basis": daily.get("type", "equity"),
        # CORE — read-only broker day reset anchor (NY 17:00, matches FTMO/
        # FundedNext/MFF/E8/TopStep). Surfaced so the UI can display it.
        "reset_time": {"timezone": "America/New_York", "hour": 17},
        # OPTIONAL — enforced only when .enabled
        "min_trading_days": min_days.get("days", 0) if min_days.get("enabled") else 0,
        "time_limit_days": time_lim.get("calendar_days", 0) if time_lim.get("enabled") else 0,
        "consistency": _extract_consistency(rules),
        "position_sizing": _extract_position_sizing(rules),
        "scaling_rule": _extract_scaling_rule(rules),
        "news_restriction": _extract_news_restriction(rules),
        # P6 audit fix #5 — turn the execution engine's intrabar
        # worst-case SL-before-TP flip on by default for every
        # prop-firm eval. The flip is a safety net that only fires
        # when BOTH SL and TP sit inside the exit candle, so cost is
        # zero for cleanly-resolving trades.
        "execution": {"enabled": True, "intrabar_mode": "worst_case"},
    }


def _extract_consistency(rules: dict) -> dict:
    """Extract consistency rule config from structured rules."""
    con = rules.get("consistency", {})
    if not con.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "max_daily_profit_pct": con.get("max_daily_profit_pct"),
    }


def _extract_position_sizing(rules: dict) -> dict:
    """Extract position sizing constraints from structured rules."""
    pos = rules.get("position_sizing", {})
    if not pos.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "max_lot_per_trade": pos.get("max_lot_per_trade"),
        "max_total_exposure": pos.get("max_total_exposure"),
    }


def _extract_scaling_rule(rules: dict) -> dict:
    """Extract optional DD-triggered risk-reduction rule.
    When enabled, simulator halves (or multiplies by risk_multiplier)
    subsequent trade PnL once cumulative DD crosses threshold_dd_pct.
    When disabled, returns a stub so the simulator ignores it."""
    sc = rules.get("scaling_rule", {})
    if not sc.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "type": sc.get("type", "risk_reduction"),
        "threshold_dd_pct": float(sc.get("threshold_dd_pct") or 5.0),
        "risk_multiplier": float(sc.get("risk_multiplier") or 0.5),
    }


def _extract_news_restriction(rules: dict) -> dict:
    """Extract news-restriction rule. STORE ONLY — simulator does NOT
    enforce this yet (no external calendar integration). Kept in the
    config so the UI can display the toggle + value."""
    # Two possible locations for backward compat: the new `news_restriction`
    # subsection OR the legacy `restrictions.news_blackout_minutes`.
    news = rules.get("news_restriction") or {}
    if news.get("enabled"):
        return {
            "enabled": True,
            "enforced": False,   # explicit flag: engine ignores it
            "blackout_minutes": news.get("blackout_minutes"),
        }
    # Legacy path — still return disabled unless the user explicitly
    # enables via the new subsection.
    return {"enabled": False, "enforced": False}


async def create_rule(rule_data: dict) -> dict:
    """Create a new firm rule set. Returns the created doc."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    slug = rule_data.get("firm_slug", "").lower().replace(" ", "_")
    if not slug:
        raise ValueError("firm_slug is required")

    existing = await db[COLLECTION].find_one({"firm_slug": slug})
    if existing:
        raise ValueError(f"Rule set for '{slug}' already exists. Use update instead.")

    doc = {
        "firm_slug": slug,
        "firm_name": rule_data.get("firm_name", slug.upper()),
        "phase": rule_data.get("phase", "Challenge"),
        "version": 1,
        "initial_balance": rule_data.get("initial_balance", 100000),
        "rules": rule_data.get("rules", {}),
        "confidence_score": rule_data.get("confidence_score", 50),
        "confidence_notes": rule_data.get("confidence_notes", ""),
        "validated": rule_data.get("validated", False),
        "validated_at": now if rule_data.get("validated") else None,
        "manual_override": rule_data.get("manual_override", False),
        "changelog": [
            {"version": 1, "date": now, "changes": "Initial creation"},
        ],
        "created_at": now,
        "updated_at": now,
    }
    await db[COLLECTION].insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_rule(firm_slug: str, updates: dict, change_note: str = "") -> dict:
    """
    Update a firm's rules. Increments version, appends to changelog.
    Returns the updated doc.
    """
    db = get_db()
    existing = await db[COLLECTION].find_one({"firm_slug": firm_slug})
    if not existing:
        raise ValueError(f"Rule set '{firm_slug}' not found")

    now = datetime.now(timezone.utc).isoformat()
    new_version = existing.get("version", 0) + 1

    set_fields = {"updated_at": now, "version": new_version}

    if "rules" in updates:
        set_fields["rules"] = updates["rules"]
    if "initial_balance" in updates:
        set_fields["initial_balance"] = updates["initial_balance"]
    if "phase" in updates:
        set_fields["phase"] = updates["phase"]
    if "firm_name" in updates:
        set_fields["firm_name"] = updates["firm_name"]
    if "confidence_score" in updates:
        set_fields["confidence_score"] = updates["confidence_score"]
    if "confidence_notes" in updates:
        set_fields["confidence_notes"] = updates["confidence_notes"]
    if "validated" in updates:
        set_fields["validated"] = updates["validated"]
        if updates["validated"]:
            set_fields["validated_at"] = now
    if "manual_override" in updates:
        set_fields["manual_override"] = updates["manual_override"]

    changelog_entry = {
        "version": new_version,
        "date": now,
        "changes": change_note or "Rule updated",
    }

    await db[COLLECTION].update_one(
        {"firm_slug": firm_slug},
        {"$set": set_fields, "$push": {"changelog": changelog_entry}},
    )

    updated = await db[COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})
    return updated


async def delete_rule(firm_slug: str) -> bool:
    """Delete a firm's rule set. Returns True if deleted."""
    db = get_db()
    result = await db[COLLECTION].delete_one({"firm_slug": firm_slug})
    return result.deleted_count > 0


async def validate_rule(firm_slug: str, confidence_score: int, notes: str = "") -> dict:
    """Mark a rule set as validated with a confidence score."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    result = await db[COLLECTION].update_one(
        {"firm_slug": firm_slug},
        {"$set": {
            "validated": True,
            "validated_at": now,
            "confidence_score": max(0, min(100, confidence_score)),
            "confidence_notes": notes,
            "updated_at": now,
        }},
    )
    if result.matched_count == 0:
        raise ValueError(f"Rule set '{firm_slug}' not found")
    return await db[COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})


async def override_rule(firm_slug: str, override: bool, note: str = "") -> dict:
    """Set or clear manual override on a rule set."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    new_version = None

    existing = await db[COLLECTION].find_one({"firm_slug": firm_slug})
    if not existing:
        raise ValueError(f"Rule set '{firm_slug}' not found")

    new_version = existing.get("version", 0) + 1
    changelog_entry = {
        "version": new_version,
        "date": now,
        "changes": f"Manual override {'enabled' if override else 'disabled'}: {note}" if note else f"Manual override {'enabled' if override else 'disabled'}",
    }

    await db[COLLECTION].update_one(
        {"firm_slug": firm_slug},
        {
            "$set": {
                "manual_override": override,
                "version": new_version,
                "updated_at": now,
            },
            "$push": {"changelog": changelog_entry},
        },
    )
    return await db[COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})
