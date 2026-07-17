"""Module 3 — Strategy Engineering."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class StrategyEngineeringModule(ModuleRunner):
    NAME = "strategy_engineering"

    def run(self, sess: Session) -> List[ProbeResult]:
        out: List[ProbeResult] = []
        # Phase-1 canonical CRUD
        create_body = {"name": "validation-suite-probe",
                        "description": "prod-validation smoke",
                        "symbol": "EURUSD", "timeframe": "H1"}
        created_id = {"v": None}

        def _capture_id(r):
            b = r.json()
            created_id["v"] = b.get("strategy_id")
            if not created_id["v"]:
                return "no strategy_id in response"
            return None

        out.append(probe(sess, module=self.NAME, name="phase1_create",
                          method="POST", path="/api/strategies",
                          json_body=create_body, expect=[200, 201],
                          validate=_capture_id))

        # Phase-1 list should return an array
        def _is_list(r):
            b = r.json()
            if not isinstance(b, list):
                return f"expected list, got {type(b).__name__}"
            return None
        out.append(probe(sess, module=self.NAME, name="phase1_list_shape",
                          method="GET", path="/api/strategies",
                          validate=_is_list))

        sid = created_id["v"] or ""
        if sid:
            out.append(probe(sess, module=self.NAME, name="phase1_get_by_id",
                              method="GET", path=f"/api/strategies/{sid}"))
            out.append(probe(sess, module=self.NAME, name="phase1_delete_by_id",
                              method="DELETE", path=f"/api/strategies/{sid}",
                              expect=[200, 204]))
            out.append(probe(sess, module=self.NAME, name="phase1_deleted_404",
                              method="GET", path=f"/api/strategies/{sid}",
                              expect=404))

        # Legacy advanced endpoints — presence check (any non-404 = mounted)
        # Bodies are intentionally invalid so the handler validates + returns
        # 400/422 — this proves the route exists without running expensive
        # legacy pipelines. warn_on_status widens accepted validity codes.
        legacy_endpoints = [
            ("generate_strategy",   "POST", "/api/generate-strategy"),
            ("run_backtest",        "POST", "/api/run-backtest"),
            ("rank_strategies",     "POST", "/api/rank-strategies"),
            ("save_strategy",       "POST", "/api/save-strategy"),
            ("validate_strategy",   "POST", "/api/validate-strategy"),
            ("optimize_strategy",   "POST", "/api/optimize-strategy"),
            ("mutate_strategy",     "POST", "/api/mutate-strategy"),
            ("analyze_strategy",    "POST", "/api/analyze-strategy"),
            ("compare_strategies",  "POST", "/api/strategies/compare"),
            ("legacy_list_wrapper", "GET",  "/api/legacy/strategies"),
        ]
        for name, method, path in legacy_endpoints:
            body = None if method == "GET" else {}
            out.append(probe(
                sess, module=self.NAME, name=name, method=method, path=path,
                json_body=body,
                expect=lambda h: h != 404 and h != 405 and h < 500,
                warn_on_status=[401],
            ))

        # Legacy list shape check (must be wrapper form)
        def _legacy_wrapper(r):
            b = r.json()
            if "strategies" not in b:
                return "expected legacy wrapper with 'strategies' key"
            return None
        out.append(probe(sess, module=self.NAME, name="legacy_wrapper_shape",
                          method="GET", path="/api/legacy/strategies",
                          validate=_legacy_wrapper))
        return out
