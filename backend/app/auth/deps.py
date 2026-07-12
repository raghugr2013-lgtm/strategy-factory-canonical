"""FastAPI auth dependencies — bearer JWT + role guards."""
from __future__ import annotations

from typing import Iterable

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.auth.security import decode_token
from app.db.models import UserPublic
from app.db.mongo import get_db


async def get_current_user(request: Request) -> UserPublic:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = auth[7:].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="wrong token type")

    user_id = payload.get("sub")
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"password_hash": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="user not found")
    if doc.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="user disabled")

    return UserPublic(
        user_id=doc["user_id"],
        email=doc["email"],
        name=doc.get("name"),
        role=doc.get("role", "viewer"),
        status=doc.get("status", "active"),
        created_at=doc["created_at"],
    )


def require_roles(*roles: str):
    """Return a dependency enforcing that the current user has one of `roles`."""

    async def _dep(user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"role '{user.role}' not permitted")
        return user

    return _dep


def require_admin():
    return require_roles("admin")
