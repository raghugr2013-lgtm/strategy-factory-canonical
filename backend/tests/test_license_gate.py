"""Phase 2 Stage 3.β — license gate tests (P2C.5)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import RawKnowledgeItem, now_iso  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge.license_gate import (  # noqa: E402
    LicenseOutcome,
    LicenseVerdict,
    classify,
    is_enabled,
)


def _item(*, license_=None, body: bytes = b"", extras=None) -> RawKnowledgeItem:
    return RawKnowledgeItem(
        domain=KnowledgeDomain.STRATEGY,
        connector_name="test",
        source_url="u", source_ref="r",
        content_hash="sha256:x",
        fetched_at=now_iso(),
        content_bytes=body,
        license=license_,
        extras=extras or {},
    )


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_LICENSE_GATE", raising=False)
    assert is_enabled() is False
    v = classify(_item(license_="MIT"))
    assert v.outcome is LicenseOutcome.UNKNOWN
    assert v.gated is False
    assert v.method == "none"


def test_spdx_permissive(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    for tag in ("MIT", "Apache-2.0", "BSD-3-Clause", "MPL-2.0", "ISC"):
        v = classify(_item(license_=tag))
        assert v.outcome is LicenseOutcome.PERMISSIVE, f"{tag} → {v.outcome}"
        assert v.method == "spdx"
        assert v.confidence == 1.0


def test_spdx_weak_copyleft(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    for tag in ("LGPL-3.0", "LGPL-2.1"):
        v = classify(_item(license_=tag))
        assert v.outcome is LicenseOutcome.WEAK_COPYLEFT
        assert v.method == "spdx"


def test_spdx_strong_copyleft(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    for tag in ("GPL-3.0", "GPL-2.0", "AGPL-3.0"):
        v = classify(_item(license_=tag))
        assert v.outcome is LicenseOutcome.STRONG_COPYLEFT


def test_spdx_proprietary(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    v = classify(_item(license_="Proprietary"))
    assert v.outcome is LicenseOutcome.PROPRIETARY


def test_extras_spdx_id_fallback(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    v = classify(_item(extras={"spdx_id": "MIT"}))
    assert v.outcome is LicenseOutcome.PERMISSIVE
    assert v.method == "spdx"


def test_heuristic_permissive(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    body = b"Copyright (c) 2026 Foo. This is released under the MIT License."
    v = classify(_item(body=body))
    assert v.outcome is LicenseOutcome.PERMISSIVE
    assert v.method == "heuristic"
    assert 0.5 <= v.confidence <= 1.0
    assert "MIT" in v.evidence.upper()


def test_heuristic_strong_copyleft(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    body = b"Licensed under the GNU General Public License v3."
    v = classify(_item(body=body))
    assert v.outcome is LicenseOutcome.STRONG_COPYLEFT


def test_heuristic_proprietary(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    body = b"Proprietary. All Rights Reserved. Do not redistribute."
    v = classify(_item(body=body))
    assert v.outcome is LicenseOutcome.PROPRIETARY


def test_unknown_when_no_signal(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    v = classify(_item(body=b"//@version=5\nstrategy('foo')"))
    assert v.outcome is LicenseOutcome.UNKNOWN
    assert v.confidence == 0.0


def test_confidence_bounded_0_1(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    v = classify(_item(license_="MIT"))
    assert 0.0 <= v.confidence <= 1.0


def test_verdict_to_outcome_shape(monkeypatch):
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    v = classify(_item(license_="MIT"))
    d = v.to_outcome()
    for k in ("outcome", "spdx_id", "confidence", "method", "evidence", "gated"):
        assert k in d
    assert d["outcome"] == "permissive"
    assert d["gated"] is True
