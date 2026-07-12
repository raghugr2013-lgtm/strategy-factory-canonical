"""Dashboard summary — counts + module status for the UI."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.db.models import UserPublic
from app.db.mongo import get_db
from app.vie.client import VIEUnavailable, get_vie

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(user: UserPublic = Depends(get_current_user)):
    db = get_db()
    users_count = await db.users.count_documents({})
    strategies_count = await db.strategies.count_documents({})
    research_count = await db.research_queries.count_documents({})

    providers_available = 0
    providers_total = 0
    vie_status = "yellow"
    try:
        provs = await get_vie().providers()
        providers_total = len(provs)
        providers_available = sum(1 for p in provs if p.get("available"))
        vie_status = "green" if providers_available > 0 else "yellow"
    except VIEUnavailable:
        vie_status = "red"

    return {
        "counts": {
            "users": users_count,
            "strategies": strategies_count,
            "research_queries": research_count,
            "providers_available": providers_available,
            "providers_total": providers_total,
        },
        "modules": {
            "auth": "green",
            "vie": vie_status,
            "mongo": "green",
            "stage2_legacy_preserved": "amber",
        },
        "user": {"email": user.email, "role": user.role},
    }
