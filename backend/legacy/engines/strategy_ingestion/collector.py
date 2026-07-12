"""External-source collectors for the ingestion pipeline.

No scraping of entire platforms. All collectors are rate-bounded and
safe to run unauthenticated. Optional `GITHUB_TOKEN` env var lifts the
GitHub rate limit when present.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ── File + path policies ─────────────────────────────────────────────

ALLOWED_EXTENSIONS = (".pine", ".mq5", ".mq4", ".py", ".pinescript")
MAX_FILE_BYTES = 40_000          # skip anything huge
MAX_FILES_PER_REPO = 3

# Static TradingView URL list — the user MUST update this file to add
# new sources; we never crawl beyond it.
TRADINGVIEW_URLS_FILE = Path(__file__).parent / "tradingview_urls.json"

# Built-in GitHub seed queries. Used alongside any user-supplied ones.
DEFAULT_GITHUB_QUERIES: List[str] = [
    "pine script strategy forex",
    "mt5 expert advisor forex",
    "forex trading strategy python",
]


# ── GitHub ───────────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"


def _github_headers() -> Dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-strategy-factory-ingestion/1.0",
    }
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


async def _github_search_repos(
    query: str, *, per_page: int = 5, timeout: float = 12.0,
) -> List[dict]:
    """Repo search (unauth-friendly). Returns up to `per_page` repos."""
    params = {"q": query, "sort": "updated", "order": "desc", "per_page": per_page}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(
                f"{GITHUB_API}/search/repositories",
                headers=_github_headers(), params=params,
            )
            if r.status_code == 403:
                logger.warning("github rate-limited (403) on repo search")
                return []
            r.raise_for_status()
            return (r.json() or {}).get("items", [])[:per_page]
    except httpx.HTTPError as e:
        logger.warning("github repo search failed: %s", e)
        return []


async def _github_list_files(
    repo_full_name: str, *, timeout: float = 12.0,
) -> List[dict]:
    """Return flattened tree of files (first branch only)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Default branch
            meta = await client.get(
                f"{GITHUB_API}/repos/{repo_full_name}",
                headers=_github_headers(),
            )
            if meta.status_code != 200:
                return []
            branch = (meta.json() or {}).get("default_branch", "main")

            # Tree (recursive)
            tr = await client.get(
                f"{GITHUB_API}/repos/{repo_full_name}/git/trees/{branch}",
                headers=_github_headers(), params={"recursive": "1"},
            )
            if tr.status_code != 200:
                return []
            return (tr.json() or {}).get("tree", [])
    except httpx.HTTPError as e:
        logger.debug("github list-files failed for %s: %s", repo_full_name, e)
        return []


async def _github_fetch_blob(url: str, *, timeout: float = 12.0) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=_github_headers())
            if r.status_code != 200:
                return None
            data = r.json() or {}
            if data.get("encoding") == "base64" and data.get("content"):
                try:
                    return base64.b64decode(data["content"]).decode("utf-8", "replace")
                except Exception:
                    return None
            if data.get("download_url"):
                raw = await client.get(data["download_url"], headers=_github_headers())
                if raw.status_code == 200:
                    return raw.text
    except httpx.HTTPError as e:
        logger.debug("github fetch blob failed: %s", e)
    return None


async def collect_from_github(
    *,
    queries: Optional[List[str]] = None,
    max_total: int = 10,
    per_query_repos: int = 3,
) -> List[Dict[str, object]]:
    """Return up to `max_total` raw code snippets from matching repos.

    Each entry: {source: 'github', name, raw_code, url, repo, path, ext}.
    """
    queries = list(queries or DEFAULT_GITHUB_QUERIES)
    out: List[Dict[str, object]] = []
    seen_urls: set = set()

    for q in queries:
        if len(out) >= max_total:
            break
        repos = await _github_search_repos(q, per_page=per_query_repos)
        for repo in repos:
            if len(out) >= max_total:
                break
            full = repo.get("full_name")
            if not full:
                continue
            tree = await _github_list_files(full)
            picked = 0
            for node in tree:
                if picked >= MAX_FILES_PER_REPO or len(out) >= max_total:
                    break
                if node.get("type") != "blob":
                    continue
                path = node.get("path", "")
                lower = path.lower()
                if not lower.endswith(ALLOWED_EXTENSIONS):
                    continue
                size = node.get("size") or 0
                if size <= 0 or size > MAX_FILE_BYTES:
                    continue
                blob_url = node.get("url")
                if not blob_url or blob_url in seen_urls:
                    continue
                code = await _github_fetch_blob(blob_url)
                if not code or len(code) < 80:
                    continue
                seen_urls.add(blob_url)
                ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
                out.append({
                    "source": "github",
                    "name": f"{full}/{path}",
                    "raw_code": code,
                    "url": f"https://github.com/{full}/blob/{repo.get('default_branch', 'main')}/{path}",
                    "repo": full,
                    "path": path,
                    "ext": ext,
                })
                picked += 1
    return out


# ── TradingView (static URL list, rate-bounded) ──────────────────────

_PINE_BLOCK_RE = re.compile(
    r"//@version\s*=\s*\d+.*?(?=\Z|//@version\s*=\s*\d+)",
    re.DOTALL | re.IGNORECASE,
)
_PINE_FENCE_RE = re.compile(
    r"```(?:pine|pinescript|tradingview)?\s*(//@version[\s\S]+?)```",
    re.IGNORECASE,
)


def _read_tradingview_urls() -> List[str]:
    if not TRADINGVIEW_URLS_FILE.exists():
        return []
    try:
        data = json.loads(TRADINGVIEW_URLS_FILE.read_text())
        return [str(u) for u in (data.get("urls") or []) if isinstance(u, str)]
    except Exception as e:
        logger.warning("failed to read tradingview_urls.json: %s", e)
        return []


async def collect_from_tradingview(
    *, max_total: int = 5, timeout: float = 12.0,
) -> List[Dict[str, object]]:
    urls = _read_tradingview_urls()
    if not urls:
        return []
    out: List[Dict[str, object]] = []
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": "ai-strategy-factory-ingestion/1.0"},
    ) as client:
        for u in urls[: max_total * 2]:
            if len(out) >= max_total:
                break
            try:
                r = await client.get(u)
            except httpx.HTTPError as e:
                logger.debug("tradingview fetch failed for %s: %s", u, e)
                continue
            if r.status_code != 200:
                continue
            html = r.text
            # Prefer fenced code blocks, fall back to bare //@version blocks
            blocks = _PINE_FENCE_RE.findall(html) or _PINE_BLOCK_RE.findall(html)
            for b in blocks[:2]:
                code = b.strip()
                if len(code) < 80 or len(code) > MAX_FILE_BYTES:
                    continue
                out.append({
                    "source": "tradingview",
                    "name": f"tradingview::{u}",
                    "raw_code": code,
                    "url": u,
                    "ext": ".pine",
                })
                if len(out) >= max_total:
                    break
    return out


# ── Local queue (manual paste) ───────────────────────────────────────

def collect_from_local_queue(local_queue: Iterable[Dict[str, str]]) -> List[Dict[str, object]]:
    """Normalise entries from the in-memory / DB local queue into the
    collector output shape."""
    out: List[Dict[str, object]] = []
    for entry in list(local_queue or []):
        code = (entry.get("raw_code") or "").strip()
        if not code or len(code) < 60:
            continue
        out.append({
            "source": entry.get("source") or "local",
            "name": entry.get("name") or "local::manual",
            "raw_code": code,
            "url": entry.get("url"),
            "ext": entry.get("ext") or "",
        })
    return out
