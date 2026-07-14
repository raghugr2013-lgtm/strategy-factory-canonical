"""VIE-aware shim for legacy `engines.llm_config`.

Original v01 file: 420 lines. Held provider tables, task→provider routing,
`EMERGENT_LLM_KEY` fallback, and validation helpers. Replaced in Phase 1A
by a thin adapter that treats VIE as the single provider fabric — VIE
itself owns provider selection + failover.

Public API preserved so legacy callers work without modification:
    def is_llm_generator_enabled() -> bool
    def is_llm_router_enabled() -> bool
    def is_auto_failover_enabled() -> bool
    def resolve_provider_for_task(task: str) -> Optional[str]
    def get_provider_config(provider: str) -> Optional[Dict[str, str]]
    def get_task_config(task: str) -> Dict[str, Optional[str]]
    def validate_environment() -> Dict[str, object]
    def get_failover_chain_for_task(task: str) -> List[Dict[str, str]]
    async def log_llm_call(...)

Vendor-independence contract: this module never reads
EMERGENT_LLM_KEY. All decisions come from `VIE /providers` (queried
lazily) or plain env vars used by VIE itself.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Task → ordered provider preference. Mirrors the recovery-bundle
# `vie/router.py` mapping so on-behavior lands identically whether the
# caller uses VIE directly or reaches it through this shim.
_TASK_PREFERENCE: Dict[str, List[str]] = {
    "strategy":   ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"],
    "research":   ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "description": ["gemini", "openai", "anthropic", "deepseek", "groq", "kimi"],
    "default":    ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"],
}

# Provider → default model. Kept aligned with vie/providers/*_p.py defaults.
_PROVIDER_DEFAULT_MODEL: Dict[str, str] = {
    "openai":    os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
    "anthropic": os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929",
    "gemini":    os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
    "deepseek":  os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat",
    "groq":      os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile",
    "kimi":      os.environ.get("KIMI_MODEL") or "kimi-k2",
}

_PROVIDER_KEY_ENV: Dict[str, str] = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "deepseek":  "DEEPSEEK_API_KEY",
    "groq":      "GROQ_API_KEY",
    "kimi":      "KIMI_API_KEY",
}


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _vie_url() -> str:
    return (os.environ.get("VIE_URL") or "http://127.0.0.1:8100").rstrip("/")


# ── Cached VIE provider snapshot ────────────────────────────────────
# We ping VIE once and cache the result for `_TTL_S` seconds. The whole
# module falls back gracefully to "no providers" if VIE is unreachable —
# strategy_engine already handles that path (offline renderer wins).

_CACHE: Dict[str, Any] = {"snapshot": None, "ts": 0.0}
_TTL_S = 30.0


def _providers_snapshot() -> List[Dict[str, Any]]:
    now = time.time()
    if _CACHE["snapshot"] is not None and (now - _CACHE["ts"]) < _TTL_S:
        return _CACHE["snapshot"]
    try:
        r = httpx.get(_vie_url() + "/providers", timeout=3.0)
        r.raise_for_status()
        snap = r.json().get("providers") or []
    except Exception as e:  # noqa: BLE001
        logger.debug("VIE /providers unreachable: %s", e)
        snap = []
    _CACHE["snapshot"] = snap
    _CACHE["ts"] = now
    return snap


def _available_provider_names() -> List[str]:
    return [p["name"] for p in _providers_snapshot() if p.get("available")]


# ── Public API ──────────────────────────────────────────────────────

def is_llm_generator_enabled() -> bool:
    """LLM strategy generation is enabled ONLY when both:
      1. The `LLM_GENERATOR_ENABLED` env flag is truthy.
      2. At least one VIE provider is currently available.
    Without both, callers should treat this as "off" and use their
    offline fallback (which strategy_engine already does).
    """
    if not _flag("LLM_GENERATOR_ENABLED", True):
        return False
    return bool(_available_provider_names())


def is_llm_router_enabled() -> bool:
    # VIE always routes internally; this shim just reports "yes" so
    # any legacy check for "is the router live" evaluates truthy.
    return True


def is_auto_failover_enabled() -> bool:
    # VIE performs failover across providers by design.
    return True


def _resolve_provider(task: str) -> Optional[str]:
    avail = _available_provider_names()
    if not avail:
        return None
    pref = _TASK_PREFERENCE.get(task) or _TASK_PREFERENCE["default"]
    for p in pref:
        if p in avail:
            return p
    return avail[0]


def resolve_provider_for_task(task: str) -> Optional[str]:
    return _resolve_provider(task)


def get_provider_config(provider: str) -> Optional[Dict[str, str]]:
    """Return `{name, model, key_env}` for the given provider name, or
    None if the provider isn't known.

    IMPORTANT: `api_key` is intentionally the string "VIE" (a marker)
    rather than the real key — strategy_engine and other callers only
    check truthiness of this field before proceeding.
    """
    provider = provider.lower().strip()
    if provider not in _PROVIDER_DEFAULT_MODEL:
        return None
    return {
        "name": provider,
        "model": _PROVIDER_DEFAULT_MODEL[provider],
        "key_env": _PROVIDER_KEY_ENV[provider],
        "api_key": "VIE",  # non-empty marker → legacy truthy check passes
    }


def get_task_config(task: str) -> Dict[str, Optional[str]]:
    """Return the resolved provider+model+key marker for `task`.

    Legacy strategy_engine._try_llm_generation reads:
        api_key = task_cfg.get("api_key")           # truthy → proceed
        provider = task_cfg.get("resolved_provider")# non-empty → proceed
        model = task_cfg.get("model")               # non-empty → proceed
    """
    provider = _resolve_provider(task)
    if not provider:
        return {"resolved_provider": None, "model": None, "api_key": None}
    return {
        "resolved_provider": provider,
        "model": _PROVIDER_DEFAULT_MODEL[provider],
        "api_key": "VIE",
    }


def get_failover_chain_for_task(task: str) -> List[Dict[str, str]]:
    """Preferred chain restricted to currently-available providers."""
    avail = _available_provider_names()
    pref = _TASK_PREFERENCE.get(task) or _TASK_PREFERENCE["default"]
    return [
        {"name": p, "model": _PROVIDER_DEFAULT_MODEL[p]}
        for p in pref
        if p in avail
    ]


def validate_environment() -> Dict[str, object]:
    """Diagnostic summary — used by legacy `/api/llm/diagnostics`. Safe
    to call even when VIE is unreachable.

    v1.1.1 additions (never removed the previous keys — additive only):
      * ``primary_provider``  — resolved routing head for `default` task.
        Prefer whatever VIE reports as available, else the first provider
        whose direct API-key env var is set. ``None`` if nothing is
        configured.
      * ``providers`` (dict)  — {name: {configured: bool, model: str,
        vie_available: bool, key_env: str}}. The frontend AI Workforce
        panel keys off this so it can render the correct "no key
        configured" vs "openai · gpt-4o-mini" state even when VIE itself
        is offline.
      * ``vie_reachable`` (bool) — did VIE answer /providers this cycle?
    """
    snap = _providers_snapshot()
    vie_reachable = len(snap) > 0

    # Build the per-provider dict. Prefer VIE snapshot info when present,
    # fall back to env-var probing so the panel isn't blank when VIE
    # is temporarily unreachable.
    providers: Dict[str, Dict[str, Any]] = {}
    snap_by_name = {p.get("name"): p for p in snap if p.get("name")}
    for name, key_env in _PROVIDER_KEY_ENV.items():
        via_vie = snap_by_name.get(name) or {}
        key_present = bool(os.environ.get(key_env))
        providers[name] = {
            "configured": bool(via_vie.get("available") or key_present),
            "model": via_vie.get("model") or _PROVIDER_DEFAULT_MODEL.get(name),
            "vie_available": bool(via_vie.get("available")),
            "key_env": key_env,
            "key_present": key_present,
        }

    # Primary provider = first entry in the default-task chain that is
    # actually configured. VIE-reported availability wins over key_present.
    primary_provider: Optional[str] = None
    for cand in _TASK_PREFERENCE.get("default", []):
        info = providers.get(cand) or {}
        if info.get("configured"):
            primary_provider = cand
            break

    return {
        "flag_enabled": _flag("LLM_GENERATOR_ENABLED", True),
        "vie_url": _vie_url(),
        "vie_reachable": vie_reachable,
        "providers_total": len(snap),
        "providers_available": len([p for p in snap if p.get("available")]),
        "available": [p["name"] for p in snap if p.get("available")],
        "task_preference": _TASK_PREFERENCE,
        "primary_provider": primary_provider,
        "providers": providers,
    }


async def log_llm_call(
    task: str,
    provider: str,
    model: str,
    ok: bool,
    latency_ms: int,
    error: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Best-effort telemetry log — writes to `llm_call_log` collection
    when Mongo is reachable. Never raises (silent on failure)."""
    try:
        from engines.db import get_db  # local import — avoids cycles
        db = get_db()
        await db.llm_call_log.insert_one({
            "task": task,
            "provider": provider,
            "model": model,
            "ok": bool(ok),
            "latency_ms": int(latency_ms),
            "error": error,
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "ts": int(time.time()),
        })
    except Exception as e:  # noqa: BLE001
        logger.debug("log_llm_call failed: %s", e)
