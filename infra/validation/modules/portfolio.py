"""Module 4 — Portfolio (Phase D adaptive portfolio engine)."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class PortfolioModule(ModuleRunner):
    NAME = "portfolio"

    def run(self, sess: Session) -> List[ProbeResult]:
        endpoints = [
            # Phase D / portfolio-intelligence engine (canonical mount)
            ("get_config",       "GET",  "/api/portfolio-intelligence/config"),
            ("list_masterbots",  "GET",  "/api/master-bot"),
            ("recent_bundles",   "GET",  "/api/portfolio-intelligence/history"),
            # Legacy portfolio surface
            ("analyze",          "POST", "/api/portfolio-analyze"),
            ("auto_build",       "POST", "/api/portfolio-auto-build"),
            ("live_allocation",  "POST", "/api/portfolio-live-allocation"),
            ("rebalance_config", "GET",  "/api/rebalance/config"),
            ("allocation_history","GET", "/api/allocation-history"),
        ]
        out: List[ProbeResult] = []
        for name, method, path in endpoints:
            body = None if method == "GET" else {}
            out.append(probe(sess, module=self.NAME, name=name,
                              method=method, path=path, json_body=body,
                              expect=lambda h: h != 404 and h < 500,
                              warn_on_status=[400, 401, 422]))
        return out
