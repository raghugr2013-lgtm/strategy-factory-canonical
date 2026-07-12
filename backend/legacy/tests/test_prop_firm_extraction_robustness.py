"""Phase-2/3 prop-firm extraction — robustness regression tests.

Locks in three real-world phrasing bugs found while verifying the
hybrid prop-firm system:

  * `min_trading_days` regex must accept "Minimum trading days: 4"
    (number AFTER the keyword), not just "minimum 4 trading days".
  * Multi-plan phase-1/phase-2 detection must accept the "8% phase 1,
    5% phase 2" ordering (number BEFORE the phase keyword), the form
    used by FundedNext, MyFundedFX, etc.
  * Type classification must NOT bleed across plan blocks — the 200k
    1-step plan after a 100k 2-step block should still classify as
    "1-step", not inherit the previous block's "2-step" label.
"""
from __future__ import annotations

from engines.prop_firm_config_engine import regex_extract
from engines.prop_firm_intelligence import regex_discover_challenges


# ── Single-config regex extractor ────────────────────────────────────


def test_single_extractor_min_trading_days_keyword_first():
    """`Minimum trading days: 4` (number AFTER keyword)."""
    text = (
        "Maximum total drawdown: 10%\n"
        "Maximum daily drawdown: 5%\n"
        "Profit target: 10%\n"
        "Minimum trading days: 4\n"
    )
    out = regex_extract(text)
    assert out["min_trading_days"] is not None, "min_trading_days regex failed"
    assert out["min_trading_days"]["value"] == 4


def test_single_extractor_min_trading_days_number_first():
    """`minimum 4 trading days` (legacy phrasing — must still work)."""
    text = "Profit target 10% and minimum 4 trading days are required."
    out = regex_extract(text)
    assert out["min_trading_days"]["value"] == 4


def test_single_extractor_all_four_required_fields():
    """Hard floor: regex_extract must recover all 4 priority fields
    from a plain prop-firm rules listing without any LLM help."""
    text = (
        "FTMO Challenge Rules\n"
        "Maximum total drawdown: 10%\n"
        "Maximum daily drawdown: 5%\n"
        "Profit target: 10%\n"
        "Minimum trading days: 4\n"
    )
    out = regex_extract(text)
    assert out["max_total_drawdown"]["value"] == 10.0
    assert out["max_daily_drawdown"]["value"] == 5.0
    assert out["profit_target"]["value"] == 10.0
    assert out["min_trading_days"]["value"] == 4


# ── Multi-plan discovery extractor ──────────────────────────────────


def _multi_plan_text() -> str:
    return (
        "FundedNext Plans\n\n"
        "$25,000 account - 2-step challenge\n"
        "Profit target: 8% phase 1, 5% phase 2\n"
        "Daily drawdown: 5%, total drawdown: 10%\n"
        "Min trading days: 5\n"
        "Fee: $148\n\n"
        "$100,000 account - 2-step challenge\n"
        "Profit target: 8% phase 1, 5% phase 2\n"
        "Daily drawdown: 5%, total drawdown: 10%\n"
        "Fee: $548\n\n"
        "$200,000 account - 1-step challenge\n"
        "Profit target: 10%\n"
        "Daily drawdown: 5%, total drawdown: 8%\n"
        "Fee: $1080\n"
    )


def test_multi_discover_all_three_plan_sizes_detected():
    plans = regex_discover_challenges(_multi_plan_text())
    sizes = sorted(p["account_size"] for p in plans)
    assert sizes == [25000, 100000, 200000]


def test_multi_discover_phase_keyword_after_percent():
    """`Profit target: 8% phase 1, 5% phase 2` — number BEFORE phase
    keyword. Must be parsed correctly."""
    plans = regex_discover_challenges(_multi_plan_text())
    p25 = next(p for p in plans if p["account_size"] == 25000)
    assert p25["rules"]["profit_target"] == 8.0
    assert p25["rules"]["profit_target_phase2"] == 5.0
    p100 = next(p for p in plans if p["account_size"] == 100000)
    assert p100["rules"]["profit_target"] == 8.0
    assert p100["rules"]["profit_target_phase2"] == 5.0


def test_multi_discover_no_type_bleed_across_blocks():
    """200k plan is 1-step in the source — must NOT inherit the
    preceding 100k block's 2-step label."""
    plans = regex_discover_challenges(_multi_plan_text())
    p200 = next(p for p in plans if p["account_size"] == 200000)
    assert p200["type"] == "1-step", (
        f"200k plan should classify as 1-step, got '{p200['type']}' "
        "(type-bleed regression)"
    )


def test_multi_discover_classifies_2step_correctly():
    """Sanity: 25k & 100k both have explicit 2-step keyword on their
    own header line and must be classified as 2-step."""
    plans = regex_discover_challenges(_multi_plan_text())
    p25 = next(p for p in plans if p["account_size"] == 25000)
    p100 = next(p for p in plans if p["account_size"] == 100000)
    assert p25["type"] == "2-step"
    assert p100["type"] == "2-step"


def test_multi_discover_recovers_per_plan_fee():
    plans = regex_discover_challenges(_multi_plan_text())
    fee_by_size = {p["account_size"]: p["fee"] for p in plans}
    assert fee_by_size[25000] == 148.0
    assert fee_by_size[100000] == 548.0
    assert fee_by_size[200000] == 1080.0


def test_multi_discover_recovers_per_plan_min_days():
    """Min trading days: 5 — number AFTER keyword phrasing — must
    survive in the discovery extractor too."""
    plans = regex_discover_challenges(_multi_plan_text())
    p25 = next(p for p in plans if p["account_size"] == 25000)
    assert p25["rules"]["min_trading_days"] == 5
