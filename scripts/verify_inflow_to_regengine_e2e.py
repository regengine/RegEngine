#!/usr/bin/env python3
"""Hard-fail local Inflow-to-RegEngine evidence proof.

This script exercises the corrected Inflow workbench "complete romaine" fixture
through the real local FastAPI routers and the configured Postgres database.
Only local principal/subscription gates are overridden; sandbox validation,
workbench persistence, webhook ingest, hash-chain verification, compliance
scoring, and FDA package export all run through their production code paths.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOTS = (
    REPO_ROOT,
    REPO_ROOT / "services",
    REPO_ROOT / "services" / "ingestion",
)

REQUIRED_TABLES = (
    "fsma.cte_events",
    "fsma.cte_kdes",
    "fsma.hash_chain",
    "fsma.fda_export_log",
    "fsma.inflow_workbench_runs",
    "fsma.inflow_workbench_commit_decisions",
    "fsma.inflow_workbench_fix_items",
    "fsma.traceability_events",
)

SOURCE = "inflow-lab-data-feeder"
EXPORT_START_DATE = "2026-04-25"
EXPORT_END_DATE = "2026-04-28"


class VerificationError(RuntimeError):
    """Raised when the local proof cannot be trusted."""


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _configure_paths() -> None:
    for root in reversed(SERVICE_ROOTS):
        root_text = str(root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)


def _configure_environment(args: argparse.Namespace) -> None:
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise VerificationError(
            "DATABASE_URL is required. Pass --database-url or set DATABASE_URL."
        )
    if not database_url.startswith("postgresql"):
        raise VerificationError(
            "This proof requires a real Postgres DATABASE_URL; sqlite/dev mocks are not accepted."
        )

    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("REGENGINE_ENV", "development")
    os.environ["API_KEY"] = args.api_key
    os.environ["REGENGINE_API_KEY"] = args.api_key
    os.environ.setdefault("WEBHOOK_INGEST_RATE_LIMIT_RPM", "1000")
    os.environ.setdefault("WEBHOOK_READ_RATE_LIMIT_RPM", "1000")
    os.environ.setdefault("INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM", "1000")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify simulated Inflow data becomes persisted RegEngine evidence."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Postgres DATABASE_URL. Defaults to the DATABASE_URL environment variable.",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/regengine-inflow-e2e",
        help="Directory for summary.json and the FDA package artifact.",
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Optional UUID tenant id. Defaults to a fresh UUID for deterministic row counts.",
    )
    parser.add_argument(
        "--api-key",
        default="regengine-inflow-e2e-local-key",
        help="Process-local preshared API key used for TestClient calls.",
    )
    return parser.parse_args(argv)


def _response_json(response, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise VerificationError(
            f"{label} failed with HTTP {response.status_code}: {response.text[:1000]}"
        )
    return response.json()


def _check_database(tenant_id: str) -> None:
    from shared.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1")).scalar_one()
        missing = [
            table_name
            for table_name in REQUIRED_TABLES
            if db.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": table_name},
            ).scalar()
            is None
        ]
        if missing:
            raise VerificationError(
                "Postgres is reachable, but required migrated tables are missing: "
                + ", ".join(missing)
            )

        from shared.tenant_context import set_tenant_guc

        set_tenant_guc(db, tenant_id)
    finally:
        db.close()


def _build_app(tenant_id: str) -> TestClient:
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.compliance_score import router as compliance_router
    from app.fda_export.router import router as fda_export_router
    from app.inflow_workbench import router as workbench_router
    from app.sandbox.router import router as sandbox_router
    from app.subscription_gate import require_active_subscription
    from app.webhook_router_v2 import router as webhook_router

    app = FastAPI()
    app.include_router(sandbox_router)
    app.include_router(workbench_router)
    app.include_router(webhook_router)
    app.include_router(compliance_router)
    app.include_router(fda_export_router)

    async def _local_principal(request: Request) -> IngestionPrincipal:
        principal = IngestionPrincipal(
            key_id="inflow-e2e-local",
            scopes=["*"],
            tenant_id=tenant_id,
            auth_mode="local_e2e",
        )
        request.state.principal = principal
        return principal

    async def _local_subscription() -> None:
        return None

    app.dependency_overrides[get_ingestion_principal] = _local_principal
    app.dependency_overrides[require_active_subscription] = _local_subscription
    return TestClient(app)


def _auth_headers(args: argparse.Namespace, tenant_id: str) -> dict[str, str]:
    return {
        "X-RegEngine-API-Key": args.api_key,
        "X-Tenant-ID": tenant_id,
        "X-Request-ID": f"inflow-e2e-{uuid.uuid4().hex[:12]}",
        "User-Agent": "regengine-inflow-e2e-verifier",
    }


def _post_json(
    client: TestClient,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
):
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    request_headers = {
        **headers,
        "content-type": "application/json",
        "Idempotency-Key": f"inflow-e2e-{uuid.uuid4()}",
    }
    secret = os.getenv("WEBHOOK_HMAC_SECRET", "").strip()
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        request_headers["X-Webhook-Signature"] = f"sha256={digest}"
    return client.post(path, content=body, headers=request_headers)


def _events_from_csv() -> list[dict[str, Any]]:
    from app.inflow_workbench import COMPLETE_ROMAINE_CSV
    from app.sandbox.csv_parser import _parse_csv_to_events

    events = _parse_csv_to_events(COMPLETE_ROMAINE_CSV)
    for event in events:
        event.pop("__normalizations__", None)
    return events


def _assert_workbench_persisted(tenant_id: str, run_id: str) -> None:
    from shared.database import SessionLocal

    db = SessionLocal()
    try:
        from shared.tenant_context import set_tenant_guc

        set_tenant_guc(db, tenant_id)
        stored = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsma.inflow_workbench_runs
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND run_id = :run_id
                """
            ),
            {"tenant_id": tenant_id, "run_id": run_id},
        ).scalar_one()
        _expect(stored == 1, "Workbench save did not persist to Postgres.")
    finally:
        db.close()


def _ensure_tenant_row(tenant_id: str) -> None:
    from shared.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO public.tenants (id, name, slug, status)
                VALUES (
                    CAST(:tenant_id AS uuid),
                    'Inflow E2E Local Tenant',
                    :slug,
                    'active'
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "tenant_id": tenant_id,
                "slug": f"inflow-e2e-{tenant_id[:8]}",
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _persistence_counts(tenant_id: str) -> dict[str, int]:
    from shared.database import SessionLocal

    db = SessionLocal()
    try:
        from shared.tenant_context import set_tenant_guc

        set_tenant_guc(db, tenant_id)
        event_count = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsma.cte_events
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND source = :source
                """
            ),
            {"tenant_id": tenant_id, "source": SOURCE},
        ).scalar_one()
        kde_count = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsma.cte_kdes k
                JOIN fsma.cte_events e ON e.id = k.cte_event_id
                WHERE e.tenant_id = CAST(:tenant_id AS uuid)
                  AND e.source = :source
                """
            ),
            {"tenant_id": tenant_id, "source": SOURCE},
        ).scalar_one()
        hash_count = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsma.hash_chain
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"tenant_id": tenant_id},
        ).scalar_one()
        hashed_events = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fsma.cte_events e
                JOIN fsma.hash_chain h
                  ON h.event_hash = e.sha256_hash
                 AND h.tenant_id = e.tenant_id
                WHERE e.tenant_id = CAST(:tenant_id AS uuid)
                  AND e.source = :source
                  AND e.sha256_hash IS NOT NULL
                  AND h.chain_hash IS NOT NULL
                """
            ),
            {"tenant_id": tenant_id, "source": SOURCE},
        ).scalar_one()
        return {
            "cte_events": int(event_count),
            "cte_kdes": int(kde_count),
            "hash_chain": int(hash_count),
            "hashed_events": int(hashed_events),
        }
    finally:
        db.close()


def _inspect_package(content: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        names = package.namelist()
        csv_names = [
            name
            for name in names
            if name.startswith("fda_spreadsheet_") and name.endswith(".csv")
        ]
        chain_names = [
            name
            for name in names
            if name.startswith("chain_verification_") and name.endswith(".json")
        ]
        _expect("manifest.json" in names, "FDA package is missing manifest.json.")
        _expect(len(csv_names) == 1, "FDA package must contain exactly one FDA CSV.")
        _expect(len(chain_names) == 1, "FDA package must contain exactly one chain payload.")

        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        chain_payload = json.loads(package.read(chain_names[0]).decode("utf-8"))
        csv_text = package.read(csv_names[0]).decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(csv_text)))

    fieldnames = rows[0].keys() if rows else []
    _expect(len(rows) == 5, f"FDA CSV expected 5 rows, found {len(rows)}.")
    _expect(
        "System Entry Timestamp" in fieldnames,
        "FDA CSV is missing System Entry Timestamp.",
    )
    _expect(
        all(row.get("System Entry Timestamp") for row in rows),
        "FDA CSV has blank System Entry Timestamp values.",
    )
    _expect(
        manifest.get("summary", {}).get("record_count") == 5,
        "FDA package manifest record_count is not 5.",
    )
    _expect(
        chain_payload.get("verification_status") == "VERIFIED",
        "FDA package chain verification payload is not VERIFIED.",
    )
    _expect(
        chain_payload.get("row_hash_coverage", {}).get("records_with_chain_hash") == 5,
        "FDA package chain payload does not show 5 chain-hashed records.",
    )

    return {
        "files": names,
        "manifest_name": "manifest.json",
        "csv_name": csv_names[0],
        "chain_name": chain_names[0],
        "row_count": len(rows),
        "system_entry_timestamp_present": True,
        "manifest_record_count": manifest.get("summary", {}).get("record_count"),
        "chain_status": chain_payload.get("verification_status"),
        "records_with_chain_hash": chain_payload.get("row_hash_coverage", {}).get("records_with_chain_hash"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    _configure_paths()
    _configure_environment(args)

    tenant_id = args.tenant_id or str(uuid.uuid4())
    uuid.UUID(tenant_id)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _check_database(tenant_id)
    _ensure_tenant_row(tenant_id)

    from app.inflow_workbench import COMPLETE_ROMAINE_CSV

    client = _build_app(tenant_id)
    headers = _auth_headers(args, tenant_id)

    sandbox = _response_json(
        client.post("/api/v1/sandbox/evaluate", json={"csv": COMPLETE_ROMAINE_CSV}),
        "sandbox preflight",
    )
    _expect(sandbox["total_events"] == 5, "Sandbox did not parse 5 clean fixture events.")
    _expect(sandbox["compliant_events"] == 5, "Clean fixture is no longer fully compliant.")
    _expect(sandbox["total_kde_errors"] == 0, "Clean fixture has KDE errors.")
    _expect(sandbox["total_rule_failures"] == 0, "Clean fixture has rule failures.")
    _expect(sandbox["submission_blocked"] is False, "Clean fixture is blocked in sandbox.")

    workbench = _response_json(
        client.post(
            "/api/v1/inflow-workbench/runs",
            json={
                "tenant_id": tenant_id,
                "source": SOURCE,
                "csv": COMPLETE_ROMAINE_CSV,
                "result": sandbox,
            },
            headers=headers,
        ),
        "workbench save",
    )
    _expect(workbench["readiness"]["score"] == 100, "Workbench readiness is not 100.")
    _expect(workbench["fix_queue"] == [], "Workbench created fix items for the clean fixture.")
    _expect(workbench["commit_gate"]["allowed"] is True, "Workbench staging gate is not allowed.")
    _assert_workbench_persisted(tenant_id, workbench["run_id"])

    ingest_payload = {
        "tenant_id": tenant_id,
        "tenant_seeded": True,
        "source": SOURCE,
        "events": _events_from_csv(),
    }
    ingest = _response_json(
        _post_json(client, "/api/v1/webhooks/ingest", ingest_payload, headers),
        "webhook ingest",
    )
    _expect(ingest["accepted"] == 5, f"Ingest accepted {ingest['accepted']} events, expected 5.")
    _expect(ingest["rejected"] == 0, f"Ingest rejected {ingest['rejected']} clean events.")
    _expect(
        all(event.get("sha256_hash") and event.get("chain_hash") for event in ingest["events"]),
        "Ingest accepted events without record and chain hashes.",
    )

    counts = _persistence_counts(tenant_id)
    _expect(counts["cte_events"] == 5, f"Postgres has {counts['cte_events']} CTE events, expected 5.")
    _expect(counts["hashed_events"] == 5, "Not all persisted CTE events have hash-chain rows.")
    _expect(counts["cte_kdes"] > 0, "Postgres has no KDE rows for the clean fixture.")

    recent = _response_json(
        client.get(
            f"/api/v1/webhooks/recent?tenant_id={tenant_id}&limit=10",
            headers=headers,
        ),
        "recent events",
    )
    _expect(recent["total"] >= 5, "Recent events did not include the ingested records.")

    chain = _response_json(
        client.get(f"/api/v1/webhooks/chain/verify?tenant_id={tenant_id}", headers=headers),
        "chain verification",
    )
    _expect(chain["chain_valid"] is True, f"Hash chain invalid: {chain.get('errors')}")
    _expect(chain["chain_length"] >= 5, "Hash chain is shorter than the ingested proof batch.")

    score = _response_json(
        client.get(f"/api/v1/compliance/score/{tenant_id}", headers=headers),
        "compliance score",
    )
    _expect(score["events_analyzed"] >= 5, "Compliance score did not analyze the ingested events.")
    _expect(score["overall_score"] > 0, "Compliance score returned zero for persisted evidence.")
    _expect(score["last_chain_hash"], "Compliance score did not expose the latest chain hash.")

    export_response = client.get(
        "/api/v1/fda/export/all"
        f"?tenant_id={tenant_id}"
        f"&start_date={EXPORT_START_DATE}"
        f"&end_date={EXPORT_END_DATE}"
        "&format=package",
        headers=headers,
    )
    if export_response.status_code >= 400:
        raise VerificationError(
            f"FDA package export failed with HTTP {export_response.status_code}: "
            f"{export_response.text[:1000]}"
        )
    _expect(
        export_response.headers.get("X-Record-Count") == "5",
        "FDA export X-Record-Count is not 5.",
    )
    _expect(
        export_response.headers.get("X-Chain-Integrity") == "VERIFIED",
        "FDA export chain integrity header is not VERIFIED.",
    )
    package_path = output_dir / "fda_export_all_package.zip"
    package_path.write_bytes(export_response.content)
    package_checks = _inspect_package(export_response.content)

    summary = {
        "tenant_id": tenant_id,
        "source": SOURCE,
        "sandbox": {
            "total_events": sandbox["total_events"],
            "compliant_events": sandbox["compliant_events"],
            "total_kde_errors": sandbox["total_kde_errors"],
            "total_rule_failures": sandbox["total_rule_failures"],
            "submission_blocked": sandbox["submission_blocked"],
        },
        "workbench": {
            "run_id": workbench["run_id"],
            "readiness_score": workbench["readiness"]["score"],
            "fix_items": len(workbench["fix_queue"]),
            "staging_allowed": workbench["commit_gate"]["allowed"],
            "export_eligible": workbench["commit_gate"]["export_eligible"],
        },
        "ingest": {
            "accepted": ingest["accepted"],
            "rejected": ingest["rejected"],
            "total": ingest["total"],
            "event_ids": [event["event_id"] for event in ingest["events"]],
        },
        "postgres_counts": counts,
        "recent": {
            "visible_events": recent["total"],
        },
        "chain": {
            "valid": chain["chain_valid"],
            "length": chain["chain_length"],
            "errors": chain["errors"],
        },
        "compliance_score": {
            "overall_score": score["overall_score"],
            "grade": score["grade"],
            "events_analyzed": score["events_analyzed"],
            "last_chain_hash": score["last_chain_hash"],
        },
        "fda_export": {
            "header_record_count": export_response.headers.get("X-Record-Count"),
            "header_chain_integrity": export_response.headers.get("X-Chain-Integrity"),
            "header_export_hash": export_response.headers.get("X-Export-Hash"),
            "header_package_hash": export_response.headers.get("X-Package-Hash"),
            "package_path": str(package_path),
            "artifact_checks": package_checks,
        },
    }

    summary_path = output_dir / "summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = run(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Inflow-to-RegEngine E2E verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
