"""Opt-in regressions against the disposable migrated local PostgreSQL stack.

Use REGENGINE_RECALL_TEST_DATABASE_URL=DATABASE_URL; all synthetic rows live
inside one outer transaction rolled back after each test. Runtime role only.
"""
import os
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import sla_tracking
from app.sla_tracking import CompletionEvidence, FDARequest, _persist_evidenced_completion
from shared.tenant_context import TenantContext, tenant_scope, set_tenant_guc

DATABASE = os.getenv('REGENGINE_RECALL_TEST_DATABASE_URL')
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not DATABASE, reason='Explicit disposable local PostgreSQL URL required')]

@pytest.fixture
def postgres(monkeypatch):
    import shared.database
    url = make_url(DATABASE)
    assert DATABASE == os.environ['DATABASE_URL']
    assert url.host in {'localhost', '127.0.0.1'} and url.username == 'regengine'
    assert url.database == 'regengine_cloud'  # cloud onboarding disposable stack
    tenant = str(uuid4())
    with tenant_scope(tenant), shared.database.engine.connect() as connection:
        outer = connection.begin()
        role = connection.execute(text('SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user')).one()
        assert role[0] == 'regengine' and not role[1] and not role[2]
        def session():
            return Session(bind=connection, join_transaction_mode='create_savepoint')
        monkeypatch.setattr(shared.database, 'SessionLocal', session)
        yield connection, session, tenant
        outer.rollback()
        for table in ('fda_sla_requests', 'fda_export_log', 'request_cases'):
            count = connection.execute(text(f'SELECT count(*) FROM fsma.{table} WHERE tenant_id=:tenant'), {'tenant':tenant}).scalar_one()
            assert count == 0  # no synthetic evidence survives the fixture
    sla_tracking._requests_store.clear()


def seed(connection, tenant):
    req = FDARequest(tenant_id=tenant)
    evidence = CompletionEvidence(export_hash='b'*64, start_date='2026-09-01', end_date='2026-10-01', completion_notes='Synthetic reviewed scope', acknowledged=True)
    artifact = str(uuid4())
    connection.execute(text("""INSERT INTO fsma.fda_sla_requests
        (id,tenant_id,request_type,status,requested_at,deadline_at) VALUES
        (:id,:tenant,'records_request','open',:received,:due)"""),
        {'id':req.id,'tenant':tenant,'received':req.requested_at,'due':req.deadline_at})
    connection.execute(text("""INSERT INTO fsma.fda_export_log
        (id,tenant_id,export_type,query_start_date,query_end_date,record_count,export_hash)
        VALUES (:id,:tenant,'fda_export_all','2026-09-01','2026-10-01',1,:hash)"""),
        {'id':artifact,'tenant':tenant,'hash':evidence.export_hash})
    return req, evidence, artifact


def test_postgres_cold_load_completion_and_replay(postgres):
    connection, session, tenant = postgres
    req, evidence, artifact = seed(connection, tenant)
    ctx = TenantContext(tenant,'jwt','synthetic-operator')
    sla_tracking._requests_store.clear()
    loaded = sla_tracking._try_load_requests(tenant)
    assert loaded and loaded[0].id == req.id and loaded[0].tenant_id == tenant
    sla_tracking._requests_store.clear()
    result = asyncio.run(sla_tracking.complete_request(req.id,evidence=evidence,ctx=ctx))
    assert result['request']['export_ids'] == [artifact]
    row = connection.execute(text('SELECT status,completed_at,notes FROM fsma.fda_sla_requests WHERE id=:id'),{'id':req.id}).one()
    assert row[0] == 'completed' and 'synthetic-operator' in row[2]
    sla_tracking._requests_store.clear()
    history = sla_tracking._try_load_requests(tenant)
    assert history[0].completed_at == row[1]
    sla_tracking._requests_store.clear()
    replay = asyncio.run(sla_tracking.complete_request(req.id,evidence=evidence,ctx=ctx))
    assert replay['request']['completed_at'] == row[1].isoformat()


def test_postgres_failed_commit_and_cross_tenant_evidence_leave_request_open(postgres, monkeypatch):
    import shared.database
    connection, session, tenant = postgres
    req,evidence,_ = seed(connection,tenant)
    ctx = TenantContext(tenant,'jwt','synthetic-operator')
    other = str(uuid4())
    set_tenant_guc(connection,other)
    connection.execute(text("""INSERT INTO fsma.fda_export_log
        (tenant_id,export_type,query_start_date,query_end_date,record_count,export_hash)
        VALUES (:other,'fda_export_all','2026-09-01','2026-10-01',1,:hash)"""), {'other':other,'hash':'c'*64})
    set_tenant_guc(connection,tenant)
    wrong = evidence.model_copy(update={'export_hash':'c'*64})
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(req,wrong,ctx)
    assert error.value.status_code == 409
    class FailedCommit(Session):
        def commit(self): raise RuntimeError('synthetic commit failure')
    monkeypatch.setattr(shared.database,'SessionLocal',lambda: FailedCommit(bind=connection,join_transaction_mode='create_savepoint'))
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(req,evidence,ctx)
    assert error.value.status_code == 503
    assert connection.execute(text('SELECT status FROM fsma.fda_sla_requests WHERE id=:id'),{'id':req.id}).scalar_one() == 'open'
    monkeypatch.setattr(shared.database,'SessionLocal',session)
    # Explicit query binding denies a different authenticated tenant even on
    # the same connection; the normal-role RLS transaction also stays scoped.
    with pytest.raises(HTTPException) as error: _persist_evidenced_completion(req,evidence,TenantContext(other,'jwt','other'))
    assert error.value.status_code == 409


def test_postgres_assemble_before_scope_can_recover_ready_and_submit(postgres):
    from shared.request_workflow import RequestWorkflow
    connection, session, tenant = postgres
    case_id = str(uuid4())
    connection.execute(text("""INSERT INTO fsma.request_cases
        (request_case_id,tenant_id,response_due_at,requesting_party,scope_type,affected_lots,package_status)
        VALUES (:id,:tenant,:due,'Synthetic FDA','tlc_trace',ARRAY['UNMATCHED-SYNTHETIC-LOT'],'gap_analysis')"""),
        {'id':case_id,'tenant':tenant,'due':datetime.now(timezone.utc)+timedelta(hours=24)})
    with session() as db:
        workflow = RequestWorkflow(db)
        package = workflow.assemble_response_package(tenant,case_id,generated_by='synthetic-operator')
        workflow.add_signoff(tenant,case_id,'package_review',signed_by='synthetic-reviewer')
        workflow.add_signoff(tenant,case_id,'final_approval',signed_by='synthetic-approver')
        blockers = workflow.check_blocking_defects(tenant,case_id)
        assert any(item.get('signoff_type') == 'scope_approval' for item in blockers['blockers'])
        recovered = workflow.add_signoff(tenant,case_id,'scope_approval',signed_by='synthetic-scope-reviewer',notes='Recovered missing scope approval')
        assert recovered['case_status'] == 'ready'
        assert workflow.check_blocking_defects(tenant,case_id)['can_submit']
        workflow.submit_package(tenant,case_id,str(package['package_id']),submitted_by='synthetic-operator',submission_method='export')
        assert workflow.get_case_detail(tenant,case_id)['package_status'] == 'submitted'
