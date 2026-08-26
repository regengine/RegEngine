"""Explicit ownership registration for consolidated FastAPI operations.

FastAPI <=0.136 copied ``APIRoute`` objects onto the parent application while
FastAPI >=0.137 keeps included routers behind wrapper objects.  Recording the
owner against the effective route table supports both shapes without guessing
from URL prefixes or endpoint module names.  The security-manifest gate
consumes the attribute set here and rejects operations which bypass these
helpers.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from types import SimpleNamespace
from typing import Any, TypeVar

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from services.shared.route_introspection import EffectiveRoute, iter_effective_routes

ROUTE_OWNER_ATTRIBUTE = "_regengine_route_owner"
EXCLUDED_ROUTES_STATE_ATTRIBUTE = "_regengine_excluded_owned_routes"

_Endpoint = TypeVar("_Endpoint", bound=Callable[..., Any])


class RouteOwnershipError(RuntimeError):
    """Raised when route ownership cannot be recorded unambiguously."""


def _effective_routes_added_since(app: FastAPI, start: int) -> list[EffectiveRoute]:
    added = SimpleNamespace(routes=app.routes[start:])
    return list(iter_effective_routes(added))


def _assign_owner(routes: Iterable[APIRoute], owner: str) -> None:
    normalized = owner.strip().lower()
    if not normalized:
        raise RouteOwnershipError("Route owner must be non-empty")

    for route in routes:
        current = getattr(route, ROUTE_OWNER_ATTRIBUTE, None)
        if current is not None and current != normalized:
            raise RouteOwnershipError(
                f"Operation {sorted(route.methods or ())} {route.path} already belongs to {current!r}; "
                f"cannot reassign it to {normalized!r}"
            )
        setattr(route, ROUTE_OWNER_ATTRIBUTE, normalized)


def include_owned_router(
    app: FastAPI,
    router: APIRouter,
    *,
    owner: str,
    excluded_operations: Iterable[tuple[str, str]] = (),
    **include_kwargs: Any,
) -> None:
    """Include ``router`` and stamp every effective operation with ``owner``."""

    excluded = {(method.upper(), path) for method, path in excluded_operations}
    router_to_include = router
    if excluded:
        matched: set[tuple[str, str]] = set()
        removed: list[EffectiveRoute] = []
        removed_route_ids: set[int] = set()
        include_prefix = str(include_kwargs.get("prefix", ""))
        for source_path, route in iter_effective_routes(router):
            effective_path = f"{include_prefix}{source_path}"
            route_keys = {
                (method, effective_path)
                for method in (route.methods or set())
                if method not in {"HEAD", "OPTIONS"}
            }
            selected = route_keys & excluded
            if selected:
                unselected = route_keys - excluded
                if unselected:
                    raise RouteOwnershipError(
                        f"Owner {owner!r} cannot partially exclude multi-method route {sorted(route_keys)}; "
                        f"also list {sorted(unselected)}"
                    )
                matched.update(selected)
                removed_route_ids.add(id(route))
                removed.append(EffectiveRoute(effective_path, route))
        missing = excluded - matched
        if missing:
            raise RouteOwnershipError(
                f"Owner {owner!r} requested exclusions that were not registered: {sorted(missing)}"
            )

        direct_route_ids = {id(route) for route in router.routes}
        nested_exclusions = removed_route_ids - direct_route_ids
        if nested_exclusions:
            raise RouteOwnershipError(
                f"Owner {owner!r} cannot exclude operations from a nested included router; "
                "filter that child router at its own include_owned_router call"
            )

        # FastAPI >=0.137 retains the included router by reference, so removing
        # a route after inclusion would also mutate the service-local router.
        # A shallow router copy gives this app its own route list while keeping
        # the original endpoint objects and lifecycle configuration intact.
        router_to_include = copy.copy(router)
        router_to_include.routes = [route for route in router.routes if id(route) not in removed_route_ids]

        _assign_owner((effective.route for effective in removed), owner)
        excluded_routes = getattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, None)
        if excluded_routes is None:
            excluded_routes = []
            setattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, excluded_routes)
        excluded_routes.extend(removed)

    start = len(app.routes)
    app.include_router(router_to_include, **include_kwargs)
    added = _effective_routes_added_since(app, start)
    _assign_owner((effective.route for effective in added), owner)


def owned_api_route(
    app: FastAPI,
    *,
    owner: str,
    path: str,
    methods: Iterable[str],
    **route_kwargs: Any,
) -> Callable[[_Endpoint], _Endpoint]:
    """Register one app-local operation and record its owner atomically."""

    normalized_methods = tuple(method.upper() for method in methods)

    def decorator(endpoint: _Endpoint) -> _Endpoint:
        start = len(app.routes)
        registered = app.api_route(path, methods=list(normalized_methods), **route_kwargs)(endpoint)
        added = _effective_routes_added_since(app, start)
        if len(added) != 1:
            raise RouteOwnershipError(f"Expected one API operation for {normalized_methods} {path}, found {len(added)}")
        _assign_owner((effective.route for effective in added), owner)
        return registered

    return decorator


def claim_existing_operation(
    app: FastAPI,
    *,
    owner: str,
    method: str,
    path: str,
) -> None:
    """Claim a route registered by a library that cannot use our decorator.

    This is intentionally exact (method plus route template).  It is currently
    used only for the Prometheus instrumentator's ``GET /metrics`` route.
    """

    normalized_method = method.upper()
    matches = [
        route
        for effective_path, route in iter_effective_routes(app)
        if effective_path == path and normalized_method in (route.methods or set())
    ]
    if len(matches) != 1:
        raise RouteOwnershipError(
            f"Expected exactly one existing operation for {normalized_method} {path}, found {len(matches)}"
        )
    _assign_owner(matches, owner)


def route_owner(route: APIRoute) -> str | None:
    """Return the owner stamped on ``route``, if any."""

    value = getattr(route, ROUTE_OWNER_ATTRIBUTE, None)
    return value if isinstance(value, str) else None


def excluded_owned_routes(app: FastAPI) -> tuple[EffectiveRoute, ...]:
    """Return source operations intentionally omitted from the app table."""

    routes = getattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, ())
    return tuple(route for route in routes if isinstance(route, EffectiveRoute))


__all__ = [
    "RouteOwnershipError",
    "claim_existing_operation",
    "excluded_owned_routes",
    "include_owned_router",
    "owned_api_route",
    "route_owner",
]
