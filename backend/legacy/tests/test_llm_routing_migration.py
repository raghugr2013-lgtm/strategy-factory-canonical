"""Phase 30.3 — LLM routing migration trust gate.

Tiers:
  T1  Router public surface (known tasks, fallback chain)
  T2  .env config invariants (auto_failover OFF, model versions)
  T3  Call-site migration (no hard-bound EMERGENT_LLM_KEY residues)
  T4  Diagnostics endpoint shape + admin gate
  T5  Anti-drift — audit-log write infra exists; no autonomous failover
"""
from __future__ import annotations

import sys

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from engines import llm_config as lc  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Tier T1 — Router public surface
# ────────────────────────────────────────────────────────────────────

class TestT1RouterSurface:

    def test_known_tasks_includes_propfirm_and_description(self):
        assert "propfirm" in lc._KNOWN_TASKS
        assert "description" in lc._KNOWN_TASKS

    def test_anthropic_default_model_is_current_sonnet(self):
        # Phase 30.3 bumps MODEL_ANTHROPIC default to claude-sonnet-4-5.
        # The .env override should be in effect, but the registry's
        # built-in default must also reflect current Anthropic naming.
        for entry in lc._PROVIDERS:
            if entry[0] == "anthropic":
                assert entry[3].startswith("claude-sonnet-4")
                return
        pytest.fail("anthropic entry missing from _PROVIDERS")

    def test_get_task_config_resolves_propfirm_to_anthropic(self):
        cfg = lc.get_task_config("propfirm")
        assert cfg["resolved_provider"] == "anthropic"
        # api_key must be present (operator uploaded ANTHROPIC_API_KEY).
        assert cfg["api_key"] is not None

    def test_get_task_config_resolves_analysis_to_anthropic(self):
        cfg = lc.get_task_config("analysis")
        assert cfg["resolved_provider"] == "anthropic"

    def test_get_failover_chain_single_element_when_disabled(self):
        # Operator decree: LLM_AUTO_FAILOVER=false during early observation.
        chain = lc.get_failover_chain_for_task("strategy")
        assert lc.is_auto_failover_enabled() is False
        assert len(chain) == 1
        assert chain[0]["resolved_provider"] == "openai"


# ────────────────────────────────────────────────────────────────────
# Tier T2 — .env config invariants
# ────────────────────────────────────────────────────────────────────

class TestT2EnvInvariants:

    def test_auto_failover_default_off(self):
        assert lc.is_auto_failover_enabled() is False

    def test_three_providers_all_configured(self):
        env = lc.validate_environment()
        for prov in ("openai", "anthropic", "deepseek"):
            assert env["providers"][prov]["configured"] is True, (
                f"{prov} missing api_key in .env"
            )


# ────────────────────────────────────────────────────────────────────
# Tier T3 — Call-site migration audit
# ────────────────────────────────────────────────────────────────────

class TestT3MigrationAudit:
    """Every migrated call site must route through get_task_config()
    and must NOT hardcode emergent-key fallbacks anymore."""

    MIGRATED_FILES = (
        "/app/backend/engines/strategy_ingestion/parser.py",
        "/app/backend/engines/prop_firm_intelligence.py",
        "/app/backend/engines/prop_firm_config_engine.py",
        "/app/backend/engines/strategy_description.py",
    )

    def test_migrated_files_use_get_task_config(self):
        for path in self.MIGRATED_FILES:
            src = open(path, "r", encoding="utf-8").read()
            assert "get_task_config" in src, f"{path} not migrated to router"

    def test_migrated_files_have_no_emergent_llm_key_read(self):
        for path in self.MIGRATED_FILES:
            src = open(path, "r", encoding="utf-8").read()
            # Allow comments / docstrings to mention EMERGENT_LLM_KEY,
            # but no actual environment read.
            assert 'os.environ.get("EMERGENT_LLM_KEY")' not in src, (
                f"{path} still reads EMERGENT_LLM_KEY directly"
            )

    def test_migrated_files_emit_audit_log_calls(self):
        """Each migrated call site must guarantee `log_llm_call` is emitted
        for every LLM attempt. As of Phase A.4 (2026 audit), the audit
        write is performed inside `engines.llm_runner` for any call site
        that delegates to `run_chat`. The discipline is satisfied if the
        file either calls `log_llm_call` directly OR routes through
        `llm_runner.run_chat` (which performs the audit write itself).
        """
        for path in self.MIGRATED_FILES:
            src = open(path, "r", encoding="utf-8").read()
            has_direct = "log_llm_call" in src
            uses_runner = (
                "llm_runner" in src
                or "from engines.llm_runner" in src
                or "engines.llm_runner.run_chat" in src
            )
            assert has_direct or uses_runner, (
                f"{path} neither emits log_llm_call directly nor routes "
                f"through llm_runner (Phase 30.3 / A.4 audit discipline)"
            )


# ────────────────────────────────────────────────────────────────────
# Tier T4 — Diagnostics endpoint
# ────────────────────────────────────────────────────────────────────

class TestT4Diagnostics:

    def test_endpoints_declared(self):
        from api.llm_diagnostics import router
        paths = [r.path for r in router.routes]
        assert "/llm/diagnostics"       in paths
        assert "/llm/call-log/recent"   in paths

    def test_diagnostics_is_get_only(self):
        from api.llm_diagnostics import router
        for r in router.routes:
            if r.path == "/llm/diagnostics":
                assert "GET" in r.methods
                assert not (r.methods & {"POST", "PUT", "PATCH", "DELETE"})
                return
        pytest.fail("/llm/diagnostics not declared")

    def test_call_log_endpoint_is_admin_gated(self):
        from api.llm_diagnostics import router
        for r in router.routes:
            if r.path == "/llm/call-log/recent":
                deps = [d.call.__name__ for d in r.dependant.dependencies if hasattr(d, "call")]
                assert "require_admin" in deps
                return
        pytest.fail("/llm/call-log/recent not declared")

    def test_diagnostics_payload_omits_keys(self):
        env = lc.validate_environment()
        for prov, info in env["providers"].items():
            assert "api_key" not in info, (
                f"validate_environment leaks key material for {prov}"
            )


# ────────────────────────────────────────────────────────────────────
# Tier T5 — Anti-drift
# ────────────────────────────────────────────────────────────────────

class TestT5AntiDrift:

    def test_log_llm_call_is_subordinate_never_raises(self):
        """log_llm_call must always be wrapped in try/except — calling
        it with bad args or no DB must not raise."""
        # Calling outside event loop is fine because the function returns
        # a coroutine; we only need to confirm the source-shape contract.
        import inspect
        src = inspect.getsource(lc.log_llm_call)
        assert "try:" in src
        assert "except Exception" in src
        assert "return None" in src

    def test_audit_log_collection_name_constant(self):
        assert lc.LLM_CALL_LOG_COLLECTION == "llm_call_log"

    def test_failover_chain_respects_disabled_flag(self):
        chain = lc.get_failover_chain_for_task("strategy")
        # Disabled → single provider only (operator decree).
        assert len(chain) == 1
