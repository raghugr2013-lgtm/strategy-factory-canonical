"""v01-compatibility shim for legacy `auth_utils` top-level import.

The v01 codebase imported `from auth_utils import ...` at the top level of
~50 router files. After consolidation, auth was rebuilt cleanly as
`app.auth.*` (JWT + 5-role RBAC + refresh-token rotation) but the preserved
legacy routers still use v01 signatures. This shim re-exports the small set
of names the legacy code actually consumes, mapping them onto the new
auth stack where the semantics match:

    hash_password / verify_password  → app.auth.security equivalents
    create_access_token              → app.auth.security.create_access_token
    decode_access_token              → app.auth.security.decode_access_token
    require_auth (FastAPI dependency)→ wraps app.auth.deps.get_current_user
    require_admin                    → wraps app.auth.deps.require_roles("admin")
    require_role(role_name)          → wraps app.auth.deps.require_roles(role_name)

Every dependency returns the SAME shape as the v01 code expected
(a `dict` with `user_id, email, role`), so no legacy router needs to be
rewritten.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, Header

from app.auth import security as _security
from app.auth.deps import get_current_user as _get_current_user
from app.auth.deps import require_roles as _require_roles
from app.db.models import UserPublic as _UserPublic

# ── password / token primitives (semantic-preserving re-exports) ─────

def hash_password(password: str) -> str:
    return _security.hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _security.verify_password(plain, hashed)


def create_access_token(user: Dict[str, Any]) -> str:
    """v01 signature: takes a user dict (subset) and returns JWT string."""
    return _security.mint_access_token(
        user_id=user.get("user_id") or user.get("id") or "",
        email=user.get("email") or "",
        role=user.get("role") or "viewer",
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    payload = _security.decode_token(token)
    return {
        "user_id": payload.get("sub") or payload.get("user_id"),
        "email": payload.get("email"),
        "role": payload.get("role") or "viewer",
    }


# ── dependency helpers (v01 signature preserved) ─────────────────────

def _to_v01(u: _UserPublic) -> Dict[str, Any]:
    return {
        "user_id": u.user_id,
        "email": u.email,
        "role": u.role,
        "status": "active",
    }


async def require_auth(user: _UserPublic = Depends(_get_current_user)) -> Dict[str, Any]:
    return _to_v01(user)


async def require_admin(user: _UserPublic = Depends(_require_roles("admin"))) -> Dict[str, Any]:
    return _to_v01(user)


def require_role(*roles: str):
    """v01 helper that returned a FastAPI dependency callable."""
    dep = _require_roles(*roles)

    async def _wrapped(u: _UserPublic = Depends(dep)) -> Dict[str, Any]:
        return _to_v01(u)

    return _wrapped


# ── v01 constants some routers reference ────────────────────────────
USERS_COLL = "users"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/refresh"}


# ── legacy middleware helpers (rarely used, but preserved) ──────────

def get_bearer_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:]


async def optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    """v01 dependency that returned the user or None if no bearer."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = _security.decode_token(authorization[7:])
        return {
            "user_id": payload.get("sub") or payload.get("user_id"),
            "email": payload.get("email"),
            "role": payload.get("role") or "viewer",
        }
    except Exception:  # noqa: BLE001
        return None


# ── v01 named aliases some routers reach for directly ──────────────
# The v01 code sometimes wrote `from auth_utils import get_current_user`
# rather than `require_auth`. Same semantics — expose both names.

async def get_current_user(user: _UserPublic = Depends(_get_current_user)) -> Dict[str, Any]:
    return _to_v01(user)


async def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    return await optional_user(authorization)


# v01 admin flag governance router uses this
require_developer = require_role("admin", "developer")
require_operator = require_role("admin", "developer", "operator")
require_researcher = require_role("admin", "developer", "researcher")
require_viewer = require_role("admin", "developer", "operator", "researcher", "viewer")
