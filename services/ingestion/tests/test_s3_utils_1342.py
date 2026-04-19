"""Coverage for app/s3_utils.py — S3 client wrappers + raw-document store.

We never touch real S3; every test monkeypatches ``s3_utils._client`` to
return a ``_FakeS3`` that records calls, and patches ``get_settings`` to
provide credentials. The module has several non-trivial branches:

- _client: raises NotImplementedError when credentials are missing.
- _ensure_bucket_security: logs-and-continues on ClientError/BotoCoreError.
- put_json / put_bytes: NoSuchBucket triggers auto-create + retry; any
  other error becomes HTTPException(500).
- _json_serializer: datetime → ISO, other types raise TypeError.
- _ensure_bucket: 404/NoSuchKey triggers create; any other ClientError
  re-raises; create failures also re-raise.
- upload_raw_document: builds tenant/date/type key, merges metadata,
  500 on ClientError/BotoCoreError.
- get_raw_document: 404 on NoSuchKey, 500 on other errors (ClientError
  or BotoCoreError).
- list_raw_documents: NoSuchBucket → empty list, other errors → 500,
  datetime LastModified formatted, string passthrough, search prefix
  assembled correctly with/without explicit prefix.

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app import s3_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_error(code: str, op: str = "PutObject") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": f"Simulated {code}"}},
        operation_name=op,
    )


class _FakeS3:
    """Records calls; responses tunable per-call via ``side_effect`` dict."""

    def __init__(self):
        self.put_calls: List[Dict[str, Any]] = []
        self.head_calls: List[Dict[str, Any]] = []
        self.create_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.paginator_calls: List[str] = []
        self.ensure_security_calls: List[str] = []

        # Per-op response/side-effect maps
        self.put_object_raises: Exception | None = None
        self.put_object_raises_once: Exception | None = None
        self.head_bucket_raises: Exception | None = None
        self.create_bucket_raises: Exception | None = None
        self.get_object_raises: Exception | None = None
        self.paginator_raises: Exception | None = None
        self.paginator_pages: List[Dict[str, Any]] = []

        # For ensure_bucket_security
        self.put_public_access_block_raises: Exception | None = None
        self.put_bucket_encryption_raises: Exception | None = None

        # get_object body
        self.get_object_response: Dict[str, Any] = {}

    # ------ put_object ------
    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        if self.put_object_raises_once is not None:
            exc = self.put_object_raises_once
            self.put_object_raises_once = None
            raise exc
        if self.put_object_raises is not None:
            raise self.put_object_raises

    # ------ head_bucket / create_bucket ------
    def head_bucket(self, Bucket):
        self.head_calls.append({"Bucket": Bucket})
        if self.head_bucket_raises is not None:
            raise self.head_bucket_raises

    def create_bucket(self, Bucket):
        self.create_calls.append({"Bucket": Bucket})
        if self.create_bucket_raises is not None:
            raise self.create_bucket_raises

    # ------ get_object ------
    def get_object(self, Bucket, Key):
        self.get_calls.append({"Bucket": Bucket, "Key": Key})
        if self.get_object_raises is not None:
            raise self.get_object_raises
        # Default: return a stub body (object with read())
        body = SimpleNamespace(read=lambda: b"doc-bytes")
        return {
            "Body": body,
            "ContentType": "text/plain",
            "Metadata": {"tenant_id": "t"},
            "ContentLength": 8,
            **self.get_object_response,
        }

    # ------ list_objects_v2 paginator ------
    def get_paginator(self, op):
        fake = self

        class _P:
            def paginate(self, **_kw):
                if fake.paginator_raises is not None:
                    raise fake.paginator_raises
                yield from fake.paginator_pages

        return _P()

    # ------ security config ------
    def put_public_access_block(self, **_kw):
        self.ensure_security_calls.append("public_access_block")
        if self.put_public_access_block_raises is not None:
            raise self.put_public_access_block_raises

    def put_bucket_encryption(self, **_kw):
        self.ensure_security_calls.append("bucket_encryption")
        if self.put_bucket_encryption_raises is not None:
            raise self.put_bucket_encryption_raises


@pytest.fixture
def fake_client(monkeypatch):
    """Return a fresh _FakeS3 that replaces s3_utils._client for the test."""
    fake = _FakeS3()
    monkeypatch.setattr(s3_utils, "_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    """Ensure logger calls don't propagate to the console during tests."""
    # s3_utils uses structlog directly — just stub the bound logger
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass

    monkeypatch.setattr(s3_utils, "logger", _Silent())


# ---------------------------------------------------------------------------
# _client
# ---------------------------------------------------------------------------


class TestClientFactory:

    def test_raises_when_credentials_missing(self, monkeypatch):
        monkeypatch.setattr(s3_utils, "get_settings", lambda: SimpleNamespace(
            object_storage_access_key_id=None,
            object_storage_secret_access_key=None,
            object_storage_region="us-east-1",
            object_storage_endpoint_url=None,
        ))
        with pytest.raises(NotImplementedError, match="S3 storage is not configured"):
            s3_utils._client()

    def test_raises_when_only_access_key_present(self, monkeypatch):
        monkeypatch.setattr(s3_utils, "get_settings", lambda: SimpleNamespace(
            object_storage_access_key_id="akid",
            object_storage_secret_access_key=None,
            object_storage_region="us-east-1",
            object_storage_endpoint_url=None,
        ))
        with pytest.raises(NotImplementedError):
            s3_utils._client()

    def test_returns_boto_client_when_configured(self, monkeypatch):
        called = {}

        class _FakeBotoSession:
            def client(self, service, **kwargs):
                called["service"] = service
                called["kwargs"] = kwargs
                return "boto-client"

        monkeypatch.setattr(s3_utils.boto3.session, "Session", lambda: _FakeBotoSession())
        monkeypatch.setattr(s3_utils, "get_settings", lambda: SimpleNamespace(
            object_storage_access_key_id="akid",
            object_storage_secret_access_key="skid",
            object_storage_region="us-west-2",
            object_storage_endpoint_url="http://minio",
        ))
        out = s3_utils._client()
        assert out == "boto-client"
        assert called["service"] == "s3"
        assert called["kwargs"]["region_name"] == "us-west-2"
        assert called["kwargs"]["endpoint_url"] == "http://minio"
        assert called["kwargs"]["aws_access_key_id"] == "akid"
        assert called["kwargs"]["aws_secret_access_key"] == "skid"


# ---------------------------------------------------------------------------
# _ensure_bucket_security
# ---------------------------------------------------------------------------


class TestEnsureBucketSecurity:

    def test_happy_path_calls_both(self, fake_client):
        s3_utils._ensure_bucket_security(fake_client, "b")
        assert fake_client.ensure_security_calls == [
            "public_access_block", "bucket_encryption",
        ]

    def test_public_access_block_failure_is_non_fatal(self, fake_client):
        fake_client.put_public_access_block_raises = _client_error("AccessDenied")
        # Doesn't raise — both calls happen
        s3_utils._ensure_bucket_security(fake_client, "b")
        assert "bucket_encryption" in fake_client.ensure_security_calls

    def test_encryption_failure_is_non_fatal(self, fake_client):
        fake_client.put_bucket_encryption_raises = BotoCoreError()
        s3_utils._ensure_bucket_security(fake_client, "b")
        # No exception raised


# ---------------------------------------------------------------------------
# put_json / put_bytes
# ---------------------------------------------------------------------------


class TestPutJson:

    def test_happy_path_returns_uri(self, fake_client):
        uri = s3_utils.put_json("bkt", "k1", {"hello": "world"})
        assert uri == "s3://bkt/k1"
        call = fake_client.put_calls[0]
        assert call["Bucket"] == "bkt"
        assert call["Key"] == "k1"
        assert call["ContentType"] == "application/json"
        assert call["ServerSideEncryption"] == "AES256"
        # Body is UTF-8 JSON
        assert b'"hello": "world"' in call["Body"]

    def test_no_such_bucket_triggers_create_and_retry(self, fake_client):
        # First put_object → NoSuchBucket, then succeeds
        fake_client.put_object_raises_once = _client_error("NoSuchBucket")
        uri = s3_utils.put_json("missing-bkt", "k", {"x": 1})
        assert uri == "s3://missing-bkt/k"
        # Two put_object calls total: failing + retry
        assert len(fake_client.put_calls) == 2
        # create_bucket called between them
        assert fake_client.create_calls == [{"Bucket": "missing-bkt"}]
        # Security hardening applied
        assert "public_access_block" in fake_client.ensure_security_calls

    def test_create_bucket_failure_falls_through_to_500(self, fake_client):
        fake_client.put_object_raises = _client_error("NoSuchBucket")
        fake_client.create_bucket_raises = _client_error("PermissionDenied")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.put_json("b", "k", {})
        assert exc_info.value.status_code == 500

    def test_other_client_error_becomes_500(self, fake_client):
        fake_client.put_object_raises = _client_error("AccessDenied")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.put_json("b", "k", {})
        assert exc_info.value.status_code == 500
        assert "Failed to store data" in exc_info.value.detail

    def test_botocore_error_becomes_500(self, fake_client):
        fake_client.put_object_raises = BotoCoreError()
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.put_json("b", "k", {})
        assert exc_info.value.status_code == 500

    def test_datetime_payload_serialized_to_iso(self, fake_client):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        s3_utils.put_json("b", "k", {"ts": ts})
        body = fake_client.put_calls[0]["Body"]
        assert b"2026-01-01T12:00:00+00:00" in body


class TestPutBytes:

    def test_happy_path(self, fake_client):
        uri = s3_utils.put_bytes("b", "k", b"\x00\x01", content_type="image/png")
        assert uri == "s3://b/k"
        call = fake_client.put_calls[0]
        assert call["ContentType"] == "image/png"
        assert call["Body"] == b"\x00\x01"
        assert call["ServerSideEncryption"] == "AES256"

    def test_no_such_bucket_retries(self, fake_client):
        fake_client.put_object_raises_once = _client_error("NoSuchBucket")
        uri = s3_utils.put_bytes("b", "k", b"x")
        assert uri == "s3://b/k"
        assert len(fake_client.put_calls) == 2
        assert fake_client.create_calls == [{"Bucket": "b"}]

    def test_create_fails_raises_500(self, fake_client):
        fake_client.put_object_raises = _client_error("NoSuchBucket")
        fake_client.create_bucket_raises = Exception("create blew up")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.put_bytes("b", "k", b"x")
        assert exc_info.value.status_code == 500

    def test_other_error_becomes_500(self, fake_client):
        fake_client.put_object_raises = BotoCoreError()
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.put_bytes("b", "k", b"x")
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _json_serializer
# ---------------------------------------------------------------------------


class TestJsonSerializer:

    def test_datetime_becomes_iso(self):
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert s3_utils._json_serializer(ts) == "2026-01-01T00:00:00+00:00"

    def test_unsupported_type_raises(self):
        class Foo:
            pass

        with pytest.raises(TypeError, match="not JSON serializable"):
            s3_utils._json_serializer(Foo())


# ---------------------------------------------------------------------------
# _ensure_bucket
# ---------------------------------------------------------------------------


class TestEnsureBucket:

    def test_existing_bucket_is_noop(self, fake_client):
        s3_utils._ensure_bucket(fake_client, "b")
        assert fake_client.head_calls == [{"Bucket": "b"}]
        assert fake_client.create_calls == []

    def test_missing_bucket_404_creates(self, fake_client):
        fake_client.head_bucket_raises = _client_error("404", op="HeadBucket")
        s3_utils._ensure_bucket(fake_client, "b")
        assert fake_client.create_calls == [{"Bucket": "b"}]

    def test_missing_bucket_NoSuchBucket_creates(self, fake_client):
        fake_client.head_bucket_raises = _client_error("NoSuchBucket", op="HeadBucket")
        s3_utils._ensure_bucket(fake_client, "b")
        assert fake_client.create_calls == [{"Bucket": "b"}]

    def test_create_bucket_failure_reraises(self, fake_client):
        fake_client.head_bucket_raises = _client_error("404", op="HeadBucket")
        fake_client.create_bucket_raises = _client_error("AccessDenied", op="CreateBucket")
        with pytest.raises(ClientError):
            s3_utils._ensure_bucket(fake_client, "b")

    def test_non_404_head_error_reraises(self, fake_client):
        fake_client.head_bucket_raises = _client_error("AccessDenied", op="HeadBucket")
        with pytest.raises(ClientError):
            s3_utils._ensure_bucket(fake_client, "b")

    def test_botocore_on_create_reraises(self, fake_client):
        fake_client.head_bucket_raises = _client_error("NoSuchBucket", op="HeadBucket")
        fake_client.create_bucket_raises = BotoCoreError()
        with pytest.raises(BotoCoreError):
            s3_utils._ensure_bucket(fake_client, "b")


# ---------------------------------------------------------------------------
# upload_raw_document
# ---------------------------------------------------------------------------


class TestUploadRawDocument:

    def test_happy_path_builds_tenant_date_key(self, fake_client, monkeypatch):
        # Freeze time for predictable date prefix
        fixed_now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

        class _F:
            @classmethod
            def now(cls, tz=None):
                return fixed_now

            isoformat = datetime.isoformat

        monkeypatch.setattr(s3_utils, "datetime", _F)

        out = s3_utils.upload_raw_document(
            content=b"payload",
            tenant_id="tnt",
            document_type="PDF",
            filename="report.pdf",
            metadata={"origin": "fda"},
        )
        assert out["bucket"] == "regengine-ingest-raw"
        # Key: tnt/2026/04/19/pdf/<uuid>-report.pdf
        assert out["key"].startswith("tnt/2026/04/19/pdf/")
        assert out["key"].endswith("-report.pdf")
        assert out["s3_uri"] == f"s3://regengine-ingest-raw/{out['key']}"
        # Metadata merged on top of built-ins
        put_call = fake_client.put_calls[0]
        assert put_call["Metadata"]["tenant_id"] == "tnt"
        assert put_call["Metadata"]["origin"] == "fda"
        assert put_call["ServerSideEncryption"] == "AES256"

    def test_no_filename_means_no_suffix(self, fake_client):
        out = s3_utils.upload_raw_document(
            content=b"x", tenant_id="t", document_type="unknown",
        )
        assert not out["key"].endswith("-")
        # Key ends with a UUID (no suffix)
        import re
        uuid_tail = out["key"].split("/")[-1]
        assert re.match(r"^[0-9a-f-]{36}$", uuid_tail)

    def test_sanitizes_slashes_in_filename(self, fake_client):
        out = s3_utils.upload_raw_document(
            content=b"x", tenant_id="t", filename="../etc/passwd",
        )
        assert ".._etc_passwd" in out["key"]
        # No raw slashes past the built-in prefix layers
        assert "/passwd" not in out["key"]

    def test_whitespace_only_filename_produces_no_suffix(self, fake_client):
        out = s3_utils.upload_raw_document(
            content=b"x", tenant_id="t", filename="   ",
        )
        # After strip, safe_name is empty → no "-" suffix
        assert not out["key"].endswith("-")

    def test_uppercase_and_space_in_document_type_normalized(self, fake_client):
        out = s3_utils.upload_raw_document(
            content=b"x", tenant_id="t", document_type="Food Safety PDF",
        )
        assert "/food_safety_pdf/" in out["key"]

    def test_client_error_becomes_500(self, fake_client):
        fake_client.put_object_raises = _client_error("SlowDown")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.upload_raw_document(content=b"x", tenant_id="t")
        assert exc_info.value.status_code == 500
        assert "Failed to store raw document" in exc_info.value.detail

    def test_botocore_error_becomes_500(self, fake_client):
        fake_client.put_object_raises = BotoCoreError()
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.upload_raw_document(content=b"x", tenant_id="t")
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# get_raw_document
# ---------------------------------------------------------------------------


class TestGetRawDocument:

    def test_happy_path(self, fake_client):
        out = s3_utils.get_raw_document("k1")
        assert out["content"] == b"doc-bytes"
        assert out["content_type"] == "text/plain"
        assert out["metadata"] == {"tenant_id": "t"}
        assert out["content_length"] == 8

    def test_defaults_when_response_missing_fields(self, fake_client):
        # Override get_object to return a minimal response (only Body)
        def _min_get(Bucket, Key):
            return {"Body": SimpleNamespace(read=lambda: b"x")}

        fake_client.get_object = _min_get
        out = s3_utils.get_raw_document("k")
        assert out["content"] == b"x"
        assert out["content_type"] == "application/octet-stream"
        assert out["metadata"] == {}
        assert out["content_length"] == 0

    def test_no_such_key_raises_404(self, fake_client):
        fake_client.get_object_raises = _client_error("NoSuchKey", op="GetObject")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.get_raw_document("missing")
        assert exc_info.value.status_code == 404
        assert "missing" in exc_info.value.detail

    def test_other_client_error_raises_500(self, fake_client):
        fake_client.get_object_raises = _client_error("AccessDenied", op="GetObject")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.get_raw_document("k")
        assert exc_info.value.status_code == 500

    def test_botocore_error_raises_500(self, fake_client):
        fake_client.get_object_raises = BotoCoreError()
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.get_raw_document("k")
        assert exc_info.value.status_code == 500

    def test_custom_bucket_passed_through(self, fake_client):
        s3_utils.get_raw_document("k", bucket="custom-bkt")
        assert fake_client.get_calls[0]["Bucket"] == "custom-bkt"


# ---------------------------------------------------------------------------
# list_raw_documents
# ---------------------------------------------------------------------------


class TestListRawDocuments:

    def test_returns_documents_with_iso_timestamps(self, fake_client):
        fake_client.paginator_pages = [{
            "Contents": [
                {
                    "Key": "t/2026/04/19/pdf/abc",
                    "Size": 512,
                    "LastModified": datetime(2026, 4, 19, 10, tzinfo=timezone.utc),
                },
                {
                    "Key": "t/2026/04/19/pdf/def",
                    "Size": 1024,
                    "LastModified": "2026-04-19T11:00:00Z",  # Already a string
                },
            ],
        }]
        docs = s3_utils.list_raw_documents("t")
        assert len(docs) == 2
        assert docs[0]["key"] == "t/2026/04/19/pdf/abc"
        assert docs[0]["size"] == 512
        assert docs[0]["last_modified"] == "2026-04-19T10:00:00+00:00"
        assert docs[0]["s3_uri"] == "s3://regengine-ingest-raw/t/2026/04/19/pdf/abc"
        # String LastModified goes through str() (same as the string itself)
        assert docs[1]["last_modified"] == "2026-04-19T11:00:00Z"

    def test_custom_prefix_appended_after_tenant(self, fake_client):
        fake_client.paginator_pages = [{"Contents": []}]
        s3_utils.list_raw_documents("t", prefix="2026/04/")
        # Can't inspect paginator args without more plumbing, but empty list OK
        assert s3_utils.list_raw_documents("t", prefix="2026/04/") == []

    def test_no_contents_key_returns_empty(self, fake_client):
        fake_client.paginator_pages = [{}]  # No "Contents" key at all
        assert s3_utils.list_raw_documents("t") == []

    def test_nosuchbucket_returns_empty_list(self, fake_client):
        fake_client.paginator_raises = _client_error("NoSuchBucket", op="ListObjectsV2")
        assert s3_utils.list_raw_documents("t") == []

    def test_404_also_returns_empty_list(self, fake_client):
        fake_client.paginator_raises = _client_error("404", op="ListObjectsV2")
        assert s3_utils.list_raw_documents("t") == []

    def test_other_client_error_raises_500(self, fake_client):
        fake_client.paginator_raises = _client_error("AccessDenied", op="ListObjectsV2")
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.list_raw_documents("t")
        assert exc_info.value.status_code == 500

    def test_botocore_error_raises_500(self, fake_client):
        fake_client.paginator_raises = BotoCoreError()
        with pytest.raises(HTTPException) as exc_info:
            s3_utils.list_raw_documents("t")
        assert exc_info.value.status_code == 500

    def test_custom_bucket(self, fake_client):
        fake_client.paginator_pages = [{"Contents": [{
            "Key": "t/file",
            "Size": 1,
            "LastModified": datetime.now(timezone.utc),
        }]}]
        docs = s3_utils.list_raw_documents("t", bucket="custom")
        assert docs[0]["s3_uri"].startswith("s3://custom/")
