"""Phase B.2 — Provider-aware budget tracker.

In-memory rolling-window state + cost accounting. Not persisted in this
first cut (matches Q5 direction: one architectural change per phase). A
follow-up phase can add Mongo persistence for restart survival without
touching the public API here.

Public API:
    class BudgetTracker
        can_afford(provider, est_cost_usd) -> (bool, reason)
        can_afford_global(est_cost_usd)    -> (bool, reason)
        record(provider, cost_usd, tokens) -> None
        register_call(provider)            -> None  # for RPM tracking
        snapshot()                          -> dict
        choose_provider(candidates,
                        est_cost_usd,
                        weights,
                        quality_scores,
                        latencies_ms,
                        breaker_states)    -> str | None

    class BudgetWeights (cost, quality, latency, availability)

    get_budget_tracker() -> singleton

Environment configuration (§6 of the design doc):
    ORCH_BUDGET_DAILY_USD_GLOBAL   default 50.0
    ORCH_BUDGET_MONTHLY_USD_GLOBAL default 1000.0
    ORCH_BUDGET_DAILY_USD_<PROVIDER>   optional
    ORCH_BUDGET_RPM_<PROVIDER>         default 60
    ORCH_BUDGET_WEIGHT_COST/QUALITY/LATENCY/AVAILABILITY
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Env helpers ─────────────────────────────────────────────────────

def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


# ── Weight dataclass ────────────────────────────────────────────────

@dataclass
class BudgetWeights:
    cost:         float = 0.4
    quality:      float = 0.4
    latency:      float = 0.15
    availability: float = 0.05

    @classmethod
    def from_env(cls) -> "BudgetWeights":
        return cls(
            cost=_float_env("ORCH_BUDGET_WEIGHT_COST", 0.4),
            quality=_float_env("ORCH_BUDGET_WEIGHT_QUALITY", 0.4),
            latency=_float_env("ORCH_BUDGET_WEIGHT_LATENCY", 0.15),
            availability=_float_env("ORCH_BUDGET_WEIGHT_AVAILABILITY", 0.05),
        )


# ── Tracker ─────────────────────────────────────────────────────────

class BudgetTracker:
    """Thread-safe in-memory budget accounting.

    Windows:
      - Provider RPM: rolling 60 s deque of call timestamps per provider.
      - Provider daily USD: (day_iso, running_sum) per provider; rolls at UTC midnight.
      - Global daily USD: same shape, aggregated.
      - Global monthly USD: (YYYY-MM, running_sum); rolls at month boundary.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._rpm_windows: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=1024))
        self._daily_provider: Dict[str, Tuple[str, float]] = {}
        self._daily_global: Tuple[str, float] = ("", 0.0)
        self._monthly_global: Tuple[str, float] = ("", 0.0)
        # Cumulative counters (for observability; never reset).
        self._calls_total: Dict[str, int] = defaultdict(int)
        self._cost_total_usd: Dict[str, float] = defaultdict(float)
        self._tokens_total: Dict[str, int] = defaultdict(int)

    # ── Time bucket helpers ──
    @staticmethod
    def _day_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _month_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _prune_rpm(self, provider: str, now: float) -> int:
        dq = self._rpm_windows[provider]
        cutoff = now - 60.0
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)

    def _roll_daily(self, provider: str) -> float:
        day = self._day_key()
        cur = self._daily_provider.get(provider)
        if cur is None or cur[0] != day:
            self._daily_provider[provider] = (day, 0.0)
        return self._daily_provider[provider][1]

    def _roll_daily_global(self) -> float:
        day = self._day_key()
        if self._daily_global[0] != day:
            self._daily_global = (day, 0.0)
        return self._daily_global[1]

    def _roll_monthly_global(self) -> float:
        month = self._month_key()
        if self._monthly_global[0] != month:
            self._monthly_global = (month, 0.0)
        return self._monthly_global[1]

    # ── Public: affordability ──
    def can_afford(self, provider: str, est_cost_usd: float) -> Tuple[bool, str]:
        """Check ALL applicable ceilings BEFORE charging. Never raises."""
        with self._lock:
            now = time.time()
            # 1. Provider RPM
            rpm_cap = _int_env(f"ORCH_BUDGET_RPM_{provider.upper()}", 60)
            in_window = self._prune_rpm(provider, now)
            if rpm_cap > 0 and in_window >= rpm_cap:
                return False, f"provider_rpm_exceeded ({in_window}/{rpm_cap} in last 60s)"
            # 2. Per-provider daily USD (unset = no cap)
            per_prov_daily_env = os.environ.get(
                f"ORCH_BUDGET_DAILY_USD_{provider.upper()}"
            )
            if per_prov_daily_env and per_prov_daily_env.strip():
                try:
                    cap = float(per_prov_daily_env)
                    spent = self._roll_daily(provider)
                    if spent + est_cost_usd > cap:
                        return False, f"provider_daily_usd_exceeded ({spent:.2f}+{est_cost_usd:.2f}>{cap:.2f})"
                except ValueError:
                    pass
            # 3. Global daily USD
            g_daily_cap = _float_env("ORCH_BUDGET_DAILY_USD_GLOBAL", 50.0)
            g_daily = self._roll_daily_global()
            if g_daily + est_cost_usd > g_daily_cap:
                return False, f"global_daily_usd_exceeded ({g_daily:.2f}+{est_cost_usd:.2f}>{g_daily_cap:.2f})"
            # 4. Global monthly USD
            g_monthly_cap = _float_env("ORCH_BUDGET_MONTHLY_USD_GLOBAL", 1000.0)
            g_monthly = self._roll_monthly_global()
            if g_monthly + est_cost_usd > g_monthly_cap:
                return False, f"global_monthly_usd_exceeded ({g_monthly:.2f}+{est_cost_usd:.2f}>{g_monthly_cap:.2f})"
            return True, "ok"

    def can_afford_global(self, est_cost_usd: float) -> Tuple[bool, str]:
        """Provider-agnostic pre-check — useful when the task hasn't picked a provider yet."""
        with self._lock:
            g_daily_cap = _float_env("ORCH_BUDGET_DAILY_USD_GLOBAL", 50.0)
            g_daily = self._roll_daily_global()
            if g_daily + est_cost_usd > g_daily_cap:
                return False, f"global_daily_usd_exceeded ({g_daily:.2f}+{est_cost_usd:.2f}>{g_daily_cap:.2f})"
            g_monthly_cap = _float_env("ORCH_BUDGET_MONTHLY_USD_GLOBAL", 1000.0)
            g_monthly = self._roll_monthly_global()
            if g_monthly + est_cost_usd > g_monthly_cap:
                return False, f"global_monthly_usd_exceeded ({g_monthly:.2f}+{est_cost_usd:.2f}>{g_monthly_cap:.2f})"
            return True, "ok"

    # ── Public: recording ──
    def register_call(self, provider: str) -> None:
        """Increment the RPM window at call-launch time. Cheap; no cost math."""
        with self._lock:
            self._rpm_windows[provider].append(time.time())
            self._calls_total[provider] += 1

    def record(self, provider: str, cost_usd: float, tokens: int = 0) -> None:
        """Record a completed call's cost + tokens against every window."""
        cost_usd = max(0.0, float(cost_usd))
        tokens = max(0, int(tokens))
        with self._lock:
            self._roll_daily(provider)
            day, spent = self._daily_provider[provider]
            self._daily_provider[provider] = (day, spent + cost_usd)

            self._roll_daily_global()
            self._daily_global = (self._daily_global[0], self._daily_global[1] + cost_usd)

            self._roll_monthly_global()
            self._monthly_global = (self._monthly_global[0], self._monthly_global[1] + cost_usd)

            self._cost_total_usd[provider] += cost_usd
            self._tokens_total[provider] += tokens

        # Phase 2 Stage 1 — best-effort write-through. Uses fire-and-forget
        # asyncio task when a loop is running; otherwise silently no-ops
        # (record() may be called from sync engine code — sync callers
        # rely on load_from_mongo() at boot + periodic explicit flush).
        if self._persist_enabled():
            try:
                import asyncio as _asyncio
                loop = _asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.flush_to_mongo())
            except Exception:  # noqa: BLE001
                pass

    # ── Public: provider selection ──
    def choose_provider(
        self,
        candidates: List[str],
        est_cost_usd: float,
        weights: Optional[BudgetWeights] = None,
        quality_scores: Optional[Dict[str, float]] = None,
        latencies_ms: Optional[Dict[str, float]] = None,
        breaker_states: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Weighted pick among affordable candidates.

        For every candidate that passes `can_afford()`, compute:

            score =   weights.cost         × cost_component
                    + weights.quality      × quality_component
                    + weights.latency      × latency_component
                    + weights.availability × availability_component

        Where:
          - cost_component is inversely proportional to cost (cheaper = higher).
          - quality_component in [0..1] from provider quality scorer.
          - latency_component is inversely proportional to latency (faster = higher).
          - availability_component is 1.0 for `closed`, 0.5 for `half_open`, 0 for `open`.

        Returns the highest-scoring provider, or None if no candidate is affordable.
        """
        weights = weights or BudgetWeights.from_env()
        quality_scores = quality_scores or {}
        latencies_ms = latencies_ms or {}
        breaker_states = breaker_states or {}

        affordable: List[Tuple[str, float]] = []
        with self._lock:
            for p in candidates:
                ok, _reason = self.can_afford(p, est_cost_usd)
                if not ok:
                    continue
                # Provider-specific normalisation
                cost_component = 1.0 / (est_cost_usd + 0.001)      # never divide by 0
                quality_component = float(quality_scores.get(p, 0.5))
                lat = float(latencies_ms.get(p, 1000.0))
                latency_component = 1.0 / max(50.0, lat)           # cap floor at 50ms
                bs = breaker_states.get(p, "closed")
                availability_component = {"closed": 1.0, "half_open": 0.5, "open": 0.0}.get(bs, 1.0)

                score = (
                    weights.cost         * cost_component
                    + weights.quality      * quality_component
                    + weights.latency      * latency_component
                    + weights.availability * availability_component
                )
                affordable.append((p, score))
        if not affordable:
            return None
        affordable.sort(key=lambda x: (-x[1], x[0]))
        return affordable[0][0]

    # ── Public: snapshot ──
    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            # Ensure day/month buckets are current for the snapshot.
            _ = self._roll_daily_global()
            _ = self._roll_monthly_global()
            for p in list(self._daily_provider.keys()):
                self._roll_daily(p)

            g_daily_cap = _float_env("ORCH_BUDGET_DAILY_USD_GLOBAL", 50.0)
            g_monthly_cap = _float_env("ORCH_BUDGET_MONTHLY_USD_GLOBAL", 1000.0)

            per_provider = {}
            now = time.time()
            for p in set(list(self._rpm_windows.keys())
                          + list(self._daily_provider.keys())
                          + list(self._cost_total_usd.keys())):
                in_window = self._prune_rpm(p, now)
                daily_env = os.environ.get(f"ORCH_BUDGET_DAILY_USD_{p.upper()}")
                try:
                    daily_cap = float(daily_env) if daily_env else None
                except ValueError:
                    daily_cap = None
                per_provider[p] = {
                    "calls_total":       self._calls_total.get(p, 0),
                    "cost_total_usd":    round(self._cost_total_usd.get(p, 0.0), 4),
                    "tokens_total":      self._tokens_total.get(p, 0),
                    "rpm_last_60s":      in_window,
                    "rpm_cap":           _int_env(f"ORCH_BUDGET_RPM_{p.upper()}", 60),
                    "daily_spent_usd":   round(self._daily_provider.get(p, ("", 0.0))[1], 4),
                    "daily_cap_usd":     daily_cap,
                }
            return {
                "ts": datetime.now(timezone.utc).isoformat(),
                "global": {
                    "daily_spent_usd":  round(self._daily_global[1], 4),
                    "daily_cap_usd":    g_daily_cap,
                    "daily_headroom":   round(max(0.0, g_daily_cap - self._daily_global[1]), 4),
                    "monthly_spent_usd": round(self._monthly_global[1], 4),
                    "monthly_cap_usd":   g_monthly_cap,
                    "day_key":          self._daily_global[0],
                    "month_key":        self._monthly_global[0],
                },
                "per_provider": per_provider,
                "weights": BudgetWeights.from_env().__dict__,
            }

    # ── Test-only ──
    def _reset(self) -> None:
        with self._lock:
            self._rpm_windows.clear()
            self._daily_provider.clear()
            self._daily_global = ("", 0.0)
            self._monthly_global = ("", 0.0)
            self._calls_total.clear()
            self._cost_total_usd.clear()
            self._tokens_total.clear()

    # ── Phase 2 Stage 1 — Mongo persistence (flag-gated) ────────────
    #
    # When `BUDGET_PERSIST=true`, the tracker mirrors its rolling state
    # to `budget_state` (single-doc collection). Load at startup;
    # write-through on every `record()`. Never raises — Mongo failure
    # logs a warning and the in-memory path continues unchanged.
    #
    # Rollback: flip `BUDGET_PERSIST=false` — writes stop; existing
    # collection is untouched (safe to keep around).

    BUDGET_STATE_COLLECTION = "budget_state"
    BUDGET_STATE_ID = "singleton"

    @staticmethod
    def _persist_enabled() -> bool:
        raw = (os.environ.get("BUDGET_PERSIST") or "").strip().lower()
        return raw in ("1", "true", "yes", "y", "on")

    async def load_from_mongo(self) -> bool:
        """Rehydrate rolling state from Mongo. Called once at boot when
        `BUDGET_PERSIST=true`. Returns True on successful load, False on
        no-row / error. Never raises."""
        if not self._persist_enabled():
            return False
        try:
            from engines.db import get_db
            db = get_db()
            doc = await db[self.BUDGET_STATE_COLLECTION].find_one(
                {"_id": self.BUDGET_STATE_ID}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[budget_tracker] load_from_mongo failed: %s", e)
            return False
        if not doc:
            return False
        with self._lock:
            # Daily global — only accept if the day key matches TODAY.
            today = self._day_key()
            g_daily = doc.get("daily_global") or {}
            if g_daily.get("day") == today:
                self._daily_global = (today, float(g_daily.get("spent_usd") or 0.0))
            # Monthly global — same discipline.
            this_month = self._month_key()
            g_monthly = doc.get("monthly_global") or {}
            if g_monthly.get("month") == this_month:
                self._monthly_global = (this_month, float(g_monthly.get("spent_usd") or 0.0))
            # Per-provider daily.
            for p, row in (doc.get("daily_provider") or {}).items():
                if not isinstance(row, dict):
                    continue
                if row.get("day") != today:
                    continue
                self._daily_provider[p] = (today, float(row.get("spent_usd") or 0.0))
            # Cumulative counters (survive across days).
            for p, n in (doc.get("cost_total_usd") or {}).items():
                self._cost_total_usd[p] = float(n or 0.0)
            for p, n in (doc.get("tokens_total") or {}).items():
                self._tokens_total[p] = int(n or 0)
            for p, n in (doc.get("calls_total") or {}).items():
                self._calls_total[p] = int(n or 0)
        return True

    async def flush_to_mongo(self) -> bool:
        """Best-effort write-through. Never raises."""
        if not self._persist_enabled():
            return False
        try:
            from engines.db import get_db
            db = get_db()
            with self._lock:
                doc = {
                    "daily_global": {
                        "day": self._daily_global[0],
                        "spent_usd": round(self._daily_global[1], 6),
                    },
                    "monthly_global": {
                        "month": self._monthly_global[0],
                        "spent_usd": round(self._monthly_global[1], 6),
                    },
                    "daily_provider": {
                        p: {"day": day, "spent_usd": round(spent, 6)}
                        for p, (day, spent) in self._daily_provider.items()
                    },
                    "cost_total_usd": {p: round(v, 6) for p, v in self._cost_total_usd.items()},
                    "tokens_total": dict(self._tokens_total),
                    "calls_total": dict(self._calls_total),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            await db[self.BUDGET_STATE_COLLECTION].update_one(
                {"_id": self.BUDGET_STATE_ID},
                {"$set": doc},
                upsert=True,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug("[budget_tracker] flush_to_mongo failed: %s", e)
            return False


# ── Singleton accessor ──────────────────────────────────────────────

_TRACKER: Optional[BudgetTracker] = None


def get_budget_tracker() -> BudgetTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = BudgetTracker()
    return _TRACKER
