"""Regression tests for #1230: identity_resolution service enforces
principal-tenant lock.

Context
-------
The canonical router bug #1106 showed that a router can forward an
``X-Tenant-ID`` header without cross-checking it against the
authenticated principal's tenant. That bug was fixed in the router,
but the identity_resolution service had no defense-in-depth: any
caller who reached the service with ``tenant_id="acme"`` could write
into Acme's data regardless of which principal they were authenticated
as.

This test file locks in the #1230 fix: the service accepts an optional
``principal_tenant_id`` at construction time and rejects any write
whose ``tenant_id`` argument doesn't match. Cross-tenant writes
require an explicit ``allow_cross_tenant=True`` opt-in (platform
admin tooling).

What we test
------------
1. Constructor:
   - ``principal_tenant_id`` is keyword-only (prevents positional-arg drift).
   - ``allow_cross_tenant`` is keyword-only.
   - Defaults preserve back-compat (background jobs, test harness).

2. Guard behaviour:
   - No principal bound → no-op (back-compat).
   - Matching tenant → passes.
   - Mismatched tenant → raises ``PermissionError``.
   - Empty tenant when bound → raises ``PermissionError``.
   - ``allow_cross_tenant=True`` → bypasses even mismatch.

3. Guard is wired into every write method (source-level regex).
   This catches a future method that adds DB side-effects without
   the guard.

4. Router plumbs principal through ``_get_service`` (source check).
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make shared/ importable
service_dir = Path(__file__).resolve().parents[2] / "services"
sys.path.insert(0, str(service_dir))

from shared.identity_resolution.service import (  # noqa: E402
    IdentityResolutionService,
)


# ── 1. Constructor: keyword-only safety invariants ────────────────────────


def test_principal_tenant_id_is_keyword_only():
    """#1230: ``principal_tenant_id`` must be keyword-only. Allowing
    it as positional invites drift — a new call site that positions
    something else into the slot would silently misbind the lock."""
    sig = inspect.signature(IdentityResolutionService.__init__)
    param = sig.parameters["principal_tenant_id"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "principal_tenant_id must be keyword-only (#1230)"
    )


def test_allow_cross_tenant_is_keyword_only():
    """#1230: ``allow_cross_tenant`` is the escape hatch; it must be
    keyword-only to prevent accidental disabling of the lock."""
    sig = inspect.signature(IdentityResolutionService.__init__)
    param = sig.parameters["allow_cross_tenant"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is False


def test_constructor_defaults_preserve_backcompat():
    """Unbound construction (no principal) is the safe fallback for
    background jobs and test harnesses. It must work."""
    svc = IdentityResolutionService(MagicMock())
    # Guard becomes a no-op when _principal_tenant_id is None.
    svc._verify_tenant_access("any-tenant")
    svc._verify_tenant_access("")
    svc._verify_tenant_access("some-other-tenant")


# ── 2. Guard behaviour ─────────────────────────────────────────────────────


def test_guard_passes_on_matching_tenant():
    """The happy path: principal bound, caller supplied the same tenant."""
    svc = IdentityResolutionService(
        MagicMock(), principal_tenant_id="tenant-acme"
    )
    # No exception.
    svc._verify_tenant_access("tenant-acme")


def test_guard_rejects_mismatched_tenant():
    """The whole point of the lock: a principal bound to one tenant
    must not be able to reach into another."""
    svc = IdentityResolutionService(
        MagicMock(), principal_tenant_id="tenant-acme"
    )
    with pytest.raises(PermissionError, match="does not match"):
        svc._verify_tenant_access("tenant-globex")


def test_guard_rejects_empty_tenant_when_bound():
    """An empty string tenant slipping through the router is a bug,
    not a valid state."""
    svc = IdentityResolutionService(
        MagicMock(), principal_tenant_id="tenant-acme"
    )
    with pytest.raises(PermissionError):
        svc._verify_tenant_access("")


def test_allow_cross_tenant_bypasses_guard():
    """Platform admin tooling explicitly opts out of the lock."""
    svc = IdentityResolutionService(
        MagicMock(),
        principal_tenant_id="tenant-acme",
        allow_cross_tenant=True,
    )
    # No exception even though the tenants differ.
    svc._verify_tenant_access("tenant-globex")
    svc._verify_tenant_access("")


def test_guard_error_mentions_issue_reference():
    """Regression: the error message should point a debugger at #1230
    so the constraint is self-explaining."""
    svc = IdentityResolutionService(
        MagicMock(), principal_tenant_id="tenant-acme"
    )
    with pytest.raises(PermissionError) as exc_info:
        svc._verify_tenant_access("tenant-globex")
    assert "#1230" in str(exc_info.value)


# ── 3. Guard is wired into every write method (source-level) ──────────────


WRITE_METHODS = [
    "register_entity",
    "add_alias",
    "merge_entities",
    "split_entity",
    "queue_for_review",
    "resolve_review",
    "auto_register_from_event",
]


def _service_source() -> str:
    return inspect.getsource(IdentityResolutionService)


@pytest.mark.parametrize("method_name", WRITE_METHODS)
def test_write_method_calls_verify_tenant_access(method_name):
    """Source-level check: every write method must call
    ``self._verify_tenant_access(tenant_id)``.

    Rationale: an AST walk would be more thorough, but a regex on the
    method source is enough to catch the concrete failure mode — a
    developer adds a new method or edits an existing one and drops the
    guard. Runtime integration tests can't reliably reach every
    method's DB side-effect without a Postgres fixture.
    """
    method = getattr(IdentityResolutionService, method_name)
    src = inspect.getsource(method)
    # Match the exact guard call with the tenant_id param.
    pattern = r"self\._verify_tenant_access\(\s*tenant_id\s*\)"
    assert re.search(pattern, src), (
        f"#1230: {method_name} must call "
        f"self._verify_tenant_access(tenant_id) before any side effects."
    )


def test_read_methods_do_not_require_guard():
    """Sanity: read-only methods — the kind that filter by tenant_id in
    the SQL WHERE clause — don't need the guard because they can't
    write. We don't want this test to mandate a guard on reads; it just
    documents that the WRITE_METHODS list above is the authoritative
    surface.
    """
    read_methods = {
        "find_entity_by_alias",
        "find_potential_matches",
        "get_entity",
        "list_pending_reviews",
    }
    for name in read_methods:
        assert hasattr(IdentityResolutionService, name), (
            f"Read method {name} missing — update this test if renamed."
        )


# ── 4. Router plumbs principal through _get_service (source check) ────────


def _router_source() -> str:
    p = (
        Path(__file__).resolve().parents[2]
        / "services" / "ingestion" / "app" / "identity_router.py"
    )
    return p.read_text()


def test_router_get_service_accepts_principal():
    """#1230: ``_get_service`` must thread the principal through so
    the service can be constructed with ``principal_tenant_id``."""
    src = _router_source()
    # Signature change: _get_service(db_session, principal=...)
    assert re.search(
        r"def\s+_get_service\s*\(\s*\n?\s*db_session,\s*\n?\s*principal",
        src,
    ), (
        "#1230: _get_service must accept principal as its second arg."
    )


def test_router_passes_principal_tenant_id_to_service():
    """#1230: every ``IdentityResolutionService(...)`` construction
    in the router must bind the principal's tenant."""
    src = _router_source()
    assert "principal_tenant_id=principal_tenant_id" in src, (
        "#1230: _get_service must pass principal_tenant_id to "
        "IdentityResolutionService so writes are tenant-locked."
    )


def test_all_router_callsites_pass_principal():
    """#1230: every _get_service(...) call in the router must include
    the principal. Catches a new endpoint that forgets to thread it."""
    src = _router_source()
    # Find every _get_service(...) invocation in the router (not the
    # definition). Allow optional kwargs after principal but require
    # principal as the second positional arg.
    callsites = re.findall(
        r"_get_service\((?!\s*\n?\s*db_session,\s*principal:)(.*?)\)",
        src,
    )
    # Exclude the definition (which matches "db_session,\n    principal:")
    # but the regex above already skips it. Defense-in-depth:
    callsites = [c for c in callsites if "IngestionPrincipal" not in c]
    assert callsites, "Expected to find call sites to _get_service"
    for args in callsites:
        assert "principal" in args, (
            f"#1230: _get_service call is missing principal arg: {args!r}"
        )


# ── 5. Sanity: the fix doesn't break ordinary construction ────────────────


def test_default_construction_is_unbound():
    """Service constructed without kwargs is unbound — tests and
    background jobs keep working."""
    svc = IdentityResolutionService(MagicMock())
    assert svc._principal_tenant_id is None
    assert svc._allow_cross_tenant is False


def test_bound_construction_stores_principal():
    svc = IdentityResolutionService(
        MagicMock(), principal_tenant_id="tenant-acme"
    )
    assert svc._principal_tenant_id == "tenant-acme"
    assert svc._allow_cross_tenant is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
