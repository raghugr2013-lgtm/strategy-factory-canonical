"""
Backend API tests for Prop Firm Intelligence Layer (Phase 3).

Tests:
  - POST /api/prop-firms/discover-challenges (PDF multi-plan, no input, PDF > 5MB, unreachable URL)
  - POST /api/prop-firms/save-challenges (valid with mirror, empty challenges, no mirror)
  - GET /api/prop-firms/intelligence/list
  - GET /api/prop-firms/intelligence/{slug} (nonexistent)
  - DELETE /api/prop-firms/intelligence/{slug}
  - Verify /api/challenge-firms includes mirrored plans
  - Regression: Phase 2 endpoints still work
  - Regression: seeded firms still present
"""

import io
import os
import pytest
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

# Use localhost for testing as per agent instructions
if "preview.emergentagent.com" in BASE_URL:
    BASE_URL = "http://localhost:8001"


def create_multi_plan_pdf():
    """Create a test PDF with multiple prop firm challenge plans."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    lines = [
        "Acme Prop Challenges",
        "",
        "Two-Step Evaluation",
        "$10,000 Account - Challenge fee: $89",
        "Phase 1: 8% profit target",
        "Phase 2: 5% profit target",
        "Maximum total drawdown 10%. Maximum daily drawdown 5%.",
        "Minimum 4 trading days.",
        "",
        "$25,000 Account - Challenge fee: $199",
        "Phase 1: 8% profit target",
        "Phase 2: 5% profit target",
        "Maximum total drawdown 10%. Maximum daily drawdown 5%.",
        "Minimum 4 trading days.",
        "",
        "$100,000 Account - Challenge fee: $549",
        "Phase 1: 8% profit target",
        "Phase 2: 5% profit target",
        "Maximum total drawdown 10%. Maximum daily drawdown 5%.",
        "Minimum 4 trading days.",
        "",
        "One-Step Direct",
        "$50,000 account, challenge fee $299.",
        "Profit target 10%.",
        "Maximum total drawdown 6%. Maximum daily drawdown 3%.",
        "Minimum 3 trading days.",
    ]
    y = 770
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
        if y < 50:
            c.showPage()
            y = 770
    c.save()
    buf.seek(0)
    return buf.getvalue()


def create_large_pdf():
    """Create a PDF > 5MB for testing size limit."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Add lots of pages with lots of text to exceed 5MB
    for page in range(2000):
        for i in range(60):
            c.drawString(50, 750 - i * 12, f"Page {page} Line {i}: " + "X" * 200)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


class TestDiscoverChallenges:
    """Tests for POST /api/prop-firms/discover-challenges"""

    def test_discover_pdf_multi_plan_success(self):
        """PDF with multiple plans should return 200 with ≥4 challenges, each with 100% confidence."""
        pdf_bytes = create_multi_plan_pdf()
        files = {"pdf": ("acme_challenges.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"firm_name": "TEST_Acme Prop"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/discover-challenges", files=files, data=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        challenges = result.get("challenges", [])
        assert len(challenges) >= 4, f"Expected ≥4 challenges, got {len(challenges)}"
        
        # Verify each challenge has required fields
        for c in challenges:
            assert "account_size" in c
            assert "type" in c
            assert "fee" in c
            assert "rules" in c
            assert "confidence" in c
            assert c["source"] == "regex"
            assert c["confidence"] == 100, f"Expected 100% confidence, got {c['confidence']}"
        
        # Verify sources_used includes pdf
        assert "pdf" in result.get("sources_used", [])
        
        print(f"✓ Discover PDF multi-plan: {len(challenges)} challenges found, all 100% confidence")

    def test_discover_no_url_no_pdf_returns_400(self):
        """No website_url and no PDF should return 400."""
        data = {"firm_name": "TEST_Firm"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/discover-challenges", data=data)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        result = response.json()
        assert "detail" in result
        assert "website" in result["detail"].lower() or "pdf" in result["detail"].lower()
        print(f"✓ No input returns 400: {result['detail']}")

    @pytest.mark.skip(reason="Creating 5MB+ PDF takes too long for CI")
    def test_discover_pdf_over_5mb_returns_400(self):
        """PDF > 5MB should return 400."""
        pdf_bytes = create_large_pdf()
        assert len(pdf_bytes) > 5 * 1024 * 1024, f"PDF should be > 5MB, got {len(pdf_bytes)}"
        
        files = {"pdf": ("large.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"firm_name": "TEST_Firm"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/discover-challenges", files=files, data=data)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        result = response.json()
        assert "5 MB" in result["detail"] or "5MB" in result["detail"]
        print(f"✓ PDF > 5MB returns 400: {result['detail']}")

    def test_discover_unreachable_website_graceful_fallback(self):
        """Unreachable website should return 200 with method='none' and still extract from PDF."""
        pdf_bytes = create_multi_plan_pdf()
        files = {"pdf": ("acme.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {
            "firm_name": "TEST_Firm",
            "website_url": "https://nonexistent-domain-xyz123.invalid/rules"
        }
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/discover-challenges", files=files, data=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Pages should show method='none' or error
        pages = result.get("pages", [])
        assert len(pages) > 0, "Should have attempted to crawl pages"
        for p in pages:
            assert p.get("method") == "none" or p.get("error") is not None
        
        # Should still extract from PDF
        assert "pdf" in result.get("sources_used", [])
        assert len(result.get("challenges", [])) >= 4
        
        print(f"✓ Unreachable website graceful fallback: {len(pages)} pages attempted, PDF extraction worked")


class TestSaveChallenges:
    """Tests for POST /api/prop-firms/save-challenges"""

    def test_save_with_mirror_to_rules_true(self):
        """Valid save with mirror_to_rules=true should create mirrored plan slugs."""
        payload = {
            "firm_name": "TEST_Save Mirror",
            "website": None,
            "mirror_to_rules": True,
            "challenges": [
                {"account_size": 10000, "type": "2-step", "fee": 89, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"},
                {"account_size": 25000, "type": "2-step", "fee": 199, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"},
                {"account_size": 50000, "type": "1-step", "fee": 299, "rules": {"profit_target": 10, "max_total_drawdown": 6, "max_daily_drawdown": 3, "min_trading_days": 3}, "confidence": 100, "source": "regex"},
                {"account_size": 100000, "type": "2-step", "fee": 549, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"},
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prop-firms/save-challenges",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert result["status"] == "saved"
        mirrored = result.get("mirrored_plan_slugs", [])
        assert len(mirrored) == 4, f"Expected 4 mirrored slugs, got {len(mirrored)}"
        
        # Verify slug pattern: {firm_slug}_{sizek}k_{type}
        expected_patterns = ["test_save_mirror_10k_2step", "test_save_mirror_25k_2step", "test_save_mirror_50k_1step", "test_save_mirror_100k_2step"]
        for pattern in expected_patterns:
            assert pattern in mirrored, f"Expected {pattern} in mirrored slugs"
        
        print(f"✓ Save with mirror: {mirrored}")
        
        # Verify plans appear in challenge-firms
        firms_resp = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms = firms_resp.json().get("firms", {})
        for slug in mirrored:
            assert slug in firms, f"Mirrored slug {slug} should be in challenge-firms"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/prop-firms/intelligence/test_save_mirror")

    def test_save_empty_challenges_returns_400(self):
        """Empty challenges list should return 400."""
        payload = {
            "firm_name": "TEST_Empty",
            "challenges": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prop-firms/save-challenges",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        result = response.json()
        assert "empty" in result["detail"].lower()
        print(f"✓ Empty challenges returns 400: {result['detail']}")

    def test_save_with_mirror_to_rules_false(self):
        """Save with mirror_to_rules=false should NOT add plans to challenge-firms."""
        payload = {
            "firm_name": "TEST_No Mirror",
            "website": None,
            "mirror_to_rules": False,
            "challenges": [
                {"account_size": 10000, "type": "2-step", "fee": 89, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"}
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prop-firms/save-challenges",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert result["status"] == "saved"
        mirrored = result.get("mirrored_plan_slugs", [])
        assert len(mirrored) == 0, f"Expected 0 mirrored slugs, got {len(mirrored)}"
        
        # Verify plans do NOT appear in challenge-firms
        firms_resp = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms = firms_resp.json().get("firms", {})
        assert "test_no_mirror_10k_2step" not in firms, "No-mirror plan should NOT be in challenge-firms"
        
        print("✓ Save without mirror: mirrored_plan_slugs empty, not in challenge-firms")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/prop-firms/intelligence/test_no_mirror")


class TestIntelligenceList:
    """Tests for GET /api/prop-firms/intelligence/list"""

    def test_list_returns_count_and_firms(self):
        """List should return count and firms array."""
        response = requests.get(f"{BASE_URL}/api/prop-firms/intelligence/list")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert "count" in result
        assert "firms" in result
        assert isinstance(result["firms"], list)
        
        print(f"✓ Intelligence list: count={result['count']}")


class TestIntelligenceGetAndDelete:
    """Tests for GET/DELETE /api/prop-firms/intelligence/{slug}"""

    def test_get_nonexistent_slug_returns_404(self):
        """GET nonexistent slug should return 404."""
        response = requests.get(f"{BASE_URL}/api/prop-firms/intelligence/algo-trader-hub-26")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ GET nonexistent slug returns 404")

    def test_delete_removes_firm_and_mirrored_plans(self):
        """DELETE should remove firm doc AND all mirrored plan rows from challenge_rules."""
        # First create a firm with mirrored plans
        payload = {
            "firm_name": "TEST_Delete Firm",
            "mirror_to_rules": True,
            "challenges": [
                {"account_size": 10000, "type": "2-step", "fee": 89, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"},
                {"account_size": 25000, "type": "2-step", "fee": 199, "rules": {"profit_target": 8, "max_total_drawdown": 10, "max_daily_drawdown": 5, "min_trading_days": 4}, "confidence": 100, "source": "regex"},
            ]
        }
        save_resp = requests.post(
            f"{BASE_URL}/api/prop-firms/save-challenges",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert save_resp.status_code == 200
        mirrored = save_resp.json().get("mirrored_plan_slugs", [])
        
        # Verify plans exist in challenge-firms
        firms_resp = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms_before = firms_resp.json().get("firms", {})
        for slug in mirrored:
            assert slug in firms_before, f"Mirrored slug {slug} should be in challenge-firms before delete"
        
        # Delete
        del_resp = requests.delete(f"{BASE_URL}/api/prop-firms/intelligence/test_delete_firm")
        assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}: {del_resp.text}"
        result = del_resp.json()
        assert result["status"] == "deleted"
        assert result["removed_firms"] == 1
        assert result["removed_plan_rules"] == 2
        
        # Verify plans are gone from challenge-firms
        firms_resp2 = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms_after = firms_resp2.json().get("firms", {})
        for slug in mirrored:
            assert slug not in firms_after, f"Mirrored slug {slug} should NOT be in challenge-firms after delete"
        
        print(f"✓ DELETE removes firm and {result['removed_plan_rules']} mirrored plans")


class TestRegressionPhase2:
    """Regression tests for Phase 2 endpoints"""

    def test_phase2_extract_still_works(self):
        """Phase 2 /api/prop-firms/extract should still work."""
        pdf_bytes = create_multi_plan_pdf()
        files = {"pdf": ("rules.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"firm_name": "TEST_Phase2 Extract", "challenge_size": "100000"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/extract", files=files, data=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert result["confidence"] == 100
        assert "pdf" in result["sources_used"]
        print(f"✓ Phase 2 extract still works: confidence={result['confidence']}")

    def test_phase2_save_still_works(self):
        """Phase 2 /api/prop-firms/save should still work."""
        payload = {
            "firm_name": "TEST_Phase2 Save",
            "challenge_size": 100000,
            "rules": {
                "max_total_drawdown": 10.0,
                "max_daily_drawdown": 5.0,
                "profit_target": 10.0,
                "min_trading_days": 4
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prop-firms/save",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert result["status"] == "saved"
        assert result["config"]["firm_slug"] == "test_phase2_save"
        print(f"✓ Phase 2 save still works: slug={result['config']['firm_slug']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/prop-firms/test_phase2_save")


class TestRegressionSeededFirms:
    """Regression tests for seeded firms"""

    def test_seeded_firms_still_present(self):
        """Default seeded firms (ftmo/fundednext/pipfarm) should still be present."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        firms = result.get("firms", {})
        expected_firms = ["ftmo", "fundednext", "pipfarm"]
        for firm in expected_firms:
            assert firm in firms, f"Seeded firm '{firm}' should be in challenge-firms"
        
        print(f"✓ Seeded firms present: {expected_firms}")

    def test_simulate_challenge_endpoint_reachable(self):
        """Simulate challenge endpoint should still be reachable."""
        payload = {
            "firm_slug": "ftmo",
            "strategy_text": "Buy when RSI < 30, sell when RSI > 70",
            "pair": "EURUSD",
            "timeframe": "H1"
        }
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        # May fail due to missing data, but should not 404
        assert response.status_code != 404, "simulate-challenge endpoint should exist"
        print(f"✓ /api/simulate-challenge endpoint reachable (status={response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
