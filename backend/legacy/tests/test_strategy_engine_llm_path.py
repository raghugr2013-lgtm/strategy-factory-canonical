"""
Phase 18 — sanity tests for the LLM activation path in
`engines.strategy_engine.generate_strategy_text`.

Goals:
  * Flag OFF                              → offline path used.
  * Flag ON  + no provider key            → offline path used.
  * Flag ON  + LlmChat raises             → offline path used (fallback).
  * Flag ON  + LLM returns drifted text   → offline path used (validation).
  * Flag ON  + LLM returns valid text     → LLM text returned as-is.

Every test monkey-patches `LlmChat` so we never hit the network.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def strategy_engine(monkeypatch):
    """Fresh strategy_engine module with cleared counters + cleared
    recent-signature buffer + a clean env. Each test re-imports so the
    LLM_STATS counters and signature buffer are isolated.
    """
    for var in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
        "EMERGENT_LLM_KEY", "MODEL_OPENAI", "MODEL_ANTHROPIC",
        "MODEL_DEEPSEEK", "LLM_GENERATOR_ENABLED", "LLM_ROUTER_ENABLED",
        "LLM_PRIMARY_PROVIDER", "LLM_FALLBACK_PROVIDER",
        "LLM_SECONDARY_FALLBACK", "LLM_TASK_STRATEGY",
    ):
        monkeypatch.delenv(var, raising=False)
    # Reload llm_config FIRST so strategy_engine sees a fresh view.
    from engines import llm_config as cfg_mod
    importlib.reload(cfg_mod)
    from engines import strategy_engine as mod
    importlib.reload(mod)
    mod.reset_recent_signatures()
    mod.reset_generation_stats()
    return mod


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Tests ─────────────────────────────────────────────────────────────

def test_flag_off_uses_offline(strategy_engine):
    text = _run(strategy_engine.generate_strategy_text("EURUSD", "H1", ""))
    assert text.startswith("STRATEGY:")
    stats = strategy_engine.get_generation_stats()
    assert stats["llm_disabled"] >= 1
    assert stats["offline_fallback"] >= 1
    assert stats["llm_success"] == 0


def test_flag_on_but_no_key_uses_offline(monkeypatch, strategy_engine):
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", "true")
    # Re-import llm_config + strategy_engine so the new env is observed.
    from engines import llm_config as cfg_mod
    importlib.reload(cfg_mod)
    from engines import strategy_engine as mod
    importlib.reload(mod)
    mod.reset_recent_signatures()
    mod.reset_generation_stats()

    text = _run(mod.generate_strategy_text("EURUSD", "H1", ""))
    assert text.startswith("STRATEGY:")
    stats = mod.get_generation_stats()
    assert stats["llm_disabled"] >= 1, stats
    assert stats["llm_success"] == 0


def test_llm_error_falls_back_to_offline(monkeypatch, strategy_engine):
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TASK_STRATEGY", "openai")
    from engines import llm_config as cfg_mod
    importlib.reload(cfg_mod)
    from engines import strategy_engine as mod
    importlib.reload(mod)
    mod.reset_recent_signatures()
    mod.reset_generation_stats()

    # Patch LlmChat to raise on send_message.
    import emergentintegrations.llm.chat as chat_mod

    class _BoomChat:
        def __init__(self, *a, **kw): pass
        def with_model(self, *a, **kw): return self
        async def send_message(self, *a, **kw):
            raise RuntimeError("simulated provider 503")

    monkeypatch.setattr(chat_mod, "LlmChat", _BoomChat)

    text = _run(mod.generate_strategy_text("EURUSD", "H1", ""))
    assert text.startswith("STRATEGY:")          # offline render kicked in
    stats = mod.get_generation_stats()
    assert stats["llm_error"] == 1, stats
    assert stats["offline_fallback"] == 1
    assert stats["llm_success"] == 0


def test_llm_drift_falls_back_to_offline(monkeypatch, strategy_engine):
    """If the LLM smuggles in a foreign indicator, _has_drift catches it
    and we fall back to the offline path."""
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    from engines import llm_config as cfg_mod
    importlib.reload(cfg_mod)
    from engines import strategy_engine as mod
    importlib.reload(mod)
    mod.reset_recent_signatures()
    mod.reset_generation_stats()

    import emergentintegrations.llm.chat as chat_mod

    class _DriftChat:
        def __init__(self, *a, **kw): pass
        def with_model(self, *a, **kw): return self
        async def send_message(self, *a, **kw):
            # Mention every indicator family — guaranteed drift for any cfg
            # because at least one will not be in the cfg's allowed pool.
            return (
                "STRATEGY: Bad\n"
                "TYPE: trend_following\n"
                "INDICATORS: EMA(9), SMA(20), MACD(12/26/9), RSI(14), "
                "BB(20,2.0), Donchian(20), ATR(14), VWAP, session high\n"
                "ENTRY LONG: x\nENTRY SHORT: y\nEXIT: SL=20 | TP=40\n"
                "PARAMETERS: foo=1\n"
            )

    monkeypatch.setattr(chat_mod, "LlmChat", _DriftChat)

    text = _run(mod.generate_strategy_text("EURUSD", "H1", ""))
    assert text.startswith("STRATEGY:")
    stats = mod.get_generation_stats()
    assert stats["llm_validation_fail"] == 1, stats
    assert stats["offline_fallback"] == 1
    assert stats["llm_success"] == 0


def test_llm_success_returns_llm_text(monkeypatch, strategy_engine):
    """A clean LLM output that mentions only the cfg's indicators is
    returned verbatim — offline renderer is bypassed."""
    monkeypatch.setenv("LLM_GENERATOR_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    from engines import llm_config as cfg_mod
    importlib.reload(cfg_mod)
    from engines import strategy_engine as mod
    importlib.reload(mod)
    mod.reset_recent_signatures()
    mod.reset_generation_stats()

    captured = {}
    import emergentintegrations.llm.chat as chat_mod

    class _GoodChat:
        def __init__(self, api_key, session_id, system_message, **kw):
            captured["api_key"] = api_key
            captured["system"] = system_message

        def with_model(self, provider, model):
            captured["provider"] = provider
            captured["model"] = model
            return self

        async def send_message(self, user_msg):
            captured["user_text"] = getattr(user_msg, "text", str(user_msg))
            # Echo a minimal but valid-looking text. Use ONLY a pattern
            # the validator can accept — RSI is in mean_reversion's pool,
            # session high/low in session_based, etc. We pick a string
            # that mentions ATR (in breakout + volatility_based pools).
            # If the cfg doesn't include ATR, drift fires and the text
            # is rejected — which is fine; the assertion below uses
            # `any` over enough trials.
            return (
                "STRATEGY: LLM Output\n"
                "TYPE: trend_following\n"
                "INDICATORS: EMA(8) / EMA(21)\n"
                "ENTRY LONG: BUY when EMA(8) > EMA(21)\n"
                "ENTRY SHORT: SELL when EMA(8) < EMA(21)\n"
                "EXIT: SL=20 pips | TP=40 pips\n"
                "PARAMETERS: ema_fast=8, ema_slow=21\n"
            )

    monkeypatch.setattr(chat_mod, "LlmChat", _GoodChat)

    # Force a trend_following + EMA cfg so the LLM stub validates.
    # We seed by calling generate repeatedly until we see an LLM success.
    # Across ≤ 25 calls the trend_following/EMA combo will land at least
    # once given the diversity catalogue.
    saw_llm_success = False
    for _ in range(25):
        mod.reset_generation_stats()
        text = _run(mod.generate_strategy_text("EURUSD", "H1", "trend"))
        s = mod.get_generation_stats()
        if s["llm_success"] == 1:
            saw_llm_success = True
            assert text.startswith("STRATEGY: LLM Output")
            assert captured["provider"] == "openai"
            assert captured["model"]            # whatever MODEL_OPENAI default is
            assert captured["api_key"] == "sk-fake"
            break
    assert saw_llm_success, "expected at least one LLM success across 25 trials"
