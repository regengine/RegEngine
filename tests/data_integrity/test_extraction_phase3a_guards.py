"""Guards for the Phase 3a extraction test.

The extraction test used to ship a default test API key in source and
fetched a live external FDA page on every run with no opt-in gate. These
tests lock in the fix: the key must come from the environment and the
live fetch must sit behind an explicit flag.
"""

import importlib
import pathlib

import pytest

TARGET = pathlib.Path(__file__).with_name("test_fsma_204_extraction_phase3a.py")
MODULE_NAME = "tests.data_integrity.test_fsma_204_extraction_phase3a"


def _source() -> str:
    return TARGET.read_text(encoding="utf-8")


def test_no_default_api_key_in_source():
    source = _source()
    assert "rge_phase2b" not in source, "default test key is still in source"
    assert "REGENGINE_TEST_API_KEY" in source


def test_live_fetch_has_explicit_opt_in_gate():
    source = _source()
    assert "REGENGINE_ALLOW_LIVE_FDA_FETCH" in source, "live fetch flag is missing"
    assert "pytest.skip" in source, "live fetch must skip without opt-in"


def test_module_key_defaults_to_none_without_env(monkeypatch):
    monkeypatch.delenv("REGENGINE_TEST_API_KEY", raising=False)
    module = importlib.import_module(MODULE_NAME)
    monkeypatch.delenv("REGENGINE_TEST_API_KEY", raising=False)
    importlib.reload(module)
    try:
        assert module.API_KEY is None, "key must be None when the env var is unset"
    finally:
        importlib.reload(module)


def test_extraction_test_skips_without_key(monkeypatch):
    monkeypatch.delenv("REGENGINE_TEST_API_KEY", raising=False)
    monkeypatch.setenv("REGENGINE_ALLOW_LIVE_FDA_FETCH", "1")
    module = importlib.import_module(MODULE_NAME)
    importlib.reload(module)
    try:
        case = module.TestFSMA204ExtractionPhase3a()
        with pytest.raises(pytest.skip.Exception) as excinfo:
            case.test_fact_extraction_quality()
        assert "REGENGINE_TEST_API_KEY" in str(excinfo.value.msg)
    finally:
        importlib.reload(module)


def test_extraction_test_skips_without_live_flag(monkeypatch):
    monkeypatch.setenv("REGENGINE_TEST_API_KEY", "guard-only-dummy-key")
    monkeypatch.delenv("REGENGINE_ALLOW_LIVE_FDA_FETCH", raising=False)
    module = importlib.import_module(MODULE_NAME)
    importlib.reload(module)
    try:
        case = module.TestFSMA204ExtractionPhase3a()
        with pytest.raises(pytest.skip.Exception) as excinfo:
            case.test_fact_extraction_quality()
        assert "REGENGINE_ALLOW_LIVE_FDA_FETCH" in str(excinfo.value.msg)
    finally:
        importlib.reload(module)
