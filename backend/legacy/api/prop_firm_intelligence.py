"""
API routes for the Prop Firm Intelligence Layer (Phase 3 — additive).

  POST /api/prop-firms/discover-challenges
       multipart: firm_name, website_url?, pdf? → preview of detected plans.
  POST /api/prop-firms/save-challenges
       JSON: persist user-approved plans (+ optional mirror to challenge_rules).
  GET  /api/prop-firms/intelligence/list
  GET  /api/prop-firms/intelligence/{slug}
  DELETE /api/prop-firms/intelligence/{slug}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from engines.prop_firm_intelligence import (
    MAX_PAGES,
    delete_firm,
    discover_firm,
    get_firm,
    list_firms,
    parse_pdf_bytes,
    save_challenges,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prop-firms", tags=["prop-firms-intelligence"])

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB


# ── Request models ──────────────────────────────────────────────────

class ChallengeRulesPayload(BaseModel):
    profit_target: Optional[float] = None
    profit_target_phase2: Optional[float] = None
    max_total_drawdown: Optional[float] = None
    max_daily_drawdown: Optional[float] = None
    min_trading_days: Optional[int] = None


class ChallengePlanPayload(BaseModel):
    account_size: int = Field(..., ge=1000)
    type: str
    fee: Optional[float] = None
    rules: ChallengeRulesPayload
    confidence: Optional[int] = 0
    source: Optional[str] = "manual"


class SaveChallengesRequest(BaseModel):
    firm_name: str = Field(..., min_length=1)
    website: Optional[str] = None
    challenges: List[ChallengePlanPayload]
    mirror_to_rules: bool = True
    discovery_meta: Optional[Dict[str, Any]] = None


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/discover-challenges")
async def discover_challenges(
    firm_name: str = Form(...),
    website_url: Optional[str] = Form(None),
    pdf: Optional[UploadFile] = File(None),
):
    """Multi-page crawl + per-plan rule discovery. Returns a preview; does
    NOT persist anything."""
    if not firm_name.strip():
        raise HTTPException(status_code=400, detail="firm_name is required")
    if not website_url and (pdf is None or not pdf.filename):
        raise HTTPException(
            status_code=400,
            detail="Provide at least a website_url or a PDF upload.",
        )

    pdf_text = ""
    pdf_meta = {"pages": 0, "error": None, "filename": None}
    if pdf is not None and pdf.filename:
        blob = await pdf.read()
        if len(blob) > MAX_PDF_BYTES:
            raise HTTPException(status_code=400, detail="PDF exceeds 5 MB limit")
        parsed = parse_pdf_bytes(blob)
        pdf_text = parsed.get("text", "") or ""
        pdf_meta = {
            "pages": parsed.get("pages", 0),
            "error": parsed.get("error"),
            "filename": pdf.filename,
        }

    result = await discover_firm(
        firm_name=firm_name.strip(),
        website_url=website_url,
        pdf_text=pdf_text,
    )
    result["pdf_meta"] = pdf_meta
    result["max_pages_cap"] = MAX_PAGES
    return result


@router.post("/save-challenges")
async def save_challenges_endpoint(req: SaveChallengesRequest):
    """Persist user-approved challenge plans."""
    if not req.challenges:
        raise HTTPException(status_code=400, detail="challenges list cannot be empty")
    try:
        saved = await save_challenges(
            firm_name=req.firm_name,
            website=req.website,
            challenges=[c.model_dump() for c in req.challenges],
            mirror_to_rules=req.mirror_to_rules,
            discovery_meta=req.discovery_meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "saved", **saved}


@router.get("/intelligence/list")
async def intelligence_list():
    firms = await list_firms()
    return {"count": len(firms), "firms": firms}


@router.get("/intelligence/{firm_slug}")
async def intelligence_get(firm_slug: str):
    doc = await get_firm(firm_slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Firm '{firm_slug}' not found")
    return doc


@router.delete("/intelligence/{firm_slug}")
async def intelligence_delete(firm_slug: str):
    n_cfg, n_plans = await delete_firm(firm_slug)
    if n_cfg == 0 and n_plans == 0:
        raise HTTPException(status_code=404, detail=f"Firm '{firm_slug}' not found")
    return {"status": "deleted", "firm_slug": firm_slug,
            "removed_firms": n_cfg, "removed_plan_rules": n_plans}
