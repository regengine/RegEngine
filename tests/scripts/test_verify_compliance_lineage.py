from __future__ import annotations

import importlib.util
from pathlib import Path

import requests

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_compliance_lineage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_compliance_lineage", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_verify_lineage_reports_missing_hash_instead_of_crashing(capsys) -> None:
    facts = [
        {"id": "f1", "key": "Compliance Date", "value": "January 20, 2026", "_doc_version": 1},
        {
            "id": "f2",
            "key": "Compliance Date",
            "value": "July 20, 2028",
            "fact_hash": "abcdef123456",
            "previous_fact_id": "f1",
            "_doc_version": 2,
        },
    ]
    result = _MODULE.verify_lineage(facts)
    captured = capsys.readouterr().out.lower()
    assert result is False
    assert "missing" in captured and "hash" in captured


def test_verify_lineage_reports_missing_value_instead_of_crashing() -> None:
    facts = [
        {"id": "f1", "key": "Compliance Date", "fact_hash": "abcdef123456", "_doc_version": 1},
        {"id": "f2", "key": "Compliance Date", "value": None, "fact_hash": "987654321", "_doc_version": 2},
    ]
    assert _MODULE.verify_lineage(facts) is False


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


def test_fetch_distinguishes_fatal_from_transient_errors(monkeypatch, capsys) -> None:
    def fatal_get(*args, **kwargs):
        return _Resp(status_code=403, payload={"detail": "forbidden"})

    monkeypatch.setattr(_MODULE.requests, "get", fatal_get)
    assert _MODULE.get_compliance_date_facts("run-fatal") == []
    fatal_out = capsys.readouterr().out.lower()
    assert "fatal" in fatal_out

    def transient_get(*args, **kwargs):
        raise requests.exceptions.ConnectTimeout("slow peer")

    monkeypatch.setattr(_MODULE.requests, "get", transient_get)
    assert _MODULE.get_compliance_date_facts("run-transient") == []
    transient_out = capsys.readouterr().out.lower()
    assert "transient" in transient_out
    assert "transient" not in fatal_out


def test_fetch_skips_doc_missing_document_code(monkeypatch) -> None:
    docs = [{"id": "d1", "original_file_path": _MODULE.LIVE_FDA_URL + "?run=r1"}]

    def fake_get(url, **kwargs):
        if url.endswith("/pcos/authorities"):
            return _Resp(status_code=200, payload=docs)
        raise AssertionError(f"unexpected export fetch for {url}")

    monkeypatch.setattr(_MODULE.requests, "get", fake_get)
    assert _MODULE.get_compliance_date_facts("r1") == []
