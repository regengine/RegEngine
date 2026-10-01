"""Completion commits only tenant-scoped durable export evidence."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app.sla_tracking import FDARequest, CompletionEvidence, _persist_evidenced_completion
from shared.tenant_context import TenantContext

HASH = 'a' * 64
CTX = TenantContext('tenant-1', 'jwt', 'operator-1')
EVIDENCE = CompletionEvidence(export_hash=HASH, start_date='2026-09-01', end_date='2026-10-01', completion_notes='Reviewed request scope', acknowledged=True)

@pytest.fixture
def db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr('shared.database.SessionLocal', lambda: db)
    return db

def stored():
    return {'status':'open', 'completed_at':None, 'export_ids':None, 'notes':'Original request'}

def result(row):
    obj = MagicMock(); obj.mappings.return_value.first.return_value = row; return obj

def req():
    return FDARequest(tenant_id='tenant-1')

def test_commit_records_artifact_dates_actor_and_attestation(db):
    db.execute.side_effect = [result(stored()), result({'id':'export-1'}), MagicMock()]
    completed = _persist_evidenced_completion(req(), EVIDENCE, CTX)
    assert completed.status == 'completed'
    assert completed.export_ids == ['export-1']
    assert 'operator-1' in completed.notes and HASH in completed.notes and '2026-09-01' in completed.notes
    query, params = db.execute.call_args_list[1].args
    assert params['tenant_id'] == CTX.tenant_id and params['hash'] == HASH
    assert "record_count > 0" in str(query) and "export_type = 'fda_export_all'" in str(query)
    db.commit.assert_called_once()

@pytest.mark.parametrize('artifact', [None])
def test_unknown_hash_or_wrong_tenant_does_not_close(db, artifact):
    original = req(); db.execute.side_effect = [result(stored()), result(artifact)]
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(original, EVIDENCE, CTX)
    assert error.value.status_code == 409
    assert original.status == 'open'
    db.commit.assert_not_called()

def test_commit_failure_leaves_request_open(db):
    original = req(); db.execute.side_effect = [result(stored()), result({'id':'export-1'}), MagicMock()]
    db.commit.side_effect = RuntimeError('unavailable')
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(original, EVIDENCE, CTX)
    assert error.value.status_code == 503 and original.status == 'open'
    db.rollback.assert_called_once()

def test_repeat_does_not_rewrite_completion_time(db):
    time = datetime(2026, 9, 30, tzinfo=timezone.utc)
    row = stored(); row.update(status='completed', completed_at=time, export_ids='export-1')
    db.execute.return_value = result(row)
    completed = _persist_evidenced_completion(req(), EVIDENCE, CTX)
    assert completed.completed_at == time
    assert db.execute.call_count == 1
    db.commit.assert_not_called()

def test_no_attestation_or_missing_durable_request_never_completes(db):
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(req(), EVIDENCE.model_copy(update={'acknowledged':False}), CTX)
    assert error.value.status_code == 422
    db.execute.assert_not_called()
    db.execute.return_value = result(None)
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(req(), EVIDENCE, CTX)
    assert error.value.status_code == 409
    db.commit.assert_not_called()


def test_cold_worker_loads_driver_uuid_history_and_completion_replay(monkeypatch):
    from types import SimpleNamespace
    from uuid import UUID
    from app import sla_tracking
    request_id, tenant_id = UUID('11111111-1111-4111-8111-111111111111'), UUID('22222222-2222-4222-8222-222222222222')
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(id=request_id, tenant_id=tenant_id, request_type='records_request',
        requested_at=now, deadline_at=now, status='completed', completed_at=now, export_ids='export-1', notes='attested')
    db = MagicMock(); db.execute.return_value.fetchall.return_value = [row]
    monkeypatch.setattr('shared.database.SessionLocal', lambda: db)
    sla_tracking._requests_store.clear()
    loaded = sla_tracking._try_load_requests(str(tenant_id))
    assert loaded is not None and loaded[0].id == str(request_id)
    assert loaded[0].tenant_id == str(tenant_id)
    assert loaded[0].status == 'completed' and loaded[0].export_ids == ['export-1']
    assert str(request_id) in sla_tracking._requests_store
    sla_tracking._requests_store.clear()
    monkeypatch.setattr(sla_tracking, '_persist_evidenced_completion', lambda req, evidence, ctx: req)
    import asyncio
    replay = asyncio.run(sla_tracking.complete_request(str(request_id), evidence=EVIDENCE, ctx=TenantContext(str(tenant_id),'jwt','operator')))
    assert replay['request']['status'] == 'completed'
    assert replay['request']['completed_at'] == now.isoformat()
