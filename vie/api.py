"""VIE HTTP service — single generate endpoint + provider status + probe."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load env from vie/.env then process env (process env wins)
_BASE = Path(__file__).resolve().parent
load_dotenv(_BASE / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from .registry import get_registry  # noqa: E402
from .router import route  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s vie: %(message)s")
logger = logging.getLogger("vie")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    task: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    system_message: str = ""
    temperature: float = 0.3
    max_tokens: Optional[int] = None


class GenerateResponse(BaseModel):
    provider: str
    model: str
    output: str
    usage: Optional[Dict[str, Any]] = None
    task: Optional[str] = None


app = FastAPI(title="VIE — VQB Intelligence Engine", version="1.0.0")


@app.get("/health")
def health():
    reg = get_registry()
    avail = reg.available()
    return {
        "status": "ok",
        "providers_total": len(reg.all()),
        "providers_available": len(avail),
        "available": [p.name for p in avail],
    }


@app.get("/providers")
def providers():
    return {"providers": get_registry().status()}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    reg = get_registry()
    available_names = [p.name for p in reg.available()]

    if not available_names:
        raise HTTPException(status_code=503, detail="no providers available (no API keys configured)")

    # 1. explicit provider override
    if req.provider:
        p = reg.get(req.provider)
        if p is None:
            raise HTTPException(status_code=400, detail=f"unknown provider: {req.provider}")
        if not p.available:
            raise HTTPException(status_code=503, detail=f"provider '{req.provider}' unavailable (missing API key)")
        candidates = [req.provider]
    else:
        # 2. task-based routing (or default)
        candidates = route(req.task or "default", available_names)
        if not candidates:
            candidates = available_names  # fall back to any

    last_err: Optional[Exception] = None
    for name in candidates:
        p = reg.get(name)
        if p is None or not p.available:
            continue
        try:
            result = p.generate(
                prompt=req.prompt,
                system_message=req.system_message,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            )
            return GenerateResponse(
                provider=name,
                model=result.get("model", p.default_model),
                output=result.get("output", ""),
                usage=result.get("usage"),
                task=req.task,
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("provider %s failed: %s — trying next", name, e)
            continue

    raise HTTPException(status_code=502, detail=f"all providers failed: {last_err}")


class ProbeRequest(BaseModel):
    provider: Optional[str] = None  # None → probe all
    prompt: str = "ping"
    max_tokens: int = 5
    timeout_s: float = 15.0


class ProbeResult(BaseModel):
    name: str
    available: bool
    tested: bool
    ok: bool
    latency_ms: Optional[int] = None
    model: Optional[str] = None
    error: Optional[str] = None


@app.post("/probe")
def probe(req: ProbeRequest) -> Dict[str, List[ProbeResult]]:
    """Live diagnostic — pings each provider with a tiny prompt.

    - `provider=None` → probes every provider in the registry.
    - Unavailable providers report `{available: false, tested: false}`.
    - Errors are captured per-provider — one bad provider does not abort the run.
    """
    reg = get_registry()

    if req.provider:
        p = reg.get(req.provider)
        if p is None:
            raise HTTPException(status_code=400, detail=f"unknown provider: {req.provider}")
        targets = [p]
    else:
        targets = reg.all()

    results: List[ProbeResult] = []
    for p in targets:
        if not p.available:
            results.append(
                ProbeResult(name=p.name, available=False, tested=False, ok=False, error="api key not configured")
            )
            continue

        start = time.perf_counter()
        try:
            out = p.generate(
                prompt=req.prompt,
                system_message="Reply with the single word 'ok'.",
                temperature=0.0,
                max_tokens=req.max_tokens,
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                ProbeResult(
                    name=p.name,
                    available=True,
                    tested=True,
                    ok=True,
                    latency_ms=elapsed_ms,
                    model=out.get("model") if isinstance(out, dict) else None,
                )
            )
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                ProbeResult(
                    name=p.name,
                    available=True,
                    tested=True,
                    ok=False,
                    latency_ms=elapsed_ms,
                    error=str(e)[:300],
                )
            )

    return {"results": results}
