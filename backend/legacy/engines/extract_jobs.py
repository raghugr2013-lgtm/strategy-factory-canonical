"""Background-job wrapper around the existing `extract_rules` pipeline.

The synchronous `/api/prop-firms/extract` endpoint can take 60-120 s for
heavy URLs because it chains website scraping + PDF parsing + LLM
normalisation. This module adds a tiny in-process job queue so the UI
can fire-and-poll instead of holding the HTTP connection open.

No changes to the underlying extract logic — we just wrap it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.prop_firm_config_engine import (
    extract_rules,
    parse_pdf_bytes,
    save_pdf_blob,
    scrape_website,
    _slugify,
)
from engines.prop_firm_rule_engine import ingest_parsed_rules

logger = logging.getLogger(__name__)

JOB_COLL = "prop_firm_extract_jobs"

# In-memory task registry so we don't double-spawn on the same job_id
_RUNNING: Dict[str, asyncio.Task] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def enqueue_extract(
    *, firm_name: str, challenge_size: float,
    website_url: Optional[str] = None, pdf_bytes: Optional[bytes] = None,
    pdf_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new extract job, persist it, and spawn a background task.
    Returns {job_id, status:'queued', ...}. Never blocks the caller."""
    db = get_db()
    job_id = uuid.uuid4().hex[:16]
    now = _now_iso()
    doc = {
        "job_id": job_id,
        "status": "queued",
        "firm_name": firm_name,
        "firm_slug": _slugify(firm_name),
        "challenge_size": challenge_size,
        "website_url": website_url,
        "pdf_filename": pdf_filename,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    await db[JOB_COLL].insert_one({**doc})
    # Launch in the background
    task = asyncio.create_task(
        _run_job(job_id, firm_name=firm_name, website_url=website_url,
                 pdf_bytes=pdf_bytes, pdf_filename=pdf_filename,
                 challenge_size=challenge_size),
    )
    _RUNNING[job_id] = task
    task.add_done_callback(lambda _t: _RUNNING.pop(job_id, None))
    doc.pop("_id", None)
    return doc


async def _run_job(
    job_id: str, *, firm_name: str,
    website_url: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: Optional[str] = None,
    challenge_size: float = 100000.0,
) -> None:
    db = get_db()
    await db[JOB_COLL].update_one(
        {"job_id": job_id},
        {"$set": {"status": "running", "updated_at": _now_iso()}},
    )
    try:
        scrape: Dict[str, Any] = {"text": "", "method": "none", "error": None}
        if website_url:
            scrape = await scrape_website(website_url)
        pdf_text = ""
        pdf_path: Optional[str] = None
        pdf_meta: Dict[str, Any] = {"pages": 0, "error": None, "saved": False}
        if pdf_bytes:
            parsed = parse_pdf_bytes(pdf_bytes)
            pdf_text = parsed.get("text", "") or ""
            pdf_meta = {
                "pages": parsed.get("pages", 0),
                "error": parsed.get("error"),
                "saved": False,
                "filename": pdf_filename,
            }
            try:
                pdf_path = save_pdf_blob(pdf_bytes, _slugify(firm_name))
                pdf_meta["saved"] = True
            except Exception as e:  # pragma: no cover
                logger.warning("extract job save_pdf failed: %s", e)

        extracted = await extract_rules(
            website_text=scrape.get("text", "") or "",
            pdf_text=pdf_text,
            firm_name=firm_name.strip(),
        )

        # Side effect: persist into prop_firm_rules as status='parsed'
        try:
            await ingest_parsed_rules(
                firm_slug=_slugify(firm_name),
                firm_name=firm_name.strip(),
                parsed_rules=extracted.get("extracted") or {},
                parser_confidence=(extracted.get("confidence") or 0) / 100.0
                    if isinstance(extracted.get("confidence"), (int, float)) else None,
                source_type="pdf" if pdf_path else ("url" if website_url else None),
                source_url=website_url,
            )
        except Exception as e:
            logger.debug("ingest_parsed_rules failed in job: %s", e)

        result = {
            "firm_name": firm_name.strip(),
            "firm_slug": _slugify(firm_name),
            "website": website_url,
            "challenge_size": float(challenge_size),
            "extracted": extracted["extracted"],
            "confidence": extracted["confidence"],
            "sources_used": extracted["sources_used"],
            "missing_fields": extracted["missing_fields"],
            "website_meta": {
                "method": scrape.get("method"),
                "error": scrape.get("error"),
                "text_length": len(scrape.get("text") or ""),
            },
            "pdf_meta": pdf_meta,
            "pdf_path": pdf_path,
        }
        await db[JOB_COLL].update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "done", "result": result, "error": None,
                "updated_at": _now_iso(), "completed_at": _now_iso(),
            }},
        )
    except Exception as e:
        logger.exception("extract job %s failed", job_id)
        await db[JOB_COLL].update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "error",
                "error": f"{type(e).__name__}: {str(e)[:300]}",
                "updated_at": _now_iso(),
                "completed_at": _now_iso(),
            }},
        )


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[JOB_COLL].find_one({"job_id": job_id}, {"_id": 0})


async def list_recent_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[JOB_COLL].find({}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 200)))
    return [d async for d in cursor]
