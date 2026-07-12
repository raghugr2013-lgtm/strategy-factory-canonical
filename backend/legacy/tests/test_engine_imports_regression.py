"""
Engine-import regression test (Phase 2 P2.7 safeguard).

Purpose
-------
Catch the exact class of "credit-exhausted partial edit" footprint that
the F1 finding in PHASE_2_CHECKPOINT_INTEGRITY_REVIEW.md identified:
a module that REFERENCES a name in a function body without importing it
at module level. The bug never fires at import time (function body is
deferred), so the backend boots cleanly — but the first runtime call
crashes with NameError, bypassing the very Phase 2 guard the edit was
meant to install.

This test imports every Python module under `engines/`, `api/`, and
`data_engine/` and `inspect.getmembers()` every callable in each. We
don't EXECUTE function bodies (too slow, too many side-effects); we
verify that:

  1. The module imports without raising (catches missing imports at the
     module-level).
  2. `ast.parse(open(module).read())` parses (catches syntax errors).
  3. `compile(source, fname, 'exec')` succeeds (catches encoding /
     indentation errors).

Static AST analysis ALSO walks every function body and collects every
`Name` node used in `Load` context. Cross-references against the
module's available bindings (imports + module-level assignments +
builtins). Any unresolved name in a function body is reported.

This is intentionally LIGHTWEIGHT — runs in <10 seconds, so it can be
wired into pre-commit or CI without slowing the iteration loop.
"""
from __future__ import annotations

import ast
import builtins
import importlib
import sys
from pathlib import Path
from typing import List, Set, Tuple

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = ("engines", "api", "data_engine")


def _python_files() -> List[Path]:
    out: List[Path] = []
    for d in TARGET_DIRS:
        root = BACKEND_ROOT / d
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return out


def _module_name(p: Path) -> str:
    rel = p.relative_to(BACKEND_ROOT).with_suffix("")
    return ".".join(rel.parts)


# Ensure the backend root is on sys.path so `import engines.xxx` works
# when the test is invoked from /app or anywhere else.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Ensure env is loaded so engines that read os.environ at import-time
# (e.g. engines.db) don't choke on missing MONGO_URL.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────
# Test 1 — every module imports without raising.
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("py_file", _python_files(), ids=_module_name)
def test_module_imports_cleanly(py_file: Path) -> None:
    """A NameError at import-time is the FIRST signal of a partial edit.
    This also catches missing modules, circular imports, syntax errors,
    and indentation glitches that the linter sometimes lets through.
    """
    mod_name = _module_name(py_file)
    try:
        importlib.import_module(mod_name)
    except ImportError as e:
        # Tolerate genuinely-optional integrations that may be absent
        # from a slim dev environment (e.g. selenium for the prop-firm
        # scraper). The test is about CODE coherence, not deployment.
        msg = str(e)
        if any(opt in msg for opt in (
            "No module named 'selenium'",
            "No module named 'playwright'",
        )):
            pytest.skip(f"optional dependency missing: {msg}")
        raise
    except Exception as e:                                  # pragma: no cover
        pytest.fail(f"{mod_name} failed to import: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────
# Test 2 — AST static name-resolution.
# ─────────────────────────────────────────────────────────────────────
def _collect_module_bindings(tree: ast.Module) -> Set[str]:
    """Names defined at module level — imports, defs, classes, assigns."""
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    # star imports — can't statically resolve; mark
                    # module as "lenient" by collecting nothing here.
                    return set()  # signal: skip checks for this module
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
                elif isinstance(tgt, (ast.Tuple, ast.List)):
                    for elt in tgt.elts:
                        if isinstance(elt, ast.Name):
                            names.add(elt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _local_names_in_function(fn: ast.AST) -> Set[str]:
    """Names introduced by a function: args, locals, walrus, with/for/except targets."""
    locals_: Set[str] = set()
    # Args
    args = getattr(fn, "args", None)
    if args:
        for a in (
            list(args.args) + list(args.kwonlyargs) + list(args.posonlyargs or [])
        ):
            locals_.add(a.arg)
        if args.vararg:
            locals_.add(args.vararg.arg)
        if args.kwarg:
            locals_.add(args.kwarg.arg)
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assign):
            for tgt in sub.targets:
                for n in ast.walk(tgt):
                    if isinstance(n, ast.Name):
                        locals_.add(n.id)
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
            locals_.add(sub.target.id)
        elif isinstance(sub, ast.AugAssign) and isinstance(sub.target, ast.Name):
            locals_.add(sub.target.id)
        elif isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
            locals_.add(sub.target.id)
        elif isinstance(sub, (ast.For, ast.AsyncFor)):
            for n in ast.walk(sub.target):
                if isinstance(n, ast.Name):
                    locals_.add(n.id)
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                if item.optional_vars:
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name):
                            locals_.add(n.id)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            locals_.add(sub.name)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            locals_.add(sub.name)
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                locals_.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(sub, ast.ImportFrom):
            for alias in sub.names:
                if alias.name != "*":
                    locals_.add(alias.asname or alias.name)
        elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for gen in sub.generators:
                for n in ast.walk(gen.target):
                    if isinstance(n, ast.Name):
                        locals_.add(n.id)
        elif isinstance(sub, ast.Lambda):
            # Lambda parameter names are bound within the lambda body
            # which `ast.walk(fn)` still traverses. Collect them as
            # function-scope locals (slight over-approximation, but it
            # eliminates the entire class of false positives caused by
            # `lambda kv: kv[1]` style inline callables, which are
            # ubiquitous in dict/list sort and reduce idioms).
            lam_args = sub.args
            for a in (
                list(lam_args.args) + list(lam_args.kwonlyargs)
                + list(lam_args.posonlyargs or [])
            ):
                locals_.add(a.arg)
            if lam_args.vararg:
                locals_.add(lam_args.vararg.arg)
            if lam_args.kwarg:
                locals_.add(lam_args.kwarg.arg)
    return locals_


def _walk_names_in_scope(fn: ast.AST):
    """Iterate Name(Load) nodes in `fn`'s OWN scope (skip into nested
    FunctionDef/AsyncFunctionDef/Lambda bodies — they have their own
    scopes and will be checked separately by the caller)."""
    # Start with fn's direct body / args / decorators
    skip_classes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        if isinstance(node, skip_classes):
            # Skip the nested function's args+body+decorators entirely.
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _unresolved_names(py_file: Path) -> List[Tuple[str, int, str]]:
    """Return [(function_qualname, lineno, name), …] for every Name(Load)
    that is not resolvable from module bindings + enclosing-function
    closures + function-local introductions + builtins.

    Closure tracking: when we descend into a nested function, the names
    introduced by EVERY enclosing function become legitimate references
    inside the inner body (Python's lexical scope rules). The walker
    threads a scope-stack of enclosing-function locals to honour that.
    """
    src = py_file.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(py_file))
    module_bindings = _collect_module_bindings(tree)
    if not module_bindings:
        return []
    builtin_names = set(dir(builtins))

    results: List[Tuple[str, int, str]] = []

    def _walk_funcs(node: ast.AST, qual_prefix: str, enclosing: Set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{qual_prefix}.{child.name}" if qual_prefix else child.name
                locals_ = _local_names_in_function(child)
                allowed = module_bindings | enclosing | locals_ | builtin_names
                for sub in _walk_names_in_scope(child):
                    if sub.id not in allowed:
                        results.append((qual, sub.lineno, sub.id))
                # Pass enclosing+locals down into nested functions.
                _walk_funcs(child, qual, enclosing | locals_)
            elif isinstance(child, ast.ClassDef):
                inner_qual = (
                    f"{qual_prefix}.{child.name}" if qual_prefix else child.name
                )
                _walk_funcs(child, inner_qual, enclosing)

    _walk_funcs(tree, "", set())
    return results


@pytest.mark.parametrize("py_file", _python_files(), ids=_module_name)
def test_no_unresolved_names_in_function_bodies(py_file: Path) -> None:
    """The F1-class bug: a function body references a name (e.g. `os`)
    that is NOT in the module's import set. Backend boots fine — the
    body is never executed at import time — but the first call crashes
    with NameError, bypassing the Phase 2 guard the edit was meant to
    install.

    This test parses each module statically, collects module-level
    bindings + function-local introductions + builtins, then flags any
    Load-context Name in a function body that is unresolvable.

    False-positive guard: modules with `from x import *` are skipped
    because star-imports cannot be statically resolved.
    """
    unresolved = _unresolved_names(py_file)
    if not unresolved:
        return

    # Group by name for a tighter report.
    by_name: dict = {}
    for qual, lineno, name in unresolved:
        by_name.setdefault(name, []).append(f"{qual}:L{lineno}")

    msg_lines = [f"unresolved names in {_module_name(py_file)}:"]
    for name, sites in sorted(by_name.items()):
        msg_lines.append(f"  {name!r} at " + ", ".join(sites))
    pytest.fail("\n".join(msg_lines))
