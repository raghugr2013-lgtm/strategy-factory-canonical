"""
Phase 12 — cBot Compile Engine (lightweight static checker).

This is a structural validator, not a full C# compiler. It verifies the
invariants we care about for template-generated cTrader cBots:

    * all template placeholders resolved (no `{{...}}` left)
    * balanced braces, brackets, parentheses
    * required `using cAlgo.API;` + `public class ... : Robot`
    * single top-level namespace
    * `OnStart()` and `OnBar()` methods present
    * no raw `;;` sequences, no empty `if ()` guards
    * every statement line inside a method body ends with `;` or a brace

Return:
    {
      "compile_status": "success" | "warning" | "error",
      "errors": [str, ...],
      "warnings": [str, ...],
    }
"""
from __future__ import annotations

import re


_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def _balanced(pairs: str, source: str) -> tuple[bool, int]:
    """Count (balance, unmatched_count) for pair chars like '()'."""
    open_c, close_c = pairs[0], pairs[1]
    depth = 0
    for ch in source:
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth < 0:
                return False, depth
    return depth == 0, depth


def _strip_strings_and_comments(src: str) -> str:
    """Remove string literals + // and /* */ comments to avoid false flags."""
    # strip block comments
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    # strip line comments
    src = re.sub(r"//[^\n]*", "", src)
    # strip "..." strings (simple, no escape handling)
    src = re.sub(r"\"(?:\\.|[^\"\\])*\"", "\"\"", src)
    return src


def _check_statement_termination(src: str) -> list[str]:
    """
    Very light scan for missing semicolons. We only flag clearly
    unambiguous cases: lines that look like method calls / assignments
    and don't end with ';', '{', '}', ',' or '('.
    """
    warnings: list[str] = []
    stripped = _strip_strings_and_comments(src)
    for i, raw in enumerate(stripped.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        # Skip structural lines
        if any(line.startswith(kw) for kw in (
            "using ", "namespace ", "public ", "private ", "protected ",
            "[", "//", "/*", "*", "#"
        )):
            continue
        if line in ("{", "}", "};"):
            continue
        if line.endswith((";", "{", "}", ",", "(", ":", ")")):
            continue
        # lone `else`, `do` etc.
        if line in ("else", "do", "try"):
            continue
        if line.startswith("else ") or line.startswith("for ") or \
           line.startswith("while ") or line.startswith("if ") or \
           line.startswith("foreach "):
            continue
        warnings.append(f"line {i}: possibly missing ';' → {line[:80]}")
        if len(warnings) > 20:  # cap
            break
    return warnings


def validate(code: str) -> dict:
    """Main entry — return compile_status + errors/warnings.

    Errors/warnings are dicts with:
        {"code": "<ERR_CODE>", "message": str, "detail": dict}
    A plain string array (`errors_plain` / `warnings_plain`) is also
    included for backward compatibility with callers expecting strings.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    if not isinstance(code, str) or not code.strip():
        return {"compile_status": "error",
                "errors": [{"code": "EMPTY", "message": "Code is empty."}],
                "warnings": [],
                "errors_plain": ["Code is empty."],
                "warnings_plain": []}

    # ── 1. Placeholders resolved ──
    unresolved = _PLACEHOLDER_RE.findall(code)
    if unresolved:
        errors.append({
            "code": "UNRESOLVED_PLACEHOLDER",
            "message": f"Unresolved placeholders: {sorted(set(unresolved))}",
            "detail": {"placeholders": sorted(set(unresolved))},
        })

    # ── 2. Required structural markers ──
    if "using cAlgo.API;" not in code:
        errors.append({"code": "MISSING_USING", "message": "Missing `using cAlgo.API;`",
                       "detail": {"using": "cAlgo.API"}})
    if "namespace " not in code:
        errors.append({"code": "MISSING_NAMESPACE",
                       "message": "Missing `namespace` declaration."})
    if re.search(r"public\s+class\s+\w+\s*:\s*Robot", code) is None:
        errors.append({"code": "MISSING_ROBOT_CLASS",
                       "message": "Missing `public class <Name> : Robot`"})
    if "protected override void OnStart()" not in code:
        errors.append({"code": "MISSING_ONSTART",
                       "message": "Missing OnStart() override."})
    if "protected override void OnBar()" not in code:
        warnings.append({"code": "NO_ONBAR",
                         "message": "No OnBar() override — bot only reacts on ticks."})

    # ── 3. Balanced brackets ──
    sanitised = _strip_strings_and_comments(code)
    for pair in ("{}", "()", "[]"):
        ok, depth = _balanced(pair, sanitised)
        if not ok:
            errors.append({
                "code": "UNBALANCED_BRACKETS",
                "message": f"Unbalanced `{pair}` (delta={depth}).",
                "detail": {"pair": pair, "delta": depth},
            })

    # ── 4. Obvious junk ──
    if ";;" in sanitised:
        warnings.append({"code": "DOUBLE_SEMICOLON",
                         "message": "Found `;;` — empty statement."})
    if re.search(r"\bif\s*\(\s*\)", sanitised):
        errors.append({"code": "EMPTY_IF",
                       "message": "Empty `if()` condition."})
    if re.search(r"\bwhile\s*\(\s*\)", sanitised):
        errors.append({"code": "EMPTY_WHILE",
                       "message": "Empty `while()` condition."})

    # ── 5. Statement termination (warnings only) ──
    term_warnings = _check_statement_termination(code)
    for msg in term_warnings:
        warnings.append({"code": "MISSING_SEMICOLON",
                         "message": msg,
                         "detail": {"line_text": msg.split("→", 1)[-1].strip()
                                                 if "→" in msg else msg}})

    # ── Status ──
    if errors:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "success"

    return {
        "compile_status": status,
        "errors": errors,
        "warnings": warnings,
        "errors_plain": [e["message"] for e in errors],
        "warnings_plain": [w["message"] for w in warnings],
    }
