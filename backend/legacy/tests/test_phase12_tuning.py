"""
Phase 12 — Tuning & Optimization tests.

Covers:
  * Step 1 — quality floor upsert + fallback to defaults.
  * Step 2 — recency-weighted profit factor math.
  * Step 4 — slot stats rolling update + list.
  * Step 5 — adaptive per_combo bracketing (weak / base / strong).
  * Step 3 — performance snapshot creation (survival + live/backtest gap).
  * Step 6 — event logger append + filter.
  * Step 7 — Phase 11 integration stays backward compatible when Phase 12
              collections are empty, and honours the configured floor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import phase12_tuning as t12
from engines import gem_factory_engine as gf


LIB = "strategy_library"


@pytest_asyncio.fixture(autouse=True)
async def _fresh():
    from engines import db as _db_module
    _db_module._client = None
    _db_module._db = None
    db = _db_module.get_db()
    for c in (LIB, "live_tracking", gf.RUN_STATE_COLL,
              t12.SETTINGS_COLL, t12.SLOT_STATS_COLL,
              t12.PERF_COLL, t12.EVENTS_COLL):
        await db[c].delete_many({})
    yield
    for c in (LIB, "live_tracking", gf.RUN_STATE_COLL,
              t12.SETTINGS_COLL, t12.SLOT_STATS_COLL,
              t12.PERF_COLL, t12.EVENTS_COLL):
        await db[c].delete_many({})


# ─────────────────────────────────────────────────────────────────────
# Step 1 — Quality floor settings
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quality_floor_defaults_when_empty():
    floor = await t12.get_quality_floor()
    assert floor == t12.DEFAULT_QUALITY_FLOOR


@pytest.mark.asyncio
async def test_quality_floor_partial_override_merges_over_defaults():
    merged = await t12.set_quality_floor({"min_profit_factor": 1.5})
    assert merged["min_profit_factor"] == 1.5
    # Others should be the defaults
    assert merged["min_stability_score"] == t12.DEFAULT_QUALITY_FLOOR["min_stability_score"]
    assert merged["max_drawdown_pct"] == t12.DEFAULT_QUALITY_FLOOR["max_drawdown_pct"]


@pytest.mark.asyncio
async def test_quality_floor_ignores_unknown_keys():
    merged = await t12.set_quality_floor({"foo": 99, "min_profit_factor": 1.3})
    assert "foo" not in merged
    assert merged["min_profit_factor"] == 1.3


@pytest.mark.asyncio
async def test_quality_floor_rejects_non_numeric_values():
    with pytest.raises(ValueError):
        await t12.set_quality_floor({"min_profit_factor": "hello"})


@pytest.mark.asyncio
async def test_quality_floor_reset_restores_defaults():
    await t12.set_quality_floor({"min_profit_factor": 2.0})
    await t12.reset_quality_floor()
    floor = await t12.get_quality_floor()
    assert floor == t12.DEFAULT_QUALITY_FLOOR


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Recency weighting
# ─────────────────────────────────────────────────────────────────────

def test_recent_trades_weighted_more_than_old():
    now = datetime(2026, 4, 19, tzinfo=timezone.utc)
    # Recent wins are small; old losses are large. Unweighted PF ≈ 0.5.
    # With recency weighting (2× on last 6mo, 1× on older), PF rises.
    trades = [
        {"pnl": 10, "ts": (now - timedelta(days=30)).isoformat()},   # recent
        {"pnl": 10, "ts": (now - timedelta(days=60)).isoformat()},   # recent
        {"pnl": -10, "ts": (now - timedelta(days=400)).isoformat()}, # old
        {"pnl": -10, "ts": (now - timedelta(days=500)).isoformat()}, # old
    ]
    pf = t12.weighted_profit_factor(trades, now=now)
    # weighted num = 2*10 + 2*10 = 40; weighted den = 1*10 + 1*10 = 20 → PF 2.0
    assert pf == pytest.approx(2.0, rel=1e-3)


def test_recency_buckets_6_12mo_get_15x():
    now = datetime(2026, 4, 19, tzinfo=timezone.utc)
    assert t12._recency_weight(t12._months_ago(now - timedelta(days=30), now)) == 2.0
    assert t12._recency_weight(t12._months_ago(now - timedelta(days=270), now)) == 1.5
    assert t12._recency_weight(t12._months_ago(now - timedelta(days=700), now)) == 1.0
    # None timestamp → default 1×
    assert t12._recency_weight(None) == 1.0


def test_weighted_pf_returns_zero_when_no_trades():
    assert t12.weighted_profit_factor([]) == 0.0
    assert t12.weighted_profit_factor(None) == 0.0


def test_attach_recency_score_nondestructive():
    now = datetime(2026, 4, 19, tzinfo=timezone.utc)
    card = {
        "score": 75,
        "backtest": {
            "profit_factor": 1.4,
            "trades": [
                {"pnl": 5, "ts": (now - timedelta(days=10)).isoformat()},
                {"pnl": -2, "ts": (now - timedelta(days=20)).isoformat()},
            ],
        },
    }
    out = t12.attach_recency_score(card)
    assert out is card
    assert out["score"] == 75  # original preserved
    assert "recency_weighted_pf" in out
    assert out["recency_weighted_pf"] > 0


# ─────────────────────────────────────────────────────────────────────
# Step 4 — Slot stats
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slot_stats_rolling_update():
    await t12.update_slot_stats(pair="EURUSD", timeframe="H1", style="trend",
                                 generated=10, saved=3, pf_samples=[1.5, 1.8])
    s = await t12.get_slot_stats("EURUSD", "H1", "trend")
    assert s["n_generated"] == 10
    assert s["n_saved"] == 3
    assert s["success_rate"] == 0.3
    assert s["avg_pf"] > 0

    # Second run folds in
    await t12.update_slot_stats(pair="EURUSD", timeframe="H1", style="trend",
                                 generated=10, saved=7, pf_samples=[2.0])
    s2 = await t12.get_slot_stats("EURUSD", "H1", "trend")
    assert s2["n_generated"] == 20
    assert s2["n_saved"] == 10
    assert s2["success_rate"] == 0.5


@pytest.mark.asyncio
async def test_slot_stats_missing_slot_returns_zero_defaults():
    s = await t12.get_slot_stats("XAUUSD", "M5", "breakout")
    assert s["n_generated"] == 0
    assert s["n_saved"] == 0
    assert s["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_list_slot_stats_sorts_by_success_rate_desc():
    await t12.update_slot_stats(pair="EURUSD", timeframe="H1", style="trend",
                                 generated=10, saved=8)  # sr 0.8
    await t12.update_slot_stats(pair="GBPUSD", timeframe="H4", style="breakout",
                                 generated=10, saved=2)  # sr 0.2
    rows = await t12.list_slot_stats()
    assert rows[0]["pair"] == "EURUSD"
    assert rows[-1]["pair"] == "GBPUSD"


# ─────────────────────────────────────────────────────────────────────
# Step 5 — Adaptive per_combo
# ─────────────────────────────────────────────────────────────────────

def test_adaptive_returns_base_when_insufficient_samples():
    stats = {"n_generated": 2, "success_rate": 0.9}
    assert t12.adaptive_per_combo(stats, base=30) == 30


def test_adaptive_reduces_for_strong_slots():
    stats = {"n_generated": 100, "success_rate": 0.7}
    assert t12.adaptive_per_combo(stats, base=30) == t12.PER_COMBO_STRONG  # 20


def test_adaptive_increases_for_weak_slots():
    stats = {"n_generated": 100, "success_rate": 0.1}
    assert t12.adaptive_per_combo(stats, base=30) == t12.PER_COMBO_WEAK  # 45


def test_adaptive_returns_base_for_normal_slots():
    stats = {"n_generated": 100, "success_rate": 0.35}
    assert t12.adaptive_per_combo(stats, base=30) == 30


def test_adaptive_clamps_to_bounds():
    # Missing / malformed input
    assert t12.PER_COMBO_MIN <= t12.adaptive_per_combo({}, base=30) <= t12.PER_COMBO_MAX
    assert t12.PER_COMBO_MIN <= t12.adaptive_per_combo(None, base=99) <= t12.PER_COMBO_MAX


# ─────────────────────────────────────────────────────────────────────
# Step 3 — Performance snapshot
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_performance_snapshot_computes_survival_and_gap():
    from engines import db as _db
    db = _db.get_db()
    saved_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    await db[LIB].insert_one({
        "strategy_id": "sp1", "fingerprint": "fp_sp1", "status": "active",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend",
        "saved_at": saved_iso,
        "backtest": {"profit_factor": 1.5},
    })
    await db["live_tracking"].insert_one({
        "strategy_id": "sp1",
        "live_metrics": {"profit_factor": 1.2},
    })
    snap = await t12.record_performance_snapshot("sp1")
    assert snap["strategy_id"] == "sp1"
    assert 6 <= (snap["survival_days"] or 0) <= 8
    assert snap["backtest_pf"] == 1.5
    assert snap["live_pf"] == 1.2
    assert snap["live_vs_backtest_gap"] == pytest.approx(-0.3, abs=1e-3)


@pytest.mark.asyncio
async def test_performance_snapshot_unknown_strategy_returns_none():
    snap = await t12.record_performance_snapshot("nope")
    assert snap is None


# ─────────────────────────────────────────────────────────────────────
# Step 6 — Event log
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_event_log_append_and_filter():
    await t12.record_event("rejected", pair="EURUSD", timeframe="H1", style="trend",
                           strategy_id="x1", reasons=["pf too low"])
    await t12.record_event("retired", pair="GBPUSD", timeframe="H4", style="breakout",
                           strategy_id="x2", reasons=["loss streak 6"])
    await t12.record_event("replaced", pair="EURUSD", timeframe="H1", style="trend",
                           reasons=["auto_replacement_queued"])

    rejected = await t12.list_events(event_type="rejected")
    assert len(rejected) == 1
    assert rejected[0]["strategy_id"] == "x1"

    retired = await t12.list_events(event_type="retired")
    assert len(retired) == 1
    assert retired[0]["slot"]["pair"] == "GBPUSD"

    all_events = await t12.list_events()
    assert len(all_events) == 3


@pytest.mark.asyncio
async def test_event_log_rejects_invalid_type():
    with pytest.raises(ValueError):
        await t12.record_event("garbage", pair="EURUSD")
    with pytest.raises(ValueError):
        await t12.list_events(event_type="unknown")


# ─────────────────────────────────────────────────────────────────────
# Step 7 — Phase 11 integration (backward compatibility + floor override)
# ─────────────────────────────────────────────────────────────────────

def test_gem_factory_strict_floor_respects_phase12_override():
    """Direct unit check: when an override dict is passed, the gate uses it."""
    card = {
        "backtest": {"profit_factor": 1.3, "max_drawdown_pct": 5.0, "total_trades": 80},
        "stability_score": 60, "pass_probability": 60,
    }
    # Default floor (pf ≥ 1.2) → passes
    ok1, _ = gf._passes_strict_floor(card)
    assert ok1
    # Override to pf ≥ 1.5 → fails
    ok2, reasons2 = gf._passes_strict_floor(card, floor={"min_profit_factor": 1.5})
    assert not ok2
    assert any("pf" in r for r in reasons2)


def test_gem_factory_strict_floor_ignores_invalid_override_keys():
    card = {
        "backtest": {"profit_factor": 1.3, "max_drawdown_pct": 5.0, "total_trades": 80},
        "stability_score": 60, "pass_probability": 60,
    }
    ok, _ = gf._passes_strict_floor(card, floor={"bogus_key": 999})
    assert ok  # invalid key ignored → default floor applies


@pytest.mark.asyncio
async def test_gem_factory_accepts_per_combo_20():
    """Phase 12 requirement — strong slots can reduce per_combo to 20."""

    called_per_combo = {}

    async def fake_combo(pair, tf, style, *, per_combo, firm, top_n,
                         refine_top, prefilter_top):
        called_per_combo["value"] = per_combo
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}

    import engines.auto_factory_engine as afe
    orig = afe._run_one_combo
    afe._run_one_combo = fake_combo  # type: ignore
    try:
        summary = await gf.run_gem_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
            per_combo=20, m1_mode="off", auto_replace_retired=False,
        )
    finally:
        afe._run_one_combo = orig  # type: ignore

    # When no prior slot stats exist, adaptive returns the base (20 here).
    assert called_per_combo["value"] == 20
    assert summary["config"]["per_combo"] == 20
    # slot_results should now carry per_combo_used
    assert summary["slots"][0]["per_combo_used"] == 20


@pytest.mark.asyncio
async def test_gem_factory_adaptive_uses_slot_stats_to_override_base():
    """Strong prior stats → adaptive reduces per_combo below base regardless."""
    # Seed strong-slot history (>= SLOT_STRONG_MIN_SAMPLES, success_rate >= 0.5)
    await t12.update_slot_stats(pair="EURUSD", timeframe="H1", style="trend-following",
                                 generated=20, saved=15)

    called_per_combo = {}

    async def fake_combo(pair, tf, style, *, per_combo, firm, top_n,
                         refine_top, prefilter_top):
        called_per_combo["value"] = per_combo
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}

    import engines.auto_factory_engine as afe
    orig = afe._run_one_combo
    afe._run_one_combo = fake_combo  # type: ignore
    try:
        await gf.run_gem_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
            per_combo=45, m1_mode="off", auto_replace_retired=False,
        )
    finally:
        afe._run_one_combo = orig  # type: ignore

    # adaptive recommends PER_COMBO_STRONG (20) despite base=45
    assert called_per_combo["value"] == t12.PER_COMBO_STRONG


@pytest.mark.asyncio
async def test_gem_factory_writes_slot_stats_after_run():
    async def fake_combo(pair, tf, style, *, per_combo, firm, top_n,
                         refine_top, prefilter_top):
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}

    import engines.auto_factory_engine as afe
    orig = afe._run_one_combo
    afe._run_one_combo = fake_combo  # type: ignore
    try:
        await gf.run_gem_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
            per_combo=30, m1_mode="off", auto_replace_retired=False,
        )
    finally:
        afe._run_one_combo = orig  # type: ignore

    s = await t12.get_slot_stats("EURUSD", "H1", "trend-following")
    # No candidates → n_generated stays 0 (len(candidates) was 0).
    assert s["n_generated"] == 0


@pytest.mark.asyncio
async def test_gem_factory_logs_retire_event_from_sweep():
    """Retired strategies from the sweep emit a 'retired' event."""
    from engines import db as _db
    db = _db.get_db()
    # Pre-seed a degrading row that will cross into 'retired' this sweep
    await db[LIB].insert_one({
        "strategy_id": "sg_retire", "fingerprint": "fp_retire",
        "status": "degrading",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
    })
    await db["live_tracking"].insert_one({
        "strategy_id": "sg_retire",
        "live_metrics": {"profit_factor": 0.4, "current_loss_streak": 7,
                         "max_drawdown_pct": 5.0, "win_rate": 30},
    })

    async def fake_combo(pair, tf, style, *, per_combo, firm, top_n,
                         refine_top, prefilter_top):
        return {"status": "complete", "generated": 0, "top_returned": 0,
                "saved": 0, "saved_ids": [], "runtime_sec": 0.0}

    import engines.auto_factory_engine as afe
    orig = afe._run_one_combo
    afe._run_one_combo = fake_combo  # type: ignore
    try:
        summary = await gf.run_gem_factory(
            pairs=["EURUSD"], timeframes=["H1"], styles=["trend-following"],
            per_combo=30, m1_mode="off", auto_replace_retired=True,
        )
    finally:
        afe._run_one_combo = orig  # type: ignore

    assert summary["totals"]["retired"] == 1
    retired = await t12.list_events(event_type="retired")
    assert any(r["strategy_id"] == "sg_retire" for r in retired)
    replaced = await t12.list_events(event_type="replaced")
    assert len(replaced) >= 1
