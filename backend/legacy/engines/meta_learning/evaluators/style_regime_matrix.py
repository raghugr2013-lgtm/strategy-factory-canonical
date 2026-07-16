"""Phase I — style_regime_matrix evaluator (§7.4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import normalise_pnl
from ..types import MetaEvaluation, MetaSurface

METHOD = "style_regime_miscalibration_v1"


def evaluate_style_regime_matrix(
    pairs: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int,
) -> List[MetaEvaluation]:
    if not pairs:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()

    cells: Dict[str, Dict[str, float]] = {}
    for p in pairs:
        d = p.get("decision") or {}
        m = d.get("metrics") or {}
        style = str(m.get("style") or m.get("brain_style") or "unknown")
        regime = str(m.get("regime") or m.get("brain_regime") or "unknown")
        r = (p.get("realised") or {}).get("metrics") or {}
        pnl = float(r.get("realised_pnl") or 0.0)
        expected = float(m.get("regime_fit") or m.get("score_now") or 0.5)
        realised = (normalise_pnl(pnl) + 1.0) / 2.0
        key = f"{style}\u00d7{regime}"
        st = cells.setdefault(key, {"n": 0.0, "exp": 0.0, "real": 0.0})
        st["n"] += 1
        st["exp"] += expected
        st["real"] += realised

    evaluations: List[MetaEvaluation] = []
    for key, st in cells.items():
        if st["n"] < max(3, min_samples // 5):  # per-cell sample floor
            continue
        gap = (st["real"] - st["exp"]) / st["n"]
        eid = "ml_eval_" + uuid.uuid4().hex[:12]
        evaluations.append(MetaEvaluation(
            evaluation_id=eid, account_id=None,
            surface=MetaSurface.STYLE_REGIME_MATRIX,
            target=key,
            window_start=window_start, window_end=window_end,
            n_samples=int(st["n"]),
            method=METHOD,
            metrics={"miscalibration": round(gap, 4),
                      "mean_expected": round(st["exp"] / st["n"], 4),
                      "mean_realised": round(st["real"] / st["n"], 4)},
            significance=round(min(1.0, abs(gap) * 3.0), 4),
            evidence={"style_regime_key": key},
            computed_at=computed_at,
        ))
    return evaluations
