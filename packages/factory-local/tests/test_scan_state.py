"""Offline tests for --scan-state: a mocked getMasterList, per bill LegiScan responses, and a
scripted LLM. No network, no Postgres, no OPA."""

import base64

import httpx
import pytest
from app import local_factory as lf
from test_live_bill import HTML_DOC, KEY, LLM_IR, FakeConn, FakeLLM

# Expected stage 1 scores in the comments. Bonus is +3 when status >= 2 and the score is > 0.
MASTERLIST = {
    "session": {"session_id": 2100, "session_name": "2026 Regular Session"},
    "0": {
        "bill_id": 101,
        "number": "SB1",
        "status": 1,
        "title": "Artificial Intelligence consumer protections",
        "description": "Requires an IMPACT ASSESSMENT before deployment",
    },  # 5 + 5 = 10, no bonus
    "1": {"bill_id": 102, "number": "HB2", "status": "3", "title": "Biometric privacy act", "description": ""},  # 8 + 3
    "2": {
        "bill_id": 103,
        "number": "HB3",
        "status": 5,
        "title": "Artificial intelligence",
        "description": "",
    },  # vetoed
    "3": {
        "bill_id": 104,
        "number": "HB4",
        "status": 2,
        "title": "Supplemental Budget",
        "description": "artificial intelligence office",
    },  # noise
    "4": {"bill_id": 105, "number": "SB5", "status": 1, "title": "Employer disclosure", "description": ""},  # 6
    "5": {"bill_id": 106, "number": "SB6", "status": 2, "title": "Employer reporting", "description": ""},  # 6 + 3
    "6": {"bill_id": 107, "number": "SB7", "status": 1, "title": "Financial literacy week", "description": ""},  # 2
    "7": {"bill_id": 108, "number": "SB8", "status": 2, "title": "Financial institutions", "description": ""},  # 2 + 3
    "8": {
        "bill_id": 109,
        "number": "HB9",
        "status": 2,
        "title": "SCHOOL DISTRICT artificial intelligence pilot",
        "description": "",
    },  # noise, upper case
    "9": {
        "bill_id": 110,
        "number": "HB10",
        "status": 4,
        "title": "Data broker registry",
        "description": "Annual audit of registrants",
    },  # 4 + 3 + 3 = 10, ties SB1 on score and wins on status
    "10": {"bill_id": 111, "number": "HB11", "status": 6, "title": "Data broker privacy", "description": ""},  # failed
    "11": {"bill_id": 112, "number": "HB12", "status": 3, "title": "Naming a post office", "description": ""},  # 0
    "12": {"bill_id": 113, "number": "HB13", "status": 0, "title": "Privacy", "description": ""},  # no status
}


def scan_legiscan(calls: list | None = None) -> lf.LegiScanClient:
    calls = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        assert params["key"] == KEY
        op = params["op"]
        if op == "getMasterList":
            return httpx.Response(200, json={"status": "OK", "masterlist": MASTERLIST})
        if op == "getBill":
            bill_id = int(params["id"])
            number = next(e["number"] for k, e in MASTERLIST.items() if k != "session" and e["bill_id"] == bill_id)
            bill = {
                "bill_id": bill_id,
                "state": "CO",
                "bill_number": number,
                "title": f"bill {number}",
                "session": {"session_id": 2100},
                # doc_id encodes the bill so getBillText can answer per bill.
                "texts": [{"doc_id": bill_id * 10, "date": "2026-02-01", "type": "Introduced", "mime": "text/html"}],
            }
            return httpx.Response(200, json={"status": "OK", "bill": bill})
        if op == "getBillText":
            body = {"doc_id": int(params["id"]), "mime": "text/html", "doc": base64.b64encode(HTML_DOC).decode()}
            return httpx.Response(200, json={"status": "OK", "text": body})
        return httpx.Response(404)

    return lf.LegiScanClient(KEY, transport=httpx.MockTransport(handler))


class ScriptedLLM(FakeLLM):
    """Answers per rule_id: an opportunity score, or an exception to raise."""

    def __init__(self, script: dict):
        super().__init__()
        self.script = script

    def _parse(self, **kwargs):
        rule_id = kwargs["messages"][1]["content"].split("\n", 1)[0].removeprefix("rule_id: ")
        answer = self.script[rule_id]
        if isinstance(answer, Exception):
            raise answer
        self._message.parsed = lf.LiveDeonticIR.model_validate({**LLM_IR, "opportunity_score_vs": answer})
        return super()._parse(**kwargs)


@pytest.fixture
def fake_deploy(monkeypatch):
    deployed = []
    monkeypatch.setattr(lf, "pg_connect", FakeConn)
    monkeypatch.setattr(lf, "ensure_schema", lambda c: None)

    def deploy(c, ir, rule_uid, rego, version_uid, tenant_id, cases, data_path):
        deployed.append(rule_uid)
        return {"chain": {"ok": True, "count": len(cases), "first_bad": None}}

    monkeypatch.setattr(lf, "deploy_and_record", deploy)
    return deployed


# Stage 1


def test_masterlist_is_one_call_and_ranked():
    calls = []
    got = scan_legiscan(calls).fetch_state_master_candidates("co", limit=10)
    assert calls == [{"key": KEY, "op": "getMasterList", "state": "CO"}]
    assert [(c["bill_id"], c["score"]) for c in got] == [(102, 11), (110, 10), (101, 10), (106, 9), (105, 6), (108, 5)]


def test_status_filter_keeps_only_1_to_4():
    ids = {c["bill_id"] for c in scan_legiscan().fetch_state_master_candidates("CO", limit=50)}
    assert not ids & {103, 111, 113}  # vetoed, failed, missing status
    assert 102 in ids  # status sent as the string "3"


def test_noise_keywords_exclude_case_insensitive():
    ids = {c["bill_id"] for c in scan_legiscan().fetch_state_master_candidates("CO", limit=50)}
    assert 104 not in ids  # "Budget" in the title, AI in the description
    assert 109 not in ids  # "SCHOOL DISTRICT"
    assert lf.score_candidate("A bill CONGRATULATING the team on its privacy work", 3) is None


def test_scoring_bonus_and_minimum():
    assert lf.score_candidate("Artificial Intelligence impact assessment", 1) == (
        10,
        ["artificial intelligence", "impact assessment"],
    )
    assert lf.score_candidate("Artificial Intelligence impact assessment", 2)[0] == 13
    assert lf.score_candidate("Naming a post office", 4) == (0, [])  # no bonus without a keyword
    ids = {c["bill_id"] for c in scan_legiscan().fetch_state_master_candidates("CO", limit=50)}
    assert 107 not in ids  # financial (2) at status 1 is under 4
    assert 108 in ids  # financial (2) + bonus (3) at status 2 reaches 5
    assert 112 not in ids


def test_top_n_and_tie_break_on_status():
    got = scan_legiscan().fetch_state_master_candidates("CO", limit=3)
    assert [c["bill_id"] for c in got] == [102, 110, 101]  # 110 and 101 tie at 10; status 4 beats 1
    assert got[0] == {
        "bill_id": 102,
        "number": "HB2",
        "title": "Biometric privacy act",
        "status": 3,
        "score": 11,
        "matched": ["biometric", "privacy"],
    }


# Stage 2


def test_system_prompt_has_the_opportunity_rubric():
    assert "opportunity_score_vs is an integer 0 to 100" in lf.LLM_SYSTEM_PROMPT
    assert "70 or more" in lf.LLM_SYSTEM_PROMPT


@pytest.mark.parametrize(("score", "action"), [(70, "GREENLIT"), (69, "SKIPPED")])
def test_threshold_is_70_inclusive(fake_deploy, score, action):
    row = lf.process_single_bill(102, scan_legiscan(), "t1", ScriptedLLM({"CO_HB2_2100": score}))
    assert row["action"] == action
    assert row["opportunity_score_vs"] == score and row["z3_status"] == lf.OK_STATUS
    if action == "GREENLIT":
        assert fake_deploy == ["CO_HB2_2100"] and row["cartridge"] == "cartridges/co_hb2_2100.rego"
    else:
        assert fake_deploy == [] and row["cartridge"] is None
        assert row["reason"] == "opportunity_score_vs 69 < 70"


def test_skipped_bill_stores_version_but_no_rule_or_deploy(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(lf, "pg_connect", lambda: conn)
    monkeypatch.setattr(lf, "ensure_schema", lambda c: None)
    monkeypatch.setattr(lf, "deploy_and_record", lambda *a, **k: pytest.fail("must not deploy"))
    row = lf.process_single_bill(102, scan_legiscan(), llm_client=ScriptedLLM({"CO_HB2_2100": 10}))
    assert row["action"] == "SKIPPED" and row["copycats"] == []
    assert not any("extracted_rules" in sql for sql, _ in conn.executed)


def test_scan_reports_errors_and_continues(fake_deploy):
    llm = ScriptedLLM({"CO_HB2_2100": 85, "CO_HB10_2100": RuntimeError("model down"), "CO_SB1_2100": 40})
    rows = lf.scan_state("CO", scan_legiscan(), top_n=3, tenant_id="t1", llm_client=llm)
    assert [(r["rank"], r["bill_uid"], r["action"]) for r in rows] == [
        (1, "CO_HB2_2100", "GREENLIT"),
        (2, "CO_SB1_2100", "SKIPPED"),
        (3, "CO_HB10", "ERROR"),  # ran second, after the error the loop went on to SB1
    ]
    assert fake_deploy == ["CO_HB2_2100"]
    assert "model down" in rows[2]["reason"] and rows[2]["legiscan_bill_id"] == 110
    assert [r["candidate_score"] for r in rows] == [11, 10, 10]

    matrix = lf.format_matrix(rows).splitlines()
    assert matrix[0].split() == ["rank", "bill_uid", "score", "max", "fine", "PRA", "Z3", "status", "action"]
    assert "GREENLIT cartridges/co_hb2_2100.rego" in matrix[1] and "$20,000" in matrix[1] and " no " in matrix[1]
    assert "SKIPPED: opportunity_score_vs 40 < 70" in matrix[2]
    assert "ERROR: LiveBillError" in matrix[3] and "model down" in matrix[3]


def test_main_scan_prints_matrix(monkeypatch, capsys):
    monkeypatch.setenv("LEGISCAN_API_KEY", KEY)
    client = scan_legiscan()
    monkeypatch.setattr(lf, "LegiScanClient", lambda key: client)
    seen = []

    def fake_process(bill_id, legiscan, tenant_id, llm_client, threshold, sim_threshold):
        assert sim_threshold == 0.80
        seen.append(bill_id)
        if bill_id == 110:
            raise lf.LiveBillError("LegiScan getBill returned HTTP 500")
        return {
            "bill_uid": f"B{bill_id}",
            "opportunity_score_vs": 50,
            "max_penalty_usd": 0,
            "private_right_of_action": True,
            "z3_status": lf.OK_STATUS,
            "action": "SKIPPED",
            "reason": "opportunity_score_vs 50 < 70",
            "cartridge": None,
        }

    monkeypatch.setattr(lf, "process_single_bill", fake_process)
    assert lf.main(["--scan-state", "--state", "CO", "--top-n", "2"]) == 1  # one bill errored
    assert seen == [102, 110]
    out = capsys.readouterr().out
    assert "B102" in out and "ERROR: LiveBillError: LegiScan getBill returned HTTP 500" in out
    assert KEY not in out


def test_main_scan_needs_key_and_rejects_bill(monkeypatch, capsys):
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    assert lf.main(["--scan-state"]) == 2
    with pytest.raises(SystemExit):
        lf.main(["--scan-state", "--bill", "SB1"])


def test_single_bill_prints_threshold_skip(monkeypatch, capsys):
    monkeypatch.setenv("LEGISCAN_API_KEY", KEY)
    client = scan_legiscan()
    monkeypatch.setattr(lf, "LegiScanClient", lambda key: client)
    monkeypatch.setattr(lf, "pg_connect", FakeConn)
    monkeypatch.setattr(lf, "ensure_schema", lambda c: None)
    monkeypatch.setattr(lf, "deploy_and_record", lambda *a, **k: pytest.fail("must not deploy"))
    import openai

    monkeypatch.setattr(openai, "OpenAI", lambda **_: ScriptedLLM({"CO_HB2_2100": 55}))
    assert lf.main(["--bill-id", "102"]) == 0
    err = capsys.readouterr().err
    assert "step 3 of 4: copycats >= 0.80: none" in err
    assert (
        "step 4 of 4: SKIPPED CO_HB2_2100: opportunity_score_vs 55 < 70; bill version and embedding stored, "
        "no rule compiled or deployed"
    ) in err
