import json

import httpx

import extract
from extract import extract_ir


def test_no_model_uses_fixture(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    ir, source = extract_ir("text")
    assert ir.rule_id == "US_CO_SB205_V2" and source == "fixture:OLLAMA_MODEL unset"
    assert ir.max_penalty_usd == 20000 and ir.private_right_of_action is False


def test_unreachable_host_uses_fixture(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "any")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    ir, source = extract_ir("text", timeout=2)
    assert ir.rule_id == "US_CO_SB205_V2" and source.startswith("fixture:ollama unavailable")


def _fake_post(content, calls):
    def post(url, json=None, timeout=None):
        calls.append((url, json))
        return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))
    return post


def test_valid_reply_parsed_and_only_chat_endpoint_used(monkeypatch, ir):
    calls = []
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test")
    reply = ir.model_copy(update={"rule_id": "FROM_MODEL"}).model_dump_json()
    monkeypatch.setattr(extract.httpx, "post", _fake_post(reply, calls))
    out, source = extract_ir("text")
    assert out.rule_id == "FROM_MODEL" and source == "ollama:m"
    [(url, body)] = calls
    assert url == "http://ollama.test/api/chat"
    assert body["format"]["title"] == "DeonticIR" and body["stream"] is False


def test_invalid_reply_uses_fixture(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    bad = json.dumps({"rule_id": "X", "applicability_predicates": [{"fact": "a b"}]})
    monkeypatch.setattr(extract.httpx, "post", _fake_post(bad, []))
    ir, source = extract_ir("text")
    assert ir.rule_id == "US_CO_SB205_V2" and source.startswith("fixture:invalid model output")
