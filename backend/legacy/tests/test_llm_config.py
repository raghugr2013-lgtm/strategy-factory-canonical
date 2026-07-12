"""
Phase 17 — sanity tests for engines.llm_config.

Pure unit tests — no DB, no LLM calls, no network. Just validates the
abstraction layer reads env correctly and never raises. Each test
isolates `os.environ` via `monkeypatch` so tests are order-independent.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def llm_config(monkeypatch):
    """Provide a freshly-imported `engines.llm_config` with a clean env.

    Strips every LLM-related var so each test starts from zero, then
    yields the module. After the test the fixture is torn down by
    monkeypatch automatically.
    """
    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "EMERGENT_LLM_KEY",
        "MODEL_OPENAI",
        "MODEL_ANTHROPIC",
        "MODEL_DEEPSEEK",
        "LLM_GENERATOR_ENABLED",
        "LLM_ROUTER_ENABLED",
        "LLM_PRIMARY_PROVIDER",
        "LLM_FALLBACK_PROVIDER",
        "LLM_SECONDARY_FALLBACK",
        "LLM_TASK_STRATEGY",
        "LLM_TASK_CBOT",
        "LLM_TASK_MUTATION",
        "LLM_TASK_ANALYSIS",
        "LLM_TASK_INGESTION",
    ):
        monkeypatch.delenv(var, raising=False)
    from engines import llm_config as mod
    return importlib.reload(mod)


def test_flags_default_off(llm_config):
    assert llm_config.is_llm_generator_enabled() is False
    assert llm_config.is_llm_router_enabled() is False


@pytest.mark.parametrize("val,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True),
    ("false", False), ("0", False), ("no", False), ("", False),
])
def test_generator_flag_parsing(monkeypatch, val, expected, llm_config):
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", val)
    assert llm_config.is_llm_generator_enabled() is expected


def test_resolve_provider_returns_none_when_no_keys(llm_config):
    assert llm_config.resolve_provider_for_task("strategy") is None
    cfg = llm_config.get_task_config("strategy")
    assert cfg["resolved_provider"] is None
    assert cfg["api_key"] is None


def test_resolve_uses_primary_when_configured(monkeypatch, llm_config):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    assert llm_config.resolve_provider_for_task("strategy") == "openai"


def test_task_override_beats_primary(monkeypatch, llm_config):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TASK_CBOT", "anthropic")
    assert llm_config.resolve_provider_for_task("cbot") == "anthropic"
    assert llm_config.resolve_provider_for_task("strategy") == "openai"


def test_fallback_chain_when_primary_missing_key(monkeypatch, llm_config):
    # Anthropic is requested, but only OpenAI has a key.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai")
    assert llm_config.resolve_provider_for_task("strategy") == "openai"
    cfg = llm_config.get_task_config("strategy")
    assert cfg["resolved_provider"] == "openai"
    assert cfg["fallback_applied"] is True


def test_get_provider_config_returns_none_for_unconfigured(llm_config):
    assert llm_config.get_provider_config("openai") is None
    assert llm_config.get_provider_config("nonsense") is None


def test_get_provider_config_returns_full_dict(monkeypatch, llm_config):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_OPENAI", "gpt-4o-mini")
    cfg = llm_config.get_provider_config("openai")
    assert cfg == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-test",
    }


def test_validate_environment_shape(monkeypatch, llm_config):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", "true")
    monkeypatch.setenv("LLM_ROUTER_ENABLED", "false")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TASK_CBOT", "anthropic")

    snap = llm_config.validate_environment()
    assert snap["llm_generator_enabled"] is True
    assert snap["llm_router_enabled"] is False
    assert snap["primary_provider"] == "openai"
    assert "openai" in snap["providers"]
    assert snap["providers"]["openai"]["configured"] is True
    assert snap["providers"]["anthropic"]["configured"] is False
    # Task routing — cbot was overridden to anthropic but anthropic has
    # no key, so the resolver should walk the chain back to openai.
    assert snap["task_routing"]["cbot"]["requested"] == "anthropic"
    assert snap["task_routing"]["cbot"]["resolved"] == "openai"
    assert snap["task_routing"]["strategy"]["resolved"] == "openai"
    assert "openai" in snap["fallback_chain"]


def test_existing_emergent_llm_key_unchanged(monkeypatch, llm_config):
    """Sanity: the abstraction does NOT consume EMERGENT_LLM_KEY — it's
    untouched and the legacy modules continue to read it directly."""
    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-emergent-fake")
    snap = llm_config.validate_environment()
    assert snap["emergent_llm_key_present"] is True
    # And the abstraction does not "use" it for routing — without
    # provider keys, providers should still report not configured.
    assert snap["providers"]["openai"]["configured"] is False
