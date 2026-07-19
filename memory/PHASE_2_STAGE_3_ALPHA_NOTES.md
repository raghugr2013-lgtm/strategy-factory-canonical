# Phase 2 — Stage 3.α Foundation Notes
### KnowledgeDomain Registry + KnowledgeConnector Protocol (P2C.0 + P2C.1)

> **Status:** review pending operator approval.
> Assembled: 2026-02-19.
> Scope: Phase 2 Stage 3.α as authorised on 2026-02-19 — foundation
> architecture only.

---

## 1. Executive summary

| Dimension | Result |
|---|---|
| Sub-steps implemented (P2C.0 + P2C.1) | ✅ Complete |
| New Stage-3.α tests | **50 / 50 passing** |
| Cumulative Phase-2 tests | **158 / 158 passing** (Stages 1 + 2 + 3.α) |
| Live surface | `/api/knowledge/domains`, `/api/knowledge/connectors` verified |
| Feature-flag gating | `UKIE_DOMAIN_REGISTRY_ENABLED` — HTTP 503 when off (verified) |
| Backward compatibility | Byte-identical when flag off; zero legacy behaviour change |
| Recommendation | ✅ **PASS — foundation ready; proceed to Stage 3.β on approval** |

---

## 2. What was built

### 2.1 `KnowledgeDomain` registry — the single source of truth

- **Enum** with the six canonical domains (`strategy`, `research`,
  `indicator`, `market`, `execution`, `internal_history`).
- **`KnowledgeDomainSpec`** — frozen dataclass carrying every
  operator-mandated field, all with sensible defaults:
  - `domain`, `display_name`, `description`
  - `storage_collection`, `required_fields`
  - `default_trust_floor`, `ai_context_policy`
  - `default_retention_policy`, `searchable`, `version`
- **`KNOWLEDGE_DOMAIN_REGISTRY`** — immutable module-level mapping,
  the single source of truth for domain metadata.
- **Look-up helpers**: `get_domain(name)`, `get_domain_spec(domain)`,
  `list_domains()`, `storage_collection_for(domain)`,
  `is_searchable(domain)`.

**Extensibility contract satisfied** — every field has a default, so
adding a seventh domain is one entry in the registry with no
downstream code changes.

**Files:** `/app/backend/legacy/engines/knowledge/domains.py` (330 lines).

### 2.2 `KnowledgeConnector` Protocol — with capability metadata

- **`@runtime_checkable Protocol`** with fields `name`, `source_type`,
  `supported_domains: FrozenSet[KnowledgeDomain]`, `default_trust_tier`,
  `supported_licenses`, `capabilities`, and async methods
  `discover(query) → AsyncIterator[Reference]`, `fetch(ref) → RawKnowledgeItem`,
  `rate_limit() → RateLimit`.
- **`ConnectorCapabilities`** — frozen dataclass declaring five
  capability flags, all defaulting to `False`:
  - `supports_discovery`
  - `supports_incremental_sync`
  - `supports_versioning`
  - `supports_rate_limits`
  - `supports_metadata_only`
- **Supporting shapes**: `RateLimit`, `DiscoveryQuery`, `Reference`,
  `RawKnowledgeItem` (with the `domain` field + hard-rail guardrails
  `learning_only=True`, `eligible_for_deploy=False`).

**Design promise honoured** — capability metadata is declared upfront
so future connectors plug in without interface changes.

**Files:** `/app/backend/legacy/engines/knowledge/connector.py` (240 lines).

### 2.3 `GithubConnector` — the first adapter

- Wraps `engines.strategy_ingestion.collector.collect_from_github`.
- Declares `supported_domains = frozenset({STRATEGY})`.
- Declares its **honest** capability set:
  `supports_discovery=True`, `supports_versioning=True`
  (commit-SHA extraction), `supports_rate_limits=True`
  (respects `GITHUB_TOKEN` env), `supports_incremental_sync=False`
  (Stage 4), `supports_metadata_only=False` (Stage 4).
- Emits `RawKnowledgeItem(domain=STRATEGY, ...)` with SHA-256
  content hash, MIME sniff by extension, and every guardrail set.

**Zero behaviour change** to the legacy path — the existing
`ingestion_runner` continues to call `collector` directly. The
adapter is the forward-compatible surface Stage 3.β pipeline stages
will consume.

**Files:** `/app/backend/legacy/engines/knowledge/connectors/github.py` (168 lines).

### 2.4 Registry module

- Combines domain re-exports with a connector registry
  (`register_connector`, `get_connector`, `list_connectors`,
  `connectors_for_domain`).
- Registers `GithubConnector` at import time via
  `_bootstrap_default_connectors()`.
- `register_connector()` fails fast (`TypeError`) on non-Protocol
  arguments or empty names — wiring bugs surface at boot.

**Files:** `/app/backend/legacy/engines/knowledge/registry.py` (120 lines).

### 2.5 Read-only API surface

Router mounted at `/api/knowledge/*` — feature-gated
(`UKIE_DOMAIN_REGISTRY_ENABLED=false` → HTTP 503).

| Endpoint | Purpose |
|---|---|
| `GET /api/knowledge/domains` | List all six domain specs |
| `GET /api/knowledge/domains/{domain}` | Return one domain spec (case-insensitive lookup) |
| `GET /api/knowledge/connectors` | List all registered connectors |
| `GET /api/knowledge/connectors/{name}` | Return one connector's metadata |
| `GET /api/knowledge/domains/{domain}/connectors` | List connectors supporting a given domain |

All routes are read-only. No writes. No side effects.

**Files:** `/app/backend/legacy/engines/knowledge/router.py` (125 lines).

---

## 3. Feature flag introduced

| Flag | Default | Effect when ON |
|---|---|---|
| `UKIE_DOMAIN_REGISTRY_ENABLED` | `false` | Mounts `/api/knowledge/domains/*` + `/api/knowledge/connectors/*` endpoints |

**No other flags in Stage 3.α.** Pipeline-stage flags
(`ENABLE_DOMAIN_ROUTING`, `ENABLE_LICENSE_GATE`, `ENABLE_TRUST_SCORER`,
`ENABLE_DEDUP_CHECK`, `UKIE_GOVERNANCE_CUTOVER`,
`UKIE_PROMOTE_BRIDGE_ENABLED`) come in Stage 3.β.

**Rollback:** `UKIE_DOMAIN_REGISTRY_ENABLED=false` → supervisor restart
(~30 s). Endpoints return 503. Zero data-path effect regardless of flag.

---

## 4. Test evidence

Runbook:
```
cd /app/backend && python3 -m pytest \
  tests/test_knowledge_domains.py \
  tests/test_knowledge_connector.py \
  tests/test_knowledge_router.py -q
```

Result: **50 passed in 0.85 s**.

| Test file | Tests | Coverage |
|---|---|---|
| `test_knowledge_domains.py` | 19 | Six canonical domains present; spec shape with every operator-mandated field; frozen dataclass; storage_collections unique; execution / internal_history trust-floor invariants; look-up helpers (name / value / enum-name / case-insensitive); unknown-domain error; extensibility contract (spec defaults allow minimal construction; JSON-safe `to_dict`) |
| `test_knowledge_connector.py` | 22 | Capabilities default all-False + frozen + JSON-safe; RateLimit / DiscoveryQuery / Reference shapes; RawKnowledgeItem carries `domain` + hard-rail guardrails; `to_dict` omits bytes; GithubConnector satisfies Protocol; honest capability declaration; rate-limit values sane; fetch produces canonical item with SHA-256 hash + MIME; discover on mismatched domain yields nothing; registry register/reset/lookup/list; rejects non-Protocol; rejects empty name; filter by domain works |
| `test_knowledge_router.py` | 9 | All endpoints 503 when flag off; domains-list returns six; per-domain spec returns all required fields; case-insensitive lookup; unknown → 404; connectors-list includes github; connector metadata has capability surface; per-domain-connector filter works; unknown domain → 404 |

**Regression** — Stages 1 + 2 tests continue to pass unchanged:
- Stage 1: 34 tests (health contract, workload request, hard timeout, provider hint, budget persist)
- Stage 2: 74 tests (workload queue, reservations, io pool, cts, coverage + metrics, metrics primitives)
- Stage 3.α: 50 tests
- **Total: 158 / 158 passing**

---

## 5. Live verification

Preview pod, `UKIE_DOMAIN_REGISTRY_ENABLED=true`:

```
GET /api/knowledge/domains          → 200, count=6, all six specs
GET /api/knowledge/domains/strategy → 200, full spec with 10 fields
GET /api/knowledge/connectors       → 200, count=1, github registered
GET /api/knowledge/health/system    → 200, platform_score=100, subsystems=[coe, vie, cts]
```

`UKIE_DOMAIN_REGISTRY_ENABLED=false`:
```
GET /api/knowledge/domains → 503 "UKIE_DOMAIN_REGISTRY_ENABLED is off"
```

**Health surface unchanged** — `/api/health/system` still reports three
subsystems (`coe`, `vie`, `cts`); Stage 3.α does not register a new
health provider (that lands in Stage 3.β with the pipeline stages).

---

## 6. Explicit non-goals honoured

The following are intentionally NOT in Stage 3.α, per the operator
approval on 2026-02-19:

- ❌ No pipeline stages (`domain_router`, `license_gate`, `trust_scorer`,
  `dedup_check`) — Stage 3.β
- ❌ No `KnowledgeRepository.insert_ingested()` — the governance
  cutover is Stage 3.β
- ❌ No new connectors beyond the GitHub adapter — Arxiv / PDF /
  PropFirm / TradingView / InternalMongo are Stage 4
- ❌ No retro-scoring of the 55 existing `ingested_strategies` rows —
  Stage 3.β
- ❌ No changes to `strategy_ingestion/*` behaviour — pure adapter wrap
- ❌ No CTS / COE / VIE changes
- ❌ No writes to production `strategies`, `outcome_events`,
  `ingested_strategies`

---

## 7. Files delivered

### New files
- `/app/backend/legacy/engines/knowledge/domains.py` (330 lines)
- `/app/backend/legacy/engines/knowledge/connector.py` (240 lines)
- `/app/backend/legacy/engines/knowledge/connectors/__init__.py`
- `/app/backend/legacy/engines/knowledge/connectors/github.py` (168 lines)
- `/app/backend/legacy/engines/knowledge/registry.py` (120 lines)
- `/app/backend/legacy/engines/knowledge/router.py` (125 lines)
- `/app/backend/tests/test_knowledge_domains.py` (19 tests)
- `/app/backend/tests/test_knowledge_connector.py` (22 tests)
- `/app/backend/tests/test_knowledge_router.py` (9 tests)

### Modified (surgical, additive)
- `/app/backend/legacy/engines/knowledge/__init__.py` — new Stage-3.α
  exports appended below the pre-existing L1/L2 re-exports
- `/app/backend/app/main.py` — mount UKIE router below X-COE-Pressure
  middleware; try-except guarded

**No files deleted. No production data modified. No changes to any
Stage-1 or Stage-2 file.**

---

## 8. Interface for Stage 3.β

Stage 3.β consumers should:

1. Import the domain registry via
   ```python
   from engines.knowledge import (
       KnowledgeDomain, KnowledgeDomainSpec, get_domain_spec, list_domains,
   )
   ```
2. Import the connector Protocol via
   ```python
   from engines.knowledge import (
       KnowledgeConnector, ConnectorCapabilities, RawKnowledgeItem,
       DiscoveryQuery, Reference, RateLimit,
   )
   ```
3. Route pipeline decisions by `RawKnowledgeItem.domain` — never
   hard-code a domain enum value at a decision site; always resolve
   through `get_domain_spec(item.domain)`.
4. Feature-gate every new pipeline stage individually
   (`ENABLE_DOMAIN_ROUTING`, `ENABLE_LICENSE_GATE`, etc.) — Stage 3.α
   flag `UKIE_DOMAIN_REGISTRY_ENABLED` only exposes the read-only
   discovery surface.

---

## 9. Recommendation

### ✅ **PASS — foundation ready for Stage 3.β on operator approval.**

Justification:
1. **Complete.** P2C.0 (`KnowledgeDomain` + `KnowledgeDomainSpec`) and
   P2C.1 (`KnowledgeConnector` Protocol + `GithubConnector` adapter)
   are implemented and verified.
2. **Extensibility contracts honoured.** Every domain-spec field has
   a default; every capability flag is declared upfront; adding a
   seventh domain or a new connector is one file.
3. **Zero data risk.** No writes to any collection; no changes to
   legacy ingestion behaviour; flag-off returns 503 on the new endpoints.
4. **Backward compatible.** Stage-1 (34) + Stage-2 (74) tests
   continue passing; the pre-existing `knowledge/{extractor,indexer,
   retriever,prompt_block}` module surface is unchanged.
5. **Contract-first.** The UKIE Protocol surface is stable enough
   for parallel connector development in Stage 4 (Arxiv, PDF,
   PropFirm, TradingView, InternalMongo) once Stage 3.β lands the
   pipeline.

### Recommended pre-Stage-3.β actions

1. Enable `UKIE_DOMAIN_REGISTRY_ENABLED=true` in production once
   this note is signed off. Zero data-path risk; enables operator
   dashboards + downstream connector development to consult the
   registry via HTTP.
2. Begin Stage 3.β planning: pipeline stages (`domain_router`,
   `license_gate`, `trust_scorer`, `dedup_check`),
   `KnowledgeRepository.insert_ingested()`, governance-cutover
   dry-run harness, retro-scoring script.

---

*Reviewed against:*
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §1.0 (Knowledge Domain model), §1.2 (Connector contract), §7 P2C.0 + P2C.1`
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §6.3 / §10.3`
- Live pod responses at `http://localhost:8001/api/knowledge/{domains,connectors}`
- pytest output from `/app/backend/tests/`

*Status:* **Awaiting operator sign-off. Stage 3.β planning may begin immediately after approval.**
