"""demo_freshness must use request timeouts, log polling errors, and require credentials."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo_freshness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("demo_freshness", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "ok"

    def json(self):
        return self._payload


def test_ingest_uses_request_timeout(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, **kwargs):
        seen.update(kwargs)
        return _FakeResponse({})

    monkeypatch.setattr(_MODULE.requests, "post", fake_post)
    assert _MODULE.ingest_content("body", "V1") is True
    assert seen.get("timeout") == _MODULE.REQUEST_TIMEOUT


def _install_fake_clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(_MODULE.time, "time", lambda: now["t"])

    def fake_sleep(s):
        now["t"] += s

    monkeypatch.setattr(_MODULE.time, "sleep", fake_sleep)


def test_polling_uses_request_timeout(monkeypatch):
    _install_fake_clock(monkeypatch)
    seen = {}

    def fake_get(url, headers=None, **kwargs):
        seen.update(kwargs)
        return _FakeResponse([{"original_file_path": "other"}])

    monkeypatch.setattr(_MODULE.requests, "get", fake_get)
    assert _MODULE.wait_for_doc(1) is None
    assert seen.get("timeout") == _MODULE.REQUEST_TIMEOUT


def test_polling_logs_exception_type(monkeypatch, capsys):
    _install_fake_clock(monkeypatch)

    def fake_get(url, headers=None, **kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(_MODULE.requests, "get", fake_get)
    assert _MODULE.wait_for_doc(1) is None
    assert "ConnectionError" in capsys.readouterr().out


def test_missing_credentials_exit_up_front(monkeypatch, capsys):
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        _MODULE.require_credentials()
    assert exc_info.value.code != 0
    assert "REGENGINE_API_KEY" in capsys.readouterr().out


def test_blank_credentials_exit_up_front(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "   ")
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        _MODULE.require_credentials()


def test_main_refuses_to_run_without_credentials(monkeypatch):
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        _MODULE.main()


def test_credentials_from_env_are_accepted(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "secret-from-env")
    assert _MODULE.require_credentials() == "secret-from-env"
