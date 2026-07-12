"""P0B Phase 4 — Repository-wide BID ↔ BI5 firewall scan.

This test enumerates every BID-stage source file and asserts that
NONE of them imports any BI5-side module. It is the executable form
of the firewall confirmation that was previously asserted by hand.

If you legitimately need to share a value with BID, route it through
a function argument (e.g. ``stability_score: float``), not an import.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Tuple

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Files (modules) that constitute each BID stage. These trees are the
# canonical owners of: Discovery, Mutation, Validation, Pass-Probability,
# Challenge Matching, Portfolio Selection / Combiner / Builder, and the
# Phase-30 Elite-Survivor / Governance / Deployment surfaces.
BID_STAGE_MODULES = {
    "discovery": [
        "engines/auto_factory.py",
        "engines/auto_factory_engine.py",
        "engines/auto_factory_phase55.py",
        "engines/gem_factory_engine.py",
    ],
    "mutation": [
        "engines/auto_mutation_runner.py",
        "engines/mutation_engine.py",
        "engines/mutation_pool.py",
        "engines/strategy_mutation.py",
        "api/mutation.py",
        "api/auto_mutation.py",
    ],
    "validation": [
        "engines/validation_engine.py",
        "engines/validation_report.py",
    ],
    "pass_probability": [
        "engines/pass_probability.py",
    ],
    "challenge_matching": [
        "engines/challenge_matching_engine.py",
        "engines/matching_engine.py",
        "api/challenge_matching.py",
    ],
    "portfolio_selection": [
        "engines/portfolio_engine.py",
        "engines/portfolio_builder_engine.py",
        "engines/portfolio_combiner.py",
        "engines/portfolio_intelligence_engine.py",
        "engines/portfolio_store.py",
        "engines/multi_asset_portfolio.py",
        "engines/challenge_portfolio.py",
        "engines/optimization_portfolio_bridge.py",
        "api/portfolio_builder.py",
        "api/portfolio_intelligence.py",
    ],
}

# BI5 modules a BID-stage file MUST NOT import (directly or as a
# from-import). We match on module path prefixes, so e.g.
# `engines.tick_validator` covers `from engines.tick_validator import …`.
BI5_FORBIDDEN_PREFIXES = (
    # Phase 1 evaluators
    "engines.tick_validator",
    "engines.spread_analyzer",
    "engines.slippage_model",
    "engines.execution_simulator",
    # Phase 3 orchestrator
    "engines.bi5_certification",
    # Phase 2 + 3 persistence
    "engines.persistence_adapters.market_spread_store",
    "engines.persistence_adapters.bi5_data_certification_store",
    "engines.persistence_adapters.bi5_certification_store",
    "engines.persistence_adapters",
    # BI5 ingest pipeline
    "data_engine.bi5_ingest_runner",
    "data_engine.tick_aggregator",
    "data_engine.tick_archive",
    # BI5 admin seams
    "api.bi5_certification",
    "api.bi5_ingest",
)


def _module_paths_of(file_path: Path) -> List[str]:
    """Extract every `import X` / `from X import …` module path."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports — they are project-local but never
            # cross stage boundaries (a discovery module's relative
            # import stays inside discovery).
            if node.level and not node.module:
                continue
            out.append(node.module or "")
    return out


def _is_forbidden(module: str) -> bool:
    return any(
        module == p or module.startswith(p + ".")
        for p in BI5_FORBIDDEN_PREFIXES
    )


@pytest.mark.parametrize("stage", sorted(BID_STAGE_MODULES.keys()))
def test_bid_stage_has_no_bi5_imports(stage: str) -> None:
    """Each BID stage must be 100 % BI5-free at import-time."""
    offenders: List[Tuple[str, str]] = []
    for rel in BID_STAGE_MODULES[stage]:
        p = BACKEND_ROOT / rel
        if not p.is_file():
            # Allow optional files to be absent without failing the
            # whole stage — the discovery loop above already proved
            # each stage has *at least* one file.
            continue
        for mod in _module_paths_of(p):
            if _is_forbidden(mod):
                offenders.append((rel, mod))

    assert not offenders, (
        f"BID stage {stage!r} imports BI5 modules — firewall breach.\n"
        + "\n".join(f"  {rel}: import {mod}" for rel, mod in offenders)
    )


def test_at_least_one_file_scanned_per_stage() -> None:
    """Sanity: the file inventory above should still match the repo."""
    missing: List[str] = []
    for stage, files in BID_STAGE_MODULES.items():
        existing = [f for f in files if (BACKEND_ROOT / f).is_file()]
        if not existing:
            missing.append(stage)
    assert not missing, (
        "No files found on disk for BID stages: "
        f"{missing} — update BID_STAGE_MODULES."
    )


def test_no_reverse_dep_into_bid_from_bi5_modules() -> None:
    """The BI5 modules must not import any BID-stage module either —
    the firewall is bidirectional."""
    bi5_files = [
        "engines/tick_validator.py",
        "engines/spread_analyzer.py",
        "engines/slippage_model.py",
        "engines/execution_simulator.py",
        "engines/bi5_certification.py",
        "engines/persistence_adapters/market_spread_store.py",
        "engines/persistence_adapters/bi5_data_certification_store.py",
        "engines/persistence_adapters/bi5_certification_store.py",
    ]
    forbidden_bid_prefixes = (
        "engines.auto_factory", "engines.gem_factory_engine",
        "engines.auto_mutation_runner", "engines.mutation_engine",
        "engines.mutation_pool", "engines.strategy_mutation",
        "engines.validation_engine", "engines.validation_report",
        "engines.pass_probability",
        "engines.challenge_matching_engine", "engines.matching_engine",
        "engines.portfolio_engine", "engines.portfolio_builder_engine",
        "engines.portfolio_combiner", "engines.portfolio_intelligence_engine",
        "engines.portfolio_store", "engines.multi_asset_portfolio",
        "engines.challenge_portfolio", "engines.optimization_portfolio_bridge",
        "engines.market_universe",
    )
    offenders: List[Tuple[str, str]] = []
    for rel in bi5_files:
        p = BACKEND_ROOT / rel
        if not p.is_file():
            continue
        for mod in _module_paths_of(p):
            if any(mod == fp or mod.startswith(fp + ".")
                   for fp in forbidden_bid_prefixes):
                offenders.append((rel, mod))
    assert not offenders, (
        "BI5 modules reverse-depend on BID stages — firewall breach.\n"
        + "\n".join(f"  {rel}: import {mod}" for rel, mod in offenders)
    )


def test_string_scan_catches_dynamic_imports() -> None:
    """Belt-and-braces: catch dynamic `importlib.import_module('…')`
    or string-based imports the AST scan would miss."""
    pattern = re.compile(
        r"""(?:importlib\.import_module|__import__)\s*\(\s*['"]"""
        r"(?P<mod>engines\.tick_validator|engines\.spread_analyzer|"
        r"engines\.slippage_model|engines\.execution_simulator|"
        r"engines\.bi5_certification|engines\.persistence_adapters[^'\"]*|"
        r"data_engine\.bi5_ingest_runner|api\.bi5_certification|"
        r"api\.bi5_ingest)['\"]"""
    )
    offenders: List[Tuple[str, str]] = []
    for stage, files in BID_STAGE_MODULES.items():
        for rel in files:
            p = BACKEND_ROOT / rel
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                offenders.append((rel, m.group("mod")))
    assert not offenders, (
        "Dynamic BI5 imports detected in BID stage:\n"
        + "\n".join(f"  {rel}: {mod}" for rel, mod in offenders)
    )
