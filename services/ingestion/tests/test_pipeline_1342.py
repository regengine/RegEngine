"""Unit tests for ``app.pipeline`` — issue #1342.

Covers ``ScraperPipeline.process_content`` end-to-end:

  - Empty content short-circuits with a warning and an empty dict —
    callers rely on the ``bool(event)`` contract to decide whether to
    mark a scrape job "success_empty" vs. "success".
  - Non-empty content produces a fully populated
    ``ingest.raw_collected`` event with stable shape (pipeline_version
    2.0, ISO-8601 timestamp, consistent ``raw/<jur>/<YYYY-MM-DD>/<uuid>``
    S3 key) — downstream consumers (normalization, EPCIS) parse this.
  - The S3 upload happens *before* the Kafka emit, and Kafka sees the
    s3_uri from the upload response — if that order ever flips you'll
    publish an event pointing at a nonexistent object.
  - Content-type defaults to ``application/octet-stream`` when the
    caller passes a falsy content-type, but is forwarded verbatim
    otherwise (including odd inputs like ``text/html; charset=utf-8``).
  - Metadata is attached only when truthy — an empty dict is treated
    as "no metadata" (the ``if metadata:`` branch) rather than being
    stamped in as an empty blob.
  - Constructor: custom s3/kafka injection wins over the module
    singletons; omitting both falls back to ``_SHARED_S3`` /
    ``_SHARED_KAFKA``.
  - Exception in the S3 or Kafka path is re-raised after a warning log,
    so scraper_job's try/except still records the failure.

Stubs ``app.config.get_settings`` with a minimal namespace exposing
``raw_bucket`` — the real Pydantic settings loader is not needed and
would introduce env-variable ordering tests.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app import pipeline as mod  # noqa: E402
from app.pipeline import ScraperPipeline  # noqa: E402


# ---------------------------------------------------------------------------
# Spies
# ---------------------------------------------------------------------------


class _S3Spy:
    """Records every upload; returns the URI the real S3 stub would produce."""

    def __init__(self, *, raise_on_upload: Exception | None = None):
        self.uploads: list[dict[str, Any]] = []
        self.raise_on_upload = raise_on_upload

    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: str):
        if self.raise_on_upload is not None:
            raise self.raise_on_upload
        self.uploads.append(
            {
                "bucket": bucket,
                "key": key,
                "data": data,
                "content_type": content_type,
            }
        )
        return f"s3://{bucket}/{key}"


class _KafkaSpy:
    """Records every emit; optionally raises to exercise the error path."""

    def __init__(self, *, raise_on_emit: Exception | None = None):
        self.emits: list[dict[str, Any]] = []
        self.raise_on_emit = raise_on_emit

    def emit(self, topic: str, payload: dict):
        if self.raise_on_emit is not None:
            raise self.raise_on_emit
        self.emits.append({"topic": topic, "payload": payload})
        return True


class _StructlogSpy:
    """Captures structlog-style calls without dragging in the real logger."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def _record(self, level: str, event: str, **kw: Any) -> None:
        self.calls.append((level, event, kw))

    def debug(self, event, **kw): self._record("debug", event, **kw)
    def info(self, event, **kw): self._record("info", event, **kw)
    def warning(self, event, **kw): self._record("warning", event, **kw)
    def error(self, event, **kw): self._record("error", event, **kw)

    def by_event(self, event: str) -> list[tuple[str, str, dict]]:
        return [c for c in self.calls if c[1] == event]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def log_spy(monkeypatch):
    spy = _StructlogSpy()
    monkeypatch.setattr(mod, "logger", spy)
    return spy


@pytest.fixture
def settings_stub(monkeypatch):
    fake = SimpleNamespace(raw_bucket="test-raw-bucket")
    monkeypatch.setattr(mod, "get_settings", lambda: fake)
    return fake


@pytest.fixture
def make_pipeline(settings_stub):
    """Factory that returns (pipeline, s3_spy, kafka_spy)."""

    def _make(
        *,
        s3_raise: Exception | None = None,
        kafka_raise: Exception | None = None,
    ) -> tuple[ScraperPipeline, _S3Spy, _KafkaSpy]:
        s3 = _S3Spy(raise_on_upload=s3_raise)
        kafka = _KafkaSpy(raise_on_emit=kafka_raise)
        return ScraperPipeline(s3_client=s3, kafka_producer=kafka), s3, kafka

    return _make


# ---------------------------------------------------------------------------
# Constructor — singleton fallback vs. dependency injection
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_falls_back_to_module_singletons(self, settings_stub):
        # When no s3/kafka are passed, the pipeline must pick up the
        # shared module singletons — that's the contract scraper_job
        # relies on for its _PIPELINE = ScraperPipeline() at import.
        p = ScraperPipeline()
        assert p.s3 is mod._SHARED_S3
        assert p.kafka is mod._SHARED_KAFKA

    def test_dependency_injection_wins(self, settings_stub):
        s3 = _S3Spy()
        kafka = _KafkaSpy()
        p = ScraperPipeline(s3_client=s3, kafka_producer=kafka)
        assert p.s3 is s3
        assert p.kafka is kafka
        # settings are still populated from get_settings().
        assert p.settings is settings_stub

    def test_partial_injection_mixes_with_singletons(self, settings_stub):
        # Only s3 injected — kafka falls back to singleton, and vice
        # versa. Guards against a regression where the `or` collapses
        # both defaults.
        s3 = _S3Spy()
        p1 = ScraperPipeline(s3_client=s3)
        assert p1.s3 is s3
        assert p1.kafka is mod._SHARED_KAFKA

        kafka = _KafkaSpy()
        p2 = ScraperPipeline(kafka_producer=kafka)
        assert p2.s3 is mod._SHARED_S3
        assert p2.kafka is kafka


# ---------------------------------------------------------------------------
# process_content — empty content short-circuit
# ---------------------------------------------------------------------------


class TestEmptyContent:
    def test_empty_bytes_returns_empty_dict(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=b"",
            content_type="text/html",
            jurisdiction_code="US-NY",
            source_url="https://example.gov/doc",
            tenant_id="tenant-123",
        )
        assert result == {}
        # No S3 upload, no Kafka emit — this is the whole point of the
        # short-circuit: don't ship empty blobs to storage / downstream.
        assert s3.uploads == []
        assert kafka.emits == []
        # Warning carries the URL and jurisdiction so ops can find the
        # offending scrape run.
        warn = log_spy.by_event("pipeline_empty_content")
        assert len(warn) == 1
        assert warn[0][0] == "warning"
        assert warn[0][2] == {
            "url": "https://example.gov/doc",
            "jurisdiction": "US-NY",
        }

    def test_none_content_treated_as_empty(self, make_pipeline, log_spy):
        # The check is ``if not content`` — ``None`` and ``b""`` both
        # take the same branch. Pin it so a type-narrowing refactor
        # doesn't accidentally make ``None`` fall through and crash
        # on ``len(content)``.
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=None,  # type: ignore[arg-type]
            content_type="text/html",
            jurisdiction_code="US-CA",
            source_url="https://example.ca.gov/x",
            tenant_id="t",
        )
        assert result == {}
        assert s3.uploads == []
        assert kafka.emits == []


# ---------------------------------------------------------------------------
# process_content — happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_event_shape_and_ordering(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=b"<html>hello</html>",
            content_type="text/html",
            jurisdiction_code="US-NY",
            source_url="https://ny.gov/regs/ruleset.html",
            tenant_id="tenant-abc",
        )

        # Exactly one upload, exactly one emit.
        assert len(s3.uploads) == 1
        up = s3.uploads[0]
        assert up["bucket"] == "test-raw-bucket"
        assert up["data"] == b"<html>hello</html>"
        assert up["content_type"] == "text/html"

        # Key format: raw/<jur>/<YYYY-MM-DD>/<uuid>.
        key_pat = re.compile(
            r"^raw/US-NY/\d{4}-\d{2}-\d{2}/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert key_pat.match(up["key"]), f"bad s3 key: {up['key']!r}"

        # Kafka emit carries the full event.
        assert len(kafka.emits) == 1
        emit = kafka.emits[0]
        assert emit["topic"] == "ingest.raw_collected"
        ev = emit["payload"]
        assert ev["type"] == "ingest.raw_collected"
        assert ev["jurisdiction_code"] == "US-NY"
        assert ev["source_url"] == "https://ny.gov/regs/ruleset.html"
        assert ev["s3_uri"] == f"s3://test-raw-bucket/{up['key']}"
        assert ev["content_type"] == "text/html"
        assert ev["tenant_id"] == "tenant-abc"
        assert ev["pipeline_version"] == "2.0"
        # doc_id matches the tail of the s3 key — same uuid reused.
        assert up["key"].endswith(ev["doc_id"])
        # ISO-8601 timestamp — downstream consumers parse this.
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$",
            ev["timestamp"],
        )

        # Return value is the emitted event (identity not required but
        # same contents).
        assert result == ev

    def test_returned_event_is_same_object_emitted(
        self, make_pipeline, log_spy
    ):
        # Callers in scraper_job.py do `event = pipeline.process_content(...)`
        # then push fields into the event. Pin identity so a refactor
        # that dicts-out to a new object doesn't silently break those
        # mutations.
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=b"x",
            content_type="text/plain",
            jurisdiction_code="US-TX",
            source_url="https://tx.gov/1",
            tenant_id="t",
        )
        assert result is kafka.emits[0]["payload"]

    def test_metadata_included_when_provided(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline()
        meta = {"adaptor": "fda_enforcement", "retries": 1}
        result = p.process_content(
            content=b"blob",
            content_type="application/pdf",
            jurisdiction_code="US",
            source_url="https://fda.gov/a.pdf",
            tenant_id="t",
            metadata=meta,
        )
        assert result["metadata"] == meta
        assert kafka.emits[0]["payload"]["metadata"] == meta

    def test_empty_metadata_dict_is_omitted(self, make_pipeline, log_spy):
        # ``if metadata:`` — falsy metadata (empty dict, None) must NOT
        # stamp a "metadata" key into the event. Downstream schemas
        # treat "field present but empty" differently from "absent".
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=b"x",
            content_type="text/plain",
            jurisdiction_code="US-NY",
            source_url="https://ny.gov/x",
            tenant_id="t",
            metadata={},
        )
        assert "metadata" not in result
        assert "metadata" not in kafka.emits[0]["payload"]

    def test_none_metadata_is_omitted(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline()
        result = p.process_content(
            content=b"x",
            content_type="text/plain",
            jurisdiction_code="US-NY",
            source_url="https://ny.gov/x",
            tenant_id="t",
            metadata=None,
        )
        assert "metadata" not in result

    def test_info_log_on_success(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline()
        p.process_content(
            content=b"abcdef",
            content_type="text/plain",
            jurisdiction_code="US-CA",
            source_url="https://ca.gov/x",
            tenant_id="t",
        )
        infos = log_spy.by_event("pipeline_content_processed")
        assert len(infos) == 1
        level, _, kw = infos[0]
        assert level == "info"
        assert kw["jurisdiction"] == "US-CA"
        assert kw["bytes"] == 6
        # doc_id matches the emitted event.
        assert kw["doc_id"] == kafka.emits[0]["payload"]["doc_id"]

    def test_falsy_content_type_defaults_to_octet_stream(
        self, make_pipeline, log_spy
    ):
        # S3 needs a Content-Type for anything useful on retrieval;
        # caller might pass "" when the scraper can't figure it out.
        p, s3, kafka = make_pipeline()
        p.process_content(
            content=b"x",
            content_type="",
            jurisdiction_code="US",
            source_url="https://x.gov/",
            tenant_id="t",
        )
        assert s3.uploads[0]["content_type"] == "application/octet-stream"
        # Event keeps the caller's original content_type value
        # (``""``) — only the *S3 upload* gets defaulted, because only
        # S3 needs it for on-disk metadata.
        assert kafka.emits[0]["payload"]["content_type"] == ""

    def test_non_ascii_jurisdiction_and_url_pass_through(
        self, make_pipeline, log_spy
    ):
        # Some state adapter keys are oddly shaped; key building uses
        # plain f-string so the pipeline should not try to encode.
        p, s3, kafka = make_pipeline()
        p.process_content(
            content=b"x",
            content_type="text/plain",
            jurisdiction_code="US-MÉXICO",
            source_url="https://ex.gov/año",
            tenant_id="t",
        )
        assert s3.uploads[0]["key"].startswith("raw/US-MÉXICO/")
        assert kafka.emits[0]["payload"]["source_url"] == "https://ex.gov/año"


# ---------------------------------------------------------------------------
# process_content — error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_s3_failure_logs_error_and_reraises(self, make_pipeline, log_spy):
        p, s3, kafka = make_pipeline(
            s3_raise=RuntimeError("bucket missing")
        )
        with pytest.raises(RuntimeError, match="bucket missing"):
            p.process_content(
                content=b"x",
                content_type="text/plain",
                jurisdiction_code="US-NY",
                source_url="https://ny.gov/x",
                tenant_id="t",
            )
        # Kafka must NOT be invoked when S3 failed — emitting an event
        # with no blob is the failure mode we're guarding against.
        assert kafka.emits == []

        errs = log_spy.by_event("pipeline_processing_failed")
        assert len(errs) == 1
        level, _, kw = errs[0]
        assert level == "error"
        assert kw["url"] == "https://ny.gov/x"
        assert "bucket missing" in kw["error"]

    def test_kafka_failure_logs_error_and_reraises(
        self, make_pipeline, log_spy
    ):
        # S3 succeeds, Kafka explodes — still re-raise. We get an
        # orphaned S3 object but no event; scraper_job treats the whole
        # job as failed and the next retry will re-upload.
        p, s3, kafka = make_pipeline(
            kafka_raise=ConnectionError("broker down")
        )
        with pytest.raises(ConnectionError, match="broker down"):
            p.process_content(
                content=b"x",
                content_type="text/plain",
                jurisdiction_code="US-CA",
                source_url="https://ca.gov/y",
                tenant_id="t",
            )
        # S3 did upload before kafka failed.
        assert len(s3.uploads) == 1
        errs = log_spy.by_event("pipeline_processing_failed")
        assert len(errs) == 1
        assert "broker down" in errs[0][2]["error"]
        # No success log.
        assert log_spy.by_event("pipeline_content_processed") == []

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad"),
            OSError("disk"),
            TimeoutError("slow"),
            KeyError("missing"),
        ],
    )
    def test_any_uncaught_s3_exception_propagates(
        self, make_pipeline, log_spy, exc
    ):
        # The except clause is ``except Exception`` — it catches the
        # error, logs, and re-raises the *original* exception
        # (``raise e``), not a wrapped one. Pin identity so a refactor
        # to ``raise`` vs. ``raise e`` vs. ``raise MyError(...) from e``
        # doesn't silently change the exception contract.
        p, s3, kafka = make_pipeline(s3_raise=exc)
        with pytest.raises(type(exc)) as ei:
            p.process_content(
                content=b"x",
                content_type="text/plain",
                jurisdiction_code="US",
                source_url="https://x.gov/",
                tenant_id="t",
            )
        assert ei.value is exc
