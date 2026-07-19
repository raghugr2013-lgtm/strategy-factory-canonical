# Phase 1.6 — Knowledge Engine Architecture ✅ COMPLETE

Delivered as a self-contained subsystem at ``backend/app/knowledge/``.
Every improvement below is implemented, wired, tested, and live on the
running backend at ``/api/knowledge/*``.

## What shipped

### A. Repository Safety (highest priority) ✅
New file: ``app/knowledge/repository.py``

- **``StrategyRepository``** — production reads. ``find`` / ``find_one`` /
  ``count_documents`` transparently inject
  ``{"eligible_for_deploy": True}`` into every filter. Attempting to
  override the guard (``find({"eligible_for_deploy": False})``) raises
  ``_ImmutableError`` — the caller must use ``KnowledgeRepository``
  instead. Writes pass through untouched (write-side safety is a
  governance concern).

- **``KnowledgeRepository``** — historical KB reads. Every read injects
  ``{"learning_only": True}``; ``aggregate`` transparently prepends a
  ``$match: {learning_only: true}`` stage so aggregation pipelines
  can't escape the guard. **Every mutation method
  (``insert_one``, ``insert_many``, ``update_one``, ``update_many``,
  ``delete_one``, ``delete_many``, ``replace_one``) raises
  ``_ImmutableError``.**

Both repositories are ~150 LoC of thin pymongo wrappers — the audit
surface is tiny and obvious in code review.

### B. Canonical Strategy Identity ✅
New file: ``app/knowledge/canonical.py``

- **``canonical_hash(strategy_text, parameters)``** — deterministic,
  side-effect-free 16-hex fingerprint. Collapses constants (numbers →
  ``N``), scrubs provenance annotations (``DERIVED FROM:``,
  ``SOURCE:``, ``ORIGIN:``), folds the *sorted parameter-key set* into
  the hash but ignores parameter *values* (those are already collapsed
  in the text).
- **``normalise_strategy_text``** — public helper exposing the same
  normalisation for display / debugging.

Used for: duplicate detection, near-duplicate analysis, family
clustering, mutation genealogy, knowledge retrieval — as specified.

### C. Evaluation Model ✅
New file: ``app/knowledge/evaluation.py``

Replaces the collapsed legacy ``verdict`` with **six independent
dimensions**:

| Dimension | Type | Meaning |
|---|---|---|
| `profitability` | 0..100 | PF (60%) + total-return (40%) |
| `robustness` | 0..100 | Stability; −30% if no OOS holdout |
| `overfit_risk` | 0..100 | Higher = worse. From legacy `overfit` if present, else `100 - stability` |
| `deployment_readiness` | enum | `not_ready | pending_validation | needs_oos_holdout | ready` |
| `confidence` | 0..100 | Evidence strength (trades + OOS) |
| `pass_probability` | 0..100 | Historical estimator — flagged §A4 as untrusted until re-verified |

**The evaluator structurally cannot emit `READY`.** A test locks this
invariant (`test_evaluation_never_awards_ready`) — only the current-
framework governance pipeline can promote to READY, and only after a
live re-validation pass. Historical KB entries max out at
`pending_validation` / `needs_oos_holdout`.

### D. Strategy Memory ✅
Achieved by the module layout itself — ``app/knowledge/`` is the
Strategy Memory subsystem:

| File | Role |
|---|---|
| `canonical.py` | Structural identity (fingerprinting) |
| `evaluation.py` | Split-dimension scoring |
| `similarity.py` | Pluggable retrieval backends |
| `repository.py` | Safety-first access layer |
| `router.py` | HTTP surface |
| `tests/test_safety.py` | Locks the 3 core invariants |

Ready to grow: similarity search ✓, mutation lineage (via `families`
endpoint) ✓, family clustering ✓, historical failure analysis
(evaluation.overfit_risk × pnl decomposition) ✓, champion history ✓,
reasoning support (matches carry `similarity_reasons: [str]` explaining
why each result surfaced).

### E. Knowledge API ✅
New file: ``app/knowledge/router.py`` — mounted at ``/api/knowledge``.

| Endpoint | Purpose |
|---|---|
| `POST /nearest` | Top-k similar KB entries — the flagship endpoint |
| `GET /families/{canonical_hash_key}` | Retrieve a canonical family |
| `GET /champions` | Champion strategies from Phase 1.5 analysis |
| `GET /statistics` | High-level KB metrics for dashboards |
| `GET /strategy/{strategy_id}` | Detail view of one KB entry |
| `GET /health` | Cheap KB reachability probe |

**API-contract stability guarantee** for the embedding-backend upgrade:
`SimilarityBackend` is a `Protocol`; the response envelope is
`NearestResponse` with a fixed `matches: [SimilarityMatchOut]` array
that contains no backend-specific fields. When embeddings land, callers
notice only a change in the top-level `backend` field name.

Backend selection is `SIMILARITY_BACKEND=rule_based|embedding` (env
var), defaulting to `rule_based`. An `EmbeddingSimilarityStub` is
already in the class hierarchy so the wire-up is a one-line change
when Phase 2 lands.

## Verification (all live on the local stack + isolated KB)

| Check | Result |
|---|---|
| Backend restart | Clean; `mounted knowledge router: /api/knowledge/*` in logs |
| Total OpenAPI paths | **616 → 622** (+6 net; some paths already existed under a legacy knowledge router) |
| Legacy mount unchanged | ✅ still 101 routers |
| Zero new runtime errors | ✅ (checked backend.err.log) |
| `/api/knowledge/health` | 200 · `corpus_size=140` · `backend=rule_based_v1` · `readiness_ceiling=pending_validation` |
| `/api/knowledge/statistics` | 200 · `132 families` · `39 positive-PF candidates` |
| `/api/knowledge/nearest` (ATR breakout query) | 200 · top hit 80% text overlap + 33% param overlap, correctly ranked · guardrails on every row |
| `/api/knowledge/families/{multi-hash}` | 200 · returns family members with size |
| `/api/knowledge/families/deadbeef` | 404 (correct) |
| `/api/knowledge/strategy/{id}` | 200 · full split evaluation payload |
| `/api/knowledge/nearest` with empty text | 422 (correct schema validation) |
| **Safety tests** — `pytest app/knowledge/tests/test_safety.py` | **14/14 PASS** |

## What is deliberately NOT done (per your directives)

- ❌ No path from KB to deployment. `eligible_for_deploy=False` at row level; readiness ceiling `pending_validation` at evaluator level.
- ❌ No auto-promotion. Every KB row still requires a fresh cold-insert through the current-framework strategies API.
- ❌ No changes to production governance rules. Governance code untouched. Only `app/main.py` gained one 6-line mount block.

## Backlog / P1 wired to unblock cleanly

1. **Adopt `StrategyRepository` in `app/api/strategies.py`.** Currently the strategies router still calls `db.strategies.find(...)` directly. Wrapping it in `StrategyRepository` closes the last "someone forgot the filter" path. ~10 LoC change to the read sites in that file. Ready to do next.

2. **Embedding backend**. Two-file change once AI provider keys are live: (a) fill in `EmbeddingSimilarityStub.rank` in `similarity.py`, (b) flip `SIMILARITY_BACKEND=embedding` in prod `.env`. Zero contract change.

3. **Add `canonical_hash` to new strategy inserts** on `strategies_router` so the current framework's `strategy_library` also gets first-class family clustering. One line in the create handler.
