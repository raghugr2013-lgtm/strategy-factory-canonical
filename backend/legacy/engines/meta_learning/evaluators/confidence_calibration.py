"""Phase I — confidence_calibration evaluator (§7.3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import bin_edges, bin_index, normalise_pnl
from ..types import MetaEvaluation, MetaSurface

METHOD = "reliability_curve_gap_v1"


def evaluate_confidence_calibration(
    pairs: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int,
) -> List[MetaEvaluation]:
    if not pairs:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()

    confs: List[float] = []
    outcomes: List[float] = []
    for p in pairs:
        d = p.get("decision") or {}
        m = d.get("metrics") or {}
        c = m.get("confidence") or m.get("brain_confidence")
        r = (p.get("realised") or {}).get("metrics") or {}
        pnl = float(r.get("realised_pnl") or 0.0)
        try:
            confs.append(float(c) if c is not None else 0.5)
            outcomes.append(normalise_pnl(pnl))
        except (TypeError, ValueError):
            continue

    n = len(confs)
    edges = bin_edges(0.0, 1.0, 10)
    bins: Dict[int, Dict[str, float]] = {}
    for c, o in zip(confs, outcomes):
        b = bin_index(c, edges)
        st = bins.setdefault(b, {"n": 0.0, "conf_sum": 0.0, "out_sum": 0.0})
        st["n"] += 1
        st["conf_sum"] += c
        st["out_sum"] += o

    gaps = []
    for st in bins.values():
        if st["n"] > 0:
            mc = st["conf_sum"] / st["n"]
            mo = st["out_sum"] / st["n"]
            # Map outcome [-1,1] → [0,1] for comparison
            mo01 = (mo + 1.0) / 2.0
            gaps.append(abs(mc - mo01))
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0

    eid = "ml_eval_" + uuid.uuid4().hex[:12]
    return [MetaEvaluation(
        evaluation_id=eid,
        account_id=None,
        surface=MetaSurface.CONFIDENCE_CALIBRATION,
        target="BRAIN_CONFIDENCE_SHRINK",
        window_start=window_start, window_end=window_end,
        n_samples=n,
        method=METHOD if n >= min_samples else METHOD + "_n_low",
        metrics={"mean_gap": round(mean_gap, 4),
                  "n_bins_used": len(bins)},
        significance=round(min(1.0, mean_gap * 2.0), 4),
        evidence={"bin_reliability":
                    {str(k): {"n": v["n"],
                               "mean_conf": round(v["conf_sum"] / v["n"], 4),
                               "mean_out01": round((v["out_sum"] / v["n"] + 1) / 2, 4)}
                     for k, v in bins.items() if v["n"] > 0}},
        computed_at=computed_at,
    )]
