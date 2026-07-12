"""Admin endpoints — user + provider management."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
import re
from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _norm_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email format")
    return v

from app.auth.deps import require_admin
from app.auth.security import hash_password
from app.db.models import ALL_ROLES, UserPublic
from app.db.mongo import get_db
from app.vie.client import VIEError, VIEUnavailable, get_vie

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin())])


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    name: Optional[str] = None
    role: str = "viewer"

    @field_validator("email")
    @classmethod
    def _e(cls, v: str) -> str:
        return _norm_email(v)


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=256)


@router.get("/users", response_model=List[UserPublic])
async def list_users():
    db = get_db()
    cursor = db.users.find({}, {"password_hash": 0}).sort("created_at", -1)
    out: list[UserPublic] = []
    async for d in cursor:
        out.append(
            UserPublic(
                user_id=d["user_id"],
                email=d["email"],
                name=d.get("name"),
                role=d.get("role", "viewer"),
                status=d.get("status", "active"),
                created_at=d["created_at"],
            )
        )
    return out


@router.post("/users", response_model=UserPublic, status_code=201)
async def create_user(req: CreateUserRequest):
    if req.role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ALL_ROLES}")
    db = get_db()
    email = req.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="email already registered")
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": uuid.uuid4().hex[:16],
        "email": email,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "role": req.role,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    return UserPublic(
        user_id=doc["user_id"],
        email=doc["email"],
        name=doc.get("name"),
        role=doc["role"],
        status=doc["status"],
        created_at=doc["created_at"],
    )


@router.patch("/users/{user_id}", response_model=UserPublic)
async def update_user(user_id: str, req: UpdateUserRequest):
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="user not found")
    updates: dict = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.role is not None:
        if req.role not in ALL_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {ALL_ROLES}")
        updates["role"] = req.role
    if req.status is not None:
        if req.status not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="status must be active|disabled")
        updates["status"] = req.status
    if req.password is not None:
        updates["password_hash"] = hash_password(req.password)
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
    d = await db.users.find_one({"user_id": user_id}, {"password_hash": 0})
    return UserPublic(
        user_id=d["user_id"],
        email=d["email"],
        name=d.get("name"),
        role=d.get("role", "viewer"),
        status=d.get("status", "active"),
        created_at=d["created_at"],
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    db = get_db()
    res = await db.users.delete_one({"user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="user not found")


@router.get("/providers")
async def list_providers():
    try:
        return {"providers": await get_vie().providers()}
    except VIEUnavailable as e:
        raise HTTPException(status_code=503, detail=f"VIE unavailable: {e}")


class ProbeBody(BaseModel):
    provider: Optional[str] = None


@router.post("/providers/probe")
async def probe_providers(body: ProbeBody | None = None):
    """Live probe — sends a tiny prompt to each configured provider and measures latency.

    Payload: { "provider": null }  → probe all providers.
    Payload: { "provider": "openai" } → probe only that provider.
    """
    prov = body.provider if body else None
    try:
        return {"results": await get_vie().probe(prov)}
    except VIEUnavailable as e:
        raise HTTPException(status_code=503, detail=f"VIE unavailable: {e}")
    except VIEError as e:
        # unknown provider name → upstream 400 → surface as 400 here too
        msg = str(e)
        if "400" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
