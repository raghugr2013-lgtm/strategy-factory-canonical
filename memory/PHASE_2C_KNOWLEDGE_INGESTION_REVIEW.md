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

### 1.0 The primary organizing principle — Knowledge Domains, not Connector Types

**UKIE is organised around WHAT the knowledge is about, not HOW it
was fetched.** Connectors (GitHub, ArXiv, PDF, TradingView, forums,
books) are interchangeable *implementations* that plug in beneath a
domain — they are not the design axis.

**Why this matters:** a paper about volatility regimes could arrive
via ArXiv today and via a curated PDF corpus tomorrow. A Pine script
could arrive via GitHub today and via TradingView Community
tomorrow. The consumer (AI reasoning, similarity search, strategy
generation) does not care which pipe the bytes flowed through — it
cares about the **domain of the knowledge**. Organising the whole
subsystem around domains makes new connectors trivially additive and
keeps AI-side consumers stable as the source landscape evolves.

#### 1.0.1 The six canonical domains

| Domain | What it holds | Typical raw shapes | Consumers |
|---|---|---|---|
| **`strategy`** — Strategy Knowledge | Complete trading strategies with entries/exits/risk model | Pine scripts, cAlgo cBots, EA source, whitepaper appendices, textbook systems | Similarity search during generation; mutation seeds |
| **`research`** — Research Knowledge | Academic + practitioner research: papers, whitepapers, book chapters, quantitative articles | PDFs, arXiv preprints, SSRN, EPubs, blog posts | AI reasoning context; regime / theory grounding |
| **`indicator`** — Indicator Knowledge | Formal indicator definitions + parametrisations + known failure modes | Pine indicator scripts, MQL indicator libs, ta-lib references, quant handbook entries | Indicator selector; strategy IR builders |
| **`market`** — Market Knowledge | Instrument-specific microstructure, session behaviour, regime history, correlations | Broker data notes, exchange rulebooks, symbol-behaviour studies | Regime classifier; execution model |
| **`execution`** — Execution Knowledge | Broker specifics, prop-firm rules, slippage models, commission tables, latency profiles, order-type semantics | Prop-firm PDFs, broker docs, TCA whitepapers, prime-broker FAQ | Execution engine; prop-firm rule engine; realism sweep |
| **`internal_history`** — Internal Historical Knowledge | Everything the Factory itself has produced: past strategies, outcome events, mutation lineage, meta-learning verdicts | Existing Mongo collections (`strategies`, `outcome_events`, `mutation_runs`, `factory_eval_reports`) | Self-improvement loop; provenance graph |

**Adding a seventh domain (e.g. `sentiment`, `macro`) is one file** —
a new `KnowledgeDomain` entry + its default vocabulary; every
connector already knows how to declare which domain(s) it can serve.

#### 1.0.2 Domains × Connectors — the two-axis matrix

```
                            ┌── Domains (WHAT) ────────────────────────────────┐
                            │  strategy  research  indicator  market  execution  internal_history
─────────────────────────┼──────────────────────────────────────────────────────
Connectors (HOW)         │
  GithubConnector        │     ●         ○          ●          ○         ○          -
  ArxivConnector         │     -         ●          -          ○         ○          -
  PdfConnector           │     ●         ●          ●          ●         ●          -
  TradingViewConn        │     ●         -          ●          ○         -          -
  ForumConnector         │     ○         ○          ○          ○         ○          -
  BookConnector          │     ●         ●          ●          ●         ●          -
  BrokerDocsConnector    │     -         -          -          ●         ●          -
  PropFirmConnector      │     -         -          -          -         ●          -
  InternalMongoConnector │     -         -          -          -         -          ●
─────────────────────────┴──────────────────────────────────────────────────────
                            ●  primary target
                            ○  can contribute (secondary)
                            -  not applicable
```

**Reading the matrix:**
- A **connector declares which domain(s) it can supply** via its `supported_domains` set.
- A **domain declares its expected shape + vocabulary + validators** via a `KnowledgeDomainSpec`.
- The **pipeline runs the same 8 stages** regardless of connector, but per-domain **specialisations** are dispatched via a small registry.

**One connector can populate multiple domains** — e.g. a PDF book on
"Building Trading Systems" might contribute chapters to `strategy`,
paragraphs to `research`, and appendices to `execution`. The
connector emits `RawKnowledgeItem[]` each tagged with its target
domain; the pipeline dispatches each item to the domain-specific
validator + normaliser + trust scorer.

#### 1.0.3 The `KnowledgeDomain` registry

```python
class KnowledgeDomain(str, Enum):
    STRATEGY          = "strategy"
    RESEARCH          = "research"
    INDICATOR         = "indicator"
    MARKET            = "market"
    EXECUTION         = "execution"
    INTERNAL_HISTORY  = "internal_history"


@dataclass(frozen=True)
class KnowledgeDomainSpec:
    domain:               KnowledgeDomain
    canonical_shape:      type              # dataclass — the parsed item shape
    required_fields:      tuple[str, ...]   # must be present after parsing
    validators:           tuple[Callable, ...]
    default_trust_floor:  int               # (see §3) minimum tier accepted
    normaliser:           Callable          # canonicalise units, symbols, timeframes
    embedder:             Callable          # produces the vector for similarity search
    ai_context_policy:    Literal["verbatim", "quote", "summary", "off"]
                          # how AI may consume this domain's items
```

Every connector's `fetch()` result is dispatched by the ingestion
runner into the correct domain lane based on the `RawKnowledgeItem.domain`
field. Domains keep their own storage sub-collection so consumers can
query one domain without scanning the whole KB.

### 1.1 Physical layout — domain-first pipeline, connectors underneath

```
     Connectors (interchangeable        Domains (primary axis)              Consumers
     implementations, per source)        each with its own spec, storage,   (all cross-domain
                                          validators, embedder)              queries)
     ─────────────────────────           ────────────────────────────       ────────────────
     ┌─────────────────┐
     │ GithubConnector │──┐
     ├─────────────────┤  │             ┌── strategy ─────────────────┐
     │ ArxivConnector  │  │             │   validators + normaliser   │
     ├─────────────────┤  │             │   → strategy_kb.strategies  │──┐
     │ PdfConnector    │  │             └────────────────────────────┘  │
     ├─────────────────┤  │                                             │
     │ TradingViewConn │──┼─►  ┌────────────────────────────┐          │
     ├─────────────────┤  │    │  ingestion_runner           │          │
     │ ForumConnector  │  │    │    ↓                        │          │
     ├─────────────────┤  │    │  parser  (AI / VIE-driven) │          │
     │ BookConnector   │  │    │    ↓                        │          │
     ├─────────────────┤  │    │  domain_router  ← NEW       │──┬──────┼──►  ┌── research ─────────────────┐
     │ BrokerDocsConn  │  │    │    ↓ (dispatch by domain)   │  │      │     │   validators + normaliser  │
     ├─────────────────┤  │    │  validator (domain-scoped)  │  │      │     │   → strategy_kb.research   │
     │ PropFirmConn    │──┤    │    ↓                        │  │      │     └────────────────────────────┘
     ├─────────────────┤  │    │  license_gate               │  │      │
     │ InternalMongoC  │──┘    │    ↓                        │  │      │     ┌── indicator ────────────────┐
     └─────────────────┘       │  normaliser (domain-scoped) │  ├──────┼────►│   validators + normaliser  │
        each yields             │    ↓                        │  │      │     │   → strategy_kb.indicators │
        RawKnowledgeItem        │  dedup_check                │  │      │     └────────────────────────────┘
        tagged with target      │    ↓                        │  │      │
        KnowledgeDomain         │  trust_scorer               │  │      │     ┌── market ───────────────────┐
                                │    ↓                        │  ├──────┼────►│   validators + normaliser  │
                                │  KnowledgeRepository        │  │      │     │   → strategy_kb.market     │
                                │    (per-domain writer)      │  │      │     └────────────────────────────┘
                                └────────────────────────────┘  │      │
                                                                 │      │     ┌── execution ────────────────┐
                                                                 ├──────┼────►│   validators + normaliser  │
                                                                 │      │     │   → strategy_kb.execution  │
                                                                 │      │     └────────────────────────────┘
                                                                 │      │
                                                                 │      │     ┌── internal_history ─────────┐
                                                                 └──────┴────►│   fed by InternalMongoConn │
                                                                              │   read-only mirror         │
                                                                              └────────────────────────────┘
                                                                                          ↓
                                                                              AI reasoning context / similarity
                                                                              search / mutation seeds / regime
                                                                              classifier / rule engine
```

Four new pipeline stages (`domain_router`, `license_gate`,
`dedup_check`, `trust_scorer`), two new abstractions (**`KnowledgeDomain`**
and `KnowledgeConnector`). Everything else is the existing pipeline,
generalised from the strategies-only path to a domain-partitioned
knowledge path.

**Storage layout** — one sub-collection per domain inside the isolated
`strategy_knowledge_base` DB:

```
strategy_knowledge_base
  ├── strategies            (KnowledgeDomain.STRATEGY)
  ├── research              (KnowledgeDomain.RESEARCH)
  ├── indicators            (KnowledgeDomain.INDICATOR)
  ├── market                (KnowledgeDomain.MARKET)
  ├── execution             (KnowledgeDomain.EXECUTION)
  ├── internal_history      (KnowledgeDomain.INTERNAL_HISTORY — read-only mirror)
  ├── ingestion_runs        (log — cross-domain)
  ├── raw_items             (raw bytes + hash + provenance — cross-domain)
  └── knowledge_promotions_log
```

All items retain `learning_only:True + eligible_for_deploy:False`
regardless of domain (§5).

### 1.2 The Connector contract

```python
class KnowledgeConnector(Protocol):
    """Every knowledge source implements this Protocol.

    Connectors are HOW knowledge is fetched. Each connector declares
    which Knowledge Domain(s) it can supply — one connector can
    populate multiple domains (e.g. a PDF book contributes to both
    `strategy` and `research`). The domain is the primary organising
    principle; connectors are the interchangeable fetch layer.
    """

    name: str                          # e.g. "github", "arxiv", "tradingview"
    source_type: str                   # "code" | "paper" | "post" | "book" | "docs"
    supported_domains: set[KnowledgeDomain]
                                       # which domains this connector can supply
    default_trust_tier: int            # 1..5 (see §3)
    supported_licenses: set[str] | Literal["*"]

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        """Yield references (URLs/DOIs/etc.) without fetching content."""

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        """Fetch full content + provenance metadata.

        The returned item MUST carry `domain: KnowledgeDomain` set to
        the target domain. A single fetch may split into multiple items
        (e.g. a book → chapters) each tagged with its own domain.
        """

    def rate_limit(self) -> RateLimit:
        """Declare per-source rate limits so the scheduler honours them."""
```

**Adding a new source is one file.** No changes to the pipeline
orchestrator, no changes to the parser (AI is source-agnostic), no
changes to the schema. **Adding a new domain is one file** — a
`KnowledgeDomainSpec` entry — plus one line in every connector that
opts to supply it.

### 1.3 The `RawKnowledgeItem` canonical shape

```
{
  # domain assignment (NEW — primary organising axis)
  domain:            "strategy" | "research" | "indicator" | "market" | "execution" | "internal_history",

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
consumes. The **`domain` field is set at fetch time** — the connector
knows which domain(s) it targets. The `domain_router` stage dispatches
to the domain-specific validator + normaliser + trust scorer, then
writes to that domain's sub-collection.

Parsing yields a **domain-specific `ParsedKnowledgeItem` subtype**:
- `ParsedStrategyItem` (existing `IngestedStrategy` shape)
- `ParsedResearchItem` (title, abstract, sections, citations)
- `ParsedIndicatorItem` (name, formula, parameters, failure modes)
- `ParsedMarketItem` (symbol, session, regime notes)
- `ParsedExecutionItem` (broker, rule, constraint, cost model)
- `ParsedInternalHistoryItem` (Mongo doc reference — read-only)

All parsed types share a `raw_ref` pointer back to the raw item.

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
| **Primary organising axis** | **Knowledge Domains** — `strategy`, `research`, `indicator`, `market`, `execution`, `internal_history` (§1.0) |
| **Fetch layer** | Connectors — interchangeable implementations beneath domains; one file per source, declares which domain(s) it supplies (§1.2) |
| **Domains × Connectors** | Many-to-many matrix (§1.0.2) — a book connector supplies `strategy` + `research` + `execution`; ArXiv supplies `research` only |
| **Domain contract** | `KnowledgeDomainSpec` — canonical shape, validators, normaliser, embedder, AI consumption policy per domain (§1.0.3) |
| **Sources (initial)** | GitHub, ArXiv, PDF, TradingView, forums, books, broker docs, prop-firm docs, internal Mongo (§1.0.2) |
| **Connector interface** | `KnowledgeConnector` Protocol (§1.2) — declares `supported_domains` |
| **Raw item shape** | `RawKnowledgeItem` (§1.3) — provenance-anchored + domain-tagged |
| **Parsed item shape** | Per-domain (`ParsedStrategyItem`, `ParsedResearchItem`, `ParsedIndicatorItem`, …) sharing a `raw_ref` (§1.3) |
| **Provenance** | 5 anchors: connector, url, source_ref, content_hash, fetched_at (§2) |
| **Licensing** | License gate stage; SPDX detection; 5-outcome classifier (§4) |
| **Trust** | 5-tier ladder (§3) computed by `trust_scorer` — one score per item regardless of domain |
| **Deduplication** | canonical_hash lookup **within the target domain** before insert (§1.1) |
| **Governance** | Writes routed through `KnowledgeRepository` only; production is unreachable except via the audited `/knowledge/promote` bridge (§5) |
| **Storage** | One sub-collection per domain inside `strategy_knowledge_base`; cross-domain `raw_items` + `ingestion_runs` (§1.1) |
| **Scheduler** | Existing APScheduler, per-connector rate-limited, coverage-aware (from Phase 2B lessons) |
| **AI consumption** | `/api/knowledge/nearest?domain=<d>` reads per-domain; trust-tier filtering enabled; AI context policy is a **domain-level** decision (§1.0.3) |

---

## 7. Roadmap — sequenced, reversible

| # | Step | Prereq | Effort | Reversible? |
|---|---|---|---|---|
| **P2C.0** | Land the `KnowledgeDomain` enum + `KnowledgeDomainSpec` registry with the six canonical domains. **Domains are the primary organising axis** — every downstream step consumes this registry | none | 0.5 day | Yes |
| **P2C.1** | Extract `KnowledgeConnector` Protocol (declaring `supported_domains`) + move existing GitHub logic behind it as `GithubConnector` (default `supported_domains={STRATEGY}`). No behaviour change | P2C.0 | 1 day | Yes |
| **P2C.2** | Introduce `RawKnowledgeItem` canonical shape (with `domain` field); wrap existing pipeline to produce it as an intermediate | P2C.1 | 0.5 day | Yes |
| **P2C.3** | Add `content_hash`, `source_ref`, `fetched_at`, `license` fields to every new ingested_strategies write | P2C.2 | 0.5 day | Yes — additive |
| **P2C.4** | Add `domain_router.py` — dispatches each raw item to its domain's validator/normaliser/embedder based on the `domain` field. Existing rows default to `domain=STRATEGY` | P2C.3 | 1 day | Yes — flag `ENABLE_DOMAIN_ROUTING=false` bypasses (single-domain fallback) |
| **P2C.5** | Add `license_gate.py` — 5-outcome classifier; runs post-validator, pre-normaliser | P2C.4 | 1 day | Yes — flag |
| **P2C.6** | Add `trust_scorer.py` + 5-tier ladder; fill `trust_tier` on every new row | P2C.5 | 0.5 day | Yes — flag |
| **P2C.7** | Add `dedup_check.py` using `canonical_hash` — checks **within the target domain** (a strategy hash can coexist with an identical-hash research chapter) | P2C.6 | 0.5 day | Yes — flag |
| **P2C.8** | Redirect injector output from mutation pipeline → `KnowledgeRepository.insert_ingested(domain, item)` — one audited write endpoint per domain. **This is the governance cutover** | P2C.7 | 1 day | Yes — flag |
| **P2C.9** | Add `POST /api/knowledge/promote/{item_id}` — the audited bridge from `strategy` domain KB to production `strategies` (draft state only) | P2C.8 | 0.5 day | Yes |
| **P2C.10** | New connectors — one file each. Suggested order matched to which domains most need coverage: `ArxivConnector` (research), `PdfConnector` (research + strategy + execution), `PropFirmConnector` (execution), `TradingViewConnector` (strategy + indicator), `InternalMongoConnector` (internal_history) | P2C.8 | 1 day per connector | Yes per connector |
| **P2C.11** | Retro-scoring — backfill `domain=STRATEGY` + `trust_tier` + `license` on the 55 existing rows via the new gates (dry-run first, no auto-mutate) | P2C.6 | 0.5 day | Yes |
| **P2C.12** | Dashboard surface — **domain breakdown** + trust-tier distribution + license distribution + connector-health card | P2C.6 | 1 day | Yes — pure UI |

**Total effort:** ~7.5 focused days for the core pipeline (P2C.0–P2C.9);
+1 day per new connector.

**Critical cutover:** P2C.8. Before flipping, run a dry-run that
takes the last 10 ingestion runs and verifies the new path would have
produced the same normalised items (minus the `eligible_for_deploy:
False` change and now scoped to `domain=STRATEGY`).

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

Approve or amend §1.0 (**Knowledge Domain model — the primary
organising axis**), §3 (trust tiers), and §7 (roadmap). Then, when
Phase 2 implementation begins, execute **P2C.0 → P2C.1** — a
1.5-day step that lands the `KnowledgeDomain` registry + extracts the
`KnowledgeConnector` Protocol (declaring `supported_domains`) and
moves existing GitHub logic behind it. Zero behaviour change; the
ground on which every new connector and every new domain will be
built.

Everything downstream depends on the domain registry and the
connector Protocol being stable — the domain is WHAT the knowledge
is about; the connector is HOW it was fetched. Both axes are
extension points.
