"""Regression tests for the phase3b freshness test credential handling.

The freshness test must read its API key from the REGENGINE_TEST_API_KEY
environment variable (matching the sibling phase3a test) and skip when it
is unset, instead of using a hard-coded credential.
"""

import importlib
from pathlib import Path

import pytest

import tests.data_integrity.test_fsma_204_freshness_phase3b as phase3b

MODULE_PATH = Path(__file__).with_name("test_fsma_204_freshness_phase3b.py")


def _reload_without_key(monkeypatch):
    monkeypatch.delenv("REGENGINE_TEST_API_KEY", raising=False)
    return importlib.reload(phase3b)


def _reload_with_key(monkeypatch, value="secret-xyz"):
    monkeypatch.setenv("REGENGINE_TEST_API_KEY", value)
    return importlib.reload(phase3b)


def test_no_hardcoded_admin_credential():
    source = MODULE_PATH.read_text()
    assert 'API_KEY = "admin"' not in source
    assert "API_KEY = 'admin'" not in source


def test_api_key_has_no_fallback_default():
    source = MODULE_PATH.read_text()
    assert 'os.getenv("REGENGINE_TEST_API_KEY")' in source
    assert 'os.getenv("REGENGINE_TEST_API_KEY",' not in source
    assert 'os.environ.get("REGENGINE_TEST_API_KEY",' not in source


def test_auth_headers_skip_when_env_unset(monkeypatch):
    module = _reload_without_key(monkeypatch)
    assert not module.API_KEY
    with pytest.raises(pytest.skip.Exception):
        module.auth_headers.__wrapped__()


def test_auth_headers_use_env_value(monkeypatch):
    module = _reload_with_key(monkeypatch, "secret-xyz")
    assert module.API_KEY == "secret-xyz"
    headers = module.auth_headers.__wrapped__()
    assert headers["X-RegEngine-API-Key"] == "secret-xyz"
