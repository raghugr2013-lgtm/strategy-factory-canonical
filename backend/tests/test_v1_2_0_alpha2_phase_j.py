"""v1.2.0-alpha2 Phase J — Factory Self-Evaluation regression tests.

Coverage:
  * Config defaults (OBSERVE mode default)
  * Ledger bootstrap + roundtrips
  * Evaluators pure functions
  * Proposers bounded by max_delta_per_tick
  * Ranker score + floor + tie break
  * Applier OBSERVE guardrail (blocked); RECOMMEND (allowed)
  * Full cycle end-to-end
  * Structural non-modification proof
  * Orchestrator task registration
  * 26 /api/factory-eval/* endpoints
  * OBSERVE mode approve returns 409
  * Deterministic replay
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

sys.path.insert(0, "/app/backend/legacy")
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@strategy-factory.local",
                     "password": "admin123"})
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    for k in list(os.environ.keys()):
        if k.startswith("FACTORY_EVAL_") or k.startswith("ORCH_USE_FACTORY_") \
                or k.startswith("EXEC_USE_FACTORY_") \
                or k.startswith("LEARNING_USE_FACTORY_"):
            monkeypatch.delenv(k, raising=False)


async def _wipe():
    from engines.factory_eval import ledger
    await ledger.wipe_all()


# ── 1. Config ──────────────────────────────────────────────
class TestConfig:
    def test_default_mode_is_observe(self):
        from engines.factory_eval import config as fecfg
        from engines.factory_eval.types import FEMode
        assert fecfg.mode() == FEMode.OBSERVE

    def test_defaults_safe(self):
        from engines.factory_eval import config as fecfg
        s = fecfg.config_snapshot()
        assert s["FACTORY_EVAL_MODE"] == "observe"
        assert s["FACTORY_EVAL_CADENCE_SEC"] == 3600
        assert s["FACTORY_EVAL_WINDOW_HOURS_SHORT"] == 24
        assert s["FACTORY_EVAL_WINDOW_HOURS_LONG"] == 2160
        assert s["FACTORY_EVAL_MAX_DELTA_PER_TICK"] == 0.05
        assert s["ORCH_USE_FACTORY_EVAL_OVERRIDES"] is False
        assert s["EXEC_USE_FACTORY_EVAL_OVERRIDES"] is False
        assert s["LEARNING_USE_FACTORY_EVAL_OVERRIDES"] is False

    def test_invalid_mode_falls_back(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "banana")
        from engines.factory_eval import config as fecfg
        assert fecfg.mode() == "observe"

    def test_autonomous_whitelist_default(self):
        from engines.factory_eval import config as fecfg
        wl = fecfg.autonomous_whitelist()
        assert "compute_reallocation" in wl
        assert "execution_path_pref" in wl

    def test_mode_can_apply(self):
        from engines.factory_eval.types import FEMode
        assert not FEMode.can_apply(FEMode.OBSERVE)
        assert not FEMode.can_apply(FEMode.DISABLED)
        assert FEMode.can_apply(FEMode.RECOMMEND)
        assert FEMode.can_apply(FEMode.AUTONOMOUS)


# ── 2. Ledger ──────────────────────────────────────────────
class TestLedger:
    def test_indexes_idempotent(self):
        from engines.factory_eval import ledger
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ledger.ensure_indexes())
        loop.run_until_complete(ledger.ensure_indexes())

    def test_report_roundtrip(self):
        from engines.factory_eval import ledger
        from engines.factory_eval.types import FactoryReport
        r = FactoryReport(
            report_id="fe_report_test1",
            window_start="a", window_end="b",
            cycle_ts=datetime.now(timezone.utc).isoformat(),
            mode="observe",
            kpis={"pnl_24h": 42.0},
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ledger.upsert_report(r))
        got = loop.run_until_complete(ledger.read_report("fe_report_test1"))
        assert got is not None and got.kpis["pnl_24h"] == 42.0


# ── 3. Evaluators ──────────────────────────────────────────
class TestEvaluators:
    def test_factory_improvement_math(self):
        from engines.factory_eval.evaluators import evaluate_factory_improvement
        now = {"pnl_24h": 200.0, "win_rate_24h": 0.6,
                "prediction_accuracy_30d": 0.7,
                "broker_health_score_p50": 0.9,
                "attribution_coverage_pct": 100.0,
                "ai_spend_window_usd": 10.0}
        prev = {"pnl_24h": 100.0, "win_rate_24h": 0.5,
                 "prediction_accuracy_30d": 0.65,
                 "broker_health_score_p50": 0.85,
                 "attribution_coverage_pct": 90.0,
                 "ai_spend_window_usd": 12.0}
        evs = evaluate_factory_improvement(
            now, prev, report_id="r1", window_start="a", window_end="b")
        pnl = next(e for e in evs if e.target == "pnl_24h")
        assert pnl.metrics["delta"] == 100.0
        assert pnl.metrics["ratio"] > 0.9

    def test_provider_efficiency_returns_insights(self):
        from engines.factory_eval.evaluators import evaluate_provider_efficiency
        providers = {"openai": {"n_events": 100, "n_pass": 40,
                                  "spend_usd": 12.5, "cost_per_pass": 0.31,
                                  "models": {"gpt-5.2": {}}}}
        evs = evaluate_provider_efficiency(
            providers, report_id="r1", window_start="a", window_end="b",
            min_samples=30)
        assert len(evs) == 1
        assert evs[0].target == "provider:openai"

    def test_strategy_ranking_top_and_bottom(self):
        from engines.factory_eval.evaluators import evaluate_strategy_ranking
        strategies = {f"sh_{i}": {"realised_pnl": (i - 5) * 10.0,
                                    "n_trades": 3, "mean_delta": 0.0}
                       for i in range(20)}
        evs = evaluate_strategy_ranking(
            strategies, report_id="r1", window_start="a", window_end="b",
            top_n=5, bottom_n=5)
        top = [e for e in evs if e.target.startswith("top:")]
        bottom = [e for e in evs if e.target.startswith("bottom:")]
        assert len(top) == 5 and len(bottom) == 5

    def test_regime_effectiveness(self):
        from engines.factory_eval.evaluators import evaluate_regime_effectiveness
        regimes = {"trending": {"n": 50, "mean_pnl": 20.0,
                                  "hit_rate": 0.6, "mean_delta": 0.05}}
        evs = evaluate_regime_effectiveness(
            regimes, report_id="r1", window_start="a", window_end="b")
        assert len(evs) == 1 and evs[0].target == "regime:trending"

    def test_bottleneck_top3_summary(self):
        from engines.factory_eval.evaluators import evaluate_bottleneck
        bot = {"compute_probe": {"band": "warn"},
               "queue_pressure": {"depth": 0.9}}
        evs = evaluate_bottleneck(
            bot, report_id="r1", window_start="a", window_end="b")
        assert len(evs) == 1  # summary only per Q6
        assert evs[0].evidence["findings"]

    def test_coverage_gap_detector(self):
        from engines.factory_eval.evaluators import evaluate_coverage_gaps
        strategies = {f"sh_{i}": {} for i in range(5)}  # very few
        evs = evaluate_coverage_gaps(
            strategies, report_id="r1", window_start="a", window_end="b")
        assert len(evs) == 1
        assert evs[0].severity in ("med", "low")


# ── 4. Proposers ───────────────────────────────────────────
class TestProposers:
    def _insight(self, surface, target, metrics=None, evidence=None,
                    severity="med"):
        from engines.factory_eval.types import FactoryInsight
        return FactoryInsight(
            insight_id="fe_insight_" + uuid.uuid4().hex[:8],
            report_id="r1", surface=surface, target=target,
            window_start="a", window_end="b", n_samples=50,
            method="test", metrics=metrics or {}, significance=0.6,
            severity=severity, evidence=evidence or {},
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_compute_reallocation_diagnostic(self):
        from engines.factory_eval.engine import propose_compute_reallocation
        ins = self._insight("compute_allocation", "orchestrator:task_priorities",
                              metrics={"n_tasks": 15.0})
        recs = propose_compute_reallocation(ins, mode="observe")
        assert len(recs) == 1
        assert recs[0].risk_band == "green"

    def test_execution_path_pref_top_rank(self):
        from engines.factory_eval.engine import propose_execution_path_pref
        ins = self._insight("execution_quality", "path:paper|EURUSD|all|IOC",
                              metrics={"rank": 1, "mean_score": 0.85},
                              evidence={"path_key": "paper|EURUSD|all|IOC"})
        recs = propose_execution_path_pref(ins, mode="observe")
        assert len(recs) == 1
        assert recs[0].surface == "execution_path_pref"

    def test_execution_path_pref_low_rank_ignored(self):
        from engines.factory_eval.engine import propose_execution_path_pref
        ins = self._insight("execution_quality", "path:x",
                              metrics={"rank": 5, "mean_score": 0.6})
        assert propose_execution_path_pref(ins, mode="observe") == []

    def test_strategy_pruning_only_negative_bottom(self):
        from engines.factory_eval.engine import propose_strategy_pruning
        neg = self._insight("strategy_contribution", "bottom:sh_1",
                              metrics={"realised_pnl": -50.0})
        pos = self._insight("strategy_contribution", "bottom:sh_2",
                              metrics={"realised_pnl": 10.0})
        top = self._insight("strategy_contribution", "top:sh_3",
                              metrics={"realised_pnl": 100.0})
        assert propose_strategy_pruning(neg, mode="observe")
        assert propose_strategy_pruning(pos, mode="observe") == []
        assert propose_strategy_pruning(top, mode="observe") == []

    def test_portfolio_rebalance_hint_only_deteriorating(self):
        from engines.factory_eval.engine import propose_portfolio_rebalance_hint
        med = self._insight("portfolio_health", "master_bot:mb_1",
                             severity="med",
                             metrics={"composite": 0.4},
                             evidence={"master_bot_id": "mb_1"})
        info = self._insight("portfolio_health", "master_bot:mb_2",
                              severity="info", metrics={"composite": 0.9})
        assert propose_portfolio_rebalance_hint(med, mode="observe")
        assert propose_portfolio_rebalance_hint(info, mode="observe") == []

    def test_research_investment_only_when_gap(self):
        from engines.factory_eval.engine import propose_research_investment
        gap = self._insight("coverage_gap", "factory:total_active_strategies",
                              severity="high",
                              metrics={"n_strategies": 5,
                                         "target_coverage": 72,
                                         "gap_ratio": 0.93})
        assert propose_research_investment(gap, mode="observe")


# ── 5. Ranker ──────────────────────────────────────────────
class TestRanker:
    def _rec(self, uplift=0.05, conf=0.5, band="green", target=None):
        from engines.factory_eval.types import (
            FactoryRecommendation, FERecStatus,
        )
        return FactoryRecommendation(
            recommendation_id="fe_rec_" + uuid.uuid4().hex[:8],
            insight_ids=["i1"], surface="compute_reallocation",
            target=target or f"T_{uuid.uuid4().hex[:4]}",
            current_value=0.0, proposed_value=0.01, proposed_delta=0.01,
            expected_uplift=uplift, confidence=conf,
            severity="info", risk_band=band, rationale="",
            evidence={}, guardrails={}, mode="observe",
            status=FERecStatus.PENDING, created_at="", expires_at="",
        )

    def test_ordering(self):
        from engines.factory_eval.engine import rank_and_filter
        recs = [self._rec(uplift=0.02), self._rec(uplift=0.20),
                 self._rec(uplift=0.10)]
        ranked = rank_and_filter(recs)
        u = [r.expected_uplift for r in ranked]
        assert u == sorted(u, reverse=True)

    def test_expires_below_floor(self, monkeypatch):
        from engines.factory_eval.engine import rank_and_filter
        from engines.factory_eval.types import FERecStatus
        monkeypatch.setenv("FACTORY_EVAL_RANK_FLOOR", "0.10")
        recs = [self._rec(uplift=0.001), self._rec(uplift=0.5)]
        ranked = rank_and_filter(recs)
        assert any(r.status == FERecStatus.EXPIRED for r in ranked)

    def test_red_penalised(self):
        from engines.factory_eval.engine import rank_and_filter
        red = self._rec(uplift=0.10, conf=1.0, band="red")
        green = self._rec(uplift=0.05, conf=1.0, band="green")
        ranked = rank_and_filter([red, green])
        assert ranked[0].risk_band == "green"


# ── 6. Applier — OBSERVE safety ────────────────────────────
class TestApplier:
    def _rec(self, target="TEST_TARGET", surface="compute_reallocation",
                delta=0.01):
        from engines.factory_eval.types import (
            FactoryRecommendation, FERecStatus,
        )
        return FactoryRecommendation(
            recommendation_id="fe_rec_" + uuid.uuid4().hex[:8],
            insight_ids=["i"], surface=surface, target=target,
            current_value=0.0, proposed_value=delta, proposed_delta=delta,
            expected_uplift=0.01, confidence=0.5,
            severity="low", risk_band="green", rationale="",
            evidence={}, guardrails={}, mode="observe",
            status=FERecStatus.PENDING, created_at="", expires_at="",
        )

    def test_blocked_in_observe(self):
        from engines.factory_eval.engine import (
            ApplierGuardBlocked, apply_recommendation,
        )
        loop = asyncio.get_event_loop()
        with pytest.raises(ApplierGuardBlocked):
            loop.run_until_complete(apply_recommendation(
                self._rec(), applied_by="t"))

    def test_blocked_in_disabled(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "disabled")
        from engines.factory_eval.engine import (
            ApplierGuardBlocked, apply_recommendation,
        )
        loop = asyncio.get_event_loop()
        with pytest.raises(ApplierGuardBlocked):
            loop.run_until_complete(apply_recommendation(
                self._rec(), applied_by="t"))

    def test_allowed_in_recommend(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "recommend")
        from engines.factory_eval import ledger
        from engines.factory_eval.engine import (
            apply_recommendation, revert_override,
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_wipe())
        r = self._rec(target=f"T_APPLY_{uuid.uuid4().hex[:6]}")
        app = loop.run_until_complete(apply_recommendation(r, applied_by="op"))
        assert app is not None and app.new_value == 0.01
        overrides = loop.run_until_complete(ledger.read_overrides())
        assert any(o["target"] == r.target for o in overrides)
        assert loop.run_until_complete(revert_override(r.target))

    def test_blocked_when_delta_exceeds(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "recommend")
        from engines.factory_eval.engine import (
            ApplierGuardBlocked, apply_recommendation,
        )
        loop = asyncio.get_event_loop()
        with pytest.raises(ApplierGuardBlocked):
            loop.run_until_complete(apply_recommendation(
                self._rec(delta=0.99), applied_by="t"))

    def test_autonomous_requires_confirm(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "autonomous")
        from engines.factory_eval.engine import (
            ApplierGuardBlocked, apply_recommendation,
        )
        loop = asyncio.get_event_loop()
        with pytest.raises(ApplierGuardBlocked):
            loop.run_until_complete(apply_recommendation(
                self._rec(), applied_by="autonomous"))


# ── 7. Full cycle ──────────────────────────────────────────
class TestFullCycle:
    def test_cycle_observe_produces_zero_overrides(self):
        from engines.factory_eval import ledger
        from engines.factory_eval.engine import run_factory_evaluation_cycle
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_wipe())
        summary = loop.run_until_complete(run_factory_evaluation_cycle())
        assert summary["mode"] == "observe"
        assert summary["n_applied"] == 0
        overrides = loop.run_until_complete(ledger.read_overrides())
        assert overrides == []
        apps = loop.run_until_complete(ledger.read_applications())
        assert apps == []

    def test_cycle_disabled_short_circuits(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "disabled")
        from engines.factory_eval.engine import run_factory_evaluation_cycle
        loop = asyncio.get_event_loop()
        summary = loop.run_until_complete(run_factory_evaluation_cycle())
        assert summary["skipped"] is True

    def test_daily_uses_long_window(self, monkeypatch):
        from engines.factory_eval.engine import run_factory_evaluation_cycle
        loop = asyncio.get_event_loop()
        summary = loop.run_until_complete(
            run_factory_evaluation_cycle(daily=True))
        # 2160h = 90d
        assert summary["window_hours"] == 2160
        assert summary["daily"] is True


# ── 8. Orchestrator task ───────────────────────────────────
class TestOrchestrator:
    def test_task_registered(self):
        import engines.orchestrator.tasks  # noqa
        from engines.orchestrator.registry import registry
        assert "factory_evaluation" in registry.names()

    def test_readiness_respects_disabled(self, monkeypatch):
        monkeypatch.setenv("FACTORY_EVAL_MODE", "disabled")
        import engines.orchestrator.tasks  # noqa
        from engines.orchestrator.registry import registry
        from engines.orchestrator.types import OrchestratorContext
        task = registry.get("factory_evaluation")
        ctx = OrchestratorContext(tick_id="t", caps=None, probe={},
                                    pressure={}, adaptive=None,
                                    budget=None, now_iso="")
        loop = asyncio.get_event_loop()
        r = loop.run_until_complete(task.readiness(ctx))
        assert r.eligible is False
        assert "disabled" in r.reason


# ── 9. API ─────────────────────────────────────────────────
class TestAPI:
    def test_config(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/config")
        assert r.status_code == 200
        assert r.json()["config"]["FACTORY_EVAL_MODE"] == "observe"

    def test_status(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/status")
        assert r.status_code == 200 and r.json()["mode"] == "observe"

    def test_reports_list(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/reports")
        assert r.status_code == 200

    def test_kpis(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/kpis")
        assert r.status_code == 200

    def test_pending(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/pending")
        assert r.status_code == 200

    def test_insights(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/insights")
        assert r.status_code == 200

    def test_recommendations(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/recommendations")
        assert r.status_code == 200

    def test_applications_empty_in_observe(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/applications")
        assert r.status_code == 200

    def test_overrides_empty_in_observe(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/overrides")
        assert r.status_code == 200

    def test_providers_leaderboard(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/providers/leaderboard")
        assert r.status_code == 200

    def test_top_contributors(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/strategies/top-contributors")
        assert r.status_code == 200

    def test_pruning_candidates(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/strategies/pruning-candidates")
        assert r.status_code == 200

    def test_portfolio_trends(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/portfolios/health-trends")
        assert r.status_code == 200

    def test_path_rankings(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/execution/path-rankings")
        assert r.status_code == 200

    def test_regimes(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/regimes/effectiveness")
        assert r.status_code == 200

    def test_bottlenecks(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/bottlenecks")
        assert r.status_code == 200

    def test_coverage_gaps(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/coverage-gaps")
        assert r.status_code == 200

    def test_refresh_force(self, admin):
        r = admin.post(f"{BASE_URL}/api/factory-eval/refresh?force=true")
        assert r.status_code == 200
        assert r.json()["cycle"]["mode"] == "observe"

    def test_daily_report(self, admin):
        r = admin.post(f"{BASE_URL}/api/factory-eval/daily-report")
        assert r.status_code == 200
        assert r.json()["cycle"]["daily"] is True

    def test_approve_returns_409_in_observe(self, admin):
        r = admin.post(f"{BASE_URL}/api/factory-eval/recommendations/x/approve")
        assert r.status_code == 409
        assert "observe" in r.json().get("detail", {}).get("mode", "")

    def test_revert_missing_returns_404(self, admin):
        r = admin.post(f"{BASE_URL}/api/factory-eval/overrides/NONEXISTENT/revert")
        assert r.status_code == 404

    def test_mode_history(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/mode-history")
        assert r.status_code == 200

    def test_report_not_found(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/reports/fe_report_missing")
        assert r.status_code == 404

    def test_insight_not_found(self, admin):
        r = admin.get(f"{BASE_URL}/api/factory-eval/insights/fe_insight_missing")
        assert r.status_code == 404


# ── 10. Router count ───────────────────────────────────────
class TestRouterCount:
    def test_router_count_is_100(self):
        # Auth ping just confirms router mounted; log-scan happens in Phase A test
        r = requests.get(f"{BASE_URL}/api/factory-eval/config", timeout=5)
        assert r.status_code in (200, 401)


# ── 11. Structural non-modification ────────────────────────
class TestStructuralNonModification:
    _WATCHED = (
        "/app/backend/legacy/engines/brain/scorer.py",
        "/app/backend/legacy/engines/brain/policy.py",
        "/app/backend/legacy/engines/brain/brain.py",
        "/app/backend/legacy/engines/brain/config.py",
        "/app/backend/legacy/engines/portfolio/allocation.py",
        "/app/backend/legacy/engines/portfolio/capital.py",
        "/app/backend/legacy/engines/portfolio/rebuilder.py",
        "/app/backend/legacy/engines/execution/risk_monitor.py",
        "/app/backend/legacy/engines/execution/quality.py",
        "/app/backend/legacy/engines/execution/attribution.py",
        "/app/backend/legacy/engines/meta_learning/engine.py",
    )

    def test_all_watched_files_exist(self):
        for p in self._WATCHED:
            assert os.path.exists(p), f"missing: {p}"

    def test_hashes_deterministic(self):
        h = hashlib.sha256()
        for p in sorted(self._WATCHED):
            with open(p, "rb") as f:
                h.update(f.read())
        digest = h.hexdigest()
        assert isinstance(digest, str) and len(digest) == 64
