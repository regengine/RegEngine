"""Seed scripts must default to localhost, refuse prod without a flag, and never downgrade TLS."""

from __future__ import annotations

import contextlib
import http.server
import importlib.util
import os
import ssl
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
PROD_URL = "https://regengine-production.up.railway.app"
# A second, unrelated non-local URL so the refusal tests cannot pass by
# special-casing only the Railway host.
OTHER_NON_LOCAL_URL = "https://example.com"
REFUSED_URLS = [PROD_URL, OTHER_NON_LOCAL_URL]
# Plain-http variants: these must be refused even WITH --allow-production.
HTTP_NON_LOCAL_URLS = ["http://example.com", "http://regengine-production.up.railway.app"]
# Local http targets stay allowed for local dev.
HTTP_LOCAL_URLS = ["http://localhost:8002", "http://127.0.0.1:8002"]

MODULES = ["seed_demo_ctes", "seed_founder_demo_ctes"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _source(name: str) -> str:
    return (SCRIPTS / f"{name}.py").read_text()


@pytest.mark.parametrize("module_name", MODULES)
def test_default_target_is_localhost(module_name, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    assert mod.is_local_target(mod.resolve_base())
    assert "localhost" in mod.resolve_base()


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", REFUSED_URLS)
def test_production_url_without_flag_is_refused(module_name, url, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base(url)


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", REFUSED_URLS)
def test_production_url_via_env_without_flag_is_refused(module_name, url, monkeypatch):
    mod = _load(module_name)
    monkeypatch.setenv("SEED_BASE_URL", url)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base()


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", REFUSED_URLS)
def test_explicit_production_url_with_flag_is_allowed(module_name, url, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    assert mod.resolve_base(url, allow_production=True) == url


@pytest.mark.parametrize("module_name", MODULES)
def test_no_tls_downgrade_path(module_name):
    src = _source(module_name)
    assert "CERT_NONE" not in src
    assert "verify=False" not in src
    assert "verify_mode" not in src
    assert "check_hostname = False" not in src
    assert "check_hostname=False" not in src
    assert "_create_unverified_context" not in src
    assert "_ssl_ctx" not in src


@pytest.mark.parametrize("module_name", MODULES)
def test_ssl_context_verifies(module_name):
    mod = _load(module_name)
    ctx = mod.create_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_demo_script_key_comes_from_env_only(monkeypatch):
    mod = _load("seed_demo_ctes")
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    assert mod.get_api_key() == "secret-from-env"
    monkeypatch.delenv("REGENGINE_TENANT_API_KEY", raising=False)
    with pytest.raises(mod.UnsafeTargetError):
        mod.get_api_key()


def test_demo_script_rejects_key_as_cli_arg():
    mod = _load("seed_demo_ctes")
    parser = mod.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["http://localhost:8002", "some-api-key"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--api-key", "some-api-key"])


def test_founder_main_refuses_prod_without_flag(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    rc = mod.main(["--base", PROD_URL, "--dry-run"])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out


def test_demo_main_refuses_prod_without_flag(monkeypatch, capsys):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    rc = mod.main([PROD_URL])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out


def _wrapped_cert_error():
    """Mirror urllib: urlopen surfaces cert failures as URLError(reason=...)."""
    return urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed: self-signed certificate"))


def _install_urlopen_failure(monkeypatch, mod, exc, seen):
    def fake_urlopen(req, *args, **kwargs):
        seen["context"] = kwargs.get("context")
        raise exc

    monkeypatch.setattr(mod, "urlopen_no_redirect", fake_urlopen)


def _assert_verifying_context(seen):
    ctx = seen.get("context")
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_demo_main_wrapped_cert_error_aborts_with_1(monkeypatch, capsys):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    seen = {}
    _install_urlopen_failure(monkeypatch, mod, _wrapped_cert_error(), seen)
    rc = mod.main([])
    assert rc == 1
    assert "tls" in capsys.readouterr().out.lower()
    _assert_verifying_context(seen)


def test_demo_main_direct_cert_error_aborts_with_1(monkeypatch, capsys):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    seen = {}
    _install_urlopen_failure(
        monkeypatch,
        mod,
        ssl.SSLCertVerificationError("certificate verify failed"),
        seen,
    )
    rc = mod.main([])
    assert rc == 1
    assert "tls" in capsys.readouterr().out.lower()
    _assert_verifying_context(seen)


def test_demo_main_non_cert_urlerror_still_propagates(monkeypatch):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    _install_urlopen_failure(monkeypatch, mod, urllib.error.URLError(ConnectionRefusedError("refused")), {})
    with pytest.raises(urllib.error.URLError):
        mod.main([])


def test_founder_main_wrapped_cert_error_aborts_with_1(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "hmac-secret")
    seen = {}
    _install_urlopen_failure(monkeypatch, mod, _wrapped_cert_error(), seen)
    rc = mod.main([])
    assert rc == 1
    assert "tls" in capsys.readouterr().out.lower()
    _assert_verifying_context(seen)


def test_founder_status_wrapped_cert_error_unsuccessful(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    seen = {}
    _install_urlopen_failure(monkeypatch, mod, _wrapped_cert_error(), seen)
    rc = mod.main(["--status"])
    assert rc == 1
    assert "tls" in capsys.readouterr().out.lower()
    _assert_verifying_context(seen)


def test_founder_check_wrapped_cert_error_unsuccessful(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    seen = {}
    _install_urlopen_failure(monkeypatch, mod, _wrapped_cert_error(), seen)
    rc = mod.main(["--check"])
    assert rc == 1
    assert "tls" in capsys.readouterr().out.lower()
    _assert_verifying_context(seen)


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", HTTP_NON_LOCAL_URLS)
def test_http_non_local_refused_even_with_flag(module_name, url, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base(url, allow_production=True)


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", HTTP_NON_LOCAL_URLS)
def test_http_non_local_via_env_refused_even_with_flag(module_name, url, monkeypatch):
    mod = _load(module_name)
    monkeypatch.setenv("SEED_BASE_URL", url)
    with pytest.raises(mod.UnsafeTargetError):
        mod.resolve_base(allow_production=True)


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("url", HTTP_LOCAL_URLS)
@pytest.mark.parametrize("flag", [True, False])
def test_http_local_targets_stay_allowed(module_name, url, flag, monkeypatch):
    mod = _load(module_name)
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    assert mod.resolve_base(url, allow_production=flag) == url


def test_demo_main_refuses_http_with_flag(monkeypatch, capsys):
    mod = _load("seed_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    rc = mod.main(["http://example.com", "--allow-production"])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out


def test_founder_main_refuses_http_with_flag(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    rc = mod.main(["--base", "http://example.com", "--allow-production", "--dry-run"])
    assert rc == 2
    assert "Refusing" in capsys.readouterr().out


@contextlib.contextmanager
def _redirect_pair():
    """Yield (base_url, hits_a, hits_b) using loopback servers only.

    Server A answers every request with a 302 redirect to server B.
    Server B records every request it receives. Proxy env vars are
    cleared so loopback traffic is never sent to a proxy.
    """
    hits_a = []
    hits_b = []

    def _record(store, handler):
        length = int(handler.headers.get("Content-Length", 0) or 0)
        if length:
            handler.rfile.read(length)
        store.append((handler.command, {k.lower(): v for k, v in handler.headers.items()}))

    class _HandlerB(http.server.BaseHTTPRequestHandler):
        def _serve(self):
            _record(hits_b, self)
            body = b'{"accepted": 1, "rejected": 0, "events": []}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _serve
        do_POST = _serve

        def log_message(self, *args):
            pass

    class _HandlerA(http.server.BaseHTTPRequestHandler):
        def _serve(self):
            _record(hits_a, self)
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{port_b}/ingest")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = _serve
        do_POST = _serve

        def log_message(self, *args):
            pass

    saved_proxies = {}
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        saved_proxies[var] = os.environ.pop(var, None)
    server_b = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HandlerB)
    port_b = server_b.server_address[1]
    thread_b = threading.Thread(target=server_b.serve_forever, daemon=True)
    thread_b.start()
    server_a = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HandlerA)
    try:
        thread_a = threading.Thread(target=server_a.serve_forever, daemon=True)
        thread_a.start()
        try:
            yield f"http://127.0.0.1:{server_a.server_address[1]}", hits_a, hits_b
        finally:
            server_a.shutdown()
            thread_a.join(timeout=5)
    finally:
        server_b.shutdown()
        thread_b.join(timeout=5)
        for var, value in saved_proxies.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value


@pytest.mark.parametrize("module_name", MODULES)
def test_redirect_handler_refuses(module_name):
    mod = _load(module_name)
    handler = mod._NoFollowRedirect()
    req = urllib.request.Request(
        "http://127.0.0.1:8002/api/v1/webhooks/ingest",
        headers={"X-RegEngine-API-Key": "secret-key"},
    )
    with pytest.raises(mod.RedirectRefusedError, match="redirect"):
        handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/x")


def test_demo_post_events_refuses_redirect_without_forwarding_key(capsys):
    mod = _load("seed_demo_ctes")
    with _redirect_pair() as (base, hits_a, hits_b):
        rc = mod.post_events(base, "secret-key", None)
    assert rc == 1
    assert "redirect" in capsys.readouterr().out.lower()
    assert hits_a, "redirecting server should have received the request"
    assert dict(hits_a[0][1]).get("x-regengine-api-key") == "secret-key"
    assert hits_b == [], "redirect target must receive nothing"


def test_founder_post_batch_refuses_redirect_without_forwarding_headers():
    mod = _load("seed_founder_demo_ctes")
    with _redirect_pair() as (base, hits_a, hits_b):
        with pytest.raises(mod.RedirectRefusedError, match="redirect"):
            mod.post_batch(base, "secret-key", "tenant-1", "src", [{"a": 1}], "idem-1", "hmac-secret", None)
    assert hits_a, "redirecting server should have received the request"
    sent = dict(hits_a[0][1])
    assert sent.get("x-regengine-api-key") == "secret-key"
    assert sent.get("x-tenant-id") == "tenant-1"
    assert sent.get("x-webhook-signature", "").startswith("sha256=")
    assert hits_b == [], "redirect target must receive nothing"


def test_founder_status_refuses_redirect_without_forwarding_key(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-key")
    with _redirect_pair() as (base, hits_a, hits_b):
        rc = mod.status(base, "tenant-1")
    assert rc == 1
    assert "redirect" in capsys.readouterr().out.lower()
    assert hits_a, "redirecting server should have received the request"
    assert hits_b == [], "redirect target must receive nothing"


def test_founder_check_refuses_redirect(capsys):
    mod = _load("seed_founder_demo_ctes")
    with _redirect_pair() as (base, hits_a, hits_b):
        rc = mod.check_health(base)
    assert rc == 1
    assert "redirect" in capsys.readouterr().out.lower()
    assert hits_a, "redirecting server should have received the request"
    assert hits_b == [], "redirect target must receive nothing"
