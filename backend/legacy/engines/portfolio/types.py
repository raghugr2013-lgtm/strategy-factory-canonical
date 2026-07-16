"""Phase D — shared types."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

ActionLiteral = Literal["ACTIVATE", "PAUSE", "REDUCE", "INCREASE", "REPLACE", "HOLD"]


@dataclass
class PortfolioMember:
    strategy_hash:  str
    style:          str = "unknown"
    confidence:     float = 0.5
    allocation:     float = 0.0            # 0..1
    status:         str = "active"         # active | paused | research
    tier:           str = "tier_3"         # tier_1 | tier_2 | tier_3 | research | production
    backtest:       Dict[str, Any] = field(default_factory=dict)
    equity_curve:   List[float]   = field(default_factory=list)
    recent_outcomes: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PortfolioMember":
        return cls(
            strategy_hash=str(d.get("strategy_hash") or d.get("hash") or ""),
            style=str(d.get("style") or "unknown"),
            confidence=float(d.get("confidence") or 0.5),
            allocation=float(d.get("allocation") or 0.0),
            status=str(d.get("status") or "active"),
            tier=str(d.get("tier") or "tier_3"),
            backtest=d.get("backtest") or {},
            equity_curve=list(d.get("equity_curve") or []),
            recent_outcomes=list(d.get("recent_outcomes") or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioAction:
    strategy_hash: str
    action:        str                    # ActionLiteral
    weight_delta:  float = 0.0
    reason:        str = ""
    evidence:      Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioState:
    master_bot_id: str
    tier:          str = "tier_1"
    members:       List[PortfolioMember] = field(default_factory=list)
    cash_reserve:  float = 0.1
    last_rebuild:  Optional[str] = None
    health:        Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PortfolioState":
        return cls(
            master_bot_id=str(d.get("master_bot_id") or ""),
            tier=str(d.get("tier") or "tier_1"),
            members=[PortfolioMember.from_dict(m) for m in (d.get("members") or [])],
            cash_reserve=float(d.get("cash_reserve") or 0.1),
            last_rebuild=d.get("last_rebuild"),
            health=d.get("health") or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "master_bot_id": self.master_bot_id,
            "tier":          self.tier,
            "members":       [m.to_dict() for m in self.members],
            "cash_reserve":  self.cash_reserve,
            "last_rebuild":  self.last_rebuild,
            "health":        self.health,
        }
