"""v1.2.0-alpha2 Phase H — Paper-flow drill smoke test.

Runs the canonical `paper_flow_drill.py` harness at the 10-order preset
and asserts all validation categories PASS. Serves as the CI regression
gate on the Phase H acceptance artifact.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile


def test_drill_10_orders_all_pass():
    """The 10-order preset must PASS every validation category."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        path = tf.name
    env = {**os.environ,
           "PYTHONPATH": "/app/backend:/app/backend/legacy"}
    r = subprocess.run(
        ["python3", "/app/backend/scripts/paper_flow_drill.py",
          "--orders", "10", "--json", path],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert r.returncode == 0, f"drill failed:\n{r.stdout}\n{r.stderr}"
    report = json.load(open(path))
    assert report["verdict"] == "PASS"
    assert report["n_failed"] == 0
    # Every named validation category must be present.
    got = {v["name"] for v in report["validations"]}
    expected = {
        "order_lifecycle", "position_lifecycle", "journal_integrity",
        "replay_consistency", "pnl_correctness", "explainability_chain",
        "execution_quality", "deterministic_replay", "stress_scenarios",
    }
    assert expected.issubset(got), f"missing: {expected - got}"
