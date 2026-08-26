"""Explicit ownership registration for consolidated FastAPI operations.

FastAPI copies ``APIRoute`` objects when a router is included.  Recording the
owner at inclusion time avoids fragile ownership guesses from URL prefixes or
endpoint module names.  The security-manifest gate consumes the attribute set
here and rejects any operation which bypasses these helpers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

ROUTE_OWNER_ATTRIBUTE = "_regengine_route_owner"
EXCLUDED_ROUTES_STATE_ATTRIBUTE = "_regengine_excluded_owned_routes"

_Endpoint = TypeVar("_Endpoint", bound=Callable[..., Any])


class RouteOwnershipError(RuntimeError):
    """Raised when route ownership cannot be recorded unambiguously."""


def _api_routes_added_since(app: FastAPI, start: int) -> list[APIRoute]:
    return [route for route in app.routes[start:] if isinstance(route, APIRoute)]


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
    """Include ``router`` and stamp every copied operation with ``owner``."""

    start = len(app.routes)
    app.include_router(router, **include_kwargs)
    added = _api_routes_added_since(app, start)
    excluded = {(method.upper(), path) for method, path in excluded_operations}
    if excluded:
        matched: set[tuple[str, str]] = set()
        kept: list[APIRoute] = []
        removed: list[APIRoute] = []
        for route in added:
            route_keys = {
                (method, route.path) for method in (route.methods or set()) if method not in {"HEAD", "OPTIONS"}
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
                app.routes.remove(route)
                removed.append(route)
            else:
                kept.append(route)
        missing = excluded - matched
        if missing:
            raise RouteOwnershipError(
                f"Owner {owner!r} requested exclusions that were not registered: {sorted(missing)}"
            )
        _assign_owner(removed, owner)
        excluded_routes = getattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, None)
        if excluded_routes is None:
            excluded_routes = []
            setattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, excluded_routes)
        excluded_routes.extend(removed)
        added = kept
    _assign_owner(added, owner)


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
        added = _api_routes_added_since(app, start)
        if len(added) != 1:
            raise RouteOwnershipError(f"Expected one API operation for {normalized_methods} {path}, found {len(added)}")
        _assign_owner(added, owner)
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
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == path and normalized_method in (route.methods or set())
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


def excluded_owned_routes(app: FastAPI) -> tuple[APIRoute, ...]:
    """Return source operations intentionally omitted from the app table."""

    routes = getattr(app.state, EXCLUDED_ROUTES_STATE_ATTRIBUTE, ())
    return tuple(route for route in routes if isinstance(route, APIRoute))


__all__ = [
    "RouteOwnershipError",
    "claim_existing_operation",
    "excluded_owned_routes",
    "include_owned_router",
    "owned_api_route",
    "route_owner",
]
