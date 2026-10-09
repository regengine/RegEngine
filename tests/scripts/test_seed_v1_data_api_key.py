"""seed_v1_data must use the real API key only and fail when it is unset.

Regression test for the audit finding: the script used to fall back to the
test-auth bypass token as its API credential. It must read REGENGINE_API_KEY
only and refuse to run without it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("seed_v1_data", SCRIPTS / "seed_v1_data.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_no_bypass_token_fallback_in_source():
    src = (SCRIPTS / "seed_v1_data.py").read_text()
    assert "AUTH_TEST_BYPASS_TOKEN" not in src


def test_get_api_key_reads_real_key(monkeypatch):
    mod = _load()
    monkeypatch.setenv("REGENGINE_API_KEY", "real-key")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "bypass-token")
    assert mod.get_api_key() == "real-key"


def test_get_api_key_fails_when_unset_even_with_bypass_token(monkeypatch):
    mod = _load()
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "bypass-token")
    with pytest.raises(SystemExit):
        mod.get_api_key()


def test_get_api_key_fails_when_nothing_set(monkeypatch):
    mod = _load()
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        mod.get_api_key()


def test_seed_v1_refuses_without_key_and_sends_no_request(monkeypatch):
    mod = _load()
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "bypass-token")

    def _fail_post(*args, **kwargs):
        raise AssertionError("no HTTP request must be sent without a real API key")

    monkeypatch.setattr(mod.requests, "post", _fail_post)
    with pytest.raises(SystemExit):
        mod.seed_v1("test-run")


def test_seed_v1_sends_real_key_not_bypass_token(monkeypatch):
    mod = _load()
    monkeypatch.setenv("REGENGINE_API_KEY", "real-key")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", "bypass-token")
    seen = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def _fake_post(url, json=None, headers=None):
        seen["headers"] = headers
        return _Resp()

    monkeypatch.setattr(mod.requests, "post", _fake_post)
    assert mod.seed_v1("test-run") is True
    assert seen["headers"]["X-RegEngine-API-Key"] == "real-key"
