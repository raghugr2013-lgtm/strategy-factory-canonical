"""
Auth API — signup / login / me.

Signup creates a user with status="pending". Login returns a JWT only
when status=="approved"; otherwise 403. Password hashes use bcrypt.

Fully additive. Lives alongside existing routers.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from auth_utils import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from engines.db import get_db

logger = logging.getLogger(__name__)

USERS_COLL = "users"

router = APIRouter(prefix="/auth", tags=["auth"])

import re
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _validate_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email format")
    if len(v) > 254:
        raise ValueError("email too long")
    return v


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validate_email(v)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validate_email(v)


@router.post("/signup")
async def signup(req: SignupRequest):
    """Create a new user with status=pending. Admin must approve before login works."""
    email = req.email.lower().strip()
    db = get_db()
    # Unique-index guard + clear error surface
    existing = await db[USERS_COLL].find_one({"email": email}, {"_id": 0, "status": 1})
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")

    user_doc = {
        "user_id": uuid.uuid4().hex[:12],
        "email": email,
        "password_hash": hash_password(req.password),
        "role": "user",
        "status": "pending",
        "created_at": _now_iso(),
    }
    try:
        await db[USERS_COLL].insert_one(user_doc)
    except Exception as e:
        logger.exception("signup failed")
        # Race with the unique index: surface as 409.
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail="email already registered")
        raise HTTPException(status_code=500, detail="signup failed")

    return {
        "message": "Account created. Awaiting admin approval.",
        "email": email,
        "status": "pending",
    }


@router.post("/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    db = get_db()
    user = await db[USERS_COLL].find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="invalid credentials")

    status = user.get("status", "pending")
    if status == "rejected":
        raise HTTPException(status_code=403, detail="account rejected")
    if status != "approved":
        raise HTTPException(status_code=403, detail="account awaiting admin approval")

    token = create_token(user)
    return {
        "token": token,
        "user": {
            "user_id": user.get("user_id"),
            "email": user["email"],
            "role": user.get("role", "user"),
            "status": user.get("status"),
            "created_at": user.get("created_at"),
        },
    }


@router.get("/me")
async def me(request: Request, user: dict = Depends(get_current_user)):
    # `get_current_user` already strips password_hash + validates approval.
    return {"user": user}
