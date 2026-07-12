# ASF_PACKAGE_V1_SPEC.md — Strategy Archive Framework Package Specification

**Schema version:** `1.0`
**Status:** **LOCKED — planning lock-in only. No code implements this yet.**
**Locked on:** 2026-06-13
**Locked by:** receiving agent, on operator authorisation
**Companion docs:**
* `ASF_BACKEND_ARCHITECTURE.md` — module layout, API surface, persistence, scheduler placeholder.
* `MIGRATION_EXPORT_PLAN.md` — 1-vCPU → ASF export-format contract (first concrete producer of this spec).
* `MIGRATION_PRIORITY.md` — T1/T2/T3 tier policy (consumed by the migration adapter when it implements this spec).
* `POST_IMPORT_PIPELINE.md` — 6-stage pipeline that consumes imported packages.

**Authority:** This document is the **single source of truth for ASF Package v1.0 wire-format.** Every ASF reader and writer — current and future — MUST honour it. Any change to v1.0 semantics requires a new minor version (1.1, 1.2, …) and BOTH versions must remain readable by all current producers for at least one release cycle.

---

## 1. Scope and intent

The ASF Package is a **single-file, lossless, deterministic, schema-versioned bundle** that carries one or more strategies + their full lineage, evidence, certification, scoring, portfolio assignments, Master Bot membership, and calibration snapshots, such that:

1. The receiver can **rematerialise** the strategies into a canonical `strategy_library` (and downstream collections) with byte-faithful fingerprints.
2. The receiver can **re-derive** every score and verdict by replaying the included calibration snapshot — never blind-trusting the exported numerics.
3. The receiver can **detect duplicates** via two independent identity dimensions (`fingerprint` — bucketed-params; `strategy_hash` — text-exact).
4. The receiver can **walk the lineage** (parent ↔ child mutation edges) without external state.
5. **Future marketplace, DR, server-transfer, portfolio-portability, and long-term preservation use cases are all satisfied by the same wire-format** — only the optional `extensions.*` envelope changes per use case.

The spec is **deliberately additive-only.** Receivers MUST preserve unknown keys on round-trip so that a v1.0 reader handling a v1.1 producer's package never corrupts state.

---

## 2. Container format

ASF Packages are **renamed ZIP archives** with extension `.asfpkg`.

Rationale:
* The existing `.cbotpack` (`backend/engines/master_bot_pack.py`) is already a renamed ZIP — operator and tooling familiarity.
* `MIGRATION_EXPORT_PLAN.md §3.C` already specifies a ZIP wrapper as one of the accepted import formats.
* `POST /api/data/backup/import` already accepts ZIP — receiver codepath is reusable.
* Cross-platform: every OS handles ZIP natively.

Filename convention:

```
asf_pkg_<TYPE>_<SHORT_SUBJECT_FP>_<YYYYMMDD>_<HHMMSS>.asfpkg
```

Where:
* `<TYPE>` ∈ `{strategy, portfolio, master_bot, full_pod, migration}`
* `<SHORT_SUBJECT_FP>` is the first 8 hex chars of the primary subject's identity hash (strategy `fingerprint` · portfolio `portfolio_id` · MB `master_bot_id` · `"pod"` for `full_pod` · `"1vcpu"` for the migration adapter).
* Timestamp is UTC, ISO-compact, no separators.

Example: `asf_pkg_strategy_3f2a51ec_20260613_103045.asfpkg`

---

## 3. Package layout

```
<root>/
├── manifest.json                       ← v1 schema; SHA-256s; counts; provenance  (REQUIRED)
├── README.md                           ← human-readable summary + restore instructions  (REQUIRED)
├── strategies/
│   ├── <fingerprint>.json              ← one file per strategy (§4)
│   └── ...                                (REQUIRED — at least one when type != "full_pod" empty)
├── lineage/
│   ├── mutation_events.jsonl           ← parent→child rows; one row per line
│   └── mutation_stability_log.jsonl    ← per-mutation stability snapshots
├── lifecycle/
│   ├── stages.jsonl                    ← strategy_lifecycle rows
│   └── history.jsonl                   ← strategy_lifecycle_history rows (incl. event_type="bi5_cert")
├── evidence/
│   ├── performance_history.jsonl       ← strategy_performance_history rows
│   ├── alerts.jsonl                    ← auto_factory_alert_log rows
│   └── audit_excerpts.jsonl            ← scoped audit_log rows (90-day window)
├── certifications/
│   ├── bi5_strategy/<strategy_hash>.json     ← per-strategy cert verdict
│   └── bi5_data/<symbol>__<window>.json      ← per (symbol, window) data cert
├── scoring/
│   ├── explorer_scores.jsonl                 ← per-strategy snapshot at export time
│   └── ranker_contributions.jsonl            ← per-candidate breakdown at export time
├── portfolios/                         ← REQUIRED iff type ∈ {portfolio, master_bot, full_pod}
│   ├── portfolio_<id>.json
│   └── assignments.jsonl               ← strategy → portfolio mapping rows
├── master_bot/                         ← REQUIRED iff type ∈ {master_bot, full_pod}
│   ├── definition.json                 ← immutable revision payload
│   ├── members.jsonl                   ← per-tier roster rows
│   ├── ranker_weights_snapshot.json    ← weights captured at export time
│   ├── MainSource.cs                   ← cAlgo source (carried from existing MB-7)
│   └── Properties.xml                  ← cAlgo manifest (carried from existing MB-8)
└── cert_calibration/                   ← REQUIRED — receiver uses these to replay scores
    ├── tick_validator_version.txt      ← e.g. "tick_validator@P0B-v2"
    ├── density_table_snapshot.json     ← DENSITY_TABLE at export time
    ├── thresholds.json                 ← PASS_THRESHOLD + WARN_THRESHOLD at export time
    └── ranker_version.txt              ← e.g. "master_bot_ranker@v1.1"
```

Empty sections MUST be omitted entirely (no empty directories). Receivers MUST treat absence as "no rows in that category", NOT as an error.

The `extensions/` directory MAY be added with arbitrary subdirectories. Receivers MUST preserve `extensions/` byte-faithful on round-trip.

---

## 4. Strategy document — `strategies/<fingerprint>.json`

```jsonc
{
  // ── Envelope ──────────────────────────────────────────────────────
  "asf_schema_version": "1.0",
  "exported_at":        "<UTC ISO 8601>",
  "exporter": {
    "pod_host_id":  "<host_id>",
    "build_label":  "BUILD 30.4",
    "git_sha":      "<full git SHA at export time>",
    "exporter_module": "engines.asf.exporter.single_strategy@v1"
  },

  // ── Identity (immutable; PERMANENT key) ────────────────────────────
  // `fingerprint` is the bucketed-params SHA-1 from
  // engines/strategy_library._fingerprint(). It IS the primary identity
  // across pods. NEVER overwrite on round-trip.
  "fingerprint":        "<SHA-1, 40 hex chars>",
  "fingerprint_inputs": {
    "pair":          "EURUSD",
    "timeframe":     "H1",
    "style":         "trend_follow",
    "params_canon":  "<output of _canon_params() — frozen string>",
    "strategy_text": "<full normalised text used in fingerprint>"
  },
  // `strategy_hash` = SHA-256 over strategy_text (text-exact dedup).
  // NOT used as primary key — used to detect "same text, different
  // bucketing" rare cases (different PARAM_BUCKET_PCT etc.).
  "strategy_hash":      "<SHA-256, 64 hex chars>",

  // ── Strategy definition (≥ 1 required; both preferred) ─────────────
  "strategy_text":   "<raw human-readable definition>",
  "strategy_ir":     {
    // Phase 28-C IR schema. When present, the receiver can
    // re-transpile to .cs without needing the source pod.
    "schema_version": "28-C",
    "ir":             { /* ... */ }
  },
  "params":          { "sl_pips": 50, "rsi_len": 14, "...": "..." },

  // ── Performance metrics (snapshot at export time) ──────────────────
  "metrics": {
    "total_trades":     142,
    "profit_factor":    1.43,
    "win_rate":         0.51,
    "max_drawdown_pct": 0.14,
    "sharpe":           1.2,
    "sortino":          1.9,
    "calmar":           0.9,
    "stability_score":  0.78,
    "computed_at":      "<UTC ISO>",
    "computed_on_data_window": {
      "symbol":           "EURUSD",
      "window_start_utc": "...",
      "window_end_utc":   "..."
    }
  },
  "validation_report": { /* full walk-forward + OOS + slippage report */ },
  "backtest_results":  { /* free-form, as today */ },

  // ── Mutation lineage ───────────────────────────────────────────────
  // Edge data also appears in lineage/mutation_events.jsonl. This
  // inline block is for single-strategy convenience; full graph lives
  // in the JSONL file when depth > 1.
  "lineage": {
    "parent_fingerprint": "abc123..." | null,
    "mutation_family":    "rsi_band_walk",
    "generation":         4,
    "ancestors": [
      { "fingerprint": "...", "generation": 3 },
      { "fingerprint": "...", "generation": 2 },
      { "fingerprint": "...", "generation": 1 }
    ],
    "ancestors_complete": true   // false iff the export truncated
                                  // ancestry beyond the depth limit
  },

  // ── BI5 strategy certification (snapshot) ─────────────────────────
  "bi5_cert": {
    "verdict":              "PASS" | "WARN" | "FAIL" | null,
    "composite_score":      0.87,
    "integrity_score":      1.00,
    "spread_score":         0.94,
    "slippage_score":       0.88,
    "execution_score":      0.91,
    "stability_score":      0.78,
    "evaluator_version":    "bi5_cert_engine@P0B-v3",
    "certified_at":         "<UTC ISO>",
    "early_fail_reason":    null,
    "data_cert_windows": [
      {
        "symbol":           "EURUSD",
        "window_start_utc": "...",
        "window_end_utc":   "...",
        "verdict":          "PASS",
        "bi5_score":        0.86,
        "evaluator_version":"tick_validator@P0B-v2"
      }
    ]
  },

  // ── Explorer scores + ranker contributions (snapshot) ─────────────
  "explorer": {
    "deploy_score":     82.1,
    "pass_probability": 71.3,
    "ranker_contributions": {
      "deploy_score":       0.4105,
      "pass_probability":   0.2852,
      "bi5_cert_verdict":   0.07,
      "bi5_slippage_score": 0.0264
    },
    "ranker_version":   "v1.1",
    "rank":             { "global": 17, "per_cell": 3, "computed_at": "..." }
  },

  // ── Portfolio assignments ─────────────────────────────────────────
  "portfolio_assignments": [
    {
      "portfolio_id":  "<id>",
      "role":          "core" | "diversifier" | "satellite",
      "weight":        0.18,
      "assigned_at":   "<UTC ISO>",
      "active":        true
    }
  ],

  // ── Master Bot membership ─────────────────────────────────────────
  "master_bot_memberships": [
    {
      "master_bot_id":            "<id>",
      "tier":                     1,
      "tier_rank":                2,
      "compiled_into_revision":   7,
      "compiled_at":              "<UTC ISO>",
      "active":                   true
    }
  ],

  // ── Lifecycle stage (snapshot) ────────────────────────────────────
  "lifecycle": {
    "stage":               "IMPORTED_SEED" | "PROVISIONAL" | "PROMOTED"
                           | "DEMOTED" | "RETIRED" | "BANNED",
    "stage_rank":          2,
    "stage_locked_until":  "<UTC ISO> | null",
    "promoted_at":         "...",
    "transitions_count":   4
  },

  // ── Provenance ────────────────────────────────────────────────────
  "provenance": {
    "source":              "auto_factory" | "manual" | "1vcpu_migration"
                           | "import" | "marketplace",
    "source_pod":          "<host_id>",
    "source_codebase":     {
      "git_sha":     "...",
      "build_label": "..."
    },
    "source_export_id":    "<asf_pkg id>",
    "discovered_at":       "<UTC ISO>",
    "requires_revalidation": false,
    "requires_rematching":   false,
    "tier_class":          null | "T1" | "T2" | "T3"
  },

  // ── Extension envelope (forward-compatible) ───────────────────────
  // Receivers MUST preserve unknown keys verbatim on round-trip.
  "extensions": {
    // marketplace.* keys are RESERVED for future marketplace use:
    //   "licence":      "CC-BY-SA-4.0" | "proprietary" | ...,
    //   "attribution":  "<author handle>",
    //   "price":        { "model": "free" | "paid", "sku": "..." },
    //   "signature":    "<PKI sig over package_sha256>"
    // Other namespaces are unrestricted but SHOULD be prefixed with the
    // emitter's identifier to avoid collisions.
  }
}
```

### 4.1 Required vs. optional fields

| Section | Required | Notes |
|---|---|---|
| envelope | ✅ | All fields required. |
| identity | ✅ | `fingerprint` + `fingerprint_inputs` mandatory; `strategy_hash` mandatory. |
| definition | ≥ 1 of `strategy_text` / `strategy_ir` | `params` required; can be `{}`. |
| metrics | ✅ | Empty backtest produces zeros — still present. |
| `validation_report` · `backtest_results` | optional | May be `null`. |
| lineage | ✅ if any mutation parent exists | `parent_fingerprint: null` is the orphan case. |
| `bi5_cert` | optional | `null` allowed when never certified. |
| `explorer` | optional | `null` allowed when never scored. |
| `portfolio_assignments` | ✅ | Always present; empty array allowed. |
| `master_bot_memberships` | ✅ | Always present; empty array allowed. |
| `lifecycle` | ✅ | Always present; default `stage` for un-curated strategies is `PROVISIONAL`. |
| `provenance` | ✅ | Identifies how/where/when the strategy was produced. |
| `extensions` | optional | Default `{}` permissible. |

### 4.2 Field invariants

1. `fingerprint` and `strategy_hash` MUST be computable from `fingerprint_inputs` and `strategy_text` respectively, deterministically, by any conformant reader.
2. `lineage.parent_fingerprint`, if non-null, MUST refer either to (a) another strategy in this package, or (b) to a strategy outside this package whose existence is documented in `provenance.notes`.
3. All `*_score` floats are in `[0.0, 1.0]` unless documented otherwise. Receivers MUST clamp on read.
4. All timestamps are ISO 8601 UTC strings; receivers MUST tolerate both timezone-aware and naive forms (treat naive as UTC).

---

## 5. Lineage / lifecycle / evidence JSONL files

Each `*.jsonl` file is **newline-delimited JSON**: one row per line, UTF-8, LF-only line endings, no trailing newline required.

### 5.1 `lineage/mutation_events.jsonl`

```jsonc
{
  "event_id":           "<uuid>",
  "parent_fingerprint": "<sha1 | null>",
  "child_fingerprint":  "<sha1>",
  "mutation_family":    "rsi_band_walk",
  "mutation_kind":      "param_walk" | "logic_swap" | "exit_swap" | ...,
  "operator":           "<who/what mutated>",
  "occurred_at":        "<UTC ISO>",
  "parent_metrics_snapshot": { /* PF, win_rate, drawdown at mutation time */ },
  "extensions":         {}
}
```

### 5.2 `lineage/mutation_stability_log.jsonl`

```jsonc
{
  "fingerprint":      "<sha1>",
  "stability_score":  0.78,
  "computed_at":      "<UTC ISO>",
  "method":           "<algorithm tag>",
  "inputs":           { /* free-form */ }
}
```

### 5.3 `lifecycle/stages.jsonl`

One row = one entry in `strategy_lifecycle`. Schema is the live collection schema verbatim (see `engines/strategy_lifecycle.py`).

### 5.4 `lifecycle/history.jsonl`

One row = one entry in `strategy_lifecycle_history`, **including R2's additive `event_type="bi5_cert"` rows.** Receivers MUST preserve `event_type` so cohort distribution queries (which filter on `from_stage` / `to_stage`) continue to ignore non-transition rows correctly.

### 5.5 `evidence/performance_history.jsonl`

One row = one snapshot from `strategy_performance_history`. Indexed on receive by `(strategy_hash, timestamp)` for read efficiency in dossier replay.

### 5.6 `evidence/alerts.jsonl`

One row = one alert from `auto_factory_alert_log`. Scoped to subject strategies only (export filter applies).

### 5.7 `evidence/audit_excerpts.jsonl`

One row = one entry from `audit_log` within the **90-day window prior to export**, scoped to subject strategies. The 90-day window is the operator-locked default (`MIGRATION_EXPORT_PLAN.md §2.3`); future versions may parameterise.

---

## 6. Certification snapshots

### 6.1 `certifications/bi5_strategy/<strategy_hash>.json`

One row per `(strategy_hash)` from `bi5_strategy_certifications` — the LATEST certification per strategy. Receivers MUST upsert by `(strategy_hash, pair, timeframe, style, certification_timestamp)`.

### 6.2 `certifications/bi5_data/<symbol>__<window_start_iso>.json`

One row per `(symbol, window_start_utc, window_end_utc)` data certification window referenced by ANY strategy cert in this package. Receivers MUST upsert by the same composite key. The window is captured **verbatim from `bi5_data_certification`** — receivers can replay the verdict computation against the cached BI5 archive on the receiving pod to verify the math (the `cert_calibration/` snapshot tells them how).

---

## 7. Scoring snapshots

### 7.1 `scoring/explorer_scores.jsonl`

One row per `(strategy_hash, ranker_version)` carrying `deploy_score`, `pass_probability`, the four BI5 R2 ranker contributions, and the per-cell + global rank at export time. Used by receivers to compare "did my reranking on the new pod produce the same scores?" and surface drift.

### 7.2 `scoring/ranker_contributions.jsonl`

One row per `(candidate_strategy_hash, ranker_version)` carrying the full per-signal contribution breakdown (`engines/master_bot_ranker._compute_candidate_score()` output). Verbose; primarily for forensic replay and Phase 13 dossier evidence.

---

## 8. Portfolio + Master Bot sections

Required iff the package `TYPE ∈ {portfolio, master_bot, full_pod}`.

### 8.1 `portfolios/portfolio_<id>.json`

Full row from `portfolio_lifecycle` + the latest row from `portfolio_scaling_runs` for that portfolio. Receivers upsert by `portfolio_id`.

### 8.2 `portfolios/assignments.jsonl`

One row per `(portfolio_id, strategy_hash)` from `portfolio_signals` — the strategy→portfolio mapping table. Receivers upsert by the composite key; weights and roles are overwritten on conflict (last-write-wins per `assigned_at`).

### 8.3 `master_bot/definition.json`

The immutable revision payload from `master_bot_definitions.(master_bot_id, revision)`. Schema is byte-faithful to the live collection — MB-7's revision-locking guarantees this is safe.

### 8.4 `master_bot/members.jsonl`

One row per `(master_bot_id, tier, tier_rank, strategy_hash)` from `master_bot_members`.

### 8.5 `master_bot/ranker_weights_snapshot.json`

Verbatim copy of `master_bot_ranker_config.default` AT EXPORT TIME. Receivers MUST NOT auto-apply this to the receiving pod's ranker config — it is informational only. If the receiver wants to adopt the snapshot's weights, they invoke the existing `POST /api/master-bot/ranker/config` endpoint explicitly.

### 8.6 `master_bot/MainSource.cs` + `Properties.xml`

Carried verbatim from the producing pod's MB-7 / MB-8 export. Receivers MUST treat these as opaque blobs — no schema parsing required.

---

## 9. Calibration snapshot

`cert_calibration/` is **mandatory in every package.** Without it, the receiver cannot replay scores.

| File | Contents |
|---|---|
| `tick_validator_version.txt` | Single-line ASCII, e.g. `tick_validator@P0B-v2` |
| `density_table_snapshot.json` | Full `DENSITY_TABLE` at export time (from `engines/tick_validator.py`) |
| `thresholds.json` | `{ "PASS_THRESHOLD": 0.85, "WARN_THRESHOLD": 0.70 }` |
| `ranker_version.txt` | Single-line ASCII, e.g. `master_bot_ranker@v1.1` |

On import, the receiver compares its current calibration to the snapshot. Drift surfaces a `calibration_drift_warning` in the import receipt — the import proceeds (scores are advisory anyway) but the operator is informed.

---

## 10. Manifest — `manifest.json`

```jsonc
{
  "asf_schema_version":  "1.0",
  "package_type":        "strategy" | "portfolio" | "master_bot" | "full_pod" | "migration",
  "package_id":          "<UUIDv4>",
  "package_root_fingerprint": "<SHA-1 of the primary subject, or null for full_pod>",
  "created_at":          "<UTC ISO>",
  "created_by":          "<operator email>",

  "exporter": {
    "pod_host_id":     "<host_id>",
    "build_label":     "BUILD 30.4",
    "git_sha":         "<full git SHA>",
    "exporter_module": "engines.asf.exporter.<name>@v1"
  },

  "subject_summary": {
    "strategies_count":   142,
    "portfolios_count":   3,
    "master_bots_count":  1,
    "lineage_edges":      217,
    "cert_windows":       15,
    "performance_rows":   8421,
    "alert_rows":         12,
    "audit_rows":         440
  },

  "integrity": {
    "files": [
      { "path": "strategies/abc123.json", "sha256": "<64 hex>", "size": 4823 },
      { "path": "lineage/mutation_events.jsonl", "sha256": "<64 hex>", "size": 91204 }
      /* ... one entry per file in the package, excluding manifest.json itself ... */
    ],
    "package_sha256": "<64 hex, SHA-256 over the concatenated sorted file sha256s>"
  },

  "schema_compatibility": {
    "min_reader_version":    "1.0",
    "tested_reader_versions":["1.0"]
  },

  "preserves": {
    "fingerprint":            true,
    "mutation_lineage":       true,
    "performance_history":    true,
    "bi5_certifications":     true,
    "explorer_scores":        true,
    "portfolio_assignments":  true,
    "master_bot_metadata":    true,
    "calibration_snapshot":   true
  },

  // Operator-readable verdict generated by the package writer.
  // Informational only; receivers MUST compute their own verdict from
  // `integrity.files[].sha256` + `integrity.package_sha256`.
  "self_check": {
    "all_files_present":      true,
    "all_sha256_verified":    true,
    "lineage_closure":        "complete" | "partial" | "n/a",
    "cert_replay_check":      "passed" | "skipped"
  }
}
```

### 10.1 `integrity.files[]` ordering

Files MUST be listed in lexicographic order of `path`. This makes `package_sha256` reproducible by any conformant writer regardless of filesystem walk order.

### 10.2 `package_sha256` derivation

```
package_sha256 = SHA-256( "\n".join(sorted([ file.sha256 for file in integrity.files ])) )
```

I.e. concatenate the per-file SHA-256 hex digests in sorted order, separated by `\n`, and SHA-256 the result. This is **NOT** a hash of the package's binary contents — it's a hash of the file hashes. Rationale: deterministic across ZIP compression settings and across filesystem byte ordering.

Future packages signing (Q5 of the audit, marketplace phase) signs `package_sha256` directly.

---

## 11. README.md (human-readable summary)

REQUIRED, but its exact contents are not schema-enforced. A reference template is provided in `ASF_BACKEND_ARCHITECTURE.md §3.4`. Receivers MUST NOT parse README.md — it is operator-facing only.

---

## 12. Compatibility and versioning

### 12.1 Forward-compatibility rules

1. **Receivers MUST preserve unknown keys** in every JSON object on round-trip (export → import → export). This guarantees a v1.0 reader can pass a v1.1-emitted package through without data loss.
2. **Receivers MUST tolerate missing optional sections** (treat as empty, NEVER as error).
3. **Receivers MUST reject** a package whose `asf_schema_version` major number exceeds the reader's supported major. Minor-version differences (1.0 ↔ 1.x) MUST be tolerated.
4. **Producers MUST set `schema_compatibility.min_reader_version`** to the lowest reader version known to safely consume the package. This may equal `asf_schema_version` but does not have to.

### 12.2 Forbidden changes within a major version

* Renaming a required field.
* Removing a required field.
* Changing the semantics of `fingerprint` or `strategy_hash`.
* Changing the meaning of any `verdict` value.
* Changing `package_sha256` derivation.
* Changing the manifest's `integrity.files[]` ordering rule.

### 12.3 Permitted additive changes within a major version

* Adding new optional fields to any JSON object.
* Adding new files / directories under `extensions/`.
* Adding new sub-types to `package_type`.
* Adding new entries to `schema_compatibility.tested_reader_versions`.

---

## 13. Dedup policy on import

The receiver's importer (`engines/asf/importer/upserter.py`) applies dedup in this exact order:

1. **`fingerprint` exact match** in `strategy_library` → row is a soft duplicate. Action depends on `dedup_policy`:
   * `"skip"`     — leave canonical row untouched; log `duplicate_skipped`.
   * `"merge"`    — only fill in fields that are NULL/missing in the canonical row; never overwrite non-null values.
   * `"replace"`  — overwrite the canonical row, but PRESERVE its `_id` and `provenance.discovered_at`.
2. **`strategy_hash` match (no fingerprint match)** → very rare; alert operator. Default policy `"skip"` regardless of incoming `dedup_policy`. Surfaces a `text_match_no_fp_match` warning.
3. **No match** → fresh insert.

The migration adapter (`engines/asf/importer/migration_adapter.py`) MUST default to `dedup_policy="skip"` for T1 imports so the receiving pod's curated state always wins over the migration source.

---

## 14. Use-case coverage matrix

| Use case | Required package_type | Optional but recommended sections |
|---|---|---|
| Disaster recovery snapshot | `full_pod` | all sections; weekly retention |
| Server-to-server migration | `migration` | adds `extensions.migration.{source_pod, T1/T2/T3 tier_class}` |
| Long-term strategy preservation | `strategy` | minimum is `strategies/<fp>.json` + `cert_calibration/` |
| Portfolio portability | `portfolio` | adds `portfolios/*` + every member strategy |
| Master Bot bundle handoff | `master_bot` | adds `master_bot/*` including `.cs` + `Properties.xml` |
| Marketplace publish (future) | `strategy` or `master_bot` | adds `extensions.marketplace.{licence, attribution, price, signature}` |

No new package_types are needed for these use cases. The schema is **complete for v1.0**.

---

## 15. What v1.0 deliberately does NOT include

To prevent scope creep at lock-in time, the following are EXCLUDED from v1.0:

* **Streaming / chunked packages** for > 1 GB bundles. v1.0 assumes the whole package fits in memory at decode time.
* **Cryptographic package signing.** `manifest.json.extensions.marketplace.signature` is reserved; the verification protocol is a v1.1 (or marketplace-phase) deliverable.
* **Encrypted packages.** Operators wanting at-rest encryption MUST encrypt the `.asfpkg` file at the filesystem layer (e.g. `age` / `gpg`); ASF does not encrypt content.
* **Differential / incremental packages** ("only what changed since package X"). v1.0 packages are always self-contained.
* **Multi-pod merge tooling** (e.g. "merge pod A's library with pod B's"). The import dedup policy handles pairwise merges; n-way merge is out of scope.
* **Operator-side tooling** (CLI, UI). The receiver-side `engines/asf/importer/*` and producer-side `engines/asf/exporter/*` are backend-only in v1.0 deliverables. UI is a separate phase.

---

## 16. Lock-in scope

**This document locks the v1.0 wire-format.** Specifically:

1. The package layout (§3).
2. The strategy document schema (§4).
3. The lineage / lifecycle / evidence JSONL schemas (§5).
4. The certification + scoring snapshot schemas (§6, §7).
5. The portfolio + Master Bot schemas (§8).
6. The calibration snapshot contract (§9).
7. The manifest schema and `package_sha256` derivation (§10).
8. The compatibility rules (§12).
9. The dedup policy (§13).

**What this document does NOT lock:**

* Implementation language (Python is the target but not enforced).
* Internal module file names (those are locked in `ASF_BACKEND_ARCHITECTURE.md`).
* Operator-side UI surfaces (deferred).
* Scheduler cadence (deferred — but daily 04:00 UTC is the planning default).

**Authority to change v1.0:** Operator-only. Any field rename, removal, or semantic shift requires a new minor version (1.1+) and explicit operator authorisation. The receiving agent MUST NOT change v1.0 unilaterally.

---

**End of ASF_PACKAGE_V1_SPEC.md.**
