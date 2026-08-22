"""Flatten a FastAPI app's route table, whatever shape the framework uses.

Several guards in this repo work by enumerating an app's routes: the
security gate that proves every endpoint requires auth, the SDK contract
test, and the monolith parity checks. Every one of them walked
``app.routes`` directly, which was correct while ``include_router`` copied
sub-router endpoints onto the parent as flat ``APIRoute`` objects.

fastapi 0.137 changed that. Included routers now stay on ``app.routes`` as
a single ``_IncludedRouter`` wrapper, so a direct walk sees the handful of
routes registered on the app itself and none of the hundreds behind the
routers. For a test that asserts "every endpoint requires auth" that is the
worst possible failure: not an error, just a much smaller set of endpoints
to police.

``iter_effective_routes`` restores the flat view against both shapes, and
refuses to guess. An entry it does not recognise raises ``UnknownRouteShape``
rather than being skipped — a guard that silently enumerates nothing is the
exact outcome this module exists to prevent.
"""

from __future__ import annotations

from typing import Any, Iterator, NamedTuple

from fastapi.routing import APIRoute
from starlette.routing import Mount, Route, WebSocketRoute

__all__ = ["EffectiveRoute", "UnknownRouteShape", "iter_effective_routes", "route_keys"]


class UnknownRouteShape(RuntimeError):
    """A router entry this module does not know how to descend into.

    Raised instead of skipping, so a future framework change fails a guard
    loudly rather than shrinking the set of routes it inspects.
    """


class EffectiveRoute(NamedTuple):
    """An APIRoute together with the path it is actually served on."""

    path: str
    route: APIRoute


def _from_included_router(entry: Any, prefix: str) -> Iterator[EffectiveRoute]:
    """Expand a fastapi>=0.137 ``_IncludedRouter``.

    ``effective_route_contexts()`` is fastapi's own flattening: it recurses
    through nested includes and reports each endpoint's fully-prefixed path,
    which is why this does not re-implement prefix joining.
    """
    for context in entry.effective_route_contexts():
        route = getattr(context, "original_route", None)
        if isinstance(route, APIRoute):
            yield EffectiveRoute(prefix + context.path, route)


def iter_effective_routes(app_or_router: Any, prefix: str = "") -> Iterator[EffectiveRoute]:
    """Yield every ``APIRoute`` reachable from ``app_or_router``.

    Works on a ``FastAPI`` app, an ``APIRouter``, or anything else exposing
    ``.routes``. Paths are returned as served, with all prefixes applied.
    """
    for entry in app_or_router.routes:
        if isinstance(entry, APIRoute):
            yield EffectiveRoute(prefix + entry.path, entry)
        elif hasattr(entry, "effective_route_contexts"):
            # fastapi >= 0.137: an included router, not a route.
            yield from _from_included_router(entry, prefix)
        elif isinstance(entry, Mount):
            mounted = getattr(entry, "app", None)
            if hasattr(mounted, "routes"):
                yield from iter_effective_routes(mounted, prefix + entry.path)
            elif hasattr(entry, "routes"):
                yield from iter_effective_routes(entry, prefix + entry.path)
        elif isinstance(entry, (Route, WebSocketRoute)):
            # Plain starlette routes — /openapi.json, /docs, websockets.
            # Not APIRoutes and never were; the guards have always ignored them.
            continue
        elif hasattr(entry, "routes"):
            yield from iter_effective_routes(entry, prefix)
        else:
            raise UnknownRouteShape(
                f"cannot enumerate routes behind {type(entry).__module__}.{type(entry).__name__}; "
                "teach services/shared/route_introspection.py about it rather than "
                "letting a route-enumerating guard quietly inspect fewer endpoints"
            )


def route_keys(app_or_router: Any, *, methods: frozenset[str] | None = None) -> set[str]:
    """``{"GET /api/v1/thing", ...}`` for every reachable APIRoute.

    ``methods`` defaults to the request methods the guards care about; HEAD
    and OPTIONS are excluded because fastapi adds them implicitly.
    """
    wanted = methods if methods is not None else frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
    return {
        f"{method} {path}"
        for path, route in iter_effective_routes(app_or_router)
        for method in (route.methods or ())
        if method in wanted
    }
