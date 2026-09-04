"""Explicit ownership registration for consolidated FastAPI operations.

Ownership is recorded on per-app ``APIRoute`` copies at inclusion time, which
avoids fragile ownership guesses from URL prefixes or endpoint module names.
The security-manifest gate consumes the attribute set here and rejects any
operation which bypasses these helpers.

fastapi >= 0.137 no longer copies ``APIRoute`` objects on ``include_router``;
it appends a single lazy ``_IncludedRouter`` wrapper and resolves effective
routes per request. Everything in this security layer — owner stamping,
operation exclusion, the manifest's route-table walks, and the exact-404
probes — is built on flat per-app copies, so ``include_owned_router``
materializes each lazy include back into real ``APIRoute`` objects (via
fastapi's own ``_EffectiveRouteContext`` combination of prefix, tags,
dependencies, and response defaults) before recording ownership. Without this
the consolidated app raised ``RouteOwnershipError`` at import because the
exclusion matcher saw no copied operations at all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from fastapi import APIRouter, FastAPI

# request_response must be fastapi's wrapper (not starlette's): it installs
# the fastapi_inner_astack/fastapi_function_astack scope keys the request
# handler asserts on.
from fastapi.routing import APIRoute, request_response
from starlette.routing import BaseRoute

ROUTE_OWNER_ATTRIBUTE = "_regengine_route_owner"
EXCLUDED_ROUTES_STATE_ATTRIBUTE = "_regengine_excluded_owned_routes"

_Endpoint = TypeVar("_Endpoint", bound=Callable[..., Any])


class RouteOwnershipError(RuntimeError):
    """Raised when route ownership cannot be recorded unambiguously."""


def _api_routes_added_since(app: FastAPI, start: int) -> list[APIRoute]:
    return [route for route in app.routes[start:] if isinstance(route, APIRoute)]


def _materialized_api_route(context: Any) -> APIRoute:
    """Build a flat ``APIRoute`` copy from a fastapi lazy-include context.

    ``_EffectiveRouteContext.from_api_route`` already combined the include
    context with the original route (full path, merged tags/dependencies/
    responses, resolved response-class defaults), so include-combined values
    are read off the context and route-intrinsic values off the original.
    """

    original = context.original_route
    route_class = type(original)
    materialized = route_class(
        context.path,
        endpoint=original.endpoint,
        response_model=original.response_model,
        status_code=original.status_code,
        tags=list(context.tags or []),
        dependencies=list(context.dependencies or []),
        summary=original.summary,
        description=original.description,
        response_description=original.response_description,
        responses=dict(context.responses or {}),
        deprecated=context.deprecated,
        name=original.name,
        methods=list(original.methods or []),
        operation_id=original.operation_id,
        response_model_include=original.response_model_include,
        response_model_exclude=original.response_model_exclude,
        response_model_by_alias=original.response_model_by_alias,
        response_model_exclude_unset=original.response_model_exclude_unset,
        response_model_exclude_defaults=original.response_model_exclude_defaults,
        response_model_exclude_none=original.response_model_exclude_none,
        include_in_schema=context.include_in_schema,
        response_class=context.response_class,
        dependency_overrides_provider=context.dependency_overrides_provider,
        callbacks=list(context.callbacks or []) or None,
        openapi_extra=original.openapi_extra,
        generate_unique_id_function=context.generate_unique_id_function,
        strict_content_type=context.strict_content_type,
    )
    # Streaming state is lost by the flat copy: ``stream_item_type`` is
    # derived in ``APIRoute.__init__`` only while ``response_model`` is
    # still a DefaultPlaceholder, but we pass the original's *resolved*
    # response_model (None for streaming generator endpoints), which
    # short-circuits the derivation. Restore it and rebuild the request
    # handler, which captured ``stream_item_field`` at construction time.
    # (``is_json_stream``/``is_sse_stream`` re-derive correctly from the
    # passed-through response_class.) No production route streams today —
    # this keeps the materializer faithful when one does (CodeRabbit
    # review of #3036).
    original_stream_type = getattr(original, "stream_item_type", None)
    if original_stream_type is not None and getattr(materialized, "stream_item_type", None) is None:
        materialized.stream_item_type = original_stream_type
        materialized.stream_item_field = original.stream_item_field
        materialized.app = request_response(materialized.get_route_handler())
    return materialized


def _materialize_lazy_includes(app: FastAPI, start: int) -> None:
    """Replace lazy included-router entries appended since ``start`` with flat copies."""

    tail: list[BaseRoute] = []
    changed = False
    for entry in app.routes[start:]:
        if not hasattr(entry, "effective_route_contexts"):
            tail.append(entry)
            continue
        changed = True
        for context in entry.effective_route_contexts():
            original = getattr(context, "original_route", None)
            if isinstance(original, APIRoute):
                tail.append(_materialized_api_route(context))
                continue
            starlette_route = getattr(context, "starlette_route", None)
            if starlette_route is None:
                raise RouteOwnershipError(
                    f"Cannot materialize included route entry {original!r}; teach "
                    "server/route_ownership.py about it rather than serving a route "
                    "the ownership manifest cannot see"
                )
            tail.append(starlette_route)
    if changed:
        app.routes[start:] = tail
        mark_changed = getattr(app.router, "_mark_routes_changed", None)
        if callable(mark_changed):
            mark_changed()


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
    _materialize_lazy_includes(app, start)
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
