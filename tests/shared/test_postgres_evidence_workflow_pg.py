"""Real migrated PostgreSQL regressions; opt in with an owned scratch cluster.

REGENGINE_EVIDENCE_TEST_DATABASE_URL must also be DATABASE_URL and use the
regengine runtime role. Only the local measurement runner's private Unix
socket or the explicitly designated CI live_suite database is accepted.
"""

import copy
import hashlib
import importlib.util
import json
import os
import socket
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[2]
DATABASE = os.getenv("REGENGINE_EVIDENCE_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE, reason="Explicit disposable PostgreSQL required"),
]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workflow(monkeypatch):
    url = make_url(DATABASE)
    assert DATABASE == os.environ["DATABASE_URL"]
    assert url.username == "regengine"
    if url.host:
        # The CI job provisions this isolated service database. Never reuse a
        # developer or hosted database just because credentials are available.
        assert os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
        assert url.host in {"localhost", "127.0.0.1"} and url.port == 5432 and url.database == "live_suite"
        admin_url = make_url(os.environ["REGENGINE_EVIDENCE_ADMIN_DATABASE_URL"])
        assert (admin_url.host, admin_url.port, admin_url.database) == (url.host, url.port, url.database)
        assert admin_url.username == "postgres"
        admin_connect = dict(
            dbname=url.database, user=admin_url.username, password=admin_url.password, host=url.host, port=url.port
        )
    else:
        assert url.database.startswith("ue_") and url.query["host"].startswith("/tmp/regengine-ue-pg-")
        admin_connect = dict(
            dbname=url.database, user="ue_cluster_admin", host=url.query["host"], port=url.query["port"]
        )
    connect = socket.socket.connect

    def unix_only(sock, address):
        if sock.family != socket.AF_UNIX:
            raise OSError("External network disabled in PostgreSQL regression")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", unix_only)
    proof = _load("pg_evidence_proof", ROOT / "scripts/verify_inflow_to_regengine_e2e.py")
    proof._configure_paths()
    admin = psycopg.connect(**admin_connect)
    admin.autocommit = True
    tenant, other = str(uuid4()), str(uuid4())
    with admin.cursor() as cur:
        for tid in (tenant, other):
            cur.execute(
                "INSERT INTO public.tenants(id,name,slug,status) VALUES (%s,%s,%s,'active')",
                (tid, "Synthetic PostgreSQL regression", f"pg-test-{tid}"),
            )
    client = proof._build_app(tenant)
    headers = proof._auth_headers(SimpleNamespace(api_key=os.environ["API_KEY"]), tenant)
    start = datetime.now(timezone.utc).date() - timedelta(days=2)
    end = start + timedelta(days=1)
    template = json.loads(
        json.dumps(proof._events_from_csv()).replace("2026-04-26", str(start)).replace("2026-04-27", str(end))
    )

    def events(count):
        result = []
        for lot in range(count // 5):
            for original in template:
                event = copy.deepcopy(original)
                event["traceability_lot_code"] = f"PG-REGRESSION-{lot}"
                result.append(event)
        return result

    def post(values, claimed_tenant=tenant):
        return proof._post_json(
            client,
            "/api/v1/webhooks/ingest",
            {"tenant_id": claimed_tenant, "source": "pg-evidence-regression", "events": values},
            headers,
        )

    def query(statement, tid=tenant):
        from shared.database import SessionLocal
        from shared.tenant_context import set_tenant_guc

        with SessionLocal() as db:
            set_tenant_guc(db, tid)
            return db.execute(text(statement)).fetchall()

    def package(*, legacy=False):
        endpoint = "/api/v1/fda/export/all" if legacy else "/api/v1/fda/export/v2"
        return client.get(
            f"{endpoint}?tenant_id={tenant}&start_date={start}&end_date={end}&format=package",
            headers=headers,
        )

    yield SimpleNamespace(
        proof=proof,
        client=client,
        headers=headers,
        admin=admin,
        tenant=tenant,
        other=other,
        events=events,
        post=post,
        query=query,
        package=package,
    )
    client.close()
    admin.close()


def _assert_package(workflow, tmp_path, *, verified, legacy=False):
    response = workflow.package(legacy=legacy)
    assert response.status_code == 200, response.text[:300]
    expected_status = "VERIFIED" if verified else "UNVERIFIED"
    assert response.headers["X-Chain-Integrity"] == expected_status
    path = tmp_path / ("legacy-package.zip" if legacy else "package.zip")
    path.write_bytes(response.content)
    with zipfile.ZipFile(path) as package:
        manifest = json.loads(package.read("manifest.json"))
        chain_name = next(name for name in package.namelist() if name.startswith("chain_verification_"))
        chain_payload = json.loads(package.read(chain_name))
    assert manifest["verification"]["status"] == expected_status
    assert chain_payload["verification_status"] == expected_status
    assert chain_payload["chain_verification"]["valid"] is verified
    if not legacy:
        assert response.headers["X-Export-Version"] == "2.0"
        assert chain_payload["data_source"] == "fsma.traceability_events (canonical model)"
        assert chain_payload["provenance"]["source_table"] == "fsma.traceability_events"
    verifier = _load("pg_evidence_verifier", ROOT / "frontend/public/sdk/verify_chain.py")
    assert verifier.verify_bundle(str(path)) == (0 if verified else 1)
    return chain_payload


def test_full_500_event_request_retry_alerts_and_verified_export(workflow, tmp_path):
    w = workflow
    roles = w.query(
        "SELECT current_user, rolsuper, rolbypassrls, has_any_column_privilege(current_user,'fsma.hash_chain','UPDATE') FROM pg_roles WHERE rolname=current_user"
    )[0]
    assert tuple(roles) == ("regengine", False, False, False)
    response = w.post(w.events(500))
    assert response.status_code == 200, response.text[:1000]
    assert response.json()["accepted"] == 500 and response.json()["rejected"] == 0
    assert w.query("SELECT COUNT(*) FROM fsma.cte_events")[0][0] == 500
    assert w.query("SELECT COUNT(*) FROM fsma.traceability_events")[0][0] == 500
    assert w.query("SELECT COUNT(*) FROM fsma.hash_chain")[0][0] == 500
    assert w.query("SELECT COUNT(*) FROM fsma.compliance_alerts")[0][0] == 100
    assert (
        w.query("SELECT COUNT(*) FROM fsma.compliance_alerts WHERE cte_event_id IS DISTINCT FROM event_id")[0][0] == 0
    )
    assert (
        w.query("""SELECT COUNT(*) FROM fsma.traceability_events t
          JOIN fsma.cte_events e ON e.id=t.event_id AND e.tenant_id=t.tenant_id
          JOIN fsma.hash_chain h ON h.cte_event_id=t.event_id AND h.tenant_id=t.tenant_id
          WHERE t.sha256_hash<>h.event_hash OR e.sha256_hash<>h.event_hash
             OR t.chain_hash<>h.chain_hash OR e.chain_hash<>h.chain_hash""")[0][0]
        == 0
    )
    retry = w.post(w.events(500))
    assert retry.status_code == 200
    assert retry.json()["events"] == response.json()["events"]
    assert w.query("SELECT COUNT(*) FROM fsma.hash_chain")[0][0] == 500
    assert w.query("SELECT COUNT(*) FROM fsma.compliance_alerts")[0][0] == 100
    _assert_package(w, tmp_path, verified=True)
    legacy = _assert_package(w, tmp_path, verified=False, legacy=True)
    assert legacy["record_count"] == 500
    assert legacy["row_hash_coverage"] == {
        "records_with_hash": 500,
        "records_with_chain_hash": 500,
        "missing_record_hashes": 0,
        "missing_chain_hashes": 0,
    }
    assert legacy["chain_verification"]["errors"] == [
        "Exported content was not independently verified for this source; chain diagnostics alone are insufficient."
    ]


def test_concurrent_replays_keep_one_event_and_chain_population(workflow, tmp_path):
    w = workflow
    ready = Barrier(2)

    def submit(_):
        ready.wait(timeout=10)
        return w.post(w.events(5))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert all(r.status_code == 200 and r.json()["accepted"] == 5 for r in responses)
    assert responses[0].json()["events"] == responses[1].json()["events"]
    assert w.query("SELECT COUNT(*) FROM fsma.cte_events")[0][0] == 5
    assert w.query("SELECT COUNT(*) FROM fsma.hash_chain")[0][0] == 5
    _assert_package(w, tmp_path, verified=True)


def test_tenant_obligation_alert_is_durable_without_rejecting_event(workflow, tmp_path):
    w = workflow
    with w.admin.cursor() as cur:
        cur.execute(
            "INSERT INTO public.obligations(tenant_id,obligation_text,risk_category) VALUES (%s,%s,'CRITICAL') RETURNING id",
            (w.tenant, "Synthetic required field"),
        )
        obligation = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO public.obligation_cte_rules(obligation_id,cte_type,required_kde_key,validation_rule)
                       VALUES (%s,'harvesting','synthetic_missing_kde','present')""",
            (obligation,),
        )
    response = w.post(w.events(5))
    assert response.status_code == 200 and response.json()["accepted"] == 5
    alerts = w.query(
        "SELECT cte_event_id,event_id,details FROM fsma.compliance_alerts WHERE alert_type='chain_break' AND severity='critical'"
    )
    assert len(alerts) == 1 and alerts[0][0] == alerts[0][1]
    assert alerts[0][2]["obligation_id"] == str(obligation)
    _assert_package(w, tmp_path, verified=True)


def test_single_event_fallback_preserves_canonical_hash_and_alerts(workflow, tmp_path, monkeypatch):
    from shared.cte_persistence import CTEPersistence

    def unavailable_batch(*args, **kwargs):
        raise RuntimeError("Synthetic batch failure to exercise per-event recovery")

    monkeypatch.setattr(CTEPersistence, "store_events_batch", unavailable_batch)
    response = workflow.post(workflow.events(5))
    assert response.status_code == 200 and response.json()["accepted"] == 5
    assert workflow.query("SELECT COUNT(*) FROM fsma.compliance_alerts")[0][0] == 1
    assert workflow.query("SELECT COUNT(*) FROM fsma.hash_chain")[0][0] == 5
    _assert_package(workflow, tmp_path, verified=True)


@pytest.mark.parametrize("column", ["quantity", "event_timestamp"])
def test_canonical_content_tampering_is_rejected(workflow, tmp_path, column):
    w = workflow
    assert w.post(w.events(5)).status_code == 200
    _assert_package(w, tmp_path, verified=True)
    # Simulate corruption by a cluster administrator; runtime ACLs stay intact.
    expression = "quantity + 0.25" if column == "quantity" else "event_timestamp + interval '1 minute'"
    with w.admin.cursor() as cur:
        cur.execute(f"UPDATE fsma.traceability_events SET {column}={expression} WHERE tenant_id=%s", (w.tenant,))
    _assert_package(w, tmp_path, verified=False)


def test_runtime_tenant_and_input_boundaries(workflow):
    from shared.database import SessionLocal

    w = workflow
    assert w.post(w.events(5)).status_code == 200
    for table in ("fsma.cte_events", "fsma.traceability_events", "fsma.hash_chain"):
        assert w.query(f"SELECT COUNT(*) FROM {table}", w.other)[0][0] == 0
        with SessionLocal() as db, pytest.raises(Exception, match="tenant context required"):
            db.execute(text(f"SELECT COUNT(*) FROM {table}"))
    mismatch = w.post(w.events(5), w.other)
    assert mismatch.status_code == 409 and mismatch.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    invalid = w.events(5)
    invalid[0]["quantity"] = "invalid-number"
    assert w.post(invalid).status_code == 422
    denied = w.client.post(
        "/api/v1/webhooks/ingest",
        json={"tenant_id": w.tenant, "events": w.events(5)},
        headers={
            **w.headers,
            "X-Webhook-Signature": "sha256=" + "0" * 64,
            "Idempotency-Key": "invalid-signature-regression",
        },
    )
    assert denied.status_code == 401
    assert w.query("SELECT COUNT(*) FROM fsma.hash_chain")[0][0] == 5


def test_canonical_single_and_batch_writers_need_no_chain_update_privilege(workflow):
    from app.webhook_models import IngestEvent
    from shared.canonical_event import normalize_webhook_event
    from shared.canonical_persistence import CanonicalEventStore
    from shared.database import SessionLocal

    events = [normalize_webhook_event(IngestEvent(**e), workflow.tenant) for e in workflow.events(5)]
    with SessionLocal() as db:
        store = CanonicalEventStore(db, dual_write=True)
        assert store.persist_event(events[0]).success
        assert all(r.success for r in store.persist_events_batch(events[1:]))
        db.commit()
        store.set_tenant_context(workflow.tenant)
        assert store.verify_chain_canonical(workflow.tenant).valid


# ---------------------------------------------------------------------------
# POST /api/v1/ingest/csv retains the upload in fsma.manifest_blobs (#3122),
# and the agent-artifact worker writes fsma.agent_artifacts plus a
# needs_review receipt. Both ran as the restricted role without the grants
# they need (v126), so every upload 500'd and every artifact task failed.
# Jev is answered by an in-process mock transport; nothing leaves the host.
# ---------------------------------------------------------------------------

_JEV_ANSWERS = {
    "Lot #": {
        "type": "choice",
        "choice": "traceability_lot_code",
        "confidence": 0.97,
        "probabilities": {"traceability_lot_code": 0.97, "no_match": 0.03},
    },
    "Shipped On": {
        "type": "choice",
        "choice": "ship_date",
        "confidence": 0.8,
        "probabilities": {"ship_date": 0.8, "no_match": 0.2},
    },
}


@pytest.fixture
def production_search_path():
    """Runtime connections get the server-default search_path, as in production.

    CI's job-level PGOPTIONS puts fsma and extensions on every connection,
    which would hide an unqualified pgcrypto call behind wherever the
    migrations happened to install the extension. The pool is dropped on
    both sides so no other test inherits or leaks the setting.
    """
    from shared.database import engine
    from sqlalchemy import event

    def pin(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute('SET search_path TO "$user", public')
        cursor.close()
        dbapi_connection.commit()

    engine.dispose()
    event.listen(engine, "connect", pin)
    try:
        yield '"$user", public'
    finally:
        event.remove(engine, "connect", pin)
        engine.dispose()


def _offline_jev_decider():
    import httpx2
    from shared.jev import JevDecider, JevSettings

    def answer(request):
        body = json.loads(request.content)
        columns = body["state"]["columns_to_map"]
        answers = {qid: _JEV_ANSWERS[columns[int(qid.split("_")[1])]["header"]] for qid in body["questions"]}
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_pg_regression"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 1}},
        )

    settings = JevSettings(api_key="offline-synthetic", max_retries=0, timeout_seconds=1.0)
    return JevDecider(settings, transport=httpx2.MockTransport(answer))


def _upload_csv(monkeypatch, tenant):
    """Drive the real CSV route; only the API-key lookup and Jev HTTP are stubbed."""
    from app import csv_templates
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(csv_templates, "get_jev_decider", _offline_jev_decider)
    app = FastAPI()
    app.include_router(csv_templates.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="pg-csv-regression", scopes=["*"], tenant_id=tenant
    )
    day = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    body = (
        "Lot #,tlc,Shipped On,product_description,quantity,unit_of_measure,harvest_date,location_name,"
        "reference_document\n"
        f"LOT-1,PG-CSV-{tenant[:8]}-1,{day},Kale,10,lbs,{day},Farm A,REF-1\n"
        f"LOT-2,PG-CSV-{tenant[:8]}-2,{day},Chard,5,lbs,{day},Farm A,REF-2\n"
    ).encode()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("supplier.csv", body, "text/csv")},
            data={"cte_type": "harvesting"},
            headers={"X-RegEngine-API-Key": os.environ["API_KEY"], "X-Tenant-ID": tenant},
        )
    assert response.status_code == 200, response.text[:1000]
    return response.json(), body


def _run_queued_agent_tasks(workflow, tenant):
    """Hand every queued artifact task to the real TaskWorker handler (runtime role)."""
    from shared.agent_task_bridge import AGENT_ARTIFACT_TASK_TYPE, handle_agent_artifact_task

    rows = workflow.query(
        f"SELECT payload FROM fsma.task_queue WHERE task_type = '{AGENT_ARTIFACT_TASK_TYPE}' ORDER BY id", tenant
    )
    payloads = [row[0] for row in rows]
    for payload in payloads:
        handle_agent_artifact_task(**payload)
    return payloads


def test_csv_upload_and_agent_worker_persist_as_runtime_role(workflow, monkeypatch, production_search_path):
    from shared.agent_task_bridge import handle_agent_artifact_task

    w = workflow
    assert w.query("SHOW search_path")[0][0] == production_search_path
    result, body = _upload_csv(monkeypatch, w.tenant)
    run_id = result["ingestion_run_id"]
    assert run_id and result["accepted"] == 2 and result["rejected"] == 0
    assert result["header_mapping_engine"]["artifacts_recorded"] == 2
    sha256 = hashlib.sha256(body).hexdigest()
    assert [
        tuple(r)
        for r in w.query(f"SELECT source_file_hash, record_count FROM fsma.ingestion_runs WHERE id = '{run_id}'")
    ] == [(sha256, 2)]
    assert w.query(f"SELECT COUNT(*) FROM fsma.traceability_events WHERE ingestion_run_id = '{run_id}'")[0][0] == 2
    with w.admin.cursor() as cur:
        # INSERT-only: the runtime role retains the upload but cannot read it back.
        cur.execute(
            "SELECT tenant_id::text, sha256, raw_bytes FROM fsma.manifest_blobs WHERE ingestion_run_id = %s", (run_id,)
        )
        assert [(t, s, bytes(b)) for t, s, b in cur.fetchall()] == [(w.tenant, sha256, body)]

    payloads = _run_queued_agent_tasks(w, w.tenant)
    assert len(payloads) == 2
    # Redelivery is a no-op: ON CONFLICT (artifact_id, tenant_id) keeps one
    # artifact and, since nothing was inserted, no second receipt is appended.
    for payload in payloads:
        handle_agent_artifact_task(**payload)
    with w.admin.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*), bool_and(artifact_hash = fsma.compute_agent_artifact_hash(artifact)),
                      bool_and(requires_human_review)
                 FROM fsma.agent_artifacts WHERE tenant_id = %s AND ingestion_run_id = %s""",
            (w.tenant, run_id),
        )
        assert cur.fetchone() == (2, True, True)
        cur.execute(
            """SELECT sequence_num, state, previous_receipt_hash, receipt_hash,
                      receipt_hash = fsma.compute_ingestion_run_receipt_hash(
                          tenant_id, ingestion_run_id, sequence_num, state, occurred_at, actor, request_id,
                          canonical_event_id, evidence_attachment_id, rule_evaluation_id, export_log_id,
                          payload_hash, previous_receipt_hash)
                 FROM fsma.ingestion_run_receipts
                WHERE tenant_id = %s AND ingestion_run_id = %s ORDER BY sequence_num""",
            (w.tenant, run_id),
        )
        receipts = cur.fetchall()
    assert [r[0] for r in receipts] == [1, 2]
    assert {r[1] for r in receipts} == {"needs_review"} and all(r[4] for r in receipts)
    assert [r[2] for r in receipts] == [None, receipts[0][3]]


def test_first_receipt_appends_to_one_run_serialize(workflow, monkeypatch, production_search_path):
    from shared.agent_task_bridge import append_agent_artifact_receipt, persist_agent_artifact
    from shared.database import SessionLocal
    from shared.tenant_context import set_tenant_guc

    w = workflow
    run_id = _upload_csv(monkeypatch, w.tenant)[0]["ingestion_run_id"]
    first_payload, second_payload = (
        row[0]
        for row in w.query(
            f"SELECT payload FROM fsma.task_queue WHERE payload->>'ingestion_run_id' = '{run_id}' ORDER BY id"
        )
    )

    def append(db, payload):
        set_tenant_guc(db, w.tenant)
        persist_agent_artifact(db, payload)
        return append_agent_artifact_receipt(db, payload)

    def runtime_backend_waiting_on_lock():
        with w.admin.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM pg_stat_activity
                    WHERE datname = current_database() AND usename = 'regengine' AND wait_event_type = 'Lock'"""
            )
            return cur.fetchone()[0] > 0

    # The run's first append holds the parent-run lock uncommitted. The second
    # must wait for it and chain on as sequence 2; locking the latest receipt
    # (v079) had no row to lock here, so both took sequence 1 and one failed
    # on the unique key.
    with SessionLocal() as first, SessionLocal() as second, ThreadPoolExecutor(max_workers=1) as pool:
        append(first, first_payload)
        pending = pool.submit(append, second, second_payload)
        deadline = time.monotonic() + 10
        while not runtime_backend_waiting_on_lock():
            assert not pending.done() and time.monotonic() < deadline, "second append never waited"
            time.sleep(0.05)
        first.commit()
        assert pending.result(timeout=10).ledger_state == "needs_review"
        second.commit()
    with w.admin.cursor() as cur:
        cur.execute(
            """SELECT sequence_num, previous_receipt_hash, receipt_hash FROM fsma.ingestion_run_receipts
                WHERE ingestion_run_id = %s ORDER BY sequence_num""",
            (run_id,),
        )
        receipts = cur.fetchall()
    assert [r[0] for r in receipts] == [1, 2] and receipts[1][1] == receipts[0][2]


def test_runtime_ingest_evidence_grants_stay_tenant_isolated(workflow, monkeypatch, production_search_path):
    from shared.agent_task_bridge import append_agent_artifact_receipt, persist_agent_artifact
    from shared.database import SessionLocal
    from shared.tenant_context import set_tenant_guc

    w = workflow
    other_run = _upload_csv(monkeypatch, w.other)[0]["ingestion_run_id"]
    other_payload = _run_queued_agent_tasks(w, w.other)[0]
    own_run = _upload_csv(monkeypatch, w.tenant)[0]["ingestion_run_id"]
    own_payload = _run_queued_agent_tasks(w, w.tenant)[0]
    with w.admin.cursor() as cur:
        # Another tenant's run that has no blob yet: only the composite
        # (ingestion_run_id, tenant_id) key stops a blob from attaching to it.
        cur.execute(
            "INSERT INTO fsma.ingestion_runs (tenant_id, source_system) VALUES (%s, 'csv_upload') RETURNING id",
            (w.other,),
        )
        other_blobless_run = str(cur.fetchone()[0])

    # The narrow SELECT grants still pass through RLS: the other tenant's rows are invisible.
    assert (
        w.query(f"SELECT artifact_id FROM fsma.agent_artifacts WHERE artifact_id = '{other_payload['artifact_id']}'")
        == []
    )
    assert w.query(f"SELECT receipt_id FROM fsma.ingestion_run_receipts WHERE ingestion_run_id = '{other_run}'") == []
    assert len(w.query("SELECT artifact_id FROM fsma.agent_artifacts")) == 2

    def rejected(match, statement, params=None, call=None):
        with SessionLocal() as db:
            set_tenant_guc(db, w.tenant)
            with pytest.raises(DBAPIError, match=match):
                call(db) if call else db.execute(text(statement), params or {})

    for statement in (
        "SELECT COUNT(*) FROM fsma.manifest_blobs",
        "SELECT artifact FROM fsma.agent_artifacts",
        "SELECT metadata FROM fsma.ingestion_run_receipts",
        "UPDATE fsma.manifest_blobs SET storage_url = 'x'",
        "UPDATE fsma.agent_artifacts SET suggestion = 'x'",
        "UPDATE fsma.ingestion_run_receipts SET actor = 'x'",
        "DELETE FROM fsma.manifest_blobs",
        "DELETE FROM fsma.agent_artifacts",
        "DELETE FROM fsma.ingestion_run_receipts",
    ):
        rejected("permission denied", statement)
    blob_insert = """INSERT INTO fsma.manifest_blobs (ingestion_run_id, tenant_id, raw_bytes, sha256, original_filename)
           VALUES (CAST(:run AS uuid), CAST(:tenant AS uuid), '\\x00', :sha, 'forged.csv')"""
    rejected("row-level security", blob_insert, {"run": other_run, "tenant": w.other, "sha": "0" * 64})
    # Own tenant id on another tenant's run passes the tenant policy; the
    # composite foreign key rejects it.
    rejected(
        "fk_manifest_blobs_run_tenant",
        blob_insert,
        {"run": other_blobless_run, "tenant": w.tenant, "sha": "0" * 64},
    )
    # INSERT is column-scoped: retention metadata cannot be forged.
    for forged_column, forged_value in (("storage_url", "https://attacker.example/x"), ("created_at", "1990-01-01")):
        rejected(
            "permission denied",
            f"""INSERT INTO fsma.manifest_blobs
                    (ingestion_run_id, tenant_id, raw_bytes, sha256, original_filename, {forged_column})
                VALUES (CAST(:run AS uuid), CAST(:tenant AS uuid), '\\x00', :sha, 'forged.csv', :value)""",
            {"run": own_run, "tenant": w.tenant, "sha": "0" * 64, "value": forged_value},
        )
    rejected("row-level security", None, call=lambda db: persist_agent_artifact(db, other_payload))
    # Reusing another tenant's artifact id under the own tenant is a loud
    # primary-key violation, never a silent ON CONFLICT no-op.
    reused_id = copy.deepcopy(own_payload)
    reused_id["artifact_id"] = reused_id["artifact"]["artifact_id"] = other_payload["artifact_id"]
    rejected("agent_artifacts_pkey", None, call=lambda db: persist_agent_artifact(db, reused_id))
    rejected("row-level security", None, call=lambda db: append_agent_artifact_receipt(db, other_payload))
    rejected(
        "foreign key",
        """INSERT INTO fsma.ingestion_run_receipts (tenant_id, ingestion_run_id, state)
           VALUES (CAST(:tenant AS uuid), CAST(:run AS uuid), 'needs_review')""",
        {"tenant": w.tenant, "run": other_run},
    )
    with w.admin.cursor() as cur:
        cur.execute(
            """SELECT (SELECT COUNT(*) FROM fsma.manifest_blobs WHERE tenant_id = %(t)s),
                      (SELECT COUNT(*) FROM fsma.agent_artifacts WHERE tenant_id = %(t)s),
                      (SELECT COUNT(*) FROM fsma.ingestion_run_receipts WHERE tenant_id = %(t)s)""",
            {"t": w.other},
        )
        assert cur.fetchone() == (1, 2, 2)
