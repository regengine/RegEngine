"""HTTP, RLS, ledger, export and tamper checks for probe.py's private fixture."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
access = Path(sys.argv[1])
assert access.parent.name.startswith("regengine-operational-") and access.is_file()
config = json.loads(access.read_text())
assert config["base_url"].startswith("http://127.0.0.1:")
redis_port = int(config["redis_port"])
assert 1 <= redis_port <= 65535
redis_url = f"redis://127.0.0.1:{redis_port}/0"
os.environ.clear()
os.environ.update(
    {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(access.parent),
        "PYTHONPATH": f"{ROOT}:{ROOT}/services",
        "REGENGINE_ENV": "test",
        "ENVIRONMENT": "test",
        "DATABASE_URL": config["runtime_url"],
        "ADMIN_DATABASE_URL": config["runtime_url"],
        "REDIS_URL": redis_url,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
)
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
import httpx
from shared.canonical_persistence import CanonicalEventStore
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Resolve HMAC from disposable DB (never from access.json — CodeQL clear-text-storage).
_meta_engine = create_engine(config["owner_url"])
with _meta_engine.connect() as _meta_conn:
    hmac_secret = _meta_conn.execute(
        text("SELECT value FROM probe_harness_meta WHERE key = 'webhook_hmac_secret'")
    ).scalar_one()
_meta_engine.dispose()
assert isinstance(hmac_secret, str) and hmac_secret

results = []


def record(name, passed, **data):
    results.append({"check": name, "passed": bool(passed), **data})
    (OUT / "checks.json").write_text(json.dumps(results, indent=2, default=str))
    print(name, "PASS" if passed else "FAIL", json.dumps(data, default=str), flush=True)


def payload(label, count=1):
    now = datetime.now(timezone.utc)
    return {
        "source": "local-acceptance",
        "events": [
            {
                "cte_type": "shipping",
                "traceability_lot_code": f"LOCAL-{label}-{i}",
                "product_description": "Synthetic Romaine Lettuce",
                "quantity": 24,
                "unit_of_measure": "cases",
                "location_name": "Synthetic packing site",
                "timestamp": now.isoformat(),
                "kdes": {
                    "ship_date": now.date().isoformat(),
                    "ship_from_location": "Synthetic packing site",
                    "ship_to_location": "Synthetic distribution center",
                    "reference_document": f"BOL-{label}-{i}",
                    "reference_document_type": "Bill of Lading",
                    "reference_document_number": f"BOL-{label}-{i}",
                    "tlc_source_reference": f"SRC-{label}-{i}",
                    "traceability_lot_code_source_reference": f"SRC-{label}-{i}",
                },
            }
            for i in range(count)
        ],
    }


def headers(tenant=0, key=None):
    fixture = config["fixtures"][tenant]
    return {
        "X-RegEngine-API-Key": fixture["key"],
        "X-Tenant-ID": fixture["tenant"],
        "Idempotency-Key": key or str(uuid4()),
    }


def post(client, body, tenant=0, key=None, override=None):
    raw = json.dumps(body).encode()
    hdr = headers(tenant, key) | {
        "Content-Type": "application/json",
        "X-Webhook-Signature": "sha256=" + hmac.new(hmac_secret.encode(), raw, hashlib.sha256).hexdigest(),
    }
    if override:
        hdr.update(override)
    return client.post("/api/v1/webhooks/ingest", content=raw, headers=hdr)


with httpx.Client(base_url=config["base_url"], timeout=120) as client:
    body = payload("single-" + uuid4().hex[:8])
    key = str(uuid4())
    first = post(client, body, key=key)
    record(
        "authenticated_ingest",
        first.status_code == 200 and first.json().get("accepted") == 1,
        http=first.status_code,
        body=first.json(),
    )
    replay = post(client, body, key=key)
    record(
        "same_key_replay",
        replay.status_code == 200 and replay.json() == first.json(),
        http=replay.status_code,
        replayed=replay.headers.get("x-idempotent-replayed"),
    )
    fresh = post(client, body)
    ids = lambda response: [row.get("event_id") for row in response.json().get("events", [])]
    record(
        "fresh_key_datastore_dedup",
        fresh.status_code == 200 and ids(fresh) == ids(first),
        http=fresh.status_code,
        event_ids=ids(fresh),
    )
    conflict = post(client, payload("conflict"), key=key)
    record("same_key_changed_body_rejected", conflict.status_code == 409, http=conflict.status_code)
    crossed = post(client, body, override={"X-Tenant-ID": config["fixtures"][1]["tenant"]})
    record("cross_tenant_header_rejected", crossed.status_code in (401, 403), http=crossed.status_code)
    unauth = post(client, body, override={"X-RegEngine-API-Key": "synthetic-invalid"})
    record("invalid_key_rejected", unauth.status_code in (401, 403), http=unauth.status_code)
    second = post(client, payload("tenant-two"), tenant=1)
    record(
        "second_authenticated_tenant",
        second.status_code == 200 and second.json().get("accepted") == 1,
        http=second.status_code,
        body=second.json(),
    )
    started = time.monotonic()
    batch = post(client, payload("max500-" + uuid4().hex[:8], 500))
    record(
        "max500_batch",
        batch.status_code == 200 and batch.json().get("accepted") == 500,
        http=batch.status_code,
        accepted=batch.json().get("accepted"),
        rejected=batch.json().get("rejected"),
        seconds=round(time.monotonic() - started, 3),
        error=batch.json() if batch.status_code != 200 else None,
    )
    now = datetime.now(timezone.utc)
    for i in range(2):
        response = client.get(
            "/api/v1/fda/export/all",
            params={
                "tenant_id": config["fixtures"][i]["tenant"],
                "format": "package",
                "start_date": now.date().isoformat(),
                "end_date": (now + timedelta(days=1)).date().isoformat(),
            },
            headers=headers(i),
        )
        record(
            f"export_tenant_{i}",
            response.status_code == 200 and response.headers.get("x-chain-integrity") == "VERIFIED",
            http=response.status_code,
            chain_integrity=response.headers.get("x-chain-integrity"),
            bytes=len(response.content),
            error=response.text[:1000] if response.status_code != 200 else None,
        )
        if response.status_code == 200:
            bundle = OUT / f"tenant-{i}.zip"
            bundle.write_bytes(response.content)
            verify = subprocess.run(
                [sys.executable, str(ROOT / "frontend/public/sdk/verify_chain.py"), str(bundle)],
                capture_output=True,
                text=True,
            )
            record(
                f"standalone_export_verifier_{i}",
                verify.returncode == 0,
                exit=verify.returncode,
                output=(verify.stdout + verify.stderr)[-1800:],
            )
            if i == 0:
                tampered = OUT / "tampered.zip"
                with zipfile.ZipFile(io.BytesIO(response.content)) as source, zipfile.ZipFile(tampered, "w") as target:
                    modified = False
                    for name in source.namelist():
                        content = source.read(name)
                        if name.endswith(".csv") and not modified:
                            content = content.replace(b"Synthetic Romaine Lettuce", b"Tampered! Romaine Lettuce", 1)
                            modified = True
                        target.writestr(name, content)
                check = subprocess.run(
                    [sys.executable, str(ROOT / "frontend/public/sdk/verify_chain.py"), str(tampered)],
                    capture_output=True,
                    text=True,
                )
                record(
                    "tampered_export_rejected",
                    modified and check.returncode != 0,
                    exit=check.returncode,
                    output=(check.stdout + check.stderr)[-1800:],
                )

engine = create_engine(config["runtime_url"])
for i, fixture in enumerate(config["fixtures"]):
    with Session(engine) as session:
        store = CanonicalEventStore(session, dual_write=False)
        store.set_tenant_context(fixture["tenant"])
        verification = store.verify_chain_canonical(fixture["tenant"])
        record(
            f"canonical_chain_{i}",
            verification.valid,
            chain_length=verification.chain_length,
            errors=verification.errors[:5],
        )
        other = config["fixtures"][1 - i]["tenant"]
        count = session.execute(
            text("SELECT count(*) FROM fsma.traceability_events WHERE tenant_id=CAST(:other AS uuid)"), {"other": other}
        ).scalar()
        record(f"rls_cross_tenant_read_{i}", count == 0, visible_rows=count)
engine.dispose()
owner = create_engine(config["owner_url"])
with Session(owner) as session:
    tenant = config["fixtures"][0]["tenant"]
    store = CanonicalEventStore(session, dual_write=False)
    store.set_tenant_context(tenant)
    row = session.execute(
        text("SELECT event_id FROM fsma.traceability_events WHERE tenant_id=CAST(:tenant AS uuid) LIMIT 1"),
        {"tenant": tenant},
    ).first()
    if row:
        session.execute(
            text("UPDATE fsma.traceability_events SET quantity=quantity+1 WHERE event_id=:event"), {"event": row[0]}
        )
        verification = store.verify_chain_canonical(tenant)
        record("stored_content_tamper_rejected", not verification.valid, errors=verification.errors[:2])
        session.rollback()
owner.dispose()
print("DONE", flush=True)

raise SystemExit(0 if all(item["passed"] for item in results) else 1)
