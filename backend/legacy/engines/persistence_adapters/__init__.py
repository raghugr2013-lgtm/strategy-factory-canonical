"""P0B Phase 2 — Persistence adapters.

Thin Mongo upsert/lookup helpers that translate Phase 1 dataclasses
(`engines.tick_validator.BI5ScoreReport`,
`engines.spread_analyzer.SpreadBar`) into idempotent Mongo writes.

Phase 2 owns TWO collections, both data-feed-side:

    * ``market_spread``             — per-minute spread OHLC bars
    * ``bi5_data_certification``    — per-(symbol, window) data-feed
                                      quality cert (the BI5 ingest
                                      health certificate)

The **strategy-level** ``bi5_certification`` collection is intentionally
NOT created here. It is owned by the P0B Phase 3 orchestrator, which
naturally carries the upstream strategy context (strategy_id, pair,
timeframe, style, mutation_family, parent_strategy_id, stability_score).
Introducing those fields in the persistence layer before the
orchestrator exists would leak architectural concerns downward.

BID/BI5 firewall
────────────────
These adapters are BI5-side. They MUST NOT import from any of:
    discovery, mutation, validation, pass_probability,
    challenge_matching, portfolio_selection, phase30_*.

They may import:
    * `engines.db` (Mongo client)
    * Phase 1 dataclasses (`engines.tick_validator`, `engines.spread_analyzer`)
    * pymongo
"""
from engines.persistence_adapters.bi5_data_certification_store import (
    BI5_DATA_CERT_COLL,
    find_data_certs_by_verdict,
    get_data_certification,
    get_latest_data_certification,
    upsert_data_certification,
)
from engines.persistence_adapters.market_spread_store import (
    MARKET_SPREAD_COLL,
    find_spread_bars,
    upsert_spread_bars,
)

__all__ = [
    "BI5_DATA_CERT_COLL",
    "MARKET_SPREAD_COLL",
    "find_data_certs_by_verdict",
    "find_spread_bars",
    "get_data_certification",
    "get_latest_data_certification",
    "upsert_data_certification",
    "upsert_spread_bars",
]
