"""Regression tests for #1268: recall endpoints must not collapse
missing tenant_id into a literal ``"default"`` string.

Context
-------
The original bug: every recall endpoint read ``tenant_id`` from the
API key via ``api_key.get("tenant_id", "default")``. If the key
validator returned an object where ``tenant_id`` was missing or null
(misconfigured key, stale cache, new key type), the literal string
``"default"`` became the tenant identifier — collapsing all such
calls into a shared pseudo-tenant bucket. Because recall data is
regulatory evidence, this silent cross-contamination would be an
FDA audit risk and could be exploited by an attacker with a
malformed key.

The fix was applied in an earlier PR: every recall endpoint now uses
``tenant_id: uuid.UUID = Depends(get_current_tenant_id)``. That
dependency raises HTTP 401 when the auth context has no tenant_id
— fail-closed, no pseudo-bucket.

These regression tests LOCK IN the fix:

1. No file in ``services/`` uses the banned pattern
   ``api_key.get("tenant_id", "default")`` or any equivalent literal-
   string fallback for tenant_id.
2. Every recall endpoint signature uses ``get_current_tenant_id``.
3. The recall router does not reference the ``"default"`` literal
   as a tenant identifier anywhere.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parents[1] / "services"
RECALL_ROUTER = (
    SERVICES_ROOT / "graph" / "app" / "routers" / "fsma" / "recall.py"
)

# Make services importable for import-time check (below).
sys.path.insert(0, str(SERVICES_ROOT))


# ── 1. Banned pattern: api_key.get("tenant_id", "default") ────────────────


# The pattern we never want to see again. Spaces/quotes optional.
_BANNED_PATTERNS = [
    re.compile(
        r"""api_key\s*\.\s*get\s*\(\s*["']tenant_id["']\s*,\s*["']default["']\s*\)""",
    ),
    re.compile(
        r"""\.get\s*\(\s*["']tenant_id["']\s*,\s*["']default["']\s*\)""",
    ),
]


def _python_files_under(root: Path):
    for py in root.rglob("*.py"):
        # Skip tests — this test file itself contains the pattern as
        # a literal for the regex check.
        if "/tests/" in str(py):
            continue
        yield py


def test_no_api_key_tenant_id_default_fallback():
    """#1268: nobody reintroduces ``api_key.get("tenant_id", "default")``.

    This is the exact pattern that silently collapsed missing
    tenant_ids into a shared pseudo-bucket. A regression on any
    endpoint — not just recall — would reopen the same vuln."""
    offenders = []
    for py in _python_files_under(SERVICES_ROOT):
        text = py.read_text(errors="ignore")
        for pattern in _BANNED_PATTERNS:
            if pattern.search(text):
                offenders.append(str(py))
                break
    assert not offenders, (
        "#1268: found banned pattern api_key.get('tenant_id', 'default') "
        f"in: {offenders}. Use "
        "``Depends(get_current_tenant_id)`` instead — it raises 401 "
        "when tenant_id is missing rather than collapsing into a "
        "pseudo-bucket."
    )


# ── 2. Every recall endpoint uses get_current_tenant_id ───────────────────


def _endpoint_functions(module_path: Path):
    """Yield (name, FunctionDef) for every async function decorated with
    ``@router.<method>(...)``."""
    tree = ast.parse(module_path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            # Decorators are either ast.Call (``@router.get("/foo")``)
            # or ast.Attribute (``@router.get``).
            func = dec.func if isinstance(dec, ast.Call) else dec
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "router"
            ):
                yield node.name, node
                break


def test_every_recall_endpoint_uses_get_current_tenant_id():
    """#1268: every endpoint function in recall.py must accept
    ``tenant_id`` via ``Depends(get_current_tenant_id)``. Anything
    else (e.g. reading tenant_id from a query param, from
    ``api_key``, or defaulting to a literal) is the original bug."""
    assert RECALL_ROUTER.exists(), (
        f"Expected {RECALL_ROUTER} — file moved? Update this test."
    )

    endpoints = list(_endpoint_functions(RECALL_ROUTER))
    assert endpoints, (
        "No endpoint functions found in recall.py — has the file "
        "been restructured? Update this test if so."
    )

    offenders = []
    for name, fn in endpoints:
        # Look for a parameter named tenant_id with a default value
        # that's a Call to get_current_tenant_id via Depends.
        has_tenant_dep = False
        for arg in fn.args.args + fn.args.kwonlyargs:
            if arg.arg != "tenant_id":
                continue
            # Find the default value for this arg.
            default = _default_for_arg(fn, arg)
            if default is None:
                continue
            if _is_depends_get_current_tenant_id(default):
                has_tenant_dep = True
                break
        if not has_tenant_dep:
            offenders.append(name)

    assert not offenders, (
        f"#1268: the following recall endpoints do NOT use "
        f"Depends(get_current_tenant_id) for tenant_id: {offenders}. "
        f"Every endpoint must fail-closed on missing tenant_id."
    )


def _default_for_arg(fn, target_arg):
    """Match a FunctionDef argument to its default-value AST node."""
    # Positional args with defaults.
    n_positional = len(fn.args.args)
    n_positional_defaults = len(fn.args.defaults)
    for i, a in enumerate(fn.args.args):
        if a is target_arg:
            # Defaults fill from the right.
            default_index = i - (n_positional - n_positional_defaults)
            if default_index >= 0:
                return fn.args.defaults[default_index]
            return None
    # Keyword-only args.
    for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        if a is target_arg:
            return d
    return None


def _is_depends_get_current_tenant_id(node):
    """Return True for ``Depends(get_current_tenant_id)`` expressions."""
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != "Depends":
        return False
    if not node.args:
        return False
    arg0 = node.args[0]
    if isinstance(arg0, ast.Name) and arg0.id == "get_current_tenant_id":
        return True
    # Also accept ``shared.middleware.get_current_tenant_id``-style.
    if isinstance(arg0, ast.Attribute) and arg0.attr == "get_current_tenant_id":
        return True
    return False


# ── 3. No "default" string used as a tenant_id fallback in recall ────────


def test_recall_router_never_references_default_tenant_string():
    """Defensive: the literal string ``"default"`` MUST NOT appear in
    recall.py as a tenant value. Even a comment that looks like a
    refactor artifact could confuse a future reader."""
    text = RECALL_ROUTER.read_text()
    # We're looking for uses as a fallback in .get(..., "default") —
    # nothing legitimate in recall should need that.
    pattern = re.compile(r"""\.get\s*\([^)]*["']default["']""")
    assert not pattern.search(text), (
        "#1268: recall.py contains a .get(..., 'default') fallback "
        "that could mask missing tenant_id."
    )


# ── 4. The auth + middleware contract is intact ───────────────────────────


def test_get_current_tenant_id_raises_401_on_missing():
    """The dependency the fix relies on must fail-closed. If this
    ever changes, recall endpoints would silently accept anonymous
    requests."""
    from unittest.mock import MagicMock

    from shared.middleware.tenant_context import get_current_tenant_id
    from fastapi import HTTPException

    request = MagicMock()
    # Simulate no tenant_id in state.
    request.state = MagicMock(spec=[])  # no tenant_id attribute

    import asyncio
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            get_current_tenant_id(request)
        )
    assert exc_info.value.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
