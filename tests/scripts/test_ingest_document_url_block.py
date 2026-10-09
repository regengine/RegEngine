"""Ingest script must refuse to fetch non-public URLs.

scripts/ingest_document.py downloads an operator-supplied URL. Without a
guard, that URL can point at loopback, private, or link-local addresses
(such as cloud metadata endpoints). These tests pin the private-address
block, including redirects that hop to a non-public target.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ingest_document.py"

HOST_IPS = {
    "example.com": ["93.184.216.34"],
    "localhost": ["127.0.0.1"],
}


def _load_ingest_module():
    for name in ("services", "services.nlp", "services.nlp.app"):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules.setdefault(name, module)
    stub = types.ModuleType("services.nlp.app.extractors")
    for extractor in ("DORAExtractor", "NYDFSExtractor", "SECSCIExtractor"):
        setattr(stub, extractor, type(extractor, (), {}))
    sys.modules["services.nlp.app.extractors"] = stub

    spec = importlib.util.spec_from_file_location("_ingest_document_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_module = _load_ingest_module()


class _FakeResponse:
    def __init__(self, content=b"data", location=None):
        self.content = content
        self.headers = {"location": location} if location else {}
        self.is_redirect = location is not None

    def raise_for_status(self):
        return None


@pytest.fixture()
def ingestion():
    return _module.DocumentIngestion()


@pytest.fixture()
def fake_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        try:
            address = str(_module.ipaddress.ip_address(host))
            ips = [address]
        except ValueError:
            if host in HOST_IPS:
                ips = HOST_IPS[host]
            else:
                raise socket.gaierror(f"Name or service not known: {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return fake_getaddrinfo


@pytest.fixture()
def no_fetch(monkeypatch):
    def fail(url, **kwargs):
        raise AssertionError(f"must not fetch {url}")

    monkeypatch.setattr(_module.requests, "get", fail)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/doc.pdf",
        "http://10.1.2.3/doc.pdf",
        "http://172.16.0.5/doc.pdf",
        "http://192.168.1.10/doc.pdf",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/doc.pdf",
        "http://[::1]/doc.pdf",
    ],
)
def test_download_refuses_non_public_hosts(ingestion, fake_dns, no_fetch, url):
    with pytest.raises(ValueError, match="non-public"):
        ingestion._download_file(url)


def test_download_refuses_non_http_scheme(ingestion, fake_dns, no_fetch):
    with pytest.raises(ValueError, match="only http and https"):
        ingestion._download_file("ftp://example.com/doc.pdf")


def test_download_refuses_unresolvable_host(ingestion, fake_dns, no_fetch):
    with pytest.raises(ValueError, match="unresolvable"):
        ingestion._download_file("http://does-not-exist.invalid/doc.pdf")


def test_download_refuses_redirect_to_private_host(ingestion, fake_dns, monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == "http://example.com/doc.pdf":
            return _FakeResponse(location="http://169.254.169.254/latest/meta-data/")
        raise AssertionError(f"must not fetch {url}")

    monkeypatch.setattr(_module.requests, "get", fake_get)
    with pytest.raises(ValueError, match="non-public"):
        ingestion._download_file("http://example.com/doc.pdf")
    assert calls == ["http://example.com/doc.pdf"]


def test_download_refuses_redirect_loop(ingestion, fake_dns, monkeypatch):
    def fake_get(url, **kwargs):
        return _FakeResponse(location="http://example.com/other.pdf")

    monkeypatch.setattr(_module.requests, "get", fake_get)
    with pytest.raises(ValueError, match="redirect"):
        ingestion._download_file("http://example.com/doc.pdf")


def test_download_succeeds_for_public_host(ingestion, fake_dns, monkeypatch, capsys):
    def fake_get(url, **kwargs):
        assert kwargs.get("allow_redirects") is False
        assert url == "http://example.com/doc.pdf"
        return _FakeResponse(content=b"pdf-bytes")

    monkeypatch.setattr(_module.requests, "get", fake_get)
    assert ingestion._download_file("http://example.com/doc.pdf") == b"pdf-bytes"
    capsys.readouterr()
