"""Synthetic, offline probes of verification boundaries; no app/data mutations.

Run with the project's Python environment from any working directory. Results
describe observed behavior, not a claim that unsafe acceptance is desirable.
The public-bundle probe uses only stdlib + the published offline verifier;
the other probes use installed application dependencies and in-memory SQLite.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import zipfile


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "services"), str(ROOT / "services/ingestion"), str(ROOT)]


def deny_network(*args, **kwargs):
    raise RuntimeError("security reproduction prohibits network connections")


socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network

spec = importlib.util.spec_from_file_location(
    "published_verifier", ROOT / "frontend/public/sdk/verify_chain.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

from app import fda_export_service as export_service  # noqa: E402
from app.proof_verify_router import _verify_payload, _verify_zip_bundle  # noqa: E402
from shared.cte_persistence import CTEPersistence, compute_chain_hash, compute_event_hash  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def report(case: str, **values):
    print(json.dumps({"case": case, **values}, sort_keys=True))


def offline_check(path: Path):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        status = verifier.verify_bundle(str(path))
    return {"exit": status, "output": output.getvalue().strip()}


def bundle_bytes(content: bytes, manifest: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("synthetic.csv", content)
        bundle.writestr("manifest.json", json.dumps(manifest))
    return buffer.getvalue()


def manifest_for(content: bytes) -> dict:
    digest = hashlib.sha256(content).hexdigest()
    return {
        "version": "1.0", "_comment": "SYNTHETIC SECURITY EXPERIMENT",
        "files": [{"path": "synthetic.csv", "size": len(content), "sha256": digest}],
        "merkle": {"root": verifier._merkle_root([digest]), "leaves": [digest]},
    }


with tempfile.TemporaryDirectory(prefix="regengine-security-synthetic-") as temp:
    original = b"lot,quantity\nSYNTHETIC,10\n"
    changed = b"lot,quantity\nSYNTHETIC,99\n"
    for label, content, manifest in (
        ("original", original, manifest_for(original)),
        ("changed_content_unchanged_manifest", changed, manifest_for(original)),
        ("changed_content_recomputed_manifest", changed, manifest_for(changed)),
    ):
        path = Path(temp) / f"{label}.zip"
        path.write_bytes(bundle_bytes(content, manifest))
        public_result = _verify_zip_bundle(path.read_bytes())
        report(label, offline=offline_check(path), public_verified=public_result.verified)

    event = {
        "id": "synthetic-event", "event_type": "receiving",
        "traceability_lot_code": "SYNTHETIC", "quantity": 10,
        "unit_of_measure": "cases", "event_timestamp": "2026-08-01T12:00:00+00:00",
        "sha256_hash": "a" * 64, "chain_hash": "b" * 64, "kdes": {},
    }
    events = [event]
    completeness = export_service._build_completeness_summary(events)
    csv_content = export_service._generate_csv(events)
    csv_hash = hashlib.sha256(csv_content.encode()).hexdigest()
    chain = SimpleNamespace(valid=True, chain_length=1, errors=[], checked_at="synthetic")
    payload = export_service._build_chain_verification_payload(
        tenant_id="synthetic-tenant", tlc="SYNTHETIC", events=events,
        csv_hash=csv_hash, chain_verification=chain, completeness_summary=completeness,
    )
    package, metadata = export_service._build_fda_package(
        events=events, csv_content=csv_content, csv_hash=csv_hash, chain_payload=payload,
        completeness_summary=completeness, tenant_id="synthetic-tenant", tlc="SYNTHETIC",
        query_start_date=None, query_end_date=None,
    )
    path = Path(temp) / "generated-fda-package.zip"
    path.write_bytes(package)
    public_result = _verify_zip_bundle(package)
    report("actual_generator_to_verifiers", offline=offline_check(path),
           public_verified=public_result.verified,
           failed_checks=[c.name for c in public_result.checks if not c.passed])

    chain.valid = False
    chain.errors = ["synthetic chain break"]
    partial = export_service._build_chain_verification_payload(
        tenant_id="synthetic-tenant", tlc="SYNTHETIC", events=[{}],
        csv_hash=csv_hash, chain_verification=chain, completeness_summary=completeness,
    )
    report("invalid_chain_and_missing_hash", status=partial["verification_status"],
           chain_valid=partial["chain_verification"]["valid"])

engine = create_engine("sqlite:///:memory:")
with engine.begin() as db:
    db.execute(text("ATTACH DATABASE ':memory:' AS fsma"))
    db.execute(text("CREATE TABLE fsma.cte_events (id TEXT, tenant_id TEXT, validation_status TEXT, quantity REAL)"))
    db.execute(text("CREATE TABLE fsma.hash_chain (sequence_num INTEGER, event_hash TEXT, previous_chain_hash TEXT, chain_hash TEXT, cte_event_id TEXT, tenant_id TEXT)"))
    digest = compute_event_hash("e1", "receiving", "SYNTHETIC", "", 10, "cases", None, None,
                                "2026-08-01T12:00:00+00:00", {})
    db.execute(text("INSERT INTO fsma.cte_events VALUES ('e1', 'tenant-a', 'valid', 10)"))
    db.execute(text("INSERT INTO fsma.hash_chain VALUES (1, :h, NULL, :c, 'e1', 'tenant-a')"),
               {"h": digest, "c": compute_chain_hash(digest, None)})
    persistence = CTEPersistence(db)
    before = persistence.verify_chain("tenant-a").valid
    db.execute(text("UPDATE fsma.cte_events SET quantity=99 WHERE id='e1'"))
    after = persistence.verify_chain("tenant-a").valid
    recomputed = compute_event_hash("e1", "receiving", "SYNTHETIC", "", 99, "cases", None, None,
                                    "2026-08-01T12:00:00+00:00", {})
    report("changed_persisted_quantity", before_valid=before, after_valid=after,
           quantity_hash_changed=(recomputed != digest))
    db.execute(text("INSERT INTO fsma.cte_events VALUES ('e2', 'tenant-b', 'valid', 10)"))
    db.execute(text("INSERT INTO fsma.hash_chain VALUES (1, :h, NULL, :c, 'e2', 'tenant-b')"),
               {"h": digest, "c": compute_chain_hash(digest, None)})
    db.execute(text("UPDATE fsma.hash_chain SET chain_hash=:h WHERE tenant_id='tenant-a'"),
               {"h": "0" * 64})
    report("corrupted_chain_negative_control", valid=persistence.verify_chain("tenant-a").valid,
           unrelated_tenant_valid=persistence.verify_chain("tenant-b").valid,
           unrelated_tenant_chain_length=persistence.verify_chain("tenant-b").chain_length)

bare = _verify_payload(manifest={}, events=[{"sha256_hash": "z" * 64}], declared_root=None)
report("nonhex_hash_without_trusted_root", verified=bare.verified)
