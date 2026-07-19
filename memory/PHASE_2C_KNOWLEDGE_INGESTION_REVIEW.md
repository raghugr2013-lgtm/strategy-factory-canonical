# Phase 2C — Knowledge Ingestion Architecture Review
### Universal Knowledge Ingestion Engine (design before implementation)

> **Status:** review only — no code changes.
> This document audits the existing ingestion pipeline at commit `829f31d`
> and proposes its evolution into a **Universal Knowledge Ingestion
> Engine** capable of taking any external knowledge source (GitHub,
> PDF, academic paper, TradingView, forum post, book excerpt) into
> the Historical KB with full provenance, licensing awareness, trust
> levels, and post-Phase-1.6 governance.

---

## 0. Current state

### 0.1 The existing pipeline (already 9 modules, well-structured)

```
      curated_sources                        (whitelist of high-signal repos)
             ↓
      collector.py       ────►  raw github blob (rate-bounded, optional token)
             ↓
      parser.py          ────►  AI-parsed structured record          (VIE call)
             ↓
      validator.py       ────►  reject/accept + reason
             ↓
      normalizer.py      ────►  maps to internal vocabulary
             ↓
      injector.py        ────►  hands to mutation pipeline           ⚠ governance
             ↓
      ingested_strategies (Mongo) + ingestion_runs (log)
```

Files (`backend/legacy/engines/strategy_ingestion/`):
`collector.py, parser.py, validator.py, normalizer.py, injector.py,
schema.py, curated_sources.py, ingestion_runner.py, __init__.py`

API surface:
`/api/ingestion/*`, `/api/knowledge/*` (already exists — legacy),
`/api/research/*`, `/api/research-lineage/*`.

Storage:
`ingested_strategies` (55 rows in the prior-pod dump — confirmed
Phase 1.5), `ingestion_runs` (11 rows), one document per raw import
with `source, url, name, type, indicators, entry_logic, exit_logic,
risk_model, timeframe, pair, confidence, quality_score, status,
reason, raw_code_preview, run_id`.

Scheduler: APScheduler `AsyncIOScheduler` inside `ingestion_runner.py`,
toggle-able via API.

### 0.2 What is production-grade today (keep)

| Component | Verdict |
|---|---|
| **6-stage pipeline separation** (collect → parse → validate → normalize → inject → log) | ✅ Textbook — each stage is pure enough to unit-test independently |
| **AI-driven parser** using VIE for the collect-to-structured step | ✅ The right layer to consume unstructured input; already vendor-independent |
| **Curated source whitelist** (`curated_sources.py`) instead of broad GitHub search | ✅ Correct — the header comment explicitly documents that broad search yielded low-signal tail (README-only projects, tutorials) |
| **Injector as the *sole bridge* to mutation** (`injector.py` header states "the ONE bridge") | ✅ Right architectural rule; only one file to audit for governance |
| **Per-run + per-strategy logs** in Mongo | ✅ Provenance floor already in place |
| **Rate-bounded collectors** with optional `GITHUB_TOKEN` | ✅ Cost-safe by default |
| **APScheduler orchestration** with API toggle | ✅ Consistent with the rest of the platform |

### 0.3 The seven real gaps

| # | Gap | Severity | Why it matters for a Universal KIE |
|---|---|---|---|
| G1 | **Only one connector type** (GitHub). No abstraction; adding TradingView or a PDF corpus requires rewriting `collector.py` | Critical | The word "Universal" in the phase name is the whole point |
| G2 | **No connector interface / Protocol** — everything is procedural in `collector.py` | Critical | Blocks parallel connector development |
| G3 | **Provenance is thin** — URL + `run_id` but no license, no content hash, no author, no fetched-at timestamp integrity, no upstream commit SHA | Major | Legal + auditability |
| G4 | **No licensing filter** — a repo without a `LICENSE` file is treated identically to MIT/Apache | Major | Legal risk (proprietary → derivative works) |
| G5 | **Binary "accepted/rejected"** — no trust levels, no quality tiers | Major | AI can't reason about corpus reliability without this |
| G6 | **Auto-injection into mutation pipeline predates Phase 1.6 guardrails** — `injector.py` writes strategies that historically had `verdict="RISKY"` but no `eligible_for_deploy` field | Critical | Violates the Phase 1.6-final safety invariant unless every new inject writes `eligible_for_deploy: False` |
| G7 | **No content deduplication** — a GitHub repo edited slightly re-ingests as a new strategy; no `canonical_hash` check against the KB before injection | Major | Corpus pollution |

---

## 1. The Universal Knowledge Ingestion Engine (UKIE)

### 1.1 Physical layout — same pipeline, connector abstraction added

```
    Connectors (pluggable)                Pipeline (unchanged shape)
    ────────────────────                  ─────────────────────────
    ┌─────────────────┐
    │ GithubConnector │──┐
    ├─────────────────┤  │
    │ PdfConnector    │  │
    ├─────────────────┤  │      ┌────────────────────────────┐
    │ ArxivConnector  │──┼─────►│  ingestion_runner           │
    ├─────────────────┤  │      │    ↓                        │
    │ TradingViewConn │  │      │  parser  (AI, VIE-driven)  │
    ├─────────────────┤  │      │    ↓                        │
    │ ForumConnector  │  │      │  validator                  │
    ├─────────────────┤  │      │    ↓                        │
    │ BookConnector   │──┘      │  license_gate    ← NEW      │
    └─────────────────┘         │    ↓                        │
        each yields             │  normalizer                 │
        RawKnowledgeItem        │    ↓                        │
                                │  dedup_check     ← NEW      │
                                │    ↓                        │
                                │  trust_scorer    ← NEW      │
                                │    ↓                        │
                                │  KnowledgeRepository        │
                                │    (writes learning_only)   │
                                └────────────────────────────┘
                                          ↓
                                strategy_knowledge_base DB
                                  (isolated per Phase 1.5)
```

Three new pipeline stages (`license_gate`, `dedup_check`, `trust_scorer`),
one new abstraction (connector Protocol). Everything else is the
existing pipeline, moved from the strategies-only path to a general
knowledge path.

### 1.2 The Connector contract

```python
class KnowledgeConnector(Protocol):
    """Every knowledge source implements this Protocol."""

    name: str                  # e.g. "github", "arxiv", "tradingview"
    source_type: str           # "code" | "paper" | "post" | "book"
    default_trust_tier: int    # 1..5 (see §3)
    supported_licenses: set[str] | Literal["*"]

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        """Yield references (URLs/DOIs/etc.) without fetching content."""

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        """Fetch full content + provenance metadata."""

    def rate_limit(self) -> RateLimit:
        """Declare per-source rate limits so the scheduler honours them."""
```

**Adding a new source is one file.** No changes to the pipeline
orchestrator, no changes to the parser (AI is source-agnostic), no
changes to the schema.

### 1.3 The `RawKnowledgeItem` canonical shape

```
{
  # provenance (Phase 1.6-mandatory)
  connector_name:    "github",
  source_url:        "https://github.com/foo/bar/blob/abc123/ema.pine",
  source_ref:        "abc123",              # commit SHA / DOI / URL fragment
  content_hash:      "sha256:...",          # of the raw bytes
  fetched_at:        <UTC iso>,
  author:            "trugurpala",
  license:           "MIT" | "Apache-2.0" | "unknown" | "proprietary",
  license_confidence: 0..1,

  # payload
  content_bytes:     BinData(...),          # raw for parser
  content_mime:      "text/plain" | "application/pdf" | "text/x-pine",

  # guardrails (Phase 1.6)
  learning_only:      True,                 # HARD RAIL — every KIE item
  eligible_for_deploy: False,               # HARD RAIL — every KIE item

  # trust (populated post-scoring)
  trust_tier:         null,                 # 1..5, filled by trust_scorer
  trust_reasons:      []
}
```

This is the shape every connector produces and every downstream stage
consumes. It is not the *parsed* strategy — it is the *raw* item with
full provenance. Parsing yields a `ParsedKnowledgeItem` which is the
existing `IngestedStrategy` shape plus a `raw_ref` pointer.

---

## 2. Provenance Guarantee

### 2.1 What we track

Every ingested row carries **five provenance anchors**:

1. **`connector_name`** — which connector fetched it (e.g. "github")
2. **`source_url`** — canonical URL of the source
3. **`source_ref`** — immutable pointer (commit SHA / DOI / permalink)
4. **`content_hash`** — SHA-256 of the raw bytes as fetched
5. **`fetched_at`** — UTC timestamp of fetch

Content hash + source_ref together let us **prove** what we ingested
years later even if the URL 404s. If a strategy's provenance ever
becomes disputed, we can produce the exact bytes that produced our
KB entry.

### 2.2 Immutable audit trail

`ingestion_runs` gains: `connector_snapshot` (version hash of the
connector code + curated_sources hash) so future re-runs of the same
window are reproducible.

---

## 3. Trust Tiers

Replace binary `accepted/rejected` with a **5-tier trust ladder**.

| Tier | Label | Criteria | AI-consumption rules |
|---|---|---|---|
| **T5 — Authoritative** | Verified peer-reviewed source, permissive license, high-quality code | e.g. arXiv paper with 100+ citations; a whitelisted institutional repo | May be quoted verbatim in AI reasoning context |
| **T4 — Curated** | High-signal source on the curated whitelist, clean license, structural completeness | GitHub curated repo, clean MIT | Included in similarity search + reasoning context |
| **T3 — Standard** | Public source, license present, parser confidence ≥ 0.8 | Uncurated GitHub w/ LICENSE file | Included in similarity search only |
| **T2 — Observational** | License present but restrictive OR parser confidence < 0.8 | Non-permissive license, forum post with attribution | Included in **counter-example** pool only (learn what NOT to do) |
| **T1 — Quarantine** | License missing, source unverified, parser rejected | GitHub repo without LICENSE, uncredited copy | Not consumed. Stored for audit only. |

Trust is computed by `trust_scorer` based on: connector's `default_trust_tier`, license outcome, parser confidence, deduplication result, source authority signals (stars, citations).

**AI queries filter by trust tier by default.** A dashboard control
lets an operator broaden the pool for research.

---

## 4. Licensing Awareness

### 4.1 License gate (new pipeline stage)

Before injection, every item passes through `license_gate.py`:

```
def license_gate(item: RawKnowledgeItem) -> LicenseVerdict:
    1. Detect license via GitHub API 'license' field
       OR SPDX-ID scan of LICENSE / LICENCE / COPYING files
       OR heuristic classifier over the first 1 kB of any LICENSE.md
    2. Classify:
         permissive  = {MIT, Apache-2.0, BSD-*, ISC, Unlicense, CC0}
         weak_copyleft = {MPL-2.0, LGPL-*}
         copyleft    = {GPL-2.0, GPL-3.0, AGPL-*}
         restrictive = {CC-BY-NC-*, non-commercial}
         unknown     = <not detected>
    3. Emit verdict:
         permissive       → allow, trust_tier unchanged
         weak_copyleft    → allow, trust_tier -= 0
         copyleft         → allow BUT mark 'derived_works_encumbered=True'
         restrictive      → allow into T2 observational only
         unknown          → allow into T1 quarantine only
```

### 4.2 What "allow into T1 quarantine" means

Even quarantined items are ingested — we don't throw away knowledge.
But `strategy_kb_view` filters exclude T1 by default, and the KB
similarity API never returns them. They exist only for later human
review.

### 4.3 The three questions this answers

- *Can this strategy inform ours?* → Yes if T3+
- *Can our AI-generated derivative be published/deployed?* → Only if
  the source-of-inspiration is T4+ and permissive
- *Can we prove we're not infringing?* → Yes — content_hash +
  source_ref + license_gate verdict all persisted

---

## 5. Governance Alignment with Phase 1.6

### 5.1 The critical wiring change

`injector.py` today hands parsed strategies to the *mutation
pipeline* with `auto_save=True`. Post-Phase-1.6, this MUST route
through `KnowledgeRepository`, not the production strategies path:

```
Old:  parser → validator → normalizer → injector → mutation_pipeline (auto_save)
                                          ↓
                                       strategies collection    ⚠ WRONG

New:  parser → validator → license_gate → normalizer → dedup_check
              → trust_scorer → knowledge_writer
                                          ↓
                                strategy_knowledge_base.ingested_items
                                (learning_only:True, eligible_for_deploy:False)
```

The mutation pipeline never receives an ingested strategy as a live
candidate. If an operator wants to *promote* an ingested strategy for
mutation, that is an **explicit, audited, human-gated action** —
a new endpoint `POST /api/knowledge/promote/{item_id}` that requires
`admin` role and writes to `strategies` with `eligible_for_deploy:
False` (draft state), so the current-framework governance pipeline
gets the final say.

### 5.2 The three hard rails (structural, not procedural)

1. All KIE writes go through `KnowledgeRepository` → writes forbidden,
   so ingestion cannot mutate old KB entries — it can only insert new
   ones (via a specific `insert_ingested` method that we add and audit).
2. All KIE items carry `learning_only:True + eligible_for_deploy:False`
   as row-level guards.
3. Production strategy reads (via `StrategyRepository`, Phase 1.6-final)
   filter these out. Zero code path can leak a KIE item into a
   deployment candidate.

### 5.3 The exception path

To allow ingested items to eventually inform mutation, we add ONE
new controlled bridge — `POST /api/knowledge/promote/{item_id}`:

- Requires `admin` role
- Validates the item is T4+
- Recomputes the item's `canonical_hash` and compares against
  existing `strategies.canonical_hash` — refuses if a near-dup exists
- Writes a **new draft** into `strategies` with
  `eligible_for_deploy: False`, `origin_kb_id: <item_id>`,
  `promoted_by: <user>`, `promoted_at: <ts>`
- Writes an audit row to `knowledge_promotions_log`
- Governance pipeline (unchanged) decides whether the draft ever
  reaches deployment

The user's original goal — "AI to use the KB as read-only reasoning
support, never as a deployment source" — is preserved verbatim by
this design.

---

## 6. Recommended architecture summary

| Aspect | Design |
|---|---|
| **Sources** | Any — connector plugin per source, one file each |
| **Connector interface** | `KnowledgeConnector` Protocol (§1.2) |
| **Raw item shape** | `RawKnowledgeItem` (§1.3) — provenance-anchored |
| **Provenance** | 5 anchors: connector, url, source_ref, content_hash, fetched_at (§2) |
| **Licensing** | License gate stage; SPDX detection; 5-outcome classifier (§4) |
| **Trust** | 5-tier ladder (§3) computed by trust_scorer |
| **Deduplication** | canonical_hash lookup against KB before insert (§1.1) |
| **Governance** | Writes routed through KnowledgeRepository only; production is unreachable except via the audited `/knowledge/promote` bridge (§5) |
| **Storage** | `strategy_knowledge_base.ingested_items` (raw), `.parsed_items` (structured), `.ingestion_runs` (log) — all learning_only:True |
| **Scheduler** | Existing APScheduler, per-connector rate-limited, coverage-aware (from Phase 2B lessons) |
| **AI consumption** | `/api/knowledge/nearest` (already exists) reads these via `KnowledgeRepository`; trust-tier filtering enabled |

---

## 7. Roadmap — sequenced, reversible

| # | Step | Prereq | Effort | Reversible? |
|---|---|---|---|---|
| **P2C.1** | Extract `KnowledgeConnector` Protocol + move existing GitHub logic behind it as `GithubConnector`. No behaviour change | none | 1 day | Yes |
| **P2C.2** | Introduce `RawKnowledgeItem` canonical shape; wrap existing pipeline to produce it as an intermediate | P2C.1 | 0.5 day | Yes |
| **P2C.3** | Add `content_hash`, `source_ref`, `fetched_at`, `license` fields to every new ingested_strategies write | P2C.2 | 0.5 day | Yes — additive |
| **P2C.4** | Add `license_gate.py` — 5-outcome classifier; runs post-validator, pre-normalizer | P2C.3 | 1 day | Yes — feature flag `ENABLE_LICENSE_GATE=false` bypasses |
| **P2C.5** | Add `trust_scorer.py` + 5-tier ladder; fill `trust_tier` on every new row | P2C.4 | 0.5 day | Yes — flag |
| **P2C.6** | Add `dedup_check.py` using `canonical_hash` from Phase 1.6; refuse insert on hash collision unless `force=true` | P2C.5 | 0.5 day | Yes — flag |
| **P2C.7** | Redirect injector output from mutation pipeline → `KnowledgeRepository.insert_ingested()` (new method — the single audited write endpoint). **This is the governance cutover** | P2C.6 | 1 day | Yes — flag |
| **P2C.8** | Add `POST /api/knowledge/promote/{item_id}` — the audited bridge from KB to `strategies` (draft state only) | P2C.7 | 0.5 day | Yes |
| **P2C.9** | New connectors — one file each. Suggested order: `ArxivConnector` (papers), `PdfConnector` (books/PDFs), `TradingViewConnector` (community scripts) | P2C.7 | 1 day per connector | Yes per connector |
| **P2C.10** | Retro-scoring — backfill `trust_tier` + `license` on the 55 existing rows via the new gates (dry-run first, no auto-mutate) | P2C.5 | 0.5 day | Yes |
| **P2C.11** | Dashboard surface — trust-tier breakdown + license distribution + connector-health card | P2C.5 | 1 day | Yes — pure UI |

**Total effort:** ~7 focused days for the core pipeline (P2C.1–P2C.8);
+1 day per new connector.

**Critical cutover:** P2C.7. Before flipping, run a dry-run that
takes the last 10 ingestion runs and verifies the new path would have
produced the same normalised items (minus the `eligible_for_deploy:
False` change).

---

## 8. Interaction with prior phases

- **Phase 1.5 (KB import):** UKIE writes to the same
  `strategy_knowledge_base` DB. The 55 existing `ingested_strategies`
  rows get backfilled with license + trust_tier fields on P2C.10.
- **Phase 1.6 (Repository safety):** UKIE writes through
  `KnowledgeRepository`. The Phase 1.6-final adoption already covers
  every production strategy read; UKIE items are structurally
  invisible to any production path.
- **Phase 2A (AI):** The AI's `knowledge_extraction` capability
  becomes UKIE's parser backend — one call site to VIE, provider-
  agnostic. The AI's `strategy_generation` calls filter reasoning
  context to `trust_tier >= T3` by default.
- **Phase 2B (Data):** UKIE has no direct data-layer dependency, but
  benefits from the coverage_report semantics — the same "gaps as
  first-class citizens" thinking applies to knowledge coverage
  (`which papers about mean-reversion are we missing?`).

---

## 9. Non-goals honoured

- No implementation. Design only.
- No new connectors written. Interface + one migration of existing
  GitHub logic to conform to it.
- No changes to the mutation pipeline itself. Only the input source
  is redirected (P2C.7).
- No prompt changes.

---

## 10. Recommended next call

Approve or amend §3 (trust tiers) and §7 (roadmap). Then, when Phase
2 implementation begins, execute **P2C.1** — a 1-day step that
extracts the connector Protocol and moves existing GitHub logic
behind it. Zero behaviour change; the ground on which every new
connector will be built.

Everything downstream depends only on the Protocol being stable.
