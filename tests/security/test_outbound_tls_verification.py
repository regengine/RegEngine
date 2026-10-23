"""Outbound TLS verification contract.

Pins that the two outbound HTTPS paths verify server certificates and
hostnames, and that a loopback server with an untrusted self-signed
certificate is refused:

* ``services/shared/safe_http.py`` — SSRF-safe httpx clients/transports.
* ``scripts/security/staging_release_gate.py`` — urllib staging gate transport.

No network beyond 127.0.0.1, no database, no stored records. The self-signed
certificate is generated per test in ``tmp_path``.
"""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import ipaddress
import re
import socket
import ssl
import sys
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPSHandler, Request

import httpx
import pytest
from shared import safe_http

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAFE_HTTP_SOURCE = _REPO_ROOT / "services" / "shared" / "safe_http.py"
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "security" / "staging_release_gate.py"


def _load_gate():
    # Reuse the module if test_staging_release_gate_runner already loaded it,
    # so both test files share one GateError class.
    existing = sys.modules.get("staging_release_gate")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("staging_release_gate", _GATE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_GATE = _load_gate()


def _assert_verifying(ctx: object) -> None:
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


# ---------------------------------------------------------------------------
# (1) safe_http
# ---------------------------------------------------------------------------


def test_safe_http_build_ssl_context_requires_cert_and_hostname():
    _assert_verifying(safe_http._build_ssl_context())


def test_safe_http_source_never_disables_verification():
    source = _SAFE_HTTP_SOURCE.read_text(encoding="utf-8")
    forbidden = [
        r"verify\s*=\s*False",
        r"CERT_NONE",
        r"check_hostname\s*=\s*False",
        r"_create_unverified_context",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, source), f"safe_http.py matches forbidden pattern {pattern!r}"


class _TransportCaptured(Exception):
    pass


def _recording_transport(base: type, captured: list, *, stop: bool) -> type:
    class _Recording(base):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs):
            captured.append(kwargs.get("verify"))
            if stop:
                raise _TransportCaptured
            super().__init__(**kwargs)

    return _Recording


def _pin_public(monkeypatch) -> None:
    # Skip DNS: the transports are never used to connect in these tests.
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))


def test_safe_http_sync_get_transport_receives_verifying_context(monkeypatch):
    _pin_public(monkeypatch)
    captured: list = []
    monkeypatch.setattr(
        safe_http,
        "_IPPinnedSyncTransport",
        _recording_transport(safe_http._IPPinnedSyncTransport, captured, stop=True),
    )
    with pytest.raises(_TransportCaptured):
        safe_http.safe_httpx_get_sync("https://example.com/", validator=lambda u: u)
    assert len(captured) == 1
    _assert_verifying(captured[0])


def test_safe_http_sync_post_transport_receives_verifying_context(monkeypatch):
    _pin_public(monkeypatch)
    captured: list = []
    monkeypatch.setattr(
        safe_http,
        "_IPPinnedSyncTransport",
        _recording_transport(safe_http._IPPinnedSyncTransport, captured, stop=True),
    )
    with pytest.raises(_TransportCaptured):
        safe_http.safe_httpx_post_sync("https://example.com/", json={}, validator=lambda u: u)
    assert len(captured) == 1
    _assert_verifying(captured[0])


def test_safe_http_async_client_transport_receives_verifying_context(monkeypatch):
    _pin_public(monkeypatch)
    captured: list = []
    monkeypatch.setattr(
        safe_http,
        "_IPPinnedAsyncTransport",
        _recording_transport(safe_http._IPPinnedAsyncTransport, captured, stop=False),
    )
    client = safe_http.safe_httpx_client(url="https://example.com/")
    assert isinstance(client, httpx.AsyncClient)
    assert len(captured) == 1
    _assert_verifying(captured[0])


# ---------------------------------------------------------------------------
# (2) staging_release_gate._urllib_transport
# ---------------------------------------------------------------------------


def test_gate_urllib_transport_uses_verifying_https_handler(monkeypatch):
    captured_handlers: list = []

    class _FakeOpener:
        def open(self, request, timeout):  # noqa: ANN001, ANN201
            raise URLError("stop before network")

    def _fake_build_opener(*handlers):
        captured_handlers.extend(handlers)
        return _FakeOpener()

    monkeypatch.setattr(_GATE, "build_opener", _fake_build_opener)
    with pytest.raises(_GATE.GateError):
        _GATE._urllib_transport("GET", "https://staging.example.invalid/health", {}, None, 1.0)

    https_handlers = [h for h in captured_handlers if isinstance(h, HTTPSHandler)]
    assert len(https_handlers) == 1
    _assert_verifying(https_handlers[0]._context)
    assert any(isinstance(h, _GATE._NoRedirect) for h in captured_handlers)


def test_gate_no_redirect_refuses_https_to_http_downgrade():
    request = Request("https://staging.example.invalid/api", method="GET")
    result = _GATE._NoRedirect().redirect_request(request, None, 302, "Found", {}, "http://staging.example.invalid/api")
    assert result is None


# ---------------------------------------------------------------------------
# (3) Refusal against a loopback TLS server with an untrusted certificate
# ---------------------------------------------------------------------------


def _write_self_signed_cert(tmp_path: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        # SANs match the hostname so only the untrusted issuer causes refusal.
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@contextlib.contextmanager
def _loopback_tls_server(tmp_path: Path):
    cert_path, key_path = _write_self_signed_cert(tmp_path)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert_path, key_path)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def _serve():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except (socket.timeout, OSError):
                continue
            conn.settimeout(5)
            try:
                with server_ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except (ssl.SSLError, OSError):
                # Expected: the verifying client aborts the handshake.
                pass
            finally:
                conn.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=5)
        listener.close()


def test_safe_http_context_refuses_untrusted_loopback_cert(tmp_path):
    with _loopback_tls_server(tmp_path) as port:
        ctx = safe_http._build_ssl_context()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with pytest.raises(ssl.SSLCertVerificationError):
                ctx.wrap_socket(raw, server_hostname="localhost")


def test_safe_http_get_refuses_untrusted_loopback_cert(tmp_path, monkeypatch):
    # Pin to loopback (bypassing the SSRF public-IP check for this test only)
    # so the real transport stack performs the TLS handshake.
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("127.0.0.1", "localhost"))
    with _loopback_tls_server(tmp_path) as port:
        with pytest.raises(httpx.ConnectError) as excinfo:
            safe_http.safe_httpx_get_sync(f"https://localhost:{port}/", validator=lambda u: u, timeout=5)
    assert "CERTIFICATE_VERIFY_FAILED" in str(excinfo.value)


def test_gate_urllib_transport_refuses_untrusted_loopback_cert(tmp_path):
    with _loopback_tls_server(tmp_path) as port:
        with pytest.raises(_GATE.GateError) as excinfo:
            _GATE._urllib_transport("GET", f"https://127.0.0.1:{port}/health", {}, None, 5.0)
    cause = excinfo.value.__cause__
    assert isinstance(cause, URLError)
    assert isinstance(cause.reason, ssl.SSLCertVerificationError)
