"""Status mapping tests for ``CanonicalEventStore`` ingestion runs.

Covers the ingestion-run management surface of
``shared.canonical_persistence.writer`` (``create_ingestion_run`` and
``complete_ingestion_run``) with a mocked session, so no live Postgres
is needed:

1. ``create_ingestion_run`` returns the run id and binds the INSERT.
2. ``complete_ingestion_run`` reports ``completed`` when nothing was rejected.
3. ``complete_ingestion_run`` reports ``partial`` when anything was rejected
   (edge: a run with any rejection must never read as fully completed).
4. ``complete_ingestion_run`` serializes the errors list as JSON.
5. ``complete_ingestion_run`` raises ``ValueError`` when no row matches
   (error: unknown run id, or a run id owned by another tenant).
6. ``complete_ingestion_run`` rejects a non-UUID tenant before any UPDATE
   (error: fail loud instead of binding an RLS-breaking GUC value).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from shared.canonical_event import IngestionRun, IngestionSource
from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import FakeSession, _FakeResult


class _UpdateResult(_FakeResult):
    """``_FakeResult`` carrying a ``rowcount`` for the UPDATE path."""

    def __init__(self, rowcount: int = 1):
        super().__init__()
        self.rowcount = rowcount


def _make_run(**overrides):
    """Build a minimal ``IngestionRun`` with a fresh UUID tenant by default."""
    fields = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        source_system=IngestionSource.CSV_UPLOAD,
        source_file_name="upload.csv",
        source_file_hash="f" * 64,
        source_file_size=256,
        record_count=4,
        mapper_version="2.3.1",
        schema_version="1.0.0",
        status="processing",
        initiated_by="qa-test",
    )
    fields.update(overrides)
    return IngestionRun(**fields)


def _new_store(session: FakeSession) -> CanonicalEventStore:
    return CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)


def _single_update_params(session: FakeSession):
    updates = [(sql, params) for sql, params in session.calls if "UPDATE fsma.ingestion_runs" in sql]
    assert updates, "complete_ingestion_run must issue an UPDATE"
    assert len(updates) == 1, "complete_ingestion_run must issue exactly one UPDATE"
    return updates[0][1]


class TestCreateIngestionRun:
    def test_returns_run_id_as_string(self):
        session = FakeSession()
        store = _new_store(session)
        run = _make_run()

        assert store.create_ingestion_run(run) == str(run.id)

    def test_insert_binds_run_fields(self):
        session = FakeSession()
        store = _new_store(session)
        run = _make_run(record_count=4)

        store.create_ingestion_run(run)

        inserts = [(sql, params) for sql, params in session.calls if "INSERT INTO fsma.ingestion_runs" in sql]
        assert inserts, "create_ingestion_run must issue an INSERT"
        _, params = inserts[0]
        assert params["id"] == str(run.id)
        assert params["tenant_id"] == str(run.tenant_id)
        assert params["source_system"] == IngestionSource.CSV_UPLOAD.value
        assert params["status"] == "processing"
        assert params["record_count"] == 4
        assert params["mapper_version"] == "2.3.1"


class TestCompleteIngestionRunStatus:
    def test_all_accepted_marks_completed(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=1))
        store = _new_store(session)
        tenant_id = str(uuid4())

        store.complete_ingestion_run(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            accepted=10,
            rejected=0,
        )

        assert _single_update_params(session)["status"] == "completed"

    def test_any_rejection_marks_partial(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=1))
        store = _new_store(session)
        tenant_id = str(uuid4())

        store.complete_ingestion_run(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            accepted=9,
            rejected=1,
        )

        assert _single_update_params(session)["status"] == "partial"

    def test_counts_are_bound_on_update(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=1))
        store = _new_store(session)
        run_id, tenant_id = str(uuid4()), str(uuid4())

        store.complete_ingestion_run(run_id=run_id, tenant_id=tenant_id, accepted=7, rejected=3)

        params = _single_update_params(session)
        assert params["id"] == run_id
        assert params["tenant_id"] == tenant_id
        assert params["accepted"] == 7
        assert params["rejected"] == 3

    def test_errors_list_is_serialized_as_json(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=1))
        store = _new_store(session)
        errors = [{"row": 2, "reason": "missing lot code"}]

        store.complete_ingestion_run(
            run_id=str(uuid4()),
            tenant_id=str(uuid4()),
            accepted=3,
            rejected=1,
            errors=errors,
        )

        assert json.loads(_single_update_params(session)["errors"]) == errors

    def test_missing_errors_defaults_to_empty_json_list(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=1))
        store = _new_store(session)

        store.complete_ingestion_run(
            run_id=str(uuid4()),
            tenant_id=str(uuid4()),
            accepted=4,
            rejected=0,
        )

        assert _single_update_params(session)["errors"] == "[]"


class TestCompleteIngestionRunErrors:
    def test_no_matching_row_raises_value_error(self):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _UpdateResult(rowcount=0))
        store = _new_store(session)

        with pytest.raises(ValueError, match="no run matched"):
            store.complete_ingestion_run(
                run_id=str(uuid4()),
                tenant_id=str(uuid4()),
                accepted=1,
                rejected=0,
            )

    def test_non_uuid_tenant_raises_before_any_update(self):
        session = FakeSession()
        store = _new_store(session)

        with pytest.raises(ValueError):
            store.complete_ingestion_run(
                run_id=str(uuid4()),
                tenant_id="not-a-uuid",
                accepted=1,
                rejected=0,
            )

        assert not [sql for sql, _ in session.calls if "UPDATE fsma.ingestion_runs" in sql], (
            "invalid tenant must fail before the UPDATE runs"
        )
