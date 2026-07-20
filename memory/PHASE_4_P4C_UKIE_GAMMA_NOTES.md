# Phase 4 Stage 4 — P4C UKIE γ: Implementation Notes

> **Status:** IMPLEMENTED, tested, dormant.
> All P4C feature flags default OFF. Zero production behaviour change.
> Landed: 2026-07-20.
> Preceded by: `PHASE_4_MASTER_PLAN.md §5` (operator-approved).
> Cumulative Phase-2 + P4A + P4B + P4C unit tests: **302 / 302 passing**
> (275 prior + 27 new for P4C).

---

## 1. What landed

All five sub-milestones from PHASE_4_MASTER_PLAN §5 delivered as
additive modules inside `engines/knowledge/`. Nothing in Stage 3.α/β/γ
was modified — the modules compose alongside via `router.py`'s
sub-router mounting pattern.

### 1.1 Modules added

| Component | File | Purpose |
|---|---|---|
| **P4C.1** Retrieval | `retrieval.py` | Read-only ranking-aware query engine over `strategy_knowledge_base` |
| **P4C.2** Ranking v2 | `ranking.py` | Layered multipliers (trust × license × recency × contested × endorsement) over base similarity |
| **P4C.3** Lifecycle sweeper | `lifecycle.py` | Retention TTL + decay annotation per-domain |
| **P4C.4** Confidence evolution | `confidence.py` | Endorsement + contradiction event stores |
| **P4C.5** Governance policy | `governance_policy.py` | Advisory rule engine (`auto_promote_candidate`, `needs_review`) — **never** calls the promote bridge |
| — | `ukie_gamma_router.py` | Endpoint surface |
| — | `test_ukie_gamma.py` | 27 tests |

### 1.2 New endpoints (all self-guard HTTP 503 when flag off)

| Method | Path | Flag |
|---|---|---|
| `POST` | `/api/knowledge/query` | `UKIE_QUERY_API_ENABLED` |
| `POST` | `/api/knowledge/lifecycle-sweep` | `UKIE_LIFECYCLE_SWEEP_ENABLED` |
| `POST` | `/api/knowledge/endorsement` | `UKIE_CONFIDENCE_EVOLUTION_ENABLED` |
| `POST` | `/api/knowledge/contradiction` | `UKIE_CONFIDENCE_EVOLUTION_ENABLED` |
| `POST` | `/api/knowledge/governance/evaluate/{kb_id}` | `UKIE_GOVERNANCE_POLICY_ENABLED` |

Total `/api/knowledge/*` routes: **25** (5 new + 20 pre-existing).

### 1.3 Per-component notes

**P4C.1 Retrieval API.** `POST /api/knowledge/query` accepts
`domain`, `query`, `top_k`, `pair`, `timeframe`, `min_trust_tier`,
`license_outcomes`. Returns ordered matches with per-item ranking
breakdown. **Never returns `content_bytes`.** Domain policy is
enforced at response composition:
* `summary` / `off` → `content_preview = None`
* `quote` / `verbatim` → truncated (≤ 280 chars) `content_preview`

Default licence whitelist: `["permissive", "weak_copyleft"]` (matches
the Stage-3.γ promote gate).

**P4C.2 Ranking v2.** Layered multipliers:

| Factor | Multiplier |
|---|---|
| trust_tier=5 | ×1.15 |
| trust_tier=4 | ×1.10 |
| trust_tier=3 | ×1.00 |
| trust_tier=2 | ×0.85 |
| trust_tier=1 | ×0.65 |
| license permissive | ×1.00 |
| license weak_copyleft | ×0.95 |
| **license strong_copyleft** | **×0.00 (structurally hidden)** |
| **license proprietary** | **×0.00 (structurally hidden)** |
| license unknown | ×0.85 |
| age < 30d | ×1.10 |
| age > 365d | ×0.95 |
| contested=true | ×0.80 |
| endorsements_30d | ×(1.0 + 0.02 × N), capped at +20 % |

When `UKIE_RANKING_V2_ENABLED=false`, every multiplier collapses to
1.0 — `final_score == base_similarity`, byte-identical to Phase-1.6.
Reasons list is surfaced for operator debug
(`ranking_v2_disabled`, `license_zeroed:proprietary`, `contested_penalty`,
`endorsement_boost_N`, `recency_young`, `recency_stale`).

**P4C.3 Lifecycle sweeper.** Per-domain retention respected from the
Stage-3.α registry:
* `forever` → nothing expires
* `365d` → market
* `180d` → execution
* `session`, `90d`, other — supported

Decay annotation (§5.3): items in `market` / `execution` that survive
a sweep get `confidence_decay` = `min(1.0, age_s / policy_s)` set on
the row so retrieval can penalise stale items without deleting.

Every sweep produces:
* One `SweepSummary` with per-domain counts (`scanned`, `deleted`,
  `decayed`) — returned in the HTTP response.
* One audit event per (domain, run) in `lifecycle_events` when
  `dry_run=false`.

`annotate_decay_only=true` short-circuits deletion — a completely
safe mode for the operator to bootstrap decay markers before enabling
real deletion.

**P4C.4 Confidence evolution.**
* `record_endorsement(kb_id, domain, source, context)` — one row in
  `knowledge_endorsement_events`.
* `endorsements_last_30d(kb_id)` — count queried by ranking-v2 (via
  the injected `endorsements_30d` kwarg to `compose`).
* `record_contradiction(domain, kb_id_a, kb_id_b, reason, reported_by)`
  — writes one `knowledge_contradiction_events` row AND stamps
  `contested=true` on both KB rows. Ranking-v2 then applies the ×0.80
  penalty.

Flag off: every method returns `{"status": "flag_off"}` and does not
touch Mongo.

**P4C.5 Governance policy language.** Operator-authored rules in
`strategy_knowledge_base.promote_policies` (latest by
`policy_version`). Each rule declares `all_of` conditions and one
`action` string:

Supported operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`.
Supported fields: `trust_tier`, `license_outcome` (alias for
`license_verdict.outcome`), `endorsements_30d`, `contested`,
`extras.*`, plus any other row-level field via direct read.

**Actions are advisory only:**
* Stamped on the KB row via `advisory_tags` array (e.g.
  `["flag_as_auto_promote_candidate"]`).
* NEVER trigger an automatic promote call. Stage-3.γ invariant
  (per-item, operator-approved) preserved.

`write_verdict()` only sets `advisory_tags`, `governance_policy_id`,
`governance_policy_version`. It NEVER touches `trust_tier`,
`license`, `learning_only`, or `eligible_for_deploy`.

### 1.4 Files added / modified

Added (7 files):
- `backend/legacy/engines/knowledge/ranking.py`
- `backend/legacy/engines/knowledge/retrieval.py`
- `backend/legacy/engines/knowledge/lifecycle.py`
- `backend/legacy/engines/knowledge/confidence.py`
- `backend/legacy/engines/knowledge/governance_policy.py`
- `backend/legacy/engines/knowledge/ukie_gamma_router.py`
- `backend/tests/test_ukie_gamma.py` (27 tests)

Modified (2 files):
- `backend/legacy/engines/knowledge/router.py` — mounts
  `ukie_gamma_router` alongside the existing `promote_router` /
  `retro_score_router` / `connector_router`.
- `backend/legacy/engines/knowledge/__init__.py` — new exports.

---

## 2. Feature-flag matrix

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_QUERY_API_ENABLED` | `false` | `/api/knowledge/query` served (else 503) |
| `UKIE_RANKING_V2_ENABLED` | `false` | Layered multipliers active; when off, `final_score == base_similarity` byte-identically |
| `UKIE_LIFECYCLE_SWEEP_ENABLED` | `false` | `/api/knowledge/lifecycle-sweep` served + sweep can delete/decay |
| `UKIE_CONFIDENCE_EVOLUTION_ENABLED` | `false` | Endorsement + contradiction stores active; `contested=true` gets stamped |
| `UKIE_GOVERNANCE_POLICY_ENABLED` | `false` | Policy evaluator returns non-empty verdicts; `advisory_tags` stamped by `write_verdict()` |

**Every flag defaults OFF.** Zero production behaviour change.

---

## 3. Rollback SLA

| Rollback path | Mechanism | Target SLA |
|---|---|---|
| Query API disable | `UKIE_QUERY_API_ENABLED=false` + restart | ~30s |
| Ranking-v2 disable | `UKIE_RANKING_V2_ENABLED=false` | ~30s → base similarity returns; matches unchanged |
| Lifecycle disable | `UKIE_LIFECYCLE_SWEEP_ENABLED=false` | ~30s → sweep no-op, TTL indexes preserved for audit |
| Confidence disable | `UKIE_CONFIDENCE_EVOLUTION_ENABLED=false` | ~30s → collections untouched |
| Governance disable | `UKIE_GOVERNANCE_POLICY_ENABLED=false` | ~30s → advisory tags remain stamped but ignored |
| Nuclear P4C rollback | Flip all 5 flags off + restart | ~60s → platform returns to post-P4B posture |

---

## 4. Cumulative test status

```
tests/test_knowledge_*                     · PASS (Stage 3.α/β/γ)
tests/test_bi5_bid_diff.py                 · PASS (Stage 2 shadow)
tests/test_promote_bridge.py               · PASS (Stage 3.γ)
tests/test_retro_score.py                  · PASS (Stage 3.γ)
tests/test_connector_scaffolding.py        · PASS (P4A)
tests/test_connectors_stage4.py            · PASS (P4A)
tests/test_coe_gamma.py                    · PASS (P4B)
tests/test_ukie_gamma.py                   · PASS (P4C — new, 27 tests)
──────────────────────────────────────────────────────────
Cumulative UKIE + BI5 + Stage-4 P4A + P4B + P4C: 302 / 302 PASSING
```

Test-count evolution:
- Pre-P4A: 181
- After P4A: 239 (+58)
- After P4B: 275 (+36)
- **After P4C: 302 (+27)**

Per-component coverage:
- Ranking (7) · Rule-based similarity (3) · Retrieval engine (5) ·
  Lifecycle (3) · Confidence (3) · Governance policy (4) · Router (2)

---

## 5. Architectural recommendations before proceeding to P4D

1. **Retrieval is DB-scan today; encoder path deferred.** The
   `RetrievalEngine` iterates each domain sub-collection with a
   Mongo `find(...)` + in-process similarity computation. For KB
   sizes < 100k rows this is plenty; when the KB grows, an
   embedding backend + ANN index (fastembed / pgvector /
   in-Mongo `$vectorSearch`) plugs into the same
   `similarity_fn` injection port with no API change. Recommend
   deferring to Phase 5 unless corpus grows past ~50k.
2. **`content_preview` is bounded at 280 chars.** This matches
   Twitter-length quotable excerpt norms and stays well below any
   licence-quotation concerns. Do NOT raise without a governance
   review.
3. **Lifecycle sweeper needs a scheduler hook.** The module runs
   on-demand via `POST /api/knowledge/lifecycle-sweep`. Wiring it
   to `factory-runner` for a 24h cadence is a one-line schedule
   registration at activation time — kept out of P4C to preserve
   "no timers auto-start" invariant.
4. **Governance policies live in Mongo, not code.** The operator
   authors + edits `promote_policies` documents at activation
   time. Recommend versioning policies in a git-tracked YAML
   under `docs/policies/` and syncing on deploy (Stage 5 concern;
   not blocking).
5. **Ranking's zero-multiplier for `strong_copyleft` /
   `proprietary` is structural.** Even if a caller passes
   `license_outcomes=["proprietary"]` to `POST /query`, the ranker
   still returns `final_score=0.0` → the item is filtered by the
   post-sort truncation. This is intentional defence-in-depth
   against operator mistake; the caller-boundary whitelist is a
   second layer.
6. **Content-preview inclusion depends on the domain's
   `ai_context_policy`.** `summary` / `off` never leak text;
   `quote` / `verbatim` return truncated previews. This aligns
   with the Stage-3.α domain-registry contract. If a new domain
   is added with policy `off`, retrieval automatically respects
   it without code changes.

**Recommendation:** proceed to **P4D — Observability Finalisation**
(UKIE health provider · connector health persistence · knowledge
metrics · dashboards · alerts · audit visibility). P4C leaves the
platform in a clean state; nothing in P4D touches retrieval or
ranking surfaces.

---

## 6. Explicit non-goals maintained

- **No automatic promote calls.** Every governance action is
  advisory only. Stage-3.γ per-item, operator-approved discipline
  is preserved intact.
- **No writes to production `strategies`.** Every P4C write goes
  into `strategy_knowledge_base` sub-collections.
- **No writes to legacy `ingested_strategies`.**
- **No mutation of trust_tier or license fields by policy engine.**
- **No encoder / ANN index.** Deferred to Phase 5.
- **No auto-scheduled sweeper.** On-demand via endpoint only until
  the operator wires `factory-runner` at activation time.

---

## 7. Live-verification checklist (operator, when ready)

Preview pod, all P4C flags OFF (default):
- [ ] `POST /api/knowledge/query {"query": "regime"}` → 503
- [ ] `POST /api/knowledge/lifecycle-sweep {}` → 503
- [ ] `POST /api/knowledge/endorsement {...}` → 503
- [ ] `POST /api/knowledge/contradiction {...}` → 503
- [ ] `POST /api/knowledge/governance/evaluate/kb-1 {"domain":"strategy"}` → 503

With `UKIE_QUERY_API_ENABLED=true` (only):
- [ ] `POST /api/knowledge/query` returns `{status:"ok", matches:[...]}`
- [ ] Every match carries `learning_only=true`, `eligible_for_deploy=false`
- [ ] `content_preview` is null for `research` / `market` /
      `internal_history` (summary policy)
- [ ] Ranking `final_score == similarity_score` when
      `UKIE_RANKING_V2_ENABLED=false`

With `UKIE_RANKING_V2_ENABLED=true`:
- [ ] `final_score` shifts per multiplier
- [ ] Any `proprietary` / `strong_copyleft` item is filtered
      (multiplier 0.0)

With `UKIE_LIFECYCLE_SWEEP_ENABLED=true` (dry-run first):
- [ ] `POST /api/knowledge/lifecycle-sweep {"dry_run":true}` reports
      per-domain scanned/deleted/decayed with `dry_run=true`; zero
      audit events land.
- [ ] `POST /api/knowledge/lifecycle-sweep {"dry_run":false}` actually
      deletes and stamps one `lifecycle_events` row per (domain, run).

With `UKIE_CONFIDENCE_EVOLUTION_ENABLED=true`:
- [ ] Endorsement recorded; `endorsements_last_30d` increases.
- [ ] Contradiction recorded → both target KB rows carry
      `contested=true`.

With `UKIE_GOVERNANCE_POLICY_ENABLED=true`:
- [ ] Seed a policy in `promote_policies`.
- [ ] `POST /api/knowledge/governance/evaluate/{kb_id} {"domain":"strategy","write":false}` returns matched rules + actions; no KB mutation.
- [ ] With `write=true` — KB row now carries
      `advisory_tags` + `governance_policy_id`; trust_tier / license /
      hard-rail flags UNCHANGED.

Rollback:
- [ ] Flip every P4C flag → false + restart → every P4C endpoint
      returns 503; retrieval, ranking, lifecycle, confidence,
      governance all inert. Post-P4B posture restored byte-identically.

---

*Status:* **P4C implemented, tested, dormant. Awaiting operator signal
to proceed to P4D — Observability Finalisation.**
