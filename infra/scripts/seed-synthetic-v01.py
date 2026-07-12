#!/usr/bin/env python3
"""Strategy Factory — Synthetic v01 seed generator.

Produces a realistic v01-shaped MongoDB dataset in a chosen DB name so the
migration pipeline can be exercised end-to-end without touching the real VPS.

Seeded shapes deliberately include the messy fields the migration
transformers must handle:
  * users with `status: pending|approved`, `role: user`, missing `user_id`
  * strategies with `id`/`sid`/`strategyId` variants and missing `strategy_id`
  * research_lineage (old name) with `query` instead of `prompt`
  * strategy_library (v01 cohort of 14) with mixed shapes
  * every pass-through collection with a few rows
  * an "unknown_v01_collection" to prove the coverage validator flags it

Usage:
    python infra/scripts/seed-synthetic-v01.py \\
        --uri mongodb://localhost:27017 --db synthetic_v01
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

try:
    import bcrypt
    from pymongo import MongoClient
except ImportError:
    sys.stderr.write("error: pymongo + bcrypt required. Run: pip install pymongo==4.9.2 bcrypt\n")
    sys.exit(2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def seed(uri: str, db_name: str) -> None:
    client = MongoClient(uri)
    client.drop_database(db_name)
    db = client[db_name]

    now = datetime.now(timezone.utc)

    # ── users (mixed shapes) ────────────────────────────────────────
    users = [
        {"email": "Admin@Old-VPS.local",  "password_hash": _hash("Jahnav@2018"), "role": "admin",     "status": "approved", "created_at": now - timedelta(days=180)},
        {"email": "researcher@old.local", "password_hash": _hash("res123"),      "role": "user",      "status": "approved", "created_at": now - timedelta(days=120)},
        {"email": "operator@old.local",   "password_hash": _hash("op123"),       "role": "user",      "status": "pending",  "created_at": now - timedelta(days=90)},
        {"email": "viewer@old.local",     "password_hash": _hash("vw123"),       "role": "",          "status": "approved", "created_at": now - timedelta(days=60)},
        {"email": "dev@old.local",        "password_hash": _hash("dv123"),       "role": "developer", "status": "approved", "created_at": now - timedelta(days=45)},
        {"email": "OLDBOB@vps.LOCAL",     "password_hash": _hash("bob"),         "role": "user",      "status": "approved", "created_at": now - timedelta(days=200), "user_id": "bob-legacy"},
        {"email": "disabled@old.local",   "password_hash": _hash("dis"),         "role": "user",      "status": "disabled", "created_at": now - timedelta(days=300)},
    ]
    db.users.insert_many(users)

    # ── strategies (mixed id shapes) ────────────────────────────────
    strategies = []
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "AUDUSD"]
    timeframes = ["M15", "M30", "H1", "H4", "D1"]
    for i in range(22):
        base = {
            "name": f"v01 Strategy {i}",
            "symbol": random.choice(symbols),
            "timeframe": random.choice(timeframes),
            "ir": {"entry": "close > sma(20)", "exit": "close < sma(20)"},
            "tags": ["v01", "cohort"],
            "owner": random.choice(["admin@old-vps.local", "researcher@old.local", "dev@old.local"]),
            "created_at": (now - timedelta(days=random.randint(1, 180))).isoformat(),
            "status": random.choice(["draft", "validated", "backtested", None]),
            "custom_v01_field": {"nested": True, "n": i},
        }
        # Vary the identifier field to test the backfill logic
        variant = i % 4
        if variant == 0:
            base["strategy_id"] = f"sf-{uuid.uuid4().hex[:12]}"
        elif variant == 1:
            base["id"] = f"leg-{i:03d}"
        elif variant == 2:
            base["sid"] = f"sid-{i:03d}"
        # variant 3 → no identifier, transformer must synthesise one
        strategies.append(base)
    db.strategies.insert_many(strategies)

    # ── strategy_library (v01 14-cohort) with rich production-shaped metadata ────
    library = []
    for i in range(14):
        library.append({
            "title": f"Cohort Strategy #{i+1:02d}",
            "strategyId": f"cohort-{i:02d}",
            "symbol": random.choice(symbols),
            "timeframe": random.choice(timeframes),
            "created_by": "admin@old-vps.local",
            "created_at": now - timedelta(days=200 + i),
            # rich production metadata that must survive verbatim
            "fingerprint": f"fp-{uuid.uuid4().hex}",
            "content_hash": f"sha256-{uuid.uuid4().hex}",
            "lineage": {
                "parent_id": f"cohort-{max(0, i-1):02d}" if i > 0 else None,
                "generation": i // 3,
                "ancestors": [f"cohort-{j:02d}" for j in range(max(0, i-2), i)],
            },
            "validation_history": [
                {"kind": "walk_forward", "sharpe": 1.4 + 0.05*i, "at": now - timedelta(days=180 + i)},
                {"kind": "monte_carlo", "p95_dd": 0.12 - 0.002*i, "at": now - timedelta(days=170 + i)},
            ],
            "bi5": {
                "certified": True,
                "provider": "dukascopy",
                "coverage_from": (now - timedelta(days=2000)).isoformat(),
                "coverage_to": (now - timedelta(days=30)).isoformat(),
            },
            "lifecycle": {
                "phase": random.choice(["draft", "validated", "certified", "retired"]),
                "history": [
                    {"phase": "draft", "at": now - timedelta(days=210 + i)},
                    {"phase": "validated", "at": now - timedelta(days=180 + i)},
                ],
            },
            "provenance": {
                "source_bundle": "v01-handoff",
                "imported_at": now - timedelta(days=200),
                "importer": "vqb-consolidator@0.9",
            },
            "backtest_snapshot": {
                "sharpe": round(random.uniform(0.5, 2.5), 2),
                "trades": random.randint(50, 500),
                "mdd": round(random.uniform(0.05, 0.25), 3),
            },
            "notes": "Preserved from v01 delivery bundle",
        })
    db.strategy_library.insert_many(library)

    # ── research_lineage (old name) ─────────────────────────────────
    lineage = []
    for i in range(30):
        lineage.append({
            "id": f"q-{i:04d}",
            "query": f"What is the best entry filter for a {random.choice(symbols)} scalper?",
            "model_provider": random.choice(["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"]),
            "user_id": random.choice(["admin@old-vps.local", "researcher@old.local"]),
            "created_at": now - timedelta(hours=random.randint(1, 720)),
            "response_summary": "…legacy response summary…",
        })
    db.research_lineage.insert_many(lineage)

    # ── research_queries (already-modern rows co-existing) ──────────
    db.research_queries.insert_many([
        {"query_id": "modern-1", "prompt": "Explain SMC concepts.", "provider": "openai",
         "created_by": "researcher@old.local", "created_at": now - timedelta(days=1)},
        {"query_id": "modern-2", "prompt": "Best walk-forward setup for FX H1.", "provider": "anthropic",
         "created_by": "researcher@old.local", "created_at": now - timedelta(days=2)},
    ])

    # ── pass-through collections ────────────────────────────────────
    db.validation_reports.insert_many([
        {"strategy_id": s["strategy_id"] if s.get("strategy_id") else s.get("id"),
         "type": "walk_forward",
         "created_at": now - timedelta(days=random.randint(1, 30)),
         "metrics": {"sharpe": round(random.uniform(0.5, 2.5), 2), "mdd": round(random.uniform(0.05, 0.25), 3)}}
        for s in strategies[:8] if s.get("strategy_id") or s.get("id")
    ])
    db.backtest_results.insert_many([
        {"strategy_ref": s.get("strategy_id") or s.get("id") or s.get("sid"),
         "equity_curve": [1000, 1010, 995, 1030],
         "trades": random.randint(20, 200)}
        for s in strategies[:12]
    ])
    db.master_bots.insert_many([
        {"bot_id": "mb-01", "name": "Composite EURUSD", "strategies": ["cohort-00", "cohort-01"], "created_by": "admin@old-vps.local"},
        {"bot_id": "mb-02", "name": "Multi-Symbol Grid", "strategies": ["cohort-02", "cohort-03", "cohort-04"], "created_by": "dev@old.local"},
    ])
    db.master_bot_exports.insert_many([
        {"export_id": "exp-01", "bot_id": "mb-01", "format": "asf", "created_at": now - timedelta(days=3)},
    ])
    db.portfolio_definitions.insert_many([
        {"portfolio_id": "port-01", "name": "Balanced Prop", "components": ["mb-01", "mb-02"]},
    ])
    db.mutation_pool.insert_many([
        {"mutation_id": f"mut-{i:03d}", "parent": "cohort-01", "delta": {"period": 10 + i}} for i in range(6)
    ])
    db.market_universe.insert_many([{"symbol": s, "tier": random.choice(["A", "B"])} for s in symbols])
    db.market_intelligence.insert_many([
        {"symbol": "EURUSD", "regime": "trend", "as_of": now - timedelta(hours=6)},
        {"symbol": "XAUUSD", "regime": "range", "as_of": now - timedelta(hours=6)},
    ])
    db.prop_firm_configs.insert_many([{"firm": "FTMO", "max_daily_dd": 0.05, "max_total_dd": 0.10}])
    db.prop_firm_rules.insert_many([{"firm": "FTMO", "consistency": 0.5, "min_days": 5}])
    db.governance_universe.insert_many([{"symbol": "BTCUSD", "allowed": True, "notes": "requires broker A"}])
    db.survivor_registry.insert_many([{"strategy_id": "cohort-01", "cycles_survived": 4}])
    db.readiness_snapshots.insert_many([{"as_of": now - timedelta(days=1), "green": True}])
    db.bi5_certifications.insert_many([{"symbol": "EURUSD", "verified": True, "as_of": now - timedelta(days=1)}])
    db.settings.insert_many([{"key": "vie_default_provider", "value": "openai"},
                             {"key": "risk_ceiling", "value": 0.02}])
    db.audit_log.insert_many([
        {"ts_dt": now - timedelta(hours=i), "actor": "admin@old-vps.local", "action": f"legacy_action_{i}"}
        for i in range(10)
    ])
    db.strategy_versions.insert_many([
        {"strategy_id": "cohort-00", "version": 1, "notes": "initial"},
        {"strategy_id": "cohort-00", "version": 2, "notes": "tightened stop"},
    ])
    db.lifecycle_events.insert_many([
        {"strategy_id": "cohort-00", "event": "validated", "at": now - timedelta(days=30)},
    ])
    db.strategy_memory.insert_many([
        {"strategy_id": "cohort-00", "note": "regime dependency observed", "at": now - timedelta(days=15)},
    ])

    # ── an unknown collection to prove the coverage validator ──────
    # Kept in default (non-strict) mode only — this deliberate collection
    # exercises the auto-passthrough safety net. If you add it to
    # MIGRATION_PLAN the strict-mode pytest test (test_10) will fail.
    db.legacy_experimental_notes.insert_many([{"note": f"experimental idea {i}"} for i in range(3)])

    # ── 22 collections that the operator's real production DB had but our
    # original plan missed. Seeding them (empty) proves the expanded plan
    # covers them and that strict mode passes on the seeded dataset.
    for name in (
        "advisory_locks", "asf_import_log", "auto_run_cycles",
        "bi5_cert_sweep_log", "bi5_cert_sweep_runs", "bi5_certification",
        "bi5_data_certification", "calibration_outcomes", "calibration_tables",
        "cbot_parity_signoff", "ingested_strategies", "market_universe_audit",
        "market_universe_symbols", "master_bot_members", "master_bot_ranker_config",
        "master_bot_tiers", "multi_cycle_runs", "orchestrator_env_priority",
        "post_import_pipeline_log", "risk_of_ruin_evaluations", "runner_accounts",
        "runner_token_rotation_history",
    ):
        db[name].insert_one({"seeded": True, "note": f"synthetic seed for {name}"})

    total = sum(db[c].count_documents({}) for c in db.list_collection_names())
    print(f"[seed] {db_name}: {len(db.list_collection_names())} collections, {total} documents")
    print(f"[seed] as of: {_now_iso()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--db", default="synthetic_v01")
    args = ap.parse_args()
    seed(args.uri, args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
