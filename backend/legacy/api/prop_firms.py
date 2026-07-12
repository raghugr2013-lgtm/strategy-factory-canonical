"""
API routes for the Prop Firm Config System (Phase 2 — additive).

Endpoints:
  POST /api/prop-firms/extract   multipart form: firm_name, challenge_size,
                                 website_url?, pdf? → returns extracted rules
                                 (PREVIEW, not persisted).
  POST /api/prop-firms/save      JSON: persists user-approved config.
  GET  /api/prop-firms/list      list all configs.
  GET  /api/prop-firms/{slug}    get one.
  DELETE /api/prop-firms/{slug}  remove config + mirrored challenge_rules row.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from engines.prop_firm_config_engine import (
    delete_config,
    extract_rules,
    get_config,
    list_configs,
    parse_pdf_bytes,
    save_config,
    save_pdf_blob,
    scrape_website,
    _slugify,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prop-firms", tags=["prop-firms"])

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB


# ── Request / response models ────────────────────────────────────────

class ConsistencyRulePayload(BaseModel):
    enabled: bool = False
    max_daily_profit_pct: Optional[float] = None


class NewsRestrictionPayload(BaseModel):
    enabled: bool = False
    blackout_minutes: Optional[int] = None


class LotSizeLimitPayload(BaseModel):
    enabled: bool = False
    max_lot_per_trade: Optional[float] = None
    max_total_exposure: Optional[float] = None


class ScalingRulePayload(BaseModel):
    enabled: bool = False
    type: str = "risk_reduction"
    threshold_dd_pct: Optional[float] = 5.0
    risk_multiplier: Optional[float] = 0.5


class MinTradingDaysPayload(BaseModel):
    enabled: bool = False
    days: int = 0


class RulesPayload(BaseModel):
    # CORE (always enforced) — required on save.
    max_total_drawdown: Optional[float] = None
    max_daily_drawdown: Optional[float] = None
    profit_target: Optional[float] = None
    # OPTIONAL — toggle-based. Each accepts a typed object OR legacy flat
    # form for backward compat; `_build_challenge_rules_doc` normalises.
    min_trading_days: Optional[Any] = None            # int | MinTradingDaysPayload
    consistency_rule: Optional[ConsistencyRulePayload] = None
    consistency_rules: Optional[Dict[str, Any]] = None  # legacy alias
    news_restriction: Optional[NewsRestrictionPayload] = None
    lot_size_limit: Optional[LotSizeLimitPayload] = None
    scaling_rule: Optional[ScalingRulePayload] = None
    # Metadata (not rules)
    fees: Optional[float] = None
    confidence_score: Optional[int] = None


class SaveFirmRequest(BaseModel):
    firm_name: str = Field(..., min_length=1)
    website: Optional[str] = None
    challenge_size: float = Field(..., ge=1000)
    rules: RulesPayload
    extraction_meta: Optional[Dict[str, Any]] = None
    pdf_path: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/extract")
async def extract_firm(
    firm_name: str = Form(...),
    challenge_size: float = Form(...),
    website_url: Optional[str] = Form(None),
    pdf: Optional[UploadFile] = File(None),
):
    """
    Hybrid extract: scrape website + parse PDF + regex + LLM-fallback.
    Returns extracted rules for user review. Persists the uploaded PDF
    on disk so it can be reused on save, but does NOT commit rules yet.
    """
    if not firm_name.strip():
        raise HTTPException(status_code=400, detail="firm_name is required")
    if challenge_size < 1000:
        raise HTTPException(status_code=400, detail="challenge_size must be >= 1000")
    if not website_url and (pdf is None or not pdf.filename):
        raise HTTPException(
            status_code=400,
            detail="Provide at least a website_url or a PDF upload.",
        )

    # Scrape website (best-effort)
    scrape: Dict[str, Any] = {"text": "", "method": "none", "error": None}
    if website_url:
        scrape = await scrape_website(website_url)

    # Parse PDF (best-effort)
    pdf_text = ""
    pdf_path: Optional[str] = None
    pdf_meta: Dict[str, Any] = {"pages": 0, "error": None, "saved": False}
    if pdf is not None and pdf.filename:
        blob = await pdf.read()
        if len(blob) > MAX_PDF_BYTES:
            raise HTTPException(status_code=400, detail="PDF exceeds 5 MB limit")
        parsed = parse_pdf_bytes(blob)
        pdf_text = parsed.get("text", "") or ""
        pdf_meta = {
            "pages": parsed.get("pages", 0),
            "error": parsed.get("error"),
            "saved": False,
            "filename": pdf.filename,
        }
        try:
            pdf_path = save_pdf_blob(blob, _slugify(firm_name))
            pdf_meta["saved"] = True
        except Exception as e:  # pragma: no cover
            logger.warning(f"[prop_firm_config] failed to save PDF: {e}")

    result = await extract_rules(
        website_text=scrape.get("text", "") or "",
        pdf_text=pdf_text,
        firm_name=firm_name.strip(),
    )

    # Additive: persist into prop_firm_rules as status='parsed' so the
    # Review & Approval layer can track it. Never blocks the extract flow.
    try:
        from engines.prop_firm_rule_engine import ingest_parsed_rules
        await ingest_parsed_rules(
            firm_slug=_slugify(firm_name),
            firm_name=firm_name.strip(),
            parsed_rules=result.get("extracted") or {},
            parser_confidence=(result.get("confidence") or 0) / 100.0
                if isinstance(result.get("confidence"), (int, float)) else None,
            source_type="pdf" if pdf_path else ("url" if website_url else None),
            source_url=website_url,
        )
    except Exception as e:  # pragma: no cover
        logger.debug("ingest_parsed_rules failed: %s", e)

    return {
        "firm_name": firm_name.strip(),
        "firm_slug": _slugify(firm_name),
        "website": website_url,
        "challenge_size": float(challenge_size),
        "extracted": result["extracted"],
        "confidence": result["confidence"],
        "sources_used": result["sources_used"],
        "missing_fields": result["missing_fields"],
        "website_meta": {
            "method": scrape.get("method"),
            "error": scrape.get("error"),
            "text_length": len(scrape.get("text") or ""),
        },
        "pdf_meta": pdf_meta,
        "pdf_path": pdf_path,
    }


# ── Background-job variant ──────────────────────────────────────────

@router.post("/extract-async")
async def extract_firm_async(
    firm_name: str = Form(...),
    challenge_size: float = Form(...),
    website_url: Optional[str] = Form(None),
    pdf: Optional[UploadFile] = File(None),
):
    """Non-blocking version of `/extract`. Returns a job_id immediately
    and runs the scrape + parse + LLM-normalise pipeline in the
    background. Poll `/extract-jobs/{job_id}` for the result."""
    if not firm_name.strip():
        raise HTTPException(status_code=400, detail="firm_name is required")
    if challenge_size < 1000:
        raise HTTPException(status_code=400, detail="challenge_size must be >= 1000")
    if not website_url and (pdf is None or not pdf.filename):
        raise HTTPException(
            status_code=400,
            detail="Provide at least a website_url or a PDF upload.",
        )

    pdf_bytes: Optional[bytes] = None
    pdf_filename: Optional[str] = None
    if pdf is not None and pdf.filename:
        pdf_bytes = await pdf.read()
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise HTTPException(status_code=400, detail="PDF exceeds 5 MB limit")
        pdf_filename = pdf.filename

    from engines.extract_jobs import enqueue_extract
    doc = await enqueue_extract(
        firm_name=firm_name.strip(),
        challenge_size=float(challenge_size),
        website_url=website_url,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )
    return doc


@router.get("/extract-jobs/{job_id}")
async def get_extract_job(job_id: str):
    from engines.extract_jobs import get_job
    doc = await get_job(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return doc


@router.get("/extract-jobs")
async def list_extract_jobs(limit: int = 50):
    from engines.extract_jobs import list_recent_jobs
    rows = await list_recent_jobs(limit)
    return {"count": len(rows), "jobs": rows}


@router.post("/save")
async def save_firm(req: SaveFirmRequest):
    """Persist a user-approved prop firm config."""
    try:
        saved = await save_config(
            firm_name=req.firm_name,
            website=req.website,
            challenge_size=req.challenge_size,
            rules=req.rules.model_dump(exclude_none=True),
            pdf_path=req.pdf_path,
            extraction_meta=req.extraction_meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "saved", "config": saved}


@router.get("/list")
async def list_firms():
    configs = await list_configs()
    return {"count": len(configs), "configs": configs}


@router.get("/{firm_slug}")
async def get_firm(firm_slug: str):
    doc = await get_config(firm_slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Config '{firm_slug}' not found")
    return doc


@router.delete("/{firm_slug}")
async def delete_firm(firm_slug: str):
    n_cfg, n_rules = await delete_config(firm_slug)
    if n_cfg == 0 and n_rules == 0:
        raise HTTPException(status_code=404, detail=f"Config '{firm_slug}' not found")
    return {"status": "deleted", "firm_slug": firm_slug, "removed_config": n_cfg, "removed_rules": n_rules}
