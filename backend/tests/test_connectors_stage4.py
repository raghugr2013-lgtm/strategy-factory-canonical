"""Phase 2 Stage 4 — Concrete connectors' behaviour (P4A.1–P4A.5).

Covers all five Stage-4 connectors. Each test is self-contained; no
real network I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import DiscoveryQuery, Reference  # noqa: E402
from engines.knowledge.connectors.arxiv import ArxivConnector  # noqa: E402
from engines.knowledge.connectors.pdf import PdfConnector  # noqa: E402
from engines.knowledge.connectors.propfirm import PropFirmConnector  # noqa: E402
from engines.knowledge.connectors.tradingview import TradingViewConnector  # noqa: E402
from engines.knowledge.connectors.internal_mongo import (  # noqa: E402
    InternalMongoConnector, _stable_hash,
)
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402


def _enable_framework(monkeypatch, per_connector_flag: str) -> None:
    monkeypatch.setenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", "true")
    monkeypatch.setenv(per_connector_flag, "true")


# ── Fake async DB (used by internal_mongo tests) ─────────────────────

class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


class _FakeColl:
    def __init__(self, rows):
        self._rows = rows
    def find(self, q):
        return _FakeCursor(self._rows)


class _FakeDB:
    def __init__(self, mapping):
        self._m = mapping
    def __getitem__(self, name):
        return _FakeColl(self._m.get(name, []))


# ── ArxivConnector ───────────────────────────────────────────────────

class TestArxiv:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", raising=False)
        monkeypatch.delenv("UKIE_CONNECTOR_ARXIV_ENABLED", raising=False)
        c = ArxivConnector()
        assert c.is_flag_enabled() is False

    def test_supported_domains(self):
        assert KnowledgeDomain.RESEARCH in ArxivConnector.supported_domains
        assert KnowledgeDomain.STRATEGY not in ArxivConnector.supported_domains

    @pytest.mark.asyncio
    async def test_discover_yields_seeded_refs(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_ARXIV_ENABLED")
        c = ArxivConnector()
        c.seed([
            Reference(connector_name="arxiv",
                      source_url="https://arxiv.org/abs/1234", source_ref="1234",
                      target_domain=KnowledgeDomain.RESEARCH,
                      extras={"abstract": "A regime-detection paper.",
                              "authors": "A. Trader", "citations": 50}),
        ])
        seen = []
        async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.RESEARCH,
                                                  limit=10)):
            seen.append(r)
        assert len(seen) == 1
        assert seen[0].source_ref == "1234"

    @pytest.mark.asyncio
    async def test_discover_flag_off_yields_nothing(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_ARXIV_ENABLED", raising=False)
        c = ArxivConnector()
        c.seed([Reference(connector_name="arxiv", source_url="u", source_ref="r",
                          target_domain=KnowledgeDomain.RESEARCH)])
        seen = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.RESEARCH))]
        assert seen == []

    @pytest.mark.asyncio
    async def test_fetch_produces_valid_item(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_ARXIV_ENABLED")
        c = ArxivConnector()
        ref = Reference(connector_name="arxiv", source_url="u", source_ref="1234",
                        target_domain=KnowledgeDomain.RESEARCH,
                        extras={"abstract": "hi", "authors": "A", "citations": 5})
        item = await c.fetch(ref)
        assert item.domain == KnowledgeDomain.RESEARCH
        assert item.content_hash.startswith("sha256:")
        assert item.extras["connector_version"] == c.connector_version

    def test_rate_limit_configured(self):
        rl = ArxivConnector().rate_limit()
        assert rl.requests_per_minute == 60


# ── PdfConnector ─────────────────────────────────────────────────────

class TestPdf:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_PDF_ENABLED", raising=False)
        c = PdfConnector()
        assert c.is_flag_enabled() is False

    def test_supported_domains_include_research(self):
        for d in (KnowledgeDomain.RESEARCH, KnowledgeDomain.STRATEGY,
                  KnowledgeDomain.EXECUTION, KnowledgeDomain.INDICATOR):
            assert d in PdfConnector.supported_domains

    @pytest.mark.asyncio
    async def test_discover_yields_only_matching_domain(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_PDF_ENABLED")
        c = PdfConnector()
        c.seed([
            Reference(connector_name="pdf", source_url="a", source_ref="a",
                      target_domain=KnowledgeDomain.RESEARCH),
            Reference(connector_name="pdf", source_url="b", source_ref="b",
                      target_domain=KnowledgeDomain.EXECUTION),
        ])
        got_r = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.RESEARCH))]
        got_e = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.EXECUTION))]
        assert len(got_r) == 1 and got_r[0].source_ref == "a"
        assert len(got_e) == 1 and got_e[0].source_ref == "b"

    @pytest.mark.asyncio
    async def test_fetch_uses_text_hint(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_PDF_ENABLED")
        c = PdfConnector()
        ref = Reference(connector_name="pdf", source_url="u", source_ref="r",
                        target_domain=KnowledgeDomain.RESEARCH,
                        extras={"text": "Pre-extracted body."})
        item = await c.fetch(ref)
        assert item.content_bytes == b"Pre-extracted body."
        assert item.extras["parser_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_curated_flag_propagated(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_PDF_ENABLED")
        c = PdfConnector()
        ref = Reference(connector_name="pdf", source_url="u", source_ref="r",
                        target_domain=KnowledgeDomain.RESEARCH,
                        extras={"text": "hi", "curated": True})
        item = await c.fetch(ref)
        assert item.extras.get("curated") is True

    def test_capabilities(self):
        caps = PdfConnector.capabilities
        assert caps.supports_discovery is False
        assert caps.supports_incremental_sync is True


# ── PropFirmConnector ────────────────────────────────────────────────

class TestPropFirm:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_PROPFIRM_ENABLED", raising=False)
        c = PropFirmConnector()
        assert c.is_flag_enabled() is False

    def test_execution_domain_only(self):
        assert PropFirmConnector.supported_domains == frozenset({KnowledgeDomain.EXECUTION})

    def test_default_trust_tier(self):
        assert PropFirmConnector.default_trust_tier == 4

    @pytest.mark.asyncio
    async def test_discover_walks_allowlist(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_PROPFIRM_ENABLED")
        c = PropFirmConnector(allowlist=[
            {"firm_name": "ftmo", "rulebook_url": "https://ftmo.com/rules",
             "auth": "none", "curated_trust_tier": 4},
            {"firm_name": "myff", "rulebook_url": "https://myff/rules",
             "auth": "none", "curated_trust_tier": 5},
        ])
        got = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.EXECUTION))]
        assert len(got) == 2
        firms = sorted(r.extras["firm_name"] for r in got)
        assert firms == ["ftmo", "myff"]

    @pytest.mark.asyncio
    async def test_fetch_stamps_proprietary_license(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_PROPFIRM_ENABLED")
        c = PropFirmConnector()
        ref = Reference(connector_name="propfirm", source_url="u",
                        source_ref="firm@rulebook",
                        target_domain=KnowledgeDomain.EXECUTION,
                        extras={"firm_name": "test", "text": "Max daily drawdown: 5%"})
        item = await c.fetch(ref)
        assert item.license == "proprietary"
        assert item.author == "test"
        assert item.content_bytes == b"Max daily drawdown: 5%"

    def test_conservative_rate_limit(self):
        rl = PropFirmConnector().rate_limit()
        assert rl.requests_per_minute <= 10


# ── TradingViewConnector ─────────────────────────────────────────────

class TestTradingView:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_TRADINGVIEW_ENABLED", raising=False)
        c = TradingViewConnector()
        assert c.is_flag_enabled() is False

    def test_dual_domain_support(self):
        assert KnowledgeDomain.STRATEGY in TradingViewConnector.supported_domains
        assert KnowledgeDomain.INDICATOR in TradingViewConnector.supported_domains

    @pytest.mark.asyncio
    async def test_fetch_detects_mpl_header(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_TRADINGVIEW_ENABLED")
        c = TradingViewConnector()
        pine = (
            "// This source code is subject to the terms of the Mozilla Public License 2.0\n"
            "// @version=5\nstrategy('MPL EMA cross')\n"
        )
        ref = Reference(connector_name="tradingview", source_url="u", source_ref="r",
                        target_domain=KnowledgeDomain.STRATEGY,
                        extras={"pine_source": pine})
        item = await c.fetch(ref)
        assert item.license == "MPL-2.0"
        assert item.license_confidence >= 0.8
        assert item.content_mime == "text/x-pine"

    @pytest.mark.asyncio
    async def test_fetch_without_mpl_header_unknown(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_TRADINGVIEW_ENABLED")
        c = TradingViewConnector()
        pine = "// @version=5\nstrategy('proprietary')\n"
        ref = Reference(connector_name="tradingview", source_url="u", source_ref="r",
                        target_domain=KnowledgeDomain.STRATEGY,
                        extras={"pine_source": pine})
        item = await c.fetch(ref)
        assert item.license is None
        assert item.license_confidence == 0.0

    @pytest.mark.asyncio
    async def test_house_scripts_curated_flag(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_TRADINGVIEW_ENABLED")
        c = TradingViewConnector()
        ref = Reference(connector_name="tradingview", source_url="u", source_ref="r",
                        target_domain=KnowledgeDomain.INDICATOR,
                        extras={"pine_source": "// @version=5\nindicator('house')",
                                "tv_house_scripts": True})
        item = await c.fetch(ref)
        assert item.extras["curated"] is True

    @pytest.mark.asyncio
    async def test_discover_filters_by_domain(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_TRADINGVIEW_ENABLED")
        c = TradingViewConnector()
        c.seed([
            Reference(connector_name="tradingview", source_url="a", source_ref="s1",
                      target_domain=KnowledgeDomain.STRATEGY),
            Reference(connector_name="tradingview", source_url="b", source_ref="i1",
                      target_domain=KnowledgeDomain.INDICATOR),
        ])
        s = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.STRATEGY))]
        i = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.INDICATOR))]
        assert len(s) == 1 and s[0].source_ref == "s1"
        assert len(i) == 1 and i[0].source_ref == "i1"


# ── InternalMongoConnector ───────────────────────────────────────────

class TestInternalMongo:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED", raising=False)
        c = InternalMongoConnector()
        assert c.is_flag_enabled() is False

    def test_internal_history_domain_only(self):
        assert InternalMongoConnector.supported_domains == frozenset({KnowledgeDomain.INTERNAL_HISTORY})

    def test_trust_tier_is_t5(self):
        assert InternalMongoConnector.default_trust_tier == 5

    def test_stable_hash_ignores_id(self):
        a = {"_id": "1", "x": 1, "y": 2}
        b = {"_id": "999", "y": 2, "x": 1}
        assert _stable_hash(a) == _stable_hash(b)

    @pytest.mark.asyncio
    async def test_discover_walks_source_collections(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED")
        db = _FakeDB({
            "strategy_library": [{"_id": "s1", "strategy_id": "abc"}],
            "mutation_events":  [{"_id": "e1", "event_id": "ev-1"}],
        })
        c = InternalMongoConnector(
            db_getter=lambda: db,
            source_collections=["strategy_library", "mutation_events"],
        )
        got = [r async for r in c.discover(DiscoveryQuery(domain=KnowledgeDomain.INTERNAL_HISTORY))]
        assert len(got) == 2
        collections = sorted(r.extras["collection"] for r in got)
        assert collections == ["mutation_events", "strategy_library"]

    @pytest.mark.asyncio
    async def test_fetch_produces_json_content(self, monkeypatch):
        _enable_framework(monkeypatch, "UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED")
        c = InternalMongoConnector(db_getter=lambda: _FakeDB({}))
        ref = Reference(connector_name="internal_mongo",
                        source_url="mongo://strategy_library/s1", source_ref="sha256:x",
                        target_domain=KnowledgeDomain.INTERNAL_HISTORY,
                        extras={"collection": "strategy_library", "row_id": "s1",
                                "row": {"strategy_id": "abc", "score": 42}})
        item = await c.fetch(ref)
        assert item.domain == KnowledgeDomain.INTERNAL_HISTORY
        assert item.content_mime == "application/json"
        assert item.license == "internal"
        assert item.extras["curated"] is True
        assert b"strategy_id" in item.content_bytes
