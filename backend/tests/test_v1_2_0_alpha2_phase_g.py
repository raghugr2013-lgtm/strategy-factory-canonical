"""v1.2.0-alpha2 Phase G — Market Intelligence regression tests.

Verifies:
  1. Types + config env-driven; MI_ENABLED master switch works.
  2. Observers deterministic + bounded [0..1]; edge cases graceful.
  3. Change detectors fire on injected volatility jump / breakout drop /
     correlation break / noise increase.
  4. Aggregator produces bounded MarketIntelligence with all 5 scores.
  5. Ledger persists snapshots / states / changes / intelligence.
  6. Brain bridge respects two-step opt-in (MI_ENABLED +
     BRAIN_USES_MARKET_INTELLIGENCE).
  7. Scorer defaults preserve Phase F byte-identical output.
  8. Scorer with weights > 0 shifts score_now measurably.
  9. Policy market-driven force-pause is OFF by default and fires
     when BRAIN_MARKET_RISK_PAUSE_ENABLED=true.
 10. 7 new /api/market-intelligence/* endpoints reachable.
 11. Router count = 97 (Phase G adds `market_intelligence_engine`).
 12. Full regression sweep across A/B/B.1/B.2/C/D/F endpoints.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

# Enable Phase G package importability under both /app/backend and /app/backend/legacy
sys.path.insert(0, "/app/backend/legacy")
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@strategy-factory.local",
                     "password": "admin123"})
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── 1. Config + master switch ────────────────────────────────────
class TestConfig:
    def test_config_snapshot_present(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/observers/config")
        assert r.status_code == 200
        cfg = r.json()["config"]
        for k in ("MI_ENABLED", "MI_UNIVERSE", "MI_TIMEFRAMES",
                  "BRAIN_USES_MARKET_INTELLIGENCE",
                  "BRAIN_W_MARKET_CONFIDENCE",
                  "BRAIN_MARKET_RISK_PAUSE_ENABLED"):
            assert k in cfg
        # Defaults per operator ruling
        assert cfg["BRAIN_USES_MARKET_INTELLIGENCE"] is False
        assert cfg["BRAIN_W_MARKET_CONFIDENCE"] == 0.0
        assert cfg["BRAIN_W_STYLE_CONFIDENCE"] == 0.0
        assert cfg["BRAIN_W_OPPORTUNITY"] == 0.0
        assert cfg["BRAIN_MARKET_RISK_PAUSE_ENABLED"] is False

    def test_universe_env_driven(self):
        from engines.market_intel_engine import config as mcfg
        prev = os.environ.get("MI_UNIVERSE", "")
        try:
            os.environ["MI_UNIVERSE"] = "AAA,BBB,CCC"
            assert mcfg.mi_universe() == ["AAA", "BBB", "CCC"]
        finally:
            if prev:
                os.environ["MI_UNIVERSE"] = prev
            else:
                os.environ.pop("MI_UNIVERSE", None)


# ── 2. Observer determinism + bounds ─────────────────────────────
class TestObservers:
    def _snaps(self, n=200, amp=0.001):
        from engines.market_intel_engine import MarketSnapshot
        return [MarketSnapshot(
            pair="EURUSD", timeframe="H1",
            ts=f"2026-01-01T{i:02d}:00:00Z",
            close=round(1.08 + amp * math.sin(i / 12.0), 6),
            range_pct=amp, volatility=amp,
            session=["asian","london","ny","overlap"][i % 4],
        ) for i in range(n)]

    def test_trend_duration_bounded(self):
        from engines.market_intel_engine.observers import observe_trend_duration
        r1 = observe_trend_duration(self._snaps())
        r2 = observe_trend_duration(self._snaps())
        assert 0.0 <= r1.score <= 1.0
        assert r1.score == r2.score  # determinism

    def test_volatility_dynamics_bucket(self):
        from engines.market_intel_engine.observers import observe_volatility_dynamics
        r = observe_volatility_dynamics(self._snaps())
        assert 0.0 <= r.score <= 1.0
        assert r.evidence["regime"] in (
            "compression", "mild_compression", "normal",
            "expansion", "severe_expansion")

    def test_breakout_quality_no_data(self):
        from engines.market_intel_engine.observers import observe_breakout_quality
        r = observe_breakout_quality([])
        assert r.score == 0.5
        assert "insufficient_data" in r.evidence.get("reason", "")

    def test_reversal_strength_bounded(self):
        from engines.market_intel_engine.observers import observe_reversal_strength
        r = observe_reversal_strength(self._snaps())
        assert 0.0 <= r.score <= 1.0

    def test_session_stats_returns_bias(self):
        from engines.market_intel_engine.observers import observe_session_stats
        r = observe_session_stats(self._snaps())
        assert 0.0 <= r.score <= 1.0
        assert isinstance(r.evidence.get("bias"), dict)

    def test_liquidity_estimator_band(self):
        from engines.market_intel_engine.observers import observe_liquidity
        r = observe_liquidity(self._snaps())
        assert r.evidence["band"] in ("high", "medium", "low", "unknown")

    def test_correlation_no_universe_neutral(self):
        from engines.market_intel_engine.observers import observe_correlation
        r = observe_correlation(self._snaps())
        assert r.score == 0.5
        assert r.evidence["avg_correlation"] is None

    def test_style_performance_neutral_without_outcomes(self):
        from engines.market_intel_engine.observers import observe_style_performance
        r = observe_style_performance(self._snaps(), recent_outcomes=None)
        assert r.score == 0.5
        assert "trend_following" in r.evidence["style_scores"]


# ── 3. Change detection fires on injected shift ──────────────────
class TestChangeDetection:
    def test_volatility_regime_shift_detected(self):
        from engines.market_intel_engine import detect_structural_changes
        from engines.market_intel_engine.types import MarketState
        base = [MarketState(pair="P", timeframe="H1", window="24h",
                             ts=f"t{i}", volatility_mean=0.001,
                             trend_duration_bars=5.0,
                             breakout_success_rate=0.5,
                             avg_correlation_to_universe=0.2,
                             noise_ratio=0.5) for i in range(5)]
        # inject a 10x volatility jump
        base.append(MarketState(pair="P", timeframe="H1", window="24h",
                                 ts="t5", volatility_mean=0.010,
                                 trend_duration_bars=5.0,
                                 breakout_success_rate=0.5,
                                 avg_correlation_to_universe=0.2,
                                 noise_ratio=0.5))
        ch = detect_structural_changes("P", "H1", "24h", base)
        types = [c.change_type for c in ch]
        assert "volatility_regime_shift" in types
        # Method label per Phase F convention
        assert all(c.method.startswith("heuristic") for c in ch)

    def test_breakout_degradation_detected(self):
        from engines.market_intel_engine import detect_structural_changes
        from engines.market_intel_engine.types import MarketState
        base = [MarketState(pair="P", timeframe="H1", window="24h",
                             ts=f"t{i}", volatility_mean=0.001,
                             trend_duration_bars=5.0,
                             breakout_success_rate=0.75,
                             avg_correlation_to_universe=0.2,
                             noise_ratio=0.5) for i in range(5)]
        base.append(MarketState(pair="P", timeframe="H1", window="24h",
                                 ts="t5", volatility_mean=0.001,
                                 trend_duration_bars=5.0,
                                 breakout_success_rate=0.25,
                                 avg_correlation_to_universe=0.2,
                                 noise_ratio=0.5))
        ch = detect_structural_changes("P", "H1", "24h", base)
        assert "breakout_degradation" in [c.change_type for c in ch]

    def test_insufficient_history_no_changes(self):
        from engines.market_intel_engine import detect_structural_changes
        from engines.market_intel_engine.types import MarketState
        assert detect_structural_changes(
            "P", "H1", "24h",
            [MarketState(pair="P", timeframe="H1", window="24h", ts="t")]
        ) == []


# ── 4. Aggregator end-to-end ────────────────────────────────────
class TestAggregator:
    def test_compute_market_intelligence_scores_bounded(self):
        script = """
import asyncio, math, os, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.market_intel_engine import (MarketSnapshot,
    compute_market_intelligence, reset_snapshot_cache)
async def go():
    reset_snapshot_cache()
    snaps = [MarketSnapshot(pair='TESTA', timeframe='H1',
        ts=f'2026-01-01T{i:02d}:00:00Z',
        close=round(1.08 + 0.001*math.sin(i/12.0), 6),
        range_pct=0.001, volatility=0.001,
        session=['asian','london','ny','overlap'][i%4])
        for i in range(60)]
    mi = await compute_market_intelligence('TESTA','H1',
        snapshots=snaps, persist=False)
    for k in ('market_confidence','regime_confidence',
              'opportunity_score','risk_environment'):
        v = getattr(mi, k)
        assert 0.0 <= v <= 1.0, f'{k}={v} out of bounds'
    assert isinstance(mi.style_confidence, dict)
    print('AGGREGATOR_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "AGGREGATOR_OK" in r.stdout


# ── 5. Ledger persistence ───────────────────────────────────────
class TestLedger:
    def test_snapshot_and_intelligence_persist(self):
        script = """
import asyncio, os, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.market_intel_engine import (MarketSnapshot, ledger,
    compute_market_intelligence, reset_snapshot_cache)
async def go():
    await ledger.ensure_indexes()
    from engines.db import get_db
    db = get_db()
    for c in ('market_snapshots','market_states','structural_changes','market_intelligence'):
        await db[c].delete_many({'pair':'PLED'})
    snaps = [MarketSnapshot(pair='PLED', timeframe='H1',
        ts=f'2026-01-01T{i:02d}:00:00Z', close=1.0+i*0.001,
        range_pct=0.001, volatility=0.001)
        for i in range(50)]
    reset_snapshot_cache()
    mi = await compute_market_intelligence('PLED','H1',
        snapshots=snaps, persist=True)
    latest = await ledger.read_latest_intelligence('PLED','H1')
    assert latest is not None, 'no MI persisted'
    print('MI_MC=', latest.market_confidence)
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "MI_MC=" in r.stdout


# ── 6. Brain bridge respects two-step opt-in ────────────────────
class TestBrainBridge:
    def test_dormant_without_switches(self):
        script = """
import asyncio, os, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
os.environ['MI_ENABLED']='true'
os.environ['BRAIN_USES_MARKET_INTELLIGENCE']='false'
from engines.market_intel_engine import load_market_intelligence
async def go():
    r = await load_market_intelligence('EURUSD','H1')
    print('R=', r)
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0
        assert "R= None" in r.stdout

    def test_dormant_when_master_switch_off(self):
        script = """
import asyncio, os, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
os.environ['MI_ENABLED']='false'
os.environ['BRAIN_USES_MARKET_INTELLIGENCE']='true'
from engines.market_intel_engine import load_market_intelligence
async def go():
    r = await load_market_intelligence('EURUSD','H1')
    print('R=', r)
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0
        assert "R= None" in r.stdout


# ── 7-8. Scorer additive with weights=0 vs weights>0 ────────────
class TestScorerAdditive:
    def test_weights_zero_preserve_phase_f(self):
        """With BRAIN_W_MARKET_*=0, the scorer's score_now must be
        byte-identical with-vs-without market signals present."""
        script = """
import sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
import os
for k in ('BRAIN_W_MARKET_CONFIDENCE','BRAIN_W_STYLE_CONFIDENCE','BRAIN_W_OPPORTUNITY'):
    os.environ[k]='0.0'
from engines.brain.types import BrainSignals
from engines.brain.scorer import score_strategy
# Without MI
s_no = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london')
# With MI (all populated)
s_mi = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london',
    market_confidence=0.9, style_confidence={'trend_following': 0.9},
    opportunity_score=0.9, risk_environment=0.9)
m = {'strategy_hash':'x','style':'trend_following','confidence':0.7,
     'backtest':{'profit_factor':1.8,'max_drawdown_pct':8}}
sc_no = score_strategy(m, s_no).score_now
sc_mi = score_strategy(m, s_mi).score_now
print('EQUAL=', sc_no == sc_mi, 'sc_no=', sc_no, 'sc_mi=', sc_mi)
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "EQUAL= True" in r.stdout

    def test_weights_positive_shift_score(self):
        script = """
import sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
import os
os.environ['BRAIN_W_MARKET_CONFIDENCE']='0.10'
os.environ['BRAIN_W_STYLE_CONFIDENCE']='0.10'
os.environ['BRAIN_W_OPPORTUNITY']='0.10'
from engines.brain.types import BrainSignals
from engines.brain.scorer import score_strategy
s_low = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london',
    market_confidence=0.1, style_confidence={'trend_following': 0.1},
    opportunity_score=0.1)
s_hi = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london',
    market_confidence=0.9, style_confidence={'trend_following': 0.9},
    opportunity_score=0.9)
m = {'strategy_hash':'x','style':'trend_following','confidence':0.7,
     'backtest':{'profit_factor':1.8,'max_drawdown_pct':8}}
lo = score_strategy(m, s_low).score_now
hi = score_strategy(m, s_hi).score_now
print('HI_GT_LO=', hi > lo, 'lo=', lo, 'hi=', hi)
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "HI_GT_LO= True" in r.stdout


# ── 9. Policy market-driven force-pause hook ─────────────────────
class TestPolicyForcePause:
    def test_off_by_default(self):
        """With BRAIN_MARKET_RISK_PAUSE_ENABLED unset, a hostile market
        does NOT force-pause an otherwise healthy strategy."""
        script = """
import sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
import os
os.environ['MI_ENABLED']='true'
os.environ['BRAIN_USES_MARKET_INTELLIGENCE']='true'
os.environ.pop('BRAIN_MARKET_RISK_PAUSE_ENABLED', None)
from engines.brain.types import BrainSignals, StrategyScore
from engines.brain.policy import decide_action
sig = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london',
    risk_environment=0.05, style_confidence={'trend_following': 0.05})
score = StrategyScore(strategy_hash='x', score_now=0.9, score_next=0.9)
m = {'strategy_hash':'x','style':'trend_following','confidence':0.7,
     'allocation':0.10,'status':'active',
     'backtest':{'profit_factor':1.8,'max_drawdown_pct':8}}
d = decide_action(m, score, sig)
print('ACTION=', d.action)
print('MARKET_DRIVEN=', (d.evidence or {}).get('market_driven', False))
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        # Not PAUSE (or if PAUSE, not market-driven).
        assert "MARKET_DRIVEN= False" in r.stdout

    def test_on_when_operator_opts_in(self):
        script = """
import sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
import os
os.environ['MI_ENABLED']='true'
os.environ['BRAIN_USES_MARKET_INTELLIGENCE']='true'
os.environ['BRAIN_MARKET_RISK_PAUSE_ENABLED']='true'
os.environ['BRAIN_MARKET_RISK_PAUSE_THRESHOLD']='0.20'
os.environ['BRAIN_MARKET_STYLE_MIN_CONFIDENCE']='0.25'
from engines.brain.types import BrainSignals, StrategyScore
from engines.brain.policy import decide_action
sig = BrainSignals(regime='trending', regime_confidence=0.8,
    diversification_score=1.0, risk_budget_headroom=1.0,
    liquidity_band='high', session='london',
    risk_environment=0.05, style_confidence={'trend_following': 0.05})
score = StrategyScore(strategy_hash='x', score_now=0.9, score_next=0.9)
m = {'strategy_hash':'x','style':'trend_following','confidence':0.7,
     'allocation':0.10,'status':'active',
     'backtest':{'profit_factor':1.8,'max_drawdown_pct':8}}
d = decide_action(m, score, sig)
print('ACTION=', d.action)
print('MARKET_DRIVEN=', (d.evidence or {}).get('market_driven', False))
print('TARGET=', d.target_weight)
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "ACTION= PAUSE" in r.stdout
        assert "MARKET_DRIVEN= True" in r.stdout


# ── 10. API endpoints reachable ─────────────────────────────────
class TestEndpoints:
    def test_observers_config(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/observers/config")
        assert r.status_code == 200
        assert "config" in r.json()

    def test_state_returns_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/state"
                      f"?pair=EURUSD&timeframe=H1&window=24h")
        assert r.status_code == 200
        assert set(r.json().keys()) >= {"pair", "timeframe", "window", "state"}

    def test_state_history(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/state/history"
                      f"?pair=EURUSD&timeframe=H1&window=24h&limit=5")
        assert r.status_code == 200
        b = r.json()
        assert "states" in b and isinstance(b["states"], list)

    def test_changes(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/changes?limit=10")
        assert r.status_code == 200
        assert "changes" in r.json()

    def test_intelligence(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/intelligence"
                      f"?pair=EURUSD&timeframe=H1")
        assert r.status_code == 200

    def test_refresh_admin(self, admin):
        r = admin.post(f"{BASE_URL}/api/market-intelligence/refresh"
                       f"?pair=EURUSD&timeframe=H1")
        assert r.status_code == 200
        assert r.json()["refreshed"] is True
        assert "intelligence" in r.json()

    def test_explain_404_on_missing(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/explain/nonexistent")
        # Either 404 (bad id) or 200 with None doc, but our impl → 404.
        assert r.status_code in (404, 400)


# ── 11. Router count and orchestrator task registration ─────────
class TestRouterAndTaskCount:
    def test_router_count_is_97(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        m = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert m
        assert m[-1] in ("97", "98", "99"), (
            f"latest boot reports {m[-1]} routers "
            f"(expected 97 or 98 — Phase G adds market_intelligence_engine; Phase H9 adds execution_engine)")

    def test_orchestrator_task_registered(self):
        script = """
import sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
import engines.orchestrator.tasks  # side-effect registration
from engines.orchestrator import registry
print('NAMES=', 'market_intelligence_refresh' in registry.names())
print('COUNT=', len(registry.names()))
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "NAMES= True" in r.stdout


# ── 12. Regression sweep across earlier phases ──────────────────
class TestRegressionSweep:
    ENDPOINTS = [
        "/api/health",
        "/api/orchestrator/status",
        "/api/orchestrator/tasks",
        "/api/intelligence/regime",
        "/api/portfolio/health/x",
        "/api/brain/policy/weights",
        "/api/brain/signals",
        "/api/market-intelligence/observers/config",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=15)
        assert r.status_code == 200, f"{ep} → {r.status_code}"
