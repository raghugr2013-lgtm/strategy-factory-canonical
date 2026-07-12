"""Idempotent admin seeding — safe to call on every boot."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.auth.security import hash_password, verify_password
from app.core.config import get_settings
from app.db.mongo import get_db

logger = logging.getLogger(__name__)


async def seed_admin() -> None:
    s = get_settings()
    email = (s.admin_email or "").strip().lower()
    pwd = s.admin_password or ""
    if not email or not pwd:
        logger.warning("admin seed skipped: ADMIN_EMAIL / ADMIN_PASSWORD not set")
        return

    db = get_db()
    now = datetime.now(timezone.utc)
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one(
            {
                "user_id": uuid.uuid4().hex[:16],
                "email": email,
                "password_hash": hash_password(pwd),
                "name": "Administrator",
                "role": "admin",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        )
        logger.info("admin seeded: %s", email)
        return

    updates = {}
    if not verify_password(pwd, existing.get("password_hash", "")):
        updates["password_hash"] = hash_password(pwd)
    if existing.get("role") != "admin":
        updates["role"] = "admin"
    if existing.get("status") != "active":
        updates["status"] = "active"
    if updates:
        updates["updated_at"] = now
        await db.users.update_one({"email": email}, {"$set": updates})
        logger.info("admin updated: %s (%s)", email, ",".join(updates.keys()))
