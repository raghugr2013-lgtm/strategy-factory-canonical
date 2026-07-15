"""Curated list of high-signal algorithmic-trading repositories.

The pre-1.1.1 ingestion pipeline used three broad GitHub search
queries:
    "pine script strategy forex"
    "mt5 expert advisor forex"
    "forex trading strategy python"

Those queries surface a large tail of README-only projects, generic
tutorials, and incomplete code snippets, which is why the parser
reports "No identifiable entry rule" for the vast majority of results.

This module fixes the signal-to-noise problem two ways:

  1. `CURATED_REPOS` — a hand-picked list of repositories that are
     known to contain executable strategy code (backtest.py libraries,
     Pine strategies with clear entry/exit blocks, MT5 EAs with source,
     public Freqtrade / QuantConnect / VectorBT strategy repos, etc.).
     The collector will ingest these UNCONDITIONALLY every cycle.

  2. `HIGH_SIGNAL_QUERIES` — narrower search queries with GitHub
     modifiers (`language:pinescript`, `filename:strategy.py`, star
     thresholds, path constraints) so the query results are pre-filtered
     to repos that *actually* contain trading logic.

Both are versioned in-source so operators can audit and PR changes.
Runtime override: `INGESTION_GITHUB_QUERIES` / `INGESTION_GITHUB_REPOS`
env vars (comma-separated) take precedence — see `collector.py`.

Non-goal: this file does NOT vet the *quality* of the strategies at
each repo. Downstream `parser.py` + `validator.py` reject anything
without a parseable entry/exit block, so a curated repo that stops
being useful will simply degrade to zero ingested rows.
"""
from __future__ import annotations

from typing import List, Tuple


# ── High-signal GitHub search queries ────────────────────────────────
# Each entry is a *fully-formed GitHub advanced-search query string*.
# Prefer language filters, file-name / path constraints, star cut-offs.
# Keep the list short — the ingestion runner iterates every one.
HIGH_SIGNAL_QUERIES: List[str] = [
    # Pine Script — study/strategy files only, must have a real body.
    'language:pinescript stars:>50 "strategy("',
    'language:pinescript "strategy.entry" stars:>20',

    # Python backtesting libraries — repos hosting *strategy files*.
    'filename:strategy.py language:python "backtrader" stars:>50',
    'filename:strategy.py language:python "vectorbt" stars:>25',
    'filename:strategy.py language:python "freqtrade" stars:>50',
    '"class.*Strategy" language:python "def next" stars:>30 topic:algotrading',

    # MT4/MT5 Expert Advisors — .mq4/.mq5 files with actual OnTick logic.
    'extension:mq5 "OnTick" stars:>10',
    'extension:mq4 "OnTick" stars:>10',

    # QuantConnect Lean strategies.
    '"Initialize" "OnData" language:python topic:quantconnect stars:>20',

    # Cross-platform: repos explicitly tagged as trading-strategies.
    'topic:trading-strategies stars:>75',
    'topic:algorithmic-trading stars:>100',
]


# ── Curated repository allow-list ────────────────────────────────────
# (owner, repo, one-line rationale). These are always crawled — no
# search step involved. Keep to <30 to stay under GitHub rate limits.
# NOTE: license compatibility is checked upstream by the parser, which
# ships only the structural signal (indicators + entry/exit tokens),
# never the verbatim code, into the knowledge index.
CURATED_REPOS: List[Tuple[str, str, str]] = [
    # ── Python backtesting frameworks with real strategy examples ─────
    ("mementum", "backtrader", "reference implementation site (samples/)"),
    ("polakowo", "vectorbt", "high-star vectorised backtester examples"),
    ("kernc",   "backtesting.py", "canonical Python backtester examples"),
    ("edtechre", "pybroker", "modern Python framework examples"),
    ("QuantConnect", "Lean", "official Lean strategy library"),

    # ── Freqtrade strategy corpora ────────────────────────────────────
    ("freqtrade", "freqtrade-strategies", "official strategy examples"),
    ("iterativv", "NostalgiaForInfinity", "actively-maintained NFI series"),
    ("Kyoto-Meister", "kyoto-Freqtrade-strategies", "community NFI derivatives"),

    # ── Pine Script strategy collections ──────────────────────────────
    ("robswc", "tradingview-scraper", "TradingView strategy scraper (Pine samples)"),
    ("PineCoders", "TASC-Article-Strategies", "Technical Analysis of Stocks & Commodities"),

    # ── MT5 / MQL5 corpora ────────────────────────────────────────────
    ("MetaTrader5", "python-forex-strategies", "modern MT5 python bridge examples"),

    # ── Multi-language / research corpora ─────────────────────────────
    ("hackingthemarkets", "trend-following-python", "Sentdex/HTM trend examples"),
    ("stefan-jansen", "machine-learning-for-trading", "Jansen textbook strategies"),
    ("je-suis-tm", "quant-trading", "collection of trend/mean-rev studies"),

    # ── Prop-firm / challenge-specific ────────────────────────────────
    ("bitperbit", "prop-firm-strategies", "prop-firm challenge references"),
]


def normalize_repo_full_name(entry: Tuple[str, str, str]) -> str:
    owner, repo, _ = entry
    return f"{owner}/{repo}"


def all_curated_full_names() -> List[str]:
    return [normalize_repo_full_name(e) for e in CURATED_REPOS]
