"""
Backend API tests for Prop Firm Config System (Phase 2).

Tests:
  - POST /api/prop-firms/extract (PDF-only, no input, invalid challenge_size, unreachable URL)
  - POST /api/prop-firms/save (valid, invalid challenge_size)
  - GET /api/prop-firms/list
  - GET /api/prop-firms/{slug} (nonexistent)
  - DELETE /api/prop-firms/{slug}
  - Verify /api/challenge-firms includes new firms and excludes deleted ones
  - Regression: existing endpoints still work
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


def create_test_pdf():
    """Create a test PDF with prop firm rules."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    lines = [
        "Profit target 10%.",
        "Maximum total drawdown 10%.",
        "Maximum daily drawdown 5%.",
        "Minimum 4 trading days.",
        "Consistency rule: max daily profit 50%.",
        "Challenge fee: $549.",
    ]
    for i, line in enumerate(lines):
        c.drawString(50, 750 - i * 20, line)
    c.save()
    buf.seek(0)
    return buf.getvalue()


def create_large_pdf():
    """Create a PDF > 5MB for testing size limit."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Add lots of text to make it large
    for page in range(200):
        for i in range(50):
            c.drawString(50, 750 - i * 14, f"Page {page} Line {i}: " + "X" * 100)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


class TestPropFirmExtract:
    """Tests for POST /api/prop-firms/extract"""

    def test_extract_pdf_only_success(self):
        """PDF-only input should return 200 with confidence 100 and all fields extracted."""
        pdf_bytes = create_test_pdf()
        files = {"pdf": ("rules.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"firm_name": "Regression Firm", "challenge_size": "100000"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/extract", files=files, data=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Verify confidence is 100 (all 4 required fields extracted)
        assert result["confidence"] == 100, f"Expected confidence 100, got {result['confidence']}"
        
        # Verify all required fields extracted with source=regex
        extracted = result["extracted"]
        assert extracted["max_total_drawdown"]["value"] == 10.0
        assert extracted["max_total_drawdown"]["source"] == "regex"
        assert extracted["max_daily_drawdown"]["value"] == 5.0
        assert extracted["max_daily_drawdown"]["source"] == "regex"
        assert extracted["profit_target"]["value"] == 10.0
        assert extracted["profit_target"]["source"] == "regex"
        assert extracted["min_trading_days"]["value"] == 4
        assert extracted["min_trading_days"]["source"] == "regex"
        
        # Verify pdf_path is saved
        assert result.get("pdf_path") is not None, "pdf_path should be saved"
        assert "pdf" in result["sources_used"]
        
        print(f"✓ Extract PDF-only success: confidence={result['confidence']}, sources={result['sources_used']}")

    def test_extract_no_website_no_pdf_returns_400(self):
        """No website_url and no PDF should return 400."""
        data = {"firm_name": "Test Firm", "challenge_size": "100000"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/extract", data=data)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        result = response.json()
        assert "detail" in result
        assert "website" in result["detail"].lower() or "pdf" in result["detail"].lower()
        print(f"✓ No input returns 400: {result['detail']}")

    def test_extract_challenge_size_below_1000_returns_400(self):
        """challenge_size < 1000 should return 400."""
        pdf_bytes = create_test_pdf()
        files = {"pdf": ("rules.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"firm_name": "Test Firm", "challenge_size": "500"}
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/extract", files=files, data=data)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        result = response.json()
        assert "1000" in result["detail"] or "challenge_size" in result["detail"].lower()
        print(f"✓ challenge_size=500 returns 400: {result['detail']}")

    def test_extract_unreachable_website_graceful_fallback(self):
        """Unreachable website should return 200 with graceful fallback."""
        pdf_bytes = create_test_pdf()
        files = {"pdf": ("rules.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {
            "firm_name": "Test Firm",
            "challenge_size": "100000",
            "website_url": "https://nonexistent-domain-xyz123.invalid/rules"
        }
        
        response = requests.post(f"{BASE_URL}/api/prop-firms/extract", files=files, data=data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Should still extract from PDF
        assert result["confidence"] == 100
        
        # website_meta should indicate error or method=none
        website_meta = result.get("website_meta", {})
        assert website_meta.get("error") is not None or website_meta.get("method") == "none"
        
        print(f"✓ Unreachable website graceful fallback: website_meta={website_meta}")


class TestPropFirmSave:
    """Tests for POST /api/prop-firms/save"""

    def test_save_valid_config(self):
        """Valid save should return 200 with status=saved and firm_slug."""
        payload = {
            "firm_name": "Test Save Firm",
            "website": "https://example.com",
            "challenge_size": 100000,
            "rules": {
                "max_total_drawdown": 10.0,
                "max_daily_drawdown": 5.0,
                "profit_target": 10.0,
                "min_trading_days": 4,
                "consistency_rules": {"max_daily_profit_pct": 50.0},
                "fees": 549.0,
                "confidence_score": 100
            },
            "extraction_meta": {"confidence": 100, "sources_used": ["pdf"]},
            "pdf_path": None
        }
        
        response = requests.post(
            f"{BASE_URL}/api/prop-firms/save",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert result["status"] == "saved"
        assert "config" in result
        assert result["config"]["firm_slug"] == "test_save_firm"
        
        print(f"✓ Save valid config: slug={result['config']['firm_slug']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/prop-firms/test_save_firm")

    def test_save_challenge_size_below_1000_returns_400(self):
        """challenge_size < 1000 should return 400."""
        payload = {
            "firm_name": "Test Firm",
            "challenge_size": 500,
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
        
        assert response.status_code == 400 or response.status_code == 422, f"Expected 400/422, got {response.status_code}: {response.text}"
        print("✓ Save with challenge_size=500 returns error")


class TestPropFirmList:
    """Tests for GET /api/prop-firms/list"""

    def test_list_returns_count_and_configs(self):
        """List should return count and configs array."""
        response = requests.get(f"{BASE_URL}/api/prop-firms/list")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert "count" in result
        assert "configs" in result
        assert isinstance(result["configs"], list)
        
        print(f"✓ List returns count={result['count']}, configs array")


class TestPropFirmGetAndDelete:
    """Tests for GET/DELETE /api/prop-firms/{slug}"""

    def test_get_nonexistent_slug_returns_404(self):
        """GET nonexistent slug should return 404."""
        response = requests.get(f"{BASE_URL}/api/prop-firms/algo-trader-hub-26")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✓ GET nonexistent slug returns 404")

    def test_delete_removes_config_and_challenge_rules(self):
        """DELETE should remove both prop_firm_configs and challenge_rules entries."""
        # First create a firm
        payload = {
            "firm_name": "Delete Test Firm",
            "challenge_size": 100000,
            "rules": {
                "max_total_drawdown": 10.0,
                "max_daily_drawdown": 5.0,
                "profit_target": 10.0,
                "min_trading_days": 4
            }
        }
        save_resp = requests.post(
            f"{BASE_URL}/api/prop-firms/save",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert save_resp.status_code == 200
        slug = save_resp.json()["config"]["firm_slug"]
        
        # Verify it appears in challenge-firms
        firms_resp = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert firms_resp.status_code == 200
        firms_before = firms_resp.json().get("firms", {})
        assert slug in firms_before, f"Firm {slug} should be in challenge-firms before delete"
        
        # Delete
        del_resp = requests.delete(f"{BASE_URL}/api/prop-firms/{slug}")
        assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}: {del_resp.text}"
        result = del_resp.json()
        assert result["status"] == "deleted"
        
        # Verify it's gone from challenge-firms
        firms_resp2 = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms_after = firms_resp2.json().get("firms", {})
        assert slug not in firms_after, f"Firm {slug} should NOT be in challenge-firms after delete"
        
        print("✓ DELETE removes config and challenge_rules entry")


class TestChallengeFirmsIntegration:
    """Tests for /api/challenge-firms integration"""

    def test_challenge_firms_includes_seeded_firms(self):
        """Default seeded firms (ftmo/fundednext/pipfarm) should be present."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        firms = result.get("firms", {})
        # At least the seeded firms should exist
        expected_firms = ["ftmo", "fundednext", "pipfarm"]
        for firm in expected_firms:
            assert firm in firms, f"Seeded firm '{firm}' should be in challenge-firms"
        
        print(f"✓ Challenge-firms includes seeded firms: {list(firms.keys())}")

    def test_new_firm_appears_in_challenge_firms(self):
        """Newly saved firm should appear in /api/challenge-firms."""
        # Create a new firm
        payload = {
            "firm_name": "Integration Test Firm",
            "challenge_size": 50000,
            "rules": {
                "max_total_drawdown": 8.0,
                "max_daily_drawdown": 4.0,
                "profit_target": 12.0,
                "min_trading_days": 3
            }
        }
        save_resp = requests.post(
            f"{BASE_URL}/api/prop-firms/save",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert save_resp.status_code == 200
        slug = save_resp.json()["config"]["firm_slug"]
        
        # Check it appears in challenge-firms
        firms_resp = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert firms_resp.status_code == 200
        firms = firms_resp.json().get("firms", {})
        assert slug in firms, f"New firm '{slug}' should appear in challenge-firms"
        
        print(f"✓ New firm appears in challenge-firms: {slug}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/prop-firms/{slug}")


class TestExistingEndpointsRegression:
    """Regression tests for existing endpoints"""

    def test_health_endpoint(self):
        """Health endpoint should still work."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        print("✓ /api/health works")

    def test_challenge_firms_endpoint(self):
        """Challenge firms endpoint should still work."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert response.status_code == 200
        result = response.json()
        assert "firms" in result
        print(f"✓ /api/challenge-firms works: {len(result['firms'])} firms")

    def test_simulate_challenge_endpoint(self):
        """Simulate challenge endpoint should still work (basic check)."""
        # Just verify the endpoint exists and accepts requests
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
        print(f"✓ /api/simulate-challenge endpoint exists (status={response.status_code})")

    @pytest.mark.skip(reason="match-prop-firms endpoint not implemented in Phase 2")
    def test_match_prop_firms_endpoint(self):
        """Match prop firms endpoint should still work (basic check)."""
        payload = {
            "strategy_text": "Buy when RSI < 30",
            "pair": "EURUSD",
            "timeframe": "H1"
        }
        response = requests.post(
            f"{BASE_URL}/api/match-prop-firms",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        # May fail due to missing data, but should not 404
        assert response.status_code != 404, "match-prop-firms endpoint should exist"
        print(f"✓ /api/match-prop-firms endpoint exists (status={response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
