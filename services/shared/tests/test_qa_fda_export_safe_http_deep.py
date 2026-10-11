"""Deep QA for shared FDA export primitives and safe HTTP seams.

Covers date-window edge cases, filename hardening, CSV coercion, PII scope
gating, pagination boundaries, and the SSRF-safe HTTP helpers. Fast and
deterministic: DNS and transports are mocked, no network, no sleeps.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from shared import safe_http
from shared.fda_export import (
    MAX_EXPORT_WINDOW_DAYS,
    ExportWindowError,
    hash_pii_value,
    paginate,
    redact_pii_row,
    safe_cell,
    safe_filename,
    safe_filename_token,
    validate_export_window,
)
from shared.fda_export.pii import _caller_has_full_pii, redact_pii_extras
from shared.url_validation import SSRFError


class TestExportWindowEdges:
    def test_aware_datetime_crossing_midnight_normalizes_to_utc(self):
        window = validate_export_window(
            datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=2))),
            datetime(2026, 1, 5, 0, 30, tzinfo=timezone(timedelta(hours=2))),
        )
        assert (window.start, window.end) == (date(2025, 12, 31), date(2026, 1, 4))

    def test_naive_datetime_treated_as_utc(self):
        window = validate_export_window(datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 2, 12, 0))
        assert (window.start, window.end) == (date(2026, 1, 1), date(2026, 1, 2))

    def test_same_day_window_has_zero_span(self):
        window = validate_export_window("2026-04-01", "2026-04-01")
        assert window.span_days == 0
        assert window.to_iso() == ("2026-04-01", "2026-04-01")

    def test_unsupported_type_rejected(self):
        with pytest.raises(ExportWindowError, match="unsupported type"):
            validate_export_window(20260101, "2026-02-01")

    def test_max_days_override_respected(self):
        with pytest.raises(ExportWindowError, match="exceeds"):
            validate_export_window("2026-01-01", "2026-03-01", max_days=10)
        window = validate_export_window("2026-01-01", "2026-01-05", max_days=10)
        assert window.span_days == 4

    def test_default_cap_constant(self):
        assert MAX_EXPORT_WINDOW_DAYS == 90


class TestFilenames:
    def test_unicode_token_collapses_to_underscores(self):
        out = safe_filename_token("café-ü-7317")
        assert out == "caf_-_-7317"
        assert out.isascii()

    def test_timestamp_sanitized(self):
        out = safe_filename("pkg", timestamp="2026-01-01T00:00:00Z bad:header")
        assert "\r" not in out and "\n" not in out and ":" not in out

    def test_empty_extension_falls_back_to_csv(self):
        assert safe_filename("pkg", extension="") == "pkg.csv"
        assert safe_filename("pkg", extension="...") == "pkg.csv"

    def test_prefix_traversal_neutralized(self):
        out = safe_filename("../../etc/passwd")
        assert ".." not in out and "/" not in out


class TestCsvSafety:
    def test_scalar_coercion(self):
        assert safe_cell(True) == "True"
        assert safe_cell(0) == "0"
        assert safe_cell(b"ab") == "b'ab'"

    def test_leading_whitespace_before_formula_is_not_quoted(self):
        assert safe_cell(" =HACK()") == " =HACK()"

    def test_minus_prefix_quoted(self):
        assert safe_cell("-5+3+cmd") == "'-5+3+cmd"


class TestPiiScopes:
    def test_scope_matching_ignores_case_and_whitespace(self):
        assert _caller_has_full_pii(["  FDA.EXPORT.FULL_PII "]) is True
        assert _caller_has_full_pii(["fda.export.pii"]) is True
        assert _caller_has_full_pii(["fda.*"]) is True

    def test_base_export_scope_alone_still_redacts(self):
        assert _caller_has_full_pii(["fda.export"]) is False

    def test_unknown_strategy_fails_closed_to_placeholder(self):
        out = redact_pii_row({"Location Name": "Farm"}, caller_scopes=[], strategy="bogus")
        assert out["Location Name"] == "[REDACTED]"

    def test_granted_row_is_a_copy(self):
        row = {"Location Name": "Farm"}
        out = redact_pii_row(row, caller_scopes=["*"])
        out["Location Name"] = "changed"
        assert row["Location Name"] == "Farm"

    def test_extras_key_match_is_case_insensitive(self):
        out = redact_pii_extras({"ContactEmail": "a@b.c", "speed_mph": "45"}, caller_scopes=[])
        assert out == {"ContactEmail": "[REDACTED]", "speed_mph": "45"}

    def test_hash_length_parameter(self):
        assert hash_pii_value("x", length=4) == "pii_" + hash_pii_value("x")[4:8]
        assert hash_pii_value("x", length=4).startswith("pii_")

    def test_empty_scope_list_redacts(self):
        assert _caller_has_full_pii([]) is False
        assert _caller_has_full_pii([""]) is False


class TestPaginateBoundaries:
    def _collect(self, agen):
        async def runner():
            return [batch async for batch in agen]

        return asyncio.run(runner())

    def test_empty_batch_with_live_cursor_ends_iteration(self):
        async def fetcher(*, cursor, limit):
            if cursor is None:
                return ([], "cursor-live")
            return ([1], None)

        assert self._collect(paginate(fetcher, batch_size=5)) == []

    def test_exact_cap_does_not_raise(self):
        async def fetcher(*, cursor, limit):
            return ([1, 2, 3], None)

        assert self._collect(paginate(fetcher, batch_size=5, max_events=3)) == [[1, 2, 3]]


class TestPinnedSession:
    def test_closed_session_rejects_get_and_post(self):
        session = safe_http.PinnedHTTPSession()
        session.close()
        with pytest.raises(RuntimeError, match="closed"):
            session.get("https://example.com/")
        with pytest.raises(RuntimeError, match="closed"):
            session.post("https://example.com/")

    def test_get_merges_params_into_url(self, monkeypatch):
        seen = {}

        def fake_get(url, *, headers=None, timeout=None):
            seen["url"] = url
            return "sentinel"

        monkeypatch.setattr(safe_http, "safe_httpx_get_sync", fake_get)
        session = safe_http.PinnedHTTPSession(headers={"X-A": "b"})
        assert session.get("https://example.com/s", params={"q": "x y"}) == "sentinel"
        assert seen["url"] == "https://example.com/s?q=x+y"


class TestSafeHttpRedirects:
    def _redirect_response(self, location=None):
        headers = {"location": location} if location else {}
        return httpx.Response(302, headers=headers, request=httpx.Request("GET", "https://example.com/"))

    def test_get_sync_refuses_endless_redirects(self, monkeypatch):
        monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "x"))
        monkeypatch.setattr(safe_http, "_build_ssl_context", lambda: None)

        class LoopingClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, url):
                return httpx.Response(
                    302,
                    headers={"location": "https://example.com/next"},
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(safe_http.httpx, "Client", LoopingClient)
        with pytest.raises(SSRFError, match="Too many redirects"):
            safe_http.safe_httpx_get_sync(
                "https://example.com/",
                validator=lambda u: u,
                max_redirects=2,
            )

    async def test_async_redirect_without_location_raises(self, monkeypatch):
        class FakeClient:
            async def get(self, url):
                return httpx.Response(302, request=httpx.Request("GET", "https://example.com/"))

            async def aclose(self):
                pass

        def fake_factory(**kwargs):
            return FakeClient()

        monkeypatch.setattr(safe_http, "safe_httpx_client", fake_factory)
        with pytest.raises(SSRFError, match="without Location"):
            await safe_http.follow_redirects_safely("https://example.com/", validator=lambda u: u)

    def test_async_ipv6_transport_brackets_literal(self, monkeypatch):
        observed = {}

        async def fake_handle(_transport, request):
            observed["url"] = str(request.url)
            observed["host"] = request.headers["Host"]
            observed["sni"] = request.extensions["sni_hostname"]
            return httpx.Response(200, request=request)

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)
        transport = safe_http._IPPinnedAsyncTransport(pinned_ip="2606:4700:4700::1111", original_host="example.com")

        async def run():
            try:
                return await transport.handle_async_request(httpx.Request("GET", "https://example.com/document"))
            finally:
                await transport.aclose()

        assert asyncio.run(run()).status_code == 200
        assert observed == {
            "url": "https://[2606:4700:4700::1111]/document",
            "host": "example.com",
            "sni": "example.com",
        }


class TestSafeFetchContent:
    def test_http_error_propagates_unwrapped(self, monkeypatch):
        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("GET", "https://example.com/"),
            response=httpx.Response(500, request=httpx.Request("GET", "https://example.com/")),
        )
        monkeypatch.setattr(safe_http, "validate_url", lambda u: u)
        monkeypatch.setattr(safe_http, "safe_httpx_get_sync", lambda *a, **kw: fake_response)
        with pytest.raises(httpx.HTTPStatusError):
            safe_http.safe_fetch_content("https://example.com/")
