"""Module 7 — Execution Intelligence (Phase H)."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class ExecutionIntelligenceModule(ModuleRunner):
    NAME = "execution_intelligence"

    def run(self, sess: Session) -> List[ProbeResult]:
        endpoints = [
            ("config",         "GET",  "/api/execution/config"),
            ("status",         "GET",  "/api/execution/status"),
            ("orders",         "GET",  "/api/execution/orders"),
            ("fills",          "GET",  "/api/execution/fills"),
            ("positions",      "GET",  "/api/execution/positions"),
            ("quality",        "GET",  "/api/execution/quality"),
            ("attribution",    "GET",  "/api/execution/attribution"),
            ("risk_status",    "GET",  "/api/execution/risk/status"),
            ("broker_health",  "GET",  "/api/execution/broker/health"),
            ("paper_config",   "GET",  "/api/execution/paper/config"),
            ("journal_recent", "GET",  "/api/execution/journal?limit=5"),
        ]
        out: List[ProbeResult] = []
        for name, method, path in endpoints:
            out.append(probe(sess, module=self.NAME, name=name,
                              method=method, path=path,
                              expect=lambda h: h != 404 and h < 500,
                              warn_on_status=[204, 400, 503]))
        return out
