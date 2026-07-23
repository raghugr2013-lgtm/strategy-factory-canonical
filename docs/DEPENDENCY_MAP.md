# Strategy Factory — Dependency Map

**Companion to:** `docs/CAPABILITY_INVENTORY.md`, `docs/GAP_ANALYSIS.md`.
**Purpose:** State — with zero ambiguity — which existing subsystems
power each future module and which modules can be composed entirely
from existing capabilities.

Labels reference the sections and IDs in the Capability Inventory
(A1..M7). Read the tables from left to right: "future module" ← "power
source". If a row is missing an ID, that module cannot be built until
the corresponding capability is added.

---

## 1 · Dependency lattice (top view)

```
                    ┌───────────────────────────────────────────┐
                    │       Historical Knowledge Base           │
                    │  A7 · B1 · B2 · B3 · B4 · B5 · B6 · B8    │
                    └────────────────┬──────────────────────────┘
                                     │
                        ┌────────────┴─────────────┐
                        ▼                          ▼
              ┌───────────────────┐      ┌──────────────────────┐
              │ Strategy Explorer │      │  Strategy Registry   │
              │ M4 · M1 · K10     │      │ A6 · B2 · B3 · K1/K2 │
              └─────────┬─────────┘      │  · G6 (challenge)    │
                        │                └───────────┬──────────┘
                        ▼                            ▼
                   ┌────────────────────────────────────┐
                   │   Autonomous Research Factory      │
                   │  C1..C6 · D1..D9 · E1..E8 · F* · I*│
                   │  · K3..K8 · L1..L7 · J1..J6 (via  │
                   │    C7 activation)                  │
                   └────────────────────┬───────────────┘
                                        ▼
                       ┌────────────────────────────┐
                       │      Master Bot             │
                       │ G4 · I1 · G1..G3 · C4      │
                       └────────────┬───────────────┘
                                    ▼
                       ┌────────────────────────────┐
                       │      Paper Trading         │
                       │ H1..H7 · G4 · I2 · I3 · K8 │
                       └────────────┬───────────────┘
                                    ▼
                       ┌────────────────────────────┐
                       │      Export Engine         │
                       │ D3 · G4 · (MT4/MT5=Build)  │
                       └────────────┬───────────────┘
                                    ▼
                       ┌────────────────────────────┐
                       │     Human Workspace        │
                       │ M1..M7 · A1..A5 · K10      │
                       │ (Timeline swap post-freeze)│
                       └────────────────────────────┘
```

---

## 2 · Module-by-module dependency table

Column meanings:
- **Powered by (Reuse):** existing subsystems the module consumes directly.
- **Composed from (existing):** modules that assemble multiple existing capabilities without new engines.
- **Requires (Extend/Refine):** the small deltas from `docs/GAP_ANALYSIS.md`.
- **Requires (Build New):** truly new engines. Empty means none.

### 2.1 · Historical Knowledge Base

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | A7 knowledge router · B1 KnowledgeRepository · B2 StrategyRepository · B3 canonical hash · B4 evaluation · B6 champions/families/statistics · A9 DB bootstrap · L6 db indexes |
| Composed from (existing) | Yes — end-to-end read path already live in production |
| Requires (Extend) | B5 embedding backend · B7 KB migration spec execution · B8 UKIE domain / connector wiring |
| Requires (Build New) | — |

### 2.2 · Autonomous Research Factory

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | Full scheduler tier C1..C6 · full strategy generation stack D1..D9 · full validation stack E1..E8 · full data/BI5 F1..F10 · full intelligence stack I1..I7 · governance/safety K1..K10 · infra primitives L1..L7 · AI workforce I6 · VIE providers A8 |
| Composed from (existing) | Yes at the engine level. The 17 orchestrator tasks (C4) already cover every autonomous verb: generate → backtest → mutate → optimize → validate → rank → promote → retire → learn → refresh MI / knowledge / master-bot → attribute → self-rebuild |
| Requires (Refine) | A10 → C7: swap Phase-0 runner stub for recovered `legacy.factory_runner` |
| Requires (Extend) | J1..J6 Factory Supervisor activation once C7 is wired |
| Requires (Build New) | — |

### 2.3 · Strategy Explorer

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | A6 strategies CRUD · B2 StrategyRepository · B6 champions/families/statistics · legacy `strategy_memory` router (`/strategies/explorer`) · M4 Strategy Pipeline surface · M1 Strategy Passport · K10 research lineage · G6 challenge matching |
| Composed from (existing) | Yes — backend already serves every needed endpoint |
| Requires (Extend) | Frontend action for re-insert-as-cold (calls `POST /api/strategies`); Timeline shim → real endpoint swap when freeze lifts |
| Requires (Build New) | — |

### 2.4 · Strategy Registry

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | A6 strategies · B3 canonical hash · `engines/strategy_lifecycle.py` · `engines/strategy_library.py` · K1 activation journal · K2 audit log · K10 research lineage · Library API (via `dashboard_route` side-effect) · M4/M1 surfaces |
| Composed from (existing) | Yes — every registry primitive exists |
| Requires (Extend) | — |
| Requires (Build New) | — |

### 2.5 · Master Bot

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | G4 (engine · definition · diff · export · pack · deployment · ranker) · I1 intelligence master-bot builder · G1..G3 portfolio · C4 `master_bot_bundle_refresh` orchestrator task · A6 strategies CRUD · G5 prop-firm · G6 challenge |
| Composed from (existing) | Yes — end-to-end ready |
| Requires (Extend) | — |
| Requires (Build New) | — |

### 2.6 · Paper Trading

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | H1 paper engine · H2 v1.2 execution (journal + replay + quality + attribution + risk) · H4 ledger backends · H5 slippage + realism · H6 live tracking · H7 trade runner · G4 master bot bundles · I2 brain · I3 market intelligence · K8 alerts · C4 `broker_health_check` + `execution_attribution` tasks |
| Composed from (existing) | Yes — paper path is live; live-broker path is one adapter away |
| Requires (Extend) | H3 cTrader adapter (or another live broker) |
| Requires (Build New) | — |

### 2.7 · Export Engine

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | D2 Strategy IR · D3 cBot pipeline (ir_transpiler + ir_templates + parity + auto-fix + log diagnostic) · G4 master-bot pack/diff/export · `/api/cbot/*` and `/api/master-bot/export` routes |
| Composed from (existing) | Yes — cTrader C# emit is production |
| Requires (Extend) | — |
| Requires (Build New) | MT4/MT5 emitters, only when business demand appears — architecturally slot alongside `cbot_engine/ir_transpiler.py` |

### 2.8 · Human Workspace

| Aspect | Bindings |
|--------|----------|
| Powered by (Reuse) | M7 CommandShell / TopTabBar / LifecycleRail / StatusRail / AuthGate / CmdKPalette / FactoryWalkthrough · A1..A5 auth+admin+dashboard+research+health · M1 Strategy Passport · M2 Approvals + Timeline shim · M3..M6 Lab/Pipeline/Coverage/Market Data/Datasets/Optimization/Validation surfaces · K10 research lineage · J4 notification center (post-supervisor activation) |
| Composed from (existing) | Yes — shell + surfaces are live |
| Requires (Extend) | Command Palette · Strategy Pipeline entry · Approvals inbox on Command surface · Timeline shim → real endpoint swap post-freeze · Progressive personalization modes |
| Requires (Build New) | — |

---

## 3 · Cross-module capability sharing

Which existing subsystem powers multiple future modules? (High
sharing = high reuse leverage.)

| Subsystem | Powers |
|-----------|--------|
| A6 Strategies CRUD | Explorer · Registry · Master Bot · Autonomous Factory · Human Workspace |
| B1/B2 Repositories | KB · Explorer · Registry · Autonomous Factory |
| B3 Canonical hash | KB · Registry · Autonomous Factory (dedup) |
| C1..C6 Scheduler tier | Autonomous Factory · Paper Trading · Master Bot · KB refresh |
| D2 Strategy IR | Autonomous Factory · Master Bot · Export Engine · Paper Trading (replay) |
| D3 cBot pipeline | Master Bot · Export Engine · Paper Trading (broker parity checks) |
| E1..E8 Validation stack | Autonomous Factory · Registry (lifecycle promotion) · Master Bot |
| F1..F10 Data engine | Every downstream module (universal data supply) |
| G4 Master Bot engine | Master Bot · Paper Trading · Export Engine · Autonomous Factory |
| H2 Execution engine v1.2 | Paper Trading · Master Bot deployment · Autonomous Factory (attribution task) |
| I1..I7 Intelligence stack | Autonomous Factory · Master Bot · Paper Trading · Explorer (regime tags) |
| J1..J6 Factory Supervisor (once activated) | Autonomous Factory (fleet) · Human Workspace (notification center · copilot) |
| K1..K10 Governance | Every module — audit + safety layer |
| L1..L7 Infra primitives | Every module — CPU/IO pools, health, LLM, indexes |
| M2 Approvals + Timeline | Explorer · Human Workspace · Autonomous Factory (approval gates) |

Every future module composes from at least 6 existing subsystems. No
module needs a bespoke engine except the optional MT4/MT5 emitter.

---

## 4 · Modules composable ENTIRELY from existing capabilities

These modules have **zero Build-New** requirements — they can ship
today by wiring what already exists:

- **Historical Knowledge Base** (needs 3 Extends but the read path is
  already live).
- **Strategy Registry** — zero deltas.
- **Master Bot** — zero deltas.
- **Export Engine** (for cTrader C# — zero deltas; MT4/MT5 optional).
- **Strategy Explorer** — one frontend action + one shim swap.
- **Human Workspace** — three frontend extensions.

The only modules with a non-trivial delta are:

- **Autonomous Research Factory** — one Refine (runner) + one Extend
  (Supervisor activation).
- **Paper Trading** — one Extend (live broker adapter).

**Nothing** in the long-term vision requires a Replace or a
greenfield backend build.

---

## 5 · Bootstrap order (dependency-safe)

Sequence in which each downstream module becomes safe to ship, given
its dependencies:

1. **Historical KB** — already live in production; add embedding
   backend + finish KB migration spec.
2. **Strategy Registry** — already live; no dependencies remain.
3. **Strategy Explorer** — add one frontend action; depends on 1 + 2.
4. **Autonomous Research Factory** — refine runner + activate
   supervisor; depends on 1 + 2 + full engine stack (already there).
5. **Master Bot** — already live; refreshes benefit from step 4.
6. **Paper Trading** — already live for paper; add live broker
   adapter; depends on 5.
7. **Export Engine** — already live for cTrader; MT4/MT5 optional.
8. **Human Workspace** — progressive frontend extensions; depends on
   1 + 3 + 4 (approvals) + 5 + 6.

The parallel path is clear: Step 1's three Extends can proceed
alongside Step 4's two changes; every other module only needs frontend
work once the two Extends land.
