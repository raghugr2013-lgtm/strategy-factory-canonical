"""Module 5 — Prop Firm."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class PropFirmModule(ModuleRunner):
    NAME = "propfirm"

    def run(self, sess: Session) -> List[ProbeResult]:
        endpoints = [
            ("challenge_firms",    "GET",  "/api/challenge-firms"),
            ("challenge_rules",    "GET",  "/api/challenge-rules"),
            ("match_strategy",     "POST", "/api/match-strategy"),
            ("profile_strategy",   "POST", "/api/profile-strategy"),
            ("estimate_prob",      "POST", "/api/estimate-probability"),
            ("simulate_challenge", "POST", "/api/simulate-challenge"),
            ("safety_check",       "POST", "/api/safety-check"),
        ]
        out: List[ProbeResult] = []
        for name, method, path in endpoints:
            body = None if method == "GET" else {}
            out.append(probe(sess, module=self.NAME, name=name,
                              method=method, path=path, json_body=body,
                              expect=lambda h: h != 404 and h < 500,
                              warn_on_status=[400, 401, 422]))
        return out
