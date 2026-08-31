"""Experimental, offline QA probes; no product source is modified.

Run with the existing project virtualenv Python and either ``pytest`` or
``artifacts``. Network creation, DNS, subprocesses, and SQLite connections
are denied; test persistence is fake. All input records are synthetic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.clear()
os.environ.update({
    "PATH": "/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHON_DOTENV_DISABLED": "1",
    "ENVIRONMENT": "test",
    "REGENGINE_ENV": "test",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "AWS_EC2_METADATA_DISABLED": "true",
})
sys.dont_write_bytecode = True


def isolation(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                 "subprocess.Popen", "os.system", "sqlite3.connect"}:
        raise RuntimeError(f"QA isolation denied {event}")
    if event == "socket.__new__" and len(args) > 1 and args[1] != 1:
        raise RuntimeError("QA isolation denied non-Unix socket")


sys.addaudithook(isolation)
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))


def versions():
    import importlib.metadata as metadata
    result = {"python": sys.version.split()[0], "executable": sys.executable}
    for dependency in ("pytest", "pytest-asyncio", "fastapi", "pydantic",
                       "SQLAlchemy", "httpx", "fpdf2"):
        try:
            result[dependency] = metadata.version(dependency)
        except metadata.PackageNotFoundError:
            result[dependency] = "not installed"
    return result


def existing_tests():
    import json
    import pytest
    print(json.dumps({"dependencies": versions(), "isolation": "no network, no DB, no subprocess"}))
    paths = [
        "tests/shared/test_canonical_event_idempotency_key.py",
        "tests/shared/test_canonical_persistence_hardening.py",
        "tests/shared/test_canonical_persistence_tenant_context.py",
        "services/ingestion/tests/test_webhook_router_v2_enforcement.py",
        "services/ingestion/tests/test_fda_export_service_1342.py",
        "services/ingestion/tests/test_fda_export_queries_1342.py",
        "services/ingestion/tests/test_fda_export_audit_logging.py",
        "services/ingestion/tests/test_fda_export_router_1342.py",
    ]
    print("pytest arguments:", paths)
    return pytest.main([
        "-p", "pytest_asyncio.plugin", "-p", "no:cacheprovider", "-o", "addopts=",
        "--import-mode=importlib", "--asyncio-mode=auto", "-q", "-ra", *paths,
    ])


def artifact_probe():
    import contextlib
    import copy
    import hashlib
    import importlib.util
    import io
    import json
    import tempfile
    import time
    import zipfile
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location("qa_public_verifier", ROOT / "frontend/public/sdk/verify_chain.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    # Independent construction, not calling the verifier's hash/Merkle helpers.
    def make_manifest(data):
        digest = hashlib.sha256(data).hexdigest()
        root = hashlib.sha256(("leaf|" + digest).encode()).hexdigest()
        return {"files": [{"path": "events.csv", "sha256": digest, "size": len(data)}],
                "merkle": {"root": root, "leaves": [digest]}}

    source = b"event_id,quantity\nsynthetic-event,10\n"
    altered = source.replace(b",10", b",99")
    manifest = make_manifest(source)
    cases = [
        ("valid", source, manifest, {}, 0),
        ("changed_data_unchanged_manifest", altered, manifest, {}, 1),
        ("changed_data_recomputed_manifest", altered, make_manifest(altered), {}, 0),
        ("extra_undeclared_file", source, manifest, {"undeclared.txt": b"not covered by manifest"}, 0),
        ("malformed_manifest_top_level_list", source, [], {}, "AttributeError"),
    ]
    missing = copy.deepcopy(manifest)
    missing["files"][0]["path"] = "missing.csv"
    cases.append(("declared_file_missing", source, missing, {}, 1))
    bad_leaves = copy.deepcopy(manifest)
    bad_leaves["merkle"]["leaves"] = ["0" * 64]
    cases.append(("inconsistent_leaves", source, bad_leaves, {}, 1))
    results = []
    with tempfile.TemporaryDirectory(prefix="regengine-qa-") as tmp:
        for name, data, case_manifest, extras, expected in cases:
            path = Path(tmp) / (name + ".zip")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("manifest.json", json.dumps(case_manifest))
                bundle.writestr("events.csv", data)
                for extra_path, extra_data in extras.items():
                    bundle.writestr(extra_path, extra_data)
            capture = io.StringIO()
            try:
                with contextlib.redirect_stdout(capture):
                    observed = verifier.verify_bundle(str(path))
            except Exception as exc:
                observed = type(exc).__name__
            results.append({"case": name, "observed": observed, "expected_after_inspection": expected,
                            "output": capture.getvalue().splitlines()})
            assert observed == expected, (name, observed, expected)

        sys.path.insert(0, str(ROOT / "services/ingestion"))
        from app.fda_export_service import (
            _generate_csv_v2, _build_completeness_summary,
            _build_chain_verification_payload, _build_fda_package,
        )
        event = {
            "id": "synthetic-event", "event_type": "shipping",
            "traceability_lot_code": "SYNTHETIC-LOT", "product_description": "Synthetic product",
            "quantity": 10, "unit_of_measure": "cases",
            "event_timestamp": "2026-08-31T00:00:00+00:00", "kdes": {},
            "sha256_hash": "a" * 64, "chain_hash": "b" * 64,
        }
        csv_text = _generate_csv_v2([event])
        csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
        completeness = _build_completeness_summary([event])
        chain = _build_chain_verification_payload(
            tenant_id="00000000-0000-4000-8000-000000000001", tlc="SYNTHETIC-LOT",
            events=[event], csv_hash=csv_hash, completeness_summary=completeness,
            chain_verification=SimpleNamespace(valid=True, chain_length=1, errors=[],
                                               checked_at="2026-08-31T00:00:00+00:00"),
        )
        package_bytes, metadata = _build_fda_package(
            events=[event], csv_content=csv_text, csv_hash=csv_hash, chain_payload=chain,
            completeness_summary=completeness, tenant_id="00000000-0000-4000-8000-000000000001",
            tlc="SYNTHETIC-LOT", query_start_date=None, query_end_date=None,
        )
        package_path = Path(tmp) / "real_helper_package.zip"
        package_path.write_bytes(package_bytes)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            status = verifier.verify_bundle(str(package_path))
        assert status == 1
        results.append({"case": "production_package_helper_to_public_sdk", "observed": status,
                        "output": capture.getvalue().splitlines(),
                        "manifest_file_fields": sorted(metadata["manifest"]["files"][0]),
                        "manifest_has_merkle": "merkle" in metadata["manifest"],
                        "package_sha256": metadata["package_hash"]})
        scales = []
        for count in (1, 10, 100, 1000, 10000):
            start = time.perf_counter()
            data = _generate_csv_v2([event] * count).encode()
            formatted = time.perf_counter() - start
            path = Path(tmp) / "scale.zip"
            start = time.perf_counter()
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("events.csv", data)
                bundle.writestr("manifest.json", json.dumps(make_manifest(data)))
            packaged = time.perf_counter() - start
            capture = io.StringIO()
            start = time.perf_counter()
            with contextlib.redirect_stdout(capture):
                status = verifier.verify_bundle(str(path))
            verified = time.perf_counter() - start
            assert status == 0
            scales.append({"rows": count, "csv_bytes": len(data), "zip_bytes": path.stat().st_size,
                           "format_seconds": formatted, "zip_seconds": packaged,
                           "verify_seconds": verified})

    tenant_checks = tenant_probe()
    print(json.dumps({"reality_level": 5, "dependencies": versions(),
                      "platform": {"system": os.uname().sysname, "machine": os.uname().machine},
                      "cases": results, "scales": scales,
                      "tenant_context_checks": tenant_checks,
                      "limits": "Synthetic repeated rows, one run per scale, no persistence/auth/network; timings are not production throughput. 100000 and 1000000 rows not materialized because observed API cap is 10000."}, indent=2))
    return 0


def tenant_probe():
    """Check the current primitive without the tests' stale SET LOCAL matcher."""
    from uuid import UUID, uuid4
    from tests.shared.test_canonical_persistence_hardening import (
        FakeSession, _FakeResult, _RowcountResult, _make_event,
    )
    from shared.canonical_event import IngestionRun, IngestionSource
    from shared.canonical_persistence.writer import CanonicalEventStore

    tenant = UUID("00000000-0000-4000-8000-000000000001")
    records = []
    for operation in ("persist_event", "persist_events_batch", "create_ingestion_run", "complete_ingestion_run"):
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _RowcountResult(rowcount=1))
        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        if operation == "persist_event":
            store.persist_event(_make_event(tenant_id=tenant))
        elif operation == "persist_events_batch":
            store.persist_events_batch([_make_event(tenant_id=tenant)])
        elif operation == "create_ingestion_run":
            store.create_ingestion_run(IngestionRun(
                id=uuid4(), tenant_id=tenant, source_system=IngestionSource.WEBHOOK_API,
                source_file_name="synthetic.csv", source_file_hash="a" * 64,
                source_file_size=10, record_count=1, mapper_version="v1",
                schema_version="v1", status="processing", initiated_by="synthetic-test",
            ))
        else:
            store.complete_ingestion_run(str(uuid4()), str(tenant), 1, 0)
        sql, params = session.calls[0]
        assert sql == "SELECT set_config('app.tenant_id', :tid, true)"
        assert params == {"tid": str(tenant)}
        records.append({"operation": operation, "first_sql": sql, "first_params": params})

    session = FakeSession()
    store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
    try:
        store.set_tenant_context("invalid-tenant")
        raise AssertionError("invalid tenant was accepted")
    except ValueError:
        assert not session.calls
    records.append({"operation": "invalid_uuid", "rejected_before_sql": True})
    try:
        store.persist_events_batch([_make_event(tenant_id=tenant), _make_event(tenant_id=uuid4())])
        raise AssertionError("mixed tenant batch was accepted")
    except ValueError:
        assert not session.calls
    records.append({"operation": "mixed_tenant_batch", "rejected_before_sql": True})
    return records


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "artifacts"
    raise SystemExit(existing_tests() if mode == "pytest" else artifact_probe())
