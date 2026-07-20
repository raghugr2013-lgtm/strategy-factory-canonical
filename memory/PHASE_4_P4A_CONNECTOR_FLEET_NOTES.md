# Phase 4 Stage 4 — P4A Connector Fleet: Implementation Notes

> **Status:** IMPLEMENTED, tested, dormant.
> All P4A feature flags default OFF. Zero production behaviour change.
> Landed: 2026-07-20.
> Preceded by: `PHASE_4_MASTER_PLAN.md` (operator-approved).
> Cumulative Phase-2 + P4A unit tests: **239 / 239 passing**
> (181 prior + 58 new for P4A).

---

## 1. What landed

P4A.0 through P4A.5 delivered per the master plan §3.

### 1.1 Scaffolding (P4A.0)

Four new modules provide the shared connector plumbing that every
Stage-4 connector inherits from:

- **`connector_auth.py`** — auth models (`NoAuth`, `ApiKeyAuth`,
  `BearerAuth`, `OAuthClientCredentials`). Every secret is read at
  call time from env vars; `__repr__` and `to_health_dict()` redact.
- **`connector_retry.py`** — declarative `RetryPolicy` +
  three named policies (`CONNECTOR_DEFAULT`, `CONNECTOR_CONSERVATIVE`,
  `CONNECTOR_AGGRESSIVE`). Pure data; supports full / equal / none
  jitter modes and a mandatory 429 cool-off floor.
- **`connector_health.py`** — `ConnectorState` enum (registered →
  opted_in → healthy ⇄ degraded ⇄ cooling → failing → quarantined →
  dormant) + `ConnectorObserver` (in-process bookkeeping) +
  `ConnectorHealthSnapshot` dataclass.
- **`connectors/base.py`** — `AbstractConnector` composing all of the
  above. Provides `_call_with_retry`, `content_hash`, `is_flag_enabled`,
  `is_available`, `health_snapshot()`.

### 1.2 Five concrete connectors (P4A.1–P4A.5)

| Connector | Module | Domains | Trust seed | Auth | Discovery |
|---|---|---|---|---|---|
| `ArxivConnector` | `connectors/arxiv.py` | RESEARCH | T4 | Optional API key | ✅ (+ seed) |
| `PdfConnector` | `connectors/pdf.py` | RESEARCH / STRATEGY / EXECUTION / INDICATOR | T3 (T4 when `curated=true`) | NoAuth / BearerAuth (injected) | ❌ (curated seed only) |
| `PropFirmConnector` | `connectors/propfirm.py` | EXECUTION | T4 | NoAuth (default) / OAuth | ✅ (walks curated allow-list) |
| `TradingViewConnector` | `connectors/tradingview.py` | STRATEGY / INDICATOR | T3 (T4 for house scripts) | NoAuth | ❌ (curated seed only) |
| `InternalMongoConnector` | `connectors/internal_mongo.py` | INTERNAL_HISTORY | T5 | NoAuth (in-process DB) | ✅ (cursor over source collections) |

**Live network I/O is deferred.** Every connector accepts an optional
`http_client` (or `db_getter`) injection port for tests. When the flag
is enabled but no client is injected, connectors run in **seed mode**
(curated references) — no external calls are made until an operator
explicitly wires a live client. This satisfies the master-plan
requirement that flag-off = byte-identical posture.

### 1.3 Registry — flag-aware filtering

`engines/knowledge/registry.py` — `list_connectors()` / `get_connector()`
now filter by two-level flag gating:
1. **Master switch**: `UKIE_CONNECTOR_FRAMEWORK_ENABLED` (default OFF)
   — when off, every Stage-4 connector is hidden.
2. **Per-connector flag**: `UKIE_CONNECTOR_<NAME>_ENABLED` — only
   enabled connectors appear.

Legacy connectors (no `flag_name` attribute — e.g. `GithubConnector`)
remain visible unconditionally to preserve Stage 3.α behaviour
byte-identically.

### 1.4 Health-visibility endpoints

Two new admin endpoints (both gate on
`UKIE_CONNECTOR_FRAMEWORK_ENABLED`, HTTP 503 when off):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/knowledge/connectors/health` | Aggregate snapshot for every visible connector |
| `GET` | `/api/knowledge/connectors/{name}/health` | Per-connector snapshot |

Route-ordering: the new endpoints are inserted **before** the Stage-3.α
`/connectors/{name}` catch-all so `/connectors/health` doesn't get
routed through the wrong gate.

### 1.5 Files added / modified

Added (11 files):
- `backend/legacy/engines/knowledge/connector_auth.py`
- `backend/legacy/engines/knowledge/connector_retry.py`
- `backend/legacy/engines/knowledge/connector_health.py`
- `backend/legacy/engines/knowledge/connector_router.py`
- `backend/legacy/engines/knowledge/connectors/base.py`
- `backend/legacy/engines/knowledge/connectors/arxiv.py`
- `backend/legacy/engines/knowledge/connectors/pdf.py`
- `backend/legacy/engines/knowledge/connectors/propfirm.py`
- `backend/legacy/engines/knowledge/connectors/tradingview.py`
- `backend/legacy/engines/knowledge/connectors/internal_mongo.py`
- `backend/tests/test_connector_scaffolding.py` (30 tests)
- `backend/tests/test_connectors_stage4.py` (28 tests)

Modified (3 files):
- `backend/legacy/engines/knowledge/registry.py` — two-level flag
  filtering + bootstrap the five new connectors (flag-hidden by
  default).
- `backend/legacy/engines/knowledge/router.py` — mount connector-health
  routes before the Stage-3.α `/connectors/{name}` catch-all.
- `backend/legacy/engines/knowledge/__init__.py` — new exports for the
  auth, retry, health, base, and five connector classes.

---

## 2. Feature-flag matrix

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_CONNECTOR_FRAMEWORK_ENABLED` | `false` | Master switch: Stage-4 connectors visible in `list_connectors()`; connector-health endpoints served (else HTTP 503) |
| `UKIE_CONNECTOR_ARXIV_ENABLED` | `false` | ArxivConnector visible + operational (once framework is on) |
| `UKIE_CONNECTOR_PDF_ENABLED` | `false` | PdfConnector visible + operational |
| `UKIE_CONNECTOR_PROPFIRM_ENABLED` | `false` | PropFirmConnector visible + operational |
| `UKIE_CONNECTOR_TRADINGVIEW_ENABLED` | `false` | TradingViewConnector visible + operational |
| `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED` | `false` | InternalMongoConnector visible + operational |

Optional secrets (all optional, no defaults):
- `ARXIV_API_KEY` — raises Arxiv rate limits
- `INTERNAL_MONGO_BEARER_TOKEN` — placeholder (not used by the
  in-process connector but the auth mode is declared for future
  distributed workers)
- `PROPFIRM_CLIENT_ID` / `PROPFIRM_CLIENT_SECRET` — OAuth for firms
  that require it

Every flag defaults OFF. **Zero production behaviour change.**

---

## 3. Rollback SLA

| Rollback path | Mechanism | Target SLA |
|---|---|---|
| Framework-wide (turn off all Stage-4 connectors) | `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false` + supervisor restart | ~30s |
| Per-connector opt-out | Corresponding `UKIE_CONNECTOR_<NAME>_ENABLED=false` + restart | ~30s |
| Nuclear per-connector deletion | `db.strategy_knowledge_base.<collection>.deleteMany({connector_name: "<name>"})` — connector name is stamped on every written item | seconds |

All continue to meet the 60-s platform SLA.

---

## 4. Cumulative test status

```
tests/test_knowledge_domains.py         · PASS   (Stage 3.α)
tests/test_knowledge_connector.py       · PASS   (Stage 3.α)
tests/test_knowledge_router.py          · PASS   (Stage 3.α)
tests/test_knowledge_pipeline.py        · PASS   (Stage 3.β)
tests/test_domain_router.py             · PASS   (Stage 3.β)
tests/test_license_gate.py              · PASS   (Stage 3.β)
tests/test_trust_scorer.py              · PASS   (Stage 3.β)
tests/test_dedup_and_repository.py      · PASS   (Stage 3.β)
tests/test_bi5_bid_diff.py              · PASS   (Stage 2 shadow)
tests/test_promote_bridge.py            · PASS   (Stage 3.γ)
tests/test_retro_score.py               · PASS   (Stage 3.γ)
tests/test_connector_scaffolding.py     · PASS   (Stage 4 P4A — new, 30 tests)
tests/test_connectors_stage4.py         · PASS   (Stage 4 P4A — new, 28 tests)
──────────────────────────────────────────────────────────────────
Total UKIE + Stage-2 shadow + Stage-4 P4A unit tests: 239 / 239 PASSING
```

Test-count evolution:
- Before P4A: 181 UKIE + BI5 unit tests
- After P4A: **239** unit tests (+58 for P4A)
- Test authoring:
  - `test_connector_scaffolding.py` — 30 tests covering auth
    redaction, retry policy math, observer transitions, abstract
    base gating, registry flag-filter behaviour, and router 503/200
    on the health endpoints
  - `test_connectors_stage4.py` — 28 tests covering each of the five
    connectors' `discover` / `fetch` / rate-limit / license detection
    / trust boost paths, all with injected fakes (zero real network)

---

## 5. Architectural recommendations before proceeding to P4B

1. **Live-mode wiring is separate.** The current implementation ships
   the seed-mode surface plus the injectable HTTP-client / DB-getter
   port. When Coherent UKIE Activation happens post-freeze, we'll
   wire real `aiohttp.ClientSession` calls into each connector's
   `http_client` slot. That's a one-line switch per connector and
   NOT a Stage-4 concern.
2. **Connector-events collection is declared but not written.** The
   plan (§3.7) calls for a `strategy_knowledge_base.connector_events`
   collection to persist state transitions. The in-process observer
   currently keeps history in memory. Persisting to Mongo is a
   Stage-4 P4D task (Observability finalisation) — deferring keeps
   P4A's write surface = 0.
3. **Route ordering is fragile.** We rely on `routes.insert(0, ...)`
   to place the new `/connectors/health` route before the Stage-3.α
   `/connectors/{name}` catch-all. Consider a small comment or a
   dedicated router-composition helper before Stage 5. Not blocking
   for Stage 4.
4. **AbstractConnector is optional.** The Protocol pattern from Stage
   3.α still holds — a connector can implement the Protocol without
   inheriting `AbstractConnector`. `GithubConnector` is a live proof
   of this. Keep the base class as an ergonomic helper, not a
   contract requirement. This decoupling helps for future distributed
   workers that might host lightweight connector adapters.
5. **No connector wire is currently held open.** All I/O is invoked
   per-`discover`/`fetch` call. When a live HTTP client is injected,
   the caller owns its lifecycle. This is the correct posture for
   distribution readiness.

**Recommendation:** proceed to **P4B — COE γ** in the sequenced order.
P4A leaves the system in a clean state; the connector-events Mongo
sink is intentionally deferred to P4D where the whole observability
surface lands together.

---

## 6. Explicit non-goals maintained

- No writes to production `strategies` (Stage-3.γ invariant preserved).
- No writes to legacy `ingested_strategies` (Stage-3.γ retro-score
  discipline preserved).
- No live network I/O by default (seed mode is the only default).
- No connector-events persistence (deferred to P4D).
- No health-provider retrofit for other subsystems (deferred to P4D).
- No retrieval API / ranking-v2 (deferred to P4C).

---

## 7. Live-verification checklist (operator, when ready)

Preview pod, `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false` (default):
- [ ] `GET /api/knowledge/connectors/health` → HTTP 503
- [ ] `GET /api/knowledge/connectors/arxiv/health` → HTTP 503
- [ ] `GET /api/knowledge/connectors` (Stage 3.α, once
      `UKIE_DOMAIN_REGISTRY_ENABLED=true`) returns only the legacy
      `github` connector.

With `UKIE_CONNECTOR_FRAMEWORK_ENABLED=true`,
`UKIE_CONNECTOR_ARXIV_ENABLED=true` (Stage 3.α also on):
- [ ] `GET /api/knowledge/connectors/health` → 200 with 2 entries
      (`github`, `arxiv`)
- [ ] `GET /api/knowledge/connectors/arxiv/health` → 200; snapshot
      shows `flag_enabled=true, auth_mode="api_key", state="opted_in"`
- [ ] `GET /api/knowledge/domains/research/connectors` includes
      `arxiv`
- [ ] `POST /api/knowledge/dry-run` still runs the built-in fixture
      unchanged.

Rollback:
- [ ] Set `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false` → both new
      endpoints return 503; `list_connectors()` returns only `github`.
- [ ] `/api/health/system` unchanged: `platform_score=100 · [coe, vie, cts]`
      (no new subsystem block until P4D lands the health-provider).

---

*Status:* **P4A implemented, tested, dormant. Awaiting operator
signal to proceed to P4B — COE γ.**
