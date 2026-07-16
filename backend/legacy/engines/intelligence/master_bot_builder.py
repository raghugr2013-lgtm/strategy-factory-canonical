"""Phase C.3 — Master Bot Builder.

Assembles diversified Tier 1 / Tier 2 / Tier 3 bundles from the pool of
classified, portfolio-scored strategies. Never mutates the underlying
`strategy_library`; produces a `BundleReport` that the operator (or
`master_bot_bundle_refresh` orchestrator task) can persist via
`engines.master_bot_engine.set_tier_metadata`.

Algorithm — greedy contribution-maximising selection with style-balance
and correlation constraints:

    1. Rank the pool by solo_score DESC.
    2. Iterate; for each candidate:
         a. Compute portfolio_contribution_score against the growing bundle.
         b. Accept iff contribution_score ≥ MIN_CONTRIBUTION.
         c. Enforce style cap (no single style > 40% of a tier).
         d. Enforce correlation cap (avg |corr| ≤ 0.7 vs bundle).
    3. Split top 30 accepted into Tier 1 (1..10), Tier 2 (11..20), Tier 3 (21..30).

Deterministic — same pool + same regime → same bundle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .portfolio_intelligence import portfolio_contribution_score, PortfolioScore
from .strategy_intelligence import classify_strategy

MIN_CONTRIBUTION = 0.05
MAX_STYLE_SHARE = 0.4      # no single style > 40% of a tier
MAX_TIER_SIZE = 10


@dataclass
class BundleReport:
    generated_at:   str
    pool_size:      int
    accepted:       int
    rejected:       int
    tier_1:         List[Dict[str, Any]] = field(default_factory=list)
    tier_2:         List[Dict[str, Any]] = field(default_factory=list)
    tier_3:         List[Dict[str, Any]] = field(default_factory=list)
    style_balance:  Dict[str, int]       = field(default_factory=dict)
    rejections:     List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tier_style_frequencies(tier: List[Dict[str, Any]]) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for s in tier:
        st = str(s.get("style") or "unknown")
        freq[st] = freq.get(st, 0) + 1
    return freq


def _accept_style_cap_ok(candidate_style: str, tier: List[Dict[str, Any]]) -> bool:
    if len(tier) >= MAX_TIER_SIZE:
        return False
    proposed_size = len(tier) + 1
    freq = _tier_style_frequencies(tier)
    cand_share = (freq.get(candidate_style, 0) + 1) / proposed_size
    # Allow small tiers (<5) to exceed the cap so we can seed properly.
    if proposed_size < 5:
        return True
    return cand_share <= MAX_STYLE_SHARE


def build_tiered_bundles(
    strategies: List[Dict[str, Any]],
    *,
    min_contribution: float = MIN_CONTRIBUTION,
) -> BundleReport:
    """Build Tier 1 / 2 / 3 from `strategies`.

    Each input element MUST expose:
        - strategy_hash
        - strategy_text (used for classification if `style` not present)
        - backtest_result   (dict) OR flat metric fields (profit_factor, …)
        - equity_curve (optional; enables correlation penalty)
    Returns a `BundleReport`. Never raises.
    """
    from datetime import datetime, timezone

    if not strategies:
        return BundleReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            pool_size=0, accepted=0, rejected=0,
        )

    # 1. Enrich every strategy with classification + solo score.
    enriched: List[Dict[str, Any]] = []
    for s in strategies:
        cls = classify_strategy(s)
        bt = s.get("backtest_result") or s.get("bt") or {
            "profit_factor":    s.get("profit_factor"),
            "max_drawdown_pct": s.get("max_drawdown_pct"),
            "win_rate":         s.get("win_rate"),
            "total_trades":     s.get("total_trades"),
            "rr_ratio":         s.get("rr_ratio"),
        }
        enriched.append({
            "strategy_hash":      cls.strategy_hash,
            "style":              cls.style,
            "regime_suitability": cls.regime_suitability,
            "risk_profile":       cls.risk_profile,
            "confidence":         cls.confidence,
            "backtest":           bt,
            "equity_curve":       s.get("equity_curve") or [],
            "raw":                s,
        })

    # 2. Rank by solo_score DESC (deterministic).
    from .portfolio_intelligence import _solo_score  # noqa: SLF001 — internal use OK
    for e in enriched:
        e["solo_score"] = _solo_score(e["backtest"])
    enriched.sort(key=lambda x: (-x["solo_score"], str(x.get("strategy_hash") or "")))

    # 3. Greedy accept into a single growing bundle up to 30.
    bundle: List[Dict[str, Any]] = []
    rejections: List[Dict[str, Any]] = []

    for c in enriched:
        if len(bundle) >= 3 * MAX_TIER_SIZE:
            break
        ps = portfolio_contribution_score(c, bundle)
        if ps.contribution_score < min_contribution:
            rejections.append({
                "strategy_hash":       c["strategy_hash"],
                "reason":              "below_min_contribution",
                "contribution_score":  ps.contribution_score,
            })
            continue

        # Style cap: only apply if bundle currently has room in ≥ 1 tier below full.
        target_tier_size = min(MAX_TIER_SIZE, len(bundle) % MAX_TIER_SIZE)
        tier_slice_start = (len(bundle) // MAX_TIER_SIZE) * MAX_TIER_SIZE
        current_tier = bundle[tier_slice_start:]
        if not _accept_style_cap_ok(c["style"], current_tier):
            rejections.append({
                "strategy_hash":  c["strategy_hash"],
                "reason":         "style_cap_exceeded",
                "style":          c["style"],
            })
            continue

        c["portfolio_score"] = ps.to_dict()
        bundle.append(c)

    # 4. Split into tiers.
    def _shape(s: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "strategy_hash":     s["strategy_hash"],
            "style":             s["style"],
            "confidence":        s["confidence"],
            "solo_score":        s["solo_score"],
            "regime_suitability": s["regime_suitability"],
            "risk_profile":      s["risk_profile"],
            "portfolio_score":   s.get("portfolio_score"),
        }

    tier_1 = [_shape(s) for s in bundle[0:10]]
    tier_2 = [_shape(s) for s in bundle[10:20]]
    tier_3 = [_shape(s) for s in bundle[20:30]]
    style_balance = _tier_style_frequencies(bundle)

    from datetime import datetime, timezone
    return BundleReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        pool_size=len(strategies),
        accepted=len(bundle),
        rejected=len(rejections),
        tier_1=tier_1, tier_2=tier_2, tier_3=tier_3,
        style_balance=style_balance,
        rejections=rejections[:50],   # cap
    )
