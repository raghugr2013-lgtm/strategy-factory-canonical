# AI Learning Layer — v1.1.1 Architecture Proposal

**Status:** Design (not yet implemented). Additive on top of the frozen v01 architecture — no legacy engine is removed.

**Objective:** Turn the 2,080 recovered strategy documents (14 Library + 126 Archive + 892 Lifecycle History + 1,047 Performance History + 1 base strategy) into a queryable knowledge base that every future AI generation call automatically consults. Recovered strategies remain **non-production** — they inform the AI, they do not trade.

---

## 1. Design Constraints (from the user directive)

- Recovered strategies are **learning data**, never deployed live.
- Learning MUST cover: winning strategies · failed strategies · lifecycle history · mutation history · performance history.
- Future generated strategies must **reference this knowledge automatically** — no operator context injection per call.
- Additive on top of v01 — never disturb existing engines, routes, or DB schema.
- Vendor-independent — knowledge retrieval is a local operation, not an external service.

---

## 2. Architecture (three layers)

```
                      ┌───────────────────────────────────────┐
                      │  Existing v01 generation surfaces     │
                      │    /api/generate-strategy              │
                      │    /api/mutation/mutate                │
                      │    /api/auto-factory/run               │
                      └──────────────┬────────────────────────┘
                                     │ (prompt build)
                                     ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  L1  Knowledge Retriever  (NEW — read-only)                │
   │      engines.knowledge.retriever                            │
   │  ──────────────────────────────────────────────────────────│
   │  * top-K nearest neighbours by (pair, timeframe, style)     │
   │  * winners / losers cohort with quantile stats              │
   │  * mutation lineage — what prior mutation shapes worked     │
   │  * lifecycle patterns — which promotion paths deployed      │
   │  * failure fingerprints — which shapes always regress       │
   │  Injected as a compact JSON block into the LLM system       │
   │  prompt via legacy.engines.llm_config task-templates.       │
   └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  L2  Knowledge Cache        (NEW — periodic refresh)       │
   │      collection: strategy_knowledge_index                   │
   │  ──────────────────────────────────────────────────────────│
   │  Denormalised, index-friendly rollup rebuilt every N min    │
   │  by APScheduler. One document per (strategy_hash):          │
   │  {                                                          │
   │    strategy_hash, pair, timeframe, style,                   │
   │    indicators[], regime_tags[], mutation_family,            │
   │    verdict,                # win|loss|neutral               │
   │    best_pf, avg_pf, worst_dd, stability_score,              │
   │    lifecycle_terminal_stage,                                │
   │    embedding: [float32; 64] (optional — see §4)             │
   │    knowledge_summary_text: "..."   # 1-paragraph gist       │
   │    __ttl: 2026-03-15T00Z    # index expiry for GC           │
   │  }                                                          │
   └─────────────────────────────────────────────────────────────┘
                                     ▲
                                     │ (rebuild source)
   ┌─────────────────────────────────────────────────────────────┐
   │  L0  Source of Truth  (EXISTING — unchanged)               │
   │      strategy_library, strategy_library_archive,            │
   │      strategy_lifecycle_history, strategy_performance_history│
   │      mutation_events, mutation_runs                          │
   └─────────────────────────────────────────────────────────────┘
```

**No legacy code is touched.** L0 stays exactly as v01 defined it. L1 and L2 are new modules that live in `backend/legacy/engines/knowledge/` (or `backend/app/knowledge/` — see §7).

---

## 3. Retrieval contract (L1 API)

```python
from engines.knowledge.retriever import KnowledgeContext, retrieve

ctx: KnowledgeContext = await retrieve(
    pair="EURUSD",
    timeframe="1h",
    style="trend",          # trend | mean_reversion | breakout | scalp
    top_k=8,
    include_failures=True,  # v01 winner-only mode is opt-out
)
# ctx.winners      → list of top-K reference strategies (rich metrics)
# ctx.losers       → list of anti-patterns to avoid
# ctx.mutation_paths → ["ema→rsi promotion", "sl_widen: pf +0.31 median"]
# ctx.lifecycle_paths → {"candidate→production": 22, "candidate→archive": 47}
# ctx.summary_text → LLM-ready system-prompt block (max 2 KB)
```

The `summary_text` field is inlined into the LLM system prompt by
`legacy.engines.llm_prompts.build_strategy_prompt()` via a new
`KNOWLEDGE_BLOCK` template placeholder.

---

## 4. Retrieval implementation options

| Option | Cost | Quality | Ships in |
|---|---|---|---|
| **A. Metadata filter + rank** (pair, timeframe, style; sort by score) | 0 external deps | good baseline | week 1 |
| **B. TF-IDF over `knowledge_summary_text`** | +scikit-learn | better | week 2 |
| **C. Dense embeddings** (via VIE `/embed`, or SentenceTransformer local) | +VIE embedding endpoint OR +torch | best | month 2 |

Ship A first — it's a pure MongoDB query and returns knowledge on day 1. Add B/C additively once volume and quality justify.

---

## 5. Refresh scheduler (L2)

Reuses the existing APScheduler singleton already spun up for
`auto_data_maintainer` — no new process. New job:

```python
# knowledge_index_job — 15-minute interval
await knowledge.rebuild_index(scope="incremental")   # every 15 min
# once nightly at 02:00 UTC:
await knowledge.rebuild_index(scope="full")
```

Incremental rebuild watches `strategy_library` + `strategy_lifecycle_history`
for `updated_at > last_rebuild_ts`. Full rebuild reindexes everything and
purges TTL-expired knowledge rows.

---

## 6. Frontend surfacing

Additive routes only. No existing UI is changed.

| Endpoint | Purpose |
|---|---|
| `GET /api/knowledge/status` | Index size, last rebuild, coverage per (pair, tf). |
| `GET /api/knowledge/lookup?pair=&timeframe=&style=&top_k=8` | Same shape as `KnowledgeContext` above, admin-only. |
| `POST /api/knowledge/rebuild` | Force rebuild (admin). |
| `POST /api/knowledge/preview-prompt` | Return the exact LLM prompt block that would be injected for a hypothetical (pair, tf, style). Debug tool. |

Command Shell gains a **"Knowledge"** rail item that renders index health
+ a "preview prompt" trigger — nothing above the fold changes.

---

## 7. Directory placement

Both options work; recommend **A**:

**A. `backend/app/knowledge/`** — Phase-1 core namespace. Rationale: the
learning layer is a v1.1 addition and should live alongside the modern
Phase-1 code so it can freely import from `app.core`, `app.db`, and
`app.auth`. Legacy engines can still import it via the sys.path shim.

**B. `backend/legacy/engines/knowledge/`** — v01 namespace. Rationale:
symmetric with the existing `strategy_memory`, `strategy_library`,
`llm_config` engines. Drawback: importing modern Phase-1 utilities
requires the shim.

---

## 8. Prompt injection contract

`legacy.engines.llm_prompts` is patched additively: before returning
the assembled system-prompt, it calls `knowledge.get_prompt_block(
pair, timeframe, style)` and prepends the block under a `## Prior
knowledge` section. If knowledge is empty (cold start), the block is
literally the string `"(no prior knowledge yet — generating from
scratch)"` so the prompt shape stays byte-stable.

Every LLM call thereafter is audited via the existing
`log_llm_call()` telemetry with a new `knowledge_hash` field so we can
correlate generation quality with retrieval quality later.

---

## 9. Data-flow guarantees

- **No modification of L0 collections** — the learning layer only reads
  `strategy_library*`, `strategy_lifecycle_history`,
  `strategy_performance_history`, `mutation_events`, `mutation_runs`.
- **No live-trading path change** — recovered docs still have
  `status="active"` etc., but the *runner* code paths check
  `is_migration_record == True` (added in §11) and short-circuit
  activation to `False`. Learning-only.
- **Full rollback** — dropping the `strategy_knowledge_index`
  collection reverts the platform to identical v01 behaviour.

---

## 10. Migration-record fencing

The recovery migration stamps every doc with `__migration_source =
"strategy_factory_recovery"`. Live-trading guards check this stamp
before any activation flow:

```python
# legacy/engines/activation.py (patch)
if doc.get("__migration_source") == "strategy_factory_recovery":
    raise ActivationBlocked("recovered strategies are learning data only")
```

This is the ONLY code path that behaviourally distinguishes recovered
docs from generated docs. Every read (Library, Explorer, History,
Performance) surfaces them identically.

---

## 11. Rollout plan

| Phase | Duration | Deliverable |
|---|---|---|
| **1** | day 1 | `strategy_knowledge_index` collection + baseline metadata rebuild job (option A retrieval). Admin-only `/api/knowledge/status` + `/lookup`. Frontend Command Shell Knowledge tile. |
| **2** | week 2 | TF-IDF summary_text scoring. Prompt-injection hook active behind `KNOWLEDGE_INJECTION=true` flag. |
| **3** | month 1 | Winners/losers cohort stats surfaced in the Explorer row-detail drawer ("similar historical wins/losses"). |
| **4** | month 2 | Optional dense embeddings via VIE `/embed`. Auto-A/B: 50 % of generation calls include knowledge, 50 % don't; measure verdict-pass delta. |

---

## 12. Success metric

After Phase 2, at least 60 % of AI-generated strategies for a given
(pair, timeframe) inherit at least ONE indicator or mutation shape from
the top-3 retrieved historical winners for that scope. Tracked by the
existing `mutation_events` collection with a new `derived_from_hash[]`
field.
