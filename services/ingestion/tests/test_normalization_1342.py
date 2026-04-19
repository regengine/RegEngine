"""Coverage for app/normalization.py — regulatory document normalization.

Locks:
- normalize_document field shape and hash determinism
- _derive_document_id: sha256 of source_url + first 4096 chars of text
- _content_hash: excludes content_sha256, stable across dict ordering
- _serialize_datetime: datetime/list/dict/passthrough
- _extract_text: payload text short-circuits, then format-specific
  dispatch (html / xml / csv / excel / docx / edi / pdf / bytes fallback
  / empty)
- _extract_text_from_payload: body > text > content > abstract preference
- _extract_from_pdf: pdfminer happy path (with monkeypatched extractor)
- _parse_datetime: None, datetime (tz + naive), ISO string, garbage → None

Issue: #1342
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import normalization as norm
from app.models import PositionMapEntry, TextExtractionMetadata
from app.normalization import (
    _content_hash,
    _derive_document_id,
    _extract_from_pdf,
    _extract_text,
    _extract_text_from_payload,
    _parse_datetime,
    _serialize_datetime,
    normalize_document,
)


# ---------------------------------------------------------------------------
# _serialize_datetime
# ---------------------------------------------------------------------------


class TestSerializeDatetime:
    def test_datetime_converts_to_iso_utc(self):
        dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert _serialize_datetime(dt) == "2026-01-02T03:04:05+00:00"

    def test_list_recurses(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _serialize_datetime([dt, "x", 1])
        assert result[0].startswith("2026-01-01")
        assert result[1] == "x"
        assert result[2] == 1

    def test_dict_recurses(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _serialize_datetime({"d": dt, "n": 42, "s": "hi"})
        assert result["d"].startswith("2026-01-01")
        assert result["n"] == 42
        assert result["s"] == "hi"

    def test_primitive_passthrough(self):
        assert _serialize_datetime("hello") == "hello"
        assert _serialize_datetime(42) == 42
        assert _serialize_datetime(None) is None
        assert _serialize_datetime(3.14) == 3.14

    def test_nested_structure(self):
        dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        result = _serialize_datetime({"items": [{"when": dt}]})
        assert result["items"][0]["when"].startswith("2026-03-01")


# ---------------------------------------------------------------------------
# _derive_document_id
# ---------------------------------------------------------------------------


class TestDeriveDocumentId:
    def test_deterministic(self):
        a = _derive_document_id("http://a", "text")
        b = _derive_document_id("http://a", "text")
        assert a == b

    def test_url_affects_id(self):
        a = _derive_document_id("http://a", "text")
        b = _derive_document_id("http://b", "text")
        assert a != b

    def test_text_affects_id(self):
        a = _derive_document_id("http://a", "one")
        b = _derive_document_id("http://a", "two")
        assert a != b

    def test_returns_hex_sha256(self):
        out = _derive_document_id("http://a", "text")
        assert len(out) == 64
        assert all(c in "0123456789abcdef" for c in out)

    def test_truncates_text_to_4096_chars(self):
        short = "x" * 4096
        long = "x" * 4096 + "different-suffix-ignored"
        assert _derive_document_id("http://a", short) == _derive_document_id("http://a", long)


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_excludes_content_sha256_field(self):
        a = _content_hash({"title": "x", "content_sha256": "AAA"})
        b = _content_hash({"title": "x", "content_sha256": "BBB"})
        assert a == b

    def test_stable_across_dict_order(self):
        a = _content_hash({"a": 1, "b": 2})
        b = _content_hash({"b": 2, "a": 1})
        assert a == b

    def test_different_titles_hash_differently(self):
        a = _content_hash({"title": "x"})
        b = _content_hash({"title": "y"})
        assert a != b

    def test_serializes_datetime_values(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = _content_hash({"retrieved_at": dt, "title": "t"})
        assert len(out) == 64

    def test_hex_sha256_format(self):
        out = _content_hash({"x": 1})
        assert len(out) == 64
        assert all(c in "0123456789abcdef" for c in out)


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_none_returns_none(self):
        assert _parse_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_datetime("") is None

    def test_tz_aware_datetime_passthrough(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _parse_datetime(dt) == dt

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2026, 1, 1)
        out = _parse_datetime(dt)
        assert out.tzinfo is timezone.utc

    def test_iso_string_parsed(self):
        out = _parse_datetime("2026-01-02T03:04:05+00:00")
        assert out.year == 2026 and out.month == 1 and out.day == 2
        assert out.tzinfo is not None

    def test_iso_string_naive_gets_utc(self):
        out = _parse_datetime("2026-01-02T03:04:05")
        assert out.tzinfo is timezone.utc

    def test_garbage_string_returns_none(self):
        assert _parse_datetime("not a date") is None

    def test_invalid_type_returns_none(self):
        # isoparse(str(int)) raises → returns None via except
        assert _parse_datetime([1, 2, 3]) is None


# ---------------------------------------------------------------------------
# _extract_text_from_payload
# ---------------------------------------------------------------------------


class TestExtractTextFromPayload:
    def test_body_wins(self):
        assert _extract_text_from_payload({"body": "B", "text": "T"}) == "B"

    def test_text_second(self):
        assert _extract_text_from_payload({"text": "T", "content": "C"}) == "T"

    def test_content_third(self):
        assert _extract_text_from_payload({"content": "C", "abstract": "A"}) == "C"

    def test_abstract_last(self):
        assert _extract_text_from_payload({"abstract": "A"}) == "A"

    def test_strips_whitespace(self):
        assert _extract_text_from_payload({"body": "  hi  "}) == "hi"

    def test_non_string_skipped(self):
        assert _extract_text_from_payload({"body": 42, "text": "T"}) == "T"

    def test_empty_string_skipped(self):
        assert _extract_text_from_payload({"body": "", "text": "T"}) == "T"

    def test_whitespace_only_skipped(self):
        assert _extract_text_from_payload({"body": "   ", "text": "T"}) == "T"

    def test_no_candidates_returns_empty(self):
        assert _extract_text_from_payload({"other": "x"}) == ""


# ---------------------------------------------------------------------------
# _extract_text — format dispatch
# ---------------------------------------------------------------------------


def _stub_meta():
    return TextExtractionMetadata(engine="stub", confidence_mean=0.5, confidence_std=0.1)


def _stub_position():
    return [PositionMapEntry(page=1, char_start=0, char_end=5, source_start=0, source_end=5)]


class TestExtractText:
    def test_payload_text_short_circuits(self):
        text, meta, pmap = _extract_text(
            raw_payload={"body": "hello world"},
            raw_bytes=b"<html>ignored</html>",
            content_type="text/html",
        )
        assert text == "hello world"
        assert meta.engine == "payload"
        assert meta.confidence_mean == 1.0
        assert pmap[0].char_start == 0
        assert pmap[0].char_end == len(text)

    def test_html_by_content_type(self, monkeypatch):
        called = {}
        def _html(b):
            called["html"] = b
            return ("HTML", _stub_meta(), _stub_position())

        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_html", _html)
        text, meta, pmap = _extract_text(None, b"<html/>", "text/html")
        assert text == "HTML"
        assert called["html"] == b"<html/>"

    def test_xml_by_content_type(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_xml", lambda b: ("XML", _stub_meta(), _stub_position()))
        # HTML token absent → xml branch
        text, _, _ = _extract_text(None, b"<x/>", "application/xml")
        assert text == "XML"

    def test_xml_not_html(self, monkeypatch):
        """xml-in-html path falls to html (xml branch requires NOT html)."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_html", lambda b: ("HTML", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"<x/>", "application/xhtml+xml")
        assert text == "HTML"

    def test_csv_by_content_type(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_csv", lambda b: ("CSV", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"a,b,c", "text/csv")
        assert text == "CSV"

    def test_csv_by_comma_separated(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_csv", lambda b: ("CSV", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"a,b", "text/comma-separated-values")
        assert text == "CSV"

    def test_excel_by_detected_format(self, monkeypatch):
        """detect_format returns 'excel' → excel branch."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "excel")
        monkeypatch.setattr(fe, "extract_from_excel", lambda b: ("XLSX", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"PK...", None)
        assert text == "XLSX"

    def test_excel_by_ct_substring(self, monkeypatch):
        """content_type contains 'excel' → excel branch (unique, no xml conflict)."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "extract_from_excel", lambda b: ("XLSX", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"PK", "application/excel-legacy")
        assert text == "XLSX"

    def test_docx_by_detected_format(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "docx")
        monkeypatch.setattr(fe, "extract_from_docx", lambda b: ("DOCX", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"PK...", None)
        assert text == "DOCX"

    def test_docx_by_msword_ct(self, monkeypatch):
        """application/msword → docx branch."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "extract_from_docx", lambda b: ("DOCX", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"...", "application/msword")
        assert text == "DOCX"

    def test_edi_by_content_type(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "extract_from_edi", lambda b: ("EDI", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"ISA*00...", "application/edi-x12")
        assert text == "EDI"

    def test_edi_by_is_edi_detection(self, monkeypatch):
        """No matching content-type but is_edi_content() returns True."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "is_edi_content", lambda b: True)
        monkeypatch.setattr(fe, "extract_from_edi", lambda b: ("EDI", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"ISA*00*", None)
        assert text == "EDI"

    def test_pdf_by_content_type(self, monkeypatch):
        """PDF branch delegates to _extract_from_pdf (patched out)."""
        monkeypatch.setattr(
            norm,
            "_extract_from_pdf",
            lambda b: ("PDF", _stub_meta(), _stub_position()),
        )
        text, _, _ = _extract_text(None, b"%PDF-1.4", "application/pdf")
        assert text == "PDF"

    def test_fallback_bytes_utf8(self, monkeypatch):
        """Unknown format with non-empty bytes → utf-8 decode fallback."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "is_edi_content", lambda b: False)
        text, meta, pmap = _extract_text(None, b"hello bytes", "application/octet-stream")
        assert text == "hello bytes"
        assert meta.engine == "bytes"
        assert pmap[0].source_end == len(b"hello bytes")

    def test_fallback_empty_bytes(self, monkeypatch):
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "is_edi_content", lambda b: False)
        text, meta, pmap = _extract_text(None, b"", None)
        assert text == ""
        assert meta.engine == "unknown"
        assert meta.confidence_mean == 0.0
        assert meta.confidence_std == 1.0
        assert pmap == []

    def test_detected_format_html(self, monkeypatch):
        """detect_format returns 'html' even when content_type doesn't say html."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "html")
        monkeypatch.setattr(fe, "extract_from_html", lambda b: ("H!", _stub_meta(), _stub_position()))
        text, _, _ = _extract_text(None, b"<x/>", "application/octet-stream")
        assert text == "H!"

    def test_empty_payload_dict_falls_through_to_format(self, monkeypatch):
        """raw_payload = {} is falsy for the first branch."""
        import app.format_extractors as fe
        monkeypatch.setattr(fe, "detect_format", lambda ct, b: "unknown")
        monkeypatch.setattr(fe, "is_edi_content", lambda b: False)
        text, meta, _ = _extract_text({}, b"bytes-go-here", None)
        assert text == "bytes-go-here"
        assert meta.engine == "bytes"


# ---------------------------------------------------------------------------
# _extract_from_pdf — pdfminer success + empty-text fallback
# ---------------------------------------------------------------------------


class TestExtractFromPdf:
    def test_pdfminer_text_returned(self, monkeypatch):
        """pdfminer.high_level.extract_text returns non-empty → pdfminer meta."""
        fake_module = SimpleNamespace(extract_text=lambda stream: "extracted text")
        import sys
        monkeypatch.setitem(sys.modules, "pdfminer.high_level", fake_module)
        text, meta, pmap = _extract_from_pdf(b"%PDF-1.4\nxxx")
        assert text == "extracted text"
        assert meta.engine == "pdfminer"
        assert meta.confidence_mean == 0.9
        assert pmap[0].char_end == len(text)

    def test_pdfminer_empty_tesseract_success(self, monkeypatch):
        """pdfminer returns empty → tesseract happy path with realistic stub."""
        import sys
        fake_pdfminer = SimpleNamespace(extract_text=lambda stream: "")
        monkeypatch.setitem(sys.modules, "pdfminer.high_level", fake_pdfminer)

        # Stub pytesseract with Output.DICT + image_to_data
        fake_tess = SimpleNamespace(
            Output=SimpleNamespace(DICT="DICT"),
            image_to_data=lambda image, output_type: {
                "text": ["hello", " ", "world"],
                "conf": ["95", "0", "99"],
            },
        )
        monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)

        fake_pdf2image = SimpleNamespace(
            convert_from_bytes=lambda raw: ["image1-stub"]
        )
        monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

        text, meta, pmap = _extract_from_pdf(b"%PDF-1.4")
        assert "hello" in text and "world" in text
        assert meta.engine == "tesseract"
        assert meta.confidence_mean > 0
        assert len(pmap) == 1
        assert pmap[0].page == 1

    def test_tesseract_multi_page_with_non_numeric_conf(self, monkeypatch):
        """Multiple pages, one word has non-numeric conf → conf=0 fallback."""
        import sys
        fake_pdfminer = SimpleNamespace(extract_text=lambda stream: "")
        monkeypatch.setitem(sys.modules, "pdfminer.high_level", fake_pdfminer)

        pages = ["img-1", "img-2"]
        page_data = [
            {"text": ["page1"], "conf": ["-1"]},  # -1 conf ignored (not appended)
            {"text": ["page2", "word"], "conf": ["abc", "80"]},  # abc → 0.0
        ]
        call_idx = {"i": 0}
        def _image_to_data(image, output_type):
            i = call_idx["i"]
            call_idx["i"] += 1
            return page_data[i]

        fake_tess = SimpleNamespace(
            Output=SimpleNamespace(DICT="DICT"),
            image_to_data=_image_to_data,
        )
        monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
        monkeypatch.setitem(
            sys.modules,
            "pdf2image",
            SimpleNamespace(convert_from_bytes=lambda raw: pages),
        )

        text, meta, pmap = _extract_from_pdf(b"%PDF")
        assert "page1" in text
        assert "page2" in text
        assert meta.engine == "tesseract"
        assert len(pmap) == 2
        # All empty-string / zero confidences → still some numbers
        assert meta.confidence_mean >= 0

    def test_tesseract_empty_word_list(self, monkeypatch):
        """Empty text list + no confidences → mean 0.5, variance 0.25 defaults."""
        import sys
        fake_pdfminer = SimpleNamespace(extract_text=lambda stream: "")
        monkeypatch.setitem(sys.modules, "pdfminer.high_level", fake_pdfminer)

        fake_tess = SimpleNamespace(
            Output=SimpleNamespace(DICT="DICT"),
            image_to_data=lambda image, output_type: {"text": ["   "], "conf": ["95"]},
        )
        monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
        monkeypatch.setitem(
            sys.modules,
            "pdf2image",
            SimpleNamespace(convert_from_bytes=lambda raw: ["img"]),
        )

        text, meta, pmap = _extract_from_pdf(b"%PDF")
        assert text == ""
        assert meta.engine == "tesseract"
        assert meta.confidence_mean == 0.5  # fallback when confidences empty
        assert meta.confidence_std == 0.5  # sqrt(0.25)


# ---------------------------------------------------------------------------
# normalize_document — integration
# ---------------------------------------------------------------------------


class TestNormalizeDocument:
    def test_happy_path_with_payload_text(self):
        payload = {
            "title": "Rule Title",
            "jurisdiction": "US-FDA",
            "publication_date": "2026-01-15T00:00:00+00:00",
            "source_system": "federal_register",
            "body": "Full regulation text here.",
        }
        normalized, doc_id, sha = normalize_document(
            raw_payload=payload,
            raw_bytes=b"",
            source_url="https://example.gov/rule",
            content_type=None,
        )
        assert normalized["title"] == "Rule Title"
        assert normalized["jurisdiction"] == "US-FDA"
        assert normalized["source_system"] == "federal_register"
        assert normalized["text"] == "Full regulation text here."
        assert normalized["document_id"] == doc_id
        assert normalized["content_sha256"] == sha
        assert normalized["retrieved_at"].tzinfo is not None

    def test_none_payload_uses_empty_dict(self):
        normalized, _, _ = normalize_document(
            raw_payload=None,
            raw_bytes=b"",
            source_url="https://x",
            content_type=None,
        )
        assert normalized["title"] is None
        assert normalized["jurisdiction"] is None
        assert normalized["source_system"] == "unknown"

    def test_headline_fallback_for_title(self):
        normalized, _, _ = normalize_document(
            raw_payload={"headline": "Alt Title", "body": "text"},
            raw_bytes=b"",
            source_url="http://x",
            content_type=None,
        )
        assert normalized["title"] == "Alt Title"

    def test_agency_fallback_for_jurisdiction(self):
        normalized, _, _ = normalize_document(
            raw_payload={"agency": "FDA", "body": "text"},
            raw_bytes=b"",
            source_url="http://x",
            content_type=None,
        )
        assert normalized["jurisdiction"] == "FDA"

    def test_explicit_document_id_preserved(self):
        normalized, doc_id, _ = normalize_document(
            raw_payload={"document_id": "custom-id-1", "body": "text"},
            raw_bytes=b"",
            source_url="http://x",
            content_type=None,
        )
        assert doc_id == "custom-id-1"
        assert normalized["document_id"] == "custom-id-1"

    def test_missing_publication_date_uses_now_utc(self):
        before = datetime.now(timezone.utc)
        normalized, _, _ = normalize_document(
            raw_payload={"body": "text"},
            raw_bytes=b"",
            source_url="http://x",
            content_type=None,
        )
        after = datetime.now(timezone.utc)
        assert before <= normalized["retrieved_at"] <= after

    def test_content_sha256_is_deterministic(self):
        payload = {"body": "same", "title": "t", "publication_date": "2026-01-01T00:00:00+00:00"}
        _, _, sha_a = normalize_document(payload, b"", "http://x", None)
        _, _, sha_b = normalize_document(payload, b"", "http://x", None)
        assert sha_a == sha_b

    def test_content_sha256_hex_length(self):
        _, _, sha = normalize_document({"body": "t"}, b"", "http://x", None)
        assert len(sha) == 64

    def test_content_type_propagated(self):
        normalized, _, _ = normalize_document(
            {"body": "t"}, b"", "http://x", "text/plain"
        )
        assert normalized["content_type"] == "text/plain"
