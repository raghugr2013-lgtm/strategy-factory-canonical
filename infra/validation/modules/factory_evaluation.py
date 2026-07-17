"""Module 9 — Factory Self-Evaluation (Phase J). OBSERVE-mode invariants."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class FactoryEvaluationModule(ModuleRunner):
    NAME = "factory_evaluation"

    def run(self, sess: Session) -> List[ProbeResult]:
        out: List[ProbeResult] = []

        def _mode_is_observe(r):
            b = r.json()
            m = (b.get("config") or {}).get("FACTORY_EVAL_MODE")
            if m != "observe":
                return f"mode is {m!r}, expected 'observe'"
            return None
        out.append(probe(sess, module=self.NAME, name="mode_is_observe",
                          method="GET", path="/api/factory-eval/config",
                          validate=_mode_is_observe))

        out.append(probe(sess, module=self.NAME, name="cycle_refresh_force",
                          method="POST",
                          path="/api/factory-eval/refresh?force=true",
                          expect=[200]))

        def _empty(r):
            b = r.json()
            n = b.get("count")
            if n and n > 0:
                return f"expected 0 rows in OBSERVE, got {n}"
            return None
        out.append(probe(sess, module=self.NAME, name="observe_zero_overrides",
                          method="GET", path="/api/factory-eval/overrides",
                          validate=_empty))
        out.append(probe(sess, module=self.NAME, name="observe_zero_apps",
                          method="GET", path="/api/factory-eval/applications",
                          validate=_empty))
        out.append(probe(sess, module=self.NAME, name="approve_blocked_409",
                          method="POST",
                          path="/api/factory-eval/recommendations/x/approve",
                          expect=409))

        # Read surface
        for name, path in (
            ("reports_list",     "/api/factory-eval/reports?limit=5"),
            ("reports_latest",   "/api/factory-eval/reports/latest"),
            ("kpis",             "/api/factory-eval/kpis"),
            ("insights",         "/api/factory-eval/insights?limit=10"),
            ("pending",          "/api/factory-eval/pending"),
            ("providers_lead",   "/api/factory-eval/providers/leaderboard"),
            ("top_strategies",   "/api/factory-eval/strategies/top-contributors"),
            ("pruning_cands",    "/api/factory-eval/strategies/pruning-candidates"),
            ("portfolio_trends", "/api/factory-eval/portfolios/health-trends"),
            ("path_rankings",    "/api/factory-eval/execution/path-rankings"),
            ("regime_eff",       "/api/factory-eval/regimes/effectiveness"),
            ("bottlenecks",      "/api/factory-eval/bottlenecks"),
            ("coverage_gaps",    "/api/factory-eval/coverage-gaps"),
        ):
            out.append(probe(sess, module=self.NAME, name=name,
                              method="GET", path=path,
                              # Latest may be 404 before first cycle; warn.
                              expect=lambda h: h != 500 and h < 500,
                              warn_on_status=[404]))
        return out
