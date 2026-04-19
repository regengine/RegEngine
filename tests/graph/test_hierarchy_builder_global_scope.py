"""Regression tests for #1304: ``build_jurisdiction_hierarchy`` global
taxonomy invariant.

Context
-------
Jurisdictions are global regulatory taxonomy ("US", "US-CA", "EU") —
a single shared set, NOT tenant-scoped. Because ``Neo4jClient`` forces
all tenants into ``DB_GLOBAL`` (a separate critical issue tracked at
#1315), these MERGEs land in the same graph as tenant data. If a
future caller misuses ``build_jurisdiction_hierarchy`` from a
tenant-scoped path, it would silently pollute the global namespace
and potentially accept attacker-controlled jurisdiction codes.

This test file locks in the #1304 hardening:

1. Codes are validated against a whitelist BEFORE any MERGE runs.
2. Invalid codes abort the whole build (fail-closed).
3. Every created node gets the ``:GlobalJurisdiction`` label and
   ``scope='global'`` property.
4. No FastAPI router module imports the builder (static grep check).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).resolve().parents[2] / "services" / "graph"
sys.path.insert(0, str(service_dir))

from app.hierarchy_builder import (  # noqa: E402
    InvalidJurisdictionCodeError,
    _JURISDICTION_CODE_RE,
    _MAX_JURISDICTION_CODE_LENGTH,
    _validate_jurisdiction_code,
    build_jurisdiction_hierarchy,
    parent_code_for,
)


# ── 1. Validator whitelist ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code",
    ["US", "EU", "US-CA", "US-CA-SF", "EU-FR-75", "IN-MH", "CN-11"],
)
def test_validator_accepts_well_formed_codes(code):
    """Canonical ISO-ish codes pass the whitelist."""
    _validate_jurisdiction_code(code)


@pytest.mark.parametrize(
    "code",
    [
        "",                    # empty
        "us-ca",               # lowercase
        "US--CA",              # empty segment
        "US/CA",               # disallowed separator
        "US CA",               # whitespace
        "US;DROP TABLE",       # injection-shaped input
        "US'OR'1'='1",         # injection-shaped input
        "US<script>",          # XSS-shaped input
        "A" * 64,              # oversize single segment
        "US-" + ("A" * 32),    # oversize with separator
    ],
)
def test_validator_rejects_malformed_codes(code):
    """Anything outside the whitelist raises."""
    with pytest.raises(InvalidJurisdictionCodeError):
        _validate_jurisdiction_code(code)


def test_validator_rejects_non_strings():
    """A programming bug that passes e.g. a list must be caught."""
    with pytest.raises(InvalidJurisdictionCodeError):
        _validate_jurisdiction_code(["US"])
    with pytest.raises(InvalidJurisdictionCodeError):
        _validate_jurisdiction_code(None)
    with pytest.raises(InvalidJurisdictionCodeError):
        _validate_jurisdiction_code(12345)


def test_validator_respects_max_length():
    """Codes exceeding the max length are rejected even if each segment
    matches individually — guards against pathological inputs that
    could bloat Neo4j's string index."""
    # Max single-segment segments can produce e.g. "AAAAAA-BBBBBB-CCCCCC-DDDDDD-EEEEEE"
    # which is 41 chars, already over the 32-char ceiling.
    too_long = "-".join(["ABCDEF"] * 6)
    assert len(too_long) > _MAX_JURISDICTION_CODE_LENGTH
    with pytest.raises(InvalidJurisdictionCodeError):
        _validate_jurisdiction_code(too_long)


def test_regex_matches_intended_pattern():
    """The regex is part of the public contract; lock it in."""
    assert _JURISDICTION_CODE_RE.fullmatch("US")
    assert _JURISDICTION_CODE_RE.fullmatch("US-CA")
    assert _JURISDICTION_CODE_RE.fullmatch("US-CA-SF")
    assert not _JURISDICTION_CODE_RE.fullmatch("us")
    assert not _JURISDICTION_CODE_RE.fullmatch("US-")
    assert not _JURISDICTION_CODE_RE.fullmatch("-US")


# ── 2. parent_code_for helper ──────────────────────────────────────────────


def test_parent_code_for_simple():
    assert parent_code_for("US-CA") == "US"
    assert parent_code_for("US-CA-SF") == "US-CA"
    assert parent_code_for("US") is None
    assert parent_code_for("") is None


# ── 3. Builder: fail-closed on invalid codes ──────────────────────────────


def test_builder_rejects_invalid_code_before_any_merge():
    """A single bad code in the input set aborts the WHOLE build —
    no partial MERGEs. This matters because a half-built hierarchy
    is harder to debug than an error."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = None

    with pytest.raises(InvalidJurisdictionCodeError):
        build_jurisdiction_hierarchy(driver, ["US", "US-CA", "bad-code"])

    # No MERGE should have run — validation happened first.
    assert session.run.call_count == 0


def test_builder_rejects_invalid_parent():
    """The parent code is derived from the child; if the derivation
    produces something invalid, reject.

    In practice a valid child produces a valid parent, but the explicit
    re-validation guards against edge cases in future parent derivation
    logic."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    # This is well-formed, so it should pass — sanity check.
    build_jurisdiction_hierarchy(driver, ["US-CA"])


# ── 4. Builder: node labelling and scope property ─────────────────────────


def test_builder_sets_global_jurisdiction_label():
    """Every node MERGE must set the :GlobalJurisdiction label and
    scope='global' property.

    We verify by inspecting the Cypher string passed to session.run."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    build_jurisdiction_hierarchy(driver, ["US", "US-CA"])

    # Collect all Cypher strings issued.
    cypher_calls = [call.args[0] for call in session.run.call_args_list]
    assert cypher_calls, "Expected MERGE calls"
    for cypher in cypher_calls:
        assert ":GlobalJurisdiction" in cypher, (
            f"#1304: every MERGE must label the node :GlobalJurisdiction. "
            f"Missing in: {cypher}"
        )
        assert "scope = 'global'" in cypher, (
            f"#1304: every MERGE must set scope='global'. "
            f"Missing in: {cypher}"
        )


def test_builder_emits_both_node_and_edge_for_parent_child():
    """US-CA should produce: node MERGE for US-CA, plus a parent+edge
    MERGE block."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    build_jurisdiction_hierarchy(driver, ["US-CA"])

    # One call for the child node MERGE, one for the parent+edge block.
    assert session.run.call_count == 2
    cypher_calls = [call.args[0] for call in session.run.call_args_list]
    assert any("CONTAINS" in c for c in cypher_calls)


def test_builder_skips_empty_codes():
    """Empty strings in the iterable are dropped, not rejected.
    This matches the original behaviour for back-compat."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    # ``""`` is dropped; ``"US"`` goes through.
    build_jurisdiction_hierarchy(driver, ["", "US"])

    # Exactly one call: the US node MERGE. No parent.
    assert session.run.call_count == 1


# ── 5. No request-handler imports the builder (static check) ──────────────


def test_no_fastapi_router_imports_builder():
    """#1304: the builder is for admin scripts ONLY. A FastAPI router
    that imports it would let a tenant mutate global taxonomy.

    This test greps the ``services/graph/app/routers`` tree (and any
    other routers directory we have) for imports of
    ``build_jurisdiction_hierarchy``. If any router imports it, this
    test fails — forcing the author to either justify the exception
    or route through an admin-scoped path.
    """
    root = Path(__file__).resolve().parents[2] / "services"
    offenders = []
    for py in root.rglob("*.py"):
        # Skip the builder itself, its admin script, and tests.
        if "hierarchy_builder.py" in py.name:
            continue
        if "scripts/build_hierarchy.py" in str(py):
            continue
        if "/tests/" in str(py):
            continue
        text = py.read_text(errors="ignore")
        if "build_jurisdiction_hierarchy" in text:
            # Check whether this file is a router / request handler.
            if "APIRouter" in text or "@router." in text or "FastAPI" in text:
                offenders.append(str(py))
    assert not offenders, (
        f"#1304: build_jurisdiction_hierarchy is imported by a FastAPI "
        f"router: {offenders}. This function writes to global taxonomy "
        f"and must never be reachable from a request handler."
    )


# ── 6. Module docstring documents the invariant ──────────────────────────


def test_module_docstring_documents_invariant():
    """Part of the fix is documentation discoverability: anyone who
    opens the module should see the invariant before they touch it."""
    import app.hierarchy_builder as mod
    doc = mod.__doc__ or ""
    # Look for key phrases that capture the invariant.
    assert "GLOBAL" in doc.upper(), doc
    assert "#1304" in doc
    # Must warn against request-handler use.
    assert re.search(r"request[- ]handler|FastAPI|router", doc, re.I), doc


def test_function_docstring_documents_invariant():
    """The same warning must be visible in the function's own
    docstring so ``help(build_jurisdiction_hierarchy)`` shows it."""
    doc = build_jurisdiction_hierarchy.__doc__ or ""
    assert "GLOBAL" in doc.upper()
    assert "#1304" in doc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
