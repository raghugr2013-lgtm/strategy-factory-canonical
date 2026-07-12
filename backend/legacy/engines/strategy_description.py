"""
Strategy Description Layer — additive, read-only enrichment.

Produces a structured, human-readable explanation of a strategy using the
existing `gpt-4o` LLM path (same integration as `strategy_engine`), caches
the result by a deterministic fingerprint so repeat reads are free.

Public surface:
    DESC_COLL
    FINGERPRINT_NS                 — string prefixed to every fingerprint
    DescriptionSchema (docstring)
    generate_description(...)      — always calls the LLM, no caching
    get_or_create_description(...) — cache-first; falls back to generate
    get_cached_description(fp)     — lookup only

Constraints honoured:
    * No changes to scoring / validation / mutation / evolution / saving.
    * Pure enrichment — never raises in the hot path; callers receive a
      structured error payload instead.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

DESC_COLL = "strategy_descriptions"
FINGERPRINT_NS = "desc_v1"


# ── Fingerprint (stable across whitespace / numeric edits) ────────────

_WS_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = _WS_RE.sub(" ", t)
    return t


def fingerprint_of(
    strategy_text: str,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
) -> str:
    """Deterministic key. Includes pair/timeframe so the same template
    text targeted at different pairs gets a distinct description."""
    raw = "||".join([
        FINGERPRINT_NS,
        (pair or "").upper(),
        (timeframe or "").upper(),
        _normalise(strategy_text),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ── LLM prompt / schema ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior quantitative trading analyst explaining
a trading strategy to a new desk trader in plain English.

Return ONLY valid JSON that matches this exact schema — no prose, no code
fences, no commentary:

{
  "summary":          "ONE-LINE plain-English summary of the strategy",
  "entry_logic":      "2-3 sentences describing long/short entry conditions",
  "exit_logic":       "1-2 sentences describing stop-loss, take-profit and exit signals",
  "indicators_used":  ["short labels, e.g. 'EMA 8/21', 'RSI 14', 'ATR 14'"],
  "risk_reward":      "concise label, e.g. '1:1.75 (SL 20 / TP 35 pips)'",
  "best_for":         "market conditions where the strategy thrives (e.g. 'trending markets with clear direction')",
  "risks":            ["2-4 short bullets describing key risks / failure modes"],
  "confidence":       "low | medium | high — how reliable your description is based on the provided text",
  "tags":             ["2-5 short, lowercase tags, e.g. 'trend-following','momentum','scalping','crossover'"]
}

Rules:
- Every field is REQUIRED. Use empty string / empty list only if truly unknowable.
- Keep sentences tight. No emojis. No markdown.
- Base your answer strictly on the strategy text + optional backtest metrics.
  Do NOT invent indicators that aren't in the text.
"""


# ── Public: generate ──────────────────────────────────────────────────

async def generate_description(
    strategy_text: str,
    *,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    style: Optional[str] = None,
    backtest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the LLM, parse the JSON response, return the structured payload.

    On any failure returns a payload with `error` populated (never raises).
    """
    # Phase 30.3 — strategy description routes through `description` task.
    # Provider/model resolution stays for diagnostic visibility but the
    # actual call is delegated to the failover-aware llm_runner (VIE).
    from engines import llm_config as _lc
    _cfg = _lc.get_task_config("description")
    api_key = _cfg.get("api_key")
    if not api_key:
        return {"error": "no_api_key — configure provider keys in .env"}

    # Phase 1B+: emergentintegrations SDK removed — call is routed via
    # engines.llm_runner (VIE HTTP client).

    context_bits = []
    if pair:
        context_bits.append(f"Pair: {pair.upper()}")
    if timeframe:
        context_bits.append(f"Timeframe: {timeframe.upper()}")
    if style:
        context_bits.append(f"Style: {style}")
    if isinstance(backtest, dict) and backtest:
        m = backtest
        context_bits.append(
            "Backtest: "
            f"PF={m.get('profit_factor')}, "
            f"WR={m.get('win_rate')}%, "
            f"MaxDD={m.get('max_drawdown_pct')}%, "
            f"Trades={m.get('total_trades')}, "
            f"Return={m.get('total_return_pct')}%"
        )
    context = "\n".join(context_bits)

    prompt = (
        f"{context}\n\n"
        "STRATEGY TEXT:\n"
        f"{strategy_text.strip()}\n\n"
        "Return the JSON only."
    )

    try:
        from engines.llm_runner import run_chat as _run_chat
        raw = await _run_chat("description", prompt, system_message=SYSTEM_PROMPT)
        if raw is None:
            return {"error": "llm_call_failed: all providers offline or failed"}
    except Exception as e:
        logger.warning("describe LLM call failed: %s", e)
        return {"error": f"llm_call_failed: {str(e)[:240]}"}

    # Strip code fences if the model relapses; extract first {...} block.
    parsed = _parse_json_response(raw)
    if parsed is None:
        return {"error": "llm_returned_non_json", "raw_preview": (raw or "")[:400]}
    return parsed


def _parse_json_response(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        # Drop ```json ... ``` fences
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # Last-ditch: pull the first {...} block.
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ── Public: cache-aware ───────────────────────────────────────────────

async def get_cached_description(fp: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        doc = await db[DESC_COLL].find_one({"fingerprint": fp}, {"_id": 0})
    except Exception as e:
        logger.debug("desc cache lookup failed: %s", e)
        return None
    return doc


async def get_or_create_description(
    strategy_text: str,
    *,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    style: Optional[str] = None,
    backtest: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Return `{fingerprint, description, cached: bool, created_at}`.

    On generation failure the payload still includes `fingerprint` so
    callers can retry later; `description` will be `{error: "..."}`.
    """
    fp = fingerprint_of(strategy_text, pair=pair, timeframe=timeframe)

    if not force:
        cached = await get_cached_description(fp)
        if cached:
            return {
                "fingerprint": fp,
                "description": cached.get("description"),
                "cached": True,
                "created_at": cached.get("created_at"),
                "pair": cached.get("pair"),
                "timeframe": cached.get("timeframe"),
            }

    description = await generate_description(
        strategy_text, pair=pair, timeframe=timeframe,
        style=style, backtest=backtest,
    )
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "fingerprint": fp,
        "pair": (pair or None) and pair.upper(),
        "timeframe": (timeframe or None) and timeframe.upper(),
        "style": style or None,
        "description": description,
        "created_at": now,
    }
    # Only persist successful generations; errored responses are returned
    # but not cached (so a retry after a transient LLM hiccup succeeds).
    if not description.get("error"):
        try:
            db = get_db()
            # Upsert so a race between two callers doesn't blow up.
            await db[DESC_COLL].update_one(
                {"fingerprint": fp},
                {"$setOnInsert": doc},
                upsert=True,
            )
            # Ensure index (best-effort, idempotent).
            await db[DESC_COLL].create_index(
                "fingerprint", unique=True, background=True,
            )
        except Exception as e:
            logger.debug("desc cache persist failed: %s", e)

    return {
        "fingerprint": fp,
        "description": description,
        "cached": False,
        "created_at": now,
        "pair": doc["pair"],
        "timeframe": doc["timeframe"],
    }
