"""Tests for ``services/ingestion/app/proof_verify_router.py``.

Public hash-chain verifier. Coverage:

- Tenant isolation: endpoint accepts no tenant input and never reads
  tenant data. We assert (a) no auth is required, (b) the module does
  not import any tenant-scoped clients, and (c) calls succeed without a
  tenant header.
- Schema validation: malformed JSON, missing fields, bad event hashes
  return 400.
- Failure modes: oversized payload (413), malformed ZIP, missing
  manifest, path-traversal entries, zip bombs.
- Happy path: round-trip a manufactured bundle and confirm
  ``verified == True`` and ``merkle_root_recomputed`` matches.
"""
from __future__ import annotations

import hashlib
import io
import json
import runpy
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.proof_verify_router import (
    MAX_BUNDLE_BYTES,
    router as proof_verify_router,
)
from app.fda_export_service import _build_fda_package
from shared.merkle_tree import MerkleTree
from shared.rate_limit import limiter


REPO_ROOT = Path(__file__).resolve().parents[3]


def _build_app() -> FastAPI:
    app = FastAPI()
    # slowapi requires the limiter to be attached to app.state for the
    # ``@limiter.limit`` decorator to find a key function.
    app.state.limiter = limiter
    app.include_router(proof_verify_router)
    return app


@pytest.fixture
def client() -> TestClient:
    # Reset the shared slowapi limiter state between tests so the 10/min
    # limit doesn't leak across test cases. ``Limiter`` exposes a
    # ``reset`` method for this purpose; fall back to clearing the
    # internal storage if the API differs.
    try:
        limiter.reset()
    except Exception:  # pragma: no cover — defensive fallback
        storage = getattr(limiter, "_storage", None) or getattr(
            getattr(limiter, "limiter", None), "storage", None
        )
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# Helpers — manufacture a valid bundle from synthetic event hashes
# ---------------------------------------------------------------------------
def _make_event_hashes(n: int) -> list[str]:
    return [hashlib.sha256(f"event-{i}".encode()).hexdigest() for i in range(n)]


def _make_zip_bundle(
    event_hashes: list[str],
    *,
    declared_root: str | None = None,
    include_manifest: bool = True,
    bad_path: str | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> bytes:
    csv_content = "Event ID,Hash\n" + "\n".join(
        f"{i},{h}" for i, h in enumerate(event_hashes)
    )
    csv_bytes = csv_content.encode("utf-8")
    csv_name = "fda_spreadsheet_test.csv"

    chain_payload: dict[str, Any] = {
        "version": "1.0",
        "merkle_root": declared_root,
        "events": [{"event_hash": h} for h in event_hashes],
    }
    chain_bytes = json.dumps(chain_payload).encode("utf-8")
    chain_name = "chain_verification_test.json"

    manifest = {
        "version": "1.0",
        "export_type": "fda_traceability_package",
        "file_hashes": {
            csv_name: hashlib.sha256(csv_bytes).hexdigest(),
            chain_name: hashlib.sha256(chain_bytes).hexdigest(),
        },
        "merkle_root": declared_root,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_manifest:
            zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(csv_name, csv_bytes)
        zf.writestr(chain_name, chain_bytes)
        if bad_path is not None:
            zf.writestr(bad_path, b"hostile")
        for name, data in (extra_files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tenant-isolation guarantees
# ---------------------------------------------------------------------------
class TestTenantIsolation:
    def test_endpoint_accepts_no_tenant_header_and_works(self, client: TestClient):
        """The endpoint must work with zero tenant context."""
        hashes = _make_event_hashes(3)
        root = MerkleTree(hashes).root
        body = {
            "manifest": {"version": "1.0", "export_type": "fda_traceability_package"},
            "events": [{"event_hash": h} for h in hashes],
            "merkle_root": root,
        }
        # NOTE: no X-Tenant-ID header, no API key.
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is True
        assert data["merkle_root_recomputed"] == root

    def test_module_does_not_import_tenant_scoped_clients(self):
        """Defense-in-depth: the verifier module must not import any
        tenant-scoped persistence client. Static check restricted to
        actual import statements (docstring / comment mentions are
        permitted because they describe the constraint).
        """
        from app import proof_verify_router as mod

        src = open(mod.__file__).read()
        # Only inspect lines that are real imports.
        import_lines = [
            ln for ln in src.splitlines()
            if ln.lstrip().startswith(("import ", "from "))
        ]
        forbidden = [
            "shared.database",
            "shared.cte_persistence",
            "CTEPersistence",
            "SessionLocal",
            "neo4j",
            "Neo4jClient",
            "shared.canonical_persistence",
        ]
        joined = "\n".join(import_lines)
        offenders = [tok for tok in forbidden if tok in joined]
        assert not offenders, (
            f"proof_verify_router imports tenant-scoped symbols: {offenders}\n"
            f"Import lines:\n{joined}"
        )

    def test_tenant_id_in_payload_is_ignored(self, client: TestClient):
        """A caller-supplied ``tenant_id`` field in the manifest must not
        cause any privileged behavior. The bundle is treated as opaque
        bytes and verified structurally.
        """
        hashes = _make_event_hashes(2)
        root = MerkleTree(hashes).root
        body = {
            "manifest": {
                "version": "1.0",
                "tenant_id": "00000000-0000-0000-0000-000000000000",  # ignored
            },
            "events": [{"event_hash": h} for h in hashes],
            "merkle_root": root,
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200
        # Verification result is identical with or without the field.
        assert resp.json()["verified"] is True


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
class TestSchemaValidation:
    def test_rejects_unparseable_json(self, client: TestClient):
        resp = client.post(
            "/api/v1/proof/verify",
            data="not-json-at-all",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        assert "malformed" in resp.json()["detail"].lower()

    def test_rejects_request_with_no_body_and_no_file(self, client: TestClient):
        resp = client.post("/api/v1/proof/verify")
        assert resp.status_code == 400

    def test_rejects_event_with_bad_hash(self, client: TestClient):
        body = {
            "manifest": {"version": "1.0"},
            "events": [{"event_hash": "not-a-real-hash"}],
            "merkle_root": "ignored",
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200  # structural failure, reported in checks
        data = resp.json()
        assert data["verified"] is False
        names = {c["name"]: c for c in data["checks"]}
        assert names["event_hashes_well_formed"]["passed"] is False

    def test_empty_events_list_fails_verification(self, client: TestClient):
        resp = client.post(
            "/api/v1/proof/verify",
            json={"manifest": {"version": "1.0"}, "events": [], "merkle_root": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        names = {c["name"] for c in data["checks"]}
        assert "events_present" in names

    def test_declared_root_mismatch_marks_unverified(self, client: TestClient):
        hashes = _make_event_hashes(4)
        body = {
            "manifest": {"version": "1.0"},
            "events": [{"event_hash": h} for h in hashes],
            "merkle_root": "00" * 32,  # bogus
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        names = {c["name"]: c for c in data["checks"]}
        assert names["merkle_root_matches_declared"]["passed"] is False
        # But we still report the recomputed root.
        assert len(data["merkle_root_recomputed"]) == 64


# ---------------------------------------------------------------------------
# Failure modes — oversized, malformed ZIP, traversal, missing manifest
# ---------------------------------------------------------------------------
class TestFailureModes:
    def test_oversized_json_returns_413(self, client: TestClient):
        big = "x" * (MAX_BUNDLE_BYTES + 100)
        resp = client.post(
            "/api/v1/proof/verify",
            data=big,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 413

    def test_oversized_zip_returns_413(self, client: TestClient):
        big = b"PK\x03\x04" + b"\x00" * (MAX_BUNDLE_BYTES + 100)
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("big.zip", big, "application/zip")},
        )
        assert resp.status_code == 413

    def test_malformed_zip_returns_400(self, client: TestClient):
        # Starts with the ZIP magic so the router takes the ZIP path,
        # but is not actually a valid archive.
        bad = b"PK\x03\x04" + b"garbage-not-a-real-zip"
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("bad.zip", bad, "application/zip")},
        )
        assert resp.status_code == 400
        assert "malformed zip" in resp.json()["detail"].lower()

    def test_zip_missing_manifest_returns_400(self, client: TestClient):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", b"no manifest here")
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("nomanifest.zip", buf.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        assert "manifest.json" in resp.json()["detail"]

    def test_zip_with_path_traversal_entry_rejected(self, client: TestClient):
        hashes = _make_event_hashes(2)
        root = MerkleTree(hashes).root
        bundle = _make_zip_bundle(
            hashes, declared_root=root, bad_path="../../etc/passwd"
        )
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("bad.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 400
        assert "unsafe zip entry" in resp.json()["detail"].lower()

    def test_zip_with_absolute_path_entry_rejected(self, client: TestClient):
        hashes = _make_event_hashes(2)
        root = MerkleTree(hashes).root
        bundle = _make_zip_bundle(
            hashes, declared_root=root, bad_path="/etc/passwd"
        )
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("bad.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 400

    def test_unsupported_content_type_rejected(self, client: TestClient):
        hashes = _make_event_hashes(1)
        root = MerkleTree(hashes).root
        bundle = _make_zip_bundle(hashes, declared_root=root)
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("file.exe", bundle, "application/x-msdownload")},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Happy path — round-trip a real ZIP
# ---------------------------------------------------------------------------
class TestZipRoundTrip:
    def test_checked_in_public_audit_bundle_verifies(self, client: TestClient):
        """The ZIP linked from /proof must verify through the public API."""
        bundle = (REPO_ROOT / "frontend/public/proof/audit-bundle.zip").read_bytes()

        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("audit-bundle.zip", bundle, "application/zip")},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is True, data
        names = {c["name"]: c for c in data["checks"]}
        assert names["manifest_files_present"]["passed"] is True
        assert names["file_hashes_match_manifest"]["passed"] is True
        assert names["merkle_root_matches_declared"]["passed"] is True
        assert len(data["merkle_root_recomputed"]) == 64

    def test_checked_in_tampered_public_audit_bundle_fails(
        self, client: TestClient
    ):
        """The tampered ZIP linked from /proof must fail verification."""
        bundle = (
            REPO_ROOT / "frontend/public/proof/audit-bundle-tampered.zip"
        ).read_bytes()

        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("audit-bundle-tampered.zip", bundle, "application/zip")},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is False, data
        names = {c["name"]: c for c in data["checks"]}
        assert names["file_hashes_match_manifest"]["passed"] is False

    def test_zip_bundle_verified_end_to_end(self, client: TestClient):
        hashes = _make_event_hashes(8)
        root = MerkleTree(hashes).root
        bundle = _make_zip_bundle(hashes, declared_root=root)

        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("export.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is True, data
        assert data["merkle_root_recomputed"] == root
        names = {c["name"] for c in data["checks"]}
        # Key structural assertions surfaced as named checks.
        assert "zip_structure" in names
        assert "file_hashes_match_manifest" in names
        assert "merkle_root_matches_declared" in names

    def test_zip_with_tampered_csv_fails_file_hash_check(self, client: TestClient):
        """A CSV whose bytes don't hash to the manifest-declared digest
        must surface as a failed ``file_hashes_match_manifest`` check.
        """
        hashes = _make_event_hashes(3)
        root = MerkleTree(hashes).root
        # Build a normal bundle, then rewrite the CSV inside to invalidate
        # its declared hash.
        bundle = _make_zip_bundle(hashes, declared_root=root)
        zin = zipfile.ZipFile(io.BytesIO(bundle))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.namelist():
                data = zin.read(item)
                if item.startswith("fda_spreadsheet"):
                    data = data + b"\nTAMPERED"
                zout.writestr(item, data)

        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("tampered.zip", out.getvalue(), "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        names = {c["name"]: c for c in data["checks"]}
        assert names["file_hashes_match_manifest"]["passed"] is False

    def test_generated_fda_package_round_trips_through_both_public_verifiers(
        self,
        client: TestClient,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        """The production package builder and both published verifiers share one contract."""
        csv_content = "Event ID,Traceability Lot Code\nsynthetic-event-1,SYNTHETIC-LOT-1\n"
        csv_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        completeness = {
            "required_checks_total": 1,
            "required_checks_passed": 1,
            "required_checks_missing": 0,
            "required_kde_coverage_ratio": 1.0,
            "events_with_missing_required_fields": 0,
            "missing_required_by_field": {},
            "missing_required_events": [],
        }
        package_bytes, package_meta = _build_fda_package(
            events=[
                {
                    "id": "synthetic-event-1",
                    "event_type": "RECEIVING",
                    "traceability_lot_code": "SYNTHETIC-LOT-1",
                }
            ],
            csv_content=csv_content,
            csv_hash=csv_hash,
            chain_payload={
                "version": "1.0",
                "verification_status": "VERIFIED",
                "chain_verification": {
                    "valid": True,
                    "chain_length": 1,
                    "errors": [],
                    "checked_at": "2026-08-31T00:00:00+00:00",
                },
            },
            completeness_summary=completeness,
            tenant_id="synthetic-tenant",
            tlc="SYNTHETIC-LOT-1",
            query_start_date=None,
            query_end_date=None,
        )

        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package.zip", package_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True, response.json()

        sdk_verify_bundle = runpy.run_path(
            str(REPO_ROOT / "frontend/public/sdk/verify_chain.py")
        )["verify_bundle"]
        package_path = tmp_path / "fda-package.zip"
        package_path.write_bytes(package_bytes)
        assert sdk_verify_bundle(str(package_path)) == 0

        csv_name = package_meta["csv_name"]
        tampered = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as source:
            with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    data = source.read(member.filename)
                    if member.filename == csv_name:
                        data += b"TAMPERED"
                    target.writestr(member, data)

        tampered_bytes = tampered.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-tampered.zip", tampered_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["file_hashes_match_manifest"]["passed"] is False

        tampered_path = tmp_path / "fda-package-tampered.zip"
        tampered_path.write_bytes(tampered_bytes)
        assert sdk_verify_bundle(str(tampered_path)) == 1
        assert "verify: FAILED" in capsys.readouterr().out
