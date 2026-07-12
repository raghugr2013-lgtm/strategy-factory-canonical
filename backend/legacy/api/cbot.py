from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from typing import Any, Optional

from cbot_engine.ir_transpiler import (
    UnsupportedIROperatorError, transpile_ir_to_csharp,
)

router = APIRouter()


class CbotRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    backtest_params: Optional[dict] = None
    sim_settings: Optional[dict] = None
    safety_rules: Optional[dict] = None
    indicators: Optional[dict] = None
    strategy_type: Optional[str] = None
    extraction: Optional[dict] = None
    # Phase 28-C — when present, the deterministic IR transpiler is
    # always used (operator decision #4 — IR is canonical, no mode
    # flags). The legacy LLM/stub generator is retained below as the
    # fallback for callers that haven't migrated.
    strategy_ir: Optional[Any] = None


@router.post("/generate-cbot")
async def generate_cbot(req: CbotRequest):
    # Phase 28-C dispatch — IR present → deterministic transpiler.
    if req.strategy_ir is not None:
        # ── Phase B.2 (soft) — parity sign-off lookup ──────────────
        # Compute the IR's strategy_hash first (deterministic) so we
        # can look up a sign-off without round-tripping through the
        # transpiler twice. The transpiler is pure and idempotent so
        # we just call it once with the resolved parity metadata.
        parity_status = "PENDING"
        parity_fixtures_passed = 0
        parity_warning: Optional[str] = None
        try:
            from engines import cbot_parity as _cp
            from cbot_engine.ir_transpiler import _strategy_hash  # type: ignore
            # Hash is derivable from the IR via the transpiler's
            # internal helper. Falling back gracefully if the helper
            # moves in a future Phase.
            try:
                # Schema-validate first so the hash is computed from
                # the same canonical dict the transpiler will hash.
                from engines.strategy_ir import StrategyIR
                ir_dict = (
                    req.strategy_ir.model_dump(mode="json")
                    if hasattr(req.strategy_ir, "model_dump")
                    else StrategyIR.model_validate(req.strategy_ir).model_dump(mode="json")
                )
                _hash = _strategy_hash(ir_dict)
            except Exception:
                _hash = None
            if _hash:
                signoff = await _cp.get_signoff(_hash)
                if _cp.is_passed(signoff):
                    parity_status = "PASSED"
                    parity_fixtures_passed = int(
                        (signoff or {}).get("fixtures_passed") or 0
                    )
                else:
                    parity_warning = (
                        f"parity sign-off missing or not passed for "
                        f"hash={_hash[:12]}…; ship at your own risk. "
                        f"POST /api/cbot-parity/{_hash}/sign-off to verify."
                    )
        except Exception:
            # Parity lookup is best-effort — never blocks the legacy
            # transpile path. Phase B.5 will promote this to a hard gate.
            pass

        try:
            out = transpile_ir_to_csharp(
                req.strategy_ir,
                parity_status=parity_status,
                parity_fixtures_passed=parity_fixtures_passed,
            )
        except UnsupportedIROperatorError as e:
            # Honest refusal — operator directive #7. The transpiler's
            # own v1 coverage check fires.
            raise HTTPException(
                status_code=422,
                detail={"error": "unsupported_ir_operator", "message": str(e)},
            )
        except ValidationError as e:
            # Honest refusal — Phase 28-A schema literal enum rejected
            # the IR before the transpiler ever saw it. Same refusal
            # category, different layer.
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_strategy_ir",
                          "message": "Strategy-IR failed schema validation.",
                          "errors": e.errors()[:5]},
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {
            "code": out["csharp"],
            "bot_name": out["bot_name"],
            "filename": out["filename"],
            "pair": out["metadata"]["pair"],
            "timeframe": out["metadata"]["timeframe"],
            "strategy_hash": out["strategy_hash"],
            "transpiler_version": out["transpiler_version"],
            "ir_version": out["ir_version"],
            "htf_parity_mode": out["htf_parity_mode"],
            "parity_status": out.get("parity_status") or parity_status,
            "parity_fixtures_passed": out.get("parity_fixtures_passed") or parity_fixtures_passed,
            "parity_warning": parity_warning,
            "metadata": out["metadata"],
            "source": "ir_transpiler",
        }
    # Legacy path — RETIRED (P0.1 institutional execution hardening).
    # Operator directive: deterministic OR fail; never deterministic OR
    # silently degrade. The legacy `generate_cbot_code` returned a
    # hard-coded SimpleBot stub regardless of `strategy_text`, which is
    # operationally unsafe. Calling /api/generate-cbot WITHOUT a
    # `strategy_ir` payload now fails loudly.
    raise HTTPException(
        status_code=410,
        detail={
            "error":   "legacy_cbot_generator_retired",
            "message": (
                "The legacy (no-IR) cBot generation path has been retired "
                "as of P0.1. Callers MUST supply a `strategy_ir` payload "
                "so the deterministic IR transpiler can render the cBot. "
                "Returning a stub bot silently is operationally unsafe and "
                "is no longer permitted."
            ),
            "remediation": (
                "Build the StrategyIR first (engines.strategy_ir_builders "
                "or engines.mutation_engine), then re-POST with "
                "strategy_ir set to the validated IR dict."
            ),
            "retired_at": "2026-05-22",
            "phase":      "P0.1",
        },
    )
