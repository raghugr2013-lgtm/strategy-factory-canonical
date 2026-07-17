"""Module 6 — Market Intelligence (Phase G)."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class MarketIntelligenceModule(ModuleRunner):
    NAME = "market_intelligence"

    def run(self, sess: Session) -> List[ProbeResult]:
        endpoints = [
            ("config",             "GET",  "/api/market-intelligence/config"),
            ("rankings",           "GET",  "/api/market-intelligence/rankings"),
            ("state_snapshot",     "GET",  "/api/market-intelligence/state"),
            ("state_history",      "GET",  "/api/market-intelligence/state/history"),
            ("recent_changes",     "GET",  "/api/market-intelligence/changes"),
            ("observers_config",   "GET",  "/api/market-intelligence/observers/config"),
            ("aggregate",          "GET",  "/api/market-intelligence/intelligence"),
        ]
        out: List[ProbeResult] = []
        for name, method, path in endpoints:
            out.append(probe(sess, module=self.NAME, name=name,
                              method=method, path=path,
                              expect=lambda h: h != 404 and h < 500,
                              warn_on_status=[204, 400]))
        return out
