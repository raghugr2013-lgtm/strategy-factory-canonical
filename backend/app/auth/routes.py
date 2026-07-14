"""Auth endpoints — login, refresh, logout, me."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
import re
from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _norm_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email format")
    return v

from app.auth.deps import get_current_user
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import UserPublic
from app.db.mongo import get_db
import uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _e(cls, v: str) -> str:
        return _norm_email(v)


class SignupRequest(BaseModel):
    """v01-compatible public signup — creates a user with status="pending".
    Admin approval is required before login succeeds. Mirrors the shape used
    by the frontend `signup()` helper in services/auth.js.
    """
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=256)

    @field_validator("email")
    @classmethod
    def _e(cls, v: str) -> str:
        return _norm_email(v)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_min: int
    # v01 compatibility fields (Strategy Factory legacy AuthGate & services/auth.js)
    token: Optional[str] = None
    user: Optional[dict] = None


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenPair)
async def login(req: LoginRequest):
    db = get_db()
    email = req.email.strip().lower()
    doc = await db.users.find_one({"email": email})
    if not doc or not verify_password(req.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="invalid email or password")
    if doc.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="account disabled")
    # v01 admin-approve-signup flow: block login until approved.
    if doc.get("status") == "pending":
        raise HTTPException(status_code=403, detail="account awaiting admin approval")
    if doc.get("status") == "rejected":
        raise HTTPException(status_code=403, detail="account rejected")

    access = create_access_token(user_id=doc["user_id"], email=doc["email"], role=doc.get("role", "viewer"))
    refresh, jti, expires_at = create_refresh_token(user_id=doc["user_id"])

    await db.refresh_tokens.insert_one(
        {
            "jti": jti,
            "user_id": doc["user_id"],
            "expires_at": expires_at,
            "revoked": False,
            "created_at": datetime.now(timezone.utc),
        }
    )
    from app.core.config import get_settings

    s = get_settings()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in_min=s.jwt_access_ttl_min,
        token=access,  # v01 legacy alias
        user={
            "user_id": doc["user_id"],
            "email": doc["email"],
            "role": doc.get("role", "viewer"),
            "status": doc.get("status", "approved"),
        },
    )


@router.post("/signup")
async def signup(req: SignupRequest):
    """Public signup — creates a user with status="pending". Admin must
    approve via `/api/admin/approve/{user_id}` before the account can log in.
    Idempotent-friendly: returns 409 if the email is already registered.
    Response shape matches v01 legacy so services/auth.js works unchanged.
    """
    email = req.email.strip().lower()
    db = get_db()
    existing = await db.users.find_one({"email": email}, {"_id": 0, "status": 1})
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": uuid.uuid4().hex[:16],
        "email": email,
        "password_hash": hash_password(req.password),
        "role": "viewer",
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.users.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        logger.exception("signup failed")
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail="email already registered")
        raise HTTPException(status_code=500, detail="signup failed")

    return {
        "message": "Account created. Awaiting admin approval.",
        "email": email,
        "status": "pending",
    }



@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="refresh expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid refresh")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="wrong token type")

    db = get_db()
    jti = payload.get("jti")
    record = await db.refresh_tokens.find_one({"jti": jti})
    if not record or record.get("revoked"):
        raise HTTPException(status_code=401, detail="refresh revoked")

    user = await db.users.find_one({"user_id": payload.get("sub")})
    if not user or user.get("status") == "disabled":
        raise HTTPException(status_code=401, detail="user unavailable")

    # rotate: revoke old, issue new pair
    await db.refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})
    access = create_access_token(user_id=user["user_id"], email=user["email"], role=user.get("role", "viewer"))
    new_refresh, new_jti, expires_at = create_refresh_token(user_id=user["user_id"])
    await db.refresh_tokens.insert_one(
        {
            "jti": new_jti,
            "user_id": user["user_id"],
            "expires_at": expires_at,
            "revoked": False,
            "created_at": datetime.now(timezone.utc),
        }
    )
    from app.core.config import get_settings

    s = get_settings()
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        expires_in_min=s.jwt_access_ttl_min,
    )


@router.post("/logout")
async def logout(req: Optional[RefreshRequest] = None, user: UserPublic = Depends(get_current_user)):
    db = get_db()
    if req and req.refresh_token:
        try:
            payload = decode_token(req.refresh_token)
            jti = payload.get("jti")
            if jti:
                await db.refresh_tokens.update_one({"jti": jti}, {"$set": {"revoked": True}})
        except jwt.InvalidTokenError:
            pass
    return {"ok": True}


@router.get("/me")
async def me(user: UserPublic = Depends(get_current_user)):
    # Dual shape: flat (Phase-1) + nested { user } (v01 legacy AuthGate/services/auth.js).
    payload = user.model_dump(mode="json")
    return {**payload, "user": payload}
