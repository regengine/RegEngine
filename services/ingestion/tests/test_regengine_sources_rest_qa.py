"""QA coverage for regengine_ingestion sources, utils, storage, audit and engine.

These modules had no dedicated tests. All tests are deterministic:
network is stubbed out, sleeps are disabled, no database is used.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from regengine_ingestion.audit.logger import AuditLogger
from regengine_ingestion.config import FrameworkConfig, IngestionConfig, SourceType
from regengine_ingestion.engine import IngestionEngine
from regengine_ingestion.models import AuditEntry, IngestionJob, IngestionResult, JobStatus
from regengine_ingestion.sources.ecfr import ECFRAdapter
from regengine_ingestion.sources.fda import FDAAdapter
from regengine_ingestion.sources.federal_register import FederalRegisterAdapter
from regengine_ingestion.sources.fsma_204 import FSMA204Adapter
from regengine_ingestion.storage.manager import StorageManager
from regengine_ingestion.utils import (
    RateLimiter,
    generate_document_id,
    hash_content,
    hash_text,
    verify_hash,
)
from regengine_ingestion.utils.robots import RobotsChecker


@pytest.fixture(autouse=True)
def no_sleeps(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def make_adapter(cls, **attrs):
    adapter = cls.__new__(cls)
    adapter.audit_logger = None
    adapter.user_agent = "test-agent"
    adapter.rate_limiter = RateLimiter(requests_per_minute=100000)
    for key, value in attrs.items():
        setattr(adapter, key, value)
    return adapter


class FakeResponse:
    def __init__(self, content=b"", status_code=200, headers=None, json_data=None, error=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.headers = {}
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.handler(url, params)


class TestRateLimiter:
    def test_first_call_does_not_sleep(self):
        slept = []
        limiter = RateLimiter(requests_per_minute=60)
        original = time.sleep
        try:
            time.sleep = slept.append
            limiter.wait_if_needed("example.com")
        finally:
            time.sleep = original
        assert slept == []
        assert limiter._last_request.get("example.com") is not None

    def test_second_immediate_call_sleeps(self):
        slept = []
        limiter = RateLimiter(requests_per_minute=60)
        original = time.sleep
        try:
            time.sleep = slept.append
            limiter.wait_if_needed("example.com")
            limiter.wait_if_needed("example.com")
        finally:
            time.sleep = original
        assert len(slept) == 1
        assert slept[0] > 0

    def test_error_backoff_sequence_then_none(self):
        limiter = RateLimiter(requests_per_minute=60, max_retries=3)
        assert limiter.record_error("d.com") == 1.0
        assert limiter.record_error("d.com") == 2.0
        assert limiter.record_error("d.com") == 4.0
        assert limiter.record_error("d.com") is None

    def test_linear_backoff_when_not_exponential(self):
        limiter = RateLimiter(requests_per_minute=60, exponential_backoff=False)
        assert limiter.record_error("d.com") == 1.0
        assert limiter.record_error("d.com") == 2.0

    def test_success_resets_retry_count(self):
        limiter = RateLimiter(requests_per_minute=60, max_retries=1)
        assert limiter.record_error("d.com") == 1.0
        limiter.record_success("d.com")
        assert limiter.record_error("d.com") == 1.0

    def test_respect_retry_after_seconds(self):
        slept = []
        limiter = RateLimiter()
        original = time.sleep
        try:
            time.sleep = slept.append
            limiter.respect_retry_after("5")
        finally:
            time.sleep = original
        assert slept == [5]

    def test_respect_retry_after_invalid_ignored(self):
        limiter = RateLimiter()
        limiter.respect_retry_after("not-a-date-or-number")

    def test_respect_retry_after_http_date_does_not_raise(self):
        slept = []
        limiter = RateLimiter()
        original = time.sleep
        try:
            time.sleep = slept.append
            limiter.respect_retry_after("Wed, 21 Oct 2015 07:28:00 GMT")
        finally:
            time.sleep = original
        assert slept == []


class TestCrypto:
    def test_hash_content_known_vector(self):
        sha256, sha512 = hash_content(b"abc")
        assert sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        assert len(sha512) == 128

    def test_hash_text_matches_utf8_bytes(self):
        assert hash_text("abc") == hash_content("abc".encode("utf-8"))

    def test_verify_hash(self):
        sha256, _ = hash_content(b"data")
        assert verify_hash(b"data", sha256) is True
        assert verify_hash(b"other", sha256) is False

    def test_generate_document_id_defaults_to_full_digest(self):
        digest = "a" * 64
        assert generate_document_id(digest) == digest

    def test_generate_document_id_short_prefix_warns(self):
        with pytest.warns(DeprecationWarning):
            assert generate_document_id("a" * 64, prefix_length=16) == "a" * 16


class TestModels:
    def test_success_rate_zero_when_nothing_processed(self):
        job = IngestionJob(job_id="j", vertical="v", source_type="s")
        assert IngestionResult(job=job).success_rate == 0.0

    def test_success_rate_percentage(self):
        job = IngestionJob(job_id="j", vertical="v", source_type="s")
        job.documents_processed = 4
        job.documents_succeeded = 3
        assert IngestionResult(job=job).success_rate == 75.0

    def test_audit_entry_to_dict(self):
        entry = AuditEntry(
            timestamp=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            job_id="j1",
            action="fetch",
            resource_type="url",
        )
        data = entry.to_dict()
        assert data["job_id"] == "j1"
        assert data["timestamp"] == "2024-01-02T03:04:05+00:00"
        assert data["status"] == "success"


class TestAuditLogger:
    def test_log_writes_jsonl(self, tmp_path):
        logger = AuditLogger("job-1", tmp_path)
        logger.log("fetch", "url", resource_id="https://x.example", status="success")
        lines = (tmp_path / "job_job-1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["job_id"] == "job-1"
        assert record["action"] == "fetch"
        assert record["resource_id"] == "https://x.example"

    def test_helpers_record_expected_actions(self, tmp_path):
        logger = AuditLogger("job-2", tmp_path)
        logger.log_fetch("https://x.example", "success", http_status=200)
        logger.log_parse("doc-1", "success", "text_parser")
        logger.log_store("doc-1", "success", "documents/v/doc-1.bin")
        logger.log_skip("doc-2", "duplicate")
        records = [
            json.loads(line) for line in (tmp_path / "job_job-2.jsonl").read_text(encoding="utf-8").strip().split("\n")
        ]
        assert [r["action"] for r in records] == ["fetch", "parse", "store", "skip"]
        assert records[0]["details"] == {"http_status": 200}
        assert records[3]["status"] == "skipped"

    def test_no_audit_dir_writes_nothing(self):
        logger = AuditLogger("job-3", None)
        logger.log("fetch", "url")


class TestStorageManager:
    def test_store_and_retrieve_roundtrip(self, tmp_path):
        manager = StorageManager(tmp_path)
        doc_id, storage_key, sha = manager.store_document(b"hello", "food")
        assert manager.retrieve_document(storage_key) == b"hello"
        assert manager.document_exists(sha, "food") is True
        assert storage_key.startswith("documents/food/")

    def test_document_missing_returns_false(self, tmp_path):
        manager = StorageManager(tmp_path)
        assert manager.document_exists("0" * 64, "food") is False

    def test_unsafe_vertical_rejected(self, tmp_path):
        manager = StorageManager(tmp_path)
        with pytest.raises(ValueError):
            manager.store_document(b"x", "../escape")
        with pytest.raises(ValueError):
            manager.document_exists("0" * 64, "a/b")

    def test_unsafe_storage_key_rejected(self, tmp_path):
        manager = StorageManager(tmp_path)
        with pytest.raises(ValueError):
            manager.retrieve_document("../secret")
        with pytest.raises(ValueError):
            manager.retrieve_document("/absolute")


class TestECFRAdapter:
    def test_source_name(self):
        assert make_adapter(ECFRAdapter).get_source_name() == "ecfr"

    def test_missing_params_yields_nothing(self):
        adapter = make_adapter(ECFRAdapter, session=FakeSession(lambda u, p: FakeResponse()))
        assert list(adapter.fetch_documents("food")) == []
        assert list(adapter.fetch_documents("food", cfr_title=21)) == []

    def test_success_yields_document_metadata(self):
        def handler(url, params):
            assert "title-21" in url
            assert params == {"part": "112"}
            return FakeResponse(b"<xml/>", headers={"ETag": '"abc"'})

        adapter = make_adapter(ECFRAdapter, session=FakeSession(handler))
        results = list(adapter.fetch_documents("food", cfr_title=21, cfr_part=112))
        assert len(results) == 1
        content, source_meta, doc_meta = results[0]
        assert content == b"<xml/>"
        assert source_meta.etag == '"abc"'
        assert doc_meta["cfr_references"] == ["21 CFR 112"]
        assert doc_meta["document_type"] == "regulation"

    def test_failure_yields_nothing(self):
        def handler(url, params):
            return FakeResponse(error=ValueError("boom"))

        adapter = make_adapter(ECFRAdapter, session=FakeSession(handler))
        assert list(adapter.fetch_documents("food", cfr_title=21, cfr_part=112)) == []


class TestFDAAdapter:
    def test_rate_limit_depends_on_api_key(self):
        assert FDAAdapter(api_key=None).rate_limiter.requests_per_minute == 40
        assert FDAAdapter(api_key="k").rate_limiter.requests_per_minute == 240

    def test_success_yields_warning_letters(self):
        payload = {
            "results": [
                {"company_name": "Acme", "letter_id": "L1", "posted_date": "2024-01-01", "subject": "s"},
                {"company_name": "Beta", "letter_id": "L2", "posted_date": "2024-01-02", "subject": "t"},
            ]
        }

        def handler(url, params):
            assert url.endswith("/food/enforcement.json")
            assert params["limit"] == 2
            return FakeResponse(b"{}", json_data=payload)

        adapter = make_adapter(FDAAdapter, session=FakeSession(handler), api_key=None)
        results = list(adapter.fetch_documents("food", max_documents=2))
        assert len(results) == 2
        content, _, doc_meta = results[0]
        assert json.loads(content)["company_name"] == "Acme"
        assert doc_meta["document_type"] == "warning_letter"
        assert doc_meta["agencies"] == ["FDA"]

    def test_failure_yields_nothing(self):
        def handler(url, params):
            return FakeResponse(error=ValueError("boom"))

        adapter = make_adapter(FDAAdapter, session=FakeSession(handler), api_key=None)
        assert list(adapter.fetch_documents("food")) == []


class TestFederalRegisterAdapter:
    def test_source_name(self):
        assert make_adapter(FederalRegisterAdapter).get_source_name() == "federal_register"

    def test_success_fetches_full_text(self):
        search = {"results": [{"document_number": "1", "title": "T", "full_text_xml_url": "https://x/doc.xml"}]}

        def handler(url, params):
            if url.endswith("documents.json"):
                assert params["per_page"] == 10
                return FakeResponse(b"{}", json_data=search)
            assert url == "https://x/doc.xml"
            return FakeResponse(b"body", headers={"Content-Type": "text/plain"})

        adapter = make_adapter(FederalRegisterAdapter, session=FakeSession(handler))
        results = list(adapter.fetch_documents("food", max_documents=10))
        assert len(results) == 1
        content, source_meta, doc_meta = results[0]
        assert content == b"body"
        assert source_meta.source_url == "https://x/doc.xml"
        assert doc_meta["document_number"] == "1"

    def test_skips_docs_without_number_or_url(self):
        search = {
            "results": [
                {"title": "no number"},
                {"document_number": "2", "title": "no url"},
            ]
        }
        adapter = make_adapter(
            FederalRegisterAdapter, session=FakeSession(lambda u, p: FakeResponse(b"{}", json_data=search))
        )
        assert list(adapter.fetch_documents("food")) == []

    def test_search_failure_yields_nothing(self):
        def handler(url, params):
            return FakeResponse(error=ValueError("boom"))

        adapter = make_adapter(FederalRegisterAdapter, session=FakeSession(handler))
        assert list(adapter.fetch_documents("food")) == []

    def test_parse_last_modified_is_timezone_aware(self):
        adapter = make_adapter(FederalRegisterAdapter)
        parsed = adapter._parse_last_modified("Wed, 21 Oct 2015 07:28:00 GMT")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() is not None

    def test_parse_last_modified_invalid_inputs(self):
        adapter = make_adapter(FederalRegisterAdapter)
        assert adapter._parse_last_modified(None) is None
        assert adapter._parse_last_modified("garbage") is None

    def test_extract_cfr_references(self):
        adapter = make_adapter(FederalRegisterAdapter)
        doc = {"regulations_dot_gov_info": {"documents": [{"title": 21, "part": 112}, {"nope": 1}]}}
        assert adapter._extract_cfr_references(doc) == ["21 CFR 112"]
        assert adapter._extract_cfr_references({}) == []


class TestFSMA204Adapter:
    def test_source_name(self):
        assert make_adapter(FSMA204Adapter).get_source_name() == "fsma_204"

    def test_main_page_only_when_no_ftl_link(self):
        html = b"<html><body><p>traceability</p></body></html>"

        def handler(url, params):
            return FakeResponse(html, headers={"Content-Type": "text/html"})

        adapter = make_adapter(FSMA204Adapter, session=FakeSession(handler))
        results = list(adapter.fetch_documents())
        assert len(results) == 1
        assert results[0][0] == html
        assert results[0][2]["agencies"] == ["FDA"]

    def test_ftl_link_followed(self):
        html = b'<html><body><a href="/ftl.pdf">Food Traceability List download</a></body></html>'

        def handler(url, params):
            if url.endswith("ftl.pdf"):
                return FakeResponse(b"%PDF", headers={"Content-Type": "application/pdf"})
            return FakeResponse(html, headers={"Content-Type": "text/html"})

        adapter = make_adapter(FSMA204Adapter, session=FakeSession(handler))
        results = list(adapter.fetch_documents(max_documents=5))
        assert len(results) == 2
        assert results[1][0] == b"%PDF"
        assert results[1][2]["title"] == "Food Traceability List (FTL)"

    def test_http_error_yields_nothing(self):
        import httpx

        def handler(url, params):
            return FakeResponse(error=httpx.ConnectError("down"))

        adapter = make_adapter(FSMA204Adapter, session=FakeSession(handler))
        assert list(adapter.fetch_documents()) == []


class FakeAdapter:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def fetch_documents(self, **kwargs):
        if self.error is not None:
            raise self.error
        yield from self.items


def engine_with(storage_path, monkeypatch, adapter):
    config = FrameworkConfig.default()
    config.storage.filesystem_path = Path(storage_path)
    engine = IngestionEngine(config, StorageManager(Path(storage_path)))
    monkeypatch.setattr(engine, "_create_adapter", lambda cfg, logger: adapter)
    return engine


class TestIngestionEngine:
    def test_run_job_stores_and_dedups(self, tmp_path, monkeypatch):
        from regengine_ingestion.models import SourceMetadata

        meta = SourceMetadata(
            source_url="https://x",
            fetch_timestamp=datetime.now(timezone.utc),
            http_headers={"Content-Type": "text/plain"},
        )
        items = [
            (b"doc-one", meta, {"title": "One"}),
            (b"doc-one", meta, {"title": "One dup"}),
            (b"doc-two", meta, {"title": "Two"}),
        ]
        engine = engine_with(tmp_path, monkeypatch, FakeAdapter(items))
        result = engine.run_job(IngestionConfig(source_type=SourceType.FDA, vertical="food", tenant_id="t-1"))
        assert result.job.status == JobStatus.COMPLETED
        assert result.job.tenant_id == "t-1"
        assert result.job.documents_processed == 3
        assert result.job.documents_succeeded == 2
        assert result.job.documents_skipped == 1
        assert [d.title for d in result.documents] == ["One", "Two"]
        assert {d.tenant_id for d in result.documents} == {"t-1"}
        assert result.success_rate == pytest.approx(200 / 3)

    def test_run_job_tolerates_parse_failure(self, tmp_path, monkeypatch):
        from regengine_ingestion.models import SourceMetadata

        meta = SourceMetadata(source_url="https://x", fetch_timestamp=datetime.now(timezone.utc))
        engine = engine_with(tmp_path, monkeypatch, FakeAdapter([(b"raw", meta, {"title": "R"})]))
        monkeypatch.setattr(engine.parser_registry, "parse", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
        result = engine.run_job(IngestionConfig(source_type=SourceType.FDA, vertical="food", tenant_id="t-1"))
        assert result.job.status == JobStatus.COMPLETED
        assert result.job.documents_succeeded == 1
        assert result.documents[0].text == ""
        assert result.documents[0].tenant_id == "t-1"

    def test_run_job_failure_marks_job_failed(self, tmp_path, monkeypatch):
        engine = engine_with(tmp_path, monkeypatch, FakeAdapter(error=RuntimeError("source down")))
        result = engine.run_job(IngestionConfig(source_type=SourceType.FDA, vertical="food"))
        assert result.job.status == JobStatus.FAILED
        assert result.job.error_message == "source down"
        assert result.job.completed_at is not None

    def test_create_adapter_rejects_unknown_source(self, tmp_path):
        engine = IngestionEngine(FrameworkConfig.default(), StorageManager(tmp_path))
        with pytest.raises(ValueError):
            engine._create_adapter(
                IngestionConfig(source_type=SourceType.WEB_CRAWLER, vertical="food"), audit_logger=None
            )

    def test_parse_date(self, tmp_path):
        engine = IngestionEngine(FrameworkConfig.default(), StorageManager(tmp_path))
        assert engine._parse_date(None) is None
        assert engine._parse_date("garbage") is None
        parsed = engine._parse_date("2024-01-02T03:04:05Z")
        assert parsed is not None
        assert parsed.utcoffset() is not None


class TestRobotsChecker:
    def test_allows_when_robots_unreadable(self, monkeypatch):
        import urllib.robotparser

        def boom(self):
            raise OSError("no network")

        monkeypatch.setattr(urllib.robotparser.RobotFileParser, "read", boom)
        assert RobotsChecker().can_fetch("https://example.com/page") is True

    def test_uses_cached_parser_result(self):
        checker = RobotsChecker()
        domain = "https://example.com"

        class Parser:
            def can_fetch(self, agent, url):
                return url.endswith("/allowed")

            def crawl_delay(self, agent):
                return 5

        checker._parsers[domain] = Parser()
        assert checker.can_fetch("https://example.com/allowed") is True
        assert checker.can_fetch("https://example.com/denied") is False
        assert checker.get_crawl_delay("https://example.com/allowed") == 5.0

    def test_crawl_delay_none_when_not_specified(self):
        checker = RobotsChecker()

        class Parser:
            def can_fetch(self, agent, url):
                return True

            def crawl_delay(self, agent):
                return None

        checker._parsers["https://example.com"] = Parser()
        assert checker.get_crawl_delay("https://example.com/page") is None
