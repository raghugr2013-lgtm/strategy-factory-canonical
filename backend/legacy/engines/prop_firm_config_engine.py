"""
Prop Firm Config Engine — Phase 2 (Hybrid Input).

Responsibilities:
  1. Scrape a prop firm website (Playwright first, requests+BS4 fallback).
  2. Parse an uploaded rules PDF (pdfplumber).
  3. Extract the standard rule fields (hybrid: regex first, GPT-5.2 fallback
     only for missing / ambiguous fields).
  4. Persist user-approved configs to `prop_firm_configs` and mirror into
     the existing `challenge_rules` collection so the simulator, ranker,
     and firm dropdown pick new firms up automatically WITHOUT modifying
     any existing engine.

IMPORTANT: This module is purely additive. It does not touch / mutate
existing engines (strategy/validation/decision/ranking/refinement/code
generator/compile).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

CONFIG_COLLECTION = "prop_firm_configs"
RULES_COLLECTION = "challenge_rules"  # existing — we only upsert (no schema changes)

PDF_STORAGE_DIR = Path("/app/backend/prop_firm_pdfs")
PDF_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Standard fields we always try to extract
RULE_FIELDS = [
    "max_total_drawdown",
    "max_daily_drawdown",
    "profit_target",
    "min_trading_days",
]


# ═══════════════════════════════════════════════════════════════════════
# Text source 1 — Website scraping
# ═══════════════════════════════════════════════════════════════════════

async def scrape_website(url: str, timeout_ms: int = 20000) -> Dict[str, Any]:
    """
    Scrape a prop firm website and return its visible text content.

    Strategy: Playwright first (handles JS-rendered sites). Falls back to
    requests+BeautifulSoup on any failure. Returns a dict with:
      { "text": str, "method": "playwright"|"requests"|"none", "error": str|None }
    """
    if not url:
        return {"text": "", "method": "none", "error": "no url"}

    # --- Playwright path ---
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # best-effort: give JS a moment, don't fail if network never idles
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                text = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
                await context.close()
                return {"text": (text or "").strip(), "method": "playwright", "error": None}
            finally:
                await browser.close()
    except Exception as e:
        logger.info(f"[prop_firm_config] playwright scrape failed for {url}: {e}")

    # --- requests + BS4 fallback ---
    try:
        import requests
        from bs4 import BeautifulSoup

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StrategyFactoryBot/1.0)"
                },
            ),
        )
        if resp.status_code >= 400:
            return {"text": "", "method": "requests", "error": f"http {resp.status_code}"}
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return {"text": text.strip(), "method": "requests", "error": None}
    except Exception as e:
        return {"text": "", "method": "none", "error": f"scrape failed: {e}"}


# ═══════════════════════════════════════════════════════════════════════
# Text source 2 — PDF parsing
# ═══════════════════════════════════════════════════════════════════════

def parse_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract text from a PDF blob. Returns {text, pages, error}."""
    if not pdf_bytes:
        return {"text": "", "pages": 0, "error": "empty pdf"}
    try:
        import pdfplumber

        out: List[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t:
                    out.append(t)
            pages = len(pdf.pages)
        return {"text": "\n\n".join(out).strip(), "pages": pages, "error": None}
    except Exception as e:
        # pypdf fallback
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(pdf_bytes))
            out = []
            for page in reader.pages:
                try:
                    out.append(page.extract_text() or "")
                except Exception:
                    pass
            return {
                "text": "\n\n".join(out).strip(),
                "pages": len(reader.pages),
                "error": None,
            }
        except Exception as e2:
            return {"text": "", "pages": 0, "error": f"pdf parse failed: {e} / {e2}"}


def save_pdf_blob(pdf_bytes: bytes, firm_slug: str) -> Optional[str]:
    """Persist the uploaded PDF on disk for reprocessing. Returns path or None."""
    if not pdf_bytes:
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe = re.sub(r"[^a-z0-9_]", "_", firm_slug.lower()) or "firm"
    path = PDF_STORAGE_DIR / f"{safe}_{ts}.pdf"
    path.write_bytes(pdf_bytes)
    return str(path)


# ═══════════════════════════════════════════════════════════════════════
# Rule extraction — Regex (primary) + LLM (fallback)
# ═══════════════════════════════════════════════════════════════════════

# Regex patterns tuned for common prop firm phrasing.
# Returned value is a percent (for DD / profit target) or an integer (days).
_RE_MAX_TOTAL = re.compile(
    r"(?:max(?:imum)?\s+)?(?:total|overall|maximum)\s*"
    r"(?:draw[-\s]?down|loss|dd)"
    r"[^%\d\n]{0,80}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_MAX_DAILY = re.compile(
    r"(?:max(?:imum)?\s+)?(?:daily|day(?:ly)?|per[-\s]?day)\s*"
    r"(?:draw[-\s]?down|loss|dd)"
    r"[^%\d\n]{0,80}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_PROFIT = re.compile(
    r"(?:profit\s*target|target\s*profit|profit\s*goal|profit\s*objective)"
    r"[^%\d\n]{0,80}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_MIN_DAYS = re.compile(
    # Two common phrasings:
    #   1. "minimum 4 trading days" / "at least 5 active days"
    #   2. "minimum trading days: 4" / "min trading days 5"
    r"(?:"
    r"(?:min(?:imum)?|at\s*least)\s*(\d{1,3})\s*(?:trading|active)?\s*days?"
    r"|"
    r"(?:min(?:imum)?\s+)?(?:trading|active)\s*days?\s*[:\-=]?\s*(\d{1,3})"
    r")",
    re.IGNORECASE,
)
_RE_CONSISTENCY = re.compile(
    r"consistency[^.\n]{0,160}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_FEE = re.compile(
    r"(?:fee|price|cost)[^\n\$€£]{0,40}?[\$€£]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    if not m:
        return None
    # Multi-alternative patterns may have multiple capture groups where
    # only one is populated for any given match. Walk the groups and
    # return the first non-None one (falls back to group(1) for single-
    # group patterns).
    for g in m.groups():
        if g is not None:
            return g
    return m.group(1) if m.lastindex else None


def regex_extract(text: str) -> Dict[str, Any]:
    """
    Run regex-based extraction on combined text.

    Returns { field: {value, source: "regex", excerpt: str} | None }
    """
    out: Dict[str, Any] = {
        f: None for f in RULE_FIELDS + ["consistency_rules", "fees"]
    }
    if not text:
        return out

    def _excerpt(match_text: Optional[str], key_pattern: str) -> str:
        if not match_text:
            return ""
        m = re.search(
            r".{0,90}" + re.escape(match_text) + r".{0,40}",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        return (m.group(0).strip() if m else "").replace("\n", " ")[:240]

    # floats
    for field, pat in [
        ("max_total_drawdown", _RE_MAX_TOTAL),
        ("max_daily_drawdown", _RE_MAX_DAILY),
        ("profit_target", _RE_PROFIT),
    ]:
        val = _first_match(pat, text)
        if val is not None:
            try:
                v = float(val)
                if 0 < v <= 100:
                    out[field] = {
                        "value": v,
                        "source": "regex",
                        "excerpt": _excerpt(val, pat.pattern),
                    }
            except ValueError:
                pass

    val = _first_match(_RE_MIN_DAYS, text)
    if val is not None:
        try:
            v = int(val)
            if 0 < v <= 60:
                out["min_trading_days"] = {
                    "value": v,
                    "source": "regex",
                    "excerpt": _excerpt(val, _RE_MIN_DAYS.pattern),
                }
        except ValueError:
            pass

    cons = _first_match(_RE_CONSISTENCY, text)
    if cons is not None:
        try:
            v = float(cons)
            out["consistency_rules"] = {
                "value": {"max_daily_profit_pct": v},
                "source": "regex",
                "excerpt": _excerpt(cons, _RE_CONSISTENCY.pattern),
            }
        except ValueError:
            pass

    fee = _first_match(_RE_FEE, text)
    if fee is not None:
        try:
            v = float(fee)
            out["fees"] = {
                "value": v,
                "source": "regex",
                "excerpt": _excerpt(fee, _RE_FEE.pattern),
            }
        except ValueError:
            pass

    return out


def _fields_needing_llm(extracted: Dict[str, Any]) -> List[str]:
    """Required fields still missing after regex pass."""
    return [f for f in RULE_FIELDS if extracted.get(f) is None]


async def llm_fill_missing(
    text: str, missing: List[str], firm_name: str
) -> Dict[str, Any]:
    """
    Fall-back LLM extraction for missing fields only. Phase 30.3 routes
    this through the operator-decreed `propfirm` task (default: Claude).
    Returns { field: {value, source: "llm", excerpt} } for whatever the
    model could recover. Never raises — on any failure returns an empty
    dict so regex values are preserved.
    """
    from engines import llm_config as _lc
    _cfg = _lc.get_task_config("propfirm")
    api_key = _cfg.get("api_key")
    if not api_key or not missing or not text:
        return {}

    # Keep prompt small: first ~6000 chars is almost always enough for a
    # rules page / terms PDF preface.
    sample = text[:6000]

    schema_hint = {
        "max_total_drawdown": "number in percent, e.g. 10",
        "max_daily_drawdown": "number in percent, e.g. 5",
        "profit_target": "number in percent, e.g. 10",
        "min_trading_days": "integer, e.g. 4",
    }
    wanted = {k: schema_hint[k] for k in missing if k in schema_hint}

    system_msg = (
        "You are a compliance data extractor for prop-firm challenge rules. "
        "Read the provided rules text and extract ONLY the requested fields. "
        "Output STRICT JSON — no prose, no markdown fences. If a field is not "
        "stated in the text, set it to null. Percentages must be returned as "
        "plain numbers (e.g. 10, not '10%'). Days must be integers."
    )
    user_msg = (
        f"Firm: {firm_name}\n\n"
        f"Fields to extract (with expected types):\n{json.dumps(wanted, indent=2)}\n\n"
        f"Rules text:\n---\n{sample}\n---\n\n"
        f"Return JSON with exactly these keys: {list(wanted.keys())}."
    )

    try:
        from engines.llm_runner import run_chat as _run_chat
        response = await _run_chat("propfirm", user_msg, system_message=system_msg)
        if response is None:
            logger.warning("[prop_firm_config] LLM fallback: all providers offline/failed")
            return {}
        raw = (response or "").strip()
        # Strip fences if any leaked through
        raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"[prop_firm_config] LLM fallback failed: {e}")
        return {}

    out: Dict[str, Any] = {}
    for field in missing:
        v = data.get(field)
        if v is None:
            continue
        try:
            if field == "min_trading_days":
                vv: Any = int(v)
                if not (0 < vv <= 60):
                    continue
            else:
                vv = float(v)
                if not (0 < vv <= 100):
                    continue
        except (TypeError, ValueError):
            continue
        out[field] = {"value": vv, "source": "llm", "excerpt": ""}
    return out


async def extract_rules(
    website_text: str, pdf_text: str, firm_name: str
) -> Dict[str, Any]:
    """
    Combined hybrid extraction pipeline.

    Returns a dict with:
      - extracted: {field: {value, source, excerpt} | None}
      - confidence: 0-100 int (how many required fields we recovered)
      - sources_used: list of source methods
    """
    combined = "\n\n".join([t for t in (website_text, pdf_text) if t])

    extracted = regex_extract(combined)
    missing = _fields_needing_llm(extracted)
    llm_fills: Dict[str, Any] = {}
    if missing:
        llm_fills = await llm_fill_missing(combined, missing, firm_name)
        for k, v in llm_fills.items():
            extracted[k] = v

    present = sum(1 for f in RULE_FIELDS if extracted.get(f) is not None)
    confidence = int(round(100 * present / len(RULE_FIELDS)))

    sources_used = []
    if website_text:
        sources_used.append("website")
    if pdf_text:
        sources_used.append("pdf")
    if llm_fills:
        sources_used.append("llm")

    return {
        "extracted": extracted,
        "confidence": confidence,
        "sources_used": sources_used,
        "missing_fields": _fields_needing_llm(extracted),
    }


# ═══════════════════════════════════════════════════════════════════════
# Persistence — prop_firm_configs + mirror to challenge_rules
# ═══════════════════════════════════════════════════════════════════════

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "firm"


def _build_challenge_rules_doc(
    firm_slug: str,
    firm_name: str,
    challenge_size: float,
    rules: Dict[str, Any],
    now: str,
) -> Dict[str, Any]:
    """
    Convert user-approved rules into the existing `challenge_rules`
    schema so the simulator / ranker / firm dropdown pick it up with
    zero code changes elsewhere.

    `rules` shape (user-approved, plain values):
      {
        # CORE (always enabled)
        "max_total_drawdown": 10,
        "max_daily_drawdown": 5,
        "profit_target": 10,
        # OPTIONAL — each accepts {enabled, ...params} OR legacy flat form
        "min_trading_days": 4 | {"enabled": true, "days": 4},
        "consistency_rules": {"enabled": true, "max_daily_profit_pct": 40},
        "news_restriction":  {"enabled": true, "blackout_minutes": 5},
        "lot_size_limit":    {"enabled": true, "max_lot_per_trade": 20,
                              "max_total_exposure": 30},
        "scaling_rule":      {"enabled": true, "threshold_dd_pct": 5,
                              "risk_multiplier": 0.5},
        "fees": 0 | None,
      }
    """
    total_dd = float(rules.get("max_total_drawdown") or 10.0)
    daily_dd = float(rules.get("max_daily_drawdown") or 5.0)
    target = float(rules.get("profit_target") or 10.0)

    # Optional — min_trading_days supports legacy int form + new toggled form
    mtd_raw = rules.get("min_trading_days")
    if isinstance(mtd_raw, dict):
        mtd_enabled = bool(mtd_raw.get("enabled"))
        mtd_days = int(mtd_raw.get("days") or 0)
    else:
        mtd_days = int(mtd_raw or 0)
        mtd_enabled = mtd_days > 0

    # Optional — consistency_rule (also accepts legacy
    # `consistency_rules: {max_daily_profit_pct: X}` shape)
    cons_raw = rules.get("consistency_rule") or rules.get("consistency_rules") or {}
    if isinstance(cons_raw, dict) and (
        "enabled" in cons_raw or "max_daily_profit_pct" in cons_raw
    ):
        cons_enabled = bool(
            cons_raw.get("enabled", cons_raw.get("max_daily_profit_pct") is not None)
        )
        cons_pct = cons_raw.get("max_daily_profit_pct")
    else:
        cons_enabled = False
        cons_pct = None

    # Optional — news_restriction (default disabled; simulator does NOT
    # enforce yet — stored for future enforcement)
    news_raw = rules.get("news_restriction") or {}
    news_enabled = bool(news_raw.get("enabled"))
    news_minutes = news_raw.get("blackout_minutes")

    # Optional — lot_size_limit (maps to position_sizing internally)
    lot_raw = rules.get("lot_size_limit") or rules.get("position_sizing") or {}
    lot_enabled = bool(lot_raw.get("enabled"))
    lot_per_trade = lot_raw.get("max_lot_per_trade")
    lot_total = lot_raw.get("max_total_exposure")

    # Optional — scaling_rule
    sc_raw = rules.get("scaling_rule") or {}
    sc_enabled = bool(sc_raw.get("enabled"))
    sc_threshold = float(sc_raw.get("threshold_dd_pct") or 5.0)
    sc_multiplier = float(sc_raw.get("risk_multiplier") or 0.5)

    return {
        "firm_slug": firm_slug,
        "firm_name": firm_name,
        "phase": "Challenge",
        "version": 1,
        "initial_balance": float(challenge_size),
        "rules": {
            # ── CORE (always enabled) ────────────────────────────────
            "daily_dd": {
                "enabled": True,
                "type": "equity",
                "max_pct": daily_dd,
                "description": f"Max {daily_dd}% daily drawdown (equity basis)",
            },
            "total_dd": {
                "enabled": True,
                "type": "static",
                "max_pct": total_dd,
                "description": f"Max {total_dd}% total drawdown from initial balance",
            },
            "profit_target": {
                "enabled": True,
                "target_pct": target,
                "description": f"{target}% profit target",
            },
            # ── OPTIONAL (toggle-based) ──────────────────────────────
            "min_trading_days": {
                "enabled": mtd_enabled,
                "days": mtd_days,
                "description": f"Minimum {mtd_days} trading days" if mtd_enabled else "Disabled",
            },
            "time_limit": {
                "enabled": False,
                "calendar_days": 0,
                "description": "No time limit configured",
            },
            "consistency": {
                "enabled": cons_enabled,
                "min_lots_per_day": None,
                "max_daily_profit_pct": cons_pct if cons_enabled else None,
                "description": (
                    f"Max single day = {cons_pct}% of total profit"
                    if cons_enabled and cons_pct is not None else "Disabled"
                ),
            },
            "news_restriction": {
                "enabled": news_enabled,
                "blackout_minutes": news_minutes if news_enabled else None,
                "enforced": False,
                "description": (
                    f"Stored: ±{news_minutes}min around news "
                    "(NOT enforced by engine yet)" if news_enabled else "Disabled"
                ),
            },
            "restrictions": {
                "news_blackout_minutes": news_minutes if news_enabled else None,
                "max_overnight_lots": None,
                "weekend_hold_allowed": True,
                "description": "Default restrictions",
            },
            "position_sizing": {
                "enabled": lot_enabled,
                "max_lot_per_trade": lot_per_trade if lot_enabled else None,
                "max_total_exposure": lot_total if lot_enabled else None,
                "description": (
                    f"Max {lot_per_trade} lots/trade, {lot_total} aggregate"
                    if lot_enabled else "Disabled"
                ),
            },
            "scaling_rule": {
                "enabled": sc_enabled,
                "type": "risk_reduction",
                "threshold_dd_pct": sc_threshold if sc_enabled else None,
                "risk_multiplier": sc_multiplier if sc_enabled else None,
                "description": (
                    f"Multiply risk by {sc_multiplier} once cumulative DD >= "
                    f"{sc_threshold}%" if sc_enabled else "Disabled"
                ),
            },
        },
        "confidence_score": int(rules.get("confidence_score") or 75),
        "confidence_notes": "Imported via Prop Firm Config System (Phase 2)",
        "validated": True,
        "validated_at": now,
        "manual_override": False,
        "changelog": [
            {"version": 1, "date": now, "changes": "Created via prop firm config extractor"},
        ],
        "created_at": now,
        "updated_at": now,
    }


async def save_config(
    firm_name: str,
    website: Optional[str],
    challenge_size: float,
    rules: Dict[str, Any],
    pdf_path: Optional[str] = None,
    extraction_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist the user-approved config.

    Writes:
      - prop_firm_configs (new collection, full config + metadata)
      - challenge_rules   (existing collection, upsert by firm_slug so
                           simulator & firm dropdown pick it up)
    """
    if challenge_size is None or float(challenge_size) < 1000:
        raise ValueError("challenge_size must be >= 1000")
    if not firm_name or not firm_name.strip():
        raise ValueError("firm_name is required")

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    firm_slug = _slugify(firm_name)

    config_doc = {
        "firm_slug": firm_slug,
        "firm_name": firm_name.strip(),
        "website": website or None,
        "challenge_size": float(challenge_size),
        "rules": rules,
        "pdf_path": pdf_path,
        "extraction_meta": extraction_meta or {},
        "created_at": now,
        "updated_at": now,
    }

    await db[CONFIG_COLLECTION].update_one(
        {"firm_slug": firm_slug},
        {"$set": config_doc},
        upsert=True,
    )
    try:
        await db[CONFIG_COLLECTION].create_index("firm_slug", unique=True)
    except Exception:
        pass

    # Mirror into challenge_rules so existing engines see the new firm.
    rules_doc = _build_challenge_rules_doc(
        firm_slug, firm_name.strip(), float(challenge_size), rules, now
    )
    existing = await db[RULES_COLLECTION].find_one({"firm_slug": firm_slug})
    if existing:
        new_version = int(existing.get("version", 1)) + 1
        rules_doc["version"] = new_version
        rules_doc["created_at"] = existing.get("created_at", now)
        rules_doc["changelog"] = list(existing.get("changelog", [])) + [
            {"version": new_version, "date": now, "changes": "Updated via prop firm config extractor"}
        ]
        await db[RULES_COLLECTION].update_one(
            {"firm_slug": firm_slug}, {"$set": rules_doc}
        )
    else:
        await db[RULES_COLLECTION].insert_one(rules_doc)

    # Return the config doc without _id
    saved = await db[CONFIG_COLLECTION].find_one(
        {"firm_slug": firm_slug}, {"_id": 0}
    )
    return saved


async def list_configs() -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[CONFIG_COLLECTION].find({}, {"_id": 0}).sort("created_at", -1)
    return [doc async for doc in cursor]


async def get_config(firm_slug: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[CONFIG_COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})


async def delete_config(firm_slug: str) -> Tuple[int, int]:
    """Delete both the config and its mirrored challenge_rules entry."""
    db = get_db()
    r1 = await db[CONFIG_COLLECTION].delete_one({"firm_slug": firm_slug})
    r2 = await db[RULES_COLLECTION].delete_one({"firm_slug": firm_slug})
    return r1.deleted_count, r2.deleted_count
