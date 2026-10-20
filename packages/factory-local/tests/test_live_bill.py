"""Offline tests for the live bill pipeline: LegiScan over httpx.MockTransport, a fake
OpenAI client, no network, no Postgres, no OPA."""

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from app import local_factory as lf
from schemas import DeonticIR

from conftest import make_ir

KEY = "test-legiscan-key-do-not-log"

HTML_DOC = b"""<html><head><style>p{color:red}</style><script>var x=1;</script></head>
<body><h1>SENATE BILL 24-205</h1><p>A developer of a <b>high-risk</b> AI system shall</p>
<p>complete an annual impact assessment.</p></body></html>"""


def make_pdf(text: str) -> bytes:
    """Smallest valid one page PDF with a Helvetica text line."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


BILL = {
    "bill_id": 1789,
    "state": "CO",
    "bill_number": "SB205",
    "title": "Consumer Protections for Artificial Intelligence",
    "url": "https://legiscan.com/CO/bill/SB205/2024",
    "state_link": "https://leg.colorado.gov/bills/sb24-205",
    "session": {"session_id": 2061, "year_start": 2024},
    "texts": [
        {
            "doc_id": 100,
            "date": "2024-04-10",
            "type": "Introduced",
            "mime": "text/html",
            "state_link": "https://x/intro",
        },
        {"doc_id": 300, "date": "2024-05-17", "type": "Enrolled", "mime": "text/html", "state_link": "https://x/enr"},
        {"doc_id": 200, "date": "2024-05-01", "type": "Engrossed", "mime": "text/html", "state_link": "https://x/eng"},
    ],
}


def legiscan(doc: bytes, mime: str, calls: list | None = None, search: dict | None = None) -> lf.LegiScanClient:
    calls = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        assert request.url.host == "api.legiscan.com"
        assert params["key"] == KEY
        op = params["op"]
        if op == "getSearch":
            return httpx.Response(200, json={"status": "OK", "searchresult": search})
        if op == "getBill":
            assert params["id"] == "1789"
            return httpx.Response(200, json={"status": "OK", "bill": BILL})
        if op == "getBillText":
            body = {"doc_id": int(params["id"]), "mime": mime, "doc": base64.b64encode(doc).decode()}
            return httpx.Response(200, json={"status": "OK", "text": body})
        return httpx.Response(404)

    return lf.LegiScanClient(KEY, transport=httpx.MockTransport(handler))


def test_search_bill_id_exact_match_latest_session():
    calls = []
    search = {
        "summary": {"count": 3},
        "0": {"state": "CO", "bill_number": "SB205", "bill_id": 11, "last_action_date": "2019-05-01"},
        "1": {"state": "CO", "bill_number": "SB2050", "bill_id": 12, "last_action_date": "2026-03-01"},
        "2": {"state": "CO", "bill_number": "SB 205", "bill_id": 13, "last_action_date": "2024-05-17"},
    }
    client = legiscan(b"", "text/html", calls, search)
    assert client.search_bill_id("co", "SB205") == 13
    assert calls[0]["op"] == "getSearch" and calls[0]["state"] == "CO" and calls[0]["bill"] == "SB205"


def test_search_bill_id_us_congress_and_no_match():
    search = {"summary": {}, "0": {"state": "US", "bill_number": "HR1", "bill_id": 7, "last_action_date": "2025-01-01"}}
    assert legiscan(b"", "text/html", search=search).search_bill_id("US", "HR1") == 7
    with pytest.raises(lf.LiveBillError, match="no bill HR2"):
        legiscan(b"", "text/html", search=search).search_bill_id("US", "HR2")


def test_fetch_latest_bill_text_html():
    calls = []
    meta = legiscan(HTML_DOC, "text/html", calls).fetch_latest_bill_text(1789)
    assert calls[-1] == {"key": KEY, "op": "getBillText", "id": "300"}  # latest by date, not list order
    assert meta["bill_uid"] == "CO_SB205_2061"
    assert meta["version_stage"] == "Enrolled"
    assert meta["doc_id"] == 300
    assert meta["url"] == "https://x/enr"
    assert (meta["state"], meta["bill_number"], meta["title"]) == ("CO", "SB205", BILL["title"])
    assert "high-risk" in meta["full_text"] and "annual impact assessment" in meta["full_text"]
    assert "<" not in meta["full_text"] and "var x" not in meta["full_text"] and "color:red" not in meta["full_text"]


def test_fetch_latest_bill_text_pdf():
    meta = legiscan(make_pdf("A deployer shall notify the consumer"), "application/pdf").fetch_latest_bill_text(1789)
    assert "A deployer shall notify the consumer" in meta["full_text"]


def test_unsupported_mime_is_an_error():
    with pytest.raises(lf.LiveBillError, match="unsupported"):
        legiscan(b"{\\rtf1}", "application/rtf").fetch_latest_bill_text(1789)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"status": "ERROR", "alert": {"message": "Invalid API key"}}),
        httpx.Response(200, text="not json"),
    ],
)
def test_legiscan_errors_never_contain_key(response, caplog):
    client = lf.LegiScanClient(KEY, transport=httpx.MockTransport(lambda request: response))
    caplog.set_level("DEBUG")
    with pytest.raises(lf.LiveBillError) as exc_info:
        client.get_bill(1)
    assert KEY not in str(exc_info.value)
    exc = exc_info.value  # an httpx error (which carries the URL) is never chained into the traceback
    assert exc.__cause__ is None and (exc.__context__ is None or exc.__suppress_context__)
    assert KEY not in repr(client)
    assert KEY not in caplog.text


def test_legiscan_network_error_never_contains_key():
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(lf.LiveBillError) as exc_info:
        lf.LegiScanClient(KEY, transport=httpx.MockTransport(handler)).get_bill(1)
    assert KEY not in str(exc_info.value)


LLM_IR = {
    "rule_id": "whatever-the-model-said",
    "citation": "C.R.S. § 6-1-1703",
    "modality": "OBLIGATION",
    "applicability_predicates": [
        {"fact": "fte_count", "operator": "GREATER_THAN", "value": 49},
        {"fact": "does_business_in_co", "operator": "EQUALS", "value": True},
    ],
    "action_required": "annual_impact_assessment_completed",
    "safe_harbor_control": "nist_ai_rmf_aligned",
    "max_penalty_usd": 20000,
    "private_right_of_action": False,
    "opportunity_score_vs": 72,
}


class FakeLLM:
    def __init__(self, parsed=None, refusal=None):
        self.kwargs = None
        self._message = SimpleNamespace(parsed=parsed, refusal=refusal)
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse)))

    def _parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)])


def bill_meta(text: str = "The developer shall do things.") -> dict:
    return {
        "bill_uid": "CO_SB205_2061",
        "state": "CO",
        "bill_number": "SB205",
        "version_stage": "Enrolled",
        "title": "AI",
        "full_text": text,
    }


def test_extract_uses_structured_output_and_forces_rule_id(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    fake = FakeLLM(lf.LiveDeonticIR.model_validate(LLM_IR))
    ir = lf.extract_deontic_ir_from_text(bill_meta("x" * 50000), client=fake)
    assert ir.rule_id == "CO_SB205_2061"
    assert ir.opportunity_score_vs == 72
    assert fake.kwargs["model"] == "test-model"
    assert fake.kwargs["temperature"] == 0
    assert fake.kwargs["response_format"] is lf.LiveDeonticIR
    user = fake.kwargs["messages"][1]["content"]
    assert "rule_id: CO_SB205_2061" in user
    assert user.count("x") == lf.MAX_LLM_CHARS  # body truncated to 45000 chars


def test_llm_model_accepts_any_rule_id_but_stored_ir_is_strict():
    assert lf.LiveDeonticIR.model_validate(LLM_IR).rule_id == "whatever-the-model-said"
    with pytest.raises(ValueError, match="unsafe rule_id"):
        DeonticIR.model_validate(LLM_IR)


def test_extract_refusal_is_an_error():
    with pytest.raises(lf.LiveBillError, match="refusal"):
        lf.extract_deontic_ir_from_text(bill_meta(), client=FakeLLM(None, refusal="no"))


def test_extract_wraps_client_errors():
    class Broken:
        beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=lambda **_: (_ for _ in ()).throw(OSError("down"))))
        )

    with pytest.raises(lf.LiveBillError, match="LLM extraction"):
        lf.extract_deontic_ir_from_text(bill_meta(), client=Broken())


def test_llm_defaults(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    import openai

    seen = {}

    class Recorder(FakeLLM):
        def __init__(self, **kwargs):
            seen.update(kwargs)
            super().__init__(lf.LiveDeonticIR.model_validate(LLM_IR))

    monkeypatch.setattr(openai, "OpenAI", Recorder)
    lf.extract_deontic_ir_from_text(bill_meta())
    assert seen == {"base_url": "http://localhost:11434/v1", "api_key": "ollama"}
    assert lf.llm_model() == "qwen2.5-coder:14b"


def test_boundary_payload_sits_on_threshold():
    ir = DeonticIR.model_validate({**LLM_IR, "rule_id": "CO_SB205_2061"})
    check = lf.verify_with_boundary(ir)
    assert check["verified"] is True
    assert check["status"] == "UNSAT_DETERMINISTIC_AND_COMPLETE"
    assert check["boundary_payload"] == {
        "fte_count": 50,
        "does_business_in_co": True,
        "affected_consumer_count": 1,
        "controls": {"annual_impact_assessment_completed": False, "nist_ai_rmf_aligned": False},
    }
    cases = lf.boundary_cases(ir, check["boundary_payload"])
    assert [(c[0], c[2], c[3]) for c in cases] == [
        ("boundary_breach", "NON_COMPLIANT_BREACH", 20000),
        ("boundary_safe_harbor", "COMPLIANT_VIA_SAFE_HARBOR", 0),
    ]
    assert cases[1][1]["controls"]["nist_ai_rmf_aligned"] is True


def test_boundary_less_than_and_nested_and_prohibition():
    ir = make_ir(
        "T_LT",
        [{"fact": "org.revenue_musd", "operator": "LESS_THAN", "value": 10}],
        modality="PROHIBITION",
        action_required="sells_personal_data",
    )
    payload = lf.verify_with_boundary(ir)["boundary_payload"]
    assert payload["org"] == {"revenue_musd": 9}
    assert payload["controls"]["sells_personal_data"] is True  # breach of a prohibition: the act happened


def test_contradictory_predicates_are_not_verified():
    ir = make_ir(
        "T_BAD",
        [
            {"fact": "fte_count", "operator": "GREATER_THAN", "value": 50},
            {"fact": "fte_count", "operator": "LESS_THAN", "value": 10},
        ],
    )
    check = lf.verify_with_boundary(ir)
    assert check == {**check, "verified": False, "status": "UNSAT_BREACH_UNREACHABLE", "boundary_payload": None}


def test_compiled_cartridge_package_and_status_key():
    ir = DeonticIR.model_validate({**LLM_IR, "rule_id": "CO_SB205_2061"})
    rego = lf.compile_ir_to_rego(ir, f"cartridge.{lf.cartridge_name(ir.rule_id)}")
    assert rego.startswith("package cartridge.co_sb205_2061\n")
    assert 'compliance_status := "NON_COMPLIANT_BREACH" if' in rego


class FakeConn:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


def test_live_bill_run_persists_then_deploys(monkeypatch):
    conn, deployed = FakeConn(), {}
    monkeypatch.setattr(lf, "pg_connect", lambda: conn)
    monkeypatch.setattr(lf, "ensure_schema", lambda c: None)

    def fake_deploy(c, ir, rule_uid, rego, version_uid, tenant_id, cases, data_path):
        deployed.update(rule_uid=rule_uid, version_uid=version_uid, cases=cases, data_path=data_path, rego=rego)
        return {"chain": {"ok": True, "count": len(cases), "first_bad": None}}

    monkeypatch.setattr(lf, "deploy_and_record", fake_deploy)
    out = lf.live_bill_run(
        KEY,
        "CO",
        "SB205",
        tenant_id="t1",
        legiscan=legiscan(
            HTML_DOC, "text/html", search={"0": {"state": "CO", "bill_number": "SB205", "bill_id": 1789}}
        ),
        llm_client=FakeLLM(lf.LiveDeonticIR.model_validate(LLM_IR)),
    )
    assert out["rule_uid"] == "CO_SB205_2061"
    assert out["version_uid"] == "CO_SB205_2061@300"
    assert out["package"] == "cartridge.co_sb205_2061" and out["cartridge"] == "cartridges/co_sb205_2061.rego"
    assert out["human_verified"] is False and out["chain"]["ok"] is True
    assert deployed["data_path"] == "cartridge/co_sb205_2061"
    assert deployed["rego"].startswith("package cartridge.co_sb205_2061\n")
    assert [c[2] for c in deployed["cases"]] == ["NON_COMPLIANT_BREACH", "COMPLIANT_VIA_SAFE_HARBOR"]

    (bill_sql, bill_params), (rule_sql, rule_params) = conn.executed
    assert "INSERT INTO bill_versions" in bill_sql
    assert bill_params[:3] == ("CO_SB205_2061@300", "CO_SB205_2061", "US-CO") and bill_params[-1] == "Enrolled"
    assert "INSERT INTO extracted_rules" in rule_sql and "human_verified = false" in rule_sql
    z3_record = rule_params[4].obj
    assert z3_record["status"] == "UNSAT_DETERMINISTIC_AND_COMPLETE" and z3_record["verified"] is True
    assert "opportunity_score_vs" not in rule_params[2].obj  # only DeonticIR fields are stored as the IR
    assert rule_params[-1] == 72
    json.dumps(z3_record)


def test_live_bill_run_refuses_unverified_after_persisting(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(lf, "pg_connect", lambda: conn)
    monkeypatch.setattr(lf, "ensure_schema", lambda c: None)
    monkeypatch.setattr(lf, "deploy_and_record", lambda *a, **k: pytest.fail("must not deploy"))
    bad = {
        **LLM_IR,
        "applicability_predicates": [
            {"fact": "fte_count", "operator": "GREATER_THAN", "value": 50},
            {"fact": "fte_count", "operator": "LESS_THAN", "value": 10},
        ],
    }
    with pytest.raises(lf.LiveBillError, match="UNSAT_BREACH_UNREACHABLE"):
        lf.live_bill_run(
            KEY,
            bill_id=1789,
            legiscan=legiscan(HTML_DOC, "text/html"),
            llm_client=FakeLLM(lf.LiveDeonticIR.model_validate(bad)),
        )
    assert len(conn.executed) == 2  # bill version and unverified rule are still recorded
    assert conn.executed[1][1][4].obj["verified"] is False


def test_bill_without_key_is_a_clear_error(monkeypatch, capsys):
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    monkeypatch.setattr(lf, "dry_run", lambda *a: pytest.fail("must not fall back to the dry run"))
    assert lf.main(["--bill", "SB205"]) == 2
    assert "LEGISCAN_API_KEY is not set" in capsys.readouterr().err
    assert lf.main(["--bill-id", "1789"]) == 2


def test_no_args_still_runs_the_dry_run(monkeypatch, capsys):
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(lf, "dry_run", lambda tenant: calls.append(tenant) or {"chain": {"ok": True}})
    monkeypatch.setattr(lf, "live_bill_run", lambda *a, **k: pytest.fail("no args must not go live"))
    assert lf.main([]) == 0
    assert calls == [lf.TENANT_ID]
