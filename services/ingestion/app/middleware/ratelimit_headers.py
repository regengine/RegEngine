"""Emit ``X-RateLimit-*`` headers on 2xx responses (issue #2307).

Background
----------
The ingestion service consumes a per-tenant rate-limit bucket inside several
dependencies / inline guards:

* ``app.authz.require_permission`` (RBAC bucket per scope/role)
* ``app.routes_ingest._endpoint_rate_limit`` (per-endpoint bucket)
* ``app.webhook_router_v2._check_rate_limit`` / ``_check_read_rate_limit``

Each of those records the current bucket state on ``request.state`` via
``rate_limit_limit / remaining / reset / tenant / scope``. Previously the
matching ``X-RateLimit-*`` response headers were only emitted on the 429
error path — successful 2xx responses dropped them, forcing well-behaved
clients to wait for a 429 before they could back off (defeating the whole
point of a budget header).

This middleware closes that gap. It runs late in the stack (after the
route handler completes) and copies any ``rate_limit_*`` values stashed on
``request.state`` onto the outbound response, but **only**:

* on 2xx responses (4xx/5xx already carry their own headers via the
  ``HTTPException(headers=...)`` paths), and
* on routes that are actually rate-limited (the prefix allowlist below).

The middleware does **not** call ``consume_tenant_rate_limit`` — it only
reads what the upstream guard already recorded. This guarantees we never
double-count a request against its bucket.
"""

from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Path prefixes whose handlers are guarded by a rate-limit dependency that
# populates ``request.state.rate_limit_*``. Anything outside this list is
# left untouched so unauthenticated routes (healthz, docs, openapi.json)
# do not leak misleading headers.
_RATE_LIMITED_PREFIXES: tuple[str, ...] = (
    "/api/v1/records",
    "/api/v1/webhooks",
    "/api/v1/fda/export",
    "/api/v1/ingest",
)


_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-RateLimit-Limit", "rate_limit_limit"),
    ("X-RateLimit-Remaining", "rate_limit_remaining"),
    ("X-RateLimit-Reset", "rate_limit_reset"),
    ("X-RateLimit-Tenant", "rate_limit_tenant"),
    ("X-RateLimit-Scope", "rate_limit_scope"),
)


def _path_matches(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in prefixes)


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Mirror ``request.state.rate_limit_*`` onto 2xx responses."""

    def __init__(self, app, prefixes: tuple[str, ...] = _RATE_LIMITED_PREFIXES) -> None:
        super().__init__(app)
        self._prefixes = prefixes

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only annotate successful responses on rate-limited paths. 4xx/5xx
        # responses on the 429 path already carry the headers; non-2xx
        # responses elsewhere intentionally do not advertise budget state.
        if not (200 <= response.status_code < 300):
            return response
        if not _path_matches(request.url.path, self._prefixes):
            return response

        state = getattr(request, "state", None)
        if state is None:  # pragma: no cover - defensive
            return response

        for header_name, state_attr in _HEADERS:
            # Never overwrite a value the handler explicitly set.
            if header_name in response.headers:
                continue
            value = getattr(state, state_attr, None)
            if value is None or value == "":
                continue
            response.headers[header_name] = str(value)

        return response
