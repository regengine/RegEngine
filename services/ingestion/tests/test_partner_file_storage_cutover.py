"""Unit tests for first-file partner-uploads cutover (synthetic data only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from services.ingestion.app import partner_file_storage as pfs


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def scalar_one(self):
        return self._row


class _FakeDB:
    def __init__(self):
        self.statements: List[str] = []
        self.params: List[Dict[str, Any]] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        return _FakeResult()

    def begin_nested(self):
        from contextlib import nullcontext

        return nullcontext()


@pytest.fixture
def tenant_id() -> str:
    return str(uuid4())


def test_tenant_object_key_is_tenant_scoped(tenant_id: str) -> None:
    engagement = str(uuid4())
    key = pfs.tenant_object_key(
        tenant_id=tenant_id,
        engagement_id=engagement,
        filename="synth-partner.csv",
        object_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert key.startswith(f"tenants/{tenant_id}/engagements/{engagement}/")
    assert key.endswith("-synth-partner.csv")
    assert ".." not in key


def test_persist_uses_partner_uploads_and_null_raw_bytes(monkeypatch, tenant_id: str) -> None:
    put_calls: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []

    monkeypatch.setattr(pfs, "PARTNER_UPLOADS_BUCKET", "partner-uploads")

    def _is_configured() -> bool:
        return True

    def _put_bytes(bucket, key, content, content_type="application/octet-stream"):
        put_calls.append(
            {"bucket": bucket, "key": key, "size": len(content), "content_type": content_type}
        )
        return f"s3://{bucket}/{key}"

    # Patch through the import sites used inside persist_partner_upload
    import services.ingestion.app.s3_utils as s3_utils

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", _is_configured)
    monkeypatch.setattr(s3_utils, "put_bytes", _put_bytes)

    import services.ingestion.app.remediation.audit_utils as audit_utils

    def _audit(db, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(audit_utils, "audit_event", _audit)

    db = _FakeDB()
    run_id = str(uuid4())
    content = b"lot,qty\nsynth-1,1\n"  # synthetic only
    result = pfs.persist_partner_upload(
        db,
        tenant_id=tenant_id,
        engagement_id=run_id,
        content=content,
        filename="synth-partner.csv",
        content_type="text/csv",
        uploaded_by=None,
        ingestion_run_id=run_id,
    )

    assert result["used_object_storage"] is True
    assert result["storage_url"].startswith("s3://partner-uploads/tenants/")
    assert put_calls and put_calls[0]["bucket"] == "partner-uploads"
    # partner_files INSERT then manifest_blobs INSERT
    assert any("INSERT INTO public.partner_files" in s for s in db.statements)
    blob_params = next(p for p, s in zip(db.params, db.statements) if "manifest_blobs" in s)
    assert blob_params["raw_bytes"] is None
    assert blob_params["storage_url"].startswith("s3://partner-uploads/")
    assert audits and audits[0]["event_type"] == "partner_file.upload"
    assert audits[0]["metadata"]["used_object_storage"] is True


def test_persist_falls_back_to_bytea_with_explicit_local_flag(monkeypatch, tenant_id: str) -> None:
    import services.ingestion.app.s3_utils as s3_utils
    import services.ingestion.app.remediation.audit_utils as audit_utils

    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("REGENGINE_ALLOW_MANIFEST_BYTEA_FALLBACK", "1")
    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: False)
    monkeypatch.setattr(audit_utils, "audit_event", lambda *a, **k: None)

    db = _FakeDB()
    run_id = str(uuid4())
    content = b"a,b\n1,2\n"
    result = pfs.persist_partner_upload(
        db,
        tenant_id=tenant_id,
        engagement_id=run_id,
        content=content,
        filename="local.csv",
        content_type="text/csv",
        uploaded_by="system",
        ingestion_run_id=run_id,
    )
    assert result["used_object_storage"] is False
    assert result["storage_url"] is None
    assert not any("partner_files" in s for s in db.statements)
    blob_params = next(p for p, s in zip(db.params, db.statements) if "manifest_blobs" in s)
    assert blob_params["raw_bytes"] == content


def test_persist_fail_closed_without_storage_or_flag(monkeypatch, tenant_id: str) -> None:
    """Without object storage and without the local flag, refuse the upload."""
    import services.ingestion.app.s3_utils as s3_utils
    from fastapi import HTTPException

    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.delenv("REGENGINE_ALLOW_MANIFEST_BYTEA_FALLBACK", raising=False)
    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: False)

    db = _FakeDB()
    run_id = str(uuid4())
    with pytest.raises(HTTPException) as ei:
        pfs.persist_partner_upload(
            db,
            tenant_id=tenant_id,
            engagement_id=run_id,
            content=b"a,b\n1,2\n",
            filename="local.csv",
            content_type="text/csv",
            uploaded_by="system",
            ingestion_run_id=run_id,
        )
    assert ei.value.status_code == 503
    assert not db.statements


def test_persist_fail_closed_in_production_even_with_flag(monkeypatch, tenant_id: str) -> None:
    """Production never allows the bytea fallback, flag or not."""
    import services.ingestion.app.s3_utils as s3_utils
    from fastapi import HTTPException

    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_ALLOW_MANIFEST_BYTEA_FALLBACK", "1")
    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: False)

    db = _FakeDB()
    run_id = str(uuid4())
    with pytest.raises(HTTPException) as ei:
        pfs.persist_partner_upload(
            db,
            tenant_id=tenant_id,
            engagement_id=run_id,
            content=b"a,b\n1,2\n",
            filename="local.csv",
            content_type="text/csv",
            uploaded_by="system",
            ingestion_run_id=run_id,
        )
    assert ei.value.status_code == 503


def test_resolve_manifest_raw_bytes_prefers_bytea() -> None:
    assert pfs.resolve_manifest_raw_bytes(raw_bytes=b"abc", storage_url=None) == b"abc"


def test_resolve_manifest_raw_bytes_fetches_storage(monkeypatch) -> None:
    import services.ingestion.app.s3_utils as s3_utils

    monkeypatch.setattr(
        s3_utils,
        "get_raw_document",
        lambda key, bucket: {"content": b"from-s3"},
    )
    out = pfs.resolve_manifest_raw_bytes(
        raw_bytes=None,
        storage_url="s3://partner-uploads/tenants/t/engagements/e/obj-file.csv",
    )
    assert out == b"from-s3"
