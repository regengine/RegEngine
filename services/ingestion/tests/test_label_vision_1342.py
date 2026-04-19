"""Coverage for app/label_vision.py — food label vision analysis endpoint.

Locks:
- 400 when content_type missing or not image/*.
- 400 when file bytes are empty.
- 413 when file bytes exceed 10 MB.
- Fallback (analysis_engine='unavailable') when OPENAI_API_KEY is unset.
- 502 when the vision model returns empty content.
- 502 when the vision model returns unparseable JSON (JSONDecodeError).
- 502 when AsyncOpenAI import/usage raises any of the caught exception
  types (ImportError / AttributeError / TypeError / ValueError /
  KeyError / OSError / IOError).
- Happy path: model JSON forwarded into LabelVisionResponse; fsma_kdes
  auto-built from parsed fields when the model omits them; explicit
  fsma_kdes preserved when present.
- Content-type defaults to image/jpeg when the UploadFile still has a
  valid image/* type (always set by 'image/' guard); data-URI contains
  base64-encoded bytes.

Issue: #1342
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from app import label_vision as lv


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class _FakeUpload:
    """Minimal UploadFile-like object."""

    def __init__(self, *, content_type: str | None, content: bytes):
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _choice(content):
    """Builds a response object shaped like openai chat.completions result."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class _FakeCompletions:
    def __init__(self, *, response=None, raises: Exception | None = None):
        self._response = response
        self._raises = raises
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return self._response


class _FakeAsyncOpenAI:
    """Captures the init kwargs and exposes a configurable completions stub."""

    _last_instance: "_FakeAsyncOpenAI | None" = None

    def __init__(self, *, api_key: str, completions: _FakeCompletions | None = None):
        self.api_key = api_key
        self._completions = completions or _FakeCompletions()
        self.chat = SimpleNamespace(completions=self._completions)
        _FakeAsyncOpenAI._last_instance = self


def _install_openai(monkeypatch, *, response=None, raises: Exception | None = None):
    """Install a stub ``openai`` module exposing ``AsyncOpenAI``.

    The factory captures the ctor kwargs and hands back a client whose
    chat.completions.create is governed by ``response`` / ``raises``.
    """
    captured: dict = {}

    def _factory(*, api_key: str):
        captured["api_key"] = api_key
        completions = _FakeCompletions(response=response, raises=raises)
        client = _FakeAsyncOpenAI(api_key=api_key, completions=completions)
        captured["client"] = client
        return client

    fake_mod = ModuleType("openai")
    fake_mod.AsyncOpenAI = _factory
    monkeypatch.setitem(sys.modules, "openai", fake_mod)
    return captured


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(lv, "logger", _Silent())


@pytest.fixture
def set_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:

    def test_missing_content_type_rejected(self):
        up = _FakeUpload(content_type=None, content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 400
        assert "image" in exc_info.value.detail.lower()

    def test_non_image_content_type_rejected(self):
        up = _FakeUpload(content_type="application/pdf", content=b"%PDF")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 400

    def test_empty_body_rejected(self):
        up = _FakeUpload(content_type="image/jpeg", content=b"")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()

    def test_oversized_body_rejected(self):
        up = _FakeUpload(
            content_type="image/png",
            content=b"\x00" * (10 * 1024 * 1024 + 1),
        )
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 413
        assert "10 MB" in exc_info.value.detail

    def test_exactly_at_limit_accepted(self, set_api_key, monkeypatch):
        """10 MB exactly (not > 10MB) should NOT be rejected."""
        _install_openai(
            monkeypatch,
            response=_choice(json.dumps({"fsma_compatible": True, "product_name": "p"})),
        )
        up = _FakeUpload(content_type="image/jpeg", content=b"\x00" * (10 * 1024 * 1024))
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert out.product_name == "p"


# ---------------------------------------------------------------------------
# OPENAI_API_KEY fallback
# ---------------------------------------------------------------------------


class TestUnavailableFallback:

    def test_missing_api_key_returns_unavailable(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        up = _FakeUpload(content_type="image/jpeg", content=b"\x01\x02")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert out.analysis_engine == "unavailable"
        assert "OPENAI_API_KEY" in (out.raw_text or "")

    def test_empty_api_key_returns_unavailable(self, monkeypatch):
        """Empty env var should be treated as unset by the handler."""
        monkeypatch.setenv("OPENAI_API_KEY", "")
        up = _FakeUpload(content_type="image/jpeg", content=b"\x01\x02")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert out.analysis_engine == "unavailable"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:

    def test_model_response_maps_into_response_model(self, set_api_key, monkeypatch):
        parsed = {
            "product_name": "Organic Apples",
            "brand": "Fresh Farms",
            "gtin": "01234567890128",
            "lot_code": "LOT-XYZ",
            "serial_number": "SN-1",
            "expiry_date": "2026-12-31",
            "pack_date": "2026-01-15",
            "net_weight": "500",
            "unit_of_measure": "g",
            "facility_name": "Facility A",
            "facility_address": "1 Main St",
            "country_of_origin": "USA",
            "ingredients": "Apples",
            "allergens": ["nuts"],
            "certifications": ["USDA Organic"],
            "fsma_kdes": [
                {"field": "gtin", "value": "01234567890128", "confidence": 0.95},
            ],
            "fsma_compatible": True,
            "raw_text": "all text",
        }
        captured = _install_openai(monkeypatch, response=_choice(json.dumps(parsed)))

        up = _FakeUpload(content_type="image/jpeg", content=b"IMG")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))

        assert out.product_name == "Organic Apples"
        assert out.brand == "Fresh Farms"
        assert out.gtin == "01234567890128"
        assert out.lot_code == "LOT-XYZ"
        assert out.serial_number == "SN-1"
        assert out.expiry_date == "2026-12-31"
        assert out.pack_date == "2026-01-15"
        assert out.net_weight == "500"
        assert out.unit_of_measure == "g"
        assert out.facility_name == "Facility A"
        assert out.facility_address == "1 Main St"
        assert out.country_of_origin == "USA"
        assert out.ingredients == "Apples"
        assert out.allergens == ["nuts"]
        assert out.certifications == ["USDA Organic"]
        assert len(out.fsma_kdes) == 1
        assert out.fsma_kdes[0].field == "gtin"
        assert out.fsma_kdes[0].value == "01234567890128"
        assert out.fsma_kdes[0].confidence == 0.95
        assert out.fsma_compatible is True
        assert out.raw_text == "all text"
        assert out.analysis_engine == "gpt-4o-vision"

        # API key from env threaded into the AsyncOpenAI constructor
        assert captured["api_key"] == "sk-test"

    def test_client_payload_includes_data_uri_and_prompt(self, set_api_key, monkeypatch):
        captured = _install_openai(
            monkeypatch,
            response=_choice(json.dumps({"fsma_compatible": False})),
        )
        up = _FakeUpload(content_type="image/png", content=b"PNGBYTES")
        asyncio.run(lv.analyze_label(file=up, api_key="k"))

        kwargs = captured["client"].chat.completions.last_kwargs
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["max_tokens"] == 2000

        content_parts = kwargs["messages"][0]["content"]
        # text prompt + image_url block
        assert content_parts[0]["type"] == "text"
        assert "FSMA 204" in content_parts[0]["text"]
        assert content_parts[1]["type"] == "image_url"
        expected_b64 = base64.b64encode(b"PNGBYTES").decode("utf-8")
        assert content_parts[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"

    def test_auto_build_kde_list_when_model_omits_it(self, set_api_key, monkeypatch):
        """When parsed has no fsma_kdes, handler auto-builds from scalar fields."""
        parsed = {
            "gtin": "GTIN-1",
            "lot_code": "LOT-1",
            "serial_number": None,  # excluded (falsy)
            "expiry_date": "2026-12-31",
            "pack_date": None,
            "product_name": "Apples",
            "net_weight": "",  # excluded (falsy)
            "country_of_origin": "US",
            "fsma_compatible": True,
            # no fsma_kdes key
        }
        _install_openai(monkeypatch, response=_choice(json.dumps(parsed)))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))

        fields_present = {kde.field for kde in out.fsma_kdes}
        assert "gtin" in fields_present
        assert "lot_code" in fields_present
        assert "expiry_date" in fields_present
        assert "product_name" in fields_present
        assert "country_of_origin" in fields_present
        # Falsy fields (None, "") are filtered out
        assert "serial_number" not in fields_present
        assert "pack_date" not in fields_present
        assert "net_weight" not in fields_present
        # Default confidence 0.9 is stamped
        for kde in out.fsma_kdes:
            assert kde.confidence == 0.9

    def test_auto_build_kde_list_when_empty_list_provided(self, set_api_key, monkeypatch):
        """fsma_kdes=[] triggers the auto-build branch (truthy check `if not fsma_kdes`)."""
        parsed = {"gtin": "X", "fsma_kdes": []}
        _install_openai(monkeypatch, response=_choice(json.dumps(parsed)))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert [k.field for k in out.fsma_kdes] == ["gtin"]

    def test_defaults_when_parsed_fields_missing(self, set_api_key, monkeypatch):
        """Unknown keys → LabelVisionResponse defaults (None / [] / False)."""
        _install_openai(monkeypatch, response=_choice(json.dumps({})))
        up = _FakeUpload(content_type="image/webp", content=b"x")
        out = asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert out.product_name is None
        assert out.allergens == []
        assert out.certifications == []
        assert out.fsma_compatible is False
        assert out.fsma_kdes == []


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestFailureModes:

    def test_empty_model_content_raises_502(self, set_api_key, monkeypatch):
        _install_openai(monkeypatch, response=_choice(None))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 502
        assert "Empty response" in exc_info.value.detail

    def test_empty_string_model_content_raises_502(self, set_api_key, monkeypatch):
        """Content == '' is also treated as empty (falsy check)."""
        _install_openai(monkeypatch, response=_choice(""))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 502

    def test_unparseable_json_raises_502(self, set_api_key, monkeypatch):
        _install_openai(monkeypatch, response=_choice("not-json-at-all"))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 502
        assert "unparseable" in exc_info.value.detail

    @pytest.mark.parametrize("exc", [
        AttributeError("no attr"),
        TypeError("bad type"),
        ValueError("bad value"),
        KeyError("missing key"),
        OSError("socket"),
        IOError("io"),
    ])
    def test_client_exceptions_become_502(self, set_api_key, monkeypatch, exc):
        _install_openai(monkeypatch, raises=exc)
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 502
        assert "Vision analysis failed" in exc_info.value.detail

    def test_import_error_becomes_502(self, set_api_key, monkeypatch):
        """If ``from openai import AsyncOpenAI`` itself fails, handler → 502."""
        # Install an ``openai`` module that raises ImportError on attribute access.
        fake_mod = ModuleType("openai")

        def _bad():
            raise ImportError("openai not installed")

        class _M:
            def __getattr__(self, name):
                if name == "AsyncOpenAI":
                    raise ImportError("openai missing")
                raise AttributeError(name)

        monkeypatch.setitem(sys.modules, "openai", _M())
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=up, api_key="k"))
        assert exc_info.value.status_code == 502

    def test_uncaught_exception_propagates(self, set_api_key, monkeypatch):
        """RuntimeError is NOT in the catch tuple → it bubbles out."""
        _install_openai(monkeypatch, raises=RuntimeError("boom"))
        up = _FakeUpload(content_type="image/jpeg", content=b"x")
        with pytest.raises(RuntimeError):
            asyncio.run(lv.analyze_label(file=up, api_key="k"))


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TestResponseModels:

    def test_extracted_kde_confidence_bounds(self):
        """ExtractedKDE.confidence is clamped to [0,1] by pydantic."""
        lv.ExtractedKDE(field="x", value="y", confidence=0.5)
        with pytest.raises(Exception):
            lv.ExtractedKDE(field="x", confidence=1.5)
        with pytest.raises(Exception):
            lv.ExtractedKDE(field="x", confidence=-0.1)

    def test_label_vision_response_defaults(self):
        r = lv.LabelVisionResponse()
        assert r.product_name is None
        assert r.allergens == []
        assert r.certifications == []
        assert r.fsma_kdes == []
        assert r.fsma_compatible is False
        assert r.analysis_engine == "gpt-4o-vision"
