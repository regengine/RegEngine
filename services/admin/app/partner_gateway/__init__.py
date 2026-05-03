"""RegEngine Partner Gateway — white-label API for partners.

Mounted at ``/v1/partner`` in ``services/admin/main.py``. The contract is
defined by ``regengine-partner-gateway-openapi.yaml`` at the repo root —
that file is the source of truth for paths, request/response schemas,
and required scopes (via ``x-required-scopes``).

This package is currently a skeleton: ``auth.py`` is production-ready
and enforces real scope checks against the shared ``api_keys`` table,
while ``router.py`` ships only two reference endpoints (``listClients``
and ``getRevenueMetrics``) so the auth pattern is locked in. The other
ten OpenAPI operations are TODOs — see ``router.py``.
"""
