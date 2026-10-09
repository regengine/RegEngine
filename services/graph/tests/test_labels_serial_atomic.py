"""Regression tests for atomic serial reservation in labels.py.

The audit found that concurrent ``POST /batch/init`` calls could mint
duplicate serial IDs because the reservation query read ``next_serial``
and wrote it back with no locking. These tests prove the fix:

* the first reservation attempt uses the APOC atomic counter,
* when APOC is unavailable the retry uses a lock-ordered query whose
  lock write precedes the counter read,
* two concurrent batch requests receive disjoint serial ranges, both
  with and without APOC.

The concurrency tests emulate documented Neo4j behavior in a fake
session: writes take an exclusive lock held to commit (so a second
transaction waits), while plain reads do not block. The unguarded
branch deliberately yields between read and write so the old query
deterministically produces overlapping ranges.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.routers.labels import (  # noqa: E402
    ATOMIC_RESERVE_CYPHER,
    LOCKED_RESERVE_CYPHER,
    LabelBatchInitRequest,
    PackagingLevel,
    ProductInfo,
    TraceabilityInfo,
    UnitOfMeasure,
    _is_apoc_unavailable,
    _reserve_serial_range,
    initialize_label_batch,
)

APOC_MISSING_MESSAGE = "There is no procedure with the name `apoc.atomic.add` registered for this database instance."
TEST_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_request(quantity: int = 10) -> LabelBatchInitRequest:
    return LabelBatchInitRequest(
        packer_gln="0614141000001",
        product=ProductInfo(gtin="00000012345678", description="Test Product", expected_units=1),
        traceability=TraceabilityInfo(lot_number="LOT-TEST-001", pack_date="2024-01-01"),
        quantity=quantity,
        unit_of_measure=UnitOfMeasure.EA,
        packaging_level=PackagingLevel.ITEM,
    )


def _make_record(start: int, end: int) -> MagicMock:
    record = MagicMock()
    record.__getitem__ = lambda self, key: {"start": start, "end": end}.get(key)
    return record


def _make_session(first_error=None, record=None) -> AsyncMock:
    session = AsyncMock()
    result = AsyncMock()
    result.single = AsyncMock(return_value=record)
    if first_error is not None:
        session.run = AsyncMock(side_effect=[first_error, result])
    else:
        session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestIsApocUnavailable:
    """Unit tests for the APOC-missing detector."""

    def test_procedure_not_found_code_is_apoc_missing(self):
        exc = Exception("Failed to invoke procedure")
        exc.code = "Neo.ClientError.Procedure.ProcedureNotFound"  # type: ignore[attr-defined]
        assert _is_apoc_unavailable(exc) is True

    def test_apoc_not_registered_message_is_apoc_missing(self):
        assert _is_apoc_unavailable(Exception(APOC_MISSING_MESSAGE)) is True

    def test_generic_database_error_is_not_apoc_missing(self):
        assert _is_apoc_unavailable(Exception("Database connection error")) is False

    def test_empty_result_runtime_error_is_not_apoc_missing(self):
        assert _is_apoc_unavailable(RuntimeError("Transaction returned no result")) is False


class TestReserveSerialRange:
    """The reservation helper must try the atomic counter, then fall back."""

    @pytest.mark.asyncio
    async def test_first_attempt_uses_apoc_atomic_counter(self):
        session = _make_session(record=_make_record(1, 10))
        record = await _reserve_serial_range(session, quantity=10)
        assert record["start"] == 1
        assert record["end"] == 10
        assert session.run.call_count == 1
        assert session.run.call_args[0][0] == ATOMIC_RESERVE_CYPHER
        assert "apoc.atomic.add" in session.run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_apoc_missing_falls_back_to_lock_ordered_query(self):
        session = _make_session(
            first_error=Exception(APOC_MISSING_MESSAGE),
            record=_make_record(11, 20),
        )
        record = await _reserve_serial_range(session, quantity=10)
        assert record["start"] == 11
        assert record["end"] == 20
        assert session.run.call_count == 2
        first_query = session.run.call_args_list[0][0][0]
        fallback_query = session.run.call_args_list[1][0][0]
        assert "apoc.atomic.add" in first_query
        assert fallback_query == LOCKED_RESERVE_CYPHER
        # The lock write must precede the counter read, otherwise the
        # fallback would race exactly like the old query did.
        lock_pos = fallback_query.index("SET l._serial_lock = timestamp()")
        read_pos = fallback_query.index("coalesce(l.next_serial, 1) AS start")
        assert lock_pos < read_pos
        assert "REMOVE l._serial_lock" in fallback_query

    @pytest.mark.asyncio
    async def test_non_apoc_error_is_not_retried(self):
        session = AsyncMock()
        session.run = AsyncMock(side_effect=Exception("Database connection error"))
        with pytest.raises(Exception, match="Database connection error"):
            await _reserve_serial_range(session, quantity=10)
        assert session.run.call_count == 1

    @pytest.mark.asyncio
    async def test_endpoint_serves_batch_via_fallback_without_apoc(self):
        """A deployment without APOC must still serve batches via fallback."""
        mock_neo4j = MagicMock()
        session = _make_session(
            first_error=Exception(APOC_MISSING_MESSAGE),
            record=_make_record(1, 10),
        )
        mock_neo4j.session = MagicMock(return_value=session)
        mock_neo4j.close = AsyncMock()
        mock_neo4j_class = MagicMock()
        mock_neo4j_class.return_value = mock_neo4j
        mock_neo4j_class.get_tenant_database_name = MagicMock(return_value="test-db")

        with patch("services.graph.app.routers.labels.Neo4jClient", mock_neo4j_class):
            response = await initialize_label_batch(
                request=_make_request(quantity=10),
                tenant_id=TEST_TENANT_ID,
                api_key="test-key",
            )

        assert session.run.call_count == 2
        assert response.reserved_range == {"start": 1, "end": 10}
        assert len(response.labels) == 10

    @pytest.mark.asyncio
    async def test_endpoint_still_returns_500_on_real_db_failure(self):
        mock_neo4j = MagicMock()
        session = AsyncMock()
        session.run = AsyncMock(side_effect=Exception("Database connection error"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_neo4j.session = MagicMock(return_value=session)
        mock_neo4j.close = AsyncMock()
        mock_neo4j_class = MagicMock()
        mock_neo4j_class.return_value = mock_neo4j
        mock_neo4j_class.get_tenant_database_name = MagicMock(return_value="test-db")

        with patch("services.graph.app.routers.labels.Neo4jClient", mock_neo4j_class):
            with pytest.raises(HTTPException) as exc_info:
                await initialize_label_batch(
                    request=_make_request(quantity=10),
                    tenant_id=TEST_TENANT_ID,
                    api_key="test-key",
                )

        assert exc_info.value.status_code == 500
        assert session.run.call_count == 1


class _FakeRecord:
    """Minimal record supporting record["start"] / record["end"]."""

    def __init__(self, start: int, end: int):
        self._data = {"start": start, "end": end}

    def __getitem__(self, key):
        return self._data[key]


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    """Emulates Neo4j locking for serial reservation queries.

    Queries that reserve through ``apoc.atomic.add`` or that take the
    Lot write lock first are executed while holding an exclusive lock,
    mirroring the server. A query with neither (the old fallback) reads
    the counter, yields to the event loop, then writes, so two
    concurrent reservations deterministically overlap.
    """

    def __init__(self, state, apoc_missing: bool = False):
        self._state = state
        self._apoc_missing = apoc_missing

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def run(self, query, **params):
        quantity = params["quantity"]
        if "apoc.atomic.add" in query:
            if self._apoc_missing:
                raise Exception(APOC_MISSING_MESSAGE)
            async with self._state["lock"]:
                start = self._state["next_serial"]
                self._state["next_serial"] = start + quantity
            return _FakeResult(_FakeRecord(start, start + quantity - 1))
        if "_serial_lock" in query:
            async with self._state["lock"]:
                start = self._state["next_serial"]
                self._state["next_serial"] = start + quantity
            return _FakeResult(_FakeRecord(start, start + quantity - 1))
        start = self._state["next_serial"]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self._state["next_serial"] = start + quantity
        return _FakeResult(_FakeRecord(start, start + quantity - 1))


def _make_fake_client_class(state, apoc_missing: bool = False):
    class _FakeNeo4jClient:
        def __init__(self, database=None):
            self.database = database

        @staticmethod
        def get_tenant_database_name(tenant_id):
            return "test-db"

        def session(self):
            return _FakeSession(state, apoc_missing=apoc_missing)

        async def close(self):
            return None

    return _FakeNeo4jClient


class TestConcurrentReservations:
    """Concurrent batches must receive disjoint serial ranges."""

    @pytest.mark.asyncio
    async def test_concurrent_batches_get_disjoint_ranges(self):
        state = {"next_serial": 1, "lock": asyncio.Lock()}
        fake_client_class = _make_fake_client_class(state)

        async def one_batch():
            with patch("services.graph.app.routers.labels.Neo4jClient", fake_client_class):
                return await initialize_label_batch(
                    request=_make_request(quantity=10),
                    tenant_id=TEST_TENANT_ID,
                    api_key="test-key",
                )

        first, second = await asyncio.gather(one_batch(), one_batch())

        first_ids = set(range(first.reserved_range["start"], first.reserved_range["end"] + 1))
        second_ids = set(range(second.reserved_range["start"], second.reserved_range["end"] + 1))
        assert len(first_ids) == 10
        assert len(second_ids) == 10
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_concurrent_batches_get_disjoint_ranges_without_apoc(self):
        state = {"next_serial": 1, "lock": asyncio.Lock()}
        fake_client_class = _make_fake_client_class(state, apoc_missing=True)

        async def one_batch():
            with patch("services.graph.app.routers.labels.Neo4jClient", fake_client_class):
                return await initialize_label_batch(
                    request=_make_request(quantity=10),
                    tenant_id=TEST_TENANT_ID,
                    api_key="test-key",
                )

        first, second = await asyncio.gather(one_batch(), one_batch())

        first_ids = set(range(first.reserved_range["start"], first.reserved_range["end"] + 1))
        second_ids = set(range(second.reserved_range["start"], second.reserved_range["end"] + 1))
        assert len(first_ids) == 10
        assert len(second_ids) == 10
        assert first_ids.isdisjoint(second_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
