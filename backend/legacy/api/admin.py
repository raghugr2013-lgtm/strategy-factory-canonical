"""
Admin API — list / approve / reject users.

All routes require role=="admin" (enforced by `require_admin` dep).
Fully additive — lives alongside existing routers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth_utils import require_admin
from engines.db import get_db

logger = logging.getLogger(__name__)

USERS_COLL = "users"

router = APIRouter(prefix="/admin", tags=["admin"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/users")
async def list_users(
    status: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    db = get_db()
    q = {}
    if status in ("pending", "approved", "rejected"):
        q["status"] = status
    cur = db[USERS_COLL].find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    users = await cur.to_list(length=None)
    return {"count": len(users), "users": users}


async def _set_status(user_id: str, new_status: str, admin_email: str) -> dict:
    db = get_db()
    now = _now_iso()
    update = {"status": new_status, "status_updated_at": now, "status_updated_by": admin_email}
    if new_status == "approved":
        update["approved_at"] = now
    res = await db[USERS_COLL].find_one_and_update(
        {"user_id": user_id},
        {"$set": update},
        projection={"_id": 0, "password_hash": 0},
        return_document=True,  # motor: returns the new doc
    )
    # Different motor versions use return_document with different sentinels;
    # fall back to manual re-fetch if the returned doc is None-ish.
    if not res:
        res = await db[USERS_COLL].find_one(
            {"user_id": user_id}, {"_id": 0, "password_hash": 0},
        )
    if not res:
        raise HTTPException(status_code=404, detail="user not found")
    return res


@router.post("/approve/{user_id}")
async def approve_user(user_id: str, admin: dict = Depends(require_admin)):
    # Admin cannot accidentally demote themselves via this flow.
    db = get_db()
    target = await db[USERS_COLL].find_one({"user_id": user_id}, {"_id": 0, "email": 1, "role": 1})
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    user = await _set_status(user_id, "approved", admin.get("email", ""))
    return {"status": "approved", "user": user}


@router.post("/reject/{user_id}")
async def reject_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_db()
    target = await db[USERS_COLL].find_one({"user_id": user_id}, {"_id": 0, "email": 1, "role": 1})
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="cannot reject an admin")
    user = await _set_status(user_id, "rejected", admin.get("email", ""))
    return {"status": "rejected", "user": user}
