"""Unit tests for Prop Firm Intelligence (Phase 3 — additive)."""

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from engines.prop_firm_intelligence import (
    _block_score,
    _classify_type,
    _firm_slug,
    _normalize_size,
    _plan_slug,
    _segment_by_size,
    parse_pdf_bytes,
    regex_discover_challenges,
)


SAMPLE_ACME = """
Acme Prop Challenges

Two-Step Evaluation

$10,000 Account — Challenge fee: $89
Phase 1: 8% profit target
Phase 2: 5% profit target
Maximum total drawdown 10%. Maximum daily drawdown 5%.
Minimum 4 trading days required.

$25,000 Account — Challenge fee: $199
Phase 1: 8% profit target
Phase 2: 5% profit target
Maximum total drawdown 10%. Maximum daily drawdown 5%.
Minimum 4 trading days.

$100,000 Account — Challenge fee: $549
Phase 1: 8% profit target
Phase 2: 5% profit target
Maximum total drawdown 10%. Maximum daily drawdown 5%.
Minimum 4 trading days.

One-Step Direct

$50,000 account, challenge fee $299.
Profit target 10%.
Maximum total drawdown 6%. Maximum daily drawdown 3%.
Minimum 3 trading days.

Instant Funding

$25,000 account, fee $399.
Maximum total drawdown 4%. Maximum daily drawdown 2%.
"""


def test_normalize_size_variants():
    assert _normalize_size("100", "k") == 100000
    assert _normalize_size("100,000", "") == 100000
    assert _normalize_size("100000", "") == 100000
    assert _normalize_size("25", "K") == 25000
    # out of range or non-multiple of 1k
    assert _normalize_size("999", "") is None
    assert _normalize_size("12345", "") is None


def test_classify_type_keywords():
    assert _classify_type("This is a two-step challenge") == "2-step"
    assert _classify_type("One-step direct program") == "1-step"
    assert _classify_type("Instant funding available now") == "instant"
    # Heuristic via phase mentions
    assert _classify_type("Phase 1 target 8%. Phase 2 target 5%.") == "2-step"
    assert _classify_type("Phase 1 target 10%.") == "1-step"
    assert _classify_type("just prices") == "unknown"


def test_segment_by_size_keeps_richest_block():
    blocks = dict(_segment_by_size(SAMPLE_ACME))
    assert 10000 in blocks
    assert 25000 in blocks
    assert 50000 in blocks
    assert 100000 in blocks
    # richest block for 100k must mention drawdown + phases
    assert "drawdown" in blocks[100000].lower()
    assert "phase" in blocks[100000].lower()


def test_regex_discover_challenges_acme():
    plans = regex_discover_challenges(SAMPLE_ACME)
    by_size = {p["account_size"]: p for p in plans}
    # 10k, 25k, 50k, 100k all found (instant 25k overrides 2-step 25k via
    # block-score — but both blocks contain "25,000"; richest wins).
    assert 10000 in by_size
    assert 50000 in by_size
    assert 100000 in by_size

    p10k = by_size[10000]
    assert p10k["type"] == "2-step"
    assert p10k["rules"]["profit_target"] == 8.0
    assert p10k["rules"]["profit_target_phase2"] == 5.0
    assert p10k["rules"]["max_total_drawdown"] == 10.0
    assert p10k["rules"]["max_daily_drawdown"] == 5.0
    assert p10k["rules"]["min_trading_days"] == 4
    assert p10k["fee"] == 89.0
    assert p10k["source"] == "regex"
    assert p10k["confidence"] == 100

    p50k = by_size[50000]
    assert p50k["type"] == "1-step"
    assert p50k["rules"]["profit_target"] == 10.0
    assert p50k["rules"]["max_total_drawdown"] == 6.0
    assert p50k["fee"] == 299.0


def test_regex_discover_empty_text():
    assert regex_discover_challenges("") == []
    assert regex_discover_challenges("random text with no sizes") == []


def test_parse_pdf_bytes_challenge_page():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in [
        "Acme Prop Two-Step Challenge",
        "$100,000 Account - Fee $549",
        "Phase 1: 8% profit target",
        "Phase 2: 5% profit target",
        "Maximum total drawdown 10%",
        "Maximum daily drawdown 5%",
        "Minimum 4 trading days",
    ]:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    blob = buf.getvalue()
    parsed = parse_pdf_bytes(blob)
    assert parsed["error"] is None
    plans = regex_discover_challenges(parsed["text"])
    assert len(plans) == 1
    assert plans[0]["account_size"] == 100000
    assert plans[0]["type"] == "2-step"
    assert plans[0]["fee"] == 549.0
    assert plans[0]["rules"]["profit_target"] == 8.0
    assert plans[0]["rules"]["max_total_drawdown"] == 10.0


def test_slug_helpers():
    assert _firm_slug("Acme Prop") == "acme_prop"
    assert _plan_slug("acme_prop", 100000, "2-step") == "acme_prop_100k_2step"
    assert _plan_slug("acme_prop", 50000, "1-step") == "acme_prop_50k_1step"
    assert _plan_slug("acme_prop", 25000, "instant") == "acme_prop_25k_instant"
    assert _plan_slug("x", 10000, "unknown") == "x_10k_plan"


def test_block_score_prefers_rule_keywords():
    a = "Phase 1 target profit drawdown daily fee days"
    b = "just some account text"
    assert _block_score(a) > _block_score(b)
