# DOWNLOAD_MANIFEST.md

**Purpose:** Define exactly what the operator has on hand from the 1-vCPU export.
**Status:** Placeholder until the operator delivers the archive to `/app/_migration_inbox/`.
**Companion:** `MIGRATION_EXPORT_PLAN.md` (the contract).

---

## 1. Awaiting operator delivery

The operator has stated: *"The exported 1-vCPU strategy package is already secured and downloaded."*

Until the package lands at `/app/_migration_inbox/`, this manifest holds the **expected** contents and the operator-fillable fields. After delivery, the actual values are populated from the package's own `manifest.json` and the validation script's output.

```
/app/_migration_inbox/
└── (no files yet — awaiting operator drop)
```

---

## 2. Expected manifest contract

When the package arrives, it MUST carry a `manifest.json` matching this shape:

```json
{
  "source_pod":        "1-vCPU deployment",
  "exported_at_utc":   "<YYYY-MM-DDTHH:MM:SSZ>",
  "exported_by":       "<operator email>",
  "source_db_name":    "<eg test_database>",
  "package_format":    "bson_archive | json_dir | zip",
  "package_sha256":    "<64-char hex>",
  "total_size_bytes":  <int>,
  "collections": {
    "strategy_library":             { "count": <int>, "sha256": "<64-char hex>" },
    "strategy_lifecycle":           { "count": <int>, "sha256": "<64-char hex>" },
    "strategy_lifecycle_history":   { "count": <int>, "sha256": "<64-char hex>" },
    "strategy_performance_history": { "count": <int>, "sha256": "<64-char hex>" },
    "mutation_events":              { "count": <int>, "sha256": "<64-char hex>" },
    "mutation_stability_log":       { "count": <int>, "sha256": "<64-char hex>" },
    "auto_factory_alert_log":       { "count": <int>, "sha256": "<64-char hex>" }
  },
  "schema_version":    "1-vcpu-r4 (pre-DSR)",
  "notes": "<free text>"
}
```

The validation script will refuse to import a package missing this file.

---

## 3. Operator-fillable fields (to populate at delivery)

| Field | Value |
|---|---|
| Package filename | _to fill_ |
| Package size | _to fill_ |
| Package sha256 | _to fill_ |
| Package format | _to fill (Format A / B / C from EXPORT_PLAN)_ |
| Export timestamp | _to fill_ |
| `strategy_library` row count | _to fill_ (operator says: "hundreds") |
| `strategy_lifecycle` row count | _to fill_ |
| `mutation_events` row count | _to fill_ |
| Other collections row counts | _to fill_ |
| Schema version | _to fill_ |

---

## 4. Hash + count verification (to run at delivery)

```bash
# 1. Confirm file arrived
ls -lh /app/_migration_inbox/

# 2. Verify package hash
sha256sum /app/_migration_inbox/strategy_export_*.{archive,zip}

# 3. Cross-check against manifest.json
python3 -c "
import json, hashlib, os
pkg = '/app/_migration_inbox/<filename>'
m = json.load(open('/app/_migration_inbox/manifest.json'))
h = hashlib.sha256(open(pkg, 'rb').read()).hexdigest()
print(f'package_sha256 expected={m[\"package_sha256\"]}')
print(f'package_sha256 actual  ={h}')
print(f'MATCH={h == m[\"package_sha256\"]}')
"
```

If hashes don't match, the package is rejected. Operator re-delivers.

---

## 5. Row count expectations vs reality

This is the operator's chance to confirm scale before the post-import pipeline runs (the pipeline cost scales linearly with `strategy_library.count`):

| Range | Pipeline ETA on 12-vCPU pod | Notes |
|---|---|---|
| < 100 | ~5 min | Quick win |
| 100–500 | ~20 min | Operator-mentioned range |
| 500–2,000 | ~1–2 h | Process pool can be activated (`ENABLE_PROCESS_POOL_BACKTEST=true`) |
| > 2,000 | ~half-day | Batch the import; activate adaptive pool sizing |

---

## 6. Disk budget

The Mongo database is currently 39 collections (mostly empty). Importing `strategy_library` with say 1,000 strategies × ~10 KB each = ~10 MB. Lineage collections add another ~30 MB. Total expected import footprint: **≤ 100 MB**. The pod's current free disk (~78%) trivially accommodates this.

---

## 7. Non-deliverables (must NOT be in the package)

Per `MIGRATION_EXPORT_PLAN.md §6`:
* No `users` rows
* No JWT/auth keys
* No `.env` artefacts
* No `host_capabilities` / `scaling_nodes` rows

The validation script will scan the archive and refuse import if any of these are present.

---

## 8. Status

* ⏳ **Awaiting operator drop** at `/app/_migration_inbox/`.
* On delivery, this document is updated with actual values + validation evidence.
* Validation gate must be green before `POST_IMPORT_PIPELINE.md` can be authorised.
