"""Phase 28-C — IR → cAlgo C# transpiler orchestration.

The transpiler is intentionally narrow:
    1. Validate the IR fully via Pydantic (re-uses Phase 28-A schema).
    2. Verify v1 coverage — every operator / indicator / exit kind
       must be supported. Honest refusal on anything outside scope.
    3. Walk the IR; render each piece via ``ir_emitter``.
    4. Assemble the scaffold into a single ``.cs`` source string.
    5. Stamp execution lineage metadata (IR_VERSION, TRANSPILER_VERSION,
       STRATEGY_HASH, GENERATED_AT, HTF_PARITY_MODE, PARITY_STATUS,
       PARITY_FIXTURES_PASSED).

The transpiler NEVER invents semantics. Every C# token traces back to
an IR operator + a deterministic emitter.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cbot_engine import ir_emitter as E
from cbot_engine import ir_templates as T
from engines.strategy_ir import StrategyIR, validate_ir


# Re-export so callers can catch transpiler errors without importing
# the emitter directly.
UnsupportedIROperatorError = E.UnsupportedIROperatorError


def _strategy_hash(ir_dict: dict) -> str:
    """Deterministic SHA-1 of the canonical JSON of the IR. Same IR
    → same hash regardless of dict insertion order."""
    return hashlib.sha1(
        json.dumps(ir_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_BOT_NAME_RE = re.compile(r"[^A-Za-z0-9]")


def _bot_name(ir_dict: dict, hash_hex: str) -> str:
    """Stable C# class name derived from the IR. Falls back to the
    hash prefix when metadata is sparse."""
    md = ir_dict.get("metadata") or {}
    raw = md.get("name") or md.get("mutation_type") or "IRBot"
    sanitised = _BOT_NAME_RE.sub("", str(raw))
    if not sanitised or not sanitised[0].isalpha():
        sanitised = "IRBot" + sanitised
    return f"{sanitised}_{hash_hex[:8]}"


def transpile_ir_to_csharp(
    ir: Any,
    *,
    parity_status: str = "PENDING",
    parity_fixtures_passed: Optional[int] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a validated Strategy-IR to a complete cAlgo C# cBot.

    Args:
        ir: ``StrategyIR`` instance, dict matching the schema, or
            anything that schema-validates.
        parity_status: stamped into the generated cBot's metadata
            comment block. The caller (typically a trust-gate pipeline)
            is responsible for running parity validation BEFORE setting
            this to ``"PASSED"``. Defaults to ``"PENDING"`` so a raw
            transpile is never mistaken for a parity-cleared artefact.
        parity_fixtures_passed: integer count to stamp alongside
            parity_status. ``None`` renders as ``"N/A"``.
        generated_at: ISO-8601 timestamp override (for deterministic
            test fixtures). Defaults to current UTC time.

    Returns:
        ``{"bot_name", "filename", "csharp", "strategy_hash",
          "transpiler_version", "ir_version", "htf_parity_mode",
          "metadata": {...}}``

    Raises:
        UnsupportedIROperatorError when the IR contains anything
        outside the v1 transpiler vocabulary (operators, indicators,
        exit kinds, HTF mappings). Honest refusal — never silently
        emit a placeholder.
    """
    # ── Schema validation (reuses Phase 28-A guarantees) ─────────
    if isinstance(ir, StrategyIR):
        ir_obj = ir
        ir_dict = ir.model_dump(mode="json")
    else:
        ir_obj = validate_ir(ir if isinstance(ir, dict) else dict(ir))
        ir_dict = ir_obj.model_dump(mode="json")

    # ── v1 coverage check (loud refusal on unsupported) ──────────
    ops_used, ind_kinds_used, sl_kinds, tp_kinds = E.collect_operators_and_indicators(ir_dict)
    unsupported_ops = ops_used - E.SUPPORTED_OPERATORS
    unsupported_inds = ind_kinds_used - E.SUPPORTED_INDICATORS
    unsupported_sl = sl_kinds - E.SUPPORTED_SL_KINDS
    unsupported_tp = tp_kinds - E.SUPPORTED_TP_KINDS
    if unsupported_ops or unsupported_inds or unsupported_sl or unsupported_tp:
        raise UnsupportedIROperatorError(
            "IR contains semantics outside v1 transpiler vocabulary. "
            f"operators={sorted(unsupported_ops)} "
            f"indicators={sorted(unsupported_inds)} "
            f"sl_kinds={sorted(unsupported_sl)} "
            f"tp_kinds={sorted(unsupported_tp)}"
        )

    # ── Identity ─────────────────────────────────────────────────
    hash_hex = _strategy_hash(ir_dict)
    bot_name = _bot_name(ir_dict, hash_hex)
    md = ir_dict.get("metadata") or {}
    pair = md.get("pair", "UNKNOWN")
    timeframe = md.get("timeframe", "UNKNOWN")
    mutation_type = md.get("mutation_type", "unknown")
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    # ── Indicator declarations + init ─────────────────────────────
    indicators_list = ir_dict.get("indicators") or []
    indicators_by_id = {i["id"]: i for i in indicators_list}
    htf_param_map: Dict[str, str] = {}
    field_decls, htf_field_decls, init_body = E.emit_indicator_fields_and_init(
        indicators_list, htf_param_map,
    )

    # ── Predicate emission ────────────────────────────────────────
    helpers_used: set = set()
    entry_long_expr = E._emit_predicate(
        ir_dict["entry_long"], indicators_by_id, helpers_used,
    )
    entry_short_expr = E._emit_predicate(
        ir_dict["entry_short"], indicators_by_id, helpers_used,
    )

    # ── Exit + gates ──────────────────────────────────────────────
    sl_pips_expr, tp_pips_expr, indicator_exits, force_flat_body = E.emit_exit_logic(
        ir_dict, indicators_by_id, helpers_used,
    )
    session_body = E.emit_session_body(ir_dict, helpers_used)
    volatility_body = E.emit_volatility_body(ir_dict, indicators_by_id, helpers_used)

    helpers_block = E.emit_helpers(helpers_used)
    parameters_block = E.emit_parameters(ir_dict)

    # ── HTF parity mode: APPROXIMATE if any HTF_EMA present ─────
    htf_parity_mode = "APPROXIMATE" if "HTF_EMA" in ind_kinds_used else "N/A"

    # ── Assemble ─────────────────────────────────────────────────
    csharp = T.SCAFFOLD.format(
        ir_version=ir_dict.get("ir_version", 1),
        transpiler_version=T.TRANSPILER_VERSION,
        strategy_hash=hash_hex,
        generated_at=generated_at,
        htf_parity_mode=htf_parity_mode,
        parity_status=parity_status,
        parity_fixtures_passed=(parity_fixtures_passed
                                if parity_fixtures_passed is not None
                                else "N/A"),
        mutation_type=mutation_type,
        pair=pair,
        timeframe=timeframe,
        bot_name=bot_name,
        parameters=parameters_block.rstrip(),
        indicator_fields=field_decls or "        // (no indicators)",
        htf_fields=htf_field_decls or "        // (no HTF resources)",
        indicator_init=init_body or "            // (no indicator init)",
        force_flat_check=force_flat_body or "            // (no force-flat)",
        indicator_exits=indicator_exits or "            // (no bar-checked exits)",
        entry_long_expr=entry_long_expr,
        entry_short_expr=entry_short_expr,
        session_body=session_body,
        volatility_body=volatility_body,
        sl_pips_expr=sl_pips_expr,
        tp_pips_expr=tp_pips_expr,
        helpers=helpers_block,
    )

    return {
        "bot_name": bot_name,
        "filename": f"{bot_name}.cs",
        "csharp": csharp,
        "strategy_hash": hash_hex,
        "transpiler_version": T.TRANSPILER_VERSION,
        "ir_version": ir_dict.get("ir_version", 1),
        "htf_parity_mode": htf_parity_mode,
        "metadata": {
            "pair": pair,
            "timeframe": timeframe,
            "mutation_type": mutation_type,
            "generated_at": generated_at,
            "parity_status": parity_status,
            "parity_fixtures_passed": parity_fixtures_passed,
            "operators_used": sorted(ops_used),
            "indicator_kinds_used": sorted(ind_kinds_used),
            "sl_kind": sorted(sl_kinds)[0] if sl_kinds else None,
            "tp_kind": sorted(tp_kinds)[0] if tp_kinds else None,
        },
    }


__all__ = [
    "transpile_ir_to_csharp",
    "UnsupportedIROperatorError",
]
