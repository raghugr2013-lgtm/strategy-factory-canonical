"""
Phase 12.5 — Deterministic cBot auto-fixer.

Applies pure string/regex transformations to fix well-known compile errors
emitted by `engines.compile_engine.validate`. Never uses AI / free-text.

Each fix function returns (new_code, applied: bool, note: str) so the
pipeline can report exactly which rules fired.
"""
from __future__ import annotations

import re

from engines.code_generator import (
    build_parameters_block, _indicator_init, _indicator_decls,
    _entry_logic, _exit_logic, sanitise_bot_name,
)


# ── Individual fixers ─────────────────────────────────────────────────

def _fix_unresolved_placeholder(code: str, err: dict, ctx: dict) -> tuple[str, bool, str]:
    placeholders = err.get("detail", {}).get("placeholders", [])
    applied = False
    note = ""
    params = ctx.get("parameters") or {}
    inds = ctx.get("indicators") or {}
    style = ctx.get("style") or "trend_following"
    bot_name = ctx.get("bot_name") or sanitise_bot_name(
        ctx.get("pair"), ctx.get("timeframe"), style,
    )
    for ph in placeholders:
        if ph == "{{BOT_NAME}}":
            code, n = _replace_all(code, ph, bot_name)
            applied |= n > 0
        elif ph == "{{PARAMETERS}}":
            code = code.replace(ph, build_parameters_block(params), 1)
            applied = True
        elif ph == "{{INDICATORS_DECL}}":
            code = code.replace(ph, _indicator_decls(inds), 1)
            applied = True
        elif ph == "{{INDICATORS}}":
            code = code.replace(ph, _indicator_init(inds), 1)
            applied = True
        elif ph == "{{ENTRY_LOGIC}}":
            code = code.replace(ph, _entry_logic(style, inds), 1)
            applied = True
        elif ph == "{{EXIT_LOGIC}}":
            code = code.replace(ph, _exit_logic(), 1)
            applied = True
        else:
            # Unknown placeholder — blank it out so compile can proceed.
            code = code.replace(ph, "// (auto-fix: unknown placeholder removed)")
            applied = True
    if applied:
        note = f"filled placeholders: {placeholders}"
    return code, applied, note


def _replace_all(code: str, old: str, new: str) -> tuple[str, int]:
    n = code.count(old)
    return code.replace(old, new), n


def _fix_missing_using(code: str, _err, _ctx) -> tuple[str, bool, str]:
    if "using cAlgo.API;" in code:
        return code, False, ""
    # Insert after any existing `using System;` line, else at the top.
    if "using System;" in code:
        new = code.replace("using System;", "using System;\nusing cAlgo.API;", 1)
    else:
        new = "using cAlgo.API;\n" + code
    return new, True, "prepended `using cAlgo.API;`"


def _fix_missing_namespace(code: str, _err, _ctx) -> tuple[str, bool, str]:
    if re.search(r"^\s*namespace\s", code, flags=re.MULTILINE):
        return code, False, ""
    wrapped = "namespace cAlgo.Robots\n{\n" + code + "\n}\n"
    return wrapped, True, "wrapped code in `namespace cAlgo.Robots { ... }`"


def _fix_unbalanced_braces(code: str, err: dict, _ctx) -> tuple[str, bool, str]:
    detail = err.get("detail", {})
    pair = detail.get("pair", "{}")
    delta = int(detail.get("delta", 0))
    if delta == 0:
        return code, False, ""
    open_c, close_c = pair[0], pair[1]
    _ = open_c  # unused (balance sign encodes direction)
    if delta > 0:
        # More opens than closes → append closes at end
        new = code.rstrip() + "\n" + (close_c * delta) + "\n"
        return new, True, f"appended {delta}x `{close_c}`"
    if delta < 0:
        # More closes → remove trailing occurrences of `close_c`
        # (conservative: only strip trailing ones to avoid damaging logic).
        needed = -delta
        stripped = code.rstrip()
        removed = 0
        while removed < needed and stripped.endswith(close_c):
            stripped = stripped[:-1].rstrip()
            removed += 1
        if removed > 0:
            return stripped + "\n", True, f"removed {removed}x trailing `{close_c}`"
    return code, False, ""


_MISSING_SEMI_LINE_RE = re.compile(r"(?P<line>[^\n;{}(),\[\]:]+)(?=\n|$)")


def _fix_missing_semicolon(code: str, err: dict, _ctx) -> tuple[str, bool, str]:
    """Add `;` to a specific flagged line."""
    snippet = (err.get("detail") or {}).get("line_text") or ""
    snippet = snippet.strip()
    if not snippet or ";" in snippet[-2:]:
        return code, False, ""
    # Append ";" to the first matching line that doesn't already end with `;`
    lines = code.split("\n")
    for i, ln in enumerate(lines):
        if snippet and snippet in ln and not ln.rstrip().endswith(";"):
            if not ln.rstrip().endswith(("{", "}", ",", "(", ":")):
                lines[i] = ln.rstrip() + ";"
                return "\n".join(lines), True, f"added `;` to line {i+1}"
    return code, False, ""


def _fix_missing_robot_class(code: str, _err, ctx: dict) -> tuple[str, bool, str]:
    """
    If there's no `class X : Robot`, wrap existing code in a minimal Robot
    shell. This is a last-resort rebuild — safest to regenerate from scratch.
    """
    # Rebuild from template entirely using the supplied ctx.
    from engines.code_generator import generate_code
    regen = generate_code({
        "pair": ctx.get("pair", "EURUSD"),
        "timeframe": ctx.get("timeframe", "H1"),
        "style": ctx.get("style", "trend_following"),
        "parameters": ctx.get("parameters") or {},
        "indicators": ctx.get("indicators") or {},
    })
    return regen["code"], True, "regenerated from template (missing Robot class)"


def _fix_missing_onstart(code: str, _err, _ctx) -> tuple[str, bool, str]:
    if "protected override void OnStart()" in code:
        return code, False, ""
    # Inject a minimal OnStart before the first closing brace of the class.
    m = re.search(r"public\s+class\s+\w+\s*:\s*Robot[^{]*\{", code)
    if not m:
        return code, False, ""
    insert_at = m.end()
    stub = "\n        protected override void OnStart() { }\n"
    return code[:insert_at] + stub + code[insert_at:], True, "injected empty OnStart()"


def _fix_missing_indicator_init(code: str, _err, ctx: dict) -> tuple[str, bool, str]:
    """
    If any `_ema*`, `_rsi`, etc. field is referenced but never initialised
    inside OnStart, inject the canonical init line.
    """
    inds = ctx.get("indicators") or {}
    init_block = _indicator_init(inds)
    if not init_block or init_block.strip().startswith("//"):
        return code, False, ""
    # Do nothing if all needed init lines are already present.
    missing = [ln.strip() for ln in init_block.splitlines()
               if ln.strip() and ln.strip() not in code]
    if not missing:
        return code, False, ""
    # Insert just after `protected override void OnStart() {`
    marker = "protected override void OnStart()"
    idx = code.find(marker)
    if idx < 0:
        return code, False, ""
    brace_idx = code.find("{", idx)
    if brace_idx < 0:
        return code, False, ""
    inject = "\n" + "\n".join(missing) + "\n"
    new = code[:brace_idx + 1] + inject + code[brace_idx + 1:]
    return new, True, f"injected {len(missing)} indicator init line(s)"


_INVALID_IDENT_RE = re.compile(r"\bpublic\s+(?:int|double|long|string|bool)\s+(\d\w*)")


def _fix_invalid_variable_naming(code: str, _err, _ctx) -> tuple[str, bool, str]:
    """Rename identifiers starting with a digit by prefixing `_`."""
    changed = False
    def _sub(m):
        nonlocal changed
        old = m.group(1)
        new = "_" + old
        changed = True
        return m.group(0).replace(old, new)
    new_code = _INVALID_IDENT_RE.sub(_sub, code)
    if changed:
        return new_code, True, "prefixed digit-leading identifiers with `_`"
    return code, False, ""


# ── Fix rule dispatch table ───────────────────────────────────────────

FIX_RULES = {
    "UNRESOLVED_PLACEHOLDER": _fix_unresolved_placeholder,
    "MISSING_USING":          _fix_missing_using,
    "MISSING_NAMESPACE":      _fix_missing_namespace,
    "MISSING_ROBOT_CLASS":    _fix_missing_robot_class,
    "MISSING_ONSTART":        _fix_missing_onstart,
    "UNBALANCED_BRACKETS":    _fix_unbalanced_braces,
    "MISSING_SEMICOLON":      _fix_missing_semicolon,
}


def apply_fixes(code: str, errors: list[dict], warnings: list[dict], ctx: dict) -> tuple[str, list[str]]:
    """
    Apply fix rules for each known error/warning code. Returns
    (new_code, notes). Also runs indicator-init + invalid-naming sweeps
    because those can surface as secondary effects.
    """
    notes: list[str] = []
    # Errors first (block compile), warnings second (missing semicolon).
    for diag in list(errors) + list(warnings):
        fn = FIX_RULES.get(diag.get("code"))
        if not fn:
            continue
        code, applied, note = fn(code, diag, ctx)
        if applied and note:
            notes.append(note)

    # Always-safe sweeps (idempotent)
    code, changed, note = _fix_missing_indicator_init(code, None, ctx)
    if changed:
        notes.append(note)
    code, changed, note = _fix_invalid_variable_naming(code, None, ctx)
    if changed:
        notes.append(note)

    return code, notes
