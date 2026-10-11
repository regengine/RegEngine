"""QA deep-pass: route-security manifest pure helpers and policy error paths.

Covers server/route_security_manifest.py probe-path rendering, probe-method
preference, and operation enumeration, plus server/route_security_policy.py
key formatting, public storage boundaries, and tenant API-key policy
resolution. No app import, no network, fully deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.route_security_manifest import (
    _choose_probe,
    _concrete_probe_path,
    _route_operations,
)
from server.route_security_policy import (
    RouteManifestError,
    _public_storage_boundary,
    _tenant_api_key_policy,
    operation_id,
    operation_key,
)


def _route(methods, path):
    return SimpleNamespace(methods=set(methods), path=path)


# --- _route_operations -----------------------------------------------------------


def test_route_operations_skips_head_and_options():
    assert list(_route_operations(_route({"GET", "HEAD", "OPTIONS"}, "/x"))) == [("GET", "/x")]


def test_route_operations_sorts_methods():
    assert list(_route_operations(_route({"POST", "GET"}, "/x"))) == [
        ("GET", "/x"),
        ("POST", "/x"),
    ]


# --- _concrete_probe_path ----------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("/v1/things/{thing_id}", "/v1/things/00000000-0000-4000-8000-000000000000"),
        ("/v1/things/{id}", "/v1/things/00000000-0000-4000-8000-000000000000"),
        ("/v1/items/{item_index}", "/v1/items/1"),
        ("/v1/items/{n:int}", "/v1/items/1"),
        ("/v1/items/{ratio:float}", "/v1/items/1.0"),
        ("/v1/jobs/{job_id:uuid}", "/v1/jobs/00000000-0000-4000-8000-000000000000"),
        ("/v1/files/{rest:path}", "/v1/files/disabled-probe/segment"),
        ("/v1/things/{slug}", "/v1/things/disabled-probe"),
        ("/health", "/health"),
    ],
)
def test_concrete_probe_path_renders_safe_concrete_values(template, expected):
    assert _concrete_probe_path(template) == expected


# --- _choose_probe -------------------------------------------------------------------


def test_choose_probe_prefers_get_over_mutations():
    route = _route({"GET"}, "/v1/things/{thing_id}")
    assert _choose_probe([("DELETE", route), ("GET", route)]) == (
        "GET",
        "/v1/things/00000000-0000-4000-8000-000000000000",
    )


# --- operation keys ---------------------------------------------------------------------


def test_operation_key_uppercases_method():
    assert operation_key("billing", "post", "/x") == ("billing", "POST", "/x")


def test_operation_id_format():
    assert operation_id("billing", "post", "/x") == "billing:POST:/x"


# --- public storage boundaries -------------------------------------------------------------


def test_portal_public_boundary_uses_opaque_capability():
    assert _public_storage_boundary("portal", "/api/v1/portal/abc") == ("postgres-rls:opaque-portal-capability")


def test_proof_public_boundary_uses_public_store():
    assert _public_storage_boundary("proof_verify", "/api/v1/proof/verify") == ("public-proof-store:non-secret")


def test_admin_public_flow_boundary():
    assert _public_storage_boundary("admin", "/auth/challenges") == ("admin-postgres:identity-bound-public-flow")


def test_generic_public_boundary_holds_no_tenant_secret():
    assert _public_storage_boundary("health", "/health") == ("public-static-or-health:no-tenant-secret")


# --- tenant API-key policy resolution ----------------------------------------------------------


def test_exact_operation_policy_overrides_owner_policy():
    policy = _tenant_api_key_policy(owner="status", method="GET", path="/v1/ingest/status/{job_id}")
    assert policy.storage_boundary == "redis:tenant-owner-key"
    assert policy.test_adapter == "tenant_api_key_redis_job_owner"


def test_owner_policy_applies_when_no_exact_override():
    policy = _tenant_api_key_policy(owner="csv", method="GET", path="/api/v1/csv/rows")
    assert policy.storage_boundary == "postgres-rls:credential-bound-tenant"


def test_unknown_owner_without_policy_fails_closed():
    with pytest.raises(RouteManifestError, match="No explicit tenant API-key"):
        _tenant_api_key_policy(owner="no_such_owner", method="GET", path="/x")
