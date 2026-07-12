"""
Unit tests for the Prop Firm Config Engine (Phase 2 — additive).

Regex extraction is tested offline (no DB / network). LLM fallback is NOT
invoked here (all required fields are present in the sample text, so
`_fields_needing_llm` returns an empty list).
"""

import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from engines.prop_firm_config_engine import (
    parse_pdf_bytes,
    regex_extract,
    _build_challenge_rules_doc,
    _slugify,
)


SAMPLE_TEXT = """
Demo PropFirm Challenge Rules.
Profit target: 10% within 30 days.
Maximum total drawdown is 10% from initial balance.
Maximum daily drawdown 5% based on equity.
Minimum 4 trading days required.
Consistency rule: max daily profit 50%.
Challenge fee: $549.
"""


def test_regex_extract_happy_path():
    out = regex_extract(SAMPLE_TEXT)
    assert out["max_total_drawdown"]["value"] == 10.0
    assert out["max_daily_drawdown"]["value"] == 5.0
    assert out["profit_target"]["value"] == 10.0
    assert out["min_trading_days"]["value"] == 4
    assert out["consistency_rules"]["value"]["max_daily_profit_pct"] == 50.0
    assert out["fees"]["value"] == 549.0
    for field in ("max_total_drawdown", "max_daily_drawdown", "profit_target"):
        assert out[field]["source"] == "regex"


def test_regex_extract_ignores_out_of_range():
    text = "Profit target 500%. Daily drawdown 0%. Min 999 trading days."
    out = regex_extract(text)
    # 500% and 0% must be rejected
    assert out["profit_target"] is None
    assert out["max_daily_drawdown"] is None
    # 999 days is out of sane range (>60)
    assert out["min_trading_days"] is None


def test_regex_extract_empty_text():
    out = regex_extract("")
    assert all(v is None for v in out.values())


def test_parse_pdf_bytes_roundtrip():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(50, 750, "Profit target 10%. Max total drawdown 10%.")
    c.drawString(50, 730, "Max daily drawdown 5%. Min 4 trading days.")
    c.save()
    blob = buf.getvalue()

    result = parse_pdf_bytes(blob)
    assert result["error"] is None
    assert result["pages"] == 1
    assert "10%" in result["text"]
    assert "4 trading days" in result["text"]


def test_slugify():
    assert _slugify("FTMO") == "ftmo"
    assert _slugify("My Funded FX") == "my_funded_fx"
    assert _slugify("  XYZ-123 ") == "xyz_123"
    assert _slugify("") == "firm"
    assert _slugify("!!!") == "firm"


def test_build_challenge_rules_doc():
    doc = _build_challenge_rules_doc(
        firm_slug="demo",
        firm_name="Demo",
        challenge_size=50000,
        rules={
            "max_total_drawdown": 8,
            "max_daily_drawdown": 4,
            "profit_target": 9,
            "min_trading_days": 5,
            "consistency_rules": {"max_daily_profit_pct": 40},
            "confidence_score": 88,
        },
        now="2026-01-15T00:00:00+00:00",
    )
    assert doc["firm_slug"] == "demo"
    assert doc["initial_balance"] == 50000
    assert doc["rules"]["total_dd"]["max_pct"] == 8
    assert doc["rules"]["daily_dd"]["max_pct"] == 4
    assert doc["rules"]["profit_target"]["target_pct"] == 9
    assert doc["rules"]["min_trading_days"]["days"] == 5
    assert doc["rules"]["min_trading_days"]["enabled"] is True
    assert doc["rules"]["consistency"]["enabled"] is True
    assert doc["rules"]["consistency"]["max_daily_profit_pct"] == 40
    assert doc["confidence_score"] == 88


def test_build_challenge_rules_doc_consistency_disabled_when_missing():
    doc = _build_challenge_rules_doc(
        firm_slug="x", firm_name="X", challenge_size=100000,
        rules={
            "max_total_drawdown": 10, "max_daily_drawdown": 5,
            "profit_target": 10, "min_trading_days": 0,
        },
        now="2026-01-15T00:00:00+00:00",
    )
    assert doc["rules"]["consistency"]["enabled"] is False
    assert doc["rules"]["min_trading_days"]["enabled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
