# Phase 4 (Stage 4) — Master Implementation Plan
### Connector Fleet · COE γ · UKIE γ · Observability Finalisation

> **Status:** planning only — awaiting operator approval.
> No implementation until this plan is signed off.
> Assembled: 2026-07-20.
> Precondition: Stage 3.γ APPROVED (2026-07-20); Coherent UKIE
> Activation not yet performed; production posture unchanged
> (all UKIE + Stage-3.γ flags OFF).

---

## 0. Guiding principles (unchanged since Stages 1 – 3.γ)

1. **Feature-flagged.** Every new capability defaults OFF. No route,
   no worker, no connector, no dashboard is reachable until an
   operator flips a named flag.
2. **Dry-run first.** Every write path ships a shadow-mode counterpart
   before the flag that enables the write is exposed.
3. **Backward compatibility.** No shape change to existing Stage-1..3
   documents, endpoints, or Mongo collections. Every schema evolution
   is additive.
4. **Idempotent.** Re-running any admin action produces the same
   state; no accidental duplicates, no orphan rows.
5. **Full audit trail.** Every mutation is provenance-stamped
   (`origin`, `pipeline_version`, `pipeline_contract_version`,
   `processed_at`, and where applicable `run_id` / `event_id`).
6. **Rollback strategy.** Every capability has an explicit,
   TESTED rollback path — flag flip, `deleteMany` filter, or per-item
   endpoint.
7. **Documentation first.** Nothing lands without design notes.
   Post-implementation notes are written the same day the code is
   merged.
8. **No production behaviour change until Validation Gate 5 passes
   and the operator approves activation.**

---

## 1. Scope

Four workstreams, planned separately, deliverable as a single
Stage-4 increment with independent internal sub-milestones:

- **P4A — Connector Fleet.** Five new `KnowledgeConnector`
  implementations + connector lifecycle scaffolding (registration,
  auth, retry, rate-limiting, health, feature flags).
- **P4B — COE γ.** Retry executor, dead-letter collection, work
  recovery, provider-aware admission, elastic band redistribution,
  operator dashboard endpoints, budget-headroom protection.
- **P4C — UKIE γ.** Retrieval + query API on the UKIE-KB with ranking,
  confidence evolution, lifecycle (retention TTL, decay), governance
  extensions (policy language on top of the T4+/permissive/dedup
  gate).
- **P4D — Observability Finalisation.** Per-subsystem
  `HealthSnapshot` retrofit, connector health, UKIE health,
  knowledge metrics, dashboard panels, alerting rules, audit
  visibility endpoints.

### 1.1 Non-goals for Stage 4 (deferred to Phase 5 / Autonomy prep)

- Live autonomous execution mode (Recommendation Mode / Autonomous
  Mode)
- Paper-broker validation harness
- Frontend implementation
- Backend feature freeze (comes AFTER Stage 4 completes)
- VPS deployment (post-freeze)
- 24-h / 72-h validation runs (post-freeze)
- Retrieval-augmented autonomous decisions (Stage 5.α)

### 1.2 What Stage 4 explicitly preserves

- Legacy `strategy_ingestion/*` — untouched. UKIE runs alongside;
  the legacy write path is only retired after the coherent
  activation, and that's a separate approved step.
- Legacy `ingested_strategies` — READ-ONLY (protected by Stage 3.γ
  retro-score design).
- Production `strategies` — written to ONLY via the audited Stage-3.γ
  promote bridge, with `learning_only=True`,
  `eligible_for_deploy=False`. Stage 4 does not change this.
- Every Stage-3 hard-rail invariant remains in effect.

---

## 2. Sequenced deliverables

If approved, the implementation order is:

**Track 1 — P4A Connector Fleet (parallelisable across 2 engineers)**
1. P4A.0 — connector-framework scaffolding (auth, retry, health,
   flag registry) — enabling gate for all subsequent connectors.
2. P4A.1 — `ArxivConnector` (research)
3. P4A.2 — `PdfConnector` (research + strategy + execution +
   indicator)
4. P4A.3 — `PropFirmConnector` (execution)
5. P4A.4 — `TradingViewConnector` (strategy + indicator)
6. P4A.5 — `InternalMongoConnector` (internal_history — read-only
   mirror)

**Track 2 — P4B COE γ (single engineer)**
1. P4B.1 — retry executor + exponential backoff
2. P4B.2 — dead-letter collection + endpoints
3. P4B.3 — work recovery on process crash
4. P4B.4 — provider-aware admission (circuit-breaker consult)
5. P4B.5 — age-boost score adjustment
6. P4B.6 — elastic band redistribution
7. P4B.7 — budget-headroom protection

**Track 3 — P4C UKIE γ (single engineer)**
1. P4C.1 — retrieval API (`GET /api/knowledge/query`)
2. P4C.2 — ranking backend (rule + optional embedding)
3. P4C.3 — retention TTL + lifecycle sweeper
4. P4C.4 — confidence evolution (per-domain re-scoring cadence)
5. P4C.5 — governance policy language (rule-based promote)

**Track 4 — P4D Observability (single engineer)**
1. P4D.1 — UKIE health provider (`/api/health/system` gains `ukie`)
2. P4D.2 — connector health surface
3. P4D.3 — knowledge metrics endpoint
4. P4D.4 — subsystem `HealthSnapshot` retrofits (Meta-Learning, MI,
   Execution, Portfolio, Factory-Eval)
5. P4D.5 — dashboard panels + alerting rules
6. P4D.6 — audit visibility endpoints
   (`GET /api/knowledge/promote-events`,
   `GET /api/knowledge/retro-score-runs`)

Each step ships behind at least one flag. Each step lands with
pytest coverage. Backend regression is required to remain 100% clean
across every step.

---

## 3. P4A — Connector Fleet

### 3.1 Scaffolding (P4A.0) — enabling gate

The scaffolding lands before any concrete connector. It extends the
Stage-3.α protocol (`engines.knowledge.connector.KnowledgeConnector`)
with the lifecycle bits that were deferred:

#### 3.1.1 Files to add / modify

Add:
- `engines/knowledge/connector_auth.py` — auth models
  (`NoAuth`, `ApiKeyAuth`, `OAuthClientCredentials`, `BearerAuth`)
  with an injection port (`AuthResolver`) that reads secrets from
  env, never from code.
- `engines/knowledge/connector_retry.py` — declarative retry policy
  (`RetryPolicy(max_attempts, base_delay, max_delay, jitter,
  retry_on_status={429,502,503,504})`).
- `engines/knowledge/connector_health.py` —
  `ConnectorHealthProbe(name) → HealthSnapshot` protocol.
- `engines/knowledge/connectors/base.py` — abstract base class
  (`AbstractConnector`) that composes auth + retry + rate-limiting +
  a common ETag/If-Modified-Since incremental-sync utility.

Modify:
- `engines/knowledge/registry.py` — connector registration now also
  requires a `flag_name` (per-connector master switch); connectors
  without their flag on are dropped from `list_connectors()`.
- `engines/knowledge/router.py` — mount
  `GET /api/knowledge/connectors/{name}/health` (gated by the
  connector's own flag).

Tests:
- `backend/tests/test_connector_scaffolding.py` — retry policy
  respected; auth resolver never logs secrets; health probe format;
  flag-gated visibility.

#### 3.1.2 Feature flags (scaffolding-level)

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_CONNECTOR_FRAMEWORK_ENABLED` | `false` | Loads `AbstractConnector` + retry / auth surface (does NOT enable any specific connector) |

Per-connector flags follow the naming pattern
`UKIE_CONNECTOR_<NAME>_ENABLED` (all default OFF).

### 3.2 Connector lifecycle (cross-connector contract)

Every connector goes through the following six states, each observable
via `GET /api/knowledge/connectors/{name}/health`:

```
       registered
           │  flag on
           ▼
        opted-in
           │  first discover() / fetch() success
           ▼
         healthy   ─────► degraded (recoverable errors, retries firing)
           │                    │
           │                    ▼
           ▼                 failing (retry budget exhausted)
        cooling                 │
           │                    ▼
           │                 quarantined (operator flag override)
           └────────────────────┘
```

`healthy → degraded → failing → quarantined` transitions are stamped
in a new `strategy_knowledge_base.connector_events` collection with
per-connector event history.

### 3.3 Authentication model

Every connector declares its auth mode at registration:

| Auth mode | Used by | Config env vars (example) |
|---|---|---|
| `NoAuth` | GitHub (existing), TradingView public | — |
| `ApiKeyAuth` | Arxiv (rate-limit header only) | `ARXIV_API_KEY` (optional) |
| `BearerAuth` | Internal Mongo (JWT) | `INTERNAL_MONGO_BEARER_TOKEN` |
| `OAuthClientCredentials` | PropFirm portals (some) | `PROPFIRM_CLIENT_ID`, `PROPFIRM_CLIENT_SECRET` |

**No secrets in code, no defaults for secrets in `.env.example`** —
every secret is read via `os.environ.get(...)` with `None` fallback
and the connector's `health` reports `mode="unconfigured"` when
secrets are missing (rather than crashing).

### 3.4 Versioning

Every connector carries:
- `connector_version` (semver) — bumped for any code change.
- `source_contract_version` (int) — bumped when the shape of
  `RawKnowledgeItem.extras` the connector emits changes.

Both are stamped on every `RawKnowledgeItem` (added as fields on
`RawKnowledgeItem.extras`) and propagated into the repository write
via `_build_doc`. This is additive to the existing
`pipeline_version` / `pipeline_contract_version`.

### 3.5 Retry strategy (cross-connector default)

```
RetryPolicy(
    max_attempts   = 3,
    base_delay_s   = 2.0,
    max_delay_s    = 60.0,
    jitter         = "full",
    retry_on_status= {429, 502, 503, 504},
    retry_on_exc   = (asyncio.TimeoutError, aiohttp.ClientError),
    cool_off_on_429_s = 60,
)
```

Connectors may override per-source. `429`s trigger the connector's
declared `cooloff_seconds` from `RateLimit`. Repeated `429`s move
the connector into `cooling` state and `list_connectors()` returns
`available=False` for admission decisions.

### 3.6 Failure handling

Three failure surfaces, each treated separately:

| Failure class | Handling |
|---|---|
| Transient network / 5xx | Retry per `RetryPolicy`; health = `degraded` |
| Rate-limit (429) | Honour cool-off; health = `cooling`; scheduler defers new fetches |
| Structural (parse error, malformed content) | Fail closed for that reference; audit row in `connector_events`; continues with next |
| Auth failure (401/403) | Health flips to `failing`; connector opts out until secret is rotated |

Nothing crashes the pipeline. Every failure is a data row.

### 3.7 Audit logging (per connector)

- `strategy_knowledge_base.connector_events` — one row per
  state-transition event; TTL 180d.
- `strategy_knowledge_base.ingestion_runs` — one row per
  discover / fetch batch (already present; extended with per-connector
  counts + health snapshot at end-of-batch).

### 3.8 Feature flags (per connector, default OFF)

| Flag | Connector |
|---|---|
| `UKIE_CONNECTOR_ARXIV_ENABLED` | ArxivConnector |
| `UKIE_CONNECTOR_PDF_ENABLED` | PdfConnector |
| `UKIE_CONNECTOR_PROPFIRM_ENABLED` | PropFirmConnector |
| `UKIE_CONNECTOR_TRADINGVIEW_ENABLED` | TradingViewConnector |
| `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED` | InternalMongoConnector |
| `UKIE_CONNECTOR_GITHUB_ENABLED` (existing) | GithubConnector |

The connector registry filters by these flags. A disabled connector
returns HTTP 404 from `/connectors/{name}` and does not appear in
`GET /api/knowledge/connectors`.

### 3.9 Per-connector deliverables

#### 3.9.1 `ArxivConnector`
- Domains: `research`
- Auth: `NoAuth` (public API) — optional `ARXIV_API_KEY` for
  higher rate-limit
- Source: `http://export.arxiv.org/api/query`
- Discovery: supported (search by category + query string)
- Incremental: supported (via `since` timestamp)
- Versioning: supported (arxiv IDs are permalinks)
- Trust seed: **T4** (curated academic corpus)
- Licence: Arxiv abstracts default to permissive; PDF licence
  varies — carry per-paper.

#### 3.9.2 `PdfConnector`
- Domains: `research` (default) with override via `target_domain` on
  the reference. Also usable for `strategy` / `execution` / `indicator`
  (e.g. PropFirm rulebooks distributed as PDFs).
- Auth: `NoAuth` for open URLs; `BearerAuth` optional for gated PDFs.
- Discovery: not supported — caller supplies references (curated
  seed list).
- Incremental: supported (ETag / Last-Modified).
- Extract: `pdfminer.six` (already available) — text + basic
  metadata. Never OCR (out of scope; Stage 5 candidate).
- Trust seed: **T3** by default; override per-item via `curated=true`
  in the reference extras.

#### 3.9.3 `PropFirmConnector`
- Domains: `execution` (rule sets)
- Auth: mixed — some portals are `NoAuth` (public rulebooks); some
  need `OAuthClientCredentials`.
- Discovery: NOT supported — every reference is a curated URL / PDF
  path in a static allow-list per prop firm.
- Trust seed: **T4** (rule sets need high trust — used by realism
  sweep).
- Content policy: `verbatim` (per Stage-3.α domain spec — rules
  must be quotable exactly).

#### 3.9.4 `TradingViewConnector`
- Domains: `strategy`, `indicator`
- Auth: `NoAuth` — reads public Pine scripts.
- Discovery: **NOT supported** in v1 (TV search API is rate-limited
  and terms-of-service-restricted). References come from curated
  seed lists.
- Trust seed: **T3** by default; boost via
  `extras.tv_stars` / `extras.tv_house_scripts` (house scripts
  become T4).
- Licence: `permissive` when the Pine header carries
  `// This source code is subject to the terms of the Mozilla Public
  License 2.0`; else `unknown`.

#### 3.9.5 `InternalMongoConnector`
- Domains: `internal_history` (read-only mirror of the Factory's own
  outputs — past strategies, mutation events, outcome journals).
- Auth: none (in-process Mongo connection via `engines.db.get_db`).
- Discovery: supported (`find` cursor on the source collection).
- Incremental: supported (`since` cursor on `created_at`).
- Trust seed: **T5** (produced by the Factory itself).
- Content policy: `summary` (per Stage-3.α — long docs summarised).
- WRITE POLICY: pure READ. Refuses `insert` / `update` on its own
  source collections (this is the strongest rail).

### 3.10 Rollback per connector

- Per-connector flag flip → connector disappears from registry;
  future ingestions omit it; existing rows remain (they carry the
  audit provenance).
- `deleteMany({connector_name: "<name>"})` on the KB storage
  collection — global rollback for a single connector.
- Every UKIE-KB row carries `connector_name` — the filter is
  unambiguous.

### 3.11 P4A test plan (per connector)

- Dry-run against ≥ 3 real references (recorded / VCR-style fixtures
  for CI reproducibility)
- Retry-policy respected (mock 429 → cool-off; mock 5xx → retries)
- Auth resolver never logs secrets (grep-based assertion)
- Health probe returns valid `HealthSnapshot`
- Flag-off ⇒ connector not visible from `/api/knowledge/connectors`
- Ingested items reach the domain's storage collection with correct
  `connector_name`, `connector_version`, `source_contract_version`
  stamps
- No production `strategies` writes (invariant across ALL connectors)

---

## 4. P4B — COE γ

### 4.1 Retry executor (P4B.1)

Wraps the existing `WorkloadQueue` submit path with an
exponential-backoff retry loop for **transient** failures.

- Retry classes (per WorkloadClass; each with its own budget):
  - `MARKET_DATA`: 5 attempts, 2s → 60s
  - `AGENT`: 3 attempts, 4s → 30s (LLM providers charge per attempt)
  - `BACKTEST`: 2 attempts, 10s → 60s
  - `EXECUTION`: 0 attempts (idempotency not guaranteed downstream —
    fail fast to operator)
  - `MONITORING` / `META_LEARNING` / `KNOWLEDGE`: 3 attempts each
- Per-task journal entry on each retry (writes to
  `workload_events`).
- Feature flag: `COE_RETRY_ENABLED=false` (default).

### 4.2 Dead-letter (P4B.2)

- Collection: `workload_dead_letter`
  (fields: `_id`, `workload_class`, `task_kind`, `task_id`,
   `error_class`, `error_message`, `first_failed_at`,
   `last_failed_at`, `attempts`, `provider`, `payload_snapshot`,
   `pipeline_version`).
- Endpoints:
  - `GET /api/coe/dead-letter?class=<X>&limit=<N>&offset=<M>`
  - `GET /api/coe/dead-letter/{id}` — full row
  - `POST /api/coe/dead-letter/{id}/requeue` — validates, submits
    back through the normal queue, marks the row `requeued_at`
  - `POST /api/coe/dead-letter/{id}/discard` — soft-deletes
    (`discarded_at`, `discarded_by`, `reason`)
- TTL index on `first_failed_at` — default 90 days.
- Feature flag: `COE_DEAD_LETTER_ENABLED=false` (default).

### 4.3 Work recovery (P4B.3)

On backend start-up, sweep any `workload_events` rows with
`status="in_flight"` older than `STALE_INFLIGHT_S` (default 300s).
Each stale row → either re-queued (if retry budget remains) or
dead-lettered.

- Idempotent (safe to run on every boot).
- Feature flag: `COE_WORK_RECOVERY_ENABLED=false` (default).

### 4.4 Failure isolation (P4B.4)

**Provider-aware admission** — before admitting an AGENT task or a
BACKTEST-with-LLM task, `admission_gate` consults
`ai_workforce.circuit_breaker`:

- Circuit CLOSED → admit (normal).
- Circuit OPEN for the requested provider → task is rejected with
  `reason=provider_unavailable`; VIE reroutes to another provider
  in the fallback chain.
- Circuit HALF_OPEN → admit with `probe=true` flag; a failure
  reopens; a success closes.

Feature flag: `COE_PROVIDER_AWARE_ADMISSION=false` (default).

### 4.5 Queue resilience (P4B.5, P4B.6)

- **Age-boost** in `orchestrator._score_task`: tasks waiting longer
  than `ORCH_AGE_BOOST_S` (default 60s) receive a +N priority delta
  per further 30s of wait. Prevents starvation under sustained load.
- **Elastic band redistribution** between BACKTEST ↔ MUTATION: when
  BACKTEST queue depth exceeds `ELASTIC_HIGH_WATER` and MUTATION is
  idle, MUTATION reservations temporarily loan capacity to BACKTEST.
  Reservations restored on the next scoring cycle.
- Feature flags:
  `COE_AGE_BOOST_ENABLED=false`,
  `COE_ELASTIC_BAND_ENABLED=false` (both default).

### 4.6 Budget protection (P4B.7)

- New middleware surface: **hard cutoff on daily USD budget**.
  When `budget_state.today_used_usd ≥
  budget_state.today_hard_cap_usd`, all AGENT + LLM tasks are
  refused with `HTTP 429 · reason=budget_hard_cap_reached`.
- Soft cap remains the existing warning surface.
- Feature flag: `COE_BUDGET_HARD_CAP_ENABLED=false` (default).

### 4.7 Health monitoring (P4B.8)

Per-workload-class metrics exposed via `GET /api/coe/metrics`
(already present; extended with):
- `retry_rate_per_class`
- `dead_letter_count_per_class`
- `circuit_breaker_state_per_provider`
- `queue_depth_per_class`
- `admission_p95_ms`
- `budget_headroom_usd`
- `platform_health_score` (from observability aggregator)

### 4.8 Operator controls

Admin endpoints (all flag-gated):
- `POST /api/coe/circuit-breaker/{provider}/reset` — force
  CLOSED; audited
- `POST /api/coe/queue/pause?class=<X>` — refuse new admissions for
  a class (existing in-flight work drains)
- `POST /api/coe/queue/resume?class=<X>`
- Feature flag: `COE_OPERATOR_CONTROLS_ENABLED=false` (default).

### 4.9 COE γ feature flags (all default OFF)

| Flag |
|---|
| `COE_RETRY_ENABLED` |
| `COE_DEAD_LETTER_ENABLED` |
| `COE_WORK_RECOVERY_ENABLED` |
| `COE_PROVIDER_AWARE_ADMISSION` |
| `COE_AGE_BOOST_ENABLED` |
| `COE_ELASTIC_BAND_ENABLED` |
| `COE_BUDGET_HARD_CAP_ENABLED` |
| `COE_OPERATOR_CONTROLS_ENABLED` |

### 4.10 COE γ rollback

- Every flag has a corresponding `_ENABLED=false` state.
- Dead-letter and workload_events collections are **additive** —
  disabling their flags stops future writes but preserves audit history.
- Circuit-breaker resets are audited to `coe_operator_events` for
  post-hoc review.

---

## 5. P4C — UKIE γ

### 5.1 Retrieval capabilities (P4C.1)

**New endpoint:** `POST /api/knowledge/query`

```
POST /api/knowledge/query
{
  "domain":         "strategy" | "research" | ... | null,
  "query":          "…natural language / feature keywords…",
  "top_k":          10,
  "pair":           "XAUUSD" | null,      # hard filter
  "timeframe":      "H4" | null,          # hard filter
  "min_trust_tier": 3,                    # default: domain's trust_floor
  "license_outcomes": ["permissive","weak_copyleft"]   # default
}
```

Response: ordered array of matches with `strategy_id` / `research_id`
/ ..., `similarity_score`, `similarity_reasons`, `trust_tier`,
`license`, and the guardrails object (`learning_only=true`,
`eligible_for_deploy=false`).

Zero writes. Flag-gated by `UKIE_QUERY_API_ENABLED=false` (default).

### 5.2 Ranking (P4C.2)

Two pluggable backends behind the `SimilarityBackend` protocol
already established in Phase 1.6:
- `rule_based` — canonical hash + Jaccard token overlap (already
  ships).
- `embedding` — Stage-4 addition: sentence-transformers /
  fastembed-in-process encoder over a per-domain corpus, cached in
  `strategy_knowledge_base.embedding_cache`.

Selection via `SIMILARITY_BACKEND` env (already in Phase 1.6; will be
extended to accept `"embedding"` when Stage 4 lands).

Ranking augmentation (both backends):
- `trust_tier_multiplier` — T5×1.15, T4×1.10, T3×1.00, T2×0.85,
  T1×0.65 (tunable per env).
- `license_penalty` — permissive×1.00, weak_copyleft×0.95,
  strong_copyleft×0.0 (structurally hidden), proprietary×0.0.
- `recency_boost` — items younger than 30d get ×1.10; older than
  365d get ×0.95.

Feature flag: `UKIE_RANKING_V2_ENABLED=false` (default) — when OFF,
ranking uses the Phase-1.6 rule-based baseline exactly as today.

### 5.3 Knowledge lifecycle (P4C.3)

**Retention TTL sweeper** — respects the per-domain
`default_retention_policy` declared in the Stage-3.α domain registry:
- `forever` → never expires
- `365d`, `180d`, `90d` → TTL on `inserted_at`
- `session` → cleared on each retro-score / lifecycle-sweep

Implementation: background job registered with `factory-runner`
(already in place), running every 24h under
`UKIE_LIFECYCLE_SWEEP_ENABLED=false` (default). Each expiry writes an
audit row to `strategy_knowledge_base.lifecycle_events`.

**Decay** (for the confidence evolution below): each un-touched item
in `market` (retention 365d) or `execution` (retention 180d) has its
`confidence_decay` field annotated per sweep, so retrieval can
penalise stale items without deleting them.

### 5.4 Confidence evolution (P4C.4)

Two mechanisms:

- **Endorsement events.** When retrieval returns an item and it's
  used downstream (post-promote, or referenced in an AGENT prompt),
  a `knowledge_endorsement_events` row is written. Items with
  ≥ N endorsements over rolling 30d get a `+1 tier` boost (capped at
  T5, only for items already ≥ T3).
- **Contradiction events.** When two items in the same domain
  produce contradictory findings (detected by a lightweight rule set
  or a Stage-5 AGENT task), a `knowledge_contradiction_events` row
  is written; both items get a `contested=true` flag and are
  demoted one tier for retrieval scoring.

Feature flag: `UKIE_CONFIDENCE_EVOLUTION_ENABLED=false` (default).

### 5.5 Governance extensions (P4C.5)

**Rule-based promote policy language.** Extends the Stage-3.γ hard
gate (`T4+/permissive/dedup`) with an operator-editable policy
document:

```yaml
# strategy_knowledge_base.promote_policies (Mongo doc)
policy_id: "v1"
policy_version: 1
rules:
  - name: "high-confidence auto-promote candidate"
    all_of:
      - trust_tier >= 5
      - license_outcome in ["permissive"]
      - endorsements_30d >= 3
      - contested == false
    action: "flag_as_auto_promote_candidate"
  - name: "quarantine on contradiction"
    all_of:
      - contested == true
    action: "flag_as_needs_review"
```

The `action` fields are advisory tags stored on the KB row; they do
NOT automatically call the promote bridge. All promotes remain
per-item, operator-approved (Stage 3.γ invariant preserved). This
just gives the operator a queue of "pre-vetted" candidates.

Feature flag: `UKIE_GOVERNANCE_POLICY_ENABLED=false` (default).

### 5.6 UKIE γ rollback

- Every flag is a `_ENABLED=false` flip.
- `knowledge_endorsement_events` / `knowledge_contradiction_events` /
  `lifecycle_events` are additive — disabling their flags stops
  future writes, preserves history.
- Ranking v2 flip → falls back to Phase-1.6 rule-based baseline byte-
  identically (same code path).
- No writes to production `strategies`; every Stage-4 addition lives
  in `strategy_knowledge_base`.

---

## 6. P4D — Observability Finalisation

### 6.1 UKIE health provider (P4D.1)

`GET /api/health/system` (already present; extended) gains a `ukie`
subsystem block:

```json
{
  "subsystem": "ukie",
  "status":    "healthy" | "degraded" | "failing" | "dormant",
  "flags": {
    "UKIE_DOMAIN_REGISTRY_ENABLED":   false,
    "UKIE_GOVERNANCE_CUTOVER":        false,
    "UKIE_PROMOTE_BRIDGE_ENABLED":    false,
    "UKIE_RETRO_SCORE_ENABLED":       false,
    ...
  },
  "pipeline_version":          "0.1.0",
  "pipeline_contract_version": "0.1.0",
  "kb_row_count":              <int>,
  "connector_count":           <int>,
  "connector_health":          [ ...per-connector snapshots... ],
  "recent_promote_events_24h": <int>,
  "recent_retro_score_runs_24h": <int>,
  "dry_run_verified":          true | false,
  "last_dry_run_at":           "..."
}
```

Dormant when all flags OFF (this is the STANDARD production state
until activation is approved).

Feature flag: `UKIE_HEALTH_PROVIDER_ENABLED=false` (default). When
off, the subsystem block is omitted (no shape change to existing
consumers — the aggregator returns whichever subsystems are enabled).

### 6.2 Connector health (P4D.2)

Per-connector endpoint (new):
- `GET /api/knowledge/connectors/{name}/health` — returns
  connector state, last-success timestamp, retry counts,
  auth-configured yes/no.

Aggregated view:
- `GET /api/knowledge/connectors/health` — array of all
  connectors' current health.

Both flag-gated by the connector-framework flag
(`UKIE_CONNECTOR_FRAMEWORK_ENABLED`).

### 6.3 Knowledge metrics (P4D.3)

New endpoint: `GET /api/knowledge/metrics`

- Total rows per domain
- Trust-tier distribution
- License-outcome distribution
- Rows written in last 24h / 7d / 30d
- Promote-event counts (attempted, promoted, refused, refused reasons)
- Retro-score-run counts (dry_run, commit, rollback)
- Retrieval-query counts + p95 latency (once retrieval is enabled)

Flag-gated by `UKIE_METRICS_ENABLED=false` (default).

### 6.4 Dashboard additions (P4D.4, P4D.5)

Grafana panels (added to the existing operator dashboard):

1. **UKIE state** — KB rows/domain, trust/license distributions,
   flag matrix.
2. **Connector fleet** — per-connector status LED, last-success age,
   retry rate.
3. **Promote pipeline** — attempts / promoted / refused / rollback
   over time; refuse-reason breakdown.
4. **Retro-score runs** — inserted / updated / dormant / errored
   per run; commit vs dry-run.
5. **COE γ** — retry rate, dead-letter depth, circuit-breaker states,
   queue depth, admission p95 latency, budget headroom.
6. **Subsystem health matrix** — one row per subsystem
   (COE, VIE, CTS, BI5, UKIE, Meta-Learning, MI, Execution,
   Portfolio, Factory-Eval); columns: status LED, health score,
   last-degraded-at.

All dashboards ship as JSON in `infra/grafana/dashboards/` and are
auto-provisioned via the existing Grafana provisioning path.

### 6.5 Alerting (P4D.6)

Alertmanager rules (all default off; opt-in per rule via
`ALERT_*_ENABLED`):

| Rule | Threshold | Severity |
|---|---|---|
| `platform_health_score < X` | X = 60 | HIGH |
| `budget_headroom_usd < X` | X = daily_hard_cap × 0.1 | HIGH |
| `dead_letter_depth > X` | X = 100 | MEDIUM |
| `connector_failing_count > 0` | any | MEDIUM |
| `promote_refuse_rate_1h > 50%` | | LOW |
| `admission_p95_ms > 200` | sustained 5m | MEDIUM |

### 6.6 Audit visibility endpoints (P4D.7)

- `GET /api/knowledge/promote-events?limit=&offset=&resolved=&refuse_reason=`
- `GET /api/knowledge/retro-score-runs?limit=&offset=&dry_run=`
- `GET /api/knowledge/connector-events?connector=&limit=`

All read-only. Flag-gated by `UKIE_AUDIT_VISIBILITY_ENABLED=false`
(default). Admin-only.

### 6.7 Subsystem `HealthSnapshot` retrofits (P4D.8)

New `GET /api/<subsystem>/health` endpoints for the five subsystems
that don't yet have one:
- `/api/meta-learning/health`
- `/api/mi/health`
- `/api/execution/health`
- `/api/portfolio/health`
- `/api/factory-eval/health`

Each returns a `HealthSnapshot` following the contract established
by COE / VIE / CTS. All ADDITIVE — no change to existing diagnostic
endpoints of those subsystems.

Feature flag per subsystem:
`<SUB>_HEALTH_PROVIDER_ENABLED=false` (default).

---

## 7. Cross-cutting requirements

### 7.1 Feature-flag matrix (Stage 4 additions — all default OFF)

Connector framework:
- `UKIE_CONNECTOR_FRAMEWORK_ENABLED`
- `UKIE_CONNECTOR_ARXIV_ENABLED`
- `UKIE_CONNECTOR_PDF_ENABLED`
- `UKIE_CONNECTOR_PROPFIRM_ENABLED`
- `UKIE_CONNECTOR_TRADINGVIEW_ENABLED`
- `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED`
- `UKIE_CONNECTOR_GITHUB_ENABLED`
  (existing connector, now under the same flag pattern for uniformity)

COE γ:
- `COE_RETRY_ENABLED`
- `COE_DEAD_LETTER_ENABLED`
- `COE_WORK_RECOVERY_ENABLED`
- `COE_PROVIDER_AWARE_ADMISSION`
- `COE_AGE_BOOST_ENABLED`
- `COE_ELASTIC_BAND_ENABLED`
- `COE_BUDGET_HARD_CAP_ENABLED`
- `COE_OPERATOR_CONTROLS_ENABLED`

UKIE γ:
- `UKIE_QUERY_API_ENABLED`
- `UKIE_RANKING_V2_ENABLED`
- `UKIE_LIFECYCLE_SWEEP_ENABLED`
- `UKIE_CONFIDENCE_EVOLUTION_ENABLED`
- `UKIE_GOVERNANCE_POLICY_ENABLED`

Observability:
- `UKIE_HEALTH_PROVIDER_ENABLED`
- `UKIE_METRICS_ENABLED`
- `UKIE_AUDIT_VISIBILITY_ENABLED`
- `META_LEARNING_HEALTH_PROVIDER_ENABLED`
- `MI_HEALTH_PROVIDER_ENABLED`
- `EXECUTION_HEALTH_PROVIDER_ENABLED`
- `PORTFOLIO_HEALTH_PROVIDER_ENABLED`
- `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED`
- Per-alert `ALERT_<NAME>_ENABLED`

**Every flag defaults OFF. Nothing is enabled in production by this
plan.**

### 7.2 Rollback SLA (§5.2 style, Stage-4 rollups)

| Rollback path | Target SLA |
|---|---|
| Connector opt-out | ~30s (flag flip + supervisor restart) |
| Nuclear per-connector deletion | seconds (`deleteMany({connector_name})`) |
| Retry / dead-letter / circuit-breaker capability | ~30s (flag flip) |
| Ranking v2 fallback to v1 baseline | ~30s (flag flip; ranker swap) |
| Lifecycle sweeper stop | ~30s (flag flip; TTL indexes remain but sweeper doesn't run) |
| Governance policy revoke | seconds (delete `promote_policies` doc; policy engine returns to "no policies") |
| Health provider disable | ~30s (flag flip; subsystem block omitted from aggregator) |
| Alert rule mute | seconds (Alertmanager reload) |
| Nuclear Stage-4 rollback | supervisor restart with **all** Stage-4 flags cleared → the platform reverts to post-Stage-3.γ posture byte-identically |

All continue to meet the 60-s platform SLA
(`PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §3 invariant #2`).

### 7.3 Backward compatibility

- No shape change to any Stage-1..3 endpoint response.
- Additive `HealthSnapshot` blocks in `/api/health/system` — existing
  consumers ignore unknown keys per JSON convention.
- Every new Mongo collection is created lazily on first write.
- No index migrations required on existing collections; new
  collections declare their own indexes on first write via a
  bootstrap helper.

### 7.4 Distribution readiness

- All Stage-4 additions rely on the existing shared Mongo connection
  pool (`engines.db.get_db`) — no new client, no new driver.
- The `WorkloadQueue` interface (already Protocol-based) is unchanged.
- Ranking-v2 encoder runs in-process by default; a distributed
  encoder is a future Phase-5 concern and is out of scope here.
- Connectors are Protocol-based; a distributed worker pod can host
  any subset of connectors — no code changes required.

### 7.5 Hard-rail invariants (preserved)

- Every UKIE-KB write remains `learning_only=True`,
  `eligible_for_deploy=False`. Stage 4 does NOT introduce any new
  writer that flips those bits.
- The Stage-3.γ promote bridge remains the ONLY path from KB to
  production `strategies`; Stage-4 retrieval + ranking are read-only.
- Legacy `ingested_strategies` remains READ-ONLY.

---

## 8. Validation Gate 5

### 8.1 Objectives

Confirm that Stage 4 is:
1. Fully implemented (all four workstreams).
2. All flags default OFF; the flag-off state is byte-identically the
   post-Stage-3.γ posture.
3. Every new endpoint returns HTTP 503 (or 404) when its master flag
   is off.
4. Every new capability has a passing test suite; the cumulative
   Phase-2 + Phase-4 test count is 100% clean.
5. Rollback paths are TESTED, not just declared.
6. Observability provides sufficient signal to detect degradation
   within the platform-health SLA.

### 8.2 Test strategy

- **Unit tests per component:**
  - Connector scaffolding + each of the 5 concrete connectors
    (target: ≥ 6 tests each, ≥ 30 total).
  - COE γ: retry (5), dead-letter (5), work-recovery (4),
    provider-aware admission (4), age-boost (3), elastic band (3),
    budget hard-cap (3), operator controls (3) → ≥ 30 tests.
  - UKIE γ: query API (5), ranking v2 (6), lifecycle (4),
    confidence evolution (4), governance policy (4) → ≥ 23 tests.
  - Observability: UKIE health (3), connector health (3), knowledge
    metrics (3), health retrofits × 5 subsystems (2 each = 10),
    audit visibility (3) → ≥ 22 tests.
  - **Total new tests target: ≥ 105.**

- **Integration tests** (backend live + Mongo):
  - End-to-end connector fetch → pipeline → KB write with all flags
    on (in a test env only).
  - End-to-end retrieval `POST /api/knowledge/query` against a
    seeded KB → correct ordering + guardrails.
  - Retry → success flow (mock provider that fails N-1 times).
  - Retry → dead-letter → requeue → success flow.
  - Circuit-breaker: force OPEN → task refused → VIE reroute →
    circuit closes.

- **Regression:** all 181 pre-Stage-4 UKIE + BI5 unit tests remain
  passing; the pre-existing integration suites (Phase A–J) remain at
  their Gate-3 baseline pass rate.

- **Load test:** 100 concurrent P0 requests under `pressure_band=high`
  see p95 admission latency < 200 ms (identical target as Stage 4
  §8.4 in the master plan).

### 8.3 Rollback strategy (per stage-4 workstream)

Documented in §7.2 above. Every path is a flag flip **or** a targeted
`deleteMany` filter that only matches Stage-4-produced rows. The
nuclear rollback (flip every Stage-4 flag off + supervisor restart)
returns the platform to byte-identical post-Stage-3.γ posture.

### 8.4 Production activation plan

**Stage 4 activation is a sequenced, review-gated rollout — not a
big-bang flip.** The order is:

**Phase A — Observability first (safe, read-only)**
1. `UKIE_HEALTH_PROVIDER_ENABLED=true`
2. Per-subsystem `<SUB>_HEALTH_PROVIDER_ENABLED=true`
3. `UKIE_METRICS_ENABLED=true`
4. `UKIE_AUDIT_VISIBILITY_ENABLED=true`
5. Grafana dashboards go live; alerts remain silent for 24h to
   establish baselines.

**Phase B — COE γ resilience (safe when properly gated)**
6. `COE_RETRY_ENABLED=true`
7. `COE_DEAD_LETTER_ENABLED=true`
8. `COE_WORK_RECOVERY_ENABLED=true`
9. `COE_PROVIDER_AWARE_ADMISSION=true`
10. `COE_AGE_BOOST_ENABLED=true`
11. `COE_BUDGET_HARD_CAP_ENABLED=true`
12. `COE_ELASTIC_BAND_ENABLED=true`
13. `COE_OPERATOR_CONTROLS_ENABLED=true`
    Each flag flipped one at a time; observe for 24h before the next.

**Phase C — UKIE γ retrieval (still writes-off in KB)**
14. `UKIE_QUERY_API_ENABLED=true`
15. `UKIE_LIFECYCLE_SWEEP_ENABLED=true` (respects retention policies)
16. `UKIE_RANKING_V2_ENABLED=true`
17. `UKIE_CONFIDENCE_EVOLUTION_ENABLED=true`
18. `UKIE_GOVERNANCE_POLICY_ENABLED=true`

**Phase D — Connector fleet (new writers to KB)**
19. Confirm Coherent UKIE Activation (Gate 3 §13) has completed —
    ie `UKIE_DOMAIN_REGISTRY_ENABLED=true`,
    stage flags on, `UKIE_GOVERNANCE_CUTOVER=true`.
    **If Coherent UKIE Activation has NOT happened, connector
    activation is BLOCKED.**
20. `UKIE_CONNECTOR_FRAMEWORK_ENABLED=true`
21. Per-connector flags flipped one at a time in the order
    `INTERNAL_MONGO → ARXIV → PDF → PROPFIRM → TRADINGVIEW`. Observe
    each for ≥ 24h; verify KB row counts increase; verify no writes
    to production `strategies`.

**Phase E — Alerting**
22. `ALERT_*_ENABLED=true` per alert rule, after the 24h baseline
    window in Phase A has produced usable thresholds.

At every phase, `/api/health/system` remains the source of truth for
"is the platform healthy". The operator may pause / roll back at any
phase without disturbing earlier ones.

### 8.5 Gate 5 pass criteria (checklist)

- [ ] All Stage-4 flags default OFF; production posture unchanged
- [ ] Full Stage-4 test suite passing (≥ 105 new tests) alongside the
      181 pre-existing UKIE + BI5 tests
- [ ] Every new endpoint returns HTTP 503 when its master flag is off
- [ ] Nuclear rollback proven: enable every Stage-4 flag in preview →
      disable → platform returns to byte-identical Stage-3.γ posture
- [ ] Grafana dashboards render all six panels with realistic data
- [ ] `/api/health/system` returns ≥ 10 subsystem blocks
      (existing 3 + UKIE + 5 retrofitted subsystems), each with a
      valid `HealthSnapshot`
- [ ] Every connector dry-runs against ≥ 3 references
- [ ] Retrieval query returns correctly ordered results honouring
      trust / license / recency ranking augmentations
- [ ] Retry / dead-letter / circuit-breaker flows verified end-to-end
      in preview
- [ ] Legacy `ingested_strategies` invariant verified: zero writes
      before AND after Stage 4 activation
- [ ] Production `strategies` invariant verified: no non-promote
      writes before AND after Stage 4 activation
- [ ] Documentation complete: `PHASE_4_STAGE_4_NOTES.md` +
      `PHASE_4_VALIDATION_GATE_5_REPORT.md`

---

## 9. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | A connector writes items with `learning_only=false` or `eligible_for_deploy=true` | LOW | Hard rails re-stamped at `KnowledgeRepository._build_doc` (Stage-3.β); Stage-4 does not add a new writer that touches those fields; regression test on the repo shape |
| R2 | Ranking v2 hides high-trust items behind a mis-calibrated multiplier | MEDIUM | Ranking v2 is flag-gated; when off the exact Phase-1.6 baseline runs; A/B comparison endpoint (`POST /api/knowledge/query?compare=v1,v2`) available during Phase-C rollout |
| R3 | Lifecycle sweeper deletes items still under active use | LOW | Sweeper respects the per-domain `default_retention_policy` (which defaults to `forever` for STRATEGY / RESEARCH / INDICATOR / INTERNAL_HISTORY); every deletion writes an audit row with pre-image; sweeper's flag can be flipped off within 30s |
| R4 | Circuit breaker false-positive keeps LLM traffic blocked | MEDIUM | `POST /api/coe/circuit-breaker/{provider}/reset` (operator controls) restores immediately; HALF_OPEN probes automatically re-close on success |
| R5 | Dead-letter grows unbounded | MEDIUM | TTL index (default 90d); operator dashboard shows count; alert rule at depth > 100 |
| R6 | Retro-fitted subsystem HealthSnapshots break their existing diagnostic endpoints | LOW | Additive by contract — `/api/<sub>/health` is a NEW route; existing routes untouched; test asserts no route collisions |
| R7 | Governance policy engine auto-promotes items | LOW | Policy actions are ADVISORY (`flag_as_auto_promote_candidate`) — no automated call to the promote bridge; every promote remains per-item, operator-approved (Stage 3.γ invariant preserved) |
| R8 | A connector's secret leaks in logs | LOW | Auth resolver reads from env; grep-based test asserts no secret substring ever appears in loguru captures; `str()` implementations of auth objects redact |
| R9 | Retrieval endpoint returns raw payloads that violate a domain's `ai_context_policy` | LOW | `POST /api/knowledge/query` never returns `content_bytes` when the domain policy is `summary` / `off`; only metadata + evaluation blocks |
| R10 | Coherent UKIE Activation blocked because connectors are enabled before governance cutover | MEDIUM | Phase-D activation gates on `UKIE_GOVERNANCE_CUTOVER=true`; per-connector flag enable in `admission_gate` refuses when the cutover is off; test asserts the guard |

**No CRITICAL risks. R2, R4, R5, R10 are the only MEDIUM.**

---

## 10. Estimated milestones

Assumes one engineer per workstream, parallelisable.

| Workstream | Focused days (serial) | With parallel (2–5 engineers) |
|---|---|---|
| P4A Connector scaffolding + 5 connectors | 8 | 3 (5 engineers on connectors + 1 on scaffold) |
| P4B COE γ (8 sub-items) | 6 | 4 (2 engineers) |
| P4C UKIE γ (5 sub-items) | 5 | 3 (2 engineers) |
| P4D Observability (7 sub-items) | 4 | 3 (2 engineers) |
| Test authoring + regression | 3 | 2 |
| Documentation + Gate 5 report | 2 | 2 |
| **Total** | **28 days serial** | **~10 days with parallel tracks** |

A 20% buffer (~2 days on the parallel track) is prudent for
integration surprises.

---

## 11. Ask of operator

Please confirm the plan is approved before any code lands. If
approved, next-turn output would be:

1. Implement P4A.0 (connector scaffolding) + tests
2. Implement P4A.1..5 (five connectors) in parallel + tests
3. Implement P4B.1..8 (COE γ) + tests
4. Implement P4C.1..5 (UKIE γ) + tests
5. Implement P4D.1..8 (observability) + tests
6. Produce `PHASE_4_STAGE_4_NOTES.md`
7. Produce `PHASE_4_VALIDATION_GATE_5_REPORT.md`
8. Await approval before enabling any Stage-4 flag in production
9. Sequenced activation per §8.4 phases A → E, one flag at a time,
   with 24h observation windows

**No code changes will be made until this plan is signed off.**
**Production posture remains: all UKIE + Stage-3.γ + Stage-4 flags
OFF.**
**Coherent UKIE Activation remains BLOCKED until you explicitly
approve it separately.**

---

*Reviewed against:*
- `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §6.4, §10.4, §11`
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §5 P2C.10, §6 P2C.12–15,
   §8 connectors`
- `PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md §COE γ`
- `PHASE_2_STAGE_3_ALPHA_NOTES.md` (connector Protocol foundation)
- `PHASE_2_STAGE_3_BETA_NOTES.md` (pipeline + governance cutover)
- `PHASE_2_STAGE_3_GAMMA_NOTES.md` (Promote Bridge + Retro-scoring —
   the writer surfaces this plan builds on)
- `PHASE_2_VALIDATION_GATE_3_REPORT.md` (Gate 3 pass; post-approval
   sequence)
- `PHASE_2_VALIDATION_GATE_4_REPORT.md` (Stage 3.γ approved)

*Status:* **Awaiting operator approval to begin Stage 4 implementation.**
