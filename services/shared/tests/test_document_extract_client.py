"""Offline tests for the LlamaIndex Extract wrapper in ``services/shared/document_extract``.

Every test injects a fake SDK client, so nothing reaches the network. The
contract under test:

* disabled without ``LLAMA_CLOUD_API_KEY`` (or with the kill switch) and the
  caller learns that through ``DocumentExtractUnavailable("disabled")``;
* one call uploads the document, runs the job with the pinned tier/version
  and the data-minimisation switches, and deletes the vendor-side file even
  when the job fails;
* results convert to plain, JSON-safe data with evidence and a confidence
  summary attached;
* every SDK or polling failure becomes ``DocumentExtractUnavailable`` with a
  stable ``reason``;
* extracted values never appear in RegEngine's own log records, and a
  successful call leaves a stdlib ``document_extract_completed`` line;
* settings parse defensively and never raise on the request path;
* the supplier schema's result flattens into bulk-upload parser rows.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import structlog
from llama_cloud import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from llama_cloud._polling import PollingError, PollingTimeoutError
from shared.document_extract import (
    SUPPLIER_DOCUMENT_SCHEMA,
    DocumentExtractor,
    DocumentExtractSettings,
    DocumentExtractUnavailable,
    classify_error,
    get_document_extractor,
    mime_type_for,
    reset_document_extractor,
    rows_from_extraction,
    settings as extract_settings,
    summarize_confidences,
)
from shared.document_extract.supplier_schema import MAX_ROWS_PER_SECTION

EXTRACTED = {
    "facilities": [
        {
            "name": "Salinas Packhouse",
            "street": "1200 Abbott St",
            "city": "Salinas",
            "state": "CA",
            "postal_code": "93901",
            "fda_registration_number": "",
            "roles": ["Grower", "Packer"],
        }
    ],
    "ftl_scopes": [{"facility_name": "Salinas Packhouse", "category_id": "", "category_name": "leafy greens"}],
    "tlcs": [
        {"tlc_code": "TLC-2026-SAL-1001", "facility_name": "Salinas Packhouse", "product_description": "", "status": ""}
    ],
    "events": [
        {
            "cte_type": "shipping",
            "event_time": "2026-03-03T12:00:00",
            "facility_name": "Salinas Packhouse",
            "tlc_code": "TLC-2026-SAL-1001",
            "quantity": "120",
            "unit_of_measure": "cases",
            "destination_facility_name": "Fresno DC",
        }
    ],
}
FIELD_METADATA = {
    "facilities": [
        {
            "name": {"confidence": 0.98, "citation": [{"page": 1, "matching_text": "Salinas Packhouse"}]},
            "city": {"confidence": 0.91, "citation": []},
        }
    ],
    "events": [{"cte_type": {"confidence": 0.72}, "quantity": {"confidence": 1.4}}],
}


def _settings(**overrides: Any) -> DocumentExtractSettings:
    base: dict[str, Any] = {"api_key": "test-key", "max_retries": 0, "timeout_seconds": 1.0}  # pragma: allowlist secret
    base.update(overrides)
    return DocumentExtractSettings(**base)


def _job(
    *,
    job_id: str = "job-1",
    data: Any = None,
    field_metadata: Any = None,
    tier: str = "agentic",
    version: str = "2026-10-01",
) -> SimpleNamespace:
    document_metadata = FIELD_METADATA if field_metadata is None else field_metadata
    return SimpleNamespace(
        id=job_id,
        status="COMPLETED",
        extract_result=EXTRACTED if data is None else data,
        configuration=SimpleNamespace(tier=tier, version=version),
        extract_metadata=SimpleNamespace(
            field_metadata=SimpleNamespace(document_metadata=document_metadata, page_metadata=None, row_metadata=None),
            parse_job_id="parse-1",
            parse_tier=tier,
        ),
        metadata=SimpleNamespace(usage=SimpleNamespace(num_pages_extracted=3, num_pages_billed=3)),
        usage=SimpleNamespace(credits=45.0, extract_credits=45.0, parse_credits=0.0),
    )


class FakeFiles:
    def __init__(self, *, create_error: BaseException | None = None, delete_error: BaseException | None = None) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.create_error = create_error
        self.delete_error = delete_error

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.created.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return SimpleNamespace(id="file-1", name=kwargs["file"][0], project_id="proj")

    def delete(self, file_id: str, **kwargs: Any) -> None:
        self.deleted.append(file_id)
        if self.delete_error is not None:
            raise self.delete_error


class FakeExtract:
    def __init__(self, *, job: SimpleNamespace | None = None, run_error: BaseException | None = None) -> None:
        self.runs: list[dict[str, Any]] = []
        self.job = job if job is not None else _job()
        self.run_error = run_error

    def run(self, **kwargs: Any) -> SimpleNamespace:
        self.runs.append(kwargs)
        if self.run_error is not None:
            raise self.run_error
        return self.job


class FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.files = FakeFiles(create_error=kwargs.get("create_error"), delete_error=kwargs.get("delete_error"))
        self.extract = FakeExtract(job=kwargs.get("job"), run_error=kwargs.get("run_error"))
        self.closed = False

    def close(self) -> None:
        self.closed = True


class AsyncFakeFiles(FakeFiles):
    async def create(self, **kwargs: Any) -> SimpleNamespace:  # type: ignore[override]
        return super().create(**kwargs)

    async def delete(self, file_id: str, **kwargs: Any) -> None:  # type: ignore[override]
        super().delete(file_id, **kwargs)


class AsyncFakeExtract(FakeExtract):
    async def run(self, **kwargs: Any) -> SimpleNamespace:  # type: ignore[override]
        return super().run(**kwargs)


class AsyncFakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.files = AsyncFakeFiles(create_error=kwargs.get("create_error"), delete_error=kwargs.get("delete_error"))
        self.extract = AsyncFakeExtract(job=kwargs.get("job"), run_error=kwargs.get("run_error"))
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.cloud.llamaindex.ai/api/v2/extract")


def _status_error(cls: type[APIStatusError], status: int) -> APIStatusError:
    response = httpx.Response(status, request=_request(), json={"detail": "x"})
    return cls("boom", response=response, body=None)


def _extract(extractor: DocumentExtractor, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "filename": "packet.pdf",
        "data_schema": SUPPLIER_DOCUMENT_SCHEMA,
        "purpose": "test",
        "schema_version": "1",
    }
    kwargs.update(overrides)
    return extractor.extract(b"%PDF-1.4 test", **kwargs)


# -- disabled / settings -------------------------------------------------------


def test_disabled_without_key_raises_disabled():
    extractor = DocumentExtractor(DocumentExtractSettings(api_key=None), client=FakeClient())
    assert extractor.enabled is False
    with pytest.raises(DocumentExtractUnavailable) as info:
        _extract(extractor)
    assert info.value.reason == "disabled"
    assert extractor._client.files.created == []


def test_kill_switch_disables_even_with_key():
    settings = DocumentExtractSettings.from_env(
        {"LLAMA_CLOUD_API_KEY": "k", "REGENGINE_DOC_EXTRACT_ENABLED": "0"}  # pragma: allowlist secret
    )
    assert settings.enabled is False
    assert settings.public_summary()["kill_switch"] is True
    assert settings.public_summary()["key_present"] is True


def test_settings_defaults_pin_extract_v25_and_data_minimisation():
    settings = DocumentExtractSettings.from_env({})
    assert settings.enabled is False
    assert settings.tier == "agentic"
    assert settings.version == extract_settings.DEFAULT_VERSION == "2026-10-01"
    assert settings.disable_cache is True
    assert settings.cite_sources is True
    assert settings.confidence_scores is True
    assert settings.max_pages == 50
    assert "api_key" not in repr(settings)


def test_settings_parse_defensively():
    settings = DocumentExtractSettings.from_env(
        {
            "LLAMA_CLOUD_API_KEY": "k",  # pragma: allowlist secret
            "REGENGINE_DOC_EXTRACT_TIER": "Agentic_Plus",
            "REGENGINE_DOC_EXTRACT_VERSION": "latest",
            "REGENGINE_DOC_EXTRACT_TIMEOUT_SECONDS": "not-a-number",
            "REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS": "99999",
            "REGENGINE_DOC_EXTRACT_MAX_RETRIES": "9",
            "REGENGINE_DOC_EXTRACT_MAX_PAGES": "0",
            "REGENGINE_DOC_EXTRACT_DISABLE_CACHE": "false",
            "REGENGINE_DOC_EXTRACT_CITE_SOURCES": "off",
        }
    )
    assert settings.enabled is True
    assert settings.tier == "agentic_plus"
    assert settings.version == "latest"
    assert settings.timeout_seconds == extract_settings.DEFAULT_TIMEOUT_SECONDS
    assert settings.job_timeout_seconds == extract_settings.DEFAULT_JOB_TIMEOUT_SECONDS
    assert settings.max_retries == extract_settings.DEFAULT_MAX_RETRIES
    assert settings.max_pages == extract_settings.DEFAULT_MAX_PAGES
    assert settings.disable_cache is False
    assert settings.cite_sources is False
    unknown_tier = DocumentExtractSettings.from_env({"REGENGINE_DOC_EXTRACT_TIER": "premium"})
    assert unknown_tier.tier == "agentic"
    summary = settings.public_summary()
    assert "k" not in summary.values()
    assert set(summary) == {
        "enabled",
        "key_present",
        "kill_switch",
        "tier",
        "version",
        "max_pages",
        "cite_sources",
        "confidence_scores",
        "disable_cache",
    }


# -- happy path -----------------------------------------------------------------


def test_extract_uploads_runs_and_deletes_with_pinned_configuration():
    client = FakeClient()
    extractor = DocumentExtractor(_settings(max_pages=40), client=client)

    result = _extract(extractor, max_pages=200)

    (created,) = client.files.created
    assert created["purpose"] == "extract"
    assert created["file"] == ("packet.pdf", b"%PDF-1.4 test", "application/pdf")
    (run,) = client.extract.runs
    assert run["file_input"] == "file-1"
    assert run["polling_timeout"] == extractor.settings.job_timeout_seconds
    configuration = run["configuration"]
    assert configuration["tier"] == "agentic"
    assert configuration["version"] == "2026-10-01"
    assert configuration["extraction_target"] == "per_doc"
    assert configuration["max_pages"] == 40  # caller asked for 200; environment caps at 40
    assert configuration["cite_sources"] is True
    assert configuration["confidence_scores"] is True
    assert configuration["disable_cache"] is True
    assert "system_prompt" not in configuration
    assert configuration["data_schema"] == SUPPLIER_DOCUMENT_SCHEMA
    assert client.files.deleted == ["file-1"]

    assert result.data == EXTRACTED
    assert result.records() == [EXTRACTED]
    evidence = result.evidence
    assert evidence.job_id == "job-1"
    assert evidence.file_id == "file-1"
    assert evidence.tier == "agentic"
    assert evidence.version == "2026-10-01"
    assert evidence.requested_version == "2026-10-01"
    assert evidence.pages_extracted == 3
    assert evidence.pages_billed == 3
    assert evidence.credits == 45.0
    assert evidence.parse_job_id == "parse-1"
    assert evidence.schema_version == "1"
    assert evidence.provider == "llamaindex"
    assert evidence.latency_ms >= 0

    summary = result.confidence_summary()
    assert summary["fields"] == 4
    assert summary["min"] == 0.72
    assert summary["mean"] == round((0.98 + 0.91 + 0.72 + 1.0) / 4, 4)  # 1.4 clamps to 1.0

    as_dict = result.to_dict()
    assert as_dict["data"] == EXTRACTED
    assert as_dict["field_metadata"] == FIELD_METADATA
    assert as_dict["evidence"]["job_id"] == "job-1"
    assert "data" not in result.to_dict(include_data=False)


def test_extract_passes_system_prompt_project_and_target():
    client = FakeClient(job=_job(data=[{"facilities": []}, {"tlcs": [{"tlc_code": "A"}]}]))
    extractor = DocumentExtractor(_settings(project_id="proj-9"), client=client)
    result = _extract(extractor, extraction_target="per_page", system_prompt="Only read page headers.")
    (run,) = client.extract.runs
    assert run["project_id"] == "proj-9"
    assert run["configuration"]["extraction_target"] == "per_page"
    assert run["configuration"]["system_prompt"] == "Only read page headers."
    assert client.files.created[0]["project_id"] == "proj-9"
    assert result.records() == [{"facilities": []}, {"tlcs": [{"tlc_code": "A"}]}]


def test_extract_rejects_unknown_target_before_any_upload():
    client = FakeClient()
    extractor = DocumentExtractor(_settings(), client=client)
    with pytest.raises(ValueError):
        _extract(extractor, extraction_target="per_sentence")
    assert client.files.created == []


def test_extract_async_mirrors_sync():
    client = AsyncFakeClient()
    extractor = DocumentExtractor(_settings(), async_client=client)
    result = asyncio.run(
        extractor.extract_async(
            b"%PDF", filename="scan.PDF", data_schema=SUPPLIER_DOCUMENT_SCHEMA, purpose="test_async"
        )
    )
    assert result.evidence.purpose == "test_async"
    assert client.files.created[0]["file"][2] == "application/pdf"
    assert client.files.deleted == ["file-1"]
    asyncio.run(extractor.aclose())
    assert client.closed is True


# -- failures -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "reason", "status"),
    [
        (APITimeoutError(_request()), "timeout", None),
        (APIConnectionError(request=_request()), "connection", None),
        (_status_error(RateLimitError, 429), "rate_limited", 429),
        (_status_error(AuthenticationError, 401), "auth", 401),
        (_status_error(PermissionDeniedError, 403), "auth", 403),
        (_status_error(NotFoundError, 404), "not_found", 404),
        (_status_error(BadRequestError, 400), "bad_request", 400),
        (_status_error(UnprocessableEntityError, 422), "bad_request", 422),
        (_status_error(InternalServerError, 503), "server_error", 503),
        (_status_error(APIStatusError, 409), "api_error", 409),
        (
            APIResponseValidationError(httpx.Response(200, request=_request(), text="{}"), None),
            "invalid_response",
            None,
        ),
        (PollingError("Job failed: bad schema"), "job_failed", None),
        (PollingTimeoutError("Polling timed out"), "job_timeout", None),
    ],
)
def test_run_failures_become_unavailable_and_still_delete_the_file(exc, reason, status):
    assert classify_error(exc) == reason
    client = FakeClient(run_error=exc)
    extractor = DocumentExtractor(_settings(), client=client)
    with pytest.raises(DocumentExtractUnavailable) as info:
        _extract(extractor)
    assert info.value.reason == reason
    assert info.value.status == status
    assert info.value.purpose == "test"
    assert client.files.deleted == ["file-1"]


def test_upload_failure_becomes_unavailable_without_delete():
    client = FakeClient(create_error=_status_error(AuthenticationError, 401))
    extractor = DocumentExtractor(_settings(), client=client)
    with pytest.raises(DocumentExtractUnavailable) as info:
        _extract(extractor)
    assert info.value.reason == "auth"
    assert client.extract.runs == []
    assert client.files.deleted == []


def test_delete_failure_is_logged_not_raised(caplog):
    client = FakeClient(delete_error=_status_error(InternalServerError, 500))
    extractor = DocumentExtractor(_settings(), client=client)
    with structlog.testing.capture_logs() as logs:
        result = _extract(extractor)
    assert result.evidence.job_id == "job-1"
    assert any(event["event"] == "document_extract.file_delete_failed" for event in logs)


def test_empty_result_is_unavailable():
    client = FakeClient(job=_job(data={}))
    extractor = DocumentExtractor(_settings(), client=client)
    with pytest.raises(DocumentExtractUnavailable) as info:
        _extract(extractor)
    assert info.value.reason == "empty_result"
    assert info.value.job_id == "job-1"


def test_unexpected_exception_propagates():
    """Only SDK/polling errors are fail-open; a programming error must surface."""
    client = FakeClient(run_error=KeyError("bug"))
    extractor = DocumentExtractor(_settings(), client=client)
    with pytest.raises(KeyError):
        _extract(extractor)
    assert client.files.deleted == ["file-1"]


# -- logging -------------------------------------------------------------------


def test_logs_carry_metadata_only_and_leave_an_ops_line(caplog):
    client = FakeClient()
    extractor = DocumentExtractor(_settings(), client=client)
    with caplog.at_level(logging.INFO, logger="document_extract"), structlog.testing.capture_logs() as logs:
        _extract(extractor)
    rendered = " ".join(str(event) for event in logs) + " " + caplog.text
    assert "Salinas" not in rendered
    assert "Abbott" not in rendered
    assert "TLC-2026" not in rendered
    assert "test-key" not in rendered
    completed = [event for event in logs if event["event"] == "document_extract.completed"]
    assert completed and completed[0]["job_id"] == "job-1" and completed[0]["records"] == 1
    assert any(
        "document_extract_completed purpose=test job_id=job-1" in record.getMessage() for record in caplog.records
    )


def test_unavailable_log_carries_no_document(caplog):
    client = FakeClient(run_error=_status_error(InternalServerError, 502))
    extractor = DocumentExtractor(_settings(), client=client)
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(DocumentExtractUnavailable):
            _extract(extractor)
    (event,) = [event for event in logs if event["event"] == "document_extract.unavailable"]
    assert event["reason"] == "server_error"
    assert event["status"] == 502
    assert "PDF" not in str(event)


# -- helpers ---------------------------------------------------------------------


def test_mime_type_for():
    assert mime_type_for("a.PDF") == "application/pdf"
    assert mime_type_for("scan.jpeg") == "image/jpeg"
    assert mime_type_for("noext") == "application/octet-stream"


def test_summarize_confidences_handles_nested_and_bad_values():
    metadata = {
        "a": {"confidence": 0.5, "citation": [{"confidence": "high"}]},
        "b": [{"c": {"confidence": float("nan")}}, {"d": {"confidence": -0.2}}],
        "e": {"confidence": True},
    }
    assert summarize_confidences(metadata) == {"fields": 2, "min": 0.0, "mean": 0.25}
    assert summarize_confidences(None, []) == {"fields": 0, "min": None, "mean": None}


def test_rows_from_extraction_flattens_sections_with_record_types():
    rows = rows_from_extraction(EXTRACTED)
    assert [row["record_type"] for row in rows] == ["facility", "ftl_scope", "tlc", "event"]
    facility = rows[0]
    assert facility["name"] == "Salinas Packhouse"
    assert "fda_registration_number" not in facility  # blank dropped
    assert rows[3]["destination_facility_name"] == "Fresno DC"


def test_rows_from_extraction_merges_pages_skips_junk_and_caps():
    pages = [
        {"facilities": [{"name": "A"}, "not-a-dict", {"name": ""}]},
        {"tlcs": [{"tlc_code": f"T{i}"} for i in range(MAX_ROWS_PER_SECTION + 5)]},
        "garbage",
    ]
    rows = rows_from_extraction(pages)
    assert rows[0] == {"name": "A", "record_type": "facility"}
    assert sum(1 for row in rows if row["record_type"] == "tlc") == MAX_ROWS_PER_SECTION
    assert rows_from_extraction(None) == []


def test_default_extractor_is_cached_and_resettable(monkeypatch):
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    reset_document_extractor()
    first = get_document_extractor()
    assert first is get_document_extractor()
    assert first.enabled is False
    reset_document_extractor()
    assert get_document_extractor() is not first
    reset_document_extractor()
