"""Coverage for app/fda_export/formatters.py — CSV/PDF/ZIP response builders.

All heavy lifting lives in app.fda_export_service helpers
(_generate_csv, _generate_pdf, _build_fda_package, ...). This module is a
thin orchestrator: it concatenates hashes, builds HTTP headers with PII
redaction flags (issue #1219), and wraps byte payloads in a
``StreamingResponse``. Coverage is achieved by monkeypatching the
service-level helpers so tests stay deterministic.

Locks:
- generate_csv_and_hash / generate_csv_v2_and_hash: SHA-256 matches the
  generated content; include_pii forwarded to the generator.
- build_compliance_headers: emits X-KDE-Coverage + X-KDE-Warnings, adds
  X-Compliance-Warning only when coverage < 0.80 (strict), merges ``extra``
  headers on top.
- build_csv_response: headers, X-PII-Redacted "true" when include_pii=False
  and "false" when True, chain VERIFIED/UNVERIFIED toggle, extra merge.
- build_pdf_response: delegates to _generate_pdf with include_pii, same
  header surface.
- build_package_response: forwards include_pii to chain + package builders,
  chain_payload_extras merged before packaging, X-Package-Hash from meta,
  record_count from len(events).
- make_timestamp: 15-char YYYYMMDD_HHMMSS shape.
- Re-exports: completeness_summary / safe_filename_token aliases.

Issue: #1342
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from app.fda_export import formatters as fmt
from app.fda_export_service import (
    _build_completeness_summary,
    _safe_filename_token,
)


# ---------------------------------------------------------------------------
# generate_csv_and_hash
# ---------------------------------------------------------------------------


class TestGenerateCsvAndHash:

    def test_hash_matches_content(self, monkeypatch):
        monkeypatch.setattr(
            fmt, "_generate_csv",
            lambda evs, include_pii=False: "a,b\n1,2\n",
        )
        content, h = fmt.generate_csv_and_hash([{"x": 1}])
        assert content == "a,b\n1,2\n"
        assert h == hashlib.sha256(b"a,b\n1,2\n").hexdigest()

    def test_hash_uses_utf8_encoding(self, monkeypatch):
        unicode_csv = "héllo,wörld\n"
        monkeypatch.setattr(
            fmt, "_generate_csv",
            lambda evs, include_pii=False: unicode_csv,
        )
        _, h = fmt.generate_csv_and_hash([])
        assert h == hashlib.sha256(unicode_csv.encode("utf-8")).hexdigest()

    def test_include_pii_forwarded(self, monkeypatch):
        captured = {}

        def _fake(events, include_pii=False):
            captured["include_pii"] = include_pii
            captured["events"] = events
            return "x"

        monkeypatch.setattr(fmt, "_generate_csv", _fake)
        fmt.generate_csv_and_hash([{"k": "v"}], include_pii=True)
        assert captured["include_pii"] is True
        assert captured["events"] == [{"k": "v"}]

    def test_default_include_pii_false(self, monkeypatch):
        captured = {}

        def _fake(events, include_pii=False):
            captured["include_pii"] = include_pii
            return ""

        monkeypatch.setattr(fmt, "_generate_csv", _fake)
        fmt.generate_csv_and_hash([])
        assert captured["include_pii"] is False


# ---------------------------------------------------------------------------
# generate_csv_v2_and_hash
# ---------------------------------------------------------------------------


class TestGenerateCsvV2AndHash:

    def test_hash_matches_v2_content(self, monkeypatch):
        monkeypatch.setattr(
            fmt, "_generate_csv_v2",
            lambda evs, include_pii=False: "csv-v2",
        )
        content, h = fmt.generate_csv_v2_and_hash([])
        assert content == "csv-v2"
        assert h == hashlib.sha256(b"csv-v2").hexdigest()

    def test_v2_is_separate_from_v1(self, monkeypatch):
        monkeypatch.setattr(fmt, "_generate_csv", lambda evs, include_pii=False: "v1")
        monkeypatch.setattr(fmt, "_generate_csv_v2", lambda evs, include_pii=False: "v2")
        content, _ = fmt.generate_csv_v2_and_hash([])
        assert content == "v2"

    def test_include_pii_forwarded(self, monkeypatch):
        captured = {}

        def _fake(events, include_pii=False):
            captured["include_pii"] = include_pii
            return "x"

        monkeypatch.setattr(fmt, "_generate_csv_v2", _fake)
        fmt.generate_csv_v2_and_hash([], include_pii=True)
        assert captured["include_pii"] is True


# ---------------------------------------------------------------------------
# build_compliance_headers
# ---------------------------------------------------------------------------


class TestBuildComplianceHeaders:

    def test_base_headers_emitted(self):
        summary = {
            "required_kde_coverage_ratio": 0.95,
            "events_with_missing_required_fields": 2,
        }
        h = fmt.build_compliance_headers(summary)
        assert h["X-KDE-Coverage"] == "0.95"
        assert h["X-KDE-Warnings"] == "2"

    def test_warning_absent_at_exact_threshold(self):
        """0.80 is NOT below the 0.80 threshold — no warning emitted."""
        summary = {
            "required_kde_coverage_ratio": 0.80,
            "events_with_missing_required_fields": 0,
        }
        h = fmt.build_compliance_headers(summary)
        assert "X-Compliance-Warning" not in h

    def test_warning_present_below_threshold(self):
        summary = {
            "required_kde_coverage_ratio": 0.79,
            "events_with_missing_required_fields": 99,
        }
        h = fmt.build_compliance_headers(summary)
        assert h["X-Compliance-Warning"] == "KDE coverage below 80% threshold"

    def test_extra_headers_merged(self):
        summary = {
            "required_kde_coverage_ratio": 1.0,
            "events_with_missing_required_fields": 0,
        }
        h = fmt.build_compliance_headers(summary, extra={"X-Custom": "yes"})
        assert h["X-Custom"] == "yes"
        assert h["X-KDE-Coverage"] == "1.0"

    def test_extra_overrides_base(self):
        """Keys present in ``extra`` take precedence (dict.update semantics)."""
        summary = {
            "required_kde_coverage_ratio": 1.0,
            "events_with_missing_required_fields": 0,
        }
        h = fmt.build_compliance_headers(summary, extra={"X-KDE-Coverage": "override"})
        assert h["X-KDE-Coverage"] == "override"


# ---------------------------------------------------------------------------
# build_csv_response
# ---------------------------------------------------------------------------


class TestBuildCsvResponse:

    def test_headers_pii_redacted_default(self):
        """Default include_pii=False → X-PII-Redacted: true."""
        resp = fmt.build_csv_response(
            csv_content="a,b\n1,2\n",
            filename="export.csv",
            export_hash="abc123",
            record_count=1,
            chain_valid=True,
        )
        assert resp.media_type == "text/csv"
        assert resp.headers["content-disposition"] == "attachment; filename=export.csv"
        assert resp.headers["x-export-hash"] == "abc123"
        assert resp.headers["x-record-count"] == "1"
        assert resp.headers["x-chain-integrity"] == "VERIFIED"
        assert resp.headers["x-pii-redacted"] == "true"

    def test_include_pii_flips_redacted_header(self):
        resp = fmt.build_csv_response(
            csv_content="x", filename="f.csv", export_hash="h",
            record_count=0, chain_valid=True, include_pii=True,
        )
        assert resp.headers["x-pii-redacted"] == "false"

    def test_unverified_when_chain_invalid(self):
        resp = fmt.build_csv_response(
            csv_content="x", filename="f.csv", export_hash="h",
            record_count=0, chain_valid=False,
        )
        assert resp.headers["x-chain-integrity"] == "UNVERIFIED"

    def test_extra_headers_merged(self):
        resp = fmt.build_csv_response(
            csv_content="x", filename="f.csv", export_hash="h",
            record_count=0, chain_valid=True,
            extra_headers={"X-Extra": "yes"},
        )
        assert resp.headers["x-extra"] == "yes"


# ---------------------------------------------------------------------------
# build_pdf_response
# ---------------------------------------------------------------------------


class TestBuildPdfResponse:

    def test_delegates_to_pdf_generator_with_all_kwargs(self, monkeypatch):
        captured = {}

        def _fake(events, metadata, include_pii=False):
            captured["events"] = events
            captured["metadata"] = metadata
            captured["include_pii"] = include_pii
            return b"%PDF-FAKE"

        monkeypatch.setattr(fmt, "_generate_pdf", _fake)
        resp = fmt.build_pdf_response(
            events=[{"a": 1}],
            metadata={"tenant_id": "t1"},
            filename="x.pdf",
            export_hash="hash-xyz",
            record_count=1,
            chain_valid=True,
        )
        assert captured["events"] == [{"a": 1}]
        assert captured["metadata"] == {"tenant_id": "t1"}
        assert captured["include_pii"] is False
        assert resp.media_type == "application/pdf"
        assert resp.headers["content-disposition"] == "attachment; filename=x.pdf"
        assert resp.headers["x-export-hash"] == "hash-xyz"
        assert resp.headers["x-chain-integrity"] == "VERIFIED"
        assert resp.headers["x-pii-redacted"] == "true"

    def test_include_pii_true(self, monkeypatch):
        captured = {}

        def _fake(events, metadata, include_pii=False):
            captured["include_pii"] = include_pii
            return b"%PDF"

        monkeypatch.setattr(fmt, "_generate_pdf", _fake)
        resp = fmt.build_pdf_response(
            events=[], metadata={}, filename="f.pdf",
            export_hash="h", record_count=0, chain_valid=True,
            include_pii=True,
        )
        assert captured["include_pii"] is True
        assert resp.headers["x-pii-redacted"] == "false"

    def test_unverified_chain(self, monkeypatch):
        monkeypatch.setattr(
            fmt, "_generate_pdf",
            lambda events, metadata, include_pii=False: b"x",
        )
        resp = fmt.build_pdf_response(
            events=[], metadata={}, filename="f.pdf",
            export_hash="h", record_count=0, chain_valid=False,
        )
        assert resp.headers["x-chain-integrity"] == "UNVERIFIED"

    def test_extra_headers_merged(self, monkeypatch):
        monkeypatch.setattr(
            fmt, "_generate_pdf",
            lambda events, metadata, include_pii=False: b"x",
        )
        resp = fmt.build_pdf_response(
            events=[], metadata={}, filename="f.pdf",
            export_hash="h", record_count=0, chain_valid=True,
            extra_headers={"X-Extra": "yep"},
        )
        assert resp.headers["x-extra"] == "yep"


# ---------------------------------------------------------------------------
# build_package_response
# ---------------------------------------------------------------------------


def _patch_package_deps(monkeypatch, *, package_hash="pkg-hash"):
    """Install fakes for chain payload + fda package builders. Returns a
    dict that captures the kwargs on each call."""
    captured = {}

    def _fake_chain(**kwargs):
        captured["chain_kwargs"] = kwargs
        return {"seed": "payload"}

    def _fake_package(**kwargs):
        captured["package_kwargs"] = kwargs
        return b"zipped-bytes", {"package_hash": package_hash}

    monkeypatch.setattr(fmt, "_build_chain_verification_payload", _fake_chain)
    monkeypatch.setattr(fmt, "_build_fda_package", _fake_package)
    return captured


class TestBuildPackageResponse:

    def test_happy_path_headers_and_kwargs(self, monkeypatch):
        captured = _patch_package_deps(monkeypatch)
        chain_verification = SimpleNamespace(valid=True)
        resp = fmt.build_package_response(
            events=[{"a": 1}],
            csv_content="csv-blob",
            export_hash="hash-a",
            chain_verification=chain_verification,
            completeness_summary={"required_kde_coverage_ratio": 1.0},
            tenant_id="tenant",
            tlc="TLC-1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            filename="pkg.zip",
        )
        assert resp.media_type == "application/zip"
        assert resp.headers["x-export-hash"] == "hash-a"
        assert resp.headers["x-package-hash"] == "pkg-hash"
        assert resp.headers["x-record-count"] == "1"
        assert resp.headers["x-chain-integrity"] == "VERIFIED"
        assert resp.headers["x-pii-redacted"] == "true"
        assert resp.headers["content-disposition"] == "attachment; filename=pkg.zip"
        # Chain and package helpers received include_pii=False
        assert captured["chain_kwargs"]["include_pii"] is False
        assert captured["package_kwargs"]["include_pii"] is False
        # Query date kwargs forwarded through rename
        assert captured["package_kwargs"]["query_start_date"] == "2026-01-01"
        assert captured["package_kwargs"]["query_end_date"] == "2026-01-31"
        # Without extras, chain_payload goes through unchanged
        assert captured["package_kwargs"]["chain_payload"] == {"seed": "payload"}

    def test_chain_payload_extras_merged(self, monkeypatch):
        captured = _patch_package_deps(monkeypatch)
        fmt.build_package_response(
            events=[],
            csv_content="csv",
            export_hash="h",
            chain_verification=SimpleNamespace(valid=True),
            completeness_summary={"required_kde_coverage_ratio": 1.0},
            tenant_id="t",
            tlc=None,
            start_date=None,
            end_date=None,
            filename="f.zip",
            chain_payload_extras={"extra_key": "extra_val"},
        )
        merged = captured["package_kwargs"]["chain_payload"]
        assert merged == {"seed": "payload", "extra_key": "extra_val"}

    def test_include_pii_forwarded(self, monkeypatch):
        captured = _patch_package_deps(monkeypatch)
        resp = fmt.build_package_response(
            events=[],
            csv_content="csv",
            export_hash="h",
            chain_verification=SimpleNamespace(valid=True),
            completeness_summary={"required_kde_coverage_ratio": 1.0},
            tenant_id="t",
            tlc=None,
            start_date=None,
            end_date=None,
            filename="f.zip",
            include_pii=True,
        )
        assert captured["chain_kwargs"]["include_pii"] is True
        assert captured["package_kwargs"]["include_pii"] is True
        assert resp.headers["x-pii-redacted"] == "false"

    def test_extra_headers_merged(self, monkeypatch):
        _patch_package_deps(monkeypatch)
        resp = fmt.build_package_response(
            events=[],
            csv_content="csv",
            export_hash="h",
            chain_verification=SimpleNamespace(valid=True),
            completeness_summary={"required_kde_coverage_ratio": 1.0},
            tenant_id="t",
            tlc=None,
            start_date=None,
            end_date=None,
            filename="f.zip",
            extra_headers={"X-Extra": "v"},
        )
        assert resp.headers["x-extra"] == "v"

    def test_unverified_when_chain_invalid(self, monkeypatch):
        _patch_package_deps(monkeypatch)
        resp = fmt.build_package_response(
            events=[{"x": 1}, {"x": 2}],
            csv_content="csv",
            export_hash="h",
            chain_verification=SimpleNamespace(valid=False),
            completeness_summary={"required_kde_coverage_ratio": 1.0},
            tenant_id="t",
            tlc="TLC",
            start_date=None,
            end_date=None,
            filename="f.zip",
        )
        assert resp.headers["x-chain-integrity"] == "UNVERIFIED"
        assert resp.headers["x-record-count"] == "2"


# ---------------------------------------------------------------------------
# make_timestamp
# ---------------------------------------------------------------------------


class TestMakeTimestamp:

    def test_format_shape(self):
        ts = fmt.make_timestamp()
        # YYYYMMDD_HHMMSS — 15 chars, underscore at index 8
        assert len(ts) == 15
        assert ts[8] == "_"
        assert ts[:8].isdigit()
        assert ts[9:].isdigit()


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


class TestReExports:

    def test_completeness_summary_alias(self):
        assert fmt.completeness_summary is _build_completeness_summary

    def test_safe_filename_token_alias(self):
        assert fmt.safe_filename_token is _safe_filename_token
