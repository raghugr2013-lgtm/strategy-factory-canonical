"""Phase 2, Stage 1 — VIE hardening tests.

Verifies:
  * router.py DEFAULT_TASK_MAP contains the 6 UKIE-parser tasks
  * VIEClient.generate honours `provider_hint` when the flag is on
  * VIEClient does NOT honour `provider_hint` when the flag is off
    (backwards compatibility)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_task_map_extended_with_ukie_tasks():
    # /app/vie is on sys.path in the VIE container; here we import the
    # module by absolute path.
    vie_dir = Path("/app/vie")
    if not (vie_dir / "router.py").exists():
        pytest.skip("VIE package not present in this checkout")
    if str(vie_dir.parent) not in sys.path:
        sys.path.insert(0, str(vie_dir.parent))
    from vie.router import DEFAULT_TASK_MAP  # type: ignore
    for t in [
        "parse_strategy_code",
        "parse_paper_abstract",
        "parse_indicator_definition",
        "parse_market_note",
        "parse_execution_rule",
    ]:
        assert t in DEFAULT_TASK_MAP, f"missing task: {t}"
        assert isinstance(DEFAULT_TASK_MAP[t], list) and DEFAULT_TASK_MAP[t]


@pytest.mark.asyncio
async def test_provider_hint_honoured_when_flag_on(monkeypatch):
    monkeypatch.setenv("VIE_PROVIDER_HINT_RESPECT", "true")
    from app.vie.client import VIEClient  # type: ignore

    client = VIEClient(base_url="http://vie.test", timeout_s=1)
    posted = {}

    async def fake_post(path, body):
        posted["body"] = body
        return {"provider": body.get("provider", "unknown"), "model": "x", "output": "ok", "usage": {}}

    client._post = fake_post  # type: ignore

    await client.generate(prompt="hi", task="generation", provider_hint="anthropic")
    assert posted["body"].get("provider") == "anthropic"


@pytest.mark.asyncio
async def test_provider_hint_ignored_when_flag_off(monkeypatch):
    monkeypatch.setenv("VIE_PROVIDER_HINT_RESPECT", "false")
    from app.vie.client import VIEClient  # type: ignore

    client = VIEClient(base_url="http://vie.test", timeout_s=1)
    posted = {}

    async def fake_post(path, body):
        posted["body"] = body
        return {"provider": "auto", "model": "x", "output": "ok", "usage": {}}

    client._post = fake_post  # type: ignore

    await client.generate(prompt="hi", task="generation", provider_hint="anthropic")
    # Flag off → provider must NOT appear in body
    assert "provider" not in posted["body"]


@pytest.mark.asyncio
async def test_explicit_provider_wins_over_hint(monkeypatch):
    monkeypatch.setenv("VIE_PROVIDER_HINT_RESPECT", "true")
    from app.vie.client import VIEClient  # type: ignore

    client = VIEClient(base_url="http://vie.test", timeout_s=1)
    posted = {}

    async def fake_post(path, body):
        posted["body"] = body
        return {"provider": body.get("provider"), "model": "x", "output": "ok", "usage": {}}

    client._post = fake_post  # type: ignore

    # Explicit `provider="openai"` overrides `provider_hint="anthropic"`
    await client.generate(prompt="hi", provider="openai", provider_hint="anthropic")
    assert posted["body"].get("provider") == "openai"
