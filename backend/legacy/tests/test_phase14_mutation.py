"""
Phase 14 — Strategy Mutation Engine tests.

Covers:
  * Deterministic text generation per mutation type.
  * 5–15 variant bounds respected.
  * Required input validation.
  * Each catalogue type is represented in the engine registry.
  * RSI-stripping transform.
  * End-to-end pipeline with external `prices` override (no real market
    data required), with event persistence and ranking.
  * Stats rollup math.
  * Events filter by type + bad type raises.
"""
from __future__ import annotations

from typing import List

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import mutation_engine as me


BASE = {
    "strategy_text": (
        "BUY when EMA(20) crosses above EMA(50) AND RSI(14) > 50. "
        "SL 20 pips TP 35 pips."
    ),
    "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
}


@pytest_asyncio.fixture(autouse=True)
async def _fresh():
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    db = _dbm.get_db()
    for c in (me.EVENTS_COLL, me.RUNS_COLL, me.STABILITY_COLL):
        await db[c].delete_many({})
    yield
    for c in (me.EVENTS_COLL, me.RUNS_COLL, me.STABILITY_COLL):
        await db[c].delete_many({})


# ─────────────────────────────────────────────────────────────────────
# Step 2 — catalogue + structure
# ─────────────────────────────────────────────────────────────────────

def test_catalogue_has_15_types():
    assert len(me.MUTATION_TYPES) == 15


def test_mutate_produces_between_5_and_15_variants():
    variants = me.mutate_strategy(BASE)
    assert 5 <= len(variants) <= 15


def test_mutate_cap_max_variants():
    assert len(me.mutate_strategy(BASE, max_variants=5)) == 5
    assert len(me.mutate_strategy(BASE, max_variants=10)) == 10


def test_mutate_clamps_below_min():
    # Below 5 should clamp to 5, not go lower.
    assert len(me.mutate_strategy(BASE, max_variants=1)) == 5


def test_mutate_clamps_above_max():
    assert len(me.mutate_strategy(BASE, max_variants=99)) == 15


def test_each_variant_has_expected_fields():
    for v in me.mutate_strategy(BASE):
        for k in ("mutation_type", "strategy_text", "parameters",
                  "pair", "timeframe", "style",
                  "derived_from", "variant_fingerprint"):
            assert k in v, f"missing {k}"
        assert v["mutation_type"] in me.MUTATION_TYPES
        assert v["pair"] == "EURUSD"
        assert v["timeframe"] == "H1"
        assert v["style"] == "trend-following"
        assert "DERIVED FROM" in v["strategy_text"] or "DERIVED FROM (RSI-stripped)" in v["strategy_text"]
        # fingerprints are hex digests
        assert len(v["variant_fingerprint"]) == 40


def test_mutations_are_unique():
    variants = me.mutate_strategy(BASE)
    fps = [v["variant_fingerprint"] for v in variants]
    assert len(set(fps)) == len(fps)


def test_mutation_is_deterministic():
    a = me.mutate_strategy(BASE)
    b = me.mutate_strategy(BASE)
    assert [x["strategy_text"] for x in a] == [x["strategy_text"] for x in b]
    assert [x["variant_fingerprint"] for x in a] == [x["variant_fingerprint"] for x in b]


def test_all_catalogue_types_reachable_at_max_variants():
    types = {v["mutation_type"] for v in me.mutate_strategy(BASE, max_variants=15)}
    assert types == set(me.MUTATION_TYPES)


def test_invalid_base_returns_empty():
    assert me.mutate_strategy({}) == []
    assert me.mutate_strategy({"strategy_text": "x"}) == []
    assert me.mutate_strategy({"strategy_text": "x", "pair": "EURUSD"}) == []
    assert me.mutate_strategy(None) == []  # type: ignore[arg-type]


def test_rsi_stripping_removes_rsi_clause():
    stripped = me._strip_rsi_phrases(
        "BUY when EMA(20) crosses above EMA(50) AND RSI(14) > 50."
    )
    assert "RSI" not in stripped


def test_htf_selection():
    assert me._htf("H1") == "H4"
    assert me._htf("M5") == "H1"
    assert me._htf("M1") == "M15"
    assert me._htf("D1") == "W1"
    assert me._htf("XYZ") == "H4"


# ─────────────────────────────────────────────────────────────────────
# Step 3 — pipeline integration (external prices override)
# ─────────────────────────────────────────────────────────────────────

def _sine_prices(n: int = 500) -> List[float]:
    """Cheap deterministic synthetic price series — cycles with drift so
    the backtester will produce non-zero trade counts for most variants."""
    import math
    out = []
    for i in range(n):
        out.append(1.1000 + 0.005 * math.sin(i / 15.0) + 0.00005 * i)
    return out


@pytest.mark.asyncio
async def test_pipeline_with_external_prices_returns_ranked_variants():
    summary = await me.run_mutation_pipeline(
        BASE, max_variants=8, prices=_sine_prices(400),
    )
    assert summary["status"] == "ok"
    assert summary["price_source"] == "external"
    assert summary["totals"]["variants_generated"] == 8
    assert summary["totals"]["variants_backtested"] == 8
    assert len(summary["variants"]) == 8
    assert summary["best_variant"]["mutation_type"] in me.MUTATION_TYPES

    # Ranking check: first entry must have highest (or tied) profit_factor.
    pfs = [
        (v.get("backtest") or {}).get("profit_factor") or 0.0
        for v in summary["variants"]
    ]
    assert pfs == sorted(pfs, reverse=True) or all(p == pfs[0] for p in pfs)


@pytest.mark.asyncio
async def test_pipeline_persists_events_and_run():
    from engines import db as _dbm
    db = _dbm.get_db()
    summary = await me.run_mutation_pipeline(
        BASE, max_variants=6, prices=_sine_prices(250),
    )
    assert summary["status"] == "ok"
    ev_count = await db[me.EVENTS_COLL].count_documents({})
    assert ev_count == 6
    run_count = await db[me.RUNS_COLL].count_documents({"run_id": summary["run_id"]})
    assert run_count == 1


@pytest.mark.asyncio
async def test_pipeline_rejects_short_price_series():
    summary = await me.run_mutation_pipeline(
        BASE, prices=[1.1, 1.2, 1.3],
    )
    assert summary["status"] == "data_missing"


@pytest.mark.asyncio
async def test_pipeline_data_missing_when_no_prices_and_no_real_data():
    """With no external prices and no market_data in the test DB, the
    pipeline must short-circuit cleanly, not explode."""
    summary = await me.run_mutation_pipeline(BASE, prices=None)
    assert summary["status"] == "data_missing"
    assert summary["price_source"] == "real"


@pytest.mark.asyncio
async def test_pipeline_raises_on_bad_base():
    with pytest.raises(ValueError):
        await me.run_mutation_pipeline({"pair": "EURUSD"})  # missing fields


# ─────────────────────────────────────────────────────────────────────
# Stats + events
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_rollup_computes_avgs_and_success_rate():
    from engines import db as _dbm
    db = _dbm.get_db()
    now = "2026-04-19T00:00:00+00:00"
    # 3 events for trend_pullback, 2 positive (pf >= 1), 1 negative
    await db[me.EVENTS_COLL].insert_many([
        {"run_id": "r1", "type": "trend_pullback",
         "metrics": {"profit_factor": 1.5, "max_drawdown_pct": 5.0},
         "ts": now},
        {"run_id": "r2", "type": "trend_pullback",
         "metrics": {"profit_factor": 1.1, "max_drawdown_pct": 4.0},
         "ts": now},
        {"run_id": "r3", "type": "trend_pullback",
         "metrics": {"profit_factor": 0.7, "max_drawdown_pct": 10.0},
         "ts": now},
        # 1 event for mean_reversion_rsi, failing
        {"run_id": "r4", "type": "mean_reversion_rsi",
         "metrics": {"profit_factor": 0.8, "max_drawdown_pct": 12.0},
         "ts": now},
    ])
    stats = await me.get_stats()
    by_type = {row["type"]: row for row in stats["by_type"]}
    assert stats["total_events"] == 4
    tp = by_type["trend_pullback"]
    assert tp["count"] == 3
    assert tp["avg_pf"] == pytest.approx((1.5 + 1.1 + 0.7) / 3, rel=1e-3)
    assert tp["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
    mr = by_type["mean_reversion_rsi"]
    assert mr["count"] == 1
    assert mr["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_events_filter_by_type_and_bad_type_raises():
    from engines import db as _dbm
    db = _dbm.get_db()
    await db[me.EVENTS_COLL].insert_many([
        {"run_id": "a", "type": "trend_pullback", "metrics": {}, "ts": "t1"},
        {"run_id": "b", "type": "filter_add_rsi", "metrics": {}, "ts": "t2"},
    ])
    assert len(await me.list_events(mutation_type="trend_pullback")) == 1
    assert len(await me.list_events()) == 2

    with pytest.raises(ValueError):
        await me.list_events(mutation_type="garbage")



# ─────────────────────────────────────────────────────────────────────
# Auto-save integration — `_auto_save_best` reuses the EXISTING save
# pipeline (dashboard heavy stage + strategy_library.save_strategy).
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_mutation_pipeline_emits_auto_save_result_field():
    """`auto_save_result` must be present in the summary regardless of
    whether auto_save was requested."""
    summary = await me.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(250), auto_save=False,
    )
    assert summary["status"] == "ok"
    assert "auto_save_result" in summary
    assert summary["auto_save"] is False
    assert summary["auto_save_result"] is None


@pytest.mark.asyncio
async def test_auto_save_best_invokes_existing_pipeline_and_returns_status(
    monkeypatch,
):
    """`_auto_save_best` must route through dashboard._heavy_stage and
    strategy_library.save_strategy — never bypass them."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash

    calls = {"heavy": 0, "save": 0, "save_force": [], "save_source": []}

    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        calls["heavy"] += 1
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": {"walk_forward": {"aggregate": {"stability_score": 80.0}}},
            "decision": {"decision": {"verdict": "TRADE", "confidence": "high"}},
            "simulation": None,
            "prop_firm_panel": {
                "status": "PASS", "pass_probability": 80, "consistency_score": 75,
                "max_drawdown": 3.0, "daily_drawdown": 1.0, "recommendation": "ok",
                "violations": [],
            },
            "pass_probability": 80,
            "expected_value": None,
            "prescore": light.get("prescore", 0),
            "validation_skipped": False,
        }

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    async def _fake_save(payload, *, source="dashboard", force=False):
        calls["save"] += 1
        calls["save_force"].append(force)
        calls["save_source"].append(source)
        return {
            "success": True, "status": "saved",
            "strategy_id": "abc123", "reason": "TRADE verdict",
            "fingerprint": "f" * 40,
        }

    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)
    monkeypatch.setattr(libmod, "save_strategy", _fake_save)

    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500),
        auto_save=True, firm="ftmo",
    )
    assert summary["status"] == "ok"
    res = summary["auto_save_result"]
    assert res is not None
    assert res["status"] == "saved"
    assert res["saved"] is True
    assert res["strategy_id"] == "abc123"
    assert res["mutation_type"] in me.MUTATION_TYPES
    # Pipeline must have gone through the EXISTING heavy stage + save
    assert calls["heavy"] == 1
    assert calls["save"] == 1
    # No bypass: force must be False
    assert calls["save_force"] == [False]
    assert calls["save_source"] == ["mutation_engine"]


@pytest.mark.asyncio
async def test_auto_save_best_respects_eligibility_rejection(monkeypatch):
    """If the existing eligibility gate rejects (e.g. panel FAIL or weak
    RISKY), `_auto_save_best` must report the rejection and NOT persist."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash

    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": None,
            "decision": {"decision": {"verdict": "REJECT", "confidence": "low"}},
            "simulation": None,
            "prop_firm_panel": {"status": "FAIL", "pass_probability": 10},
            "pass_probability": 10,
            "expected_value": None, "prescore": 0,
            "validation_skipped": False,
        }

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    save_calls = []

    async def _fake_save(payload, *, source="dashboard", force=False):
        save_calls.append({"source": source, "force": force,
                           "verdict": payload.get("verdict"),
                           "prop_status": (payload.get("prop_firm_panel") or {}).get("status")})
        # Delegate to real save_strategy so the real eligibility gate runs.
        return await _real_save(payload, source=source, force=force)

    _real_save = libmod.save_strategy
    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)
    monkeypatch.setattr(libmod, "save_strategy", _fake_save)

    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500),
        auto_save=True, firm="ftmo",
    )
    res = summary["auto_save_result"]
    assert res is not None
    assert res["status"] == "rejected"
    assert res["saved"] is False
    assert res["strategy_id"] is None
    # Real save_strategy was called with force=False (no bypass).
    assert save_calls and save_calls[0]["force"] is False
    assert save_calls[0]["source"] == "mutation_engine"


@pytest.mark.asyncio
async def test_auto_save_best_tags_saved_doc_with_mutation_metadata(monkeypatch):
    """After save, the persisted strategy_library doc must carry
    mutation_type + mutation_run_id for downstream traceability."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash
    from engines import db as _dbm

    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": {"walk_forward": {"aggregate": {"stability_score": 75.0}}},
            "decision": {"decision": {"verdict": "TRADE", "confidence": "high"}},
            "simulation": None,
            "prop_firm_panel": {
                "status": "PASS", "pass_probability": 75, "consistency_score": 70,
                "max_drawdown": 4.0, "daily_drawdown": 1.5, "recommendation": "ok",
                "violations": [],
            },
            "pass_probability": 75,
            "expected_value": None, "prescore": 0,
            "validation_skipped": False,
        }

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)

    # Ensure library collection is empty so save actually persists.
    db = _dbm.get_db()
    await db[libmod.COLLECTION].delete_many({})

    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500),
        auto_save=True, firm="ftmo",
    )
    res = summary["auto_save_result"]
    assert res["status"] == "saved"
    sid = res["strategy_id"]
    assert sid

    doc = await db[libmod.COLLECTION].find_one({"strategy_id": sid}, {"_id": 0})
    assert doc is not None
    assert doc.get("source") == "mutation_engine"
    assert doc.get("mutation_type") == res["mutation_type"]
    assert doc.get("mutation_run_id") == summary["run_id"]
    # Clean up
    await db[libmod.COLLECTION].delete_many({})



# ─────────────────────────────────────────────────────────────────────
# Min-trade gate + determinism
# ─────────────────────────────────────────────────────────────────────


def test_min_trades_constant_exposed():
    """Module exposes MIN_TRADES_FOR_AUTO_SAVE for traceability."""
    assert hasattr(me, "MIN_TRADES_FOR_AUTO_SAVE")
    assert isinstance(me.MIN_TRADES_FOR_AUTO_SAVE, int)
    assert me.MIN_TRADES_FOR_AUTO_SAVE == 30


@pytest.mark.asyncio
async def test_auto_save_rejects_low_trade_variants_before_save(monkeypatch):
    """When the best variant produced < MIN_TRADES_FOR_AUTO_SAVE trades,
    `_auto_save_best` must short-circuit with reason starting with
    'insufficient_trades' and NEVER reach `_heavy_stage` or
    `save_strategy`."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash

    heavy_calls, save_calls = [], []

    def _spy_heavy(*a, **k):
        heavy_calls.append(1)
        raise AssertionError("_heavy_stage must not be called when trades < min")

    async def _spy_save(payload, *, source="dashboard", force=False):
        save_calls.append(1)
        raise AssertionError("save_strategy must not be called when trades < min")

    monkeypatch.setattr(dash, "_heavy_stage", _spy_heavy)
    monkeypatch.setattr(libmod, "save_strategy", _spy_save)

    # sine(250) deliberately produces < 30 trades across all variants.
    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(250),
        auto_save=True, firm="ftmo",
    )
    assert summary["status"] == "ok"
    res = summary["auto_save_result"]
    assert res is not None
    assert res["status"] == "rejected"
    assert res["saved"] is False
    assert res["strategy_id"] is None
    assert res["fingerprint"] is None
    assert res["reason"].startswith("insufficient_trades")
    assert res["min_trades_required"] == me.MIN_TRADES_FOR_AUTO_SAVE
    assert res["trades_count"] < me.MIN_TRADES_FOR_AUTO_SAVE
    assert heavy_calls == []
    assert save_calls == []


@pytest.mark.asyncio
async def test_auto_save_threshold_is_configurable_at_runtime(monkeypatch):
    """Tightening MIN_TRADES_FOR_AUTO_SAVE must flip a previously-savable
    variant into rejection territory — confirming the constant is the
    single source of truth for the gate."""
    import engines.mutation_engine as memod
    import api.dashboard as dash
    import engines.strategy_library as libmod

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": {"walk_forward": {"aggregate": {"stability_score": 80.0}}},
            "decision": {"decision": {"verdict": "TRADE", "confidence": "high"}},
            "simulation": None,
            "prop_firm_panel": {
                "status": "PASS", "pass_probability": 80, "consistency_score": 75,
                "max_drawdown": 3.0, "daily_drawdown": 1.0,
                "recommendation": "ok", "violations": [],
            },
            "pass_probability": 80,
            "expected_value": None, "prescore": 0, "validation_skipped": False,
        }

    async def _fake_save(payload, *, source="dashboard", force=False):
        return {"success": True, "status": "saved",
                "strategy_id": "sid-x", "reason": "TRADE verdict",
                "fingerprint": "a" * 40}

    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)
    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(libmod, "save_strategy", _fake_save)

    # Raise the bar so the best variant (sine(500) → ~41 trades) no
    # longer qualifies.
    monkeypatch.setattr(memod, "MIN_TRADES_FOR_AUTO_SAVE", 1000)

    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500),
        auto_save=True, firm="ftmo",
    )
    res = summary["auto_save_result"]
    assert res["status"] == "rejected"
    assert res["reason"].startswith("insufficient_trades")
    assert res["min_trades_required"] == 1000


@pytest.mark.asyncio
async def test_auto_save_result_is_deterministic_across_runs(monkeypatch):
    """Same base + same prices + same firm must yield an identical
    `auto_save_result` (mutation_type, variant_fingerprint, fingerprint,
    score, status) across repeated runs — no randomness anywhere in the
    mutation auto-save path."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash
    from engines import db as _dbm

    # Deterministic fakes keep the test independent of the heavy stage's
    # exact numeric output while still exercising the full control flow.
    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": {"walk_forward": {"aggregate": {"stability_score": 80.0}}},
            "decision": {"decision": {"verdict": "TRADE", "confidence": "high"}},
            "simulation": None,
            "prop_firm_panel": {
                "status": "PASS", "pass_probability": 80, "consistency_score": 75,
                "max_drawdown": 3.0, "daily_drawdown": 1.0,
                "recommendation": "ok", "violations": [],
            },
            "pass_probability": 80,
            "expected_value": None, "prescore": 0, "validation_skipped": False,
        }

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)

    db = _dbm.get_db()
    prices = _sine_prices(500)

    results = []
    for _ in range(3):
        await db[libmod.COLLECTION].delete_many({})
        summary = await memod.run_mutation_pipeline(
            BASE, max_variants=5, prices=prices,
            auto_save=True, firm="ftmo",
        )
        res = summary["auto_save_result"]
        assert res["status"] == "saved"
        results.append({
            "mutation_type": res["mutation_type"],
            "variant_fingerprint": res["variant_fingerprint"],
            "fingerprint": res["fingerprint"],
            "score": res["score"],
            "verdict": res["verdict"],
            "prop_status": res["prop_status"],
        })

    # All runs must be byte-identical on the relevant fields.
    assert results[0] == results[1] == results[2], results
    await db[libmod.COLLECTION].delete_many({})


# ─────────────────────────────────────────────────────────────────────
# Phase 14.3 — Stability monitor (additive telemetry)
# ─────────────────────────────────────────────────────────────────────


def test_stability_collection_name_exposed():
    assert me.STABILITY_COLL == "mutation_stability_log"


@pytest.mark.asyncio
async def test_no_stability_log_when_auto_save_disabled():
    """With auto_save=False the stability collection must stay empty —
    the monitor only records auto_save outcomes."""
    from engines import db as _dbm
    db = _dbm.get_db()
    summary = await me.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500), auto_save=False,
    )
    assert summary["auto_save_result"] is None
    assert await db[me.STABILITY_COLL].count_documents({}) == 0


@pytest.mark.asyncio
async def test_stability_log_records_saved_outcome(monkeypatch):
    """After a successful auto-save, one log entry must exist with the
    saved status, mutation_type, trades, PF, drawdown, and run_id."""
    import engines.mutation_engine as memod
    import engines.strategy_library as libmod
    import api.dashboard as dash
    from engines import db as _dbm

    def _fake_heavy(light, rules_config, wf_n, wf_v, run_v):
        return {
            "strategy_text": light["strategy_text"],
            "pair": light["pair"], "timeframe": light["timeframe"],
            "backtest": light["backtest"],
            "trades_count": light["trades_count"],
            "validation_report": {"walk_forward": {"aggregate": {"stability_score": 80.0}}},
            "decision": {"decision": {"verdict": "TRADE", "confidence": "high"}},
            "simulation": None,
            "prop_firm_panel": {
                "status": "PASS", "pass_probability": 80, "consistency_score": 75,
                "max_drawdown": 3.0, "daily_drawdown": 1.0,
                "recommendation": "ok", "violations": [],
            },
            "pass_probability": 80,
            "expected_value": None, "prescore": 0, "validation_skipped": False,
        }

    async def _fake_rules(firm):
        return {"name": firm or "ftmo"}

    async def _fake_save(payload, *, source="dashboard", force=False):
        return {
            "success": True, "status": "saved",
            "strategy_id": "sid-stab-1", "reason": "TRADE verdict",
            "fingerprint": "s" * 40,
        }

    monkeypatch.setattr(dash, "_heavy_stage", _fake_heavy)
    monkeypatch.setattr(dash, "_resolve_rules", _fake_rules)
    monkeypatch.setattr(libmod, "save_strategy", _fake_save)

    db = _dbm.get_db()
    summary = await memod.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(500),
        auto_save=True, firm="ftmo",
    )

    logs = [d async for d in db[me.STABILITY_COLL].find({}, {"_id": 0})]
    assert len(logs) == 1
    log = logs[0]
    assert log["run_id"] == summary["run_id"]
    assert log["pair"] == "EURUSD" and log["timeframe"] == "H1"
    assert log["mutation_type"] in me.MUTATION_TYPES
    assert log["auto_save_status"] == "saved"
    assert log["saved"] is True
    assert log["rejection_reason"] is None
    assert log["strategy_id"] == "sid-stab-1"
    assert isinstance(log["trades"], int) and log["trades"] >= me.MIN_TRADES_FOR_AUTO_SAVE
    assert "profit_factor" in log
    assert "max_drawdown" in log
    assert "ts" in log and log["ts"]


@pytest.mark.asyncio
async def test_stability_log_records_insufficient_trades_rejection():
    """Low-trade rejections must also be logged, with the full reason
    and `saved=False`."""
    from engines import db as _dbm
    db = _dbm.get_db()
    summary = await me.run_mutation_pipeline(
        BASE, max_variants=5, prices=_sine_prices(250),
        auto_save=True, firm="ftmo",
    )
    assert summary["auto_save_result"]["status"] == "rejected"

    logs = [d async for d in db[me.STABILITY_COLL].find({}, {"_id": 0})]
    assert len(logs) == 1
    log = logs[0]
    assert log["auto_save_status"] == "rejected"
    assert log["saved"] is False
    assert log["strategy_id"] is None
    assert log["rejection_reason"].startswith("insufficient_trades")
    assert log["trades"] < me.MIN_TRADES_FOR_AUTO_SAVE
    assert log["run_id"] == summary["run_id"]


@pytest.mark.asyncio
async def test_list_stability_logs_filters_and_limits():
    from engines import db as _dbm
    db = _dbm.get_db()
    await db[me.STABILITY_COLL].insert_many([
        {"run_id": "r1", "mutation_type": "trend_pullback",
         "auto_save_status": "saved", "trades": 42,
         "profit_factor": 1.4, "max_drawdown": 5.0,
         "ts": "2026-04-19T10:00:00Z"},
        {"run_id": "r2", "mutation_type": "trend_pullback",
         "auto_save_status": "rejected", "trades": 12,
         "profit_factor": None, "max_drawdown": None,
         "rejection_reason": "insufficient_trades (12 < 30)",
         "ts": "2026-04-19T10:05:00Z"},
        {"run_id": "r3", "mutation_type": "filter_add_rsi",
         "auto_save_status": "saved", "trades": 35,
         "profit_factor": 1.1, "max_drawdown": 8.0,
         "ts": "2026-04-19T10:10:00Z"},
    ])

    all_logs = await me.list_stability_logs()
    assert len(all_logs) == 3
    # newest first
    assert all_logs[0]["run_id"] == "r3"

    trend_only = await me.list_stability_logs(mutation_type="trend_pullback")
    assert len(trend_only) == 2
    assert all(x["mutation_type"] == "trend_pullback" for x in trend_only)

    saved_only = await me.list_stability_logs(auto_save_status="saved")
    assert len(saved_only) == 2
    assert all(x["auto_save_status"] == "saved" for x in saved_only)

    combo = await me.list_stability_logs(
        mutation_type="trend_pullback", auto_save_status="saved",
    )
    assert len(combo) == 1 and combo[0]["run_id"] == "r1"

    with pytest.raises(ValueError):
        await me.list_stability_logs(mutation_type="nope")


@pytest.mark.asyncio
async def test_stability_stats_rollup_aggregates_correctly():
    from engines import db as _dbm
    db = _dbm.get_db()
    await db[me.STABILITY_COLL].insert_many([
        # trend_pullback: 3 entries, 2 saved, pfs 1.5 / 1.2 / 0.8, trades 40 / 50 / 20
        {"run_id": "a", "mutation_type": "trend_pullback",
         "auto_save_status": "saved", "trades": 40,
         "profit_factor": 1.5, "max_drawdown": 4.0},
        {"run_id": "b", "mutation_type": "trend_pullback",
         "auto_save_status": "saved", "trades": 50,
         "profit_factor": 1.2, "max_drawdown": 6.0},
        {"run_id": "c", "mutation_type": "trend_pullback",
         "auto_save_status": "rejected", "trades": 20,
         "profit_factor": 0.8, "max_drawdown": 12.0},
        # filter_add_rsi: 1 entry, 0 saved
        {"run_id": "d", "mutation_type": "filter_add_rsi",
         "auto_save_status": "rejected", "trades": 10,
         "profit_factor": 0.5, "max_drawdown": 15.0},
    ])
    stats = await me.get_stability_stats()
    assert stats["total_logs"] == 4
    by_type = {row["mutation_type"]: row for row in stats["by_type"]}

    tp = by_type["trend_pullback"]
    assert tp["count"] == 3
    assert tp["saved"] == 2
    assert tp["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert tp["avg_pf"] == pytest.approx((1.5 + 1.2 + 0.8) / 3, rel=1e-3)
    assert tp["avg_trades"] == pytest.approx((40 + 50 + 20) / 3, rel=1e-3)
    assert tp["avg_drawdown"] == pytest.approx((4.0 + 6.0 + 12.0) / 3, rel=1e-3)

    fr = by_type["filter_add_rsi"]
    assert fr["count"] == 1
    assert fr["saved"] == 0
    assert fr["success_rate"] == 0.0
    assert fr["avg_pf"] == pytest.approx(0.5, rel=1e-3)


@pytest.mark.asyncio
async def test_stability_stats_empty_collection_returns_empty_rollup():
    stats = await me.get_stability_stats()
    assert stats == {"by_type": [], "total_logs": 0, "rejection_reasons": {}}

