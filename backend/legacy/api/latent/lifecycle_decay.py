"""/api/latent/lifecycle_decay — diagnostic surface for aging framework."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import lifecycle_decay
from engines.feature_flags import flag

router = APIRouter()


@router.get("/latent/lifecycle_decay/distribution")
async def distribution(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only — current aging-penalty distribution across the
    `strategy_lifecycle` cohort. Cached value (last recompute)."""
    return await lifecycle_decay.get_distribution()


@router.post("/latent/lifecycle_decay/recompute")
async def recompute(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Re-evaluate aging_penalty for every lifecycle doc and persist
    the updated value. Diagnostic-only — does NOT modify current_stage
    or deploy_score (those are gated by `ENABLE_AGING_PENALTY`)."""
    return await lifecycle_decay.recompute_all()


@router.post("/latent/lifecycle_decay/seed-evidence-fields")
async def seed(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Idempotent backfill — populate `evidence.last_revalidation_at`
    on lifecycle docs that pre-date the aging framework. Safe to call
    multiple times; only writes to docs missing the field."""
    return await lifecycle_decay.seed_evidence_fields()


@router.get("/latent/lifecycle_decay/status")
async def status(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return {
        "is_active":                    bool(flag("ENABLE_AGING_PENALTY")),
        "auto_demotion_enabled":        bool(flag("ENABLE_AGING_AUTO_DEMOTION")),
        "tau_days":                     float(flag("AGING_TAU_DAYS")),
        "auto_demotion_threshold":      float(flag("AGING_AUTO_DEMOTION_THRESHOLD")),
        "note": (
            "All values are persisted but NOT applied to deploy_score "
            "or auto-demotion until the corresponding ENABLE_* flag is "
            "set to true via environment override."
        ),
    }
