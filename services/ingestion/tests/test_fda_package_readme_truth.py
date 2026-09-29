"""Generated package instructions must distinguish failure from insufficient evidence."""

import hashlib
import io
import json
import zipfile

import pytest
from app.fda_export.formatters import build_package_response, generate_csv_and_hash
from app.fda_export.queries import _verify_chain_for_export
from app.fda_export_service import _build_completeness_summary
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.verification import CanonicalChainVerification


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,chain_passed,hashes_present,status,header",
    [
        ("canonical", True, True, "VERIFIED", "VERIFIED"),
        ("canonical", True, False, "PARTIAL", "VERIFIED"),
        ("canonical", False, True, "UNVERIFIED", "UNVERIFIED"),
        ("legacy", True, True, "UNVERIFIED", "UNVERIFIED"),
        (None, True, True, "UNVERIFIED", "UNVERIFIED"),
    ],
)
async def test_package_readme_explains_verification_scope(
    monkeypatch, source, chain_passed, hashes_present, status, header
):
    chain_result = CanonicalChainVerification(
        valid=chain_passed,
        chain_length=1,
        errors=[] if chain_passed else ["Chain hash mismatch"],
        checked_at="2026-09-29T00:00:00+00:00",
        store="canonical",
    )
    monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "1")
    monkeypatch.setattr(CanonicalEventStore, "verify_chain_canonical", lambda *args: chain_result)
    scoped_result = _verify_chain_for_export(None, None, "tenant", source=source)
    events = [{"sha256_hash": "a" * 64 if hashes_present else "", "chain_hash": "b" * 64 if hashes_present else ""}]
    csv_content, csv_hash = generate_csv_and_hash(events)
    response = build_package_response(
        events=events,
        csv_content=csv_content,
        export_hash=csv_hash,
        chain_verification=scoped_result,
        completeness_summary=_build_completeness_summary(events),
        tenant_id="tenant",
        tlc=None,
        start_date=None,
        end_date=None,
        filename="export.zip",
    )
    body = b"".join([chunk async for chunk in response.body_iterator])
    with zipfile.ZipFile(io.BytesIO(body)) as package:
        manifest = json.loads(package.read("manifest.json"))
        chain_name = next(name for name in package.namelist() if name.startswith("chain_verification_"))
        artifact = json.loads(package.read(chain_name))
        readme = package.read("README.txt").decode("utf-8")
        for entry in manifest["files"]:
            assert hashlib.sha256(package.read(entry["path"])).hexdigest() == entry["sha256"]

    assert chain_result.valid is chain_passed
    assert response.headers["x-chain-integrity"] == header
    assert response.headers["x-export-hash"] == csv_hash
    assert response.headers["x-package-hash"] == hashlib.sha256(body).hexdigest()
    assert artifact["verification_status"] == manifest["verification"]["status"] == status
    assert artifact["chain_verification"]["errors"] == scoped_result.errors
    assert "VERIFIED means the persisted chain check passed and row hashes are present." in readme
    assert "PARTIAL means the persisted chain check passed but one or more row hashes are missing." in readme
    assert "do not treat this package as verified." in readme
    if source != "canonical":
        assert artifact["chain_verification"]["valid"] is False
        assert any("not independently verified for this source" in error for error in scoped_result.errors)
        assert (
            "UNVERIFIED means the chain check failed or verification evidence is insufficient for the exported source"
            in readme
        )
    elif not chain_passed:
        assert artifact["chain_verification"]["valid"] is False
        assert "UNVERIFIED means the chain check failed" in readme
