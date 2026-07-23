#!/usr/bin/env python3
"""
HKB → API view builder — populates the collections the current backend
API reads from (Feature-Freeze-safe · pure ETL · no backend change).

Bug root cause (2026-07-23): after the HKB migration, the current backend
API reads knowledge from `strategy_knowledge_base.strategy_kb_view` and
`strategy_knowledge_base.strategy_kb_champions` (see
`app/knowledge/router.py::_default_repo`), which were empty because the
migration landed data in `strategy_factory_v1.strategy_library` /
`curated_strategy_library`. This script rebuilds the derived KB views
from the imported HKB so `/api/knowledge/statistics`, `/api/knowledge/champions`,
and `/api/knowledge/nearest` return the expected populated shape.

Idempotent (upsert by `_id`) and re-runnable. Every derived doc carries
the migration provenance stamp and `learning_only: True` (KB safety
guard). Nothing writes to the production `strategies` collection —
production paths remain empty because HKB rows are `eligible_for_deploy:
False` by construction.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, math, re
from pymongo import MongoClient, ReplaceOne

MIGRATION_SOURCE  = "hkb-1vcpu-20260611"
MIGRATION_VERSION = "1.0"
PIPELINE_VERSION  = "kb_view_builder_1.0"

# Regexes cloned from app.knowledge.canonical to avoid importing the
# backend package (freeze-safe: pure data script).
_NUMBER_RE     = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_PROVENANCE_RE = re.compile(
    r"^(?:derived from|source|origin|pair|tf|mutation[_ ]run[_ ]id)\s*:.*$",
    re.IGNORECASE | re.MULTILINE,
)
_WS_RE = re.compile(r"\s+")


def canonical_hash(text: str | None, parameters: dict | None = None) -> str:
    if not text:
        norm = ""
    else:
        t = text.lower()
        t = _PROVENANCE_RE.sub("", t)
        t = _NUMBER_RE.sub("N", t)
        norm = _WS_RE.sub(" ", t).strip()
    param_keys = "|".join(sorted((parameters or {}).keys()))
    payload = f"{norm}||{param_keys}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _safe_float(v, default=0.0):
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, dict):
        for k in ("value", "ev", "expected", "mean", "usd"):
            if k in v: return _safe_float(v[k], default)
        return default
    try: return float(v)
    except Exception: return default


def build_kb_view(src_db, tgt_db, ts_iso):
    """Rebuild strategy_kb_view from strategy_library."""
    print("── STAGE A: strategy_kb_view (from strategy_library) ─────────")
    lib = list(src_db.strategy_library.find({}))
    print(f"  reading {len(lib)} rows from strategy_library")

    ops = []
    families: dict[str, list[str]] = {}
    for s in lib:
        fp = s.get("fingerprint") or str(s["_id"])
        text = s.get("strategy_text") or ""
        params = s.get("parameters") or {}
        ch = canonical_hash(text, params if isinstance(params, dict) else None)

        legacy_metrics = {
            "profit_factor":     _safe_float(s.get("profit_factor"), 0),
            "win_rate":          _safe_float(s.get("win_rate"), 0),
            "max_drawdown_pct":  _safe_float(s.get("max_drawdown_pct"), 0),
            "daily_drawdown_pct":_safe_float(s.get("daily_drawdown_pct"), 0),
            "total_trades":      int(_safe_float(s.get("total_trades"), 0)),
            "total_return_pct":  _safe_float(s.get("total_return_pct"), 0),
            "expected_value":    _safe_float(s.get("expected_value"), 0),
            "consistency_score": _safe_float(s.get("consistency_score"), 0),
            "stability_score":   _safe_float(s.get("stability_score"), 0),
            "pass_probability":  _safe_float(s.get("pass_probability"), 0),
            "score":             _safe_float(s.get("score"), 0),
        }

        doc = {
            "_id":                fp,
            "strategy_id":        fp,
            "canonical_hash":     ch,
            "pair":               s.get("pair"),
            "timeframe":          s.get("timeframe"),
            "strategy_type":      s.get("style") or s.get("mutation_type"),
            "strategy_text":      text,
            "parameters":         params if isinstance(params, dict) else {},
            "legacy_metrics":     legacy_metrics,
            "legacy_verdict":     s.get("verdict"),
            "legacy_prop_status": s.get("prop_status"),
            "created_at":         s.get("created_at"),
            # Safety guards required by the API layer
            "learning_only":      True,
            "eligible_for_deploy":False,
            # Provenance
            "__migration_source":    MIGRATION_SOURCE,
            "__migration_timestamp": ts_iso,
            "__migration_version":   MIGRATION_VERSION,
            "__pipeline_version":    PIPELINE_VERSION,
            "__legacy":              True,
        }
        ops.append(ReplaceOne({"_id": fp}, doc, upsert=True))
        families.setdefault(ch, []).append(fp)

    if ops:
        tgt_db.strategy_kb_view.bulk_write(ops, ordered=False)
    n = tgt_db.strategy_kb_view.estimated_document_count()
    fam_multi = sum(1 for k, v in families.items() if len(v) > 1)
    print(f"  strategy_kb_view    upserts={len(ops):>6d}  → tgt={n:>6d}  families={len(families)}  multi-member={fam_multi}")
    return {"strategy_kb_view_rows": n, "families": len(families), "multi_families": fam_multi}


def build_kb_champions(src_db, tgt_db, ts_iso):
    """Rebuild strategy_kb_champions from curated_strategy_library.

    Champions are the top representative per category. We tier by:
      · top_by_composite     (top 10 across all pairs)
      · top_by_pair          (best per pair)
      · top_by_timeframe     (best per timeframe)
      · a_elite / b_candidate / c_experimental (curated tier buckets)
    """
    print("\n── STAGE B: strategy_kb_champions (from curated) ─────────────")
    cur = list(src_db.curated_strategy_library.find({}, sort=[("composite_score", -1)]))
    print(f"  reading {len(cur)} rows from curated_strategy_library")

    def row(r):
        return {
            "strategy_id":     r["strategy_id"],
            "library_id":      r.get("library_id"),
            "pair":            r.get("pair"),
            "timeframe":       r.get("timeframe"),
            "composite_score": r.get("composite_score"),
            "profit_factor":   r.get("profit_factor"),
            "max_drawdown_pct":r.get("max_drawdown_pct"),
            "total_trades":    r.get("total_trades"),
            "tier":            r.get("curated_tier"),
            "unique_rank":     r.get("unique_rank"),
        }

    categories: dict[str, list] = {"top_by_composite": [], "top_by_pair": [], "top_by_timeframe": [], "a_elite": [], "b_candidate": [], "c_experimental": []}
    # top 10 by composite
    categories["top_by_composite"] = [row(r) for r in cur[:10]]
    # best per pair
    seen_pairs = set()
    for r in cur:
        p = r.get("pair")
        if p and p not in seen_pairs:
            categories["top_by_pair"].append(row(r))
            seen_pairs.add(p)
    # best per timeframe
    seen_tfs = set()
    for r in cur:
        tf = r.get("timeframe")
        if tf and tf not in seen_tfs:
            categories["top_by_timeframe"].append(row(r))
            seen_tfs.add(tf)
    for r in cur:
        tier = r.get("curated_tier") or ""
        if tier.startswith("A-"): categories["a_elite"].append(row(r))
        elif tier.startswith("B-"): categories["b_candidate"].append(row(r))
        elif tier.startswith("C-"): categories["c_experimental"].append(row(r))

    ops = []
    for cat, rows in categories.items():
        doc = {
            "_id":       f"champion:{cat}",
            "category":  cat,
            "rows":      rows,
            "size":      len(rows),
            # Safety guards + provenance
            "learning_only":         True,
            "eligible_for_deploy":   False,
            "__migration_source":    MIGRATION_SOURCE,
            "__migration_timestamp": ts_iso,
            "__migration_version":   MIGRATION_VERSION,
            "__pipeline_version":    PIPELINE_VERSION,
            "__legacy":              True,
        }
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
    if ops:
        tgt_db.strategy_kb_champions.bulk_write(ops, ordered=False)
    n = tgt_db.strategy_kb_champions.estimated_document_count()
    for cat, rows in categories.items():
        print(f"    · {cat:20s}  {len(rows):>4d} rows")
    print(f"  strategy_kb_champions upserts={len(ops):>4d}  → tgt={n:>4d}")
    return {"champions_categories": {k: len(v) for k, v in categories.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--source-db", default="strategy_factory_v1")
    ap.add_argument("--kb-db",     default="strategy_knowledge_base")
    args = ap.parse_args()
    client = MongoClient(args.mongo)
    src_db = client[args.source_db]
    kb_db  = client[args.kb_db]
    ts_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    print(f"KB VIEW BUILDER · source={args.source_db} · kb_db={args.kb_db} · ts={ts_iso}\n")

    r1 = build_kb_view(src_db, kb_db, ts_iso)
    r2 = build_kb_champions(src_db, kb_db, ts_iso)

    # Verify
    print("\n── VERIFY ────────────────────────────────────────────────────")
    kb_v = kb_db.strategy_kb_view.count_documents({"learning_only": True})
    kb_c = kb_db.strategy_kb_champions.count_documents({"learning_only": True})
    print(f"  strategy_kb_view    (learning_only) = {kb_v}")
    print(f"  strategy_kb_champions               = {kb_c}")
    print(f"  ✅ /api/knowledge/statistics will now report total_strategies={kb_v}")
    print("KB VIEW BUILD COMPLETE")


if __name__ == "__main__":
    main()
