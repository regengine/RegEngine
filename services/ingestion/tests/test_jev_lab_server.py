"""``scripts/jev_lab`` server: local-only, token-gated, privacy-guarded, and honest about fake mode.

Contract pinned here (offline fake; nothing leaves the process):

* Every ``/api`` call needs the per-process bearer token, a ``Host`` naming
  this server (DNS-rebinding defence) and no cross-site ``Origin`` or
  ``Sec-Fetch-Site``; a POST must carry this server's ``Origin``. No CORS
  header is ever sent, and every response carries the CSP and frame headers.
* The page and its two static files load without the token; nothing else
  under ``/static`` is served.
* The sandbox refuses secrets, personal data and rows of values before
  anything is sent, and never echoes what it refused.
* Labelled rows are validated like ``jev_eval_cases.json`` and kept in the
  lab directory with a ``labelled_at`` stamp.
* A score-only run and a short offline loop run in the background and land
  in the ledger; status never contains the API key.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "scripts" / "jev_lab"


def _load_lab():
    if "jev_lab" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "jev_lab", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["jev_lab"] = module
        spec.loader.exec_module(module)
    return sys.modules["jev_lab"]


_load_lab()
from jev_lab import jev_access, ledger, server  # noqa: E402

PORT = 8204
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = "test-token-not-a-secret"  # pragma: allowlist secret


@pytest.fixture
def lab(tmp_path):
    home = ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE)
    home.ensure()
    home.split_path.write_text(json.dumps({"salt": "test-salt-0", "created": "2026-01-01T00:00:00Z", "looks": {}}))
    decider = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE)
    state = server.Lab(
        decider=decider, ledger=home, proposer_backend="offline", proposer_model="m", port=PORT, token=TOKEN
    )
    yield state
    state.stop_loop()
    decider.close()


@pytest.fixture
def client(lab):
    return TestClient(server.create_app(lab), base_url=ORIGIN)


AUTH = {"Authorization": f"Bearer {TOKEN}"}
POST = {**AUTH, "Origin": ORIGIN}


def _wait_idle(lab, timeout=120.0):
    deadline = time.monotonic() + timeout
    while lab.running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not lab.running


# ---------------------------------------------------------------------------
# Local-only guard
# ---------------------------------------------------------------------------


def test_page_and_its_files_load_without_the_token_and_nothing_else_does(client):
    page = client.get("/")
    assert page.status_code == 200 and "<title>Jev Lab</title>" in page.text
    assert client.get("/static/lab.js").status_code == 200
    assert client.get("/static/lab.css").status_code == 200
    assert client.get("/static/index.html").status_code == 404
    assert client.get("/static/..%2f__init__.py").status_code == 404
    assert client.get("/docs").status_code == 404


def test_every_response_carries_the_security_headers_and_no_cors(client):
    for response in (client.get("/"), client.get("/api/status"), client.get("/api/status", headers=AUTH)):
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "method,headers,status",
    [
        ("get", {}, 401),
        ("get", {"Authorization": "Bearer wrong"}, 401),
        ("get", {**AUTH, "Host": "evil.example:8204"}, 403),
        ("get", {**AUTH, "Origin": "https://evil.example"}, 403),
        ("get", {**AUTH, "Sec-Fetch-Site": "cross-site"}, 403),
        ("post", AUTH, 403),
        ("post", {**AUTH, "Origin": "http://localhost:9999"}, 403),
    ],
)
def test_requests_from_anywhere_but_the_page_are_refused(client, method, headers, status):
    if method == "get":
        response = client.get("/api/status", headers=headers)
    else:
        response = client.post("/api/loop/stop", headers=headers, json={})

    assert response.status_code == status


def test_oversized_bodies_are_refused(client):
    response = client.post("/api/ask", headers=POST, content=b"{" + b" " * 300_000 + b"}")

    assert response.status_code == 413


def test_status_says_fake_and_never_carries_the_key(client, lab):
    response = client.get("/api/status", headers=AUTH)

    data = response.json()
    assert data["mode"] == "fake"
    assert data["jev"]["model"] == "fake-jev-offline"
    assert jev_access.FAKE_KEY not in response.text
    assert data["vocabulary"]["header_mapping"][0] == "traceability_lot_code"
    assert data["estimate"]["jev_requests_max"] > 0


def test_status_reports_held_out_wear_from_the_split_file(client, lab):
    salt = lab.ledger.epoch()["salt"]
    lab.ledger.record_holdout_look("header_mapping", salt=salt)
    lab.ledger.record_holdout_look("header_mapping", salt=salt)

    epoch = client.get("/api/status", headers=AUTH).json()["epoch"]
    assert epoch["looks"]["header_mapping"] == 2 and epoch["cap"] == ledger.MAX_HOLDOUT_LOOKS

    client.post("/api/ledger/rotate", headers=POST, json={})
    assert client.get("/api/status", headers=AUTH).json()["epoch"]["looks"] == {"header_mapping": 0, "file_cte": 0}


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


def data_ctes() -> set[str]:
    from shared.jev import cte_classification as cte

    return set(cte.CTE_NAMES) | {cte.MIXED_OR_UNCLEAR}


CTE_QUESTION = {
    "type": "choice",
    "instructions": "Which FSMA 204 critical tracking event do rows with these CSV headers record?",
    "criteria": {"shipping": "goods leaving: ship date", "receiving": "goods arriving", "unclear": None},
}


def test_ask_answers_typed_questions(client, lab):
    response = client.post(
        "/api/ask",
        headers=POST,
        json={"state": {"headers": ["Ship Dte", "Lot No."]}, "questions": {"cte": CTE_QUESTION}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "fake"
    assert data["answers"]["cte"]["choice"] == "shipping"
    assert "cte [choice]: shipping" in data["text"]
    assert lab.decider.stats()["sent"] == 1


def test_ask_publishes_one_mote_per_question_with_the_answer_s_own_confidence(client, lab):
    noul = {"type": "noul", "instructions": "Does one of the headers name a traceability lot code column?"}
    response = client.post(
        "/api/ask",
        headers=POST,
        json={"state": {"headers": ["Ship Dte", "Lot No."]}, "questions": {"cte": CTE_QUESTION, "has_lot": noul}},
    )

    data = response.json()
    motes = [item["data"] for item in lab.hub._buffer if item["event"] == "sandbox"]
    assert [m["question_id"] for m in motes] == ["cte", "has_lot"]
    assert {m["ask_id"] for m in motes} == {data["ask_id"]}
    assert motes[0]["confidence"] == pytest.approx(data["answers"]["cte"]["confidence"])
    p_yes = data["answers"]["has_lot"]["probability_yes"]
    assert motes[1]["confidence"] == pytest.approx(max(p_yes, 1 - p_yes))


def test_answer_confidence_treats_a_confident_no_like_a_confident_yes():
    assert server.answer_confidence({"type": "noul", "probability_yes": 0.03}) == pytest.approx(0.97)
    assert server.answer_confidence({"type": "noul", "probability_yes": 0.9}) == pytest.approx(0.9)
    assert server.answer_confidence({"type": "choice", "confidence": 0.6}) == 0.6
    assert server.answer_confidence({"missing": True}) is None


def test_ask_refuses_secrets_and_never_echoes_them(client, lab):
    secret = "postgres://app:hunter2@db.internal/regengine"  # pragma: allowlist secret
    response = client.post(
        "/api/ask", headers=POST, json={"state": {"log": secret}, "questions": {"cte": CTE_QUESTION}}
    )

    assert response.status_code == 422
    assert "credentials in a URL at $.state.log" in response.json()["refused"]
    assert "hunter2" not in response.text
    assert lab.decider.stats()["sent"] == 0


@pytest.mark.parametrize(
    "questions,detail",
    [
        ({}, "non-empty object"),
        ({"q": {"type": "essay", "instructions": "?"}}, "choice, noul or score"),
        ({"q": {"type": "choice", "instructions": "?", "criteria": {"a": None}}}, "at least two options"),
        ({"q": {"type": "score", "instructions": "?", "criteria": ["only"]}}, "2 to 10 levels"),
        ({"q": {"type": "choice", "instructions": "?", "criteria": 5}}, "at least two options"),
        ({"q": {"type": "score", "instructions": "?", "criteria": 3}}, "2 to 10 levels"),
        ({"q": {"type": "noul", "instructions": 7}}, "instructions must be text"),
    ],
)
def test_ask_refuses_malformed_questions(client, questions, detail):
    response = client.post("/api/ask", headers=POST, json={"state": "x", "questions": questions})

    assert response.status_code == 400 and detail in response.json()["detail"]


def test_sandbox_feedback_is_recorded_without_the_question(client, lab):
    response = client.post(
        "/api/adhoc-feedback",
        headers=POST,
        json={
            "request_id": "fake_1",
            "ask_id": "a1b2c3",
            "question_id": "cte",
            "type": "choice",
            "confidence": 0.8,
            "verdict": "wrong",
        },
    )

    assert response.status_code == 200
    row = [r for r in lab.ledger.rows() if r["type"] == "adhoc_feedback"][-1]
    assert row["verdict"] == "wrong" and row["confidence"] == 0.8 and row["mode"] == "fake"
    # The page colours the mote of exactly this question of this ask.
    event = [item["data"] for item in lab.hub._buffer if item["event"] == "feedback"][-1]
    assert event == {"ask_id": "a1b2c3", "question_id": "cte", "verdict": "wrong"}
    assert client.post("/api/adhoc-feedback", headers=POST, json={"verdict": "maybe"}).status_code == 400


def test_header_check_asks_both_production_questions(client):
    response = client.post(
        "/api/headers",
        headers=POST,
        json={"headers": ["Ship Dte", "Lot No.", "Freight Co.", "Product"], "wording": "production"},
    )

    data = response.json()
    assert response.status_code == 200
    assert [c["header"] for c in data["columns"]] == ["Ship Dte", "Lot No.", "Freight Co."]
    assert data["recognized"] == ["Product"]
    assert data["file_cte"]["answer"] in data_ctes()
    assert data["file_cte"]["band"] in {"auto_apply", "review", "reject"}
    assert data["wording"] == {"header_mapping": "csv-header-mapping.v3", "file_cte": "csv-file-cte.v2"}


def test_header_check_refuses_rows_of_values_and_broken_rows(client, lab):
    values = client.post(
        "/api/headers",
        headers=POST,
        json={"headers": ["Romaine Hearts 3ct", "LOT-R-0423", "240", "cases", "Fresh Farms Inc", "2024-04-23"]},
    )
    broken = client.post("/api/headers", headers=POST, json={"headers": ["Ship Date\nLOT-1,12", "Qty"]})

    assert values.status_code == 422 and values.json()["refused"] == [
        "cell(s) 2, 3, 6 look like values (dates, numbers or codes), not column names: paste only the header row"
    ]
    numbers = client.post(
        "/api/ask", headers=POST, json={"state": {"gln": 1234567890128}, "questions": {"cte": CTE_QUESTION}}
    )
    assert numbers.status_code == 422
    assert broken.status_code == 400
    assert lab.decider.stats()["sent"] == 0


def test_labels_are_validated_and_stamped(client, lab):
    saved = client.post(
        "/api/labels",
        headers=POST,
        json={"headers": ["Pick Dt", "Grower", "Qty"], "cte": "harvesting", "mappings": {"Pick Dt": "harvest_date"}},
    )
    unknown = client.post(
        "/api/labels", headers=POST, json={"headers": ["Pick Dt"], "mappings": {"Pick Dt": "pick_date"}}
    )
    read = client.post(
        "/api/labels", headers=POST, json={"headers": ["Quantity"], "mappings": {"Quantity": "quantity"}}
    )

    assert saved.status_code == 200 and saved.json()["id"].startswith("local-")
    case = lab.ledger.local_cases()[0]
    assert case["headers"] == ["Pick Dt", "Grower", "Qty"] and case["labelled_at"] > "2026-01-01T00:00:00Z"
    assert unknown.status_code == 400 and "unknown label(s) pick_date" in unknown.json()["detail"]
    twin = client.post(
        "/api/labels",
        headers=POST,
        json={
            "headers": [
                "Ship Dte",
                "Sales Order",
                "Cust Name",
                "Ship-To City",
                "Item Desc",
                "Lot No.",
                "Cases Shipped",
                "UOM",
                "BOL No",
                "Freight Co.",
            ],
            "cte": "shipping",
        },
    )
    assert twin.status_code == 400 and "already labelled as case erp-shipping-log" in twin.json()["detail"]
    wide = [f"Extra Col {chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(48)] + ["Pick Dt"]
    beyond = client.post("/api/labels", headers=POST, json={"headers": wide, "mappings": {"Pick Dt": "harvest_date"}})
    assert beyond.status_code == 400 and "first 48 unrecognised columns" in beyond.json()["detail"]
    assert read.status_code == 400 and "already reads" in read.json()["detail"]


# ---------------------------------------------------------------------------
# Loop control
# ---------------------------------------------------------------------------


def test_score_only_and_offline_loop_runs_land_in_the_ledger(client, lab):
    started = client.post("/api/loop/start", headers=POST, json={"generations": 0})
    assert started.status_code == 200
    _wait_idle(lab)
    assert lab.last_summary["generations"] == 0 and lab.loop_error is None

    client.post("/api/loop/start", headers=POST, json={"generations": 2, "proposer": "offline"})
    busy = client.post("/api/loop/start", headers=POST, json={"generations": 1})
    _wait_idle(lab)

    assert busy.status_code in (200, 409)
    ledger_rows = client.get("/api/ledger", headers=AUTH).json()["rows"]
    generations = [r for r in ledger_rows if r["type"] == "generation"]
    assert generations and lab.last_summary["generations"] >= 1
    digest = next(iter(generations[0]["candidates"].values()))
    diff = client.get(f"/api/question-sets/{digest}/diff", headers=AUTH).json()
    assert diff["changes"] and diff["baseline"] in {"csv-header-mapping.v3", "csv-file-cte.v2"}
    assert client.get("/api/question-sets/not-a-digest", headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "body,detail",
    [
        ({"generations": 26}, "generations must be"),
        ({"generations": "many"}, "generations must be"),
        ({"margin": 0.9}, "margin must be"),
        ({"margin": "wide"}, "margin must be"),
        ({"proposer": "gpt"}, "proposer must be"),
    ],
)
def test_loop_start_validates_its_inputs(client, body, detail):
    response = client.post("/api/loop/start", headers=POST, json=body)

    assert response.status_code == 400 and detail in response.json()["detail"]


def test_only_one_run_starts_when_two_requests_race(lab, monkeypatch):
    import threading as _threading

    gate = _threading.Barrier(2)
    started: list = []
    monkeypatch.setattr(server, "run_loop", lambda **kw: (started.append(1), time.sleep(0.3)))
    monkeypatch.setattr(server, "build_proposer", lambda backend, model: None)
    errors: list = []

    def go():
        try:
            gate.wait()
            lab.start_loop(server.LoopConfig(generations=1), "offline")
        except RuntimeError as exc:
            errors.append(str(exc))

    threads = [_threading.Thread(target=go) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    _wait_idle(lab)

    assert len(started) == 1 and errors == ["a run is already in progress"]


def test_confirm_and_rotate(client, lab):
    assert client.post("/api/confirm", headers=POST, json={"digest": "0" * 64}).status_code == 404
    salt = lab.ledger.epoch()["salt"]

    assert client.post("/api/ledger/rotate", headers=POST, json={}).json() == {"rotated": True}
    assert lab.ledger.epoch()["salt"] != salt
    assert client.post("/api/ledger/reset", headers=POST, json={}).json() == {"reset": True}


def test_event_hub_replays_the_current_run_to_late_joiners():
    hub = server.EventHub()

    async def scenario():
        hub.publish("old", {"n": 0})
        hub.publish("run_started", {"run_id": "r"})
        hub.publish("observation", {"n": 1})
        queue, backlog = hub.subscribe()
        hub.publish("run_done", {"n": 2})
        live = await asyncio.wait_for(queue.get(), 1)
        hub.unsubscribe(queue)
        return backlog, live

    backlog, live = asyncio.run(scenario())

    assert [item["event"] for item in backlog] == ["run_started", "observation"]
    assert live["event"] == "run_done"
    assert server._sse("x", {"a": 1}, 3) == b'id: 3\nevent: x\ndata: {"a": 1}\n\n'


def test_event_hub_keeps_ask_jev_events_across_runs():
    hub = server.EventHub()
    hub.publish("sandbox", {"ask_id": "a", "question_id": "q"})
    hub.publish("observation", {"n": 0})
    hub.publish("feedback", {"ask_id": "a", "question_id": "q", "verdict": "right"})
    hub.publish("run_started", {"run_id": "r"})

    assert [item["event"] for item in hub._buffer] == ["sandbox", "feedback", "run_started"]


def test_event_stream_hello_marks_where_the_replay_ends(lab):
    lab.hub.publish("sandbox", {"ask_id": "a", "question_id": "q", "confidence": 0.9})
    lab.hub.publish("run_started", {"run_id": "r"})
    last = lab.hub._buffer[-1]["seq"]

    async def first_events():
        app = server.create_app(lab)
        messages = []
        sent = asyncio.Event()

        async def receive():
            await sent.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if b"run_started" in message.get("body", b""):
                sent.set()

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/events",
            "raw_path": b"/api/events",
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "server": ("127.0.0.1", PORT),
            "client": ("127.0.0.1", 50000),
            "headers": [(b"host", f"127.0.0.1:{PORT}".encode()), (b"authorization", f"Bearer {TOKEN}".encode())],
        }
        await asyncio.wait_for(app(scope, receive, send), 10)
        return b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")

    body = asyncio.run(first_events()).decode()
    hello = json.loads(body.split("event: hello\ndata: ", 1)[1].split("\n", 1)[0])
    assert hello["replay_until"] == last and hello["backlog"] == 2
    assert body.index("event: sandbox") < body.index("event: run_started")
