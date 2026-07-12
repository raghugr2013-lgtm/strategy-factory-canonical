"""
Pass 15 — Tests for engines.deployment_extras.

Five tiers, matching the discipline used by P0.4 / P1.2 / P1.4 / P1.5 /
P1.6 / Pass 14:

  Tier 1 — Non-consumption contract.
  Tier 2 — Disk classifier + probe semantics.
  Tier 3 — Packaging probe (present + missing-artifact paths).
  Tier 4 — Recovery-tooling probe (present + missing + chmod paths).
  Tier 5 — Consolidated collect_extras() status synthesis.

Discipline:
  * Pure tests; no Mongo writes, no network.
  * Filesystem fixtures via ``tmp_path``.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Non-consumption contract
# ─────────────────────────────────────────────────────────────────────
class TestNonConsumption:
    """No module under ``backend/engines/`` may import
    ``engines.deployment_extras`` — it's a diagnostic-only surface."""

    _AUTHORIZED_IMPORTERS: set = set()

    def test_no_engine_consumer(self):
        backend = Path(__file__).resolve().parent.parent
        engines_dir = backend / "engines"
        offenders: List[str] = []
        for py in engines_dir.rglob("*.py"):
            if py.name == "deployment_extras.py":
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "from engines.deployment_extras" in stripped
                    or "import engines.deployment_extras" in stripped
                ):
                    rel = str(py.relative_to(backend))
                    if rel not in self._AUTHORIZED_IMPORTERS:
                        offenders.append(rel)
                        break
        assert not offenders, (
            f"Pass 15 non-consumption violated — engines/ imports "
            f"deployment_extras in: {offenders}."
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Disk classifier + probe
# ─────────────────────────────────────────────────────────────────────
class TestDiskClassifier:
    def test_band_ok_when_above_20pct(self):
        from engines.deployment_extras import _classify_disk
        assert _classify_disk(50.0) == "ok"
        assert _classify_disk(20.0) == "ok"

    def test_band_warn_between_10_and_20(self):
        from engines.deployment_extras import _classify_disk
        assert _classify_disk(15.0) == "warn"
        assert _classify_disk(10.0) == "warn"

    def test_band_critical_below_10(self):
        from engines.deployment_extras import _classify_disk
        assert _classify_disk(5.0) == "critical"
        assert _classify_disk(0.0) == "critical"

    def test_check_disk_returns_envelope(self, tmp_path: Path):
        from engines.deployment_extras import check_disk
        r = check_disk(str(tmp_path))
        assert r["name"] == "disk"
        assert isinstance(r["ok"], bool)
        assert r["band"] in ("ok", "warn", "critical", "error")
        assert r["total_gb"] is not None and r["total_gb"] >= 0
        assert r["free_pct"] is not None
        assert isinstance(r["detail"], str)


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Packaging probe
# ─────────────────────────────────────────────────────────────────────
class TestPackagingProbe:
    def test_missing_deploy_dir_returns_not_ok(self, tmp_path: Path):
        from engines.deployment_extras import check_packaging
        r = check_packaging(str(tmp_path))
        assert r["ok"] is False
        assert r["present"] == []
        assert set(r["missing"]) >= {"README.md", "backend.env.template"}

    def test_full_packaging_returns_ok(self, tmp_path: Path):
        from engines.deployment_extras import check_packaging
        deploy = tmp_path / "deploy"
        deploy.mkdir()
        for f in ("README.md", "backend.env.template",
                  "frontend.env.template", "supervisor.conf.template"):
            (deploy / f).write_text("x")
        (deploy / "systemd").mkdir()
        r = check_packaging(str(tmp_path))
        assert r["ok"] is True
        assert r["missing"] == []
        assert len(r["present"]) >= 5

    def test_partial_packaging_reports_missing(self, tmp_path: Path):
        from engines.deployment_extras import check_packaging
        deploy = tmp_path / "deploy"
        deploy.mkdir()
        (deploy / "README.md").write_text("x")
        r = check_packaging(str(tmp_path))
        assert r["ok"] is False
        assert "README.md" in r["present"]
        assert "backend.env.template" in r["missing"]


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Recovery-tooling probe
# ─────────────────────────────────────────────────────────────────────
class TestRecoveryTooling:
    def test_missing_scripts_dir(self, tmp_path: Path):
        from engines.deployment_extras import check_recovery_tooling
        r = check_recovery_tooling(str(tmp_path))
        assert r["ok"] is False
        assert r["present"] == []
        assert len(r["missing"]) >= 6

    def test_full_recovery_tooling_with_chmod(self, tmp_path: Path):
        from engines.deployment_extras import check_recovery_tooling
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        names = ("install.sh", "update.sh", "rollback.sh",
                 "snapshot_now.sh", "diagnose_log.sh", "deploy_check.sh")
        for n in names:
            p = scripts / n
            p.write_text("#!/bin/sh\necho ok\n")
            p.chmod(0o755)
        r = check_recovery_tooling(str(tmp_path))
        assert r["ok"] is True
        assert set(r["present"]) >= set(names)
        assert r["missing"] == []
        assert r["not_executable"] == []

    def test_present_but_not_executable_flagged(self, tmp_path: Path):
        from engines.deployment_extras import check_recovery_tooling
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        for n in ("install.sh", "update.sh", "rollback.sh",
                  "snapshot_now.sh", "diagnose_log.sh", "deploy_check.sh"):
            p = scripts / n
            p.write_text("#!/bin/sh\n")
            p.chmod(0o644)   # NOT executable
        r = check_recovery_tooling(str(tmp_path))
        assert r["ok"] is False
        assert r["missing"] == []
        assert set(r["not_executable"]) >= {"rollback.sh"}


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — Consolidated collect_extras
# ─────────────────────────────────────────────────────────────────────
class TestCollectExtras:
    def test_status_ok_when_everything_present_and_executable(self, tmp_path: Path):
        from engines.deployment_extras import collect_extras
        # Seed deploy/, scripts/, supervisor/ inside tmp_path so the
        # collector observes a "production-shaped" tree.
        (tmp_path / "deploy").mkdir()
        for f in ("README.md", "backend.env.template",
                  "frontend.env.template", "supervisor.conf.template"):
            (tmp_path / "deploy" / f).write_text("x")
        (tmp_path / "deploy" / "systemd").mkdir()
        (tmp_path / "scripts").mkdir()
        for n in ("install.sh", "update.sh", "rollback.sh",
                  "snapshot_now.sh", "diagnose_log.sh", "deploy_check.sh"):
            p = tmp_path / "scripts" / n
            p.write_text("#!/bin/sh\n")
            p.chmod(0o755)
        (tmp_path / "supervisor").mkdir()
        (tmp_path / "supervisor" / "factory_runner.conf").write_text("x")
        r = collect_extras(str(tmp_path))
        # Disk band depends on host filesystem — accept any band but
        # confirm the structural success of the other three checks.
        names_ok = {c["name"]: c["ok"] for c in r["checks"]}
        assert names_ok["packaging"] is True
        assert names_ok["recovery_tooling"] is True
        assert names_ok["supervisor_templates"] is True
        # Envelope shape
        assert r["advisory_only"] is True
        assert r["read_only"] is True
        assert r["governance_authority"] is False
        assert r["operator_authority"] == "final"

    def test_status_warn_when_partial(self, tmp_path: Path):
        from engines.deployment_extras import collect_extras
        # Only deploy/ present, others missing → ok=False, status warn or critical.
        (tmp_path / "deploy").mkdir()
        for f in ("README.md", "backend.env.template",
                  "frontend.env.template", "supervisor.conf.template"):
            (tmp_path / "deploy" / f).write_text("x")
        (tmp_path / "deploy" / "systemd").mkdir()
        r = collect_extras(str(tmp_path))
        assert r["all_ok"] is False
        assert r["status"] in ("warn", "critical")

    def test_live_production_tree_smoke(self):
        """Real /app filesystem — confirms the production layout
        actually satisfies the probe."""
        from engines.deployment_extras import collect_extras
        r = collect_extras("/app")
        names_ok = {c["name"]: c["ok"] for c in r["checks"]}
        # Packaging + recovery + supervisor must all be present in the
        # production-shaped repo (this is the institutional baseline).
        assert names_ok.get("packaging") is True, r["checks"]
        assert names_ok.get("recovery_tooling") is True, r["checks"]
        assert names_ok.get("supervisor_templates") is True, r["checks"]


if __name__ == "__main__":   # pragma: no cover
    pytest.main([__file__, "-v"])
