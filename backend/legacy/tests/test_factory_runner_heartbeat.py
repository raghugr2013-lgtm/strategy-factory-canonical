"""
Pass 16 — Tests for ``engines.factory_runner_heartbeat``.

Five tiers, matching the discipline used by every prior latent
module (P0.4 / P1.2 / P1.4 / P1.5 / P1.6 / Pass 14 / Pass 15):

  Tier 1 — Non-consumption contract (no engine consumer).
  Tier 2 — Verdict band classifier (pure function).
  Tier 3 — Verdict detail strings (operator-readable per band).
  Tier 4 — Owner-flag + cadence resolution from env.
  Tier 5 — End-to-end ``get_heartbeat_status`` envelope.

Discipline:
  * Pure tests; no Mongo writes. The Mongo-touching test (Tier 5)
    uses a tiny in-memory monkeypatch on ``engines.db.get_db`` so
    the verdict is exercised against a controlled fixture.
  * No flag flips outside the test's monkeypatched env.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Non-consumption contract
# ─────────────────────────────────────────────────────────────────────
class TestNonConsumption:
    """No module under ``backend/engines/`` may import
    ``engines.factory_runner_heartbeat`` — it is a diagnostic-only
    surface, never an engine input."""

    _AUTHORIZED_IMPORTERS: set = set()

    def test_no_engine_consumer(self):
        backend = Path(__file__).resolve().parent.parent
        engines_dir = backend / "engines"
        offenders: List[str] = []
        for py in engines_dir.rglob("*.py"):
            if py.name == "factory_runner_heartbeat.py":
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
                    "from engines.factory_runner_heartbeat" in stripped
                    or "import engines.factory_runner_heartbeat" in stripped
                ):
                    rel = str(py.relative_to(backend))
                    if rel not in self._AUTHORIZED_IMPORTERS:
                        offenders.append(rel)
                        break
        assert not offenders, (
            "Pass 16 non-consumption violated — engines/ imports "
            f"factory_runner_heartbeat in: {offenders}."
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Pure band classifier
# ─────────────────────────────────────────────────────────────────────
class TestClassifier:
    def test_alive_when_recent(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_ALIVE
        # 100s old with cadence=300s → alive (< 2 × cadence).
        assert _classify(100.0, owner_active=True, cadence_sec=300) == VERDICT_ALIVE

    def test_stale_when_2x_to_4x(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_STALE
        # 700s old with cadence=300s → stale (600 ≤ age < 1200).
        assert _classify(700.0, owner_active=True, cadence_sec=300) == VERDICT_STALE

    def test_dead_when_4x_or_more(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_DEAD
        assert _classify(1300.0, owner_active=True, cadence_sec=300) == VERDICT_DEAD
        assert _classify(86400.0, owner_active=True, cadence_sec=300) == VERDICT_DEAD

    def test_never_seen_when_owner_active(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_NEVER_SEEN
        assert _classify(None, owner_active=True, cadence_sec=300) == VERDICT_NEVER_SEEN

    def test_not_expected_when_owner_inactive(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_NOT_EXPECTED
        assert _classify(None, owner_active=False, cadence_sec=300) == VERDICT_NOT_EXPECTED

    def test_negative_age_is_unknown(self):
        from engines.factory_runner_heartbeat import _classify, VERDICT_UNKNOWN
        # Clock skew protection — a heartbeat in the future is not "alive".
        assert _classify(-10.0, owner_active=True, cadence_sec=300) == VERDICT_UNKNOWN


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Verdict detail strings
# ─────────────────────────────────────────────────────────────────────
class TestVerdictDetail:
    def test_alive_mentions_cadence(self):
        from engines.factory_runner_heartbeat import _verdict_detail, VERDICT_ALIVE
        msg = _verdict_detail(VERDICT_ALIVE, 100.0, True, 300)
        assert "fresh" in msg.lower()
        assert "300" in msg

    def test_dead_names_recovery_command(self):
        from engines.factory_runner_heartbeat import _verdict_detail, VERDICT_DEAD
        msg = _verdict_detail(VERDICT_DEAD, 5000.0, True, 300)
        assert "supervisorctl restart factory-runner" in msg

    def test_never_seen_explains_silent_failure(self):
        from engines.factory_runner_heartbeat import _verdict_detail, VERDICT_NEVER_SEEN
        msg = _verdict_detail(VERDICT_NEVER_SEEN, None, True, 300)
        assert "FACTORY_RUNNER_OWNS_SCHEDULERS" in msg
        assert "silently dormant" in msg
        assert "supervisorctl start factory-runner" in msg

    def test_not_expected_is_benign(self):
        from engines.factory_runner_heartbeat import _verdict_detail, VERDICT_NOT_EXPECTED
        msg = _verdict_detail(VERDICT_NOT_EXPECTED, None, False, 300)
        assert "uvicorn" in msg.lower()


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Env resolution
# ─────────────────────────────────────────────────────────────────────
class TestEnvResolution:
    def test_owner_flag_truthy(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        for val in ("1", "true", "True", "yes", "on", "TRUE"):
            monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", val)
            assert m._owner_flag_active() is True

    def test_owner_flag_falsy(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        for val in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", val)
            assert m._owner_flag_active() is False

    def test_cadence_default(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.delenv("FACTORY_RUNNER_HEARTBEAT_SEC", raising=False)
        assert m._heartbeat_interval_sec() == 300

    def test_cadence_env_override(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_HEARTBEAT_SEC", "600")
        assert m._heartbeat_interval_sec() == 600

    def test_cadence_floor_60_seconds(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_HEARTBEAT_SEC", "5")
        assert m._heartbeat_interval_sec() == 60

    def test_cadence_invalid_falls_back(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_HEARTBEAT_SEC", "abc")
        assert m._heartbeat_interval_sec() == 300


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — End-to-end envelope via monkeypatched Mongo seam
# ─────────────────────────────────────────────────────────────────────
class _StubAuditLog:
    """In-memory stub: stores a single row, returns it on find_one."""

    def __init__(self, row: Dict[str, Any] | None):
        self._row = row

    async def find_one(self, *_args, **_kwargs):
        return self._row


class _StubDB:
    def __init__(self, row: Dict[str, Any] | None):
        self._audit = _StubAuditLog(row)

    def __getitem__(self, name: str):
        assert name == "audit_log"
        return self._audit


class TestEndToEndEnvelope:
    @pytest.mark.asyncio
    async def test_alive_envelope(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", "true")
        monkeypatch.setenv("FACTORY_RUNNER_HEARTBEAT_SEC", "300")
        # Fresh row 30 s ago.
        ts_dt = datetime.now(timezone.utc) - timedelta(seconds=30)
        row = {"ts": ts_dt.isoformat(), "ts_dt": ts_dt, "pid": 42}
        monkeypatch.setattr(m, "get_heartbeat_status", m.get_heartbeat_status)
        # Swap engines.db.get_db so the engine pulls the stub.
        from engines import db as _db
        monkeypatch.setattr(_db, "get_db", lambda: _StubDB(row))
        out = await m.get_heartbeat_status()
        assert out["verdict"] == m.VERDICT_ALIVE
        assert out["owner_flag_active"] is True
        assert out["cadence_sec"] == 300
        assert out["last_heartbeat_pid"] == 42
        assert out["advisory_only"] is True
        assert out["governance_authority"] is False

    @pytest.mark.asyncio
    async def test_never_seen_envelope_when_owner_on(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", "true")
        from engines import db as _db
        monkeypatch.setattr(_db, "get_db", lambda: _StubDB(None))
        out = await m.get_heartbeat_status()
        assert out["verdict"] == m.VERDICT_NEVER_SEEN
        assert "silently dormant" in out["detail"]

    @pytest.mark.asyncio
    async def test_not_expected_envelope_when_owner_off(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", "false")
        from engines import db as _db
        monkeypatch.setattr(_db, "get_db", lambda: _StubDB(None))
        out = await m.get_heartbeat_status()
        assert out["verdict"] == m.VERDICT_NOT_EXPECTED
        assert "uvicorn" in out["detail"].lower()

    @pytest.mark.asyncio
    async def test_dead_envelope_when_old(self, monkeypatch):
        from engines import factory_runner_heartbeat as m
        monkeypatch.setenv("FACTORY_RUNNER_OWNS_SCHEDULERS", "true")
        monkeypatch.setenv("FACTORY_RUNNER_HEARTBEAT_SEC", "300")
        ts_dt = datetime.now(timezone.utc) - timedelta(hours=2)
        row = {"ts": ts_dt.isoformat(), "ts_dt": ts_dt, "pid": 7}
        from engines import db as _db
        monkeypatch.setattr(_db, "get_db", lambda: _StubDB(row))
        out = await m.get_heartbeat_status()
        assert out["verdict"] == m.VERDICT_DEAD
        assert "supervisorctl restart factory-runner" in out["detail"]

    @pytest.mark.asyncio
    async def test_unknown_envelope_on_mongo_error(self, monkeypatch):
        from engines import factory_runner_heartbeat as m

        class _Boom:
            def __getitem__(self, _):
                raise RuntimeError("connection refused")

        from engines import db as _db
        monkeypatch.setattr(_db, "get_db", lambda: _Boom())
        out = await m.get_heartbeat_status()
        assert out["verdict"] == m.VERDICT_UNKNOWN
        assert "connection refused" in out["detail"]


if __name__ == "__main__":   # pragma: no cover
    pytest.main([__file__, "-v"])
