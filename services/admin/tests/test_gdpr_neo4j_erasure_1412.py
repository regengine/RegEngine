"""
Tests for GDPR Neo4j erasure scoping.

Two scenarios are covered:

1. Neo4j configured and reachable — ``DETACH DELETE`` Cypher is executed with
   tenant and user parameters (never string-formatted).

2. Neo4j unavailable (driver raises) — erasure still succeeds (Postgres path
   completed), and a warning is logged instead of raising.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_TENANT_ID = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
TEST_USER_ID = "11112222-3333-4444-5555-666677778888"


def _make_async_driver_mock(run_side_effect=None):
    """Return a mock that mimics ``AsyncGraphDatabase.driver`` context manager."""
    mock_session = AsyncMock()
    if run_side_effect is not None:
        mock_session.run = AsyncMock(side_effect=run_side_effect)
    else:
        mock_session.run = AsyncMock(return_value=None)

    # session() returns an async context manager
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=session_cm)
    mock_driver.__aenter__ = AsyncMock(return_value=mock_driver)
    mock_driver.__aexit__ = AsyncMock(return_value=False)

    mock_async_gdb = MagicMock()
    mock_async_gdb.driver = MagicMock(return_value=mock_driver)
    return mock_async_gdb, mock_driver, mock_session


# ---------------------------------------------------------------------------
# Test 1: Neo4j configured — DETACH DELETE executed with tenant and user params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neo4j_user_graph_deleted_with_tenant_and_user_id(monkeypatch):
    """When NEO4J_URI is set, DETACH DELETE is scoped to the data subject."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-test:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpass")

    mock_async_gdb, mock_driver, mock_session = _make_async_driver_mock()

    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        # Re-import to pick up patched module
        import importlib
        import services.admin.app.erasure_routes as mod
        importlib.reload(mod)

        await mod._delete_neo4j_user_graph_data(TEST_TENANT_ID, TEST_USER_ID)

    mock_session.run.assert_awaited_once()
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    kwargs = call_args[1]

    # Cypher must use parameter placeholders, not formatted identifiers.
    assert "$tenant_id" in cypher, "tenant_id must be a Cypher parameter"
    assert "$user_id" in cypher, "user_id must be a Cypher parameter"
    assert TEST_TENANT_ID not in cypher, (
        "tenant_id must NOT be string-formatted into the Cypher query"
    )
    assert TEST_USER_ID not in cypher, (
        "user_id must NOT be string-formatted into the Cypher query"
    )
    assert "WHERE" in cypher, "delete query must filter by user data"
    assert "MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n" not in cypher
    assert kwargs.get("tenant_id") == TEST_TENANT_ID
    assert kwargs.get("user_id") == TEST_USER_ID


# ---------------------------------------------------------------------------
# Test 2: Neo4j unavailable — erasure still completes, warning logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neo4j_unavailable_erasure_succeeds_and_warns(monkeypatch):
    """When the Neo4j driver raises, _delete_neo4j_user_graph_data does NOT
    propagate the exception (best-effort) and logs a warning via structlog."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-test:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpass")

    mock_async_gdb, mock_driver, mock_session = _make_async_driver_mock(
        run_side_effect=Exception("Connection refused")
    )

    warning_events: list = []

    def capture_warning(*args, logger, method, event_dict):
        if method == "warning":
            warning_events.append(event_dict.copy())
        raise structlog.DropEvent()

    import structlog

    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        import importlib
        import services.admin.app.erasure_routes as mod
        importlib.reload(mod)

        with structlog.testing.capture_logs() as cap_logs:
            # Must not raise
            await mod._delete_neo4j_user_graph_data(TEST_TENANT_ID, TEST_USER_ID)

    # A warning must have been emitted
    warning_logs = [e for e in cap_logs if e.get("log_level") == "warning"]
    assert warning_logs, (
        f"Expected a warning log when Neo4j is unavailable; got: {cap_logs}"
    )
    assert any("neo4j" in e.get("event", "").lower() for e in warning_logs)


# ---------------------------------------------------------------------------
# Test 3: NEO4J_URI not set — skip silently (no driver instantiated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neo4j_skipped_when_uri_not_set(monkeypatch):
    """When NEO4J_URI / NEO4J_URL are absent, the function returns immediately
    without attempting any driver connection."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_URL", raising=False)

    mock_async_gdb = MagicMock()

    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        import importlib
        import services.admin.app.erasure_routes as mod
        importlib.reload(mod)

        # Must not raise and must not call driver()
        await mod._delete_neo4j_user_graph_data(TEST_TENANT_ID, TEST_USER_ID)

    mock_async_gdb.driver.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Source-level guardrail — tenant_id never string-formatted in Cypher
# ---------------------------------------------------------------------------


def test_cypher_constant_uses_user_parameter_not_tenant_wide_delete():
    """The module-level Cypher must stay user-scoped, never tenant-wide."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app"
        / "erasure_routes.py"
    ).read_text()

    assert "$tenant_id" in source, (
        "Cypher query must use $tenant_id parameter placeholder"
    )
    assert "$user_id" in source, (
        "Cypher query must use $user_id parameter placeholder"
    )
    assert "DETACH DELETE" in source, "DETACH DELETE must appear in erasure_routes.py"
    assert "_delete_neo4j_tenant_subgraph" not in source
    assert "_CYPHER_DELETE_TENANT_SUBGRAPH" not in source
    assert "MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n" not in source
