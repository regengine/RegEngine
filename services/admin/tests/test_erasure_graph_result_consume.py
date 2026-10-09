"""Erasure graph delete must consume its results and verify counters.

Regression tests for the finding that ``_delete_neo4j_user_graph_data``
awaited ``session.run`` but never consumed the returned result. The Neo4j
driver sends the query and buffers the result header on ``run``; the
statement is only guaranteed to have executed once the result is
consumed, and the summary counters are the only record of what the
DETACH DELETE actually removed. Without ``consume()``, a failed delete
surfaced nowhere and a silent no-op looked like success.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from services.admin.app import erasure_routes as mod

TEST_TENANT_ID = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
TEST_USER_ID = "11112222-3333-4444-5555-666677778888"


def _make_driver_with_results(delete_result, anonymize_result):
    """Return a fake AsyncGraphDatabase whose session yields the two results."""
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(side_effect=[delete_result, anonymize_result])

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=session_cm)
    mock_driver.__aenter__ = AsyncMock(return_value=mock_driver)
    mock_driver.__aexit__ = AsyncMock(return_value=False)

    mock_async_gdb = MagicMock()
    mock_async_gdb.driver = MagicMock(return_value=mock_driver)
    return mock_async_gdb, mock_session


def _make_result(nodes_deleted=0, relationships_deleted=0, properties_set=0):
    result = AsyncMock()
    result.consume = AsyncMock(
        return_value=SimpleNamespace(
            counters=SimpleNamespace(
                nodes_deleted=nodes_deleted,
                relationships_deleted=relationships_deleted,
                properties_set=properties_set,
            )
        )
    )
    return result


@pytest.mark.asyncio
async def test_graph_delete_results_consumed_and_counters_logged(monkeypatch):
    """Both Cypher results are consumed and their counters end up in logs."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-test:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpass")

    delete_result = _make_result(nodes_deleted=2, relationships_deleted=1)
    anonymize_result = _make_result(properties_set=3)
    mock_async_gdb, _mock_session = _make_driver_with_results(delete_result, anonymize_result)

    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        with structlog.testing.capture_logs() as cap_logs:
            await mod._delete_neo4j_user_graph_data(TEST_TENANT_ID, TEST_USER_ID)

    # Pre-fix code never touched the results: both consumes must run now.
    assert delete_result.consume.await_count == 1, (
        "delete result was never consumed, so DETACH DELETE may never have executed"
    )
    assert anonymize_result.consume.await_count == 1, (
        "anonymize result was never consumed, so actor rewrite may never have executed"
    )

    info_logs = [e for e in cap_logs if e.get("log_level") == "info"]
    assert info_logs, f"Expected an info log with counters; got: {cap_logs}"
    event = next(
        (e for e in info_logs if "neo4j" in e.get("event", "").lower()),
        None,
    )
    assert event is not None, f"Expected a neo4j erasure info log; got: {info_logs}"
    assert event.get("nodes_deleted") == 2
    assert event.get("relationships_deleted") == 1
    assert event.get("anonymized_properties_set") == 3


@pytest.mark.asyncio
async def test_consume_failure_warns_without_raising(monkeypatch):
    """A lazily failing query surfaces as a warning, still best-effort."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-test:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpass")

    delete_result = AsyncMock()
    delete_result.consume = AsyncMock(side_effect=Exception("Connection reset"))
    anonymize_result = _make_result()
    mock_async_gdb, _mock_session = _make_driver_with_results(delete_result, anonymize_result)

    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        with structlog.testing.capture_logs() as cap_logs:
            # Must not raise: Postgres erasure already committed.
            await mod._delete_neo4j_user_graph_data(TEST_TENANT_ID, TEST_USER_ID)

    warning_logs = [e for e in cap_logs if e.get("log_level") == "warning"]
    assert warning_logs, "A consume-time failure must be logged as a warning instead of vanishing"
    assert any("neo4j" in e.get("event", "").lower() for e in warning_logs)
