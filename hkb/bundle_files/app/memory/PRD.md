# AI Strategy Factory v10 — Product Requirements Doc (Convergence State)

**Last updated:** 2026-05-16 (Phase 30.2 seal)
**State:** Operational governance · ecosystem maturation phase · architecture phase closed

## Architecture eras (in order)

| Phase | What it sealed |
|---|---|
| 26.5 / G6 | 8-stage lifecycle hysteresis |
| 27.3/27.4 | BI5 realism gate (pf_ratio ≥ 0.75) |
| 28-A → 28-C | Strategy IR + interpreter + transpiler (sealed) |
| G1 lineage / G2 scheduler authority | Single APScheduler, lineage |
| 29.0 | Regime advisory evidence |
| 30.0 | Survivor Governance Convergence |
| 30.1 | Convergence Integration (Δ1–Δ5: strategy-truth · events · RULE 12 dormant · universe marker · GovernanceCard) |
| **30.2 (current seal)** | **Universe Governance Panel** — operator-decreed ecosystem boundary filtering A1–A6 |

## Phase 30.2 deltas (this session)
- New Mongo collection `governance_universe` (seeded: EURUSD/XAUUSD × H1/H4 × 3 styles).
- 3 new endpoints under `/api/governance/universe[/preview]`.
- 6 additive filter wirings (A1: multi_cycle_runner · A2/A3: ai_orchestrator · A4: env_priority · A5: gem_factory · A6: auto_factory_phase55).
- New React component `UniverseGovernancePanel.jsx` mounted between GovernanceCard and StrategyIngestionCard.
- Trust gate: `tests/test_universe_governance.py` — 25 cases across pure helpers / persistence / filter wiring / API surface / bypass invariants.

## Operator-decreed constants (codified, anti-drift enforced)

```
# Phase 30.0
SURVIVOR_TOP_N                     = 100
SURVIVOR_ELIGIBLE_STAGES           = (elite, portfolio_worthy, deployment_ready)
SURVIVOR_AUTO_REPLACE_ENABLED      = False
REPLACEMENT_MIN_DEPLOY_SCORE_DELTA = 5.0
REPLACEMENT_COOLDOWN_DAYS          = 7
DEFAULT_VIEW_MODE (Explorer)       = "evidence"

# Phase 30.1
AUTONOMOUS_DISCOVERY_ENABLED       = False
AUTONOMOUS_DISCOVERY_MIN_HEADROOM  = 10
INSTITUTIONAL_EVENT_TYPES          = 7-element closed taxonomy

# Phase 30.2
governance_universe (seed)         = EURUSD/XAUUSD × H1/H4 × 3 styles
  exploration_floor_pct            = 5.0
  max_active_cells                 = 8
  breadth_vs_depth                 = 0.5
  AUDIT_LOG_CAP                    = 50
auto_factory.respect_universe      = True (default; filter through universe)
```

## Trust gate scoreboard (cumulative)

```
Phase 26.5 lifecycle base          : 27 / 27 PASS
Phase 28 transpiler                : 40 / 40 PASS
Phase 28 backtest correctness      :  9 /  9 PASS
Phase 28 composer-chain            : 14 / 14 PASS
Phase 28 composer mutation         : 22 / 22 PASS
Phase 28 IR telemetry (async)      : 27 / 27 PASS
Phase 29 regime layer + OOS + WF   : 45 / 45 PASS
Phase 30 survivor governance       : 24 / 24 PASS
Phase 30.1 convergence integration : 18 / 18 PASS
Phase 30.2 universe governance     : 25 / 25 PASS
Phase 27.2 ai_orchestrator         : 10 / 10 PASS
Alert engine unit                  :  7 /  7 PASS
                                   ──────────────
                                    266 / 266 PASS
```

## Current operational state

```
SCHEDULERS                : enabled=false (operator decree — observation window)
DATABASE                  : 0 strategy_library, 0 strategy_lifecycle
MARKET DATA               : EURUSD/GBPUSD/USDJPY/XAUUSD × M15/H1/H4 — ~3y coverage
EVIDENTIAL SURVIVORS      : 0
DEPLOYMENT-READY          : 0
CTRADER EXPORTS           : 0 (gated to deployment_ready)
AUTONOMOUS DISCOVERY      : DORMANT
AUTO REPLACE              : DISABLED
GOVERNANCE CARD           : MOUNTED on main Dashboard (read-only)
UNIVERSE GOVERNANCE PANEL : MOUNTED on main Dashboard (read/write admin)
ALLOWED UNIVERSE          : EURUSD/XAUUSD × H1/H4 × 3 styles (initial decree)
```

## Anti-drift directive (operator-mandated)

The architecture phase remains **closed**. Phase 30.2 was strictly an
ECOSYSTEM-BOUNDARY pass, not expansion. No new schedulers, no new ranking systems,
no new lifecycle stages, no sealed-surface drift.

## Backlog (P0/P1/P2)

| Pri | Item | Owner-action required? |
|---|---|---|
| P0 | Trigger first evidential ingestion / auto-mutation run | Operator |
| P0 | Validate end-to-end produces first lifecycle progression | System (autonomous once schedulers enabled) |
| P1 | Phase 30.3 — flip orchestrator scheduler to `running` after observation | Operator decree |
| P1 | Phase 30.4 — flip `auto_replace_enabled=True` after observation | Operator decree |
| P1 | Phase 30.5 — flip `AUTONOMOUS_DISCOVERY_ENABLED=True` after observation | Operator decree |
| P1 | Phase 29.1 — flip `REGIME_FRAGILE` from taxonomy-only to emitted | Operator decree |
| P2 | Add universe-state pill on GovernanceCard ("2 pairs · 2 TFs · 3 styles") | Cosmetic addition |
| P2 | Phase 31 — Portfolio Intelligence (correlation gates, marginal Sharpe) | Future |
| P2 | Phase 32 — Causal Edge Attribution | Future |
| P2 | Phase 33 — Anti-correlation Mutation Pressure | Future |
| P2 | Phase 34 — Live Shadow Execution | Future |
| P2 | Phase 35 — Online Demotion Gates | Future |

## Key files reference

```
backend/engines/governance_universe.py     — Phase 30.2 ecosystem boundary helper
backend/engines/survivor_registry.py        — Phase 30, top-N universe aggregator
backend/engines/replacement_engine.py       — Phase 30, advisory + Δ2 event emit
backend/api/governance.py                   — Phase 30/30.1/30.2 endpoints
backend/api/deployment.py                   — Phase 30, deployment registry
backend/engines/regime_performance.py       — Phase 29, regime evidence aggregator
backend/api/regime.py                       — Phase 29, 3 endpoints
backend/engines/strategy_lifecycle.py       — Phase 26.5 + 29 flag + 30.1 Δ2/Δ4
backend/engines/ai_orchestrator.py          — Phase 27.2 + 30.1 Δ3 RULE 12 + 30.2 A2/A3 filter
backend/engines/multi_cycle_runner.py       — Phase 30.2 A1 filter
backend/engines/env_priority.py             — Phase 30.2 A4 filter
backend/engines/gem_factory_engine.py       — Phase 30.2 A5 filter
backend/engines/auto_factory_phase55.py     — Phase 30.2 A6 filter
backend/engines/alert_engine.py             — Phase 5.5 + 30.1 Δ2 emit_event
backend/api/strategy_memory.py              — Phase 30 cBot gate + 30.1 Δ2 emit
backend/cbot_engine/ir_transpiler.py        — Phase 28-C sealed
backend/engines/ir_interpreter.py           — Phase 28 sealed
backend/engines/strategy_ir.py              — Phase 28 sealed
backend/engines/bi5_realism.py              — Phase 27.3/27.4 sealed
backend/engines/orchestrator_scheduler.py   — G2 single APScheduler authority
backend/engines/research_lineage.py         — G1 lineage tracking
frontend/src/components/GovernanceCard.jsx           — Phase 30.1 Δ5 widget
frontend/src/components/UniverseGovernancePanel.jsx  — Phase 30.2 boundary panel
frontend/src/App.js                                  — mount points (Dashboard tab)
```

