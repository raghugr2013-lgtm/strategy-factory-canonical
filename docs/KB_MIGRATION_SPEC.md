# Historical Knowledge Base — Compatibility & Migration Specification

_Version · v0.1 · **DRAFT · FOR REVIEW**_
_Author · Main Agent (E1)_
_Date · 2026-07-22_
_Scope · Planning + architecture only. **No implementation. No data import. No backend changes.**_
_Cites · `docs/ARCHITECTURE.md` §4 (lifecycle) · §4.3 (historical KB compatibility) · §10 (Passport) · §10.4 (KB import strategy) · §12 (Approvals) · §13 (Event vocabulary) · §17 (factory lifecycle) · §18 (services) · §20 (autonomy) · §21.5 (KB-related v2 territory)_

> **Objective.** Define — before writing a single migration line — how the pre-Phase-2 historical Strategy Knowledge Base (KB) can enter the canonical Strategy Passport architecture without violating any of the six architectural invariants (§18.3). This document is deliverable-only. Import work waits for user acceptance.

---

## 0 · Executive summary

The Factory holds **two** collections of strategies that today live in **physically distinct databases**:

| Corpus | Where | Role today | Governance |
|---|---|---|---|
| **Production** — `strategies` collection in the primary DB | Prod DB | Deployable candidates. Composed via Strategy Lab. Passes through the §4 lifecycle. | `StrategyRepository` — safety filter `eligible_for_deploy != False` |
| **Historical KB** — `strategy_kb_view` (rows) + `strategy_kb_champions` (families) in `strategy_knowledge_base` DB | KB DB (isolated) | **Learning-only** corpus. Read via `POST /api/knowledge/nearest` for neighbours; never routed to deployment. | `KnowledgeRepository` — read-only, forces `learning_only=True`, refuses every write |

The migration is **not** a copy job. It is a **provenance-preserving Passport creation flow**: each KB entry becomes a new Passport-visible `strategies` row whose state is `champion` **and** whose guardrails permanently prevent deployment until a fresh evidence bundle is earned under the current framework. The KB itself is never mutated — the migration is one-way and one-shot per import batch.

Five design commitments make this safe:

1. **KB is source-of-truth for the historical corpus.** The KB collection stays untouched; migration produces derived rows in `strategies`.
2. **`learning_only=true` is permanent** for imported entries — even if they pass future gates. There is **no state under which an imported row becomes eligible for deploy** without recomposition through Strategy Lab first (§4.3, §10.4).
3. **Every import writes an immutable audit trail** to Timeline as `kb_family_imported` events (§13.1 vocabulary).
4. **Rollback is idempotent by canonical hash.** Because `canonical_hash` is deterministic (§canonical.py), reversing an import is a bounded, provable operation.
5. **No new backend endpoints** are proposed in this document. Every action described maps to endpoints and repositories that already exist under Backend Feature Freeze v1.1.0-stage4 — the migration is an admin CLI + operator UX layer over the freeze-safe primitives.

---

## 1 · Legacy corpus review

### 1.1 Where it lives

- **Database name** — `strategy_knowledge_base` (env override: `KNOWLEDGE_DB_NAME`).
- **Row collection** — `strategy_kb_view`.
- **Family collection** — `strategy_kb_champions` (Phase 1.5 champions by category).
- **Access class** — `app.knowledge.repository.KnowledgeRepository` — read-only, mandatory `learning_only=True` filter injected into every read, every write raises `_ImmutableError`.
- **Isolation guarantee** — physically distinct DB. Production `StrategyRepository` cannot see KB rows because production reads default to `eligible_for_deploy != False` and every KB row is `eligible_for_deploy=False`.

### 1.2 Observed row shape

Reconstructed from `KnowledgeRepository`, `SimilarityMatchOut`, `evaluate_from_legacy_metrics`, and the endpoints in `app/knowledge/router.py`:

```
strategy_kb_view (one document per historical strategy)
├── strategy_id            : str   (opaque identifier used by the legacy engine)
├── canonical_hash         : str   (16-hex — see §canonical.py; family key)
├── pair                   : str   (e.g. "XAUUSD")
├── timeframe              : str   (e.g. "H4")
├── strategy_type          : str   (e.g. "momentum" · "mean_reversion")
├── strategy_text          : str?  (CNL text if preserved)
├── parameters             : dict? (structural knobs; NOT tuning constants)
├── legacy_metrics         : dict
│   ├── profit_factor      : float
│   ├── total_return_pct   : float
│   ├── stability_score    : float
│   ├── max_drawdown_pct   : float
│   ├── win_rate           : float
│   ├── total_trades       : int
│   ├── oos_holdout        : bool | null
│   └── pass_probability   : float?  (legacy — flagged as 0% across the corpus)
├── rescored               : dict?  (Phase 1.5 six-dimension re-evaluation, if run)
├── learning_only          : bool   (ALWAYS true — enforced by repository)
└── eligible_for_deploy    : bool   (ALWAYS false — enforced by repository)
```

```
strategy_kb_champions (one document per family category)
├── category  : str          (e.g. "top_profitability", "top_robustness", …)
└── rows      : list[dict]   (embedded KB row references or copies)
```

### 1.3 Observed properties

Documented in `app/knowledge/evaluation.py` and the Phase 1.5 audit references:

- Legacy `verdict` field conflates *overfit risk* with *P&L outcome*.
- 100 % of the imported corpus carried `verdict=RISKY`.
- 28 % of the corpus produced positive returns with PF > 1.0 despite the RISKY label.
- Zero rows currently satisfy `oos_holdout=true` → readiness ceiling is `PENDING_VALIDATION` (never `READY`).
- Pass-probability legacy field is unreliable (Phase 1.5 §10.A4 flag).

**Implication.** The historical corpus contains real signal, but is not fit-for-purpose evidence under the current framework. Its value is **as neighbours for composition**, not as candidates for deployment.

---

## 2 · Canonical model review (target architecture)

### 2.1 Where new strategies live

- **Database** — primary Mongo DB (env `MONGO_URL`, `DB_NAME`).
- **Collection** — `strategies`.
- **Access class** — `StrategyRepository` (safety filter `eligible_for_deploy != False`).

### 2.2 Row shape (from `StrategyOut` + `create_strategy`)

```
strategies (one document per composed strategy)
├── strategy_id  : str   (16-hex uuid; assigned at insert)
├── name         : str
├── description  : str?
├── symbol       : str?
├── timeframe    : str?
├── ir           : dict? (intermediate representation, if authored via Lab)
├── tags         : list[str]
├── status       : "draft" | "backtested" | "champion" | "deployed" | "retired"
├── created_by   : str   (user_id)
├── created_at   : datetime (utc)
└── updated_at   : datetime (utc)
```

Guardrails that **are architecturally required** but **not yet materialised** as columns on the production row (they exist on KB rows):

- `learning_only` — post-freeze, imported rows must carry this permanently.
- `eligible_for_deploy` — post-freeze, imported rows must carry this as `false` at insert time.
- `framework_version` — post-freeze, imported rows must carry this as at least `"v1.1.0-stage4"` (per §4.3).

Adding these three fields is a **schema addition**, not a schema change — the `StrategyRepository.SAFETY_FILTER` already treats missing `eligible_for_deploy` as visible (backward-compat clause in `repository.py` line 79-82). New rows with the field set to `false` become invisible to production reads by construction, without breaking legacy rows.

### 2.3 Passport as the observation surface

Per §10, the Passport is a **view** composed from `strategies` + evidence + Timeline events. The migration does not need to write anything Passport-specific — the Passport surface is already emergent from the row + timeline. This is a key simplification: **the migration deliverable is one Passport per imported entry, purely by consequence of writing the row + the import event.**

---

## 3 · Schema differences (KB → canonical)

| Legacy field (`strategy_kb_view`) | Canonical field (`strategies`) | Type of change | Notes |
|---|---|---|---|
| `strategy_id` | `strategy_id` | **REKEY** | Legacy id preserved in `provenance.legacy_strategy_id`. Canonical row gets a fresh 16-hex uuid to avoid ambient collisions and keep production id-space monotonic. |
| `canonical_hash` | `canonical_hash` | **PRESERVE** | Copy verbatim. Deterministic — recomputable from text + param keys via `canonical_hash()`. Used as the family key + rollback key. |
| `pair` | `symbol` | **RENAME** | Same semantics; the canonical model uses `symbol` (aligned with market data taxonomy). Case preserved. |
| `timeframe` | `timeframe` | **PRESERVE** | 1:1. |
| `strategy_type` | `tags` (append `"kb-type:<value>"`) | **DEMOTE TO TAG** | Canonical model has no dedicated `strategy_type` field. Preserved as a tag prefix. |
| `strategy_text` | `description` (if `description` is empty) + `ir.cnl_text` | **RELOCATE** | Legacy corpus stored raw CNL text; canonical model has `description` + optional `ir`. Preserve full text — never truncate. |
| `parameters` | `ir.parameters` | **NEST** | Fold into the intermediate representation. Preserve exactly. |
| `legacy_metrics.*` | `evidence.legacy_metrics.*` | **NEST + FREEZE** | Move under a new `evidence` subdocument (added post-freeze). Never rewrite legacy values — treated as immutable historical measurement. |
| `rescored.*` (if present) | `evidence.rescored_phase15.*` | **NEST + FREEZE** | Preserve Phase 1.5 six-dimensional re-evaluation for audit continuity. |
| `learning_only=true` | `learning_only=true` | **PRESERVE PERMANENTLY** | Never flippable for imported rows. |
| `eligible_for_deploy=false` | `eligible_for_deploy=false` | **PRESERVE + LOCK** | Only a fresh Strategy Lab composition + fresh Passport gate can produce an `eligible_for_deploy=true` row. Imported row can never gain eligibility in place. |
| — (not in legacy) | `framework_version` | **NEW** | Required per §4.3. Set to the framework version active at import time, minimum `"v1.1.0-stage4"`. |
| — | `provenance.source` | **NEW** | Enum: `"kb_import"`. Distinguishes from `"lab"` / `"future:kb-derived-fresh"`. |
| — | `provenance.legacy_strategy_id` | **NEW** | The pre-import KB id, for audit reversibility. |
| — | `provenance.legacy_collection` | **NEW** | `"strategy_kb_view"` or `"strategy_kb_champions"`. |
| — | `provenance.legacy_family_category` | **NEW** | For champions imports, the category label from the KB. |
| — | `provenance.imported_at` | **NEW** | UTC ISO string. |
| — | `provenance.imported_by` | **NEW** | User id of the admin who authored the batch. |
| — | `provenance.batch_id` | **NEW** | Groups a single migration batch — used for one-shot rollback (§7). |
| — | `provenance.kb_snapshot_hash` | **NEW** | SHA-256 over the KB source row (JSON, sorted keys) at import time. Freezes the read against which we imported. |
| — | `status` | **SET** | Initial status is `champion` (see §5 promotion rules) — the KB entries survived the Phase 1.5 audit and earned family membership. |

**Zero destructive operations on KB.** Every "PRESERVE" / "RELOCATE" / "NEST" above reads the KB row; nothing writes back to `strategy_knowledge_base`.

---

## 4 · Mapping rules (canonical procedure per KB row)

Written in prose so the eventual implementer cannot mistake the intent. This is **not** code — it is the *specification*.

```
INPUT
  kb_row       :  one document from strategy_kb_view (or a champion embedded row)
  batch_ctx    :  {batch_id, imported_by, imported_at, framework_version}

OUTPUT
  candidate_doc :  the document that would be inserted into `strategies`
                   (nothing is inserted in this pass — mapping is pure).

STEPS
  1.  Compute canonical_hash from kb_row.strategy_text + kb_row.parameters
      using canonical_hash() — MUST equal kb_row.canonical_hash. If it does
      not, mark row REJECTED (see §5.RV-01). Preserve the mismatch value in
      provenance.integrity_note.

  2.  Assign a fresh strategy_id (uuid4().hex[:16]). NEVER reuse the KB id.

  3.  Build name deterministically:
        name = f"[KB] {kb_row.strategy_type or 'strategy'} · {kb_row.pair} · {kb_row.timeframe} · {kb_row.canonical_hash[:8]}"
      Deterministic naming makes re-runs of the mapper idempotent by hash.

  4.  Copy fields:
        description   = kb_row.strategy_text   (verbatim)
        symbol        = kb_row.pair
        timeframe     = kb_row.timeframe
        ir            = { cnl_text: kb_row.strategy_text,
                          parameters: kb_row.parameters or {} }
        tags          = ["kb-import",
                         f"kb-type:{kb_row.strategy_type}",
                         f"kb-hash:{kb_row.canonical_hash}"]

  5.  Guardrails (permanent):
        learning_only        = True
        eligible_for_deploy  = False
        framework_version    = batch_ctx.framework_version

  6.  Evidence bundle (immutable):
        evidence.legacy_metrics       = kb_row.legacy_metrics
        evidence.rescored_phase15     = kb_row.rescored (if present)
        evidence.readiness_ceiling    = "pending_validation"

  7.  Provenance:
        provenance.source                 = "kb_import"
        provenance.legacy_strategy_id     = kb_row.strategy_id
        provenance.legacy_collection      = source collection name
        provenance.legacy_family_category = category if imported via champions
        provenance.imported_at            = batch_ctx.imported_at
        provenance.imported_by            = batch_ctx.imported_by
        provenance.batch_id               = batch_ctx.batch_id
        provenance.kb_snapshot_hash       = SHA256(json.dumps(kb_row, sort_keys=True))

  8.  Initial state:
        status     = "champion"    (see §5 for the rationale + gates)
        created_by = provenance.imported_by
        created_at = batch_ctx.imported_at
        updated_at = batch_ctx.imported_at
```

**Idempotency property.** Running the mapper twice on the same `kb_row` with the same `batch_ctx` produces the same `candidate_doc` except for `strategy_id` (uuid). If the actual insert step consults `provenance.legacy_strategy_id` + `provenance.batch_id` for uniqueness (§5.RV-04), a repeat run is a no-op.

---

## 5 · Validation rules

Every mapped row must pass **every** rule below or be REJECTED. Rejection produces a Timeline event `kb_family_import_rejected` (§13.1 vocabulary — additive name, not implemented in this doc) and does **not** produce a row.

| Code | Rule | Rationale |
|---|---|---|
| **RV-01** | `canonical_hash(strategy_text, parameters) == kb_row.canonical_hash` | Bit-rot detection. If the recomputed hash disagrees, either the algorithm drifted or the row was mutated post-freeze; either is disqualifying. |
| **RV-02** | `strategy_text` is present and non-empty | Without CNL text the row is unauditable and cannot be reproduced by the Lab. |
| **RV-03** | `pair` and `timeframe` are non-empty strings and pass basic taxonomy check (symbol in known Coverage table; timeframe in `{M1,M5,M15,M30,H1,H4,D1,W1}` or documented extension) | Rejects malformed legacy rows before they pollute production filters. |
| **RV-04** | No existing `strategies` row has both `provenance.legacy_strategy_id == kb_row.strategy_id` **and** `provenance.batch_id == batch_ctx.batch_id` | Idempotency guard — reruns don't double-insert. |
| **RV-05** | No existing `strategies` row has `provenance.legacy_strategy_id == kb_row.strategy_id` from a **prior** batch, unless the prior row is in status `retired` | An imported KB entry can only exist once as an active canonical row. Reimport requires prior retirement (with a timeline event). |
| **RV-06** | `legacy_metrics.total_trades >= 30` **OR** operator explicitly overrides via approval reason | Excludes near-zero-trade rows from the initial champion pool. Threshold is per-batch configurable; 30 is the minimum for Phase 1.5-style stability scoring. |
| **RV-07** | `learning_only == True` on the source row | Structural safety — never import a row that claims deploy-eligibility. |
| **RV-08** | `strategy_text` does not contain provenance annotations that break `canonical_hash` (`DERIVED FROM:` / `SOURCE:` / `ORIGIN:`) | These annotations are scrubbed by `normalise_strategy_text` — presence here means the row was authored by a mutation pipeline whose lineage is elsewhere; require the referenced ancestor to be imported first (dependency ordering). |
| **RV-09** | Family membership: if importing from `strategy_kb_champions`, the row's `canonical_hash` must appear in the KB's family aggregation for its category | Prevents category cross-contamination during hand-picked champion imports. |
| **RV-10** | `framework_version` string in `batch_ctx` matches the current backend `settings.framework_version` (post-freeze) | Prevents importing under a version tag that lies about the running framework. |

**Batch-level validation.** Before any row is inserted, the whole batch must pass:

- **BV-01** — Batch size ≤ configured cap (initial recommendation: 25 rows per batch).
- **BV-02** — All source rows share the same `learning_only=True` invariant (already guaranteed by `KnowledgeRepository`, but re-asserted).
- **BV-03** — No row's canonical hash matches an *active* (non-retired) `strategies` row from **outside** the KB import pipeline (i.e. an operator has not composed a same-family draft in the Lab). If so, hold that row for a merge decision (§5.MRG-01, below).

**Merge / conflict resolution.**

- **MRG-01** — When a Lab-composed row already exists with the same `canonical_hash`: the migration **does not** merge. It attaches an annotation to the Lab row (`provenance.kb_family_neighbours += [legacy_strategy_id]`) and skips inserting the KB row. The Passport view then displays both, but only the Lab row is a candidate.
- **MRG-02** — When two KB rows in the same batch share `canonical_hash`: import the one with the higher `evidence.legacy_metrics.total_trades`; annotate the other as a family sibling in `provenance.kb_family_siblings`.

---

## 6 · Promotion rules

### 6.1 Entry state

Imported rows enter the canonical lifecycle at **`champion`** — not `draft`.

Rationale: they *already survived* the Phase 1.5 audit and earned membership in a `strategy_kb_champions` family. Placing them in `draft` would falsely imply they are pre-evidence. Placing them in `backtested` would falsely imply they carry an evidence bundle under the current framework. `champion` matches §4.1's semantics: *"has earned membership in a canonical family (KB) OR passes the current-framework Passport gate."*

**However**, `champion` is *not* the same as *deployable*. Per §4.1 and §4.2, `champion` is the *only* state where "canonical hash + evidence bundle" is complete — and the evidence bundle for imported rows is explicitly stamped `readiness_ceiling: pending_validation`. This is architecturally coherent: imported rows are champions of the legacy corpus, not deployable candidates.

### 6.2 Locked transitions

| From | To | Allowed for KB-imported row? | Rule |
|---|---|---|---|
| champion | deployed | **NO — architecturally forbidden** | §10.4 · §4.3 · §18.3 invariant 2. An imported row can never reach `deployed`. |
| champion | retired | Yes (human) | Retirement is always allowed. Timeline event `operator_strategy_retired`. |
| champion | draft | **NO** | Would falsely imply the row was newly composed. If a re-composition is desired, the operator opens Strategy Lab and drafts a **new** row using the imported one as a nearest-neighbour reference. |
| champion | backtested | **NO** | Backward move; not defined in §4.1. |
| retired | draft | **NO for imported rows** (§4.1 permits it in general) | Imported rows are terminal at `retired`. Reinstating them would break the "one-way import" property. |

### 6.3 Promotion path for KB-derived deployment

The *only* way a KB entry contributes to a deployed strategy is the **derive-then-recompose** path:

```
strategy_kb_view row (learning-only forever)
   │
   │  1. imported → strategies row (status=champion, learning_only=true, framework=v1.1.0-stage4)
   ▼
Strategy Passport (view · learning_only permanent · no PROMOTE-to-deployed CTA rendered)
   │
   │  2. operator reads the imported Passport in the Lab as a nearest-neighbour reference
   │     (POST /api/knowledge/nearest already exposes this — no new endpoint)
   ▼
new Strategy Lab draft (status=draft, learning_only=false, framework=v1.1.0-stage4)
   │
   │  3. optimize · validate · earn evidence · Passport gate
   ▼
new Passport (status=champion, eligible_for_deploy pending gate)
   │
   │  4. §12 Approvals modal · human · two-person rule if live
   ▼
deployed
```

The imported row is the **ancestor**, never the *deployed object*. This satisfies §18.3 invariant 2 (KB never talks to Execution) without adding a new architectural rail.

### 6.4 Passport UX consequences

The already-shipped `StrategyPassport.jsx` (§10) requires **no changes** to support this. Two data-driven behaviours emerge automatically:

- `tags` contains `"kb-import"` → the Guardrail chip "Learning only" already tests `/kb|import|learning/i` (see `StrategyPassport.jsx` line 330) → the chip renders `LEARNING ONLY`.
- `NEXT_TRANSITION` table (in `StrategyPassport.jsx`) currently maps `champion → 'Deploy to Paper'`. For KB-imported rows the PROMOTE CTA must be **hidden** (not merely disabled) because the transition is not just deferred — it is architecturally forbidden. This is the **one** frontend change implied by the migration, and it is planning-only for now.

---

## 7 · Evidence preservation

The KB corpus is compliance-relevant historical measurement. It must survive the migration losslessly.

### 7.1 Preservation contract

- **The KB collections are never mutated.** `KnowledgeRepository` already refuses writes; the migration only reads.
- **Every legacy field is preserved verbatim on the imported row** under `evidence.legacy_metrics` (see §4 step 6). No re-scaling, no unit conversion, no rounding beyond what pymongo already does.
- **The Phase 1.5 six-dimensional re-scoring** (if attached) lives under `evidence.rescored_phase15`, distinct from any post-freeze re-scoring.
- **The KB snapshot hash** (`provenance.kb_snapshot_hash`) locks the exact byte sequence that was imported. If the KB is later re-audited under a new algorithm, the hash difference is provable.

### 7.2 Evidence bundle shape (post-freeze schema addition)

The `evidence` subdocument is a new, additive column on `strategies` (safe under §4.3):

```
evidence: {
  legacy_metrics:      { … verbatim copy of kb_row.legacy_metrics … },
  rescored_phase15:    { … verbatim copy of kb_row.rescored …    }?,
  readiness_ceiling:   "pending_validation",   // never "ready" for imports
  framework_version:   "v1.1.0-stage4",
  imported_from:       "strategy_knowledge_base",
  snapshot_hash:       "<sha256>",
}
```

**Post-freeze `backtests` collection compatibility.** Per §4.2 the `backtests` collection is post-freeze and stores replay hash + P&L series. Imported rows have neither — they carry `legacy_metrics` instead. When `backtests` lands, its schema must include a discriminator so downstream code can distinguish "this evidence was replayed under the current framework" (produces a `backtests` document) from "this evidence is historical" (points at `evidence.legacy_metrics` only). The migration produces the second kind; the first kind is only ever produced by the Lab → Optimize → Validate path.

### 7.3 Timeline evidence

Every action in the migration writes a §13 event. Under the current shim (client-side) events are session-scoped; **when the backend Timeline endpoint arrives**, migration events become part of the compliance-relevant, indefinitely-retained governance ledger (§19.3).

| Event name (§13.1 vocabulary) | When emitted | Category (§19.3) |
|---|---|---|
| `admin_kb_batch_authored` | Operator opens the Approvals modal for a batch | Governance |
| `admin_kb_batch_approved` | Approvals modal Confirm succeeds | Governance |
| `admin_kb_batch_rejected` | Operator cancels or approval fails | Governance |
| `kb_family_imported` | One row successfully inserted into `strategies` | Composition |
| `kb_family_import_rejected` | One row fails a validation rule (§5) | Composition |
| `kb_family_skipped_merge` | One row skipped per MRG-01 (Lab row exists) | Composition |
| `admin_kb_batch_rolled_back` | Rollback command run against a batch_id | Governance |
| `kb_family_reverted` | One row deleted by rollback | Composition |

None of these are net-new naming inventions — they follow §13.1's `<actor>_<object>_<verb>` template. This document does not implement them; it names them so the eventual implementer's Timeline entries are already agreed.

---

## 8 · Rollback & audit strategy

### 8.1 Rollback primitives

Rollback is defined at three granularities. The migration tool must implement **all three**; the operator picks based on the incident.

| Level | Selector | Effect |
|---|---|---|
| **Row** | `provenance.legacy_strategy_id` | Deletes exactly one `strategies` row. Emits `kb_family_reverted`. |
| **Batch** | `provenance.batch_id` | Deletes every `strategies` row created in that batch. Emits one `admin_kb_batch_rolled_back` plus N `kb_family_reverted`. Idempotent — a second run finds no rows and no-ops. |
| **Canonical hash** | `provenance.kb_snapshot_hash` | Emergency: deletes any `strategies` row imported from a specific bytes-locked KB source, regardless of batch. Used when a specific KB row is later found to be corrupt. |

### 8.2 Rollback constraints (safety)

- Rollback only touches rows whose `provenance.source == "kb_import"`. A single guard clause prevents deleting Lab-composed rows even if a family-hash collision existed.
- Rollback **refuses** to delete any row whose status has moved off `champion` — if an imported row was retired (`retired`), rolling back would break the audit trail. Rolled-back rows must still be `champion` (i.e. never touched post-import).
- Rollback is Human tier only (§20.1) — always through the §12 Approvals modal.
- Rollback of a batch invalidates every neighbour annotation created by that batch (MRG-01), reverting the Lab rows' `provenance.kb_family_neighbours` fields to their prior state. This is a compensating write, always accompanied by a Timeline event.

### 8.3 Audit posture

- **Read audit.** The KB itself is read by `KnowledgeRepository` — a class that logs every filter it merges (via `_merge_filter`'s exception surface). No structural change needed.
- **Write audit.** Every `strategies` insert from the migration path carries `provenance.imported_by` + `provenance.imported_at` + `provenance.batch_id`. Combined with the Timeline events (§7.3), the audit trail answers *"who imported which KB row into which canonical row at what time and under what framework"* with no ambiguity.
- **Snapshot audit.** `provenance.kb_snapshot_hash` allows an auditor to prove that the row inserted into `strategies` matches (byte-for-byte, after JSON canonicalisation) the row that lived in the KB at import time. If the KB is later touched under an admin session, the hash mismatch is detectable.
- **Read-side monitoring.** The Command surface's future Approvals inbox (post-Slice δ) subscribes to Timeline `kb_family_*` events and surfaces batches under audit.

### 8.4 Non-destructive audit path

An auditor never needs write access. Everything required to verify a batch is either:

- In the KB (unchanged, byte-locked by `snapshot_hash`),
- In the `strategies` row's `provenance` and `evidence` subdocuments,
- In the Timeline events.

The full pipeline is `read KB → recompute snapshot_hash → compare to imported row → replay Timeline events for the batch_id`. Nothing in this loop mutates anything.

---

## 9 · Freeze compliance

Every action in this specification maps to primitives that already exist under Backend Feature Freeze v1.1.0-stage4:

| Migration action | Backing primitive | New backend code? |
|---|---|---|
| Read KB row | `KnowledgeRepository.find` / `find_one` | **NO** |
| Compute canonical_hash | `app.knowledge.canonical.canonical_hash` | **NO** |
| Insert `strategies` row | `POST /api/strategies` (or admin bulk equivalent) | **NO** *(existing endpoint)* |
| Add `provenance`, `evidence`, `learning_only`, `eligible_for_deploy`, `framework_version` columns | Schema additions — safe additive change | **DEFERRED** (post-freeze) |
| Emit §13 events | `timelineShim` (frontend, session-scoped) → real `POST /api/timeline/events` (post-freeze) | **DEFERRED** |
| Rollback | Existing `DELETE /api/strategies/{id}` + Timeline event | **NO** *(existing endpoint)* |
| §12 Approvals modal | Already shipped (Slice γ) | **NO** |
| Passport hides PROMOTE for imported rows | One-line frontend change on `NEXT_TRANSITION` | Frontend only |

**Net-net.** Zero backend changes are required to *plan* the migration. Two are required to *execute* it:

1. Add three schema fields (`learning_only`, `eligible_for_deploy`, `framework_version`) plus `provenance` and `evidence` subdocs to the `strategies` collection — safe additive.
2. Add a real Timeline endpoint (or accept the shim's session scope during the pilot batch).

Neither is proposed here. Both are candidates for the *first* backend-thaw slice, after this specification is accepted.

---

## 10 · Phased execution plan (still architecture-only)

Once this spec is accepted, the eventual work breaks into four phases. **This document ships all four for review — it does not execute any of them.**

### Phase M0 · Dry-run mapper (frontend-safe, freeze-safe)

- Build the mapper (§4) as a **pure function** with no side effects. Given a KB row + batch_ctx, it returns a candidate document.
- Frontend-only preview surface at `/c/admin/kb-migration` behind admin role gate. Reads KB via existing endpoints, renders the *would-be* Passport for each row, badges every RV-code that fails.
- **No writes anywhere.** Delivered purely as a review tool.

### Phase M1 · Small-batch pilot (post-freeze)

- Add the schema additions to `strategies` (§9 item 1).
- Add the real Timeline endpoint (§9 item 2).
- Import a **single hand-picked batch of ≤ 5 rows** through the §12 Approvals modal.
- Full audit trail review after each import.

### Phase M2 · Batched migration (post-freeze)

- Configurable batch size (BV-01), up to the recommended cap of 25.
- Progress surface on the Command Approvals inbox.

### Phase M3 · Ongoing hygiene (post-freeze)

- Rollback tooling drills.
- Champion family re-audit under the current framework.
- Neighbour annotations backfill for Lab drafts composed pre-migration.

---

## 11 · Open questions for the user

Explicit prompts, so review can converge:

1. **Batch cap.** Recommended initial cap is 25 (BV-01). Confirm or set your own bound.
2. **Trade threshold.** RV-06 defaults to `total_trades >= 30`. Confirm the threshold; lower/higher/leave-unspecified.
3. **Naming convention.** §4 step 3 produces names like `[KB] momentum · XAUUSD · H4 · 84d32cc1`. Approve, or specify alternative.
4. **Champion category import.** Should the initial pilot import (M1) draw from *all* categories of `strategy_kb_champions`, or restrict to one (e.g. `top_profitability`)? Default recommendation: one category.
5. **Framework tag.** Confirm `framework_version="v1.1.0-stage4"` is the value we stamp — or advance to the version at import time.
6. **Passport CTA policy for KB rows.** §6.4 recommends hiding the PROMOTE CTA entirely for `provenance.source == "kb_import"` rows. Approve, or prefer disabled-with-reason?
7. **Retirement of imported rows.** §6.2 forbids `retired → draft` for imports. Confirm — or allow with two-person rule?
8. **Merge policy.** MRG-01 says a Lab row wins any hash conflict. Confirm.
9. **Rollback tier.** §8.2 puts rollback at Human tier only. Confirm — or allow admin recommendation-only under Phase β autonomy?
10. **Neighbour annotation on Lab rows.** MRG-01 writes `provenance.kb_family_neighbours` to existing Lab rows. This is a *mutation to a Lab-composed row's provenance*. Approve, or prefer a separate join table?

---

## 12 · What this document is not

- Not a code plan. No file names, no function signatures, no test scaffolding.
- Not a UX design. §6.4 mentions the Passport implication but does not propose visual changes.
- Not a schedule. Phases M0–M3 are ordered, not dated.
- Not a scope for Execution Workspace, Broker Connections, Paper Trading, or Live Deployments. Those remain deferred until this specification is reviewed and accepted, per user directive.

---

## 13 · Approval

- [ ] Reviewed by user (name · date)
- [ ] Open questions §11 answered
- [ ] Ready for Phase M0 (dry-run mapper) authoring — pending explicit user approval

Once accepted, this document is added to `docs/` as canonical migration reference. Future work must cite it the same way implementation slices cite `ARCHITECTURE.md`.
