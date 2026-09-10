"""Separate acceptance after explicitly provisioning the repository rule catalog."""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
access = Path(sys.argv[1])
assert access.parent.name.startswith("regengine-operational-")
c = json.loads(access.read_text())
assert c["base_url"].startswith("http://127.0.0.1:")
os.environ.clear()
os.environ.update(
    {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(access.parent),
        "REGENGINE_ENV": "test",
        "ENVIRONMENT": "test",
        "DATABASE_URL": c["runtime_url"],
        "ADMIN_DATABASE_URL": c["runtime_url"],
    }
)
sys.path[:0] = [str(ROOT), str(ROOT / "services")]
import httpx
from shared.canonical_persistence import CanonicalEventStore
from shared.rules.seeds import seed_rule_definitions
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

result = {"catalog": "repository FSMA_RULE_SEEDS explicitly seeded only into disposable database"}
engine = create_engine(c["owner_url"])
with Session(engine) as session:
    result["rules_inserted"] = seed_rule_definitions(session)
    session.commit()
engine.dispose()
now = datetime.now(timezone.utc)
body = {
    "source": "local-rule-acceptance",
    "events": [
        {
            "cte_type": "shipping",
            "traceability_lot_code": f"LOCAL-RULES-{i}-{uuid4().hex[:8]}",
            "product_description": "Romaine Lettuce",
            "quantity": 24,
            "unit_of_measure": "cases",
            "location_name": "Synthetic packing site",
            "timestamp": now.isoformat(),
            "kdes": {
                "ftl_covered": True,
                "ship_date": now.date().isoformat(),
                "ship_from_location": "Synthetic packing site",
                "ship_to_location": "Synthetic distribution center",
                "reference_document": f"BOL-{i}",
                "reference_document_type": "Bill of Lading",
                "reference_document_number": f"BOL-{i}",
                "tlc_source_reference": f"SRC-{i}",
                "traceability_lot_code_source_reference": f"SRC-{i}",
            },
        }
        for i in range(500)
    ],
}
raw = json.dumps(body).encode()
tenant = c["fixtures"][0]
hdr = {
    "X-RegEngine-API-Key": tenant["key"],
    "X-Tenant-ID": tenant["tenant"],
    "Idempotency-Key": str(uuid4()),
    "Content-Type": "application/json",
    "X-Webhook-Signature": "sha256=" + hmac.new(c["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest(),
}
with httpx.Client(base_url=c["base_url"], timeout=120) as client:
    started = time.monotonic()
    response = client.post("/api/v1/webhooks/ingest", content=raw, headers=hdr)
    result["http"] = response.status_code
    result["accepted"] = response.json().get("accepted")
    result["rejected"] = response.json().get("rejected")
    result["seconds"] = round(time.monotonic() - started, 3)
    result["first_event"] = response.json().get("events", [response.json()])[0]
    export = client.get(
        "/api/v1/fda/export/all",
        params={
            "tenant_id": tenant["tenant"],
            "format": "package",
            "start_date": now.date().isoformat(),
            "end_date": (now + timedelta(days=1)).date().isoformat(),
        },
        headers=hdr,
    )
    result["export_http"] = export.status_code
    result["chain_integrity"] = export.headers.get("x-chain-integrity")
    if export.status_code == 200:
        bundle = OUT / "seeded-rules.zip"
        bundle.write_bytes(export.content)
        verify = subprocess.run(
            [sys.executable, str(ROOT / "frontend/public/sdk/verify_chain.py"), str(bundle)],
            capture_output=True,
            text=True,
        )
        result["verifier_exit"] = verify.returncode
        result["verifier_output"] = verify.stdout + verify.stderr
runtime = create_engine(c["runtime_url"])
with Session(runtime) as session:
    store = CanonicalEventStore(session, dual_write=False)
    store.set_tenant_context(tenant["tenant"])
    result["counts"] = {
        table: session.execute(
            text(f"SELECT count(*) FROM fsma.{table} WHERE tenant_id=CAST(:tenant AS uuid)"),
            {"tenant": tenant["tenant"]},
        ).scalar()
        for table in ("cte_events", "traceability_events", "hash_chain", "rule_evaluations")
    }
    verification = store.verify_chain_canonical(tenant["tenant"])
    result["canonical_valid"] = verification.valid
    result["canonical_errors"] = verification.errors[:3]
runtime.dispose()
result["passed"] = (
    result["http"] == 200
    and result["accepted"] == 500
    and result["counts"]["rule_evaluations"] >= 500
    and result["canonical_valid"]
    and result.get("verifier_exit") == 0
)
(OUT / "seeded-rules.json").write_text(json.dumps(result, indent=2, default=str))
print(json.dumps(result, indent=2, default=str))
raise SystemExit(0 if result["passed"] else 1)
