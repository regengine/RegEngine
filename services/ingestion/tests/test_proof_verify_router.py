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
from app.fda_export_service import _build_fda_package
from app.proof_verify_router import (
    MAX_BUNDLE_BYTES,
    router as proof_verify_router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
        storage = getattr(limiter, "_storage", None) or getattr(getattr(limiter, "limiter", None), "storage", None)
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
    csv_content = "Event ID,Hash\n" + "\n".join(f"{i},{h}" for i, h in enumerate(event_hashes))
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
        import_lines = [ln for ln in src.splitlines() if ln.lstrip().startswith(("import ", "from "))]
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
        assert not offenders, f"proof_verify_router imports tenant-scoped symbols: {offenders}\nImport lines:\n{joined}"

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


def _rewrite_legacy_bundle(
    bundle: bytes,
    *,
    mutate_manifest: Any = None,
    drop_members: set[str] | None = None,
    add_members: dict[str, bytes] | None = None,
    duplicate_member: str | None = None,
) -> bytes:
    """Re-zip a legacy ``file_hashes`` bundle with targeted structural edits."""
    zin = zipfile.ZipFile(io.BytesIO(bundle))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item in (drop_members or set()):
                continue
            data = zin.read(item)
            if item == "manifest.json" and mutate_manifest is not None:
                manifest = json.loads(data)
                manifest = mutate_manifest(manifest) or manifest
                data = json.dumps(manifest).encode("utf-8")
            zout.writestr(item, data)
        for name, data in (add_members or {}).items():
            zout.writestr(name, data)
        if duplicate_member is not None:
            with pytest.warns(UserWarning, match="Duplicate name"):
                zout.writestr(duplicate_member, b"forged duplicate")
    return out.getvalue()


def _checks(resp_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in resp_json["checks"]}


# ---------------------------------------------------------------------------
# Fail-closed — a structurally incomplete bundle must never verify
# ---------------------------------------------------------------------------
class TestFailClosed:
    """Optional commitments and partial file coverage are not verification.

    Regression coverage for the finding that a missing Merkle anchor was
    recorded as ``passed=True`` and that the legacy ZIP verifier skipped
    undeclared / missing members before computing ``all(checks)``.
    """

    def test_json_missing_declared_root_is_unverified(self, client: TestClient):
        hashes = _make_event_hashes(3)
        body = {"manifest": {"version": "1.0"}, "events": [{"event_hash": h} for h in hashes]}
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is False
        assert _checks(data)["merkle_root_matches_declared"]["passed"] is False
        # Recomputed root is still reported for the caller's information.
        assert data["merkle_root_recomputed"] == MerkleTree(hashes).root

    @pytest.mark.parametrize("root", ["", None])
    def test_json_empty_or_null_root_is_unverified(self, client: TestClient, root: str | None):
        hashes = _make_event_hashes(2)
        body = {
            "manifest": {"version": "1.0"},
            "events": [{"event_hash": h} for h in hashes],
            "merkle_root": root,
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert _checks(data)["merkle_root_matches_declared"]["passed"] is False

    @pytest.mark.parametrize(
        "root",
        [
            "z" * 64,  # 64 non-hex characters
            "G" * 64,
            MerkleTree(_make_event_hashes(2)).root.upper(),  # correct digits, wrong case
            "ab" * 31,  # too short
            "ab" * 33,  # too long
        ],
    )
    def test_json_non_hex_root_is_rejected(self, client: TestClient, root: str):
        hashes = _make_event_hashes(2)
        body = {
            "manifest": {"version": "1.0"},
            "events": [{"event_hash": h} for h in hashes],
            "merkle_root": root,
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        check = _checks(data)["merkle_root_matches_declared"]
        assert check["passed"] is False

    def test_json_non_hex_event_hash_is_rejected(self, client: TestClient):
        body = {
            "manifest": {"version": "1.0"},
            "events": [{"event_hash": "z" * 64}],
            "merkle_root": "00" * 32,
        }
        resp = client.post("/api/v1/proof/verify", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert _checks(data)["event_hashes_well_formed"]["passed"] is False

    def _post_zip(self, client: TestClient, bundle: bytes) -> Any:
        return client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("bundle.zip", bundle, "application/zip")},
        )

    def test_legacy_zip_baseline_verifies(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)
        data = self._post_zip(client, bundle).json()
        assert data["verified"] is True, data
        assert _checks(data)["manifest_covers_bundle_members"]["passed"] is True

    def test_legacy_zip_missing_declared_file_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)
        tampered = _rewrite_legacy_bundle(bundle, drop_members={"fda_spreadsheet_test.csv"})
        resp = self._post_zip(client, tampered)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verified"] is False
        check = _checks(data)["manifest_covers_bundle_members"]
        assert check["passed"] is False
        assert "fda_spreadsheet_test.csv" in check["detail"]

    def test_legacy_zip_declared_but_absent_entry_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)

        def add_phantom(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest["file_hashes"]["phantom.csv"] = "00" * 32
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=add_phantom)
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        assert _checks(data)["manifest_covers_bundle_members"]["passed"] is False

    def test_legacy_zip_undeclared_extra_member_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)
        tampered = _rewrite_legacy_bundle(bundle, add_members={"smuggled.csv": b"not in manifest"})
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        check = _checks(data)["manifest_covers_bundle_members"]
        assert check["passed"] is False
        assert "smuggled.csv" in check["detail"]

    def test_legacy_zip_duplicate_member_rejected(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)
        tampered = _rewrite_legacy_bundle(bundle, duplicate_member="fda_spreadsheet_test.csv")
        resp = self._post_zip(client, tampered)
        assert resp.status_code == 400
        assert "duplicate ZIP entries" in resp.json()["detail"]

    def test_legacy_zip_unsafe_declared_path_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)

        def add_traversal(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest["file_hashes"]["../escape.csv"] = "00" * 32
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=add_traversal)
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        check = _checks(data)["manifest_covers_bundle_members"]
        assert check["passed"] is False
        assert "../escape.csv" in check["detail"]

    def test_legacy_zip_non_hex_file_digest_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)

        def corrupt_digest(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest["file_hashes"]["fda_spreadsheet_test.csv"] = "z" * 64
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=corrupt_digest)
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        assert _checks(data)["manifest_covers_bundle_members"]["passed"] is False

    def test_legacy_zip_without_file_hashes_map_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)

        def drop_map(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest.pop("file_hashes")
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=drop_map)
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        assert _checks(data)["manifest_covers_bundle_members"]["passed"] is False

    def test_legacy_zip_malformed_file_hashes_shape_fails(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)

        def as_list(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest["file_hashes"] = list(manifest["file_hashes"].values())
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=as_list)
        data = self._post_zip(client, tampered).json()
        assert data["verified"] is False
        assert _checks(data)["manifest_covers_bundle_members"]["passed"] is False

    def test_legacy_zip_missing_root_is_unverified(self, client: TestClient):
        hashes = _make_event_hashes(4)
        bundle = _make_zip_bundle(hashes, declared_root=None)
        data = self._post_zip(client, bundle).json()
        assert data["verified"] is False
        assert _checks(data)["merkle_root_matches_declared"]["passed"] is False
        assert data["merkle_root_recomputed"] == MerkleTree(hashes).root

    def test_zip_manifest_that_is_not_an_object_returns_400(self, client: TestClient):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(["not", "an", "object"]))
        resp = self._post_zip(client, buf.getvalue())
        assert resp.status_code == 400
        assert "JSON object" in resp.json()["detail"]

    def test_zip_chain_artifact_that_is_not_an_object_returns_400(self, client: TestClient):
        hashes = _make_event_hashes(2)
        bundle = _make_zip_bundle(hashes, declared_root=MerkleTree(hashes).root)
        zin = zipfile.ZipFile(io.BytesIO(bundle))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zout:
            for item in zin.namelist():
                data = zin.read(item)
                if item.startswith("chain_verification"):
                    data = json.dumps([1, 2, 3]).encode("utf-8")
                zout.writestr(item, data)
        resp = self._post_zip(client, out.getvalue())
        assert resp.status_code == 400, resp.text
        assert "chain_verification" in resp.json()["detail"]

    def test_legacy_zip_non_object_summary_and_chain_result_do_not_crash(self, client: TestClient):
        hashes = _make_event_hashes(2)
        bundle = _make_zip_bundle(hashes, declared_root=None)

        def hostile_shapes(manifest: dict[str, Any]) -> dict[str, Any]:
            manifest["summary"] = ["not", "a", "dict"]
            manifest["events"] = {"not": "a list"}
            return manifest

        tampered = _rewrite_legacy_bundle(bundle, mutate_manifest=hostile_shapes)
        resp = self._post_zip(client, tampered)
        assert resp.status_code == 200, resp.text
        assert resp.json()["verified"] is False


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
        bundle = _make_zip_bundle(hashes, declared_root=root, bad_path="../../etc/passwd")
        resp = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("bad.zip", bundle, "application/zip")},
        )
        assert resp.status_code == 400
        assert "unsafe zip entry" in resp.json()["detail"].lower()

    def test_zip_with_absolute_path_entry_rejected(self, client: TestClient):
        hashes = _make_event_hashes(2)
        root = MerkleTree(hashes).root
        bundle = _make_zip_bundle(hashes, declared_root=root, bad_path="/etc/passwd")
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
def _sdk_merkle_root(file_hashes: list[str]) -> str:
    sdk = runpy.run_path(str(REPO_ROOT / "frontend/public/sdk/verify_chain.py"))
    return sdk["_merkle_root"](file_hashes)


def _make_generic_files_bundle() -> bytes:
    """Build a files[]/merkle-style bundle in-test (no checked-in fixture)."""
    payload = b"generic-bundle-test-file\n"
    file_hash = hashlib.sha256(payload).hexdigest()
    manifest = {
        "version": "1.0",
        "files": [{"path": "evidence.txt", "size": len(payload), "sha256": file_hash}],
        "merkle": {"leaves": [file_hash], "root": _sdk_merkle_root([file_hash])},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("evidence.txt", payload)
    return buf.getvalue()


class TestZipRoundTrip:
    def test_generic_bundle_may_use_unrelated_verification_metadata(
        self,
        client: TestClient,
        tmp_path: Path,
    ):
        """Only FDA markers activate persisted-chain status semantics."""
        original = _make_generic_files_bundle()
        modified = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original), "r") as source:
            with zipfile.ZipFile(modified, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    data = source.read(member.filename)
                    if member.filename == "manifest.json":
                        manifest = json.loads(data)
                        manifest["verification"] = {"scheme": "external-example"}
                        data = json.dumps(manifest).encode("utf-8")
                    target.writestr(member, data)

        bundle = modified.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("generic-bundle.zip", bundle, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True, response.json()

        sdk_verify_bundle = runpy.run_path(str(REPO_ROOT / "frontend/public/sdk/verify_chain.py"))["verify_bundle"]
        bundle_path = tmp_path / "generic-bundle.zip"
        bundle_path.write_bytes(bundle)
        assert sdk_verify_bundle(str(bundle_path)) == 0

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

        def chain_payload(
            status: str,
            *,
            valid: bool,
            missing_record_hashes: int = 0,
            missing_chain_hashes: int = 0,
        ) -> dict[str, Any]:
            return {
                "version": "1.0",
                "verification_status": status,
                "chain_verification": {
                    "valid": valid,
                    "chain_length": 1,
                    "errors": [] if valid else ["synthetic broken link"],
                    "checked_at": "2026-08-31T00:00:00+00:00",
                },
                "row_hash_coverage": {
                    "records_with_hash": 1 - missing_record_hashes,
                    "records_with_chain_hash": 1 - missing_chain_hashes,
                    "missing_record_hashes": missing_record_hashes,
                    "missing_chain_hashes": missing_chain_hashes,
                },
            }

        package_args = {
            "events": [
                {
                    "id": "synthetic-event-1",
                    "event_type": "RECEIVING",
                    "traceability_lot_code": "SYNTHETIC-LOT-1",
                }
            ],
            "csv_content": csv_content,
            "csv_hash": csv_hash,
            "completeness_summary": completeness,
            "tenant_id": "synthetic-tenant",
            "tlc": "SYNTHETIC-LOT-1",
            "query_start_date": None,
            "query_end_date": None,
        }
        package_bytes, package_meta = _build_fda_package(
            **package_args,
            chain_payload=chain_payload("VERIFIED", valid=True),
        )

        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package.zip", package_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True, response.json()

        sdk_verify_bundle = runpy.run_path(str(REPO_ROOT / "frontend/public/sdk/verify_chain.py"))["verify_bundle"]
        package_path = tmp_path / "fda-package.zip"
        package_path.write_bytes(package_bytes)
        assert sdk_verify_bundle(str(package_path)) == 0

        partial_bytes, _ = _build_fda_package(
            **package_args,
            chain_payload=chain_payload(
                "PARTIAL",
                valid=True,
                missing_record_hashes=1,
            ),
        )
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-partial.zip", partial_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True, response.json()
        partial_path = tmp_path / "fda-package-partial.zip"
        partial_path.write_bytes(partial_bytes)
        assert sdk_verify_bundle(str(partial_path)) == 0

        unverified_bytes, _ = _build_fda_package(
            **package_args,
            chain_payload=chain_payload("UNVERIFIED", valid=False),
        )
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-unverified.zip", unverified_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["package_chain_metadata_consistent"]["passed"] is True
        assert checks["package_persisted_chain_acceptable"]["passed"] is False
        unverified_path = tmp_path / "fda-package-unverified.zip"
        unverified_path.write_bytes(unverified_bytes)
        assert sdk_verify_bundle(str(unverified_path)) == 1

        # The manifest is not one of its own Merkle leaves. Changing only its
        # summary must still fail because the hashed chain artifact disagrees.
        inconsistent = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(unverified_bytes), "r") as source:
            with zipfile.ZipFile(inconsistent, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    data = source.read(member.filename)
                    if member.filename == "manifest.json":
                        manifest = json.loads(data)
                        manifest["verification"]["status"] = "VERIFIED"
                        manifest["verification"]["chain_valid"] = True
                        data = json.dumps(manifest).encode("utf-8")
                    target.writestr(member, data)
        inconsistent_bytes = inconsistent.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-inconsistent.zip", inconsistent_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["package_chain_metadata_consistent"]["passed"] is False
        inconsistent_path = tmp_path / "fda-package-inconsistent.zip"
        inconsistent_path.write_bytes(inconsistent_bytes)
        assert sdk_verify_bundle(str(inconsistent_path)) == 1

        missing_summary = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(unverified_bytes), "r") as source:
            with zipfile.ZipFile(missing_summary, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    data = source.read(member.filename)
                    if member.filename == "manifest.json":
                        manifest = json.loads(data)
                        del manifest["verification"]
                        data = json.dumps(manifest).encode("utf-8")
                    target.writestr(member, data)
        missing_summary_bytes = missing_summary.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={
                "bundle": (
                    "fda-package-missing-verification.zip",
                    missing_summary_bytes,
                    "application/zip",
                )
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["package_chain_metadata_consistent"]["passed"] is False
        missing_summary_path = tmp_path / "fda-package-missing-verification.zip"
        missing_summary_path.write_bytes(missing_summary_bytes)
        assert sdk_verify_bundle(str(missing_summary_path)) == 1

        unlisted = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as source:
            with zipfile.ZipFile(unlisted, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    target.writestr(member, source.read(member.filename))
                target.writestr("fda_spreadsheet_forged.csv", b"forged evidence")
        unlisted_bytes = unlisted.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-unlisted.zip", unlisted_bytes, "application/zip")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["manifest_covers_bundle_members"]["passed"] is False
        unlisted_path = tmp_path / "fda-package-unlisted.zip"
        unlisted_path.write_bytes(unlisted_bytes)
        assert sdk_verify_bundle(str(unlisted_path)) == 1

        duplicate = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as source:
            with zipfile.ZipFile(duplicate, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    target.writestr(member, source.read(member.filename))
                with pytest.warns(UserWarning, match="Duplicate name"):
                    target.writestr(package_meta["csv_name"], b"forged duplicate evidence")
        duplicate_bytes = duplicate.getvalue()
        response = client.post(
            "/api/v1/proof/verify",
            files={"bundle": ("fda-package-duplicate.zip", duplicate_bytes, "application/zip")},
        )
        assert response.status_code == 400, response.text
        assert "duplicate ZIP entries" in response.json()["detail"]
        duplicate_path = tmp_path / "fda-package-duplicate.zip"
        duplicate_path.write_bytes(duplicate_bytes)
        assert sdk_verify_bundle(str(duplicate_path)) == 1

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
        output = capsys.readouterr().out
        assert "verify: FAILED" in output
        assert "result: bundle UNVERIFIED" in output
        assert "result: bundle INVALID" in output


class TestEvidenceContextMember:
    """S7: the evidence_context member is covered by both public verifiers."""

    def _package(self) -> bytes:
        csv_content = "Event ID,Traceability Lot Code\nsynthetic-event-1,SYNTHETIC-LOT-1\n"
        package_bytes, _ = _build_fda_package(
            events=[{"id": "synthetic-event-1", "event_type": "RECEIVING", "traceability_lot_code": "SYNTHETIC-LOT-1"}],
            csv_content=csv_content,
            csv_hash=hashlib.sha256(csv_content.encode("utf-8")).hexdigest(),
            chain_payload={
                "version": "1.0",
                "verification_status": "VERIFIED",
                "chain_verification": {"valid": True, "chain_length": 1, "errors": [], "checked_at": "2026-08-31T00:00:00+00:00"},
                "row_hash_coverage": {
                    "records_with_hash": 1,
                    "records_with_chain_hash": 1,
                    "missing_record_hashes": 0,
                    "missing_chain_hashes": 0,
                },
            },
            completeness_summary={
                "required_kde_coverage_ratio": 1.0,
                "events_with_missing_required_fields": 0,
                "missing_required_by_field": {},
                "missing_required_events": [],
            },
            tenant_id="synthetic-tenant",
            tlc="SYNTHETIC-LOT-1",
            query_start_date=None,
            query_end_date=None,
            rule_versions={"catalog_status": "ok", "catalog": {}, "evaluated": [], "evaluated_status": "ok", "enforcement_mode": "off"},
            coverage_gate_bypassed=False,
        )
        return package_bytes

    @staticmethod
    def _rewrite(package_bytes: bytes, member_prefix: str, mutate) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as source:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    data = source.read(member.filename)
                    if member.filename.startswith(member_prefix):
                        data = mutate(data)
                    target.writestr(member, data)
        return out.getvalue()

    def test_member_present_and_package_verifies(self, client: TestClient, tmp_path: Path):
        package_bytes = self._package()
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as zf:
            names = zf.namelist()
            evidence = [n for n in names if n.startswith("evidence_context_")]
            assert len(evidence) == 1
            manifest = json.loads(zf.read("manifest.json"))
        assert evidence[0] in {entry["path"] for entry in manifest["files"]}

        response = client.post("/api/v1/proof/verify", files={"bundle": ("p.zip", package_bytes, "application/zip")})
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True, response.json()

        sdk_verify_bundle = runpy.run_path(str(REPO_ROOT / "frontend/public/sdk/verify_chain.py"))["verify_bundle"]
        path = tmp_path / "p.zip"
        path.write_bytes(package_bytes)
        assert sdk_verify_bundle(str(path)) == 0

    def test_tampered_known_gaps_fail_both_verifiers(self, client: TestClient, tmp_path: Path, capsys):
        """A same-size edit inside the member is rejected by the hash check, not the size check."""

        def _flip(data: bytes) -> bytes:
            context = json.loads(data)
            status = context["known_gaps"]["verification_status"]
            assert isinstance(status, str) and status
            context["known_gaps"]["verification_status"] = status[:-1] + ("X" if status[-1] != "X" else "Y")
            mutated = json.dumps(context, indent=2, sort_keys=True).encode("utf-8")
            assert len(mutated) == len(data), "the mutation must keep the serialized size"
            return mutated

        tampered = self._rewrite(self._package(), "evidence_context_", _flip)
        response = client.post("/api/v1/proof/verify", files={"bundle": ("t.zip", tampered, "application/zip")})
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False
        checks = {check["name"]: check for check in response.json()["checks"]}
        assert checks["file_hashes_match_manifest"]["passed"] is False
        detail = checks["file_hashes_match_manifest"]["detail"]
        assert "hash_mismatched=['evidence_context_" in detail
        assert "size_mismatched=[]" in detail

        sdk_verify_bundle = runpy.run_path(str(REPO_ROOT / "frontend/public/sdk/verify_chain.py"))["verify_bundle"]
        path = tmp_path / "t.zip"
        path.write_bytes(tampered)
        assert sdk_verify_bundle(str(path)) == 1
        output = capsys.readouterr().out
        assert "sha256 mismatch" in output
        assert "!= declared" not in output, "the SDK verifier must reject on the hash, not the size"
