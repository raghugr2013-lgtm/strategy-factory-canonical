"""
Pass 14 — Tests for engines.ingestion_health_aggregate.

Five tiers, matching the discipline used by P0.4 / P1.2 / P1.4 / P1.5 / P1.6:

  Tier 1 — Non-consumption contract: no engine imports the aggregator.
  Tier 2 — Pure helpers (classify_row, classify_heartbeat).
  Tier 3 — Pure verdict synthesiser (priority + vocabulary).
  Tier 4 — Threshold accessors (defaults + env overrides + clamping).
  Tier 5 — Live aggregator smoke test (empty Mongo state).

Discipline:
  * Pure tests; no Mongo writes, no LLM, no network.
  * The non-consumption test (Tier 1) is the institutional gate that
    prevents the aggregator from accidentally becoming a hot-path
    consumer (drives orchestration / gating / mutation).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Non-consumption contract
# ─────────────────────────────────────────────────────────────────────
class TestNonConsumption:
    """Institutional invariant: no module under ``backend/engines/``
    may import ``engines.ingestion_health_aggregate``. The aggregator
    is purely a diagnostic surface for the operator dashboard.
    """

    _AUTHORIZED_IMPORTERS: set = set()  # empty: never consumed

    def test_no_engine_consumer(self):
        backend = Path(__file__).resolve().parent.parent
        engines_dir = backend / "engines"
        offenders: List[str] = []
        for py in engines_dir.rglob("*.py"):
            if py.name == "ingestion_health_aggregate.py":
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
                    "from engines.ingestion_health_aggregate" in stripped
                    or "import engines.ingestion_health_aggregate" in stripped
                ):
                    rel = str(py.relative_to(backend))
                    if rel not in self._AUTHORIZED_IMPORTERS:
                        offenders.append(rel)
                        break
        assert not offenders, (
            "Pass 14 non-consumption violated — engines/ imports "
            f"ingestion_health_aggregate in: {offenders}. The "
            "aggregator must never drive runtime behavior."
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Pure helpers
# ─────────────────────────────────────────────────────────────────────
class TestClassifyRow:
    def test_blocked_when_zero_rows(self):
        from engines.ingestion_health_aggregate import classify_row
        assert classify_row(rows=0, completeness=0.0,
                            has_gaps=False, lag_bars=0.0) == "blocked"

    def test_blocked_when_completeness_zero(self):
        from engines.ingestion_health_aggregate import classify_row
        assert classify_row(rows=10, completeness=0.0,
                            has_gaps=False, lag_bars=0.0) == "blocked"

    def test_degraded_when_low_completeness(self):
        from engines.ingestion_health_aggregate import classify_row
        # Default min_completeness is 0.95
        assert classify_row(rows=100, completeness=0.80,
                            has_gaps=False, lag_bars=1.0) == "degraded"

    def test_degraded_when_has_gaps(self):
        from engines.ingestion_health_aggregate import classify_row
        assert classify_row(rows=100, completeness=0.99,
                            has_gaps=True, lag_bars=1.0) == "degraded"

    def test_stale_when_lag_exceeds_threshold(self):
        from engines.ingestion_health_aggregate import classify_row
        assert classify_row(rows=100, completeness=0.99,
                            has_gaps=False, lag_bars=10.0) == "stale"

    def test_healthy_when_all_good(self):
        from engines.ingestion_health_aggregate import classify_row
        assert classify_row(rows=100, completeness=0.99,
                            has_gaps=False, lag_bars=1.0) == "healthy"

    def test_priority_blocked_before_degraded(self):
        from engines.ingestion_health_aggregate import classify_row
        # Zero rows + has_gaps + low completeness — blocked wins.
        assert classify_row(rows=0, completeness=0.50,
                            has_gaps=True, lag_bars=99.0) == "blocked"


class TestClassifyHeartbeat:
    def test_missing_when_no_event(self):
        from engines.ingestion_health_aggregate import classify_heartbeat
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert classify_heartbeat(last_event_at=None, now=now) == "missing"

    def test_fresh_within_window(self):
        from engines.ingestion_health_aggregate import classify_heartbeat
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        # Default: heartbeat_fresh_minutes = 90
        last = now - timedelta(minutes=30)
        assert classify_heartbeat(last_event_at=last, now=now) == "fresh"

    def test_aged_between_fresh_and_stale(self):
        from engines.ingestion_health_aggregate import classify_heartbeat
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        # 90 < age <= 360 (defaults)
        last = now - timedelta(minutes=200)
        assert classify_heartbeat(last_event_at=last, now=now) == "aged"

    def test_stale_beyond_window(self):
        from engines.ingestion_health_aggregate import classify_heartbeat
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=24)
        assert classify_heartbeat(last_event_at=last, now=now) == "stale"


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Verdict synthesiser
# ─────────────────────────────────────────────────────────────────────
class TestSynthesiseVerdict:
    def test_healthy_all_clear(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        r = synthesise_verdict(
            per_band={"healthy": 10, "stale": 0, "degraded": 0, "blocked": 0},
            heartbeat_band="fresh", coverage_row_count=10, audit_event_count=12,
        )
        assert r["verdict"] == "HEALTHY"

    def test_blocked_priority(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        # Even with degraded/stale present, blocked wins.
        r = synthesise_verdict(
            per_band={"healthy": 1, "stale": 1, "degraded": 1, "blocked": 1},
            heartbeat_band="fresh", coverage_row_count=4, audit_event_count=5,
        )
        assert r["verdict"] == "BLOCKED"

    def test_degraded_beats_lagging(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        r = synthesise_verdict(
            per_band={"healthy": 5, "stale": 1, "degraded": 1, "blocked": 0},
            heartbeat_band="fresh", coverage_row_count=7, audit_event_count=5,
        )
        assert r["verdict"] == "DEGRADED"

    def test_lagging_when_stale_rows_only(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        r = synthesise_verdict(
            per_band={"healthy": 5, "stale": 2, "degraded": 0, "blocked": 0},
            heartbeat_band="fresh", coverage_row_count=7, audit_event_count=5,
        )
        assert r["verdict"] == "LAGGING"

    def test_stale_when_heartbeat_aged_but_rows_clean(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        r = synthesise_verdict(
            per_band={"healthy": 5, "stale": 0, "degraded": 0, "blocked": 0},
            heartbeat_band="stale", coverage_row_count=5, audit_event_count=0,
        )
        assert r["verdict"] == "STALE"

    def test_empty_when_nothing_present(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        r = synthesise_verdict(
            per_band={"healthy": 0, "stale": 0, "degraded": 0, "blocked": 0},
            heartbeat_band="missing", coverage_row_count=0, audit_event_count=0,
        )
        assert r["verdict"] == "EMPTY"

    def test_rationale_always_string(self):
        from engines.ingestion_health_aggregate import synthesise_verdict
        for hb in ("fresh", "aged", "stale", "missing"):
            for blocked in (0, 1):
                r = synthesise_verdict(
                    per_band={"healthy": 1, "stale": 0, "degraded": 0, "blocked": blocked},
                    heartbeat_band=hb, coverage_row_count=1, audit_event_count=1,
                )
                assert isinstance(r["rationale"], str) and len(r["rationale"]) > 0


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Threshold accessors
# ─────────────────────────────────────────────────────────────────────
class TestThresholds:
    def test_defaults(self):
        for var in (
            "INGEST_HEALTHY_MAX_LAG_BARS",
            "INGEST_HEALTHY_MIN_COMPLETENESS",
            "INGEST_HEARTBEAT_FRESH_MINUTES",
            "INGEST_HEARTBEAT_STALE_MINUTES",
            "INGEST_DEGRADATION_MIN_BASELINE",
        ):
            os.environ.pop(var, None)
        from engines.ingestion_health_aggregate import thresholds
        th = thresholds()
        assert th["healthy_max_lag_bars"] == 2.0
        assert th["healthy_min_completeness"] == 0.95
        assert th["heartbeat_fresh_minutes"] == 90.0
        assert th["heartbeat_stale_minutes"] == 360.0
        assert th["degradation_min_baseline"] == 50

    def test_env_overrides(self):
        os.environ["INGEST_HEALTHY_MAX_LAG_BARS"] = "5.0"
        os.environ["INGEST_HEARTBEAT_FRESH_MINUTES"] = "30"
        try:
            from engines.ingestion_health_aggregate import thresholds
            th = thresholds()
            assert th["healthy_max_lag_bars"] == 5.0
            assert th["heartbeat_fresh_minutes"] == 30.0
        finally:
            os.environ.pop("INGEST_HEALTHY_MAX_LAG_BARS", None)
            os.environ.pop("INGEST_HEARTBEAT_FRESH_MINUTES", None)

    def test_malformed_env_falls_back_to_default(self):
        os.environ["INGEST_HEALTHY_MAX_LAG_BARS"] = "not-a-number"
        try:
            from engines.ingestion_health_aggregate import thresholds
            th = thresholds()
            assert th["healthy_max_lag_bars"] == 2.0
        finally:
            os.environ.pop("INGEST_HEALTHY_MAX_LAG_BARS", None)


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — Live aggregator smoke (empty Mongo)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestLiveAggregator:
    async def test_empty_mongo_returns_structured_payload(self):
        """On a fresh DB (no data_coverage, no audit events), the
        aggregator must NOT raise and must return a structured payload
        with verdict in the allowed vocabulary.
        """
        from engines.ingestion_health_aggregate import aggregate_ingestion_health
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        r = await aggregate_ingestion_health(now=now, coverage_limit=10)
        assert r["verdict"] in (
            "EMPTY", "HEALTHY", "LAGGING", "DEGRADED",
            "STALE", "BLOCKED", "UNCERTAIN",
        )
        assert r["read_only"] is True
        assert r["advisory_only"] is True
        assert r["governance_authority"] is False
        assert r["operator_authority"] == "final"
        assert "thresholds" in r
        assert r["evaluated_at"] == now.isoformat()
        # Envelope shape
        for key in ("per_band", "row_count", "heartbeat",
                    "degradation", "coverage_row_sample"):
            assert key in r

    async def test_envelope_safe_under_filter(self):
        from engines.ingestion_health_aggregate import aggregate_ingestion_health
        r = await aggregate_ingestion_health(
            symbol="EURUSD", timeframe="H1", source="bid_1m",
            coverage_limit=5,
        )
        assert r["verdict"] in (
            "EMPTY", "HEALTHY", "LAGGING", "DEGRADED",
            "STALE", "BLOCKED", "UNCERTAIN",
        )


if __name__ == "__main__":   # pragma: no cover
    pytest.main([__file__, "-v"])
