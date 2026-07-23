# DSR ARCHITECTURAL BLUEPRINT
**Title:** Dynamic Symbol Registry — Activation Plan (DSR-1 → DSR-3)
**Purpose:** Enable the operator to onboard new tradable symbols (Forex, Metals, Crypto, Indices, CFDs, Futures) without code changes. New symbols flow automatically into Market Data, BI5, Auto Factory, Validation, Explorer, Portfolio, and Marketplace.
**Discipline:** Architectural spec only. No code changes in this turn. Additive only — sealed surfaces (G2 scheduler, IR transpiler, lifecycle engine, governance_universe) are NOT modified.
**Companion docs:** BI5_R1_ARCHITECTURAL_BLUEPRINT.md, ASF_CANONICAL_IDENTITY_MODEL.md, VALIDATED_ARCHETYPE_INVENTORY.md

---

## 0. CURRENT-STATE AUDIT (confirmed in pod)

| Component | Status | Location |
|---|---|---|
| `SYMBOL_CONFIG` (source of truth, hard-coded) | 7 symbols hard-coded | `/app/backend/config/symbols.py` |
| `INSTRUMENT_MAP` (Dukascopy mapping, hard-coded) | 3 symbols | `/app/backend/data_engine/dukascopy_downloader.py` |
| Auto-data-maintainer scheduler consumer | Iterates `SYMBOL_CONFIG` directly | `data_engine/auto_data_maintainer.py:256,263,271` |
| `governance_universe.pairs` | Separate hard-coded `DEFAULT_PAIRS` | `engines/governance_universe.py` |
| Mongo `symbol_registry` collection | **Does NOT exist** | — |
| Symbol CRUD API | **Does NOT exist** | — |
| Symbol Registry UI | **Does NOT exist** | — |
| Feature flag for activation | **Not yet defined** | proposed: `DSR_ENABLED` |

> **Audit verdict:** the previous "registry engine at ~95 % complete" assessment is *not visible on this 1-vCPU pod*. The blueprint below assumes a *greenfield* implementation. If a registry already exists on another branch/pod, this spec must be reconciled with it before merge.

---

## 1. DESIGN GOALS

1. **Single source of truth** for tradable symbols: a Mongo collection (`symbol_registry`) replaces the hard-coded `SYMBOL_CONFIG` dict.
2. **Operator-controlled** lifecycle: onboard / pause / retire symbols via UI, no deploy.
3. **Strict subordination** to `governance_universe`: a symbol's presence in `symbol_registry` is necessary but not sufficient — `governance_universe.pairs` remains the authoritative *allowed* filter.
4. **Backwards-compatible**: behaviour with feature flag OFF is byte-identical to today (continues reading `SYMBOL_CONFIG`).
5. **Shadow-mode safety**: DSR-3 enables an *audit cycle* before any new symbol enters live autonomous loops.
6. **Anti-drift**: scheduler dispatch, governance filtering, lifecycle promotion remain sealed authorities. DSR provides *catalogue*, never *policy*.

---

## 2. DATA MODEL — `symbol_registry`

```jsonc
{
  "_id": ObjectId,
  "symbol": "EURUSD",                     // canonical, uppercase, unique index
  "asset_class": "forex",                 // forex | metal | crypto | index | cfd | future
  "market_type": "forex",                 // matches SYMBOL_CONFIG.market_type (forex|crypto)
  "timezone": "UTC",
  "provider": {
    "primary":   "dukascopy",             // dukascopy | manual_csv | api_x | ...
    "fallback":  null,
    "instrument_code": "INSTRUMENT_FX_MAJORS_EUR_USD"   // provider-specific
  },
  "tick_size":    0.00001,
  "pip_size":     0.0001,
  "contract_unit": 100000,                 // forex-style; for crypto = 1
  "session": {                             // optional; defaults derived from market_type
    "open_utc":  "22:00",                  // forex: Sun 22:00 → Fri 22:00
    "close_utc": "22:00",
    "weekdays_open": [0,1,2,3,4,6]         // crypto = [0..6]
  },
  "status": "active",                     // active | paused | retired | onboarding | shadow
  "onboarded_at":  ISODate,
  "activated_at":  ISODate,
  "paused_at":     null,
  "retired_at":    null,
  "operator":      "admin@local.test",
  "notes":         "",
  "shadow_audit": {                        // populated by DSR-3
    "completed":   false,
    "started_at":  ISODate,
    "completed_at": null,
    "bid_coverage_ok":  null,
    "bi5_coverage_ok":  null,
    "calendar_validated": null,
    "report_id":   null
  },
  "subsystem_flags": {                     // which subsystems may consume this symbol
    "market_data_ingest":  true,
    "bi5_ingest":          true,
    "auto_factory":        false,          // off until shadow audit passes
    "validation":          false,
    "explorer":            false,
    "portfolio":           false,
    "marketplace":         false
  },
  "audit_log": [
    { "ts": ISODate, "actor": "admin@local.test", "action": "onboard",
      "diff": { "status": [null, "onboarding"] } }
  ],
  "version": 1                             // optimistic concurrency token
}
```

**Indexes:**
- `{ symbol: 1 }` UNIQUE
- `{ status: 1, asset_class: 1 }` for filtered listings
- `{ "subsystem_flags.market_data_ingest": 1 }` for scheduler hot-paths

---

## 3. PHASE DSR-1 — Operator Symbol Registry UI

### 3.1 Scope
A new admin-only React panel `SymbolRegistryPanel.jsx` that lists registered symbols and allows full CRUD. **No scheduler change in this phase.** The hard-coded `SYMBOL_CONFIG` is still the runtime source of truth — DSR-1 ships the catalogue alongside it.

### 3.2 Backend additions (all additive)

| Endpoint | Method | Auth | Behaviour |
|---|---|---|---|
| `/api/symbols/registry` | GET | admin | List all symbols with filters (`status`, `asset_class`) |
| `/api/symbols/registry/{symbol}` | GET | admin | Single symbol record |
| `/api/symbols/registry` | POST | admin | Create with `status='onboarding'`. Validates `asset_class`, `market_type`, `provider.instrument_code` against an allow-list. Emits `audit_log` entry. |
| `/api/symbols/registry/{symbol}` | PATCH | admin | Partial update with optimistic concurrency (`version` must match). Append to `audit_log`. Status transitions guarded by a state machine (see §3.4). |
| `/api/symbols/registry/{symbol}` | DELETE | admin | Soft delete → status=`retired`, `retired_at` set. Cannot delete if any subsystem still references this symbol. |
| `/api/symbols/registry/seed` | POST | admin | One-time idempotent seed from `SYMBOL_CONFIG` into the new collection (`status='active'`, `subsystem_flags.*=true` for the legacy 7). |
| `/api/symbols/registry/health` | GET | admin | Aggregated health: per-symbol BID + BI5 coverage status (sourced from `data_maintenance_status` + `bi5_ingest_log`) |

### 3.3 Frontend additions
- `src/components/SymbolRegistryPanel.jsx` — DataTable with rows: symbol, asset_class, status, providers, last activity, action menu.
- Add/Edit modal with field validation matching the data model.
- Status filter chips. Health column with green/amber/red indicator linking to BI5 Health panel (BI5 R1 B-9).
- Wire into existing admin nav next to `UniverseGovernancePanel`.
- `data-testid` on every interactive control (e.g., `symbol-registry-add-btn`, `symbol-registry-row-${symbol}`).

### 3.4 Status state machine
```
[NEW] --create-->  onboarding
onboarding --shadow_audit_pass--> shadow
shadow --activate-->            active
active --pause-->               paused
paused --resume-->              active
active|paused --retire-->       retired
retired (terminal; cannot resume — must re-onboard with new symbol record)
```
Transitions enforced server-side. `subsystem_flags` are mass-set per status:
- `onboarding` → all subsystem_flags = false
- `shadow` → only `market_data_ingest` and `bi5_ingest` may be true
- `active` → operator-controlled per flag
- `paused` → all false (suspends ingestion + downstream)
- `retired` → all false, no further mutations allowed

### 3.5 Acceptance criteria (DSR-1)
- Operator can add a new symbol via UI (e.g., USDCHF) and see it in the registry.
- Adding a symbol does **not** change scheduler behaviour (the symbol stays dormant).
- The seed endpoint produces 7 records matching the current `SYMBOL_CONFIG`.
- All edits are audit-logged. Concurrency conflicts return 409 with current `version`.
- Feature flag default: `DSR_ENABLED=False`. With flag off, the panel is hidden but the API endpoints still respond (data persists silently).

---

## 4. PHASE DSR-2 — Scheduler Consumes Registry

### 4.1 Scope
Replace the `for symbol in SYMBOL_CONFIG` loops in `auto_data_maintainer.py` (and any other scheduler consumer) with a registry-backed accessor. **`SYMBOL_CONFIG` is retained as a compatibility cache; the registry is the new source of truth when `DSR_ENABLED=True`.**

### 4.2 New accessor (additive, single module)

`/app/backend/engines/symbol_registry.py` (NEW file):
- `async def active_symbols(subsystem: str) -> list[dict]` — returns registry rows where `status in ("active","shadow")` AND `subsystem_flags[subsystem]=True`.
- `async def is_eligible(symbol: str, subsystem: str) -> bool` — fast accessor for governance checks.
- `async def symbol_config_for(symbol: str) -> dict` — registry row reshaped to match the legacy `SYMBOL_CONFIG` schema for drop-in use.
- Reads with TTL cache (60 s) to avoid hammering Mongo during scheduler ticks.

### 4.3 Scheduler integration

In `auto_data_maintainer.py`:
```python
# OLD (hard-coded)
for symbol in SYMBOL_CONFIG:
    await _update_bid_symbol(symbol)

# NEW (registry-backed, flag-guarded)
if DSR_ENABLED:
    rows = await symbol_registry.active_symbols("market_data_ingest")
    symbols = [r["symbol"] for r in rows]
else:
    symbols = list(SYMBOL_CONFIG)
for symbol in symbols:
    await _update_bid_symbol(symbol)
```

Same pattern for `_bi5_track_job()` consuming `subsystem='bi5_ingest'`.

### 4.4 Governance interlock (CRITICAL)
The scheduler's eligible-symbol set is the **intersection** of:
1. `symbol_registry.active_symbols(subsystem)` — the catalogue
2. `governance_universe.pairs` — the allowed policy (sealed)

A symbol may be in the registry as `active` but excluded from autonomous loops because it is not in `governance_universe.pairs`. **The governance filter remains the final authority** — DSR never overrides it.

### 4.5 Non-scheduler consumers (sequential refactor, additive)

| Consumer | Current source | DSR-2 source |
|---|---|---|
| `dukascopy_downloader.INSTRUMENT_MAP` | Hard-coded 3 symbols | Reads `provider.instrument_code` from registry row |
| `data_engine/data_maintenance.DEFAULT_PAIRS` | Hard-coded 4 symbols | Falls back to `symbol_registry.active_symbols("market_data_ingest")` |
| `governance_universe` defaults | `DEFAULT_PAIRS` constant | Optional bootstrap from registry on first init only |
| Auto Factory pair allow-list | (via governance_universe) | Unchanged — governance still authoritative |
| Validation engine pair list | (via input data) | Unchanged |
| Explorer pair list | (via governance_universe / market_data) | Unchanged |

### 4.6 Acceptance criteria (DSR-2)
- With `DSR_ENABLED=True`, adding USDCHF to the registry with `status='active'`, `subsystem_flags.market_data_ingest=true`, and adding USDCHF to `governance_universe.pairs` causes the next BID scheduler tick to include USDCHF.
- With `DSR_ENABLED=False`, scheduler behaviour is byte-identical to pre-DSR.
- Disabling `subsystem_flags.market_data_ingest` for a symbol stops ingestion within one scheduler tick.
- Symbols in `paused` or `retired` status are excluded immediately.
- No 409 conflicts (caches honor optimistic concurrency on re-fetch).

---

## 5. PHASE DSR-3 — Dynamic Universe + Shadow Audit

### 5.1 Scope
Activate the *full* dynamic-universe vision: any operator-added symbol flows automatically through Market Data → BI5 → Auto Factory → Validation → Explorer → Portfolio → Marketplace **only after passing a shadow audit**.

### 5.2 Shadow audit (new background job)
A new scheduler job `dsr_shadow_audit` runs every 30 minutes and processes registry rows with `status='shadow'`. For each:

| Check | Pass criterion |
|---|---|
| BID coverage | At least 7 days of `bid_1m` data ingested in `market_data` |
| BI5 coverage | At least 7 days of `bi5` rows OR explicit operator override |
| Calendar validation | `market_calendar.is_trading_time` produces sane density (gaps < 1 % during sessions) |
| Provider health | Last 3 incremental updates succeeded |
| Governance presence | `symbol ∈ governance_universe.pairs` (else: blocked, operator must add) |
| Backtest dry-run | Run a single-pass validation_engine on a tiny synthetic strategy; require non-error termination |

When all checks pass, the audit writes to `shadow_audit.completed=true` and emits an alert to the admin via `alert_engine`. **The operator must explicitly transition `shadow → active`** via the UI; no auto-promotion. Per anti-drift policy, autonomous loops never self-promote new symbols.

### 5.3 Subsystem propagation matrix

| Subsystem | Reads from | Trigger to onboard a new symbol |
|---|---|---|
| Market Data ingest | `subsystem_flags.market_data_ingest` | DSR-2 scheduler consumes; auto |
| BI5 ingest | `subsystem_flags.bi5_ingest` | DSR-2 scheduler consumes; auto |
| Auto Factory | `subsystem_flags.auto_factory` AND `symbol ∈ governance_universe.pairs` | Operator toggle in UI after shadow audit |
| Validation | `subsystem_flags.validation` | Operator toggle |
| Explorer | `subsystem_flags.explorer` | Operator toggle |
| Portfolio | `subsystem_flags.portfolio` | Operator toggle |
| Marketplace | `subsystem_flags.marketplace` | Operator toggle |

Each toggle is an additive flag — sealed governance / orchestration logic is unchanged. The flags are read at hot-path time by each subsystem's registry accessor.

### 5.4 Shadow Audit Report
Generated per-symbol after each shadow run:
- Stored in collection `dsr_shadow_audit_reports`
- Surface in UI under the symbol's detail drawer
- Includes: coverage windows, gap counts, calendar density, sample backtest output, drift flags

### 5.5 Acceptance criteria (DSR-3)
- Operator can onboard a new symbol (e.g., USOIL) end-to-end through the UI:
  - Add via DSR-1 panel
  - Scheduler begins ingesting via DSR-2 (after toggling `market_data_ingest` + adding to `governance_universe.pairs`)
  - Within ~7 days, shadow audit auto-completes with a report
  - Operator reviews report, transitions to `active`, toggles per-subsystem flags
  - Symbol appears in Explorer / Auto Factory / Validation seamlessly
- No code changes required to add a new symbol post-DSR-3.

---

## 6. INTEGRATION WITH VALIDATED ARCHETYPE MODEL

The recently-discovered systemic label-drift (VALIDATED_ARCHETYPE_INVENTORY) has direct implications for DSR — symbols onboarded post-DSR-3 will be subject to the same archetype-drift, so the registry must support **archetype-aware reporting**:

- The shadow audit's backtest dry-run records the resulting `validated_archetype` per (symbol, base_strategy_seed).
- The symbol detail UI surfaces, per active archetype: families currently active, edge-id memberships, contribution to portfolios.
- Marketplace listings inherited from a symbol carry the `canonical_family_key` (Layer 2) — symbols don't list strategies directly; families do.

This means **DSR is a catalogue of symbols, not a catalogue of strategies**. Strategy identity is governed by ASF_CANONICAL_IDENTITY_MODEL §3.

---

## 7. ROLLBACK / SAFETY

- `DSR_ENABLED=False` cleanly reverts every scheduler consumer to `SYMBOL_CONFIG` reads.
- Registry rows persist with flag off (silent dormancy).
- Status transitions are reversible (except `retired`).
- No destructive operations on `governance_universe` or `strategy_library`.
- Shadow audit failures do not affect existing active symbols.

---

## 8. ORDER OF OPERATIONS (implementation phase, post-blueprint approval)

1. Create `symbol_registry` collection with indexes
2. Create accessor module `engines/symbol_registry.py`
3. Build CRUD API + audit logging
4. Build UI panel + wire nav
5. Add seed endpoint, run seed (idempotent)
6. **DSR-1 ACCEPTANCE CHECK** — UI works, no scheduler change observable
7. Add `DSR_ENABLED` flag (default False) to `.env`
8. Refactor `auto_data_maintainer` to read accessor when flag on
9. Refactor `dukascopy_downloader.INSTRUMENT_MAP` to accessor (registry-backed)
10. Add governance interlock (intersection logic)
11. **DSR-2 ACCEPTANCE CHECK** — flip flag, observe seeded behaviour identical; add 1 symbol via UI; observe ingestion within one tick
12. Implement `dsr_shadow_audit` job + report collection + UI surface
13. Wire per-subsystem `subsystem_flags` reads (Auto Factory, Validation, Explorer, Portfolio, Marketplace)
14. **DSR-3 ACCEPTANCE CHECK** — onboard a brand-new symbol end-to-end without code changes

Each phase is independently shippable, additive, and reversible.

---

## 9. AUDIT BOUNDARY

This blueprint is a design document. No code modifications, no DB collection creation, no API changes have been executed by this audit pass. Implementation begins only after operator approval of this blueprint.
