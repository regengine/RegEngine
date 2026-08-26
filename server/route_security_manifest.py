"""Generate, validate, and probe the production route security manifest."""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from shared.route_introspection import EffectiveRoute, iter_effective_routes
from starlette.routing import Match, compile_path

from server.route_ownership import excluded_owned_routes, route_owner
from server.route_security_policy import (
    ALL_ROUTE_OWNERS,
    ALWAYS_MOUNTED_OWNERS,
    OMITTED_ROUTER_OWNERS,
    PRODUCTION_OWNERS,
    PUBLIC_OPERATIONS,
    REQUIRED_EXACT_TENANT_API_KEY_POLICIES,
    STRIPE_WEBHOOK_OPERATIONS,
    TENANT_API_KEY_OPERATION_POLICIES,
    TENANT_API_KEY_OWNER_POLICIES,
    Classification,
    RouteManifestError,
    classify_operation,
    operation_id,
    operation_key,
)
from server.router_policy import PRODUCTION_ENABLED_ROUTERS, VALID_ROUTER_NAMES

_FRAMEWORK_DOC_ROUTE_SIGNATURES = frozenset(
    {
        ("starlette.routing", "Route", "/docs", "swagger_ui_html", ("GET", "HEAD")),
        (
            "starlette.routing",
            "Route",
            "/docs/oauth2-redirect",
            "swagger_ui_redirect",
            ("GET", "HEAD"),
        ),
        ("starlette.routing", "Route", "/openapi.json", "openapi", ("GET", "HEAD")),
        ("starlette.routing", "Route", "/redoc", "redoc_html", ("GET", "HEAD")),
    }
)
_MINIMUM_INVENTORY_ROUTE_COUNT = 100


@dataclass(frozen=True)
class OperationManifestEntry:
    operation: str
    owner: str
    method: str
    path: str
    classification: Classification
    authentication: str
    required_permissions: tuple[str, ...]
    storage_boundary: str
    test_adapter: str


@dataclass(frozen=True)
class DisabledOperationEntry:
    operation: str
    owner: str
    method: str
    path: str
    inventory_source: str
    probe_method: str
    probe_path: str


def _route_operations(effective: EffectiveRoute) -> Iterable[tuple[str, str]]:
    for method in sorted((effective.route.methods or set()) - {"HEAD", "OPTIONS"}):
        yield method, effective.path


def _concrete_probe_path(path_template: str) -> str:
    def replace(match: re.Match[str]) -> str:
        parameter = match.group(1)
        converter = match.group(2) or ""
        lowered = parameter.lower()
        if converter == "int" or lowered.endswith(("_index", "_number")):
            return "1"
        if converter == "float":
            return "1.0"
        if converter == "uuid" or lowered.endswith("_id") or lowered in {"id", "tenant"}:
            return "00000000-0000-4000-8000-000000000000"
        if converter == "path":
            return "disabled-probe/segment"
        return "disabled-probe"

    return re.sub(r"\{([^}:]+)(?::([^}]+))?\}", replace, path_template)


def _effective_route_stub(effective: EffectiveRoute) -> APIRoute:
    """Copy an ``APIRoute`` onto the path it is actually served from.

    FastAPI >=0.137 keeps include prefixes in a wrapper context rather than on
    the original route.  Policy classification and the middleware-free 404
    probe both require the served path, while retaining the route's endpoint
    and dependency graph.  A shallow copy is sufficient because path matching
    is the only route state that changes.
    """

    stub = copy.copy(effective.route)
    stub.path = effective.path
    stub.path_regex, stub.path_format, stub.param_convertors = compile_path(effective.path)
    return stub


def _validate_owner_and_collision_invariants(routes: list[EffectiveRoute]) -> None:
    unowned = [
        f"{sorted(effective.route.methods or set())} {effective.path}"
        for effective in routes
        if route_owner(effective.route) is None
    ]
    if unowned:
        raise RouteManifestError(f"Operations bypassed ownership registration: {unowned}")

    unknown_owners = sorted(
        {
            owner
            for effective in routes
            if (owner := route_owner(effective.route)) not in ALL_ROUTE_OWNERS
        }
    )
    if unknown_owners:
        raise RouteManifestError(f"Orphaned/unknown route owners: {unknown_owners}")

    observed_router_owners = {
        route_owner(effective.route)
        for effective in routes
        if route_owner(effective.route) in VALID_ROUTER_NAMES
    }
    orphaned_catalog_owners = VALID_ROUTER_NAMES - observed_router_owners
    if orphaned_catalog_owners:
        raise RouteManifestError(
            "Router catalog entries registered no operations; remove or explicitly mount them: "
            f"{sorted(orphaned_catalog_owners)}"
        )

    by_operation: dict[tuple[str, str], list[str]] = defaultdict(list)
    for effective in routes:
        owner = route_owner(effective.route)
        for method, path in _route_operations(effective):
            by_operation[(method, path)].append(owner or "<unowned>")
    duplicates = {f"{method} {path}": owners for (method, path), owners in by_operation.items() if len(owners) > 1}
    if duplicates:
        raise RouteManifestError(f"Duplicate method/path ownership: {duplicates}")


def _validate_route_types(app: FastAPI, *, allow_framework_docs: bool) -> None:
    """Reject HTTP mounts/routes which bypass APIRoute ownership metadata."""

    unexpected: list[str] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            continue
        if hasattr(route, "effective_route_contexts"):
            for context in route.effective_route_contexts():
                original = getattr(context, "original_route", None)
                if isinstance(original, APIRoute):
                    continue
                unexpected.append(
                    repr(
                        (
                            type(original).__module__,
                            type(original).__name__,
                            getattr(context, "path", None),
                            getattr(original, "name", None),
                            tuple(sorted(getattr(original, "methods", None) or ())),
                        )
                    )
                )
            continue
        signature = (
            type(route).__module__,
            type(route).__name__,
            getattr(route, "path", None),
            getattr(route, "name", None),
            tuple(sorted(getattr(route, "methods", None) or ())),
        )
        if allow_framework_docs and signature in _FRAMEWORK_DOC_ROUTE_SIGNATURES:
            continue
        unexpected.append(repr(signature))
    if unexpected:
        raise RouteManifestError(
            "Route surfaces bypassed APIRoute ownership/classification: "
            f"{unexpected}"
        )


def build_route_security_manifest(app: FastAPI) -> dict[str, Any]:
    """Return the deterministic, sanitized manifest for ``app``."""

    _validate_route_types(app, allow_framework_docs=True)
    routes = list(iter_effective_routes(app))
    if len(routes) < _MINIMUM_INVENTORY_ROUTE_COUNT:
        raise RouteManifestError(
            f"Route inventory found only {len(routes)} effective API routes; expected at least "
            f"{_MINIMUM_INVENTORY_ROUTE_COUNT}. Refuse to validate a potentially collapsed route table."
        )
    _validate_owner_and_collision_invariants(routes)

    enabled_entries: list[OperationManifestEntry] = []
    enabled_routes: dict[tuple[str, str], APIRoute] = {}
    omitted_by_path: dict[str, list[tuple[str, APIRoute]]] = defaultdict(list)
    disabled_operations: list[tuple[str, str, str, APIRoute, str]] = []

    for effective in routes:
        route = effective.route
        owner = route_owner(route)
        if owner is None:  # guarded above; keeps type checkers honest
            continue
        for method, path in _route_operations(effective):
            if owner in PRODUCTION_OWNERS:
                policy_route = _effective_route_stub(effective)
                classification, auth, permissions, boundary, adapter_name = classify_operation(
                    policy_route,
                    owner=owner,
                    method=method,
                )
                enabled_entries.append(
                    OperationManifestEntry(
                        operation=operation_id(owner, method, path),
                        owner=owner,
                        method=method,
                        path=path,
                        classification=classification,
                        authentication=auth,
                        required_permissions=permissions,
                        storage_boundary=boundary,
                        test_adapter=adapter_name,
                    )
                )
                enabled_routes[(method, path)] = route
            elif owner in OMITTED_ROUTER_OWNERS:
                disabled_operations.append((owner, method, path, route, "development-route-table"))
                omitted_by_path[path].append((method, route))
            else:
                raise RouteManifestError(f"Operation {operation_id(owner, method, path)} has no release disposition")

    # Some service-local diagnostics are deliberately filtered while an
    # optional router is copied because another optional service registered
    # the same compatibility path first. They are absent from the executable
    # broad table (so ownership stays unique) but remain part of the exhaustive
    # omitted-source inventory and exact-404 proof.
    for effective in excluded_owned_routes(app):
        route = effective.route
        owner = route_owner(route)
        if owner not in OMITTED_ROUTER_OWNERS:
            continue
        for method, path in _route_operations(effective):
            disabled_operations.append((owner, method, path, route, "source-excluded-shadow"))
            omitted_by_path[path].append((method, route))

    observed_production_owners = {entry.owner for entry in enabled_entries}
    missing_production_owners = set(PRODUCTION_OWNERS) - observed_production_owners
    if missing_production_owners:
        raise RouteManifestError(
            f"Production owners with no executable operations: {sorted(missing_production_owners)}"
        )

    observed_enabled_keys = {operation_key(entry.owner, entry.method, entry.path) for entry in enabled_entries}
    missing_required_exact_policies = REQUIRED_EXACT_TENANT_API_KEY_POLICIES - set(
        TENANT_API_KEY_OPERATION_POLICIES
    )
    if missing_required_exact_policies:
        raise RouteManifestError(
            "Required exact tenant API-key policies are missing: "
            f"{sorted(missing_required_exact_policies)}"
        )
    stale_policy_rules = (PUBLIC_OPERATIONS | STRIPE_WEBHOOK_OPERATIONS) - observed_enabled_keys
    if stale_policy_rules:
        raise RouteManifestError(f"Explicit operation policy rules are orphaned: {sorted(stale_policy_rules)}")

    tenant_api_key_entries = [
        entry
        for entry in enabled_entries
        if entry.classification == "tenant-scoped" and entry.authentication.startswith("x-regengine-api-key")
    ]
    observed_owner_policy_names = {
        entry.owner
        for entry in tenant_api_key_entries
        if operation_key(entry.owner, entry.method, entry.path) not in TENANT_API_KEY_OPERATION_POLICIES
    }
    stale_tenant_owner_policies = set(TENANT_API_KEY_OWNER_POLICIES) - observed_owner_policy_names
    stale_tenant_operation_policies = set(TENANT_API_KEY_OPERATION_POLICIES) - observed_enabled_keys
    if stale_tenant_owner_policies or stale_tenant_operation_policies:
        raise RouteManifestError(
            "Explicit tenant API-key policies are orphaned: "
            f"owners={sorted(stale_tenant_owner_policies)}, "
            f"operations={sorted(stale_tenant_operation_policies)}"
        )

    collisions = sorted(
        f"{method} {path} ({owner} vs {route_owner(enabled_routes[(method, path)])})"
        for owner, method, path, _route, _source in disabled_operations
        if (method, path) in enabled_routes
    )
    if collisions:
        raise RouteManifestError(f"Enabled/omitted method-path collisions: {collisions}")

    disabled_entries = [
        DisabledOperationEntry(
            operation=operation_id(owner, method, path),
            owner=owner,
            method=method,
            path=path,
            inventory_source=source,
            probe_method=method,
            probe_path=_concrete_probe_path(path),
        )
        for owner, method, path, _route, source in disabled_operations
    ]

    enabled_entries.sort(key=lambda entry: (entry.path, entry.method, entry.owner))
    disabled_entries.sort(key=lambda entry: (entry.path, entry.method, entry.owner))
    classifications = Counter(entry.classification for entry in enabled_entries)

    return {
        "schema_version": 1,
        "source": "server/main.py FastAPI route table",
        "production_router_groups": sorted(PRODUCTION_ENABLED_ROUTERS),
        "always_mounted_owners": sorted(ALWAYS_MOUNTED_OWNERS),
        "enabled_operations": [
            {**asdict(entry), "required_permissions": list(entry.required_permissions)} for entry in enabled_entries
        ],
        "disabled_operations": [asdict(entry) for entry in disabled_entries],
        "summary": {
            "enabled_operation_count": len(enabled_entries),
            "disabled_operation_count": len(disabled_entries),
            "disabled_unique_path_count": len(omitted_by_path),
            "enabled_by_classification": dict(sorted(classifications.items())),
        },
    }


def production_operation_snapshot(app: FastAPI) -> list[dict[str, str]]:
    """Return the owned operation table from an actual production import."""

    _validate_route_types(app, allow_framework_docs=False)
    operations: list[dict[str, str]] = []
    for effective in iter_effective_routes(app):
        route = effective.route
        owner = route_owner(route)
        if owner is None:
            raise RouteManifestError(f"Production operation {effective.path} is unowned")
        for method, path in _route_operations(effective):
            operations.append(
                {
                    "operation": operation_id(owner, method, path),
                    "owner": owner,
                    "method": method,
                    "path": path,
                }
            )
    return sorted(operations, key=lambda item: (item["path"], item["method"], item["owner"]))


def probe_omitted_paths_exact_404(app: FastAPI, manifest: dict[str, Any]) -> int:
    """Probe every omitted operation against an actual production table.

    A middleware-free app measures routing only. Before each request Starlette's
    matcher proves no enabled route would consume it; a match fails closed and
    the request is never issued.
    """

    from fastapi.testclient import TestClient

    _validate_route_types(app, allow_framework_docs=False)
    production_routes = [_effective_route_stub(effective) for effective in iter_effective_routes(app)]
    probe_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    probe_app.router.routes.extend(production_routes)

    probes = [
        (item["probe_method"], item["path"], item["probe_path"], item["operation"])
        for item in manifest["disabled_operations"]
    ]

    with TestClient(probe_app, raise_server_exceptions=True) as client:
        for method, template, concrete_path, operation in sorted(probes):
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": concrete_path,
                "raw_path": concrete_path.encode("ascii"),
                "query_string": b"",
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 1),
                "server": ("testserver", 80),
            }
            matching = [
                f"{sorted(route.methods or set())} {route.path}"
                for route in production_routes
                if route.matches(scope)[0] is Match.FULL
            ]
            if matching:
                raise RouteManifestError(
                    f"Omitted probe {method} {concrete_path} for {operation} ({template}) would execute "
                    f"an enabled route: {matching}"
                )
            response = client.request(method, concrete_path)
            if response.status_code != 404:
                raise RouteManifestError(
                    f"Omitted probe {method} {concrete_path} for {operation} ({template}) returned "
                    f"{response.status_code}, expected exact 404"
                )
    return len(probes)


__all__ = [
    "ALWAYS_MOUNTED_OWNERS",
    "PRODUCTION_OWNERS",
    "RouteManifestError",
    "build_route_security_manifest",
    "probe_omitted_paths_exact_404",
    "production_operation_snapshot",
]
