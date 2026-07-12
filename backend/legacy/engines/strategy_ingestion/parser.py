"""AI parser — turns raw strategy code into a structured IngestedStrategy
via GPT-4o. Strict JSON output, rejects martingale/grid/unclear logic.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional


from .schema import IngestedStrategy

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert trading-code auditor and strategy extractor.

Given raw code for a forex strategy (Pine Script, MQL4/MQL5, or Python), you
MUST:

1. Decide the strategy TYPE — one of exactly these (lowercase):
     trend_following | mean_reversion | breakout | session_based |
     volatility_based | unknown
2. List the INDICATORS used. Canonical names only:
     EMA, SMA, MACD, RSI, Bollinger Bands, Donchian Channel, ATR,
     VWAP, session high/low
   If the code uses a non-standard indicator, map it to the closest
   canonical name if possible, otherwise omit it.
3. Extract ENTRY conditions (both long and short combined into one
   concise English sentence).
4. Extract EXIT conditions (SL / TP / trailing).
5. Describe the RISK MODEL in ≤15 words:
     fixed RR 1:2, fixed RR 1:3, ATR-based, structure-based, trailing stop,
     or "unknown".
6. Detect the intended TIMEFRAME if obvious (e.g. "M15", "H1"); else "H1".
7. Detect the intended PAIR if obvious (e.g. "EURUSD"); else "EURUSD".
8. Rate your CONFIDENCE in the extraction on 0.0 → 1.0 (be honest).
9. REJECT the strategy (set reject=true with a reason) if ANY of:
     - uses martingale / cost-averaging / position pyramiding
     - uses grid trading
     - logic is unreadable / obfuscated
     - relies on undisclosed ML / external signals
     - no identifiable entry rule
     - relies on hedging multiple lots simultaneously

Return ONLY valid JSON in exactly this shape, nothing else:

{
  "name": "short descriptive name",
  "type": "<one canonical type>",
  "indicators": ["..."],
  "entry_logic": "...",
  "exit_logic": "...",
  "risk_model": "...",
  "timeframe": "H1",
  "pair": "EURUSD",
  "confidence": 0.0,
  "reject": false,
  "reject_reason": null
}

No markdown. No commentary. JSON only."""


_JSON_RE = re.compile(r"\{[\s\S]+\}")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def parse_strategy_with_ai(
    raw_code: str,
    *,
    source: str = "github",
    source_url: Optional[str] = None,
    name_hint: Optional[str] = None,
) -> IngestedStrategy:
    """Parse a raw strategy code blob. Always returns an IngestedStrategy
    — a rejection is encoded via `confidence=0, rejection_reason=...`.
    """
    # Phase 30.3 — direct-provider routing via Phase 17 router.
    # Provider/model attribution kept for the no-key fallback message;
    # the actual call is delegated to the failover-aware llm_runner.
    from engines import llm_config as _lc
    _cfg = _lc.get_task_config("ingestion")
    api_key  = _cfg.get("api_key")
    provider = _cfg.get("resolved_provider") or "openai"
    if not api_key or str(api_key).strip().lower() in ("", "dummy_key", "your_key_here"):
        # Graceful fallback — keep ingestion stable when no LLM key is
        # configured. Return a low-confidence stub so callers can decide
        # to filter it out via `confidence == 0`.
        clipped = (raw_code or "")[:8000]
        return IngestedStrategy(
            name=(name_hint or "unparsed")[:160],
            type="unknown",
            source=source,
            raw_code=clipped,
            confidence=0.0,
            rejection_reason=f"no_llm_key — configure {provider.upper()}_API_KEY to enable AI parsing",
            raw_source_url=source_url,
        )

    # Cap the code size we send.
    clipped = (raw_code or "")[:8000]

    user = (
        f"SOURCE: {source}\n"
        f"FILENAME: {name_hint or '(unknown)'}\n\n"
        "CODE:\n"
        "```\n"
        f"{clipped}\n"
        "```\n\n"
        "Extract per the system instructions. Return JSON only."
    )
    try:
        from engines.llm_runner import run_chat as _run_chat
        resp = await _run_chat("ingestion", user, system_message=SYSTEM_PROMPT)
        if resp is None:
            raise RuntimeError("llm runner returned None — all providers failed or offline")
    except Exception as e:
        logger.warning("parser LLM call failed: %s", e)
        return IngestedStrategy(
            name=(name_hint or "unknown")[:160],
            type="unknown",
            source=source,
            raw_code=clipped,
            confidence=0.0,
            rejection_reason=f"llm_error: {str(e)[:180]}",
            raw_source_url=source_url,
        )

    data = _extract_json(str(resp))
    if not data or not isinstance(data, dict):
        return IngestedStrategy(
            name=(name_hint or "unknown")[:160],
            type="unknown",
            source=source,
            raw_code=clipped,
            confidence=0.0,
            rejection_reason="non_json_response",
            raw_source_url=source_url,
        )

    rejected = bool(data.get("reject"))
    reject_reason = data.get("reject_reason") if rejected else None
    confidence = float(data.get("confidence") or 0.0)
    if rejected:
        confidence = 0.0

    try:
        return IngestedStrategy(
            name=str(data.get("name") or name_hint or "ingested")[:160],
            type=str(data.get("type") or "unknown").strip().lower(),
            indicators=[str(x) for x in (data.get("indicators") or []) if x],
            entry_logic=str(data.get("entry_logic") or "").strip()[:600],
            exit_logic=str(data.get("exit_logic") or "").strip()[:600],
            risk_model=str(data.get("risk_model") or "unknown").strip()[:120],
            timeframe=str(data.get("timeframe") or "H1").upper()[:6],
            pair=str(data.get("pair") or "EURUSD").upper()[:12],
            source=source,
            raw_code=clipped,
            confidence=max(0.0, min(1.0, confidence)),
            rejection_reason=reject_reason,
            raw_source_url=source_url,
        )
    except Exception as e:
        logger.debug("parser schema error: %s", e)
        return IngestedStrategy(
            name=(name_hint or "ingested")[:160],
            type="unknown",
            source=source,
            raw_code=clipped,
            confidence=0.0,
            rejection_reason=f"schema_error: {str(e)[:180]}",
            raw_source_url=source_url,
        )
