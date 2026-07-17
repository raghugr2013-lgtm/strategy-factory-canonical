"""Module 1 — Infrastructure health."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class HealthModule(ModuleRunner):
    NAME = "health"

    def run(self, sess: Session) -> List[ProbeResult]:
        out: List[ProbeResult] = []
        # Health + deployment registry (deployment-ready strategies).
        out.append(probe(sess, module=self.NAME, name="health_endpoint",
                          method="GET", path="/api/health"))
        out.append(probe(sess, module=self.NAME, name="deployment_registry",
                          method="GET", path="/api/deployment/registry"))

        # Orchestrator task registry — surrogate for "routers/tasks mounted".
        # Success criterion: the runtime declares the expected orchestrator
        # task set (>=17 named tasks per the v1.2.0-alpha2 spec).
        def _has_tasks(r):
            body = r.json() if r.headers.get("content-type","").startswith(
                "application/json") else {}
            n = body.get("count")
            tasks = body.get("tasks") or []
            n = n if n is not None else len(tasks)
            if n is None:
                return "count/tasks not present in response"
            if int(n) < 17:
                return f"orchestrator task count={n} < 17"
            return None
        out.append(probe(sess, module=self.NAME, name="orchestrator_tasks_ok",
                          method="GET", path="/api/orchestrator/tasks",
                          validate=_has_tasks))

        # Database + services surrogates
        out.append(probe(sess, module=self.NAME, name="auth_me",
                          method="GET", path="/api/auth/me"))
        return out
