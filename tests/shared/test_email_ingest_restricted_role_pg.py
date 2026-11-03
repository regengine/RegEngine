"""email_ingest webhook as the restricted ``regengine`` role, after the runner.

Runs in the same CI step and under the same env contract as
``test_postgres_evidence_workflow_pg.py``: the database was migrated by
``scripts/run-migrations.sh`` (which reapplies the v111 cutover), and
DATABASE_URL is the NOSUPERUSER/NOBYPASSRLS runtime role. Fixture rows are
written through the provider credential only.
"""

import base64
import importlib.util
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
DATABASE = os.getenv("REGENGINE_EVIDENCE_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE, reason="Explicit disposable PostgreSQL required"),
]

BASIC_USER = "postmark-restricted-role-test"
BASIC_PASSWORD = "restricted-role-test-password"  # pragma: allowlist secret


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def email(monkeypatch):
    url = make_url(DATABASE)
    assert DATABASE == os.environ["DATABASE_URL"]
    assert url.username == "regengine"
    if url.host:
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
    # Restricted-role email ingest fixture — not 21 CFR 1.1310 location rules.
    monkeypatch.setattr("app.webhook_models.is_location_description_complete", lambda **kwargs: True)
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_USER", BASIC_USER)
    monkeypatch.setenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", BASIC_PASSWORD)
    _load("pg_email_ingest_proof", ROOT / "scripts/verify_inflow_to_regengine_e2e.py")._configure_paths()

    from app.email_ingest.router import router
    from app.inflow_workbench import COMPLETE_ROMAINE_CSV
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    admin = psycopg.connect(**admin_connect)
    admin.autocommit = True
    tenant, other = str(uuid4()), str(uuid4())
    address, other_address = f"ingest+{tenant}@inbound.test", f"ingest+{other}@inbound.test"
    with admin.cursor() as cur:
        for tid, inbound, senders in (
            (tenant, address, ["@supplier-a.test"]),
            (other, other_address, ["ops@supplier-b.test"]),
        ):
            cur.execute(
                "INSERT INTO public.tenants(id,name,slug,status) VALUES (%s,%s,%s,'active')",
                (tid, "Synthetic email-ingest regression", f"pg-email-{tid}"),
            )
            cur.execute(
                "INSERT INTO fsma.tenant_inbound_addresses(tenant_id,inbound_address,allowed_senders) "
                "VALUES (%s,%s,%s)",
                (tid, inbound, senders),
            )

    start = datetime.now(timezone.utc).date() - timedelta(days=2)
    csv_bytes = (
        COMPLETE_ROMAINE_CSV.replace("2026-04-26", str(start))
        .replace("2026-04-27", str(start + timedelta(days=1)))
        .encode()
    )
    rows = len(csv_bytes.decode().strip().splitlines()) - 1
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    def deliver(sender, recipient=address, message_id=None, auth=(BASIC_USER, BASIC_PASSWORD)):
        payload = {
            "MessageID": message_id or f"pg-email-{uuid4()}",
            "From": sender,
            "OriginalRecipient": recipient,
            "Subject": "Weekly traceability CSV",
            "Attachments": [
                {
                    "Name": "romaine.csv",
                    "Content": base64.b64encode(csv_bytes).decode(),
                    "ContentType": "text/csv",
                }
            ],
        }
        return payload["MessageID"], client.post("/webhooks/email/inbound", json=payload, headers=_basic(*auth))

    def runtime(statement, tid=tenant):
        from shared.database import SessionLocal
        from shared.tenant_context import set_tenant_guc

        with SessionLocal() as db:
            set_tenant_guc(db, tid)
            return db.execute(text(statement)).fetchall()

    def audit(message_id):
        with admin.cursor() as cur:
            cur.execute(
                "SELECT status, tenant_id::text, rejection_reason, accepted_attachment_count "
                "FROM fsma.inbound_email_audit WHERE message_id = %s",
                (message_id,),
            )
            return cur.fetchall()

    def retained_files(tid):
        with admin.cursor() as cur:
            cur.execute("SELECT original_filename FROM fsma.manifest_blobs WHERE tenant_id = %s", (tid,))
            return [row[0] for row in cur.fetchall()]

    yield SimpleNamespace(
        tenant=tenant,
        other=other,
        address=address,
        rows=rows,
        deliver=deliver,
        runtime=runtime,
        audit=audit,
        retained_files=retained_files,
    )
    client.close()
    admin.close()


def test_runtime_role_reaches_email_tables_only_through_security_definer_functions(email):
    roles = email.runtime("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
    assert tuple(roles[0]) == ("regengine", False, False)
    for statement in (
        "SELECT * FROM fsma.inbound_email_audit LIMIT 1",
        "SELECT * FROM fsma.tenant_inbound_addresses LIMIT 1",
        "INSERT INTO fsma.tenant_inbound_addresses(tenant_id,inbound_address,allowed_senders) "
        f"VALUES ('{email.tenant}', 'hijack@inbound.test', ARRAY['@attacker.test'])",
        # The CSV receipt grant is INSERT-only: retained files are never read back.
        "SELECT * FROM fsma.manifest_blobs LIMIT 1",
    ):
        with pytest.raises(Exception, match="permission denied"):
            email.runtime(statement)
    with pytest.raises(Exception, match="row-level security"):
        email.runtime(
            "INSERT INTO fsma.manifest_blobs(ingestion_run_id,tenant_id,raw_bytes,sha256,original_filename) "
            f"VALUES ('{uuid4()}', '{email.other}', 'x', 'x', 'cross-tenant.csv')"
        )


def test_allowlisted_delivery_ingests_as_regengine_and_replays_idempotently(email):
    message_id, response = email.deliver("Supplier A <Receiving@Supplier-A.test>")
    assert response.status_code == 200, response.text[:1000]
    body = response.json()
    assert (body["status"], body["tenant_id"]) == ("accepted", email.tenant)
    assert [(a["status"], a["rows_accepted"], a["rows_rejected"]) for a in body["attachments"]] == [
        ("accepted", email.rows, 0)
    ]
    assert email.audit(message_id) == [("accepted", email.tenant, None, 1)]
    assert email.runtime("SELECT COUNT(*) FROM fsma.cte_events")[0][0] == email.rows
    assert email.runtime("SELECT COUNT(*) FROM fsma.cte_events", tid=email.other)[0][0] == 0
    assert email.retained_files(email.tenant) == ["romaine.csv"]

    _, replay = email.deliver("Supplier A <Receiving@Supplier-A.test>", message_id=message_id)
    assert replay.status_code == 200
    assert replay.json() == body
    assert email.audit(message_id) == [("accepted", email.tenant, None, 1)]
    assert email.runtime("SELECT COUNT(*) FROM fsma.cte_events")[0][0] == email.rows
    assert email.retained_files(email.tenant) == ["romaine.csv"]
    assert email.retained_files(email.other) == []


@pytest.mark.parametrize(
    "sender",
    [
        "stranger@unlisted.test",
        # Allowlisted for the *other* tenant only: must not write into this one.
        "ops@supplier-b.test",
        # Suffix match is on the full "@domain", not a bare domain tail.
        "receiving@evil-supplier-a.test",
    ],
)
def test_unauthorized_sender_is_rejected_without_ingestion(email, sender):
    message_id, response = email.deliver(sender)
    assert response.status_code == 200, response.text[:1000]
    body = response.json()
    assert (body["status"], body["rejection_reason"], body["tenant_id"]) == ("rejected", "unmapped_recipient", None)
    assert email.audit(message_id) == [("rejected", None, "unmapped_recipient", 0)]
    for tid in (email.tenant, email.other):
        assert email.runtime("SELECT COUNT(*) FROM fsma.cte_events", tid=tid)[0][0] == 0


def test_bad_webhook_credentials_write_nothing(email):
    message_id, response = email.deliver("receiving@supplier-a.test", auth=(BASIC_USER, "wrong"))
    assert response.status_code == 401
    assert email.audit(message_id) == []
    assert email.runtime("SELECT COUNT(*) FROM fsma.cte_events")[0][0] == 0
