"""Bulk-upload PDF fallback to LlamaIndex Extract (``_extract_pdf_with_agent``).

The deterministic PDF pass (pdfplumber tables, then a JSON blob in the text)
stays first and unchanged. Extract runs only when that pass produced no rows
and the extractor is enabled. These tests use a fake pdfplumber module (one
page, no tables, prose text) and a fake extractor, so nothing reaches the
network or the real SDK.
"""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.bulk_upload import parsers
from app.bulk_upload.parsers import PDF_NO_ROWS_WARNING, parse_incoming_file
from shared.document_extract import DocumentExtractUnavailable, ExtractEvidence, ExtractionResult
from starlette.datastructures import UploadFile

EXTRACTED = {
    "facilities": [
        {
            "name": "Salinas Packhouse",
            "street": "1200 Abbott St",
            "city": "Salinas",
            "state": "CA",
            "postal_code": "93901",
            "roles": ["Grower"],
        }
    ],
    "ftl_scopes": [{"facility_name": "Salinas Packhouse", "category_id": "2"}],
    "tlcs": [{"tlc_code": "TLC-2026-SAL-1001", "facility_name": "Salinas Packhouse"}],
    "events": [
        {
            "cte_type": "shipping",
            "event_time": "2026-03-03T12:00:00",
            "facility_name": "Salinas Packhouse",
            "tlc_code": "TLC-2026-SAL-1001",
            "quantity": "120",
            "unit_of_measure": "cases",
        }
    ],
}


def _evidence(**overrides: Any) -> ExtractEvidence:
    base: dict[str, Any] = {
        "purpose": "bulk_upload_pdf",
        "requested_tier": "agentic",
        "requested_version": "2026-10-01",
        "tier": "agentic",
        "version": "2026-10-01",
        "job_id": "job-77",
        "file_id": "file-77",
        "extraction_target": "per_doc",
        "schema_version": "1",
        "latency_ms": 1234,
        "pages_extracted": 2,
        "pages_billed": 2,
        "credits": 30.0,
    }
    base.update(overrides)
    return ExtractEvidence(**base)


class FakeExtractor:
    def __init__(self, *, enabled: bool = True, result: ExtractionResult | None = None, error: Exception | None = None):
        self.enabled = enabled
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def extract_async(self, content: bytes, **kwargs: Any) -> ExtractionResult:
        self.calls.append({"content": content, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class _FakePage:
    def __init__(self, text: str, tables: list[list[list[str]]] | None = None) -> None:
        self._text = text
        self._tables = tables or []

    def extract_tables(self) -> list[list[list[str]]]:
        return self._tables

    def extract_text(self) -> str:
        return self._text


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _pdfplumber_with(pages: list[_FakePage]) -> SimpleNamespace:
    return SimpleNamespace(open=lambda _buf: _FakePdf(pages))


def _upload(content: bytes = b"%PDF-1.4 letter", filename: str = "supplier_letter.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content), headers={"content-type": "application/pdf"})


def _parse(pdf_module: SimpleNamespace, extractor: FakeExtractor, upload: UploadFile | None = None) -> dict[str, Any]:
    with (
        patch.dict("sys.modules", {"pdfplumber": pdf_module}),
        patch.object(parsers, "get_document_extractor", return_value=extractor),
    ):
        return asyncio.run(parse_incoming_file(upload or _upload()))


PROSE = _pdfplumber_with([_FakePage("Dear buyer, Salinas Packhouse shipped lot TLC-2026-SAL-1001 on 3 March 2026.")])


def test_fallback_runs_when_tables_yield_nothing_and_rows_flow_through_classify_row():
    extractor = FakeExtractor(
        result=ExtractionResult(
            evidence=_evidence(), data=EXTRACTED, field_metadata={"facilities": [{"name": {"confidence": 0.97}}]}
        )
    )

    parsed = _parse(PROSE, extractor)

    (call,) = extractor.calls
    assert call["content"] == b"%PDF-1.4 letter"
    assert call["filename"] == "supplier_letter.pdf"
    assert call["purpose"] == "bulk_upload_pdf"
    assert call["schema_version"] == "1"
    assert call["max_pages"] == parsers._max_pdf_pages()
    assert call["data_schema"]["properties"].keys() == {"facilities", "ftl_scopes", "tlcs", "events"}

    assert [f["name"] for f in parsed["facilities"]] == ["Salinas Packhouse"]
    assert parsed["facilities"][0]["roles"] == ["Grower"]
    assert parsed["ftl_scopes"] == [{"facility_name": "Salinas Packhouse", "category_id": "2"}]
    assert parsed["tlcs"][0]["tlc_code"] == "TLC-2026-SAL-1001"
    event = parsed["events"][0]
    assert event["cte_type"] == "shipping"
    assert event["event_time"] == "2026-03-03T12:00:00"
    assert event["kde_data"]["quantity"] == "120"
    assert event["kde_data"]["unit_of_measure"] == "cases"

    extraction = parsed["extraction"]
    assert extraction["rows"] == 4
    assert extraction["evidence"]["job_id"] == "job-77"
    assert extraction["evidence"]["version"] == "2026-10-01"
    assert extraction["confidence"] == {"fields": 1, "min": 0.97, "mean": 0.97}
    assert extraction["field_metadata"] == {"facilities": [{"name": {"confidence": 0.97}}]}
    assert "data" not in extraction

    assert PDF_NO_ROWS_WARNING not in parsed["warnings"]
    assert any(
        w.startswith("4 rows extracted by LlamaIndex Extract (tier=agentic, version=2026-10-01)")
        for w in parsed["warnings"]
    )


def test_fallback_skipped_when_extractor_disabled():
    extractor = FakeExtractor(enabled=False)
    parsed = _parse(PROSE, extractor)
    assert extractor.calls == []
    assert parsed["warnings"] == [PDF_NO_ROWS_WARNING]
    assert "extraction" not in parsed
    assert parsed["facilities"] == [] and parsed["events"] == []


def test_fallback_skipped_when_tables_already_produced_rows():
    table = [["record_type", "name", "city", "state"], ["facility", "Fresno DC", "Fresno", "CA"]]
    extractor = FakeExtractor(result=ExtractionResult(evidence=_evidence(), data=EXTRACTED))
    parsed = _parse(_pdfplumber_with([_FakePage("", tables=[table])]), extractor)
    assert extractor.calls == []
    assert [f["name"] for f in parsed["facilities"]] == ["Fresno DC"]
    assert "extraction" not in parsed


def test_vendor_failure_leaves_deterministic_result_with_one_warning():
    extractor = FakeExtractor(error=DocumentExtractUnavailable("rate_limited", purpose="bulk_upload_pdf", status=429))
    parsed = _parse(PROSE, extractor)
    assert parsed["facilities"] == [] and parsed["events"] == []
    assert "extraction" not in parsed
    assert parsed["warnings"] == [
        PDF_NO_ROWS_WARNING,
        "Document extraction agent unavailable (rate_limited); PDF parsed by tables only",
    ]


def test_unexpected_exception_is_fail_open_and_logged(caplog):
    """Anything that is not a vendor error (a bug, an odd response shape) must not 500 the upload."""
    extractor = FakeExtractor(error=AttributeError("'NoneType' object has no attribute 'id'"))
    with caplog.at_level("ERROR", logger="bulk_upload.parsers"):
        parsed = _parse(PROSE, extractor)
    assert parsed["facilities"] == [] and parsed["events"] == []
    assert "extraction" not in parsed
    assert parsed["warnings"] == [
        PDF_NO_ROWS_WARNING,
        "Document extraction agent failed unexpectedly; PDF parsed by tables only",
    ]
    assert any(
        record.getMessage() == "document_extract_fallback_failed" and record.exc_info for record in caplog.records
    )


def test_failure_while_converting_rows_leaves_no_partial_rows():
    """A conversion failure after some rows were classified must not leak those rows into the upload."""
    extractor = FakeExtractor(
        result=ExtractionResult(
            evidence=_evidence(),
            data={"facilities": [{"name": "Salinas Packhouse"}], "events": [{"cte_type": "shipping"}]},
        )
    )
    original = parsers._classify_row
    calls = {"n": 0}

    def flaky_classify(parsed: dict[str, Any], row: dict[str, Any], *, warnings: list[str]) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom on second row")
        original(parsed, row, warnings=warnings)

    with patch.object(parsers, "_classify_row", flaky_classify):
        parsed = _parse(PROSE, extractor)
    assert calls["n"] == 2
    assert parsed["facilities"] == [] and parsed["events"] == []
    assert "extraction" not in parsed
    assert parsed["warnings"][-1] == "Document extraction agent failed unexpectedly; PDF parsed by tables only"


def test_extraction_with_no_records_keeps_no_rows_warning():
    extractor = FakeExtractor(result=ExtractionResult(evidence=_evidence(), data={"facilities": [], "events": []}))
    parsed = _parse(PROSE, extractor)
    assert parsed["extraction"]["rows"] == 0
    assert PDF_NO_ROWS_WARNING in parsed["warnings"]
    assert "Document extraction agent found no FSMA 204 records in this PDF" in parsed["warnings"]


def test_page_bomb_guard_still_runs_before_any_extraction():
    pages = [MagicMock() for _ in range(parsers.DEFAULT_MAX_PDF_PAGES + 1)]
    extractor = FakeExtractor(result=ExtractionResult(evidence=_evidence(), data=EXTRACTED))
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as info:
        _parse(_pdfplumber_with(pages), extractor)
    assert info.value.status_code == 413
    assert extractor.calls == []
