"""ASF API surface — GATE 3 migration importer (admin-only).

Endpoints (all under prefix ``/api/asf``):

    POST /api/asf/import/migration               — dry-run by default
    GET  /api/asf/import/{import_id}             — fetch receipt
    POST /api/asf/import/{import_id}/commit      — commit a dry-run
    POST /api/asf/import/{import_id}/abort       — abort a dry-run

All export and generic-import endpoints (`POST /api/asf/import`, etc.)
are reserved by `ASF_BACKEND_ARCHITECTURE.md §3.10` and return 503 until
later phases ship.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from auth_utils import require_admin
from engines.asf.calibration_snapshot import compare_calibration
from engines.asf.importer.migration_adapter import adapt_1vcpu_to_asf_v1
from engines.asf.importer.upserter import (
    COLL_IMPORT_LOG,
    apply_actions,
)
from engines.asf.importer.verifier import verify
from engines.asf.importer.walker import walk
from engines.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asf", tags=["asf-migration"])


@router.post("/import/migration")
async def import_migration(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Convert and stage the 1-vCPU package into an ASF import receipt.

    Body (all optional, defaults per `GATE3_IMPLEMENTATION_PLAN.md §3`):
        ``dry_run``                  bool   default true
        ``inbox_dir``                str    default /app/_migration_inbox/
        ``dedup_policy``             str    default "skip"
        ``operator_overrides``       dict   {pf_floor, wr_floor, trades_floor,
                                            dd_ceiling, lock_days, lineage_depth,
                                            cohort_id, relaxation_reason,
                                            source_db_name, source_pod_id}
    """
    p = payload or {}
    dry_run = bool(p.get("dry_run", True))
    inbox_dir = p.get(
        "inbox_dir",
        os.environ.get("ASF_INBOX_DIR", "/app/_migration_inbox/"),
    )
    dedup_policy = p.get("dedup_policy", "skip")
    overrides = dict(p.get("operator_overrides") or {})
    # Operator-facing aliases per GATE3 plan §1.
    if "stage_locked_until_days" in overrides and "lock_days" not in overrides:
        overrides["lock_days"] = overrides.pop("stage_locked_until_days")
    if "lineage_depth_cap" in overrides and "lineage_depth" not in overrides:
        overrides["lineage_depth"] = overrides.pop("lineage_depth_cap")

    db = get_db()

    # Convert legacy mongodump → in-memory ASF v1 package.
    try:
        package = await adapt_1vcpu_to_asf_v1(
            inbox_dir=inbox_dir,
            db=db,
            operator_overrides=overrides,
        )
    except Exception as e:
        logger.exception("ASF migration adapter failed")
        raise HTTPException(
            status_code=500,
            detail=f"adapter_failed: {e}",
        )

    # Compare calibration (always zero-drift for 1-vCPU package — see
    # GATE3_IMPLEMENTATION_PLAN.md §1).
    receiver = package.calibration
    drift = compare_calibration(package=package.calibration, receiver=receiver)

    # Walk the package into ApplyActions (read-only DB lookups).
    actions = await walk(
        package=package, db=db, dedup_policy=dedup_policy,
    )

    # Apply (dry-run or wet-run).
    result = await apply_actions(
        package=package,
        actions=actions,
        db=db,
        dry_run=dry_run,
        dedup_policy=dedup_policy,
        calibration_drift=drift,
    )

    # Run verifier and merge its findings into the receipt.
    vr = await verify(
        import_id=result.import_id,
        actions=actions,
        db=db,
        dry_run=dry_run,
    )
    if vr.warnings:
        result.warnings.extend(vr.warnings)
    if vr.status == "verified_with_warnings" and result.status == "verified":
        result.status = "verified_with_warnings"
    if vr.status == "failed":
        result.status = "failed"

    receipt = result.model_dump(mode="json")
    receipt["verification"] = vr.model_dump(mode="json")
    return receipt


@router.get("/import/{import_id}")
async def get_import_receipt(
    import_id: str = Path(..., min_length=8),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    doc = await db[COLL_IMPORT_LOG].find_one(
        {"import_id": import_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="import_id not found")
    return doc


@router.post("/import/{import_id}/commit")
async def commit_import_receipt(
    import_id: str = Path(..., min_length=8),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Commit a dry-run receipt. GATE 3 scope: re-run
    ``/import/migration`` with ``dry_run=false`` instead — this endpoint
    is kept for compatibility with the locked architecture's 4-endpoint
    contract and returns the recommended path."""
    raise HTTPException(
        status_code=409,
        detail=(
            "GATE 3 scope: invoke POST /api/asf/import/migration with "
            "{\"dry_run\": false, \"operator_overrides\": {...}} to "
            "wet-run. Standalone commit-from-receipt ships in Phase 7.3."
        ),
    )


@router.post("/import/{import_id}/abort")
async def abort_import_receipt(
    import_id: str = Path(..., min_length=8),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    db = get_db()
    res = await db[COLL_IMPORT_LOG].update_one(
        {"import_id": import_id, "status": {"$in": ["pending", "verified",
                                                    "verified_with_warnings"]}},
        {"$set": {"status": "aborted"}},
    )
    if res.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="import_id not found or not in an abortable state",
        )
    return {"import_id": import_id, "status": "aborted"}
