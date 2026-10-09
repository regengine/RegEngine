"""Safe-fetch tests for the Federal Register source adapter.

The per-document ``full_text_xml_url`` / ``html_url`` values come from the
API response, so they are untrusted input. The adapter must validate them
(SSRF check) and cap the response body instead of fetching with a raw
client. Each test below fails on the old code (raw ``session.get`` of the
API-supplied URL) and passes on the fixed code.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_service_dir = Path(__file__).resolve().parent.parent
if str(_service_dir) not in sys.path:
    sys.path.insert(0, str(_service_dir))
_services_dir = _service_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from regengine_ingestion.sources.federal_register import FederalRegisterAdapter  # noqa: E402
from shared.safe_http import ResponseTooLargeError  # noqa: E402

EVIL_URL = "http://169.254.169.254/latest/meta-data/"


def _search_response(docs):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": docs}
    return resp


def _doc(url=EVIL_URL):
    return {
        "document_number": "2024-00001",
        "title": "Test document",
        "full_text_xml_url": url,
        "publication_date": "2024-01-01",
        "agencies": [],
        "type": "Rule",
    }


def _run_with_session_get(adapter, first_response, extra_calls):
    """Patch session.get: first call returns search results, later raw calls fail."""
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return first_response
        return extra_calls(url)

    with patch.object(adapter.session, "get", side_effect=fake_get):
        items = list(adapter.fetch_documents(vertical="food_safety"))
    return items, calls


def test_private_url_from_api_is_skipped_without_raw_fetch():
    """A link-local URL supplied by the API must never hit the raw client."""
    adapter = FederalRegisterAdapter()

    def no_raw_fetch(url):
        raise AssertionError(f"raw client used for API-supplied URL: {url}")

    items, calls = _run_with_session_get(adapter, _search_response([_doc()]), no_raw_fetch)
    assert items == []
    assert calls == [f"{FederalRegisterAdapter.BASE_URL}/documents.json"]


def test_oversized_document_is_skipped():
    """A response over the byte cap is skipped instead of buffered."""
    adapter = FederalRegisterAdapter()
    with (
        patch.object(
            adapter.session,
            "get",
            return_value=_search_response([_doc(url="https://www.federalregister.gov/documents/1.xml")]),
        ),
        patch(
            "regengine_ingestion.sources.federal_register.safe_httpx_get_sync",
            side_effect=ResponseTooLargeError("Response body exceeds 5242880 bytes"),
        ) as mock_safe_get,
    ):
        items = list(adapter.fetch_documents(vertical="food_safety"))
    assert items == []
    mock_safe_get.assert_called_once()


def test_valid_document_still_fetched_via_safe_client():
    """A normal document flows through the validated, capped fetcher."""
    import httpx

    adapter = FederalRegisterAdapter()
    safe_resp = httpx.Response(
        200,
        content=b"<document/>",
        headers={"ETag": '"v1"'},
        request=httpx.Request("GET", "https://www.federalregister.gov/x.xml"),
    )
    with (
        patch.object(
            adapter.session, "get", return_value=_search_response([_doc(url="https://www.federalregister.gov/x.xml")])
        ),
        patch(
            "regengine_ingestion.sources.federal_register.safe_httpx_get_sync",
            return_value=safe_resp,
        ) as mock_safe_get,
    ):
        items = list(adapter.fetch_documents(vertical="food_safety"))
    assert len(items) == 1
    content, source_meta, doc_meta = items[0]
    assert content == b"<document/>"
    assert doc_meta["document_number"] == "2024-00001"
    assert mock_safe_get.call_count == 1
    _, kwargs = mock_safe_get.call_args
    assert kwargs["headers"] == {"User-Agent": adapter.user_agent}
    assert kwargs["max_bytes"] > 0
