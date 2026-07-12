"""Research endpoints — thin wrapper that routes AI calls through VIE."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_roles
from app.db.models import UserPublic
from app.db.mongo import get_db
from app.vie.client import VIEError, VIEUnavailable, get_vie

router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    task: str = "research"
    provider: Optional[str] = None
    model: Optional[str] = None
    system_message: str = "You are a quantitative trading research assistant. Be concise and cite reasoning."
    temperature: float = 0.3
    max_tokens: Optional[int] = 1024


class ResearchOut(BaseModel):
    query_id: str
    prompt: str
    provider: str
    model: Optional[str]
    output: str
    created_at: datetime
    created_by: str


@router.post("/query", response_model=ResearchOut)
async def query(
    req: ResearchRequest,
    user: UserPublic = Depends(require_roles("admin", "developer", "researcher")),
):
    try:
        result = await get_vie().generate(
            prompt=req.prompt,
            task=req.task,
            provider=req.provider,
            model=req.model,
            system_message=req.system_message,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except VIEUnavailable as e:
        raise HTTPException(status_code=503, detail=f"VIE unavailable: {e}")
    except VIEError as e:
        raise HTTPException(status_code=502, detail=f"VIE error: {e}")

    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "query_id": uuid.uuid4().hex[:16],
        "prompt": req.prompt,
        "task": req.task,
        "provider": result.get("provider", "unknown"),
        "model": result.get("model"),
        "output": result.get("output", ""),
        "usage": result.get("usage"),
        "created_at": now,
        "created_by": user.user_id,
    }
    await db.research_queries.insert_one(doc)
    return ResearchOut(
        query_id=doc["query_id"],
        prompt=doc["prompt"],
        provider=doc["provider"],
        model=doc.get("model"),
        output=doc["output"],
        created_at=doc["created_at"],
        created_by=doc["created_by"],
    )


@router.get("/history", response_model=List[ResearchOut])
async def history(user: UserPublic = Depends(get_current_user)):
    db = get_db()
    cur = db.research_queries.find({"created_by": user.user_id}).sort("created_at", -1).limit(50)
    out: list[ResearchOut] = []
    async for d in cur:
        out.append(
            ResearchOut(
                query_id=d["query_id"],
                prompt=d["prompt"],
                provider=d.get("provider", "unknown"),
                model=d.get("model"),
                output=d.get("output", ""),
                created_at=d["created_at"],
                created_by=d.get("created_by", ""),
            )
        )
    return out
