"""Offline tests for the LlamaCloud Extract wrapper in ``services/shared/llama_extract``.

Every test uses ``httpx.MockTransport`` so nothing reaches the network. The
contract under test:

* disabled without ``LLAMA_CLOUD_API_KEY`` (or with the kill switch) and the
  caller learns that through ``LlamaExtractUnavailable("disabled")``;
* the upload and the job request on the wire carry the file, the schema and
  the tier/version/evidence switches exactly as the SDK serialises them;
* a completed job converts to plain, JSON-safe data with evidence attached;
* every SDK failure and every failed job becomes ``LlamaExtractUnavailable``
  with a stable ``reason``;
* document content and extracted values never appear in RegEngine's own log
  records, and a successful call leaves a stdlib ``llama_extract_completed``
  line;
* settings parse defensively and never raise.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import structlog
from pydantic import BaseModel, Field
from shared.llama_extract import (
    DocumentExtractor,
    ExtractionResult,
    LlamaExtractSettings,
    LlamaExtractUnavailable,
    classify_error,
    get_document_extractor,
    guard_sdk_logging,
    reset_document_extractor,
    schema_digest,
    schema_from,
    settings as extract_settings,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "lot_code": {"type": "string", "description": "Traceability lot code"},
        "ship_date": {"type": "string", "description": "Ship date, ISO 8601"},
    },
    "required": ["lot_code"],
}
DOCUMENT = b"%PDF-1.4 secret-lot-contents"
FILE_NAME = "bol.pdf"
PENDING_JOB = {
    "id": "job_1",
    "created_at": "2026-10-05T10:00:00Z",
    "updated_at": "2026-10-05T10:00:00Z",
    "file_input": "file_1",
    "project_id": "proj_1",
    "status": "PENDING",
}
COMPLETED_JOB = {
    **PENDING_JOB,
    "status": "COMPLETED",
    "configuration": {"data_schema": SCHEMA, "tier": "agentic", "version": "2.5.0-2026-10-01"},
    "extract_result": {"lot_code": "LOT-4471", "ship_date": "2026-09-30"},
    "extract_metadata": {
        "field_metadata": {
            "document_metadata": {
                "lot_code": {"citation": [{"page": 1, "matching_text": "Lot LOT-4471"}], "confidence": 0.97},
                "ship_date": {"citation": [{"page": 1, "matching_text": "Shipped 9/30/26"}], "confidence": 0.81},
            }
        },
        "parse_job_id": "parse_9",
    },
    "metadata": {"usage": {"num_pages_billed": 2, "num_pages_extracted": 2}},
    "usage": {"credits": 30.0, "extract_credits": 30.0, "parse_credits": 0.0},
}


def _settings(**overrides) -> LlamaExtractSettings:
    base = {"api_key": "test-key", "timeout_seconds": 5.0}  # pragma: allowlist secret
    base.update(overrides)
    return LlamaExtractSettings(**base)


def _extractor(handler, **overrides) -> DocumentExtractor:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return DocumentExtractor(_settings(**overrides), http_client=client, polling_interval=0.0)


class _Recorder:
    """Serve upload -> create -> poll, remembering every request."""

    def __init__(self, *, final_job=None, polls_before_done: int = 1):
        self.requests: list[httpx.Request] = []
        self.final_job = COMPLETED_JOB if final_job is None else final_job
        self.polls_before_done = polls_before_done
        self.polls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file_1", "name": FILE_NAME, "project_id": "proj_1"})
        if request.method == "POST" and request.url.path == "/api/v2/extract":
            return httpx.Response(200, json=PENDING_JOB)
        if request.method == "GET" and request.url.path == "/api/v2/extract/job_1":
            self.polls += 1
            if self.polls < self.polls_before_done:
                return httpx.Response(200, json={**PENDING_JOB, "status": "RUNNING"})
            return httpx.Response(200, json=self.final_job)
        return httpx.Response(404, json={"detail": f"unexpected {request.method} {request.url.path}"})


# ---------------------------------------------------------------------------
# Disabled / configuration
# ---------------------------------------------------------------------------


def test_disabled_without_key_sends_nothing():
    recorder = _Recorder()
    extractor = _extractor(recorder, api_key=None)
    assert extractor.enabled is False
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "disabled"
    assert recorder.requests == []


def test_kill_switch_disables_even_with_key():
    recorder = _Recorder()
    extractor = _extractor(recorder, enabled_flag=False)
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "disabled"
    assert recorder.requests == []


def test_settings_from_env_defaults_and_overrides():
    defaults = LlamaExtractSettings.from_env({})
    assert defaults.enabled is False
    assert defaults.tier == "agentic"
    assert defaults.version == "2.5"
    assert defaults.cite_sources and defaults.confidence_scores and defaults.disable_cache
    assert defaults.max_pages == 0

    custom = LlamaExtractSettings.from_env(
        {
            extract_settings.API_KEY_ENV: " k ",
            extract_settings.TIER_ENV: "Agentic_Plus",
            extract_settings.VERSION_ENV: "latest",
            extract_settings.TIMEOUT_ENV: "30",
            extract_settings.MAX_PAGES_ENV: "12",
            extract_settings.CITE_SOURCES_ENV: "0",
            extract_settings.CONFIDENCE_SCORES_ENV: "false",
            extract_settings.DISABLE_CACHE_ENV: "off",
            extract_settings.PROJECT_ID_ENV: "proj_x",
            extract_settings.BASE_URL_ENV: "https://eu.example.test",
        }
    )
    assert custom.enabled is True
    assert custom.api_key == "k"
    assert custom.tier == "agentic_plus"
    assert custom.version == "latest"
    assert custom.timeout_seconds == 30.0
    assert custom.max_pages == 12
    assert custom.cite_sources is False and custom.confidence_scores is False and custom.disable_cache is False
    assert custom.project_id == "proj_x"
    assert custom.base_url == "https://eu.example.test"


def test_settings_invalid_values_fall_back_without_raising():
    settings = LlamaExtractSettings.from_env(
        {
            extract_settings.API_KEY_ENV: "k",
            extract_settings.TIER_ENV: "premium",
            extract_settings.TIMEOUT_ENV: "forever",
            extract_settings.MAX_PAGES_ENV: "-3",
            extract_settings.ENABLED_ENV: "0",
        }
    )
    assert settings.tier == "agentic"
    assert settings.timeout_seconds == extract_settings.DEFAULT_TIMEOUT_SECONDS
    assert settings.max_pages == 0
    assert settings.enabled is False and settings.enabled_flag is False


def test_public_summary_never_contains_the_key():
    summary = _settings(api_key="super-secret-key").public_summary()  # pragma: allowlist secret
    assert summary["key_present"] is True
    assert "super-secret-key" not in json.dumps(summary)
    assert "super-secret-key" not in repr(_settings(api_key="super-secret-key"))  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


def test_upload_then_job_carries_schema_tier_version_and_switches():
    recorder = _Recorder(polls_before_done=2)
    extractor = _extractor(recorder, project_id="proj_1", max_pages=20)
    result = extractor.extract(
        DOCUMENT,
        file_name=FILE_NAME,
        data_schema=SCHEMA,
        purpose="receiving_bol",
        target_pages="1-2",
        system_prompt="Dates are US format.",
    )

    upload, create, *polls = recorder.requests
    assert upload.url.path == "/api/v1/beta/files"
    assert upload.headers["content-type"].startswith("multipart/form-data")
    assert upload.headers["authorization"] == "Bearer test-key"
    assert b'filename="bol.pdf"' in upload.content
    assert DOCUMENT in upload.content
    assert b'name="purpose"' in upload.content and b"extract" in upload.content
    assert upload.url.params.get("project_id") == "proj_1"

    body = json.loads(create.content)
    assert body["file_input"] == "file_1"
    config = body["configuration"]
    assert config["data_schema"] == SCHEMA
    assert config["tier"] == "agentic"
    assert config["version"] == "2.5"
    assert config["extraction_target"] == "per_doc"
    assert config["cite_sources"] is True
    assert config["confidence_scores"] is True
    assert config["disable_cache"] is True
    assert config["max_pages"] == 20
    assert config["target_pages"] == "1-2"
    assert config["system_prompt"] == "Dates are US format."
    assert "spreadsheet_mode" not in config

    assert [p.url.path for p in polls] == ["/api/v2/extract/job_1", "/api/v2/extract/job_1"]
    assert isinstance(result, ExtractionResult)


def test_per_call_overrides_win_over_settings():
    recorder = _Recorder()
    extractor = _extractor(recorder, tier="cost_effective", version="2.0", max_pages=50)
    extractor.extract(
        DOCUMENT,
        file_name=FILE_NAME,
        data_schema=SCHEMA,
        purpose="t",
        tier="agentic_plus",
        version="latest",
        max_pages=3,
        extraction_target="per_table_row",
        spreadsheet_mode=True,
    )
    config = json.loads(recorder.requests[1].content)["configuration"]
    assert config["tier"] == "agentic_plus"
    assert config["version"] == "latest"
    assert config["max_pages"] == 3
    assert config["extraction_target"] == "per_table_row"
    assert config["spreadsheet_mode"] is True


def test_pydantic_model_and_path_inputs(tmp_path):
    class BillOfLading(BaseModel):
        lot_code: str = Field(description="Traceability lot code")
        ship_date: str | None = None

    path = tmp_path / "shipment.pdf"
    path.write_bytes(DOCUMENT)
    recorder = _Recorder()
    extractor = _extractor(recorder)
    result = extractor.extract(path, data_schema=BillOfLading, purpose="t")

    assert b'filename="shipment.pdf"' in recorder.requests[0].content
    config = json.loads(recorder.requests[1].content)["configuration"]
    assert config["data_schema"] == BillOfLading.model_json_schema()
    assert result.evidence.file_name == "shipment.pdf"
    assert result.evidence.schema_sha256 == schema_digest(BillOfLading.model_json_schema())


def test_bytes_without_file_name_is_a_caller_error():
    extractor = _extractor(_Recorder())
    with pytest.raises(ValueError, match="file_name"):
        extractor.extract(DOCUMENT, data_schema=SCHEMA, purpose="t")


def test_bad_tier_or_target_is_a_caller_error_before_any_request():
    recorder = _Recorder()
    extractor = _extractor(recorder)
    with pytest.raises(ValueError):
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t", tier="premium")
    with pytest.raises(ValueError):
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t", extraction_target="per_row")
    with pytest.raises(TypeError):
        schema_from("not a schema")  # type: ignore[arg-type]
    assert recorder.requests == []


# ---------------------------------------------------------------------------
# Results and evidence
# ---------------------------------------------------------------------------


def test_completed_job_becomes_data_metadata_and_evidence():
    extractor = _extractor(_Recorder())
    result = extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="receiving_bol")

    assert result.data == {"lot_code": "LOT-4471", "ship_date": "2026-09-30"}
    assert result.field_metadata == {
        "target": "per_doc",
        "fields": COMPLETED_JOB["extract_metadata"]["field_metadata"]["document_metadata"],
    }
    evidence = result.evidence
    assert evidence.provider == "llama_cloud"
    assert evidence.product == "extract_v2"
    assert evidence.purpose == "receiving_bol"
    assert evidence.tier == "agentic"
    assert evidence.requested_version == "2.5"
    assert evidence.resolved_version == "2.5.0-2026-10-01"
    assert evidence.job_id == "job_1"
    assert evidence.file_id == "file_1"
    assert evidence.file_name == FILE_NAME
    assert evidence.pages_billed == 2 and evidence.pages_extracted == 2
    assert evidence.credits == 30.0
    assert evidence.parse_job_id == "parse_9"
    assert evidence.schema_sha256 == schema_digest(SCHEMA)
    assert evidence.sdk_version
    assert evidence.latency_ms >= 0
    # JSON-safe for persistence as an agent artifact.
    json.dumps(result.to_dict())


def test_per_page_result_uses_page_metadata():
    job = {
        **COMPLETED_JOB,
        "extract_result": [{"lot_code": "A"}, {"lot_code": "B"}],
        "extract_metadata": {"field_metadata": {"page_metadata": [{"lot_code": {"confidence": 0.9}}, {}]}},
    }
    extractor = _extractor(_Recorder(final_job=job))
    result = extractor.extract(
        DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t", extraction_target="per_page"
    )
    assert result.data == [{"lot_code": "A"}, {"lot_code": "B"}]
    assert result.field_metadata == {"target": "per_page", "fields": [{"lot_code": {"confidence": 0.9}}, {}]}


def test_completed_job_without_result_is_unavailable():
    job = {**COMPLETED_JOB, "extract_result": None, "extract_metadata": None}
    extractor = _extractor(_Recorder(final_job=job))
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "empty_result"
    assert excinfo.value.job_id == "job_1"


# ---------------------------------------------------------------------------
# Failures are fail-open with stable reasons
# ---------------------------------------------------------------------------


def _status_handler(status: int, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {"detail": "nope"})

    return handler


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "auth"), (403, "auth"), (429, "rate_limited"), (400, "bad_request"), (422, "bad_request")],
)
def test_upload_status_errors_map_to_reasons(status, reason):
    extractor = _extractor(_status_handler(status))
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == reason
    assert excinfo.value.status == status
    assert excinfo.value.purpose == "t"


def test_server_error_after_sdk_retry_is_server_error():
    extractor = _extractor(_status_handler(503))
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "server_error"
    assert excinfo.value.status == 503


def test_connection_error_is_connection():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    extractor = _extractor(handler)
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "connection"


def test_timeout_is_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    extractor = _extractor(handler)
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "timeout"


def test_failed_job_is_job_failed_with_job_id():
    job = {**PENDING_JOB, "status": "FAILED", "error_message": "could not parse page 3"}
    extractor = _extractor(_Recorder(final_job=job))
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "job_failed"
    assert excinfo.value.job_id == "job_1"


def test_polling_past_the_budget_is_timeout(monkeypatch):
    """A job that never completes stops at the settings budget, not the SDK's 2h default."""
    import llama_cloud._polling as polling

    class _Clock:
        """A stand-in for the ``time`` module inside the SDK's polling loop only."""

        def __init__(self) -> None:
            self.now = 0.0

        def time(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += 3.0  # every poll costs 3 fake seconds; the budget below is 5

    monkeypatch.setattr(polling, "time", _Clock())
    recorder = _Recorder(polls_before_done=10_000)
    extractor = _extractor(recorder, timeout_seconds=5.0)
    with pytest.raises(LlamaExtractUnavailable) as excinfo:
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    assert excinfo.value.reason == "timeout"
    assert excinfo.value.job_id == "job_1"
    assert recorder.polls <= 3


def test_classify_error_unknown_exception():
    assert classify_error(RuntimeError("x")) == ("sdk_error", None)


# ---------------------------------------------------------------------------
# Logging hygiene
# ---------------------------------------------------------------------------


def test_logs_carry_metadata_only_and_ops_line_on_success(caplog):
    with structlog.testing.capture_logs() as captured, caplog.at_level(logging.INFO, logger="llama_extract"):
        extractor = _extractor(_Recorder())
        extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="receiving_bol")

    dumped = json.dumps(captured, default=str)
    assert "secret-lot-contents" not in dumped
    assert "LOT-4471" not in dumped
    assert "test-key" not in dumped
    completed = [event for event in captured if event.get("event") == "llama_extract.completed"]
    assert completed and completed[0]["purpose"] == "receiving_bol" and completed[0]["job_id"] == "job_1"
    ops = [r for r in caplog.records if r.name == "llama_extract"]
    assert ops and "llama_extract_completed purpose=receiving_bol job=job_1" in ops[0].getMessage()
    assert "LOT-4471" not in ops[0].getMessage()


def test_failure_log_carries_reason_not_content():
    with structlog.testing.capture_logs() as captured:
        extractor = _extractor(_status_handler(401))
        with pytest.raises(LlamaExtractUnavailable):
            extractor.extract(DOCUMENT, file_name=FILE_NAME, data_schema=SCHEMA, purpose="t")
    warnings = [event for event in captured if event.get("event") == "llama_extract.unavailable"]
    assert warnings and warnings[0]["reason"] == "auth" and warnings[0]["status"] == 401
    assert "secret-lot-contents" not in json.dumps(captured, default=str)


def test_guard_sdk_logging_caps_debug_unless_opted_in(monkeypatch):
    sdk_logger = logging.getLogger("llama_cloud")
    monkeypatch.delenv("LLAMA_CLOUD_LOG", raising=False)
    sdk_logger.setLevel(logging.DEBUG)
    guard_sdk_logging()
    assert sdk_logger.level == logging.INFO

    monkeypatch.setenv("LLAMA_CLOUD_LOG", "debug")
    sdk_logger.setLevel(logging.DEBUG)
    guard_sdk_logging()
    assert sdk_logger.level == logging.DEBUG
    sdk_logger.setLevel(logging.NOTSET)


# ---------------------------------------------------------------------------
# Process-wide instance
# ---------------------------------------------------------------------------


def test_get_document_extractor_is_cached_until_reset(monkeypatch):
    monkeypatch.delenv(extract_settings.API_KEY_ENV, raising=False)
    reset_document_extractor()
    first = get_document_extractor()
    assert first is get_document_extractor()
    assert first.enabled is False
    monkeypatch.setenv(extract_settings.API_KEY_ENV, "k")
    assert get_document_extractor() is first  # cached: env change needs a reset
    reset_document_extractor()
    assert get_document_extractor().enabled is True
    reset_document_extractor()
