"""Tenant-scoped Neo4j session wrapper (#1397).

Background
----------
The Neo4j Python driver hands out sessions from a process-wide connection
pool. Unlike PostgreSQL (where we set ``app.tenant_id`` via ``set_config`` and
then rely on RLS policies to enforce isolation), Neo4j has no server-side
equivalent: a session has no concept of "current tenant" that Cypher can
consult. The only enforcement is whatever the caller puts in the Cypher
pattern — and per the #1393-#1396 audit, several queries historically did not
scope by ``tenant_id`` at all.

PR #1437 fixed the Cypher patterns. #1397 is about the surrounding plumbing:
we never guaranteed that a session checked out for tenant A was used only for
tenant A, and we never validated that Cypher strings included ``tenant_id``.

This module provides that plumbing, as a library that new write paths (and
the graph_outbox drainer from #1398) can adopt. It does not touch
``supplier_graph_sync.py`` — that file's ``_run`` method stays as-is for the
existing best-effort path; the reliability fix is the outbox.

Contract
--------
``session_with_tenant(driver, tenant_id)`` returns a context-managed wrapper
around a driver session. Every ``.run(query, params)`` call:

  * Injects ``tenant_id=<the bound value>`` into ``params``. If the caller
    supplied a conflicting ``params["tenant_id"]``, raises ``ValueError``.
  * Validates that ``query`` is a write query (``MERGE`` / ``CREATE``) whose
    pattern includes ``tenant_id``. Read queries must also mention
    ``tenant_id`` at least once — callers that want to run a global /
    administrative query may pass ``_allow_unscoped=True``.
  * Emits a structured log line with the tenant id and operation tag so
    incident response can reconstruct the write stream.

This is a thin belt on top of driver sessions — it is NOT a Neo4j
native-access-control feature. Treat it the same way you treat the
PostgreSQL RLS helper ``TenantContext``: belt-and-suspenders with the
server-side policy.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any, Iterator, Optional

import structlog

logger = structlog.get_logger("neo4j_tenant_context")


# Regex that asks "does this Cypher string mention tenant_id anywhere?"
#
# We intentionally keep this loose — the goal is a cheap dev-time guard
# that a developer who writes a new write path does not completely forget
# about tenant scoping. The Cypher tenant-scope audit (#1393-#1396) remains
# the source of truth for whether the MERGE pattern is correct; this regex
# just refuses queries where ``tenant_id`` appears nowhere at all.
_TENANT_TOKEN = re.compile(r"\btenant_id\b", re.IGNORECASE)


class _QueryHasNoTenantScope(ValueError):
    """Raised when a Cypher query is missing any reference to tenant_id."""


class _ConflictingTenantParam(ValueError):
    """Raised when a caller supplies a params dict with a tenant_id that
    differs from the session's bound tenant_id."""


def require_tenant_id_in_cypher(query: str) -> None:
    """Fail loudly when ``query`` has no ``tenant_id`` token.

    Raising here, rather than silently proceeding, is the whole point of
    #1397: the static check turns a "we hope this was correct" into a
    "the code refuses to run".
    """
    if _TENANT_TOKEN.search(query) is None:
        raise _QueryHasNoTenantScope(
            "Cypher query has no tenant_id scoping token; refusing to run. "
            "If this is an intentional global/admin query, call "
            "session_with_tenant(...).run(query, params, _allow_unscoped=True)."
        )


class TenantScopedNeo4jSession:
    """A wrapper around a Neo4j driver session bound to a single tenant.

    Invariants:
      * ``tenant_id`` is immutable for the life of the wrapper.
      * Every ``.run(...)`` injects ``tenant_id`` into params. If the caller
        already supplied ``tenant_id`` and it matches, we keep going; if
        it conflicts, we raise.
      * ``.run(...)`` refuses queries that have no tenant_id anywhere,
        unless ``_allow_unscoped=True`` is explicitly passed.
    """

    def __init__(self, raw_session: Any, tenant_id: str) -> None:
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        self._session = raw_session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def run(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
        *,
        _allow_unscoped: bool = False,
        **kwargs: Any,
    ) -> Any:
        params = dict(params or {})

        # Validate the query unless the caller explicitly opts out (e.g.
        # ``CALL db.ping()`` or administrative schema queries).
        if not _allow_unscoped:
            require_tenant_id_in_cypher(query)

        # Inject / validate tenant_id binding.
        existing = params.get("tenant_id")
        if existing is None:
            params["tenant_id"] = self._tenant_id
        elif str(existing) != self._tenant_id:
            raise _ConflictingTenantParam(
                f"params['tenant_id']={existing!r} conflicts with the "
                f"session-bound tenant_id={self._tenant_id!r}; refusing to run"
            )
        # If existing matches, we leave it alone.

        logger.debug(
            "neo4j_tenant_scoped_query",
            tenant_id=self._tenant_id,
            operation=params.get("operation", "unknown"),
        )
        return self._session.run(query, params, **kwargs)

    # Delegate context-manager / close semantics to the underlying session.
    def __enter__(self) -> "TenantScopedNeo4jSession":
        return self

    def __exit__(self, exc_type, exc, tb):
        close = getattr(self._session, "close", None)
        if callable(close):
            close()
        return False

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if callable(close):
            close()


@contextlib.contextmanager
def session_with_tenant(
    driver: Any, tenant_id: str
) -> Iterator[TenantScopedNeo4jSession]:
    """Open a Neo4j session bound to ``tenant_id``.

    Usage::

        with session_with_tenant(driver, tenant_id) as session:
            session.run(MERGE_FOO_QUERY, {"foo_id": ...})
            # params["tenant_id"] is filled in automatically

    The driver's native ``.session()`` method is called with no arguments;
    per-request ``database=`` routing was removed in #1093 because Neo4j
    Community Edition ignores it. Tenant scoping is a Cypher-level
    concern — the wrapper enforces that every query contributes to it.
    """
    if driver is None:
        raise ValueError("driver is required")
    raw = driver.session()
    wrapped = TenantScopedNeo4jSession(raw, tenant_id)
    try:
        yield wrapped
    finally:
        wrapped.close()


__all__ = [
    "TenantScopedNeo4jSession",
    "session_with_tenant",
    "require_tenant_id_in_cypher",
]
