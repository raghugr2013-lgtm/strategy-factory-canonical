# MIGRATION_EXPORT_PLAN.md

**Purpose:** Define exactly what was extracted from the 1-vCPU deployment, how it was packaged, and the contract the import pipeline must consume.
**Scope:** **Read-only** plan. No code modified. The operator has stated the export package is "already secured and downloaded."
**Companion docs:** `DOWNLOAD_MANIFEST.md` (what arrived), `MIGRATION_PRIORITY.md` (what gets imported first), `MIGRATION_COMPATIBILITY_AUDIT.md` (format check), `POST_IMPORT_PIPELINE.md` (what runs after).

---

## 1. Source system

| Field | Value |
|---|---|
| Source pod | 1-vCPU deployment (legacy) |
| Source UI | `_inventory/old1vcpu/src` (commits from before 2026-06) |
| Source backend | engineering ancestor of `App.zip/backend/` |
| Source DB | MongoDB (single instance) |
| Source identity model | `strategy_library._fingerprint(pair, timeframe, style, params, strategy_text)` — SHA1 over the canonical key |
| Source strategy count (operator-reported) | "hundreds" — exact count to be confirmed in DOWNLOAD_MANIFEST.md |

The 1-vCPU source code, engines, and data formats are byte-compatible with App.zip — they share lineage. The shared `_fingerprint()` function means strategy identity travels intact.

---

## 2. What MUST be exported

Authoritative scope: **strategies + their lineage + their evidence**. Everything else is reproducible on the 12-vCPU pod.

### 2.1 PRIMARY — strategies (the gold)

| Collection | Why | Per-doc payload |
|---|---|---|
| `strategy_library` | The canonical survivor set; every doc is a fingerprinted candidate. | `fingerprint`, `strategy_text`, `strategy_ir`, `strategy_hash`, `pair`, `timeframe`, `style`, `params`, `metrics` (PF, win_rate, total_trades, drawdown, sharpe, sortino, calmar, stability), `validation_report`, `backtest_results`, `created_at`, `source` (e.g. `"auto_factory"`, `"manual"`, `"workspace"`). |

### 2.2 SECONDARY — lineage & evidence (high-value)

| Collection | Why |
|---|---|
| `strategy_lifecycle` | Per-strategy stage tracking (`stage`, `state`, `transitioned_at`). Needed to skip re-discovery of demoted strategies. |
| `strategy_lifecycle_history` | Audit trail of stage transitions. Needed for Trust Score lineage. |
| `strategy_performance_history` | Rolling per-strategy snapshots. Feeds aging and stability calculations. |
| `mutation_events` | Mutation parents/children — enables re-mutation from known-good seeds without recomputing. |
| `mutation_stability_log` | Per-mutation stability scores. |
| `auto_factory_alert_log` | High-signal alert log (rare events). |

### 2.3 TERTIARY — contextual (optional)

| Collection | Why |
|---|---|
| `governance_universe` | Allowed (pair × timeframe × style) sets that produced these strategies. Useful for replay parity but the new pod ships its own seed. |
| `audit_log` (recent 90 days) | Operator action context. |
| `llm_call_log` (last 7 days only) | LLM prompt evidence. |

### 2.4 NOT exported

* Market data (BI5/BID) — re-ingested on the 12-vCPU pod by `bi5_one_shot_backfill.py`.
* Schedules / runner registrations — re-created in the new env.
* `users` collection — admin re-seeded.
* `host_capabilities`, `scaling_events`, `scaling_nodes` — host-specific, irrelevant to the new pod.
* Live tracking / paper execution session rows — point-in-time, not portable.

---

## 3. Export package format (required contract)

The 1-vCPU export should be one of:

### Format A — Mongo `mongodump` BSON archive (PREFERRED)

```
strategy_export_<YYYYMMDD>.archive       (gzipped BSON archive)
strategy_export_<YYYYMMDD>.manifest.json (sha256 + counts per collection)
```

Created by:
```bash
mongodump --uri="mongodb://..." \
  --db=<source_db> \
  --collection=strategy_library \
  --collection=strategy_lifecycle \
  --collection=strategy_lifecycle_history \
  --collection=strategy_performance_history \
  --collection=mutation_events \
  --collection=mutation_stability_log \
  --collection=auto_factory_alert_log \
  --archive=strategy_export_<YYYYMMDD>.archive --gzip
```

### Format B — JSON dump (FALLBACK)

```
strategy_export_<YYYYMMDD>/
├── strategy_library.json              (array of strategy docs)
├── strategy_lifecycle.json
├── strategy_lifecycle_history.json
├── strategy_performance_history.json
├── mutation_events.json
├── mutation_stability_log.json
├── auto_factory_alert_log.json
└── manifest.json                       (sha256 + counts per file)
```

Created by:
```bash
mongoexport --uri=... --collection=<c> --out=<c>.json --jsonArray
```

### Format C — ZIP of either of the above (operational convenience)

```
strategy_export_<YYYYMMDD>.zip
└── (contents of Format A or B)
```

The import pipeline auto-detects which format is present.

---

## 4. Export package validation requirements

Before importing, the package MUST be validated against this checklist:

| # | Check | How |
|---|---|---|
| 1 | Archive integrity | sha256 verified against `manifest.json` |
| 2 | `strategy_library.json` (or BSON collection) exists | file/collection present |
| 3 | Every strategy doc has `fingerprint` field | post-decode scan |
| 4 | Every strategy doc has `strategy_text` OR `strategy_ir` | post-decode scan |
| 5 | Every strategy doc has `pair` + `timeframe` + `style` | post-decode scan |
| 6 | Fingerprint format is SHA1 (40-char hex) | regex `^[0-9a-f]{40}$` |
| 7 | No `_id` collisions within `strategy_library` | Mongo unique constraint check |
| 8 | Lineage references are internally consistent | every `parent_fingerprint` referenced by a `mutation_events` row resolves to a `strategy_library` row, OR is marked as `external` |

The validation script lives at `backend/scripts/validate_migration_package.py` (will be created when the operator provides the actual package — kept out of scope per "do not import yet" directive).

---

## 5. Recommended exclusion policy

The 1-vCPU pod may carry low-value rows that should NOT be imported into the canonical pod:

| Filter | Why |
|---|---|
| `strategy_library.stage == 'DEMOTED' AND aging > 60d` | Aged-out demoted strategies clutter the survivor space. |
| `strategy_library.fingerprint` already present in seed | Avoid duplicate insert; merge metadata. |
| `mutation_events` where `child_fingerprint` not in `strategy_library` | Orphaned mutation rows. |
| `strategy_lifecycle_history` rows older than 180 days | Audit retention. |

Filters are applied **at import time** by the post-import pipeline, not at export time. This preserves the operator's right to inspect the full export.

---

## 6. Security & secrets

* The export package MUST NOT contain `users` rows, `auth_tokens`, or any `*.key` / `.env` artefacts.
* If LLM call log is exported, redact prompt/response bodies if they contain personally-identifiable inputs (the operator confirms what to redact).
* Transport: assume the package was downloaded by the operator via a trusted channel.

---

## 7. Deliverable

When the operator is ready to import, they place the export at:

```
/app/_migration_inbox/strategy_export_<YYYYMMDD>.[archive|zip]
```

The import pipeline (see `POST_IMPORT_PIPELINE.md`) detects it and runs validation (§4) before staging.

---

## 8. Status

* This document is **planning only**.
* No export has been ingested into `/app` yet.
* No backend code or schema has been altered.
* The operator has the export package secured externally and will deliver it after `IMPORT_READINESS_REPORT.md` is green.
