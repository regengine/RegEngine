"""Regression tests for the SSRF guard in scripts/ingest_document.py.

The defect: DocumentIngestion._download_file fetched any operator-supplied
URL with requests.get, including private addresses (localhost, RFC 1918
ranges, cloud metadata endpoints). The fix validates the initial URL and
every redirect target with validate_download_url before requesting, and
follows redirects manually so each hop is checked.

The script is loaded by file path because ``scripts/`` is not a package
(no __init__.py) and ``services/ingestion/scripts/`` (a real package)
shadows the name under pytest.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# scripts/ingest_document.py imports services.nlp extractors at module load;
# stub them so these hermetic tests do not need the NLP dependency tree.
# The stubs live only for the duration of the load below and are then
# removed, so other tests in the same pytest process are unaffected.
_STUB_NAMES = ("services", "services.nlp", "services.nlp.app", "services.nlp.app.extractors")


class _StubExtractor:
    pass


def _load_ingest():
    saved = {name: sys.modules.get(name) for name in _STUB_NAMES}
    try:
        for name in _STUB_NAMES:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod
        extractors = sys.modules["services.nlp.app.extractors"]
        extractors.DORAExtractor = _StubExtractor
        extractors.NYDFSExtractor = _StubExtractor
        extractors.SECSCIExtractor = _StubExtractor

        name = "test_support_ingest_document"
        spec = importlib.util.spec_from_file_location(
            name, REPO_ROOT / "scripts" / "ingest_document.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_ingest = _load_ingest()
DocumentIngestion = _ingest.DocumentIngestion
validate_download_url = _ingest.validate_download_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/doc.pdf",
        "http://10.0.0.5/doc.pdf",
        "http://192.168.1.10/doc.pdf",
        "http://172.16.0.1/doc.pdf",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/doc.pdf",
        "http://[::1]/doc.pdf",
        "ftp://8.8.8.8/doc.pdf",
        "file:///etc/passwd",
        "http://user:pass@8.8.8.8/doc.pdf",
        "http:///no-host",
    ],
)
def test_validate_download_url_blocks_private_or_unsafe(url):
    with pytest.raises(ValueError):
        validate_download_url(url)


def test_validate_download_url_allows_public_literal_ip():
    # Literal IP: no DNS lookup, fully hermetic.
    parsed = validate_download_url("http://8.8.8.8/doc.pdf")
    assert parsed.hostname == "8.8.8.8"


def test_download_file_never_requests_private_address(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("requests.get must not be called for private URLs")

    monkeypatch.setattr(_ingest, "requests", types.SimpleNamespace(get=_boom))
    ingestion = DocumentIngestion()
    with pytest.raises(ValueError):
        ingestion._download_file("http://127.0.0.1/doc.pdf")
    with pytest.raises(ValueError):
        ingestion._download_file("http://169.254.169.254/latest/meta-data/")


class _FakeResponse:
    def __init__(self, *, redirect_to=None, content=b"pdf-bytes"):
        self.redirect_to = redirect_to
        self.content = content
        self.headers = {"location": redirect_to} if redirect_to else {}

    @property
    def is_redirect(self):
        return self.redirect_to is not None

    def raise_for_status(self):
        pass


def test_download_file_refuses_redirect_to_private_address(monkeypatch):
    calls = []

    def _fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs.get("allow_redirects") is False
        return _FakeResponse(redirect_to="http://127.0.0.1/evil.pdf")

    monkeypatch.setattr(_ingest, "requests", types.SimpleNamespace(get=_fake_get))
    with pytest.raises(ValueError):
        DocumentIngestion()._download_file("http://8.8.8.8/start.pdf")
    assert calls == ["http://8.8.8.8/start.pdf"]


def test_download_file_follows_redirect_to_public_address(monkeypatch):
    def _fake_get(url, **kwargs):
        if url == "http://8.8.8.8/start.pdf":
            return _FakeResponse(redirect_to="http://8.8.8.8/final.pdf")
        assert url == "http://8.8.8.8/final.pdf"
        return _FakeResponse(content=b"final-bytes")

    monkeypatch.setattr(_ingest, "requests", types.SimpleNamespace(get=_fake_get))
    assert DocumentIngestion()._download_file("http://8.8.8.8/start.pdf") == b"final-bytes"
