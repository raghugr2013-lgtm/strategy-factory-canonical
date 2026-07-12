"""POST /api/latent/cbot-log-diagnostic — read-only forensic parser.

Auth-gated. Read-only. Pure function (no I/O, no Mongo).

Operator-side closure for the long-standing "compiled but non-trading
cBot" issue (audit doc §2.2 / §7.1). Accepts a captured cBot Print
log blob and returns a structured verdict: which gate is killing the
bot, recommended operator action, and verbatim sample lines.

Use this within minutes of a fleet deployment to confirm bots are
actually firing trades — or to identify the dominant gate that needs
relaxation before re-deploying.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_utils import get_current_user
from engines import cbot_log_diagnostic as DIAG

router = APIRouter()

# Hard ceiling on log size to keep the endpoint pure and bounded.
# 10 MB is generous — a full week of cTrader Print output for a single
# bot at LogVerbosity=2 is well under that.
_MAX_LOG_BYTES = 10 * 1024 * 1024


class _LogPayload(BaseModel):
    log: str = Field(
        ...,
        description=(
            "Captured cBot Print(...) output. Accepts cTrader Cloud "
            "stdout, exported log file content, or local backtest "
            "Print blob. Must contain the scaffold's [GATE] reason=… "
            "markers for the diagnostic to be useful."
        ),
    )
    max_sample_lines_per_reason: int = Field(
        5, ge=1, le=50,
        description="Per-reason verbatim sample line cap (1-50).",
    )


@router.post("/latent/cbot-log-diagnostic")
async def diagnose_cbot_log(
    payload: _LogPayload,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    log = payload.log or ""
    if len(log.encode("utf-8")) > _MAX_LOG_BYTES:
        raise HTTPException(status_code=413, detail={
            "error":   "log_too_large",
            "limit_bytes": _MAX_LOG_BYTES,
            "received_bytes": len(log.encode("utf-8")),
            "remediation": (
                "Truncate the log to the most recent 10 MB or split "
                "into multiple POSTs."
            ),
        })
    report = DIAG.parse_log(
        log, max_sample_lines_per_reason=payload.max_sample_lines_per_reason,
    )
    return {
        "endpoint":             "/api/latent/cbot-log-diagnostic",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "known_reasons":        list(DIAG.known_reasons()),
        **report,
    }
