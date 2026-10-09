"""Regression tests for the tests/audit/verify_chain.py manual helper.

The helper must stay uncollected by pytest and must never call live
services unless explicitly opted in. These tests fail on the old version
of the helper (no collection guard, unconditional localhost HTTP) and
pass on the fixed version.
"""

import importlib.util
from pathlib import Path

import pytest

HELPER_PATH = Path(__file__).resolve().parent / "verify_chain.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("audit_verify_chain_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_helper_opts_out_of_pytest_collection():
    module = _load_helper()
    assert getattr(module, "__test__", True) is False


def test_main_refuses_network_without_opt_in(monkeypatch, capsys):
    module = _load_helper()
    monkeypatch.delenv(module.LIVE_ENV_VAR, raising=False)
    calls = []

    def _no_network(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("must not call the network without opt-in")

    monkeypatch.setattr(module.requests, "get", _no_network)
    assert module.main() == 2
    assert calls == []
    assert "VERIFY_CHAIN_LIVE" in capsys.readouterr().out


def test_main_uses_configured_base_url_when_opted_in(monkeypatch):
    module = _load_helper()
    monkeypatch.setenv(module.LIVE_ENV_VAR, "1")
    monkeypatch.setenv(module.BASE_URL_ENV_VAR, "http://example.invalid:9999")
    seen_urls = []

    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_get(url, **kwargs):
        seen_urls.append(url)
        if url.rstrip("/").endswith("/pcos/authorities"):
            return _Resp([])
        return _Resp({"authority_code": "X", "documents": []})

    monkeypatch.setattr(module.requests, "get", _fake_get)
    assert module.main() == 0
    assert seen_urls
    assert all(u.startswith("http://example.invalid:9999/") for u in seen_urls)


def _fact(key="k1", fact_id="f1", value="v", version=1, previous_fact_id=None):
    return {
        "id": fact_id,
        "key": key,
        "value": value,
        "version": version,
        "condition": {},
        "source_ref": {},
        "previous_fact_id": previous_fact_id,
    }


def test_verifier_counts_a_hash_mismatch_as_failure():
    module = _load_helper()
    fact = _fact()
    fact["fact_hash"] = "0" * 64
    verifier = module.ChainVerifier({"authority_code": "X", "documents": [{"facts": [fact]}]})
    results = verifier.verify()
    assert results.hashes_verified == 0
    assert results.hashes_failed == 1
    assert results.details


def test_verifier_accepts_matching_hash_and_lineage():
    module = _load_helper()
    parent = _fact(key="k", fact_id="p", version=1)
    child = _fact(key="k", fact_id="c", version=2, previous_fact_id="p")
    probe = module.ChainVerifier({})
    parent["fact_hash"] = probe.recompute_hash(parent)
    child["fact_hash"] = probe.recompute_hash(child)
    verifier = module.ChainVerifier({"authority_code": "X", "documents": [{"facts": [parent, child]}]})
    results = verifier.verify()
    assert results.hashes_failed == 0
    assert results.hashes_verified == 2
    assert results.lineage_links_verified == 1
    assert results.lineage_links_failed == 0
    assert results.consistency_errors == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
