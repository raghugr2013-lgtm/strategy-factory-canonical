"""
Phase 8 — Challenge Portfolio Engine tests.

Scenarios required by the spec:
  1. Small budget           → only a few selections (budget binds).
  2. Large budget           → everything affordable gets picked.
  3. Mixed EV strategies    → greedy prioritizes by EV-per-dollar.

Plus edge-case coverage: max_challenges cap, negative-EV skipping,
malformed inputs silently dropped, risk summary fields present.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engines.challenge_portfolio import build_challenge_portfolio


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════
def _match(
    firm: str,
    *,
    ev: float,
    fee: float,
    prob: float = 70.0,
    robustness: str = "robust",
    risk_band: str = "low",
    max_dd: float = 4.0,
    strategy_id: str = "strat_1",
):
    """Build a matching-engine-shape entry already enriched by Phase 7."""
    return {
        "firm_slug": firm,
        "firm_name": firm.upper(),
        "strategy_id": strategy_id,
        "probability": {
            "pass_probability": prob,
            "structural_robustness": {"score": 90.0, "label": robustness},
        },
        "expected_value": {
            "expected_value": ev,
            "ev_grade": "good" if ev > 0 else "negative",
            "challenge_fee": fee,
            "risk_adjustment": {"risk_band": risk_band},
        },
        "max_drawdown_pct": max_dd,
    }


BIG_POOL = [
    _match("ftmo",       ev=20_000, fee=540, prob=85, robustness="robust"),
    _match("fundednext", ev=15_000, fee=549, prob=75, robustness="robust"),
    _match("pipfarm",    ev=12_000, fee=500, prob=70, robustness="moderate"),
    _match("myforex",    ev=8_000,  fee=600, prob=65, robustness="moderate"),
    _match("e8",         ev=4_000,  fee=900, prob=55, robustness="fragile"),   # worst ev/$
]


# ══════════════════════════════════════════════════════════════════════════
# 1. Small budget → few selections
# ══════════════════════════════════════════════════════════════════════════
class TestSmallBudget:
    def test_budget_binds_to_one(self):
        r = build_challenge_portfolio(BIG_POOL, budget=600)
        # Only ftmo at $540 fits.
        assert r["n_selected"] == 1
        assert r["selected"][0]["firm_slug"] == "ftmo"
        assert r["total_cost"] == 540.0
        assert r["remaining_budget"] == 60.0
        assert r["total_ev"] == 20_000.0

    def test_budget_zero_selects_nothing(self):
        r = build_challenge_portfolio(BIG_POOL, budget=0)
        assert r["n_selected"] == 0
        assert r["total_cost"] == 0
        assert r["total_ev"] == 0
        assert r["remaining_budget"] == 0

    def test_budget_below_cheapest_selects_nothing(self):
        r = build_challenge_portfolio(BIG_POOL, budget=400)
        assert r["n_selected"] == 0

    def test_skipped_includes_everything_not_selected(self):
        r = build_challenge_portfolio(BIG_POOL, budget=600)
        assert len(r["skipped"]) == len(BIG_POOL) - r["n_selected"]


# ══════════════════════════════════════════════════════════════════════════
# 2. Large budget → more selections
# ══════════════════════════════════════════════════════════════════════════
class TestLargeBudget:
    def test_unlimited_budget_selects_all_positive_ev(self):
        # All five matches are positive EV → all five selected.
        r = build_challenge_portfolio(BIG_POOL, budget=100_000)
        assert r["n_selected"] == len(BIG_POOL)
        selected_slugs = {c["firm_slug"] for c in r["selected"]}
        assert selected_slugs == {m["firm_slug"] for m in BIG_POOL}
        # Total cost is the sum of all fees.
        assert r["total_cost"] == sum(m["expected_value"]["challenge_fee"] for m in BIG_POOL)

    def test_medium_budget_selects_top_ranked(self):
        # $2,000 fits exactly ftmo ($540) + fundednext ($549) + pipfarm ($500)
        # = $1,589, then myforex at $600 would exceed → stopped.
        r = build_challenge_portfolio(BIG_POOL, budget=2_000)
        slugs = [c["firm_slug"] for c in r["selected"]]
        assert slugs == ["ftmo", "fundednext", "pipfarm"]
        assert r["total_cost"] == 540 + 549 + 500


# ══════════════════════════════════════════════════════════════════════════
# 3. Mixed EV → greedy prioritizes by EV / cost
# ══════════════════════════════════════════════════════════════════════════
class TestMixedEVPrioritization:
    def test_orders_by_ev_per_dollar(self):
        # ftmo    20000/540 = 37.0   (highest)
        # pipfarm 12000/500 = 24.0
        # fundednext 15000/549 = 27.3
        # myforex  8000/600 = 13.3
        # e8       4000/900 =  4.4  (lowest)
        # Correct order: ftmo, fundednext, pipfarm, myforex, e8.
        r = build_challenge_portfolio(BIG_POOL, budget=100_000)
        slugs = [c["firm_slug"] for c in r["selected"]]
        assert slugs == ["ftmo", "fundednext", "pipfarm", "myforex", "e8"]

    def test_low_ev_skipped_in_favor_of_smaller_higher_ratio(self):
        # Two items: expensive big-EV item vs cheap high-ratio item.
        # Budget only fits one of them.
        matches = [
            _match("expensive", ev=5_000,  fee=900, prob=60),   # ratio 5.55
            _match("cheap_hi",  ev=3_000,  fee=300, prob=75),   # ratio 10
        ]
        r = build_challenge_portfolio(matches, budget=900)
        # Greedy picks cheap_hi first (ratio 10) and still has $600 → but
        # expensive costs $900, doesn't fit. So only cheap_hi.
        slugs = [c["firm_slug"] for c in r["selected"]]
        assert slugs == ["cheap_hi"]

    def test_negative_ev_never_selected(self):
        matches = [
            _match("losing",   ev=-500,  fee=100, prob=10),
            _match("winning",  ev=3_000, fee=500, prob=75),
        ]
        r = build_challenge_portfolio(matches, budget=10_000)
        slugs = [c["firm_slug"] for c in r["selected"]]
        assert slugs == ["winning"]
        assert r["risk_summary"]["negative_ev_count"] == 0


# ══════════════════════════════════════════════════════════════════════════
# 4. max_challenges cap
# ══════════════════════════════════════════════════════════════════════════
class TestMaxChallengesCap:
    def test_cap_respected(self):
        r = build_challenge_portfolio(BIG_POOL, budget=100_000, max_challenges=2)
        assert r["n_selected"] == 2
        slugs = [c["firm_slug"] for c in r["selected"]]
        assert slugs == ["ftmo", "fundednext"]

    def test_cap_zero_yields_empty_portfolio(self):
        r = build_challenge_portfolio(BIG_POOL, budget=100_000, max_challenges=0)
        assert r["n_selected"] == 0

    def test_cap_none_treated_as_unlimited(self):
        r = build_challenge_portfolio(BIG_POOL, budget=100_000, max_challenges=None)
        assert r["n_selected"] == len(BIG_POOL)


# ══════════════════════════════════════════════════════════════════════════
# 5. Response shape, risk summary, malformed inputs
# ══════════════════════════════════════════════════════════════════════════
class TestResponseShape:
    def test_response_has_all_expected_keys(self):
        r = build_challenge_portfolio(BIG_POOL, budget=2_000)
        for key in (
            "selected", "skipped", "total_ev", "total_cost", "budget",
            "remaining_budget", "max_challenges", "n_selected",
            "n_considered", "risk_summary", "algorithm",
        ):
            assert key in r, f"missing {key}"
        assert r["algorithm"] == "greedy_ev_per_dollar"

    def test_risk_summary_aggregates(self):
        r = build_challenge_portfolio(BIG_POOL, budget=2_000)
        rs = r["risk_summary"]
        assert "avg_pass_probability" in rs
        assert "avg_ev_per_dollar" in rs
        assert "robustness_breakdown" in rs
        assert "risk_band_breakdown" in rs
        # All three selected items are robust or moderate → breakdown reflects that.
        total = sum(rs["robustness_breakdown"].values())
        assert total == r["n_selected"]

    def test_malformed_entries_silently_skipped(self):
        good = _match("ftmo", ev=10_000, fee=540, prob=75)
        malformed = [
            {},                                     # no firm
            {"firm_slug": "x"},                     # no EV
            {"firm_slug": "y", "expected_value": {"expected_value": 100}},  # no fee
            {"firm_slug": "z", "expected_value": {"expected_value": 500, "challenge_fee": 0}},  # bad fee
        ]
        r = build_challenge_portfolio([*malformed, good], budget=10_000)
        assert r["n_considered"] == 1
        assert r["n_selected"] == 1
        assert r["selected"][0]["firm_slug"] == "ftmo"

    def test_empty_input_returns_empty_portfolio(self):
        r = build_challenge_portfolio([], budget=10_000)
        assert r["n_selected"] == 0
        assert r["n_considered"] == 0
        assert r["total_ev"] == 0
        assert r["total_cost"] == 0

    def test_negative_budget_raises(self):
        with pytest.raises(ValueError):
            build_challenge_portfolio(BIG_POOL, budget=-1)

    def test_negative_max_challenges_raises(self):
        with pytest.raises(ValueError):
            build_challenge_portfolio(BIG_POOL, budget=1000, max_challenges=-2)
