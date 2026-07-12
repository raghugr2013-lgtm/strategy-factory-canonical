"""
Phase 12 — cBot Reliability Pipeline with Auto-Fix Loop (Phase 12.5).

Single entry: `build_reliable_cbot(strategy_profile, safety_rules)` runs
  Code Generator → Safety Injector → Compile Validator
  → (if error) deterministic auto-fix → recompile  ×  up to MAX_RETRIES.

Stop conditions:
    * compile_status == "success" → return immediately
    * compile_status == "warning" → return (warnings are non-blocking)
    * retries exhausted           → return the last result with status=error

Output contract:
    {
      "code": str,
      "compile_status": "success|warning|error",
      "attempts": int,
      "errors": [ {code, message, detail}, ... ],
      "warnings": [ {code, message, detail}, ... ],
      "bot_name": str,
      "indicators_used": [..],
      "safety": {..},
      "fix_log": [ {attempt, rules_applied: [..]}, ... ],
      "placeholders_filled": [..]
    }
"""
from __future__ import annotations

import logging

from engines.code_generator import generate_code
from engines.safety_injector import inject_safety
from engines.compile_engine import validate as compile_validate
from engines.cbot_autofix import apply_fixes

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def build_reliable_cbot(
    strategy_profile: dict,
    safety_rules: dict | None = None,
) -> dict:
    """Run Generate → Inject → Compile loop with deterministic auto-fixing."""
    safety_rules = safety_rules or {}

    # ── Phase 1: generate + inject safety ──
    gen = generate_code(strategy_profile)
    code = gen["code"]

    inj = inject_safety(
        code,
        bot_name=gen["bot_name"],
        risk_percent=float(safety_rules.get("risk_percent", 1.0)),
        max_daily_loss_pct=float(safety_rules.get("max_daily_loss_pct", 3.0)),
        max_spread_pips=(
            None if safety_rules.get("max_spread_pips") in (None, False)
            else float(safety_rules.get("max_spread_pips"))
        ),
    )
    code = inj["code"]

    # ── Phase 2: compile + auto-fix loop ──
    fix_ctx = {
        "pair": strategy_profile.get("pair"),
        "timeframe": strategy_profile.get("timeframe"),
        "style": strategy_profile.get("style")
                 or strategy_profile.get("strategy_type")
                 or "trend_following",
        "parameters": strategy_profile.get("parameters") or {},
        "indicators": strategy_profile.get("indicators") or {},
        "bot_name": gen["bot_name"],
    }

    fix_log: list[dict] = []
    attempt = 1
    report = compile_validate(code)

    while (report["compile_status"] == "error") and attempt <= MAX_RETRIES:
        new_code, notes = apply_fixes(
            code, report["errors"], report["warnings"], fix_ctx,
        )
        if new_code == code and not notes:
            # No rule could fix anything further — stop retrying.
            fix_log.append({"attempt": attempt, "rules_applied": [],
                             "note": "no matching rule — halting"})
            break
        code = new_code
        fix_log.append({"attempt": attempt, "rules_applied": notes})
        attempt += 1
        report = compile_validate(code)

    return {
        "code": code,
        "bot_name": gen["bot_name"],
        "indicators_used": gen["indicators_used"],
        "placeholders_filled": gen["placeholders_filled"],
        "safety": {
            "injections": inj["injections"],
            "config": inj["config"],
        },
        "compile_status": report["compile_status"],
        "attempts": attempt,
        "max_retries": MAX_RETRIES,
        "errors": report["errors"],
        "warnings": report["warnings"],
        "fix_log": fix_log,
    }
