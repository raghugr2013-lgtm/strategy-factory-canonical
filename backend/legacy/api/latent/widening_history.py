"""GET /api/latent/widening-history — forensic activation audit.

Strictly observational, immutable historical view. Reconstructs every
governance widening event from `audit_log.latent_capability:override_diff`
and pairs each with the stage transition + 24h pre-window context.

Discipline:
  * No writes, no flag mutation, no scheduler interaction.
  * No automation authority of any kind.
  * Payload always carries `read_only=true`,
    `governance_authority=false`, `operator_authority="final"`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_utils import get_current_user
from engines import widening_history

router = APIRouter()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"`since` must be ISO-8601 (got {value!r}): {e}",
        )


@router.get("/latent/widening-history")
async def get_widening_history(
    _user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(
        default=widening_history.DEFAULT_LIMIT,
        ge=1,
        le=widening_history.MAX_LIMIT,
        description=(
            "Maximum number of widening (override_diff) rows to "
            f"return (newest first). Bounded at {widening_history.MAX_LIMIT}."
        ),
    ),
    since: Optional[str] = Query(
        default=None,
        description=(
            "ISO-8601 timestamp. When supplied, only events at-or-after "
            "this instant are returned. Omit to scan the full TTL window."
        ),
    ),
    source: Optional[str] = Query(
        default=None,
        max_length=60,
        description=(
            "Optional case-sensitive `source` filter "
            "(e.g. `server`, `factory_runner`). Omit for all sources."
        ),
    ),
    include_boot_states: bool = Query(
        default=False,
        description=(
            "When true, also return the bare boot_state rows "
            "interleaved with override_diff events for the full "
            "activation timeline. Off by default to keep payload small."
        ),
    ),
    include_context: bool = Query(
        default=True,
        description=(
            "When true (default), each widening event carries a 24h "
            "pre-window context block (auto_cycles, multi_cycle_runs, "
            "lifecycle transitions, factory_runner heartbeat presence)."
        ),
    ),
    include_universe: bool = Query(
        default=True,
        description=(
            "When true (default), also include the operator-decreed "
            "governance_universe audit_log entries."
        ),
    ),
) -> Dict[str, Any]:
    """Return the forensic widening history payload.

    Shape documented on `engines.widening_history.build_history()`.
    Always advisory; never authoritative.
    """
    since_dt = _parse_iso(since)
    return await widening_history.build_history(
        limit=limit,
        since=since_dt,
        source=source,
        include_boot_states=include_boot_states,
        include_context=include_context,
        include_universe=include_universe,
    )
