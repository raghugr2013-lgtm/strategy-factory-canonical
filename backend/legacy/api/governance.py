"""Phase 30 — Governance API (read-only + admin-only mutations).

Mounts:
    GET  /api/governance/promotion-ledger        — stage breakdown of cohort
    GET  /api/governance/survivor-registry       — top-N elite universe
    GET  /api/governance/replacement-candidates  — advisory list
    POST /api/governance/replacement/execute     — ADMIN: apply one replacement
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines import replacement_engine as rep
from engines import survivor_registry as sr
from engines import governance_universe as gu

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])


class ExecuteReplacementRequest(BaseModel):
    incumbent_hash: str = Field(..., min_length=8, max_length=100)
    challenger_hash: str = Field(..., min_length=8, max_length=100)
    reason: str = Field(..., min_length=8, max_length=500)


@router.get("/promotion-ledger")
async def promotion_ledger() -> Dict[str, Any]:
    """Stage-by-stage breakdown of the cohort. Read-only.

    Per-stage:
      • count
      • deploy_score_p50
      • deploy_score_p90
    """
    return await sr.fetch_promotion_ledger()


@router.get("/survivor-registry")
async def survivor_registry(
    limit: int = Query(sr.SURVIVOR_TOP_N, ge=1, le=500),
) -> Dict[str, Any]:
    """Top-N elite universe (elite + portfolio_worthy + deployment_ready).
    Read-only. Sorted by deploy_score descending. Operator decision #1:
    cap=100. Override-able via `?limit=N`."""
    return await sr.fetch_survivor_universe(top_n=int(limit))


@router.get("/replacement-candidates")
async def replacement_candidates() -> Dict[str, Any]:
    """Advisory list of replacement candidates. ZERO writes.

    Each entry pairs (incumbent in bottom decile of survivor universe,
    challenger at prop_safe with higher deploy_score). `eligible=true`
    only when COOLDOWN AND DELTA both pass.
    """
    return await rep.fetch_replacement_candidates()


@router.post("/replacement/execute")
async def execute_replacement(
    req: ExecuteReplacementRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """ADMIN-ONLY. Apply one operator-approved replacement.

    Effects:
      • incumbent.current_stage → prop_safe
      • Audit rows in strategy_lifecycle_history AND audit_log
        (permanent retention)
    """
    try:
        return await rep.execute_replacement(
            incumbent_hash=req.incumbent_hash,
            challenger_hash=req.challenger_hash,
            admin_email=admin.get("email") or "admin",
            reason=req.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:                                  # pragma: no cover
        logger.exception("replacement execute failed")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# Phase 30.1 — Δ1 · Unified Strategy Truth (canonical READ surface only)
# ─────────────────────────────────────────────────────────────────────
#
# Operator constraint:
#   Δ1 must become the canonical institutional READ surface,
#   but NOT the canonical WRITE authority.
# This endpoint NEVER writes anywhere. It joins live reads across:
#   • strategy_lifecycle    (truth: stage, deploy_score, flags)
#   • strategy_performance_history (truth: per-regime evidence)
#   • strategy_library      (truth: phase-11 slot membership)
#   • survivor_registry     (truth: top-N=100 universe position)
#   • replacement_engine    (truth: incumbent/challenger pairing)
# ─────────────────────────────────────────────────────────────────────

@router.get("/strategy-truth/{strategy_hash}")
async def strategy_truth(strategy_hash: str) -> Dict[str, Any]:
    """Canonical institutional READ surface for one strategy hash.

    Returns a single consolidated payload — operator no longer needs to
    mentally merge 4–6 endpoints. ZERO writes. Phase 30.1, advisory-only.
    """
    from engines.db import get_db
    from engines import regime_performance as rp_engine
    from engines.strategy_lifecycle import get_lifecycle, LIFECYCLE_COLL

    db = get_db()

    # 1. Lifecycle truth (authoritative stage / deploy_score / flags)
    lc = await get_lifecycle(strategy_hash) or {}
    current_stage = lc.get("current_stage")
    evidence_block = lc.get("evidence") or {}
    deploy_score = evidence_block.get("deploy_score")

    # 2. Phase 11 slot membership (read from strategy_library)
    lib_doc = await db["strategy_library"].find_one(
        {"strategy_hash": strategy_hash},
        {"_id": 0, "slot_pair": 1, "slot_timeframe": 1, "slot_style": 1,
         "slot_quality_score": 1, "source": 1},
    ) or {}
    is_slot_member = bool(lib_doc.get("slot_pair") or lib_doc.get("source") == "gem_factory")
    slot_pair_tf_style = None
    if lib_doc.get("slot_pair") and lib_doc.get("slot_timeframe"):
        slot_pair_tf_style = (
            f"{lib_doc['slot_pair']}/{lib_doc['slot_timeframe']}"
            + (f"/{lib_doc['slot_style']}" if lib_doc.get("slot_style") else "")
        )

    # 3. Phase 29 regime evidence (on-read aggregator — never persisted)
    hist_rows = [
        r async for r in db["strategy_performance_history"]
        .find({"strategy_hash": strategy_hash}, {"_id": 0})
    ]
    regime_ev = rp_engine.compute_regime_performance(hist_rows)

    # 4. Phase 30 universe membership
    is_universe_member = current_stage in sr.SURVIVOR_ELIGIBLE_STAGES
    rank_in_universe: Optional[int] = None
    weakest_decile_member = False
    if is_universe_member:
        cur = db[LIFECYCLE_COLL].find(
            {"current_stage": {"$in": list(sr.SURVIVOR_ELIGIBLE_STAGES)}},
            {"_id": 0, "strategy_hash": 1, "evidence.deploy_score": 1},
        )
        eligible_docs = [d async for d in cur]
        eligible_docs.sort(key=lambda d: -sr._deploy_score_of(d))
        for idx, d in enumerate(eligible_docs):
            if d.get("strategy_hash") == strategy_hash:
                rank_in_universe = idx + 1
                break
        if rank_in_universe is not None and len(eligible_docs) >= 10:
            decile = max(1, len(eligible_docs) // 10)
            weakest_decile_member = rank_in_universe > (len(eligible_docs) - decile)

    # 5. Replacement candidacy (advisory)
    rep_block = {
        "is_incumbent_candidate":   weakest_decile_member,
        "best_challenger_hash":     None,
        "delta":                    None,
        "would_execute_if_enabled": False,
    }

    # 6. Deployment eligibility — mirrors the cBot route's gate
    cbot_exportable = (current_stage == "deployment_ready")

    return {
        "strategy_hash": strategy_hash,
        "lifecycle": {
            "current_stage":       current_stage,
            "stage_rank":          lc.get("stage_rank"),
            "flags":               lc.get("flags") or [],
            "current_stage_since": lc.get("current_stage_since"),
            "evidence":            evidence_block,
            "phase30_universe_member":      lc.get("phase30_universe_member", False),
            "phase30_universe_joined_at":   lc.get("phase30_universe_joined_at"),
        },
        "phase11_slot": {
            "is_slot_member":     is_slot_member,
            "slot_quality_score": lib_doc.get("slot_quality_score"),
            "slot_pair_tf_style": slot_pair_tf_style,
        },
        "phase29_regime": {
            "breadth_count":   regime_ev["breadth_count"],
            "fragile":         regime_ev["fragile"],
            "regimes_breadth": regime_ev["regimes_breadth"],
            "advisory_only":   True,
        },
        "phase30_universe": {
            "is_member":             is_universe_member,
            "rank_in_universe":      rank_in_universe,
            "weakest_decile_member": weakest_decile_member,
            "deploy_score":          deploy_score,
        },
        "phase30_replacement": rep_block,
        "deployment_eligibility": {
            "cbot_exportable_without_force": cbot_exportable,
            "stage":                          current_stage,
            "force_override_required":        not cbot_exportable,
        },
        "phase":         "30.1",
        "advisory_only": True,
        "computed_at":   sr._now_iso(),
    }



# ─────────────────────────────────────────────────────────────────────
# Phase 30.2 — Universe Governance (ecosystem boundary, NOT allocation)
# ─────────────────────────────────────────────────────────────────────
#
# Operator constraint:
#   The panel defines ALLOWED RESEARCH UNIVERSE.
#   env_priority + orchestrator + mutation budget retain adaptive
#   authority INSIDE that universe.
#
# Routes:
#   GET  /api/governance/universe         — read-only (any user)
#   POST /api/governance/universe         — admin-only mutation
#   GET  /api/governance/universe/preview — diagnostic intersection
# ─────────────────────────────────────────────────────────────────────


class UniversePatchRequest(BaseModel):
    pairs:                 Optional[list] = None
    timeframes:            Optional[list] = None
    styles:                Optional[list] = None
    exploration_floor_pct: Optional[float] = None
    max_active_cells:      Optional[int]   = None
    breadth_vs_depth:      Optional[float] = None


@router.get("/universe")
async def get_universe() -> Dict[str, Any]:
    """Read the operator-decreed allowed research universe."""
    return await gu.get_universe()


@router.post("/universe")
async def save_universe(
    req: UniversePatchRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """ADMIN-ONLY. Update the allowed research universe.

    Appends an entry to the audit_log (cap=50). Only fields present in
    the patch are validated/persisted; omitted fields stay untouched.
    """
    patch = {
        k: v for k, v in req.model_dump(exclude_unset=True).items()
        if v is not None
    }
    if not patch:
        # Echo current state; nothing to do.
        return await gu.get_universe(force_refresh=True)
    try:
        return await gu.save_universe(
            patch, admin_email=admin.get("email") or "admin",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/universe/preview")
async def universe_preview() -> Dict[str, Any]:
    """Diagnostic: show how each authority's default scan pool would be
    filtered by the current allowed universe. READ-ONLY · advisory."""
    from engines import multi_cycle_runner as mcr
    from engines import ai_orchestrator as ao

    # env_priority's full pool — enumerate without filter applied.
    env_pool: list = []
    try:
        from engines import env_priority as ep
        cfg = await ep.get_config()
        for tier in (cfg.get("tiers") or {}).values():
            for p in (tier.get("pairs") or []):
                for tf in (tier.get("timeframes") or []):
                    env_pool.append((p, tf))
    except Exception:                                       # pragma: no cover
        logger.debug("universe preview: env_priority pool fetch failed")

    # gem_factory full pool (3 default pairs × 4 default tfs × 3 styles
    # collapses to pair/tf cells × N=12 here — styles are reported separately).
    gf_pool = [
        (p, tf) for p in ("EURUSD", "GBPUSD", "XAUUSD")
        for tf in ("M5", "M15", "H1", "H4")
    ]

    # auto_factory_phase55 default pool from DEFAULTS.
    try:
        from engines.auto_factory_phase55 import DEFAULTS as AF55
        af_pool = [
            (p, tf) for p in (AF55.get("pairs") or [])
            for tf in (AF55.get("timeframes") or [])
        ]
    except Exception:                                       # pragma: no cover
        af_pool = []

    universe = await gu.get_universe()
    return {
        "universe": universe,
        "effective": gu.effective_preview(
            universe,
            multi_cycle_default=list(mcr.DEFAULT_SCAN),
            orchestrator_diversity=list(ao.DIVERSITY_SCAN),
            autonomous_rotation=list(ao.AUTONOMOUS_DISCOVERY_ROTATION),
            env_priority_pool=env_pool,
            gem_factory_pool=gf_pool,
            auto_factory_pool=af_pool,
        ),
        "phase":         gu.PHASE_VERSION,
        "advisory_only": True,
        "computed_at":   gu._now_iso(),
    }



# ─────────────────────────────────────────────────────────────────────
# BI5 Evolution Roadmap — Maturity Detection Framework (READ-ONLY)
# ─────────────────────────────────────────────────────────────────────
#
# Operator decree:
#   • Advisory-only. Cannot trigger phase activations.
#   • Operator decree > maturity recommendation > silence.
# ─────────────────────────────────────────────────────────────────────


@router.get("/bi5-maturity")
async def bi5_maturity() -> Dict[str, Any]:
    """Read every BI5 evolution phase's readiness signals at once.

    Strictly advisory. No side effects. The orchestrator MAY observe
    these signals but MUST NEVER autonomously activate a phase.
    Each transition requires an explicit operator session.
    """
    from engines import bi5_maturity as bm
    return await bm.evaluate_all()


# ─────────────────────────────────────────────────────────────────────
# EG Evolution Roadmap — Ecosystem Maturity Detection Framework
# ─────────────────────────────────────────────────────────────────────
#
# Operator decree:
#   • Advisory-only. Cannot trigger phase activations.
#   • Operator decree > maturity recommendation > silence.
# ─────────────────────────────────────────────────────────────────────


@router.get("/ecosystem-maturity")
async def ecosystem_maturity() -> Dict[str, Any]:
    """Read every EG evolution phase's readiness signals at once.

    Strictly advisory. No side effects. The orchestrator MAY observe
    these signals but MUST NEVER autonomously activate a phase.
    """
    from engines import ecosystem_maturity as em
    return await em.evaluate_all()
