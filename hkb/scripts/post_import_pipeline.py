#!/usr/bin/env python3
"""
HKB POST-IMPORT PIPELINE — Stage 1 · 3.5 · Curated Library
==========================================================

Deterministic, idempotent post-import processing. No backend engines are
invoked — Feature Freeze v1.1.0-stage4 preserved. Only reads from
production collections, writes the three derived collections defined in
the operator directive:

  · strategy_pass_analysis      (one doc per strategy-firm pair)
  · strategy_risk_profile       (one doc per strategy)
  · curated_strategy_library    (highest-quality unique candidates)

All derived docs also carry the migration-provenance stamp so the
operator UI can filter/quarantine them cleanly.

Idempotency: every write is upsert-by-key so re-running produces
identical output.
"""
from __future__ import annotations
import os, sys, json, math, argparse, datetime as dt
from statistics import mean, median
from collections import Counter, defaultdict
from pymongo import MongoClient, ReplaceOne

MIGRATION_SOURCE  = "hkb-1vcpu-20260611"
MIGRATION_VERSION = "1.0"
PIPELINE_VERSION  = "post_import_1.0"


def stamp(doc: dict, ts_iso: str) -> dict:
    doc["__migration_source"]    = MIGRATION_SOURCE
    doc["__migration_timestamp"] = ts_iso
    doc["__migration_version"]   = MIGRATION_VERSION
    doc["__pipeline_version"]    = PIPELINE_VERSION
    doc["__legacy"]              = True
    return doc


# ─────────────────────────── STAGE 1 — Identity ───────────────────────────
def stage1_identity(db, ts_iso):
    print("── STAGE 1: identity reconciliation ──────────────────────────")
    lib = list(db.strategy_library.find({}, {"fingerprint": 1, "created_at": 1}))
    fp_seen: dict[str, list[str]] = defaultdict(list)
    for r in lib:
        fp = r.get("fingerprint")
        if fp: fp_seen[fp].append(str(r["_id"]))
    dupes = {k: v for k, v in fp_seen.items() if len(v) > 1}
    print(f"  library.fingerprint uniqueness: {len(lib)} rows · {len(dupes)} collision sets")

    orphans = []
    lib_ids = set(str(x["_id"]) for x in db.strategy_library.find({}, {"_id": 1}))
    for lc in db.strategy_lifecycle.find({}, {"_id": 1, "library_id": 1, "strategy_hash": 1}):
        lid = lc.get("library_id")
        if lid and str(lid) not in lib_ids:
            orphans.append({"lifecycle_id": str(lc["_id"]), "library_id": str(lid), "strategy_hash": lc.get("strategy_hash")})
    print(f"  lifecycle.library_id orphans: {len(orphans)}")

    # Persist to lifecycle_orphans collection (idempotent by _id)
    if orphans:
        db.lifecycle_orphans.delete_many({"__migration_source": MIGRATION_SOURCE})
        db.lifecycle_orphans.insert_many([stamp(o, ts_iso) for o in orphans])
    return {"library_rows": len(lib), "fingerprint_collisions": len(dupes), "lifecycle_orphans": len(orphans)}


# ─────────────────────── STAGE 3.5 — Pass Analysis + Risk Profile ─────────────
def _pf_pass_probability(pf: float, dd: float, trades: int, oos_ratio: float, stability: float, firm_rules: dict) -> float:
    """Deterministic composite pass-probability estimator (0.0 – 1.0).

    We combine four dimensions each capped in [0, 1]:
      · profit_factor       — logistic around 1.2
      · max_drawdown_pct    — inverse-linear vs firm's daily_dd cap
      · out-of-sample ratio — direct (already in [0,1])
      · stability           — direct (already in [0,1])
    Then hard-gate against firm structural constraints (min_trades).
    """
    firm_dd_cap = float(firm_rules.get("max_daily_drawdown_pct", 5.0) or 5.0)
    firm_min_trades = int(firm_rules.get("min_trades", 30) or 30)
    if trades < firm_min_trades:
        return 0.0
    if dd is None or dd >= 100.0:
        return 0.0
    pf_score = 1.0 / (1.0 + math.exp(-4.0 * (pf - 1.2))) if pf and pf > 0 else 0.0
    dd_score = max(0.0, 1.0 - (dd / max(firm_dd_cap * 3.0, 1.0)))
    oos_score = max(0.0, min(1.0, oos_ratio or 0.0))
    stab_score = max(0.0, min(1.0, stability or 0.0))
    return round(0.35 * pf_score + 0.30 * dd_score + 0.20 * oos_score + 0.15 * stab_score, 4)


def _safe_float(v, default=0.0):
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, dict):
        # some rows store {"value": x, ...} — try common keys
        for k in ("value", "ev", "expected", "mean", "usd"):
            if k in v: return _safe_float(v[k], default)
        return default
    try: return float(v)
    except Exception: return default


def stage35(db, ts_iso):
    print("\n── STAGE 3.5: strategy_pass_analysis + strategy_risk_profile ─")

    # Load firm rules
    firms = list(db.prop_firm_rules.find({}))
    firm_by_slug = {f.get("firm_slug") or f.get("_id") or f.get("firm"): f for f in firms}
    print(f"  loaded {len(firms)} prop-firm rule packages: {list(firm_by_slug.keys())}")

    # OOS ratios (from mutation_stability_log) keyed by variant fingerprint
    stab_by_variant = {}
    for s in db.mutation_stability_log.find({}, {"variant_fingerprint": 1, "oos_pf": 1, "is_pf": 1, "stability_score": 1, "pass": 1}):
        vf = s.get("variant_fingerprint")
        if not vf: continue
        stab_by_variant[vf] = {
            "oos_pf":         float(s.get("oos_pf") or 0),
            "is_pf":          float(s.get("is_pf") or 1),
            "stability":      float(s.get("stability_score") or 0),
            "stab_pass":      bool(s.get("pass", False)),
        }

    # Performance history rollups by strategy_hash
    perf_by_hash = defaultdict(list)
    for p in db.strategy_performance_history.find({}, {"strategy_hash": 1, "profit_factor": 1, "win_rate": 1, "max_drawdown_pct": 1, "total_trades": 1, "sharpe_ratio": 1}):
        h = p.get("strategy_hash")
        if h: perf_by_hash[h].append(p)

    lib = list(db.strategy_library.find({}))
    print(f"  processing {len(lib)} library specimens × {len(firms)} firms = {len(lib) * len(firms)} pass_analysis rows")

    pa_ops, rp_ops = [], []
    for s in lib:
        fp = s.get("fingerprint") or str(s["_id"])
        pf = _safe_float(s.get("profit_factor"), 0)
        dd = _safe_float(s.get("max_drawdown_pct"), 100)
        trades = int(_safe_float(s.get("total_trades"), 0))
        stab_row = stab_by_variant.get(fp, {})
        oos_ratio = 0.0
        if stab_row.get("is_pf", 0) > 0:
            oos_ratio = min(1.0, stab_row["oos_pf"] / max(stab_row["is_pf"], 0.001))
        stability = stab_row.get("stability", 0.0)

        # ── strategy_risk_profile (one per strategy) ──
        rp = {
            "_id":                       f"rp:{fp}",
            "strategy_id":               fp,
            "library_id":                str(s["_id"]),
            "pair":                      s.get("pair"),
            "timeframe":                 s.get("timeframe"),
            "profit_factor":             pf,
            "max_drawdown_pct":          dd,
            "daily_drawdown_pct":        _safe_float(s.get("daily_drawdown_pct"), 0),
            "total_trades":              trades,
            "win_rate":                  _safe_float(s.get("win_rate"), 0),
            "expected_value":            _safe_float(s.get("expected_value"), 0),
            "avg_win_usd":               _safe_float(s.get("avg_win_usd"), 0),
            "avg_loss_usd":              _safe_float(s.get("avg_loss_usd"), 0),
            "consistency_score":         _safe_float(s.get("consistency_score"), 0),
            "stability_score":           stability,
            "oos_ratio":                 round(oos_ratio, 4),
            "risk_of_ruin":              round(1.0 - _pf_pass_probability(pf, dd, trades, oos_ratio, stability, {"max_daily_drawdown_pct": 5.0, "min_trades": 30}), 4),
            "confidence":                _safe_float(s.get("confidence"), 0),
            "pass_probability_v1":       _safe_float(s.get("pass_probability"), 0),
            "computed_at":               ts_iso,
        }
        stamp(rp, ts_iso)
        rp_ops.append(ReplaceOne({"_id": rp["_id"]}, rp, upsert=True))

        # ── strategy_pass_analysis (one per strategy × firm) ──
        for slug, firm in firm_by_slug.items():
            pp = _pf_pass_probability(pf, dd, trades, oos_ratio, stability, firm)
            pa = {
                "_id":                     f"pa:{fp}:{slug}",
                "strategy_id":             fp,
                "library_id":              str(s["_id"]),
                "firm_slug":               slug,
                "firm_name":               firm.get("firm_name") or slug,
                "pass_probability_v2":     pp,
                "pf_used":                 pf,
                "dd_used":                 dd,
                "trades_used":             trades,
                "oos_ratio_used":          round(oos_ratio, 4),
                "stability_used":          stability,
                "firm_max_daily_dd_pct":   _safe_float(firm.get("max_daily_drawdown_pct"), 0),
                "firm_max_total_dd_pct":   _safe_float(firm.get("max_total_drawdown_pct"), 0),
                "firm_min_trades":         int(_safe_float(firm.get("min_trades"), 0)),
                "computed_at":             ts_iso,
                "band":                    ("green"  if pp >= 0.60
                                             else "amber" if pp >= 0.30
                                             else "red"),
            }
            stamp(pa, ts_iso)
            pa_ops.append(ReplaceOne({"_id": pa["_id"]}, pa, upsert=True))

    if rp_ops:
        db.strategy_risk_profile.bulk_write(rp_ops, ordered=False)
    if pa_ops:
        db.strategy_pass_analysis.bulk_write(pa_ops, ordered=False)
    print(f"  strategy_risk_profile:   {len(rp_ops)} upserts → tgt={db.strategy_risk_profile.estimated_document_count()}")
    print(f"  strategy_pass_analysis:  {len(pa_ops)} upserts → tgt={db.strategy_pass_analysis.estimated_document_count()}")
    return {"risk_profile_rows": len(rp_ops), "pass_analysis_rows": len(pa_ops)}


# ─────────────────────────── CURATED LIBRARY ─────────────────────────────
def stage_curated(db, ts_iso, top_n: int = 20):
    print("\n── CURATED STRATEGY LIBRARY ──────────────────────────────────")
    lib = list(db.strategy_library.find({}))
    rp_by_id = {r["strategy_id"]: r for r in db.strategy_risk_profile.find({})}
    # composite = 0.35 pf + 0.30 dd-inverse + 0.20 oos + 0.15 stability
    scored = []
    for s in lib:
        fp = s.get("fingerprint") or str(s["_id"])
        rp = rp_by_id.get(fp, {})
        pf = _safe_float(rp.get("profit_factor"), 0)
        dd = _safe_float(rp.get("max_drawdown_pct"), 100)
        oos = _safe_float(rp.get("oos_ratio"), 0)
        stab = _safe_float(rp.get("stability_score"), 0)
        trades = int(_safe_float(rp.get("total_trades"), 0))
        # Composite in [0, 1]
        pf_score = 1.0 / (1.0 + math.exp(-4.0 * (pf - 1.2))) if pf > 0 else 0.0
        dd_score = max(0.0, 1.0 - (dd / 30.0))    # 0dd=1.0, 30dd=0.0
        composite = round(0.35 * pf_score + 0.30 * dd_score + 0.20 * oos + 0.15 * stab, 4)
        scored.append({
            "_id":                f"curated:{fp}",
            "strategy_id":        fp,
            "library_id":         str(s["_id"]),
            "pair":               s.get("pair"),
            "timeframe":          s.get("timeframe"),
            "style":              s.get("style"),
            "composite_score":    composite,
            "profit_factor":      pf,
            "max_drawdown_pct":   dd,
            "oos_ratio":          oos,
            "stability_score":    stab,
            "total_trades":       trades,
            "win_rate":           _safe_float(rp.get("win_rate"), 0),
            "verdict_legacy":     s.get("verdict"),
            "prop_status_legacy": s.get("prop_status"),
            "mutation_base_fingerprint":   s.get("mutation_base_fingerprint"),
            "mutation_variant_fingerprint": s.get("mutation_variant_fingerprint"),
            "curated_at":         ts_iso,
        })
    # Dedupe by (pair, timeframe, style, rounded-pf/dd) so near-identicals collapse to their best rep
    scored.sort(key=lambda x: -x["composite_score"])
    seen: set = set()
    unique = []
    for r in scored:
        # Coarser cluster key so near-identical strategies collapse
        key = (r["pair"], r["timeframe"], r["style"], round(r["profit_factor"], 1), round(r["max_drawdown_pct"], 0))
        if key in seen: continue
        seen.add(key)
        unique.append(r)
    print(f"  library specimens: {len(scored)} · unique clusters: {len(unique)}")

    # Top-N with composite_score > 0 for curated production candidates
    top = [r for r in unique if r["composite_score"] > 0][:top_n]
    print(f"  curated production candidates (top-N with composite > 0, N={top_n}): {len(top)}")

    ops = []
    for i, r in enumerate(unique):
        r["unique_rank"]           = i + 1
        r["curated_tier"]          = ("A-Elite"       if r["composite_score"] >= 0.7
                                       else "B-Candidate"   if r["composite_score"] >= 0.5
                                       else "C-Experimental" if r["composite_score"] >= 0.3
                                       else "D-Rejected")
        r["is_production_candidate"] = r in top
        stamp(r, ts_iso)
        ops.append(ReplaceOne({"_id": r["_id"]}, r, upsert=True))
    if ops:
        db.curated_strategy_library.bulk_write(ops, ordered=False)
    tiers = Counter(r["curated_tier"] for r in unique)
    print(f"  curated tiers: {dict(tiers)}")
    print(f"  curated_strategy_library upserts: {len(ops)} → tgt={db.curated_strategy_library.estimated_document_count()}")
    return {"unique_strategies": len(unique), "production_candidates": len(top), "curated_tiers": dict(tiers)}


# ─────────────────────────── VERIFY ──────────────────────────────────────
def stage_verify(db):
    print("\n── VERIFY ────────────────────────────────────────────────────")
    lib   = db.strategy_library.estimated_document_count()
    lc    = db.strategy_lifecycle.estimated_document_count()
    lch   = db.strategy_lifecycle_history.estimated_document_count()
    perf  = db.strategy_performance_history.estimated_document_count()
    mkt   = db.market_data.estimated_document_count()
    md_syms = len(db.market_data.distinct("symbol"))
    md_tfs  = len(db.market_data.distinct("timeframe"))
    pa    = db.strategy_pass_analysis.estimated_document_count()
    rp    = db.strategy_risk_profile.estimated_document_count()
    cur   = db.curated_strategy_library.estimated_document_count()
    print(f"  strategy_library                {lib:>10,}")
    print(f"  strategy_lifecycle              {lc:>10,}")
    print(f"  strategy_lifecycle_history      {lch:>10,}")
    print(f"  strategy_performance_history    {perf:>10,}")
    print(f"  market_data                     {mkt:>10,}  (symbols={md_syms}, timeframes={md_tfs})")
    print(f"  strategy_pass_analysis          {pa:>10,}")
    print(f"  strategy_risk_profile           {rp:>10,}")
    print(f"  curated_strategy_library        {cur:>10,}")
    provenance_ok = db.strategy_library.count_documents({"__migration_source": MIGRATION_SOURCE}) == lib
    print(f"  provenance stamped on 100% strategy_library rows: {'YES' if provenance_ok else 'NO'}")
    return {
        "strategy_library": lib, "strategy_lifecycle": lc, "strategy_lifecycle_history": lch,
        "strategy_performance_history": perf, "market_data": mkt, "market_data_symbols": md_syms,
        "market_data_timeframes": md_tfs, "strategy_pass_analysis": pa,
        "strategy_risk_profile": rp, "curated_strategy_library": cur,
        "provenance_ok": provenance_ok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo",  required=True)
    ap.add_argument("--target", default="strategy_factory_v1")
    ap.add_argument("--top-n",  type=int, default=20)
    args = ap.parse_args()
    client = MongoClient(args.mongo)
    db = client[args.target]
    ts_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    print(f"POST-IMPORT PIPELINE · target={args.target} · ts={ts_iso}\n")

    r1 = stage1_identity(db, ts_iso)
    r35 = stage35(db, ts_iso)
    rcur = stage_curated(db, ts_iso, top_n=args.top_n)
    rv = stage_verify(db)

    report = {
        "pipeline_version": PIPELINE_VERSION,
        "target_db": args.target,
        "run_ts": ts_iso,
        "stage1_identity": r1,
        "stage3_5_scoring": r35,
        "curated_library": rcur,
        "verify": rv,
    }
    out = f"/app/hkb/reports/post_import_run_{ts_iso.replace(':','').replace('-','')}.json"
    json.dump(report, open(out, "w"), indent=2, default=str)
    print(f"\nreport → {out}")
    print("POST-IMPORT PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
