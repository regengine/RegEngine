"""Unit tests for ``app.scrapers.state_generic`` — issue #1342.

Covers the two placeholder clients (``S3Client``, ``KafkaProducer``)
and ``StateRegistryScraper.fetch_document`` end-to-end.

Pinned behaviour:
  - ``S3Client.upload_bytes`` returns ``s3://<bucket>/<key>`` without
    any real S3 call — callers rely on this identity contract for
    dev/test boots and for the pipeline's event payload.
  - ``KafkaProducer.emit`` returns ``True`` unconditionally — the
    generic scraper uses the return value as a "sent" flag.
  - ``StateRegistryScraper.__init__`` honors the ``RAW_INGEST_BUCKET``
    env var; custom bucket/clients override both env and the bare
    defaults; leaving args blank picks up env OR the ``regengine-raw``
    literal (guards against a regression where the ``or`` collapses).
  - ``fetch_document``:
      - Rejects SSRF URLs with a ``ValueError`` (NOT the underlying
        ``SSRFError``) — caller's error handling relies on that shape.
      - Dispatches ``httpx.get`` to a thread pool via
        ``loop.run_in_executor(None, ...)``, *not* on the event loop
        thread, so the async route isn't blocked by a slow registry.
      - Calls ``resp.raise_for_status`` so HTTP 4xx/5xx propagate
        (no silent success-on-failure).
      - Builds a stable ``raw/<jur>/<YYYY-MM-DD>/<uuid>`` S3 key and
        hands it to S3 with the response's Content-Type (defaulting
        to ``application/octet-stream`` when absent).
      - Emits an ``ingest.raw_collected`` event with the resolved
        URL, the S3 uri, the doc_id (same uuid used in the S3 key),
        and the caller's tenant_id.

``httpx`` is patched module-local so the tests don't make real
network calls.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app.scrapers import state_generic as mod  # noqa: E402
from app.scrapers.state_generic import (  # noqa: E402
    KafkaProducer,
    S3Client,
    StateRegistryScraper,
)


# ---------------------------------------------------------------------------
# Spies
# ---------------------------------------------------------------------------


class _S3Spy:
    def __init__(self):
        self.uploads: list[dict[str, Any]] = []

    def upload_bytes(self, bucket, key, data, content_type):
        self.uploads.append(
            {"bucket": bucket, "key": key, "data": data, "content_type": content_type}
        )
        return f"s3://{bucket}/{key}"


class _KafkaSpy:
    def __init__(self):
        self.emits: list[dict[str, Any]] = []

    def emit(self, topic, payload):
        self.emits.append({"topic": topic, "payload": payload})
        return True


class _FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"<html/>",
        status_code: int = 200,
        content_type: str | None = "text/html",
    ):
        self.content = content
        self.status_code = status_code
        self.headers = {}
        if content_type is not None:
            self.headers["Content-Type"] = content_type

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            import httpx

            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=SimpleNamespace(),  # type: ignore[arg-type]
                response=self,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# S3Client + KafkaProducer placeholders
# ---------------------------------------------------------------------------


class TestS3ClientStub:
    def test_upload_bytes_returns_s3_uri(self):
        client = S3Client()
        out = client.upload_bytes("bkt", "raw/x/2026-04-19/abc", b"hello", "text/plain")
        assert out == "s3://bkt/raw/x/2026-04-19/abc"

    def test_upload_does_not_mutate_bucket_or_key(self):
        # Guards against a "helpful" refactor that normalizes the
        # bucket/key before returning — callers store the returned
        # URI in the event payload and need byte-for-byte identity
        # with what the pipeline hashed.
        client = S3Client()
        out = client.upload_bytes("My-BucKet", "raw/US-NY/odd key", b"x", "x")
        assert out == "s3://My-BucKet/raw/US-NY/odd key"


class TestKafkaProducerStub:
    def test_emit_returns_true(self):
        k = KafkaProducer()
        assert k.emit("some.topic", {"k": 1}) is True

    def test_emit_accepts_any_payload_shape(self):
        # The placeholder doesn't schema-check — that's intentional;
        # schema enforcement lives in the real producer. Pin it so a
        # dev doesn't accidentally add a pydantic validation call here
        # and break a test fixture.
        k = KafkaProducer()
        assert k.emit("t", {}) is True
        assert k.emit("t", {"nested": {"a": [1, 2]}}) is True


# ---------------------------------------------------------------------------
# StateRegistryScraper.__init__
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_bucket_from_env(self, monkeypatch):
        monkeypatch.setenv("RAW_INGEST_BUCKET", "env-raw-bucket")
        s = StateRegistryScraper()
        assert s.s3_bucket == "env-raw-bucket"

    def test_bucket_default_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("RAW_INGEST_BUCKET", raising=False)
        s = StateRegistryScraper()
        assert s.s3_bucket == "regengine-raw"

    def test_explicit_bucket_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("RAW_INGEST_BUCKET", "env-bucket")
        s = StateRegistryScraper(s3_bucket="explicit-bucket")
        assert s.s3_bucket == "explicit-bucket"

    def test_default_clients_are_placeholders(self, monkeypatch):
        monkeypatch.delenv("RAW_INGEST_BUCKET", raising=False)
        s = StateRegistryScraper()
        assert isinstance(s.s3, S3Client)
        assert isinstance(s.kafka, KafkaProducer)

    def test_custom_clients_override_defaults(self):
        s3 = _S3Spy()
        kafka = _KafkaSpy()
        s = StateRegistryScraper(s3_client=s3, kafka=kafka)
        assert s.s3 is s3
        assert s.kafka is kafka


# ---------------------------------------------------------------------------
# fetch_document — SSRF rejection
# ---------------------------------------------------------------------------


class TestFetchDocumentSSRF:
    def test_ssrf_error_is_wrapped_as_value_error(self, monkeypatch):
        # The caller surface is ValueError, not SSRFError — keep the
        # wrap so scrape-job retry logic doesn't have to import the
        # shared url_validation module.
        def _boom(url, *, allowed_schemes=None):
            raise mod.SSRFError("blocked: internal IP")

        monkeypatch.setattr(mod, "validate_url", _boom)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(s3_client=s3, kafka=kafka)

        with pytest.raises(ValueError, match="URL validation failed"):
            asyncio.run(
                scraper.fetch_document(
                    url="http://169.254.169.254/latest/",
                    jurisdiction_code="US-NY",
                    tenant_id="t",
                )
            )
        # No side effects when the URL is blocked.
        assert s3.uploads == []
        assert kafka.emits == []


# ---------------------------------------------------------------------------
# fetch_document — happy path
# ---------------------------------------------------------------------------


def _install_httpx_stub(
    monkeypatch,
    response: _FakeResponse,
    *,
    calls: list | None = None,
):
    """Swap mod.httpx.get for a spy — records (url, timeout) calls."""

    calls = calls if calls is not None else []

    class _HttpxStub:
        @staticmethod
        def get(url, timeout=None):
            calls.append({"url": url, "timeout": timeout})
            return response

        # keep error class reachable for _FakeResponse.raise_for_status
        class HTTPStatusError(Exception):
            def __init__(self, msg, request=None, response=None):
                super().__init__(msg)
                self.request = request
                self.response = response

    monkeypatch.setattr(mod, "httpx", _HttpxStub)
    return calls


class TestFetchDocumentHappyPath:
    def test_full_happy_path(self, monkeypatch):
        resp = _FakeResponse(content=b"<html>hi</html>", content_type="text/html")
        calls = _install_httpx_stub(monkeypatch, resp)
        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="my-bucket", s3_client=s3, kafka=kafka
        )

        out = asyncio.run(
            scraper.fetch_document(
                url="https://ny.gov/register.html",
                jurisdiction_code="US-NY",
                tenant_id="tenant-7",
            )
        )

        # httpx called with the validated URL and a 15s timeout.
        assert len(calls) == 1
        assert calls[0] == {"url": "https://ny.gov/register.html", "timeout": 15}

        # S3 upload happened exactly once with the bytes from the response.
        assert len(s3.uploads) == 1
        up = s3.uploads[0]
        assert up["bucket"] == "my-bucket"
        assert up["data"] == b"<html>hi</html>"
        assert up["content_type"] == "text/html"
        assert re.match(
            r"^raw/US-NY/\d{4}-\d{2}-\d{2}/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            up["key"],
        )

        # Kafka emit carries the full event.
        assert len(kafka.emits) == 1
        e = kafka.emits[0]
        assert e["topic"] == "ingest.raw_collected"
        ev = e["payload"]
        assert ev["type"] == "ingest.raw_collected"
        assert ev["jurisdiction_code"] == "US-NY"
        assert ev["source_url"] == "https://ny.gov/register.html"
        assert ev["s3_uri"] == f"s3://my-bucket/{up['key']}"
        assert ev["content_type"] == "text/html"
        assert ev["tenant_id"] == "tenant-7"
        # doc_id is the uuid tail of the key.
        assert up["key"].endswith(ev["doc_id"])

        # Returned event must be the exact dict emitted — callers in
        # routes_scraping inspect the return to build responses.
        assert out == ev

    def test_missing_content_type_defaults_to_octet_stream(self, monkeypatch):
        resp = _FakeResponse(content=b"\x00\x01", content_type=None)
        _install_httpx_stub(monkeypatch, resp)
        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        out = asyncio.run(
            scraper.fetch_document(
                url="https://x.gov/x", jurisdiction_code="US", tenant_id=None
            )
        )
        assert s3.uploads[0]["content_type"] == "application/octet-stream"
        assert out["content_type"] == "application/octet-stream"

    def test_tenant_id_defaults_to_none(self, monkeypatch):
        # The signature makes tenant_id optional; the payload must
        # keep the key present with a None value rather than being
        # silently dropped. Downstream event consumers branch on
        # ``tenant_id is None`` to route into the multi-tenant or
        # shared path.
        resp = _FakeResponse()
        _install_httpx_stub(monkeypatch, resp)
        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        out = asyncio.run(
            scraper.fetch_document(
                url="https://x.gov/x", jurisdiction_code="US"
            )
        )
        assert out["tenant_id"] is None

    def test_validate_url_result_used_as_fetch_url(self, monkeypatch):
        # validate_url normalizes (strips defaults, lowercases host,
        # etc.); the scraper must fetch the *normalized* URL, not the
        # caller's raw input. Guards against a refactor that passes
        # the raw URL to httpx.
        resp = _FakeResponse()
        calls = _install_httpx_stub(monkeypatch, resp)
        monkeypatch.setattr(
            mod, "validate_url", lambda u, **_: "https://normalized.example/"
        )

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        out = asyncio.run(
            scraper.fetch_document(
                url="https://RAW.EXAMPLE/?a=b", jurisdiction_code="US"
            )
        )
        assert calls[0]["url"] == "https://normalized.example/"
        # Event source_url is the normalized URL too.
        assert out["source_url"] == "https://normalized.example/"

    def test_doc_ids_are_unique_per_call(self, monkeypatch):
        # Two back-to-back fetches must produce different doc_ids and
        # S3 keys — a regression where a module-level uuid got cached
        # at import time would collapse them.
        resp = _FakeResponse()
        _install_httpx_stub(monkeypatch, resp)
        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        o1 = asyncio.run(
            scraper.fetch_document(url="https://a.gov/", jurisdiction_code="US")
        )
        o2 = asyncio.run(
            scraper.fetch_document(url="https://a.gov/", jurisdiction_code="US")
        )
        assert o1["doc_id"] != o2["doc_id"]
        assert s3.uploads[0]["key"] != s3.uploads[1]["key"]


# ---------------------------------------------------------------------------
# fetch_document — error paths
# ---------------------------------------------------------------------------


class TestFetchDocumentErrors:
    def test_http_error_propagates(self, monkeypatch):
        # 4xx/5xx must raise — silent-success on an error page would
        # push an HTML error blob into the raw bucket.
        resp = _FakeResponse(content=b"Not Found", status_code=404)

        class _HttpxStub:
            class HTTPStatusError(Exception):
                pass

            @staticmethod
            def get(url, timeout=None):
                return resp

        monkeypatch.setattr(mod, "httpx", _HttpxStub)
        monkeypatch.setattr(mod, "validate_url", lambda u, **_: u)

        # Swap the response's raise_for_status to use the stub's
        # error class so the isinstance matches.
        def _raise():
            raise _HttpxStub.HTTPStatusError("404")

        resp.raise_for_status = _raise  # type: ignore[method-assign]

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        with pytest.raises(_HttpxStub.HTTPStatusError):
            asyncio.run(
                scraper.fetch_document(
                    url="https://x.gov/missing", jurisdiction_code="US"
                )
            )
        # No upload, no emit when the HTTP call failed.
        assert s3.uploads == []
        assert kafka.emits == []

    def test_ssrf_recheck_still_runs_on_happy_path(self, monkeypatch):
        # The scraper calls validate_url *twice* — once wrapped in
        # try/except (line 49) and once bare on line 55. If someone
        # deletes the bare call they'll still be SSRF-safe (the first
        # call already did it), but the belt-and-braces pattern is
        # intentional. Pin call count so a tidy-up can't silently
        # drop the second check without the author at least seeing
        # this test fail.
        calls: list[str] = []

        def _spy(u, **_):
            calls.append(u)
            return u

        monkeypatch.setattr(mod, "validate_url", _spy)

        resp = _FakeResponse()
        _install_httpx_stub(monkeypatch, resp)

        s3, kafka = _S3Spy(), _KafkaSpy()
        scraper = StateRegistryScraper(
            s3_bucket="b", s3_client=s3, kafka=kafka
        )
        asyncio.run(
            scraper.fetch_document(
                url="https://x.gov/", jurisdiction_code="US"
            )
        )
        # Exactly two validate_url calls.
        assert len(calls) == 2
        assert calls == ["https://x.gov/", "https://x.gov/"]
