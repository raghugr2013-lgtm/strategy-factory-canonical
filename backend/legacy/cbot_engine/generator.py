"""
cBot code generator: legacy LLM/stub path (RETIRED — P0.1).

Historical role
---------------
This module previously returned a hard-coded ``SimpleBot`` that opened a
single 1000-unit BUY in ``OnTick`` regardless of ``strategy_text``,
indicator parameters, or backtest results. It was the "Offline mode (LLM
disabled)" fallback wired into ``api/cbot.py::generate_cbot`` and
``api/pipeline.py::run_full_pipeline``.

The audit (memory/EXECUTION_REALISM_AUDIT.md §1.1, §5, §6) identified
this as the largest export-reliability risk in the codebase:

  > "Any pipeline that still posts to /api/generate-cbot WITHOUT a
  >  strategy_ir payload silently receives a stub bot whose only
  >  behaviour is `if Positions.Count == 0: ExecuteMarketOrder(BUY, 1000)`
  >  on every tick. The endpoint returns HTTP 200 with
  >  source='legacy_generator' — there is no error, no warning, no
  >  compile failure."

P0.1 — Hard-disable
-------------------
Per operator directive (2026-05-22): *deterministic OR fail*, never
*deterministic OR silently degrade*. As of P0.1, every entry point into
this function raises ``LegacyGeneratorRetiredError`` (a subclass of
``RuntimeError``) immediately, before any C# code is produced.

* ``api/cbot.py`` already short-circuits at the router (HTTP 410 when
  ``strategy_ir`` is absent). This guards the public surface.
* ``api/pipeline.py`` wraps the call in a try/except. When the legacy
  generator raises, the failure is captured in ``steps_log`` as
  ``"cBot generation failed: legacy_generator_retired"`` — explicit,
  operator-visible, structured.
* Any future caller that grew up around the stub will now fail loudly
  on its first call, exactly when the operator can still see the
  deviation rather than after a fleet deployment.

The original ``CBOT_SYSTEM_PROMPT`` text and the per-strategy-type
``SIGNAL_LOGIC`` dictionary are retained below as **read-only
documentation** of the historical intent. They are not referenced by
any active code path; they remain only so the institutional record of
"what the legacy generator was supposed to do, had the LLM path ever
been wired up" is preserved for future audits.

Reversibility
-------------
Removing the P0.1 raise is a single-line revert (restore the original
``return {"code": "...SimpleBot..."}``). The SimpleBot template lives
in this module's docstring history (see git log) — it was operationally
unsafe and is intentionally not preserved as live data.
"""
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Structured error contract (P0.1)
# ─────────────────────────────────────────────────────────────────────
class LegacyGeneratorRetiredError(RuntimeError):
    """Raised by ``generate_cbot_code(...)`` to signal that the legacy
    LLM/stub cBot generation path has been retired.

    Attributes
    ----------
    error_code : str
        Stable machine-readable identifier: ``legacy_cbot_generator_retired``.
    phase : str
        ``P0.1`` — the institutional execution-hardening pass that
        retired this path.
    retired_at : str
        ``2026-05-22`` (UTC ISO date).
    remediation : str
        Operator-readable migration guidance (build a StrategyIR via
        ``engines.strategy_ir_builders`` or ``engines.mutation_engine``
        and route through ``cbot_engine.ir_transpiler.transpile_ir_to_csharp``).
    operator_message : str
        Long-form, operator-readable explanation.
    """

    error_code: str = "legacy_cbot_generator_retired"
    phase: str = "P0.1"
    retired_at: str = "2026-05-22"
    remediation: str = (
        "Build the StrategyIR first (engines.strategy_ir_builders or "
        "engines.mutation_engine), then call "
        "cbot_engine.ir_transpiler.transpile_ir_to_csharp(ir) — or POST "
        "to /api/generate-cbot with `strategy_ir` set so the router "
        "dispatches to the deterministic IR transpiler."
    )
    operator_message: str = (
        "The legacy (no-IR) cBot generator has been retired as of "
        "P0.1 (2026-05-22). It previously returned a hard-coded "
        "SimpleBot stub that ignored strategy_text and would have "
        "produced an executing-but-meaningless cBot. Callers MUST "
        "migrate to the deterministic IR transpiler path."
    )

    def __init__(self, *, caller: str = "<unknown>") -> None:
        self.caller = caller
        super().__init__(
            f"[{self.error_code}] {self.operator_message} "
            f"(caller={caller}, phase={self.phase}, "
            f"retired_at={self.retired_at}). Remediation: {self.remediation}"
        )


# ─────────────────────────────────────────────────────────────────────
# Historical documentation (NOT referenced by any active code path).
# Retained only as an institutional record of the legacy intent.
# ─────────────────────────────────────────────────────────────────────
CBOT_SYSTEM_PROMPT = """[RETIRED P0.1] This prompt was the intended
system prompt for the legacy LLM-driven cBot generator. The LLM path
was never wired up in production; the module returned a hard-coded
SimpleBot stub instead. Both have been retired. The canonical path
is now cbot_engine.ir_transpiler.transpile_ir_to_csharp(ir)."""

# Strategy-type signal-logic descriptions are no longer consulted at
# runtime. They are preserved here only as documentation of what the
# legacy LLM prompt was expected to encode.
SIGNAL_LOGIC: dict = {}


async def generate_cbot_code(*args, **kwargs):  # noqa: D401 — keep signature for callers
    """RETIRED (P0.1). Always raises ``LegacyGeneratorRetiredError``.

    The signature is preserved so static call-site analysis still finds
    every caller; the body fails loudly on entry so no caller can
    silently receive a stub bot.
    """
    caller = kwargs.pop("_caller", None) or "<unknown>"
    logger.error(
        "[legacy_cbot_generator_retired] generate_cbot_code() invoked "
        "from caller=%s — refusing per P0.1 operator directive. "
        "Migrate to cbot_engine.ir_transpiler.transpile_ir_to_csharp.",
        caller,
    )
    raise LegacyGeneratorRetiredError(caller=caller)
