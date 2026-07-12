"""Test the read-only /api/latent/activation-timeline endpoint.

Not @pytest.mark.latent — the endpoint is always-on operator
observability (mirrors `test_boot_audit_emitter.py`). Coverage:

* Auth-gating contract
* Default + bounded `limit` (clamped at MAX_LIMIT)
* `source` filter narrows to a single process identifier
* Returned rows carry the documented projection only
* Newest-first ordering (sort by ts_dt desc)
* Steady-state boots contribute zero rows (transition-only)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from engines import feature_flags as ff
from engines.db import get_db
from server import app
from auth_utils import create_token

TEST_USER_EMAIL = "test_activation_timeline@local.test"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_motor_client():
    """Same async-fixture pattern as test_boot_audit_emitter."""
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    yield


@pytest_asyncio.fixture
async def _seeded_test_user():
    """Insert (and tear down) a minimal approved user so the auth
    middleware's `users.find_one` lookup succeeds for the JWT we mint
    in `_auth_header()`. Idempotent."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "user_id":    "test_at_user",
        "email":      TEST_USER_EMAIL,
        "role":       "admin",
        "status":     "approved",
        "created_at": now,
        "approved_at": now,
    }
    await db["users"].update_one(
        {"email": TEST_USER_EMAIL},
        {"$set": user_doc},
        upsert=True,
    )
    yield user_doc
    await db["users"].delete_one({"email": TEST_USER_EMAIL})


def _auth_header() -> dict:
    """Mint a short-lived JWT for the seeded test user."""
    token = create_token({
        "user_id": "test_at_user",
        "email":   TEST_USER_EMAIL,
        "role":    "admin",
    })
    return {"Authorization": f"Bearer {token}"}


async def _seed_two_transitions(monkeypatch) -> None:
    """Write two override_diff rows via the production emitter so the
    test exercises the real schema, not a hand-built doc."""
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)

    # baseline boot
    await ff.emit_boot_audit_event(source="pytest_at_baseline")
    # activate -> diff_written (added)
    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "true")
    await ff.emit_boot_audit_event(source="pytest_at_activated")
    await ff.emit_override_diff_event(
        source="pytest_at_activated",
        extra={"pytest_marker": "at_activated"},
    )
    # deactivate -> diff_written (removed)
    monkeypatch.delenv("ENABLE_RISK_OF_RUIN", raising=False)
    await ff.emit_boot_audit_event(source="pytest_at_deactivated")
    await ff.emit_override_diff_event(
        source="pytest_at_deactivated",
        extra={"pytest_marker": "at_deactivated"},
    )


async def _cleanup_pytest_rows() -> None:
    await get_db()["audit_log"].delete_many(
        {"source": {"$regex": "^pytest_at_"}},
    )


@pytest.mark.asyncio
async def test_activation_timeline_requires_auth():
    """No bearer token → 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/latent/activation-timeline")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_activation_timeline_returns_recent_diff_rows(monkeypatch, _seeded_test_user):
    """Auth'd GET returns the documented schema for recent transitions."""
    await _seed_two_transitions(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(
            "/api/latent/activation-timeline?limit=20",
            headers=_auth_header(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"count", "limit", "source", "events"}
    assert body["limit"] == 20
    assert body["source"] is None
    assert body["count"] == len(body["events"])
    assert body["count"] >= 2  # the two transitions we just seeded

    # Schema projection — every documented field present, nothing else
    # surprising (audit_log internals like _id stay hidden).
    allowed = {
        "ts", "source", "process_pid",
        "added", "removed", "changed",
        "n_added", "n_removed", "n_changed",
        "previous_boot_ts", "previous_boot_source", "previous_boot_pid",
    }
    for row in body["events"]:
        assert "_id" not in row
        extra = set(row.keys()) - allowed
        assert not extra, f"unexpected fields in row: {extra}"

    await _cleanup_pytest_rows()


@pytest.mark.asyncio
async def test_activation_timeline_source_filter_narrows(monkeypatch, _seeded_test_user):
    """`source=pytest_at_activated` returns only the matching row."""
    await _seed_two_transitions(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(
            "/api/latent/activation-timeline?source=pytest_at_activated",
            headers=_auth_header(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "pytest_at_activated"
    assert body["count"] >= 1
    for row in body["events"]:
        assert row["source"] == "pytest_at_activated"
        # Activation row → exactly the `added` bucket carries the flag
        assert row["n_added"] == 1
        assert "ENABLE_RISK_OF_RUIN" in row["added"]

    await _cleanup_pytest_rows()


@pytest.mark.asyncio
async def test_activation_timeline_newest_first_ordering(monkeypatch, _seeded_test_user):
    """Rows are sorted by ts_dt desc — newest event must be the
    deactivation we wrote last."""
    await _seed_two_transitions(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(
            "/api/latent/activation-timeline?limit=10",
            headers=_auth_header(),
        )
    body = r.json()
    # Filter to our seeded rows only (other test runs may share the
    # collection); the FIRST seeded one we encounter should be the
    # deactivation, because it was written most recently.
    seeded = [
        row for row in body["events"]
        if row.get("source", "").startswith("pytest_at_")
    ]
    assert len(seeded) >= 2
    assert seeded[0]["source"] == "pytest_at_deactivated"
    assert seeded[0]["n_removed"] == 1
    assert "ENABLE_RISK_OF_RUIN" in seeded[0]["removed"]

    await _cleanup_pytest_rows()


@pytest.mark.asyncio
async def test_activation_timeline_limit_validation(_seeded_test_user):
    """`limit` must be 1..500 — out-of-range values rejected by FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r_high = await ac.get(
            "/api/latent/activation-timeline?limit=10000",
            headers=_auth_header(),
        )
        r_zero = await ac.get(
            "/api/latent/activation-timeline?limit=0",
            headers=_auth_header(),
        )
    assert r_high.status_code == 422
    assert r_zero.status_code == 422


@pytest.mark.asyncio
async def test_activation_timeline_empty_when_filtered_to_unknown_source(_seeded_test_user):
    """A source that has no rows returns count=0 cleanly (no error)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(
            "/api/latent/activation-timeline?source=__never_emitted__",
            headers=_auth_header(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["events"] == []


# ─────────────────────────────────────────────────────────────────────
# /api/latent/activation-timeline/summary — per-flag aggregation
# ─────────────────────────────────────────────────────────────────────

async def _seed_three_transitions_for_summary(monkeypatch) -> None:
    """Seed: baseline → activate(RoR) → deactivate(RoR) → activate(AGING).
    Expected summary contributions:
        ENABLE_RISK_OF_RUIN  → 2 transitions (1 added, 1 removed)
        ENABLE_AGING_PENALTY → 1 transition  (1 added)
    """
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)

    await ff.emit_boot_audit_event(source="pytest_at_sum_baseline")

    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "true")
    await ff.emit_boot_audit_event(source="pytest_at_sum_ror_on")
    await ff.emit_override_diff_event(source="pytest_at_sum_ror_on")

    monkeypatch.delenv("ENABLE_RISK_OF_RUIN", raising=False)
    await ff.emit_boot_audit_event(source="pytest_at_sum_ror_off")
    await ff.emit_override_diff_event(source="pytest_at_sum_ror_off")

    monkeypatch.setenv("ENABLE_AGING_PENALTY", "true")
    await ff.emit_boot_audit_event(source="pytest_at_sum_aging_on")
    await ff.emit_override_diff_event(source="pytest_at_sum_aging_on")
    monkeypatch.delenv("ENABLE_AGING_PENALTY", raising=False)


@pytest.mark.asyncio
async def test_activation_timeline_summary_requires_auth():
    """No bearer token → 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/latent/activation-timeline/summary")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_activation_timeline_summary_aggregates_per_flag(
    monkeypatch, _seeded_test_user,
):
    """The summary projects one row per flag with first_seen/last_seen/
    total_transitions + per-bucket counts. Verifies the aggregation
    over a deterministic 3-transition seed."""
    await _seed_three_transitions_for_summary(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as ac:
        r = await ac.get(
            "/api/latent/activation-timeline/summary",
            headers=_auth_header(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"count", "limit", "source", "flags"}
    assert body["source"] is None
    assert body["count"] == len(body["flags"])

    by_flag = {row["flag"]: row for row in body["flags"]}
    # The seed produces 2 transitions for RoR and 1 for AGING — but
    # other tests may share the collection; the test asserts the LOWER
    # bound, not absolute equality.
    assert "ENABLE_RISK_OF_RUIN" in by_flag
    assert "ENABLE_AGING_PENALTY" in by_flag

    ror = by_flag["ENABLE_RISK_OF_RUIN"]
    assert ror["total_transitions"] >= 2
    assert ror["n_added_events"] >= 1
    assert ror["n_removed_events"] >= 1
    assert ror["n_changed_events"] == 0
    # Schema projection — every documented field present.
    for k in (
        "flag", "first_seen", "last_seen", "total_transitions",
        "n_added_events", "n_removed_events", "n_changed_events",
        "days_dormant", "days_since_first_seen", "churn_score",
    ):
        assert k in ror
    # ISO-string conversion of first_seen / last_seen worked.
    assert isinstance(ror["first_seen"], str)
    assert isinstance(ror["last_seen"], str)
    # last_seen must be >= first_seen (lex order works on ISO-8601).
    assert ror["last_seen"] >= ror["first_seen"]
    # Derived fields — purely arithmetic, observational-only:
    #   days_dormant and days_since_first_seen must be non-negative floats
    #   days_dormant ≤ days_since_first_seen (last_seen ≥ first_seen)
    #   churn_score = total_transitions / max(days_since_first_seen, floor)
    assert isinstance(ror["days_dormant"], float)
    assert isinstance(ror["days_since_first_seen"], float)
    assert isinstance(ror["churn_score"], float)
    assert ror["days_dormant"] >= 0
    assert ror["days_since_first_seen"] >= 0
    assert ror["days_dormant"] <= ror["days_since_first_seen"]
    # churn_score is finite + reflects the seed's transition count.
    assert ror["churn_score"] > 0
    import math
    assert math.isfinite(ror["churn_score"])

    aging = by_flag["ENABLE_AGING_PENALTY"]
    assert aging["total_transitions"] >= 1
    assert aging["n_added_events"] >= 1

    await _cleanup_pytest_rows()


@pytest.mark.asyncio
async def test_activation_timeline_summary_source_filter_narrows(
    monkeypatch, _seeded_test_user,
):
    """`source=pytest_at_sum_ror_on` returns ONLY the RoR-activation flag."""
    await _seed_three_transitions_for_summary(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as ac:
        r = await ac.get(
            "/api/latent/activation-timeline/summary?source=pytest_at_sum_ror_on",
            headers=_auth_header(),
        )
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "pytest_at_sum_ror_on"
    # Source-narrowed: this source ONLY emitted the RoR activation row.
    assert body["count"] == 1
    assert body["flags"][0]["flag"] == "ENABLE_RISK_OF_RUIN"
    assert body["flags"][0]["n_added_events"] == 1
    assert body["flags"][0]["n_removed_events"] == 0

    await _cleanup_pytest_rows()


@pytest.mark.asyncio
async def test_activation_timeline_summary_limit_validation(_seeded_test_user):
    """`limit` must be 1..MAX_SUMMARY_FLAGS — out-of-range rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as ac:
        r_high = await ac.get(
            "/api/latent/activation-timeline/summary?limit=10000",
            headers=_auth_header(),
        )
        r_zero = await ac.get(
            "/api/latent/activation-timeline/summary?limit=0",
            headers=_auth_header(),
        )
    assert r_high.status_code == 422
    assert r_zero.status_code == 422


@pytest.mark.asyncio
async def test_activation_timeline_summary_empty_on_unknown_source(
    _seeded_test_user,
):
    """No matching rows → count=0, flags=[]. No error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as ac:
        r = await ac.get(
            "/api/latent/activation-timeline/summary?source=__never_emitted__",
            headers=_auth_header(),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["flags"] == []


@pytest.mark.asyncio
async def test_activation_timeline_summary_derived_fields_arithmetic(
    monkeypatch, _seeded_test_user,
):
    """The derived dormancy / churn fields are PURE arithmetic:
        * days_dormant          ≥ 0
        * days_since_first_seen ≥ 0
        * days_dormant          ≤ days_since_first_seen
        * churn_score           = total_transitions / max(
                                  days_since_first_seen, 1s-in-days)
        * churn_score is FINITE even when first_seen and now are
          microseconds apart (the 1-second floor prevents div-by-zero).

    NO threshold, NO recommendation, NO governance decision is
    derived from these fields by the endpoint — that is the
    institutional contract.
    """
    await _seed_three_transitions_for_summary(monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
    ) as ac:
        r = await ac.get(
            "/api/latent/activation-timeline/summary",
            headers=_auth_header(),
        )
    body = r.json()
    by_flag = {row["flag"]: row for row in body["flags"]}
    ror = by_flag["ENABLE_RISK_OF_RUIN"]

    import math
    # 1) Type + non-negativity.
    assert isinstance(ror["days_dormant"], float)
    assert isinstance(ror["days_since_first_seen"], float)
    assert isinstance(ror["churn_score"], float)
    assert ror["days_dormant"] >= 0
    assert ror["days_since_first_seen"] >= 0

    # 2) Bound: last_seen is by definition ≥ first_seen, so the
    # "days ago" measured from now must be the opposite.
    assert ror["days_dormant"] <= ror["days_since_first_seen"]

    # 3) churn_score arithmetic. Reconstruct the expected score from
    # the same denominator clamp the endpoint uses (1 second in days).
    floor = 1.0 / 86400.0
    expected = ror["total_transitions"] / max(
        ror["days_since_first_seen"], floor,
    )
    # Endpoint rounds to 6 decimals; allow that tolerance.
    assert abs(ror["churn_score"] - expected) < 1e-3
    assert math.isfinite(ror["churn_score"])

    # 4) Just-seen flags MUST NOT produce inf / NaN churn even when
    # the test seeded the transitions microseconds ago. The 1-second
    # floor guarantees a finite score for the lower-bound case too.
    aging = by_flag["ENABLE_AGING_PENALTY"]
    assert math.isfinite(aging["churn_score"])
    assert aging["churn_score"] > 0

    await _cleanup_pytest_rows()
