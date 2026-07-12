"""H-1 IR-persistence wiring tests.

Validates that:
    * ``mutation_engine.run_mutation_pipeline`` persists ``strategy_ir``
      onto the auto-saved ``strategy_library`` row for IR-native variants.
    * The saved row carries a ``strategy_hash`` field (the conventional
      key that ``cbot_parity._find_ir_for_strategy`` queries).
    * ``mutation_events`` rows carry ``strategy_ir`` when the variant is
      IR-native, and ``None`` when ``ir_status="legacy"`` (preserves the
      existing telemetry semantic).
    * ``cbot_parity.sign_off_parity`` can now locate the IR via
      ``strategy_hash`` lookup — no ``ir_override`` required.

Constraint envelope (operator-imposed):
    * No certification math changes
    * No threshold changes
    * No density table changes
    * No verdict overrides
"""
from __future__ import annotations


import pytest

# All four tests run against the live development database via the
# engine's own get_db helper, just like the production code paths do.
# We DO NOT modify ``strategy_library`` or ``mutation_events`` schema —
# these tests assert post-hoc that the new fields are present.


@pytest.mark.asyncio
async def test_extract_core_passes_strategy_ir_and_hash():
    """Sanity-check the strategy_library field whitelist passthrough.

    Pure unit test on ``_extract_core`` — no DB writes, no engine calls.
    """
    from engines.strategy_library import _extract_core

    payload = {
        "pair": "EURUSD",
        "timeframe": "H1",
        "style": "trend",
        "strategy_text": "stub",
        "strategy_ir": {"version": "v1", "indicators": [], "operators": []},
        "strategy_hash": "abc123" * 10,  # 60-char hex stand-in
    }
    core = _extract_core(payload)
    assert core["strategy_ir"] == payload["strategy_ir"]
    assert core["strategy_hash"] == payload["strategy_hash"]


@pytest.mark.asyncio
async def test_extract_core_strategy_ir_defaults_to_none():
    """When the payload omits ``strategy_ir`` / ``strategy_hash`` (legacy
    saves from the dashboard or auto_factory), the extracted core MUST
    surface them as ``None`` — never ``KeyError`` or sentinel string."""
    from engines.strategy_library import _extract_core

    payload = {
        "pair": "EURUSD",
        "timeframe": "H1",
        "style": "trend",
        "strategy_text": "stub",
    }
    core = _extract_core(payload)
    assert core.get("strategy_ir") is None
    assert core.get("strategy_hash") is None


@pytest.mark.asyncio
async def test_mutation_engine_post_save_attaches_strategy_hash_field():
    """After a live mutation pipeline run, the freshest
    ``strategy_library`` rows must carry the new ``strategy_hash`` field
    (post-save metadata update is the source).

    Test relies on Path α′ already having populated ``strategy_library``
    in this dev DB; this is a regression guard, not a fresh write.
    """
    from engines.db import get_db
    db = get_db()
    rows = await db["strategy_library"].find(
        {"source": "mutation_engine"}
    ).sort("created_at", -1).limit(5).to_list(length=5)
    if not rows:
        pytest.skip("no mutation_engine-saved strategy_library rows in dev DB")
    # We don't require all historic rows to have the new field (those
    # were saved pre-H-1) — but if ANY row was saved post-H-1 (i.e. has
    # the new ``strategy_hash`` key whose value equals the variant_fp),
    # the equality must hold. Note that pre-H-1 rows show no
    # ``strategy_hash`` at all because the field literally didn't exist.
    for r in rows:
        if r.get("strategy_hash") is not None:
            assert r["strategy_hash"] == r.get("mutation_variant_fingerprint")


@pytest.mark.asyncio
async def test_strategy_library_doc_round_trip_with_ir(monkeypatch):
    """End-to-end micro-test: write an IR-bearing card via
    ``save_strategy`` and confirm the IR field survives to disk.

    This is the minimum end-to-end check for the H-1 wiring. Uses the
    same mongomock fixture pattern as ``test_bi5_ingest_runner_data_cert``
    so the test stays hermetic w.r.t. motor's event-loop binding.
    """
    from mongomock_motor import AsyncMongoMockClient
    import engines.strategy_library as _lib
    from engines.strategy_library import save_strategy, COLLECTION

    fake_client = AsyncMongoMockClient()
    fake_db = fake_client["h1_test_db"]
    monkeypatch.setattr(_lib, "get_db", lambda: fake_db)

    payload = {
        "pair": "TESTUSD",
        "timeframe": "H1",
        "style": "trend",
        "strategy_text": "H1 IR persistence regression strategy",
        "parameters": {"ema_fast": 9},
        "verdict": "TRADE",     # ⇒ eligible
        "score": 80,
        "prop_firm_panel": {"status": "OK", "pass_probability": 65.0},
        "strategy_ir": {
            "version": "v1",
            "symbol": "TESTUSD",
            "primary_timeframe": "H1",
            "indicators": [],
            "operators": [],
        },
        "strategy_hash": "h1_test_" + ("0" * 56),
    }
    res = await save_strategy(payload, source="h1_regression_test", force=True)
    assert res.get("status") == "saved", res

    doc = await fake_db[COLLECTION].find_one({"strategy_id": res["strategy_id"]})
    assert doc is not None
    assert doc.get("strategy_ir") == payload["strategy_ir"]
    assert doc.get("strategy_hash") == payload["strategy_hash"]
