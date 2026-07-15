"""
Iteration 5 — AI Learning Layer (v1.1.1) backend tests.

Covers:
  * /api/knowledge/status
  * /api/knowledge/rebuild (admin-only)
  * /api/knowledge/lookup
  * /api/knowledge/preview-prompt
  * Idempotence of rebuild
  * Recovered-doc fence signal (is_recovered)
  * Extractor smoke test (offline)
  * KNOWLEDGE_INJECTION default-off code path presence
  * Curated ingestion sources (HIGH_SIGNAL_QUERIES / CURATED_REPOS / helpers)
  * Collector defaults + env override
  * Regression sanity: prior endpoints still 200
  * 90 routers/attachers online
"""
from __future__ import annotations

import os
import sys
import time
import uuid
import subprocess
from typing import Dict, List, Any

import pymongo
import pytest
import requests

# Test collection seed sentinel — used for cleanup.
TEST_SEED_MARK = True

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fall back to reading the frontend .env directly (test harness quirk)
    try:
        with open("/app/frontend/.env") as fh:
            for ln in fh:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = ln.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME") or "strategy_factory_v1"

ADMIN_EMAIL = "admin@strategy-factory.local"
ADMIN_PASS = "admin123"


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def mongo_db():
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    assert tok, f"no access_token in login response: {body}"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def non_admin_token(mongo_db, admin_headers):
    """Signup a fresh user, approve via admin, then log in as that user."""
    # signup lowercases email server-side; we must match the same casing for the
    # DB lookup below.
    email = f"test_kn_regular_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "RegularUser123!"
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={"email": email, "password": pwd, "name": "TEST Knowledge Regular"},
        timeout=15,
    )
    assert r.status_code in (200, 201), f"signup failed: {r.status_code} {r.text[:200]}"
    # Fetch user_id from DB (signup returns 'pending')
    user_doc = mongo_db["users"].find_one({"email": email}, {"_id": 0, "user_id": 1})
    if not user_doc:
        pytest.skip(f"could not locate freshly signed-up user {email}")
    user_id = user_doc["user_id"]
    # Approve via admin
    ap = requests.post(
        f"{BASE_URL}/api/admin/approve/{user_id}",
        headers=admin_headers, timeout=15,
    )
    assert ap.status_code == 200, f"approve failed: {ap.status_code} {ap.text[:200]}"
    # Login as this user
    lr = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": pwd}, timeout=15,
    )
    if lr.status_code != 200:
        pytest.skip(f"non-admin login not possible after approve: {lr.status_code} {lr.text[:200]}")
    body = lr.json()
    tok = body.get("access_token") or body.get("token")
    yield tok
    # Cleanup user
    try:
        mongo_db["users"].delete_one({"email": email})
    except Exception:
        pass


# ── Router mount sanity ─────────────────────────────────────────────

def test_backend_reports_90_routers():
    """Verify legacy full-recovery mount reports 90 routers/attachers online."""
    try:
        out = subprocess.check_output(
            ["grep", "-c", "90 routers/attachers online", "/var/log/supervisor/backend.err.log"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as e:
        out = e.output or "0"
    assert int(out) >= 1, f"expected >=1 boot with '90 routers/attachers online', got {out}"


# ── /api/knowledge/status ───────────────────────────────────────────

def test_knowledge_status_shape(admin_headers):
    r = requests.get(f"{BASE_URL}/api/knowledge/status", headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    for key in ("collection", "total", "per_source", "per_verdict", "top_pairs", "last_index_ts"):
        assert key in data, f"missing key {key!r}: {data.keys()}"
    assert data["collection"] == "strategy_knowledge_index"
    assert isinstance(data["total"], int)
    assert isinstance(data["per_source"], dict)
    assert isinstance(data["per_verdict"], dict)
    assert isinstance(data["top_pairs"], dict)


# ── /api/knowledge/rebuild auth guard ───────────────────────────────

def test_rebuild_requires_token():
    r = requests.post(
        f"{BASE_URL}/api/knowledge/rebuild",
        json={"scope": "full"}, timeout=15,
    )
    assert r.status_code == 401, f"expected 401 without token, got {r.status_code} {r.text[:200]}"


def test_rebuild_forbidden_for_non_admin(non_admin_token):
    r = requests.post(
        f"{BASE_URL}/api/knowledge/rebuild",
        json={"scope": "full"},
        headers={"Authorization": f"Bearer {non_admin_token}"},
        timeout=15,
    )
    assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code} {r.text[:200]}"


# ── End-to-end: seed → rebuild → status → lookup → preview ─────────

@pytest.fixture(scope="module")
def seeded_library(mongo_db):
    """Seed 6 __test_seed docs into strategy_library. Half are recovered."""
    docs = []
    for i in range(6):
        h = f"TEST_KN_{uuid.uuid4().hex[:12]}_{i}"
        stype = "trend_following" if i % 2 == 0 else "mean_reversion"
        indicators = ["ema", "rsi"] if stype == "trend_following" else ["rsi", "bollinger"]
        text = (
            f"STRATEGY: TEST kn {i}\n"
            f"TYPE: {stype}\n"
            f"INDICATORS: {', '.join(indicators)}\n"
            f"ENTRY LONG: {'ema20 crosses above ema50' if stype=='trend_following' else 'rsi<30 in range'}\n"
            f"EXIT: atr trailing\n"
            f"RISK MODEL: atr_stop\n"
        )
        doc = {
            "__test_seed": True,
            "strategy_hash": h,
            "pair": "EURUSD",
            "timeframe": "1h",
            "type": stype,
            "indicators": indicators,
            "text": text,
            "best_pf": 1.6 + (i * 0.08),   # 1.60 .. 2.00, all >=1.5 → win (dd<=15)
            "best_dd": 8 + i,              # 8..13, all <=15
        }
        if i < 3:
            doc["__migration_source"] = "strategy_factory_recovery"
        docs.append(doc)
    mongo_db["strategy_library"].insert_many(docs)
    yield docs
    # Cleanup — remove test seed docs and their index rows.
    mongo_db["strategy_library"].delete_many({"__test_seed": True})
    hashes = [d["strategy_hash"] for d in docs]
    mongo_db["strategy_knowledge_index"].delete_many(
        {"strategy_hash": {"$in": hashes}}
    )


def _rebuild_full(admin_headers):
    r = requests.post(
        f"{BASE_URL}/api/knowledge/rebuild",
        json={"scope": "full"}, headers=admin_headers, timeout=60,
    )
    assert r.status_code == 200, f"rebuild failed: {r.status_code} {r.text[:300]}"
    return r.json()


def test_rebuild_writes_seeded_docs(admin_headers, seeded_library):
    body = _rebuild_full(admin_headers)
    for key in ("scope", "started_at", "finished_at", "took_ms",
                "cutoff", "per_source", "total_written", "total_read"):
        assert key in body, f"missing key {key!r}: {body}"
    assert body["scope"] == "full"
    assert isinstance(body["per_source"], dict)
    assert isinstance(body["total_written"], int)
    assert isinstance(body["total_read"], int)
    assert body["total_written"] >= 6, f"expected >=6 written, got {body['total_written']}"
    assert body["per_source"].get("library", 0) >= 6


def test_status_reflects_seeded_docs(admin_headers, seeded_library, mongo_db):
    r = requests.get(f"{BASE_URL}/api/knowledge/status", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # DB may have other index rows unrelated to seed → assert >= not ==
    # But verify seeded docs are captured by counting via direct pymongo.
    hashes = [d["strategy_hash"] for d in seeded_library]
    seeded_index_rows = list(mongo_db["strategy_knowledge_index"].find(
        {"strategy_hash": {"$in": hashes}}
    ))
    assert len(seeded_index_rows) == 6, f"expected 6 seed rows in index, got {len(seeded_index_rows)}"
    for row in seeded_index_rows:
        assert row.get("verdict") == "win", f"expected verdict=win, got {row.get('verdict')} for {row.get('strategy_hash')}"
        assert row.get("source") == "library"
        assert row.get("pair") == "EURUSD"
        assert row.get("timeframe") == "1h"


def test_lookup_returns_winners(admin_headers, seeded_library):
    r = requests.get(
        f"{BASE_URL}/api/knowledge/lookup",
        params={"pair": "EURUSD", "timeframe": "1h",
                "style": "trend_following", "top_k": 5},
        headers=admin_headers, timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["total_scanned"] >= 6
    winners = data["winners"]
    assert isinstance(winners, list)
    assert len(winners) <= 5
    assert len(winners) >= 1, "expected at least one winner from seeded docs"
    w = winners[0]
    for key in ("hash", "type", "pair", "tf", "indicators", "risk", "verdict", "pf", "dd", "gist"):
        assert key in w, f"lookup winner missing key {key}: {w.keys()}"


def test_preview_prompt(admin_headers, seeded_library):
    r = requests.post(
        f"{BASE_URL}/api/knowledge/preview-prompt",
        json={
            "pair": "EURUSD", "timeframe": "1h",
            "style": "trend_following",
            "indicators": ["ema", "rsi"], "top_k": 5,
        },
        headers=admin_headers, timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    pb = data.get("prompt_block", "")
    assert isinstance(pb, str) and pb
    assert pb.startswith("Prior knowledge from"), f"prompt_block wrong prefix: {pb[:120]!r}"
    assert "pair=EURUSD" in pb
    assert "tf=1h" in pb
    assert "style=trend_following" in pb
    assert "Historical WINNERS to draw from" in pb


def test_rebuild_idempotence(admin_headers, seeded_library, mongo_db):
    """Two consecutive full rebuilds must be upserts, not duplicates."""
    b1 = _rebuild_full(admin_headers)
    hashes = [d["strategy_hash"] for d in seeded_library]
    count_after_first = mongo_db["strategy_knowledge_index"].count_documents(
        {"strategy_hash": {"$in": hashes}}
    )
    b2 = _rebuild_full(admin_headers)
    count_after_second = mongo_db["strategy_knowledge_index"].count_documents(
        {"strategy_hash": {"$in": hashes}}
    )
    assert count_after_second == count_after_first, (
        f"expected no dupe rows after 2nd rebuild — "
        f"before={count_after_first} after={count_after_second}"
    )
    # total_written on 2nd run: still counts upsert-hits (spec says == total_read)
    assert b2["total_written"] == b2["total_read"], (
        f"2nd rebuild: written {b2['total_written']} != read {b2['total_read']}"
    )


def test_recovered_flag_persisted(admin_headers, seeded_library, mongo_db):
    """Docs stamped with __migration_source=strategy_factory_recovery should
    surface with is_recovered=True in the knowledge index."""
    recovered_hashes = [d["strategy_hash"] for d in seeded_library[:3]]
    rows = list(mongo_db["strategy_knowledge_index"].find(
        {"strategy_hash": {"$in": recovered_hashes}}
    ))
    assert len(rows) == 3
    for r in rows:
        assert r.get("is_recovered") is True, (
            f"expected is_recovered=True for recovered doc {r.get('strategy_hash')}: {r}"
        )


# ── Extractor smoke test (offline) ──────────────────────────────────

def test_extractor_smoke():
    """Runs the offline extractor smoke test from the review request."""
    result = subprocess.run(
        [sys.executable, "-c",
         "from engines.knowledge.extractor import extract_features; "
         "f = extract_features({'strategy_hash':'abc','pair':'EURUSD','timeframe':'1h','indicators':['ema','rsi'],"
         "'text':'STRATEGY: X\\nTYPE: trend_following\\nENTRY LONG: ema20 crosses above ema50\\nEXIT: atr trailing\\nRISK MODEL: atr_stop'}); "
         "print(f.strategy_hash, f.pair, f.strategy_type, f.indicators, f.verdict, f.knowledge_signature)"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": "/app/backend/legacy"},
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    line = result.stdout.strip()
    assert line.startswith("abc EURUSD trend_following ['ema', 'rsi'] neutral"), line
    sig = line.split()[-1]
    assert len(sig) == 16, f"knowledge_signature should be 16 chars, got {len(sig)}: {sig!r}"


# ── KNOWLEDGE_INJECTION default-off code path ───────────────────────

def test_knowledge_injection_hook_present_and_default_off():
    """Verify strategy_engine.py contains the guarded conditional block,
    that KNOWLEDGE_INJECTION is NOT set in the running backend, and that
    the env-flag check + try/except + _LLM_STATS increment all exist."""
    src = open("/app/backend/legacy/engines/strategy_engine.py").read()
    assert 'os.environ.get("KNOWLEDGE_INJECTION"' in src
    assert 'from engines.knowledge import retrieve, build_block' in src
    assert 'knowledge_injected' in src
    # try/except must wrap the retrieval
    assert 'except Exception as e' in src  # broad but present in retrieval block
    # And confirm flag is default OFF at test time
    assert os.environ.get("KNOWLEDGE_INJECTION", "").lower() not in ("true", "1", "yes", "on")


# ── Curated ingestion sources ───────────────────────────────────────

def test_curated_sources_exports():
    from engines.strategy_ingestion.curated_sources import (
        HIGH_SIGNAL_QUERIES, CURATED_REPOS,
        all_curated_full_names, normalize_repo_full_name,
    )
    assert isinstance(HIGH_SIGNAL_QUERIES, list) and len(HIGH_SIGNAL_QUERIES) >= 8
    for q in HIGH_SIGNAL_QUERIES:
        assert isinstance(q, str) and q.strip(), f"empty query: {q!r}"
        modifiers = ("language:", "filename:", "extension:", "topic:", "stars:")
        assert any(m in q for m in modifiers), f"query lacks advanced modifier: {q!r}"
    assert isinstance(CURATED_REPOS, list) and len(CURATED_REPOS) >= 10
    for entry in CURATED_REPOS:
        assert isinstance(entry, tuple) and len(entry) == 3
        for s in entry:
            assert isinstance(s, str) and s.strip()
    names = all_curated_full_names()
    assert len(names) == len(CURATED_REPOS)
    assert all("/" in n and n.strip() for n in names)
    # helper
    assert normalize_repo_full_name(("owner", "repo", "why")) == "owner/repo"


def test_collector_defaults_changed():
    result = subprocess.run(
        [sys.executable, "-c",
         "from engines.strategy_ingestion.collector import DEFAULT_GITHUB_QUERIES; "
         "assert len(DEFAULT_GITHUB_QUERIES) >= 8; "
         "assert not any(q.strip() in ('pine script strategy forex','mt5 expert advisor forex','forex trading strategy python') for q in DEFAULT_GITHUB_QUERIES); "
         "print('OK', len(DEFAULT_GITHUB_QUERIES))"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": "/app/backend/legacy"},
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert result.stdout.strip().startswith("OK"), result.stdout


def test_env_override_queries():
    result = subprocess.run(
        [sys.executable, "-c",
         "import os; os.environ['INGESTION_GITHUB_QUERIES']='a,b'; "
         "from engines.strategy_ingestion.collector import _env_override_queries; "
         "print(_env_override_queries())"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": "/app/backend/legacy",
             "INGESTION_GITHUB_QUERIES": "a,b"},
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "['a', 'b']" in result.stdout, result.stdout


# ── Regression: earlier endpoints still 200 ─────────────────────────

REGRESSION_ENDPOINTS = [
    ("GET", "/api/library/list", None),
    ("GET", "/api/strategies/explorer", None),
    ("GET", "/api/prop-firms/list", None),
    ("GET", "/api/admin/providers", None),
    ("GET", "/api/llm/diagnostics", None),
]


@pytest.mark.parametrize("method,path,body", REGRESSION_ENDPOINTS)
def test_regression_endpoints_ok(method, path, body, admin_headers):
    if method == "GET":
        r = requests.get(f"{BASE_URL}{path}", headers=admin_headers, timeout=20)
    else:
        r = requests.request(method, f"{BASE_URL}{path}", json=body,
                             headers=admin_headers, timeout=20)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
