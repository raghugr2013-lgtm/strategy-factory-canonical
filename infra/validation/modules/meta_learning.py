"""Module 8 — Meta-Learning (Phase I). OBSERVE-mode structural invariants."""
from __future__ import annotations
from typing import List
from ..auth import Session
from . import ModuleRunner, ProbeResult, probe


class MetaLearningModule(ModuleRunner):
    NAME = "meta_learning"

    def run(self, sess: Session) -> List[ProbeResult]:
        out: List[ProbeResult] = []

        def _mode_is_observe(r):
            body = r.json()
            m = (body.get("config") or {}).get("META_LEARNING_MODE")
            if m != "observe":
                return f"mode is {m!r}, expected 'observe'"
            return None
        out.append(probe(sess, module=self.NAME, name="mode_is_observe",
                          method="GET", path="/api/meta-learning/config",
                          validate=_mode_is_observe))

        # Force a cycle so recommendations get generated
        out.append(probe(sess, module=self.NAME, name="cycle_refresh_force",
                          method="POST",
                          path="/api/meta-learning/refresh?force=true",
                          expect=[200]))

        # Read the pending list (no ordering constraint — just must exist)
        out.append(probe(sess, module=self.NAME, name="pending_list",
                          method="GET", path="/api/meta-learning/pending"))

        # OBSERVE structural safety: overrides + applications must stay empty
        def _empty(r):
            b = r.json()
            n = b.get("count")
            if n and n > 0:
                return f"expected 0 rows in OBSERVE, got {n}"
            return None
        out.append(probe(sess, module=self.NAME, name="observe_zero_overrides",
                          method="GET", path="/api/meta-learning/overrides",
                          validate=_empty))
        out.append(probe(sess, module=self.NAME, name="observe_zero_apps",
                          method="GET", path="/api/meta-learning/applications",
                          validate=_empty))

        # approve must be blocked with 409 in OBSERVE
        out.append(probe(sess, module=self.NAME, name="approve_blocked_409",
                          method="POST",
                          path="/api/meta-learning/recommendations/x/approve",
                          expect=409))

        # Reads
        out.append(probe(sess, module=self.NAME, name="evaluations",
                          method="GET",
                          path="/api/meta-learning/evaluations?limit=10"))
        out.append(probe(sess, module=self.NAME, name="recommendations",
                          method="GET",
                          path="/api/meta-learning/recommendations?limit=10"))
        out.append(probe(sess, module=self.NAME, name="mode_history",
                          method="GET",
                          path="/api/meta-learning/mode-history"))
        return out
