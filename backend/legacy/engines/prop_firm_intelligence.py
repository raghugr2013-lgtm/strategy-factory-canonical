"""
Prop Firm Intelligence Layer — Phase 3 (ADDITIVE).

Responsibilities (layered on top of Phase 2 — zero modifications to
prop_firm_config_engine or any other existing engine):

  1. Multi-page crawl of a prop firm website (discover /challenge,
     /pricing, /plans, /accounts, /evaluation style pages and pull
     their text).
  2. Challenge discovery — detect candidate plans with account_size,
     fee, profit target, phase structure.
  3. Challenge type classification — 1-step / 2-step / instant.
  4. Per-plan rule mapping — each challenge carries its own rules, not
     a global set.
  5. Persistence to a NEW collection `prop_firm_challenges`, with an
     OPTIONAL mirror into the existing `challenge_rules` collection
     (one row per plan, slug format `{firm}_{sizek}k_{type}`). Mirror
     is opt-in and performed only on user confirmation, so existing
     engines remain untouched until the user approves.

The engine re-uses Phase-2 primitives (`scrape_website`,
`parse_pdf_bytes`, LLM fallback) without changing them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from engines.db import get_db
from engines.prop_firm_config_engine import (
    parse_pdf_bytes,  # noqa: F401 — re-exported for callers
    scrape_website,
)

logger = logging.getLogger(__name__)

CHALLENGES_COLLECTION = "prop_firm_challenges"
RULES_COLLECTION = "challenge_rules"  # existing, mirrored INTO only on user confirm

# Pages that typically describe challenge plans / pricing
_DISCOVERY_KEYWORDS = (
    "challenge",
    "pricing",
    "plans",
    "accounts",
    "evaluation",
    "packages",
    "fund",
    "funded",
    "scale",
    "one-step",
    "two-step",
    "1-step",
    "2-step",
    "instant",
)

# Common path guesses (tried when no anchor link matches)
_FALLBACK_PATHS = (
    "/challenge",
    "/challenges",
    "/pricing",
    "/plans",
    "/accounts",
    "/evaluation",
    "/packages",
    "/get-funded",
)

MAX_PAGES = 6  # cap total pages crawled to keep latency bounded


# ═══════════════════════════════════════════════════════════════════════
# 1. Multi-page crawl
# ═══════════════════════════════════════════════════════════════════════

async def _extract_links(url: str, timeout_ms: int = 15000) -> List[str]:
    """Return absolute URLs found on the root page whose href/text match
    a challenge/pricing keyword. Uses Playwright (fast) with requests/BS4
    fallback."""
    origin = urlparse(url)
    base = f"{origin.scheme}://{origin.netloc}"

    def _match(href: str, txt: str) -> bool:
        hay = f"{href} {txt}".lower()
        return any(kw in hay for kw in _DISCOVERY_KEYWORDS)

    # --- Playwright path ---
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, args=["--no-sandbox"]
            )
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                links = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({ href: a.getAttribute('href') || '', txt: (a.innerText || '').trim() }))"""
                )
                await context.close()
            finally:
                await browser.close()
    except Exception as e:
        logger.info(f"[intelligence] playwright link-extract failed: {e}")
        links = []

    # --- requests + BS4 fallback if nothing from playwright ---
    if not links:
        try:
            import requests
            from bs4 import BeautifulSoup

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    url, timeout=12,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; StrategyFactoryBot/1.0)"},
                ),
            )
            if resp.status_code < 400:
                soup = BeautifulSoup(resp.text, "lxml")
                links = [{"href": a.get("href") or "", "txt": a.get_text(" ", strip=True)} for a in soup.find_all("a", href=True)]
        except Exception as e:
            logger.info(f"[intelligence] requests link-extract failed: {e}")
            links = []

    # Normalize + filter
    seen: set = set()
    out: List[str] = []
    for link in links:
        href = (link.get("href") or "").strip()
        txt = (link.get("txt") or "").strip()
        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        absolute = urljoin(base + "/", href)
        if urlparse(absolute).netloc != origin.netloc:
            continue  # stay on-site
        if absolute in seen:
            continue
        if _match(href, txt):
            seen.add(absolute)
            out.append(absolute)
    return out


async def discover_pages(url: str) -> List[str]:
    """Return a deduped list of target URLs to crawl (root + matching anchors
    + fallback paths), capped at MAX_PAGES."""
    if not url:
        return []
    root = url.rstrip("/")
    found = await _extract_links(root)
    # Add well-known fallback paths if we didn't find much via anchors
    if len(found) < 2:
        origin = urlparse(root)
        base = f"{origin.scheme}://{origin.netloc}"
        for path in _FALLBACK_PATHS:
            candidate = base + path
            if candidate not in found and candidate != root:
                found.append(candidate)
    # Dedup, keep root first
    ordered: List[str] = [root]
    for u in found:
        if u not in ordered:
            ordered.append(u)
    return ordered[:MAX_PAGES]


async def crawl_site(url: str) -> Dict[str, Any]:
    """
    Crawl the root + discovered pages. Returns:
      {
        "pages": [{"url": str, "text": str, "method": str, "error": str|None}, ...],
        "combined_text": str,
        "pages_crawled": int,
      }
    """
    targets = await discover_pages(url)
    pages: List[Dict[str, Any]] = []
    combined_chunks: List[str] = []
    # Fetch sequentially to avoid opening 6 browsers in parallel
    for t in targets:
        res = await scrape_website(t)
        entry = {
            "url": t,
            "text": (res.get("text") or "")[:40000],  # hard cap per page
            "method": res.get("method"),
            "error": res.get("error"),
        }
        pages.append(entry)
        if entry["text"]:
            combined_chunks.append(f"--- PAGE: {t} ---\n{entry['text']}")
    return {
        "pages": pages,
        "combined_text": "\n\n".join(combined_chunks),
        "pages_crawled": len(pages),
    }


# ═══════════════════════════════════════════════════════════════════════
# 2+3+4+5+6. Challenge discovery, classification, fee, per-plan rules
# ═══════════════════════════════════════════════════════════════════════

# account sizes expressed as $X,XXX / $Xk / $XXX,XXX (explicit $-prefix keeps
# us from matching random numbers like fees or percentages).
_RE_SIZE_CANDIDATE = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})+|\d{1,3}[kK]|\d{4,7})\b"
)
# fee near account context
_RE_FEE = re.compile(
    r"(?:fee|price|cost|from)\s*[:$]?\s*\$?\s*(\d{2,5}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
# phase / targets — accept the keyword BEFORE the percent (e.g.
# "phase 1: 8%") OR AFTER it (e.g. "Profit target: 8% phase 1, 5%
# phase 2"). The two alternatives keep the captured group in slot 1
# or 2; `_first_*` helpers use `m.group(1)` so we need slot 1 to be
# the value. We solve this with a single non-greedy alternation
# pattern where ONE of the two slots is guaranteed empty.
_RE_PHASE1 = re.compile(
    r"(?:"
    r"(?:phase\s*1|step\s*1|stage\s*1|first\s*phase)[^%\d\n]{0,40}?(\d+(?:\.\d+)?)\s*%"
    r"|"
    r"(\d+(?:\.\d+)?)\s*%[^%\d\n]{0,30}?(?:phase\s*1|step\s*1|stage\s*1|first\s*phase)"
    r")",
    re.IGNORECASE,
)
_RE_PHASE2 = re.compile(
    r"(?:"
    r"(?:phase\s*2|step\s*2|stage\s*2|second\s*phase|verification)[^%\d\n]{0,40}?(\d+(?:\.\d+)?)\s*%"
    r"|"
    r"(\d+(?:\.\d+)?)\s*%[^%\d\n]{0,30}?(?:phase\s*2|step\s*2|stage\s*2|second\s*phase|verification)"
    r")",
    re.IGNORECASE,
)
# Generic profit target (used when no phase language is present, e.g. 1-step plans).
_RE_GENERIC_TARGET = re.compile(
    r"(?:profit\s*target|target\s*profit|profit\s*goal|profit\s*objective)"
    r"[^%\d\n]{0,40}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
# type hints
_RE_TWO_STEP = re.compile(r"\b(?:2[-\s]?step|two[-\s]?step|two phases?)\b", re.IGNORECASE)
_RE_ONE_STEP = re.compile(r"\b(?:1[-\s]?step|one[-\s]?step|single\s*phase)\b", re.IGNORECASE)
_RE_INSTANT = re.compile(r"\b(?:instant\s*(?:fund|funding|funded)|immediate\s*funding)\b", re.IGNORECASE)
# DDs
_RE_TOTAL_DD = re.compile(
    r"(?:max(?:imum)?\s+)?(?:total|overall|max)\s*(?:draw[-\s]?down|loss)"
    r"[^%\d\n]{0,60}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_DAILY_DD = re.compile(
    r"(?:max(?:imum)?\s+)?(?:daily|day)\s*(?:draw[-\s]?down|loss)"
    r"[^%\d\n]{0,60}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RE_MIN_DAYS = re.compile(
    # Matches:
    #   "minimum 5 trading days", "at least 4 active days"
    #   "min trading days: 5", "minimum trading days 4"
    r"(?:"
    r"(?:min(?:imum)?|at\s*least)\s*(\d{1,2})\s*(?:trading|active)?\s*days?"
    r"|"
    r"(?:min(?:imum)?\s+)?(?:trading|active)\s*days?\s*[:\-=]?\s*(\d{1,2})"
    r")",
    re.IGNORECASE,
)


def _normalize_size(value: str, suffix: str = "") -> Optional[int]:
    """Return integer USD account size or None if not plausible.
    `value` may be '100,000', '100000', '100k', '100K'; `suffix` is optional."""
    if not value:
        return None
    v = value.strip()
    mul = 1
    if v.endswith(("k", "K")):
        mul = 1000
        v = v[:-1]
    elif suffix and suffix.lower() == "k":
        mul = 1000
    raw = re.sub(r"[,\s]", "", v)
    try:
        n = int(raw) * mul
    except ValueError:
        return None
    if n < 1000 or n > 5_000_000:
        return None
    # Only round sizes that look like real challenge tiers
    if n % 1000 != 0:
        return None
    return n


def _classify_type(block_text: str) -> str:
    """Classify a challenge block into 1-step / 2-step / instant / unknown.

    Precedence:
      1. Explicit keyword in pre-context (section header ABOVE the size).
      2. Explicit Phase-1 + Phase-2 BOTH present in post → definitively 2-step.
      3. Explicit keyword in first 220 chars of post-context.
      4. Single phase-1 mention → 1-step.
    """
    fence = "|||TYPEFENCE|||"
    if fence in block_text:
        pre, full_post = block_text.split(fence, 1)
    else:
        pre, full_post = "", block_text
    short_post = full_post[:220]

    # 1. Pre-context explicit keyword
    if _RE_INSTANT.search(pre):
        return "instant"
    if _RE_TWO_STEP.search(pre):
        return "2-step"
    if _RE_ONE_STEP.search(pre):
        return "1-step"

    # 2. Two-phase structure in the post — unambiguous 2-step
    if _RE_PHASE1.search(full_post) and _RE_PHASE2.search(full_post):
        return "2-step"

    # 3. Short post-context explicit keyword (avoid tail bleed-over)
    if _RE_INSTANT.search(short_post):
        return "instant"
    if _RE_TWO_STEP.search(short_post):
        return "2-step"
    if _RE_ONE_STEP.search(short_post):
        return "1-step"

    # 4. Single phase-1 only
    if _RE_PHASE1.search(full_post):
        return "1-step"
    return "unknown"


def _first_float(pattern: re.Pattern, text: str, lo: float = 0, hi: float = 100) -> Optional[float]:
    m = pattern.search(text)
    if not m:
        return None
    raw = None
    # Multi-alternative patterns expose multiple groups where only one
    # is populated for any given match. Walk them in order.
    for g in m.groups():
        if g is not None:
            raw = g
            break
    if raw is None:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if lo < v <= hi else None


def _first_int(pattern: re.Pattern, text: str, lo: int = 0, hi: int = 60) -> Optional[int]:
    m = pattern.search(text)
    if not m:
        return None
    raw = None
    for g in m.groups():
        if g is not None:
            raw = g
            break
    if raw is None:
        return None
    try:
        v = int(raw)
    except ValueError:
        return None
    return v if lo < v <= hi else None


def _segment_by_size(text: str) -> List[Tuple[int, str]]:
    """
    Split combined text into rough 'blocks' each anchored by a $-prefixed
    account size mention. Returns list of (size_usd, block_text). Each block
    is `pre_context || marker || post_context`, where `pre_context` is up to
    220 chars BEFORE the size (for section-header classification) and
    `post_context` runs until just before the next size match, capped at
    ~1400 chars. The classification fence `|||TYPEFENCE|||` separates the
    two so _classify_type can prefer pre-context.
    """
    hits: List[Tuple[int, int]] = []  # (start_idx, size_usd)
    for m in _RE_SIZE_CANDIDATE.finditer(text):
        size = _normalize_size(m.group(1))
        if size is not None:
            hits.append((m.start(), size))
    if not hits:
        return []

    # Dedup consecutive identical sizes within 200 chars
    deduped: List[Tuple[int, int]] = []
    for idx, sz in hits:
        if deduped and deduped[-1][1] == sz and idx - deduped[-1][0] < 200:
            continue
        deduped.append((idx, sz))

    blocks: List[Tuple[int, str]] = []
    for i, (idx, sz) in enumerate(deduped):
        # Pre-context window — kept tight (60 chars) to avoid the
        # "type bleed-over" problem where a previous plan's "2-step"
        # label leaks into the current plan's classification. The
        # section header for THIS plan is almost always within the
        # immediately preceding line.
        pre_start = max(0, idx - 60)
        post_end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        post_end = min(post_end, idx + 1400)
        pre = text[pre_start:idx]
        post = text[idx:post_end]
        blocks.append((sz, pre + "|||TYPEFENCE|||" + post))
    # Dedup by size: keep the richest block (most rule keywords) per size
    per_size: Dict[int, str] = {}
    for sz, blk in blocks:
        cur = per_size.get(sz, "")
        if _block_score(blk) > _block_score(cur):
            per_size[sz] = blk
    return sorted(per_size.items())


_KEYWORDS_SCORE = ("drawdown", "profit", "target", "phase", "step", "fee", "days", "daily")


def _block_score(text: str) -> int:
    t = text.lower()
    return sum(t.count(k) for k in _KEYWORDS_SCORE)


def regex_discover_challenges(text: str) -> List[Dict[str, Any]]:
    """
    Regex-first discovery. Returns a list of candidate challenges:
      [{account_size, type, fee, rules: {...}, confidence, source: 'regex'}]
    """
    if not text:
        return []
    fence = "|||TYPEFENCE|||"
    results: List[Dict[str, Any]] = []
    for size, block in _segment_by_size(text):
        # Rules must come from POST-context only (pre-context belongs to
        # the previous plan). Type classification uses the full block.
        post = block.split(fence, 1)[1] if fence in block else block
        p1 = _first_float(_RE_PHASE1, post)
        p2 = _first_float(_RE_PHASE2, post)
        generic_target = _first_float(_RE_GENERIC_TARGET, post)
        total_dd = _first_float(_RE_TOTAL_DD, post)
        daily_dd = _first_float(_RE_DAILY_DD, post)
        min_days = _first_int(_RE_MIN_DAYS, post)

        # fee: first plausible $ value (filter obvious DD/percent reuses)
        fee: Optional[float] = None
        for m in _RE_FEE.finditer(post):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            if 20 <= v <= 9000:
                fee = v
                break

        ctype = _classify_type(block)
        # Prefer phase-1 label when present; fall back to generic profit target
        profit_target = p1 if p1 is not None else (generic_target if generic_target is not None else p2)

        # Only emit a plan if we got at least one meaningful rule signal
        has_signal = any(v is not None for v in (p1, p2, total_dd, daily_dd, fee))
        if not has_signal:
            continue

        rules = {
            "profit_target": profit_target,
            "profit_target_phase2": p2 if (p1 is not None and p2 is not None) else None,
            "max_total_drawdown": total_dd,
            "max_daily_drawdown": daily_dd,
            "min_trading_days": min_days,
        }

        # Confidence: % of core fields recovered (target + total_dd + daily_dd)
        core = [profit_target, total_dd, daily_dd]
        confidence = int(round(100 * sum(1 for v in core if v is not None) / len(core)))

        results.append({
            "account_size": size,
            "type": ctype,
            "fee": fee,
            "rules": rules,
            "confidence": confidence,
            "source": "regex",
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
# LLM fallback — only invoked when regex finds nothing or confidence < 50
# ═══════════════════════════════════════════════════════════════════════

async def llm_discover_challenges(
    text: str, firm_name: str, hint: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Fall-back LLM discovery. Returns a list of challenge dicts or [] on
    any failure — never raises.
    """
    # Phase 30.3 — propfirm task routes to Anthropic per operator decree.
    # Provider/model resolution kept for guard rail (no API key → return [])
    # but the actual call is delegated to the failover-aware llm_runner.
    from engines import llm_config as _lc
    _cfg = _lc.get_task_config("propfirm")
    api_key = _cfg.get("api_key")
    if not api_key or not text:
        return []

    sample = text[:10000]
    system_msg = (
        "You are a compliance data extractor. Read the crawled text of a "
        "prop-trading firm website and return a JSON array of challenge "
        "plans. Each entry MUST have keys: account_size (int USD), type "
        "('1-step' | '2-step' | 'instant' | 'unknown'), fee (number USD or null), "
        "rules (object with profit_target, profit_target_phase2, "
        "max_total_drawdown, max_daily_drawdown, min_trading_days — all "
        "numbers or null). Output ONLY the JSON array (no prose, no "
        "markdown fences). Percentages must be plain numbers. If no plans "
        "are detectable, return []."
    )
    user_msg = (
        f"Firm: {firm_name}\n\n"
        f"Crawled text (truncated):\n---\n{sample}\n---\n\n"
        f"Regex-found plans (for reference, may be incomplete):\n"
        f"{json.dumps(hint or [], indent=2)}"
    )
    try:
        from engines.llm_runner import run_chat as _run_chat
        response = await _run_chat("propfirm", user_msg, system_message=system_msg)
        if response is None:
            logger.warning("[intelligence] LLM discovery: all providers offline/failed")
            return []
        raw = (response or "").strip()
        raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"[intelligence] LLM discovery failed: {e}")
        return []

    if not isinstance(data, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            size = int(item.get("account_size") or 0)
        except (TypeError, ValueError):
            continue
        if size < 1000:
            continue
        rules_in = item.get("rules") or {}
        rules = {
            "profit_target": _safe_num(rules_in.get("profit_target")),
            "profit_target_phase2": _safe_num(rules_in.get("profit_target_phase2")),
            "max_total_drawdown": _safe_num(rules_in.get("max_total_drawdown")),
            "max_daily_drawdown": _safe_num(rules_in.get("max_daily_drawdown")),
            "min_trading_days": _safe_int(rules_in.get("min_trading_days")),
        }
        core = [rules["profit_target"], rules["max_total_drawdown"], rules["max_daily_drawdown"]]
        confidence = int(round(100 * sum(1 for v in core if v is not None) / len(core)))
        out.append({
            "account_size": size,
            "type": (item.get("type") or "unknown"),
            "fee": _safe_num(item.get("fee")),
            "rules": rules,
            "confidence": confidence,
            "source": "llm",
        })
    return out


def _safe_num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if 0 < n <= 1_000_000 else None


def _safe_int(v: Any) -> Optional[int]:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 0 < n <= 60 else None


# ═══════════════════════════════════════════════════════════════════════
# Top-level discovery orchestration
# ═══════════════════════════════════════════════════════════════════════

async def discover_firm(
    firm_name: str,
    website_url: Optional[str],
    pdf_text: str = "",
) -> Dict[str, Any]:
    """
    Public orchestrator: crawl → regex → LLM fallback → structured output.

    Returns:
      {
        "firm": firm_name,
        "website": website_url,
        "pages": [{url, method, error}, ...],
        "challenges": [ ... ],
        "sources_used": ["website"|"pdf"|"llm"],
        "crawl_meta": {...}
      }
    """
    sources: List[str] = []
    pages_meta: List[Dict[str, Any]] = []
    text_chunks: List[str] = []

    # 1. Crawl website
    if website_url:
        crawl = await crawl_site(website_url)
        pages_meta = [
            {"url": p["url"], "method": p.get("method"), "error": p.get("error"),
             "text_length": len(p.get("text") or "")}
            for p in crawl["pages"]
        ]
        if crawl["combined_text"]:
            text_chunks.append(crawl["combined_text"])
            sources.append("website")

    # 2. Append PDF text
    if pdf_text:
        text_chunks.append(pdf_text)
        sources.append("pdf")

    combined = "\n\n".join(text_chunks)

    # 3. Regex discovery
    regex_hits = regex_discover_challenges(combined)

    # 4. LLM fallback when regex is empty or all confidences < 50
    need_llm = not regex_hits or all(c.get("confidence", 0) < 50 for c in regex_hits)
    llm_hits: List[Dict[str, Any]] = []
    if need_llm:
        llm_hits = await llm_discover_challenges(combined, firm_name, regex_hits)
        if llm_hits:
            sources.append("llm")

    # 5. Merge: regex-first, add LLM sizes not covered by regex
    merged: Dict[int, Dict[str, Any]] = {c["account_size"]: c for c in regex_hits}
    for c in llm_hits:
        if c["account_size"] not in merged:
            merged[c["account_size"]] = c
        else:
            # Fill missing fields from LLM on top of regex
            existing = merged[c["account_size"]]
            for k, v in c["rules"].items():
                if existing["rules"].get(k) is None and v is not None:
                    existing["rules"][k] = v
            if existing.get("fee") is None and c.get("fee") is not None:
                existing["fee"] = c["fee"]
            if existing.get("type") == "unknown" and c.get("type") != "unknown":
                existing["type"] = c["type"]

    challenges = sorted(merged.values(), key=lambda x: x["account_size"])

    return {
        "firm": firm_name,
        "website": website_url,
        "pages": pages_meta,
        "challenges": challenges,
        "sources_used": sources,
        "crawl_meta": {
            "pages_crawled": len(pages_meta),
            "combined_text_length": len(combined),
            "regex_hits": len(regex_hits),
            "llm_hits": len(llm_hits),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

def _firm_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "firm"


def _plan_slug(firm_slug: str, size: int, ctype: str) -> str:
    sz = f"{size // 1000}k"
    t = {"1-step": "1step", "2-step": "2step", "instant": "instant"}.get(ctype, "plan")
    return f"{firm_slug}_{sz}_{t}"


def _build_rules_doc(
    firm_slug: str,
    firm_name: str,
    challenge: Dict[str, Any],
    now: str,
) -> Dict[str, Any]:
    """Convert a single discovered challenge into the existing
    challenge_rules schema so mirroring is additive and compatible.

    Optional rules default to DISABLED (toggle-based). Extraction only
    fills min_trading_days when the firm's rules document an explicit
    minimum — otherwise that toggle also stays off."""
    r = challenge.get("rules", {}) or {}
    size = int(challenge.get("account_size") or 100000)
    ctype = challenge.get("type") or "unknown"
    plan_slug = _plan_slug(firm_slug, size, ctype)
    target = float(r.get("profit_target") or 10.0)
    total_dd = float(r.get("max_total_drawdown") or 10.0)
    daily_dd = float(r.get("max_daily_drawdown") or 5.0)
    min_days_raw = r.get("min_trading_days")
    try:
        min_days = int(min_days_raw) if min_days_raw is not None else 0
    except (TypeError, ValueError):
        min_days = 0

    return {
        "firm_slug": plan_slug,
        "firm_name": f"{firm_name} {size // 1000}k {ctype}",
        "phase": ctype,
        "version": 1,
        "initial_balance": float(size),
        "rules": {
            # CORE
            "daily_dd": {"enabled": True, "type": "equity", "max_pct": daily_dd,
                         "description": f"Max {daily_dd}% daily drawdown (equity)"},
            "total_dd": {"enabled": True, "type": "static", "max_pct": total_dd,
                         "description": f"Max {total_dd}% total drawdown"},
            "profit_target": {"enabled": True, "target_pct": target,
                              "description": f"{target}% profit target"},
            # OPTIONAL — default disabled unless extractor explicitly filled it
            "min_trading_days": {"enabled": min_days > 0, "days": min_days,
                                 "description": f"Minimum {min_days} trading days" if min_days else "Disabled"},
            "time_limit": {"enabled": False, "calendar_days": 0, "description": "No time limit configured"},
            "consistency": {"enabled": False, "min_lots_per_day": None,
                            "max_daily_profit_pct": None, "description": "Disabled"},
            "news_restriction": {"enabled": False, "blackout_minutes": None,
                                 "enforced": False,
                                 "description": "Disabled (not enforced by engine)"},
            "restrictions": {"news_blackout_minutes": None, "max_overnight_lots": None,
                             "weekend_hold_allowed": True, "description": "Default restrictions"},
            "position_sizing": {"enabled": False, "max_lot_per_trade": None,
                                "max_total_exposure": None, "description": "Disabled"},
            "scaling_rule": {"enabled": False, "type": "risk_reduction",
                             "threshold_dd_pct": None, "risk_multiplier": None,
                             "description": "Disabled"},
        },
        "confidence_score": int(challenge.get("confidence") or 70),
        "confidence_notes": f"Discovered via Prop Firm Intelligence Layer (Phase 3, source={challenge.get('source')})",
        "validated": True,
        "validated_at": now,
        "manual_override": False,
        "changelog": [{"version": 1, "date": now,
                       "changes": f"Created via intelligence discovery ({challenge.get('source')})"}],
        "created_at": now,
        "updated_at": now,
    }


async def save_challenges(
    firm_name: str,
    website: Optional[str],
    challenges: List[Dict[str, Any]],
    mirror_to_rules: bool = True,
    discovery_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist user-approved challenges.

      - Writes a single doc to `prop_firm_challenges` keyed by firm_slug
        containing the full list of plans + metadata.
      - If `mirror_to_rules`, upserts each plan as a separate row in
        `challenge_rules` so the simulator / firm dropdown pick them up
        individually. Non-destructive: existing rows are updated with a
        version bump; rows that aren't in the new set are left untouched
        (user may manually delete via Phase-2 endpoints if desired).
    """
    if not firm_name or not firm_name.strip():
        raise ValueError("firm_name is required")
    if not challenges:
        raise ValueError("challenges list cannot be empty")

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    firm_slug = _firm_slug(firm_name)

    cleaned: List[Dict[str, Any]] = []
    mirrored_slugs: List[str] = []
    for c in challenges:
        size = int(c.get("account_size") or 0)
        if size < 1000:
            raise ValueError(f"account_size must be >= 1000 (got {size})")
        ctype = c.get("type") or "unknown"
        plan = {
            "plan_slug": _plan_slug(firm_slug, size, ctype),
            "account_size": size,
            "type": ctype,
            "fee": c.get("fee"),
            "rules": c.get("rules") or {},
            "confidence": int(c.get("confidence") or 0),
            "source": c.get("source") or "manual",
        }
        cleaned.append(plan)

    doc = {
        "firm_slug": firm_slug,
        "firm_name": firm_name.strip(),
        "website": website or None,
        "challenges": cleaned,
        "discovery_meta": discovery_meta or {},
        "created_at": now,
        "updated_at": now,
    }
    await db[CHALLENGES_COLLECTION].update_one(
        {"firm_slug": firm_slug}, {"$set": doc}, upsert=True
    )
    try:
        await db[CHALLENGES_COLLECTION].create_index("firm_slug", unique=True)
    except Exception:
        pass

    if mirror_to_rules:
        for plan in cleaned:
            rule_doc = _build_rules_doc(
                firm_slug, firm_name.strip(), {
                    "account_size": plan["account_size"],
                    "type": plan["type"],
                    "rules": plan["rules"],
                    "confidence": plan["confidence"],
                    "source": plan["source"],
                }, now,
            )
            existing = await db[RULES_COLLECTION].find_one({"firm_slug": rule_doc["firm_slug"]})
            if existing:
                rule_doc["version"] = int(existing.get("version", 1)) + 1
                rule_doc["created_at"] = existing.get("created_at", now)
                rule_doc["changelog"] = list(existing.get("changelog", [])) + [
                    {"version": rule_doc["version"], "date": now,
                     "changes": "Updated via intelligence discovery"}
                ]
                await db[RULES_COLLECTION].update_one(
                    {"firm_slug": rule_doc["firm_slug"]}, {"$set": rule_doc}
                )
            else:
                await db[RULES_COLLECTION].insert_one(rule_doc)
            mirrored_slugs.append(rule_doc["firm_slug"])

    saved = await db[CHALLENGES_COLLECTION].find_one(
        {"firm_slug": firm_slug}, {"_id": 0}
    )
    return {"config": saved, "mirrored_plan_slugs": mirrored_slugs}


async def list_firms() -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[CHALLENGES_COLLECTION].find({}, {"_id": 0}).sort("created_at", -1)
    return [d async for d in cursor]


async def get_firm(firm_slug: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[CHALLENGES_COLLECTION].find_one({"firm_slug": firm_slug}, {"_id": 0})


async def delete_firm(firm_slug: str) -> Tuple[int, int]:
    """Delete challenges doc + all mirrored plan rows."""
    db = get_db()
    doc = await db[CHALLENGES_COLLECTION].find_one({"firm_slug": firm_slug})
    plan_slugs = [c["plan_slug"] for c in (doc or {}).get("challenges", []) if "plan_slug" in c]
    removed_plans = 0
    if plan_slugs:
        res = await db[RULES_COLLECTION].delete_many({"firm_slug": {"$in": plan_slugs}})
        removed_plans = res.deleted_count
    r1 = await db[CHALLENGES_COLLECTION].delete_one({"firm_slug": firm_slug})
    return r1.deleted_count, removed_plans
