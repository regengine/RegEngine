"""``scripts/jev_ask.py``: ask Jev typed questions from the command line.

Offline (``httpx2.MockTransport``): the command line becomes the API's
question object, the state goes through as given, answers print in question
order with their confidence, and the key is never printed. Without a key
nothing is sent.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
import structlog

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "jev_ask.py"
FAKE_KEY = "ts-ask-test-key-51e0"  # pragma: allowlist secret
ENV = {"TYPESAFE_API_KEY": FAKE_KEY, "REGENGINE_JEV_MAX_RETRIES": "0"}


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("jev_ask", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev_ask"] = module
    spec.loader.exec_module(module)
    return module


ANSWERS = {
    "cte": {
        "type": "choice",
        "choice": "shipping",
        "confidence": 0.91,
        "probabilities": {"shipping": 0.91, "receiving": 0.06, "unclear": 0.03},
    },
    "has_lot": {"type": "noul", "noul": 0.97},
    "risk": {
        "type": "score",
        "score": 0.4,
        "confidence": 0.8,
        "probabilities": {"0": 0.6, "1": 0.4, "2": 0.0},
        "legend": {"0": "low", "1": "medium", "2": "high"},
    },
}


def _transport(seen: dict, status: int = 200) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        seen.setdefault("bodies", []).append(body)
        seen.setdefault("requests", []).append(request)
        if status != 200:
            return httpx2.Response(status, text="down")
        answers = {qid: ANSWERS[qid] for qid in body["questions"]}
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_ask"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 40, "output_tokens": 3}},
        )

    return httpx2.MockTransport(handler)


ARGV = [
    "--state",
    '{"headers": ["Ship Dte", "Cust Name", "Lot No."]}',
    "--choice",
    "cte",
    "Which CTE do these headers record?",
    "shipping=outbound shipments",
    "receiving=inbound deliveries",
    "unclear",
    "--noul",
    "has_lot",
    "Do the headers include a lot code column?",
    "--score",
    "risk",
    "How likely is the file to be rejected as-is?",
    "low",
    "medium",
    "high",
]


def _run(script, capsys, argv, *, env=ENV, seen=None, status=200, **kwargs):
    seen = seen if seen is not None else {}
    with structlog.testing.capture_logs() as logs:
        code = script.main(argv, env=env, transport=_transport(seen, status), **kwargs)
    out, err = capsys.readouterr()
    return code, out, err, logs


def test_command_line_becomes_the_api_request(script, capsys):
    seen: dict = {}
    code, out, err, logs = _run(script, capsys, ARGV, seen=seen)

    assert code == 0, err
    (body,) = seen["bodies"]
    assert body["state"] == {"headers": ["Ship Dte", "Cust Name", "Lot No."]}
    questions = body["questions"]
    assert list(questions) == ["cte", "has_lot", "risk"]
    assert questions["cte"]["type"] == "choice"
    assert questions["cte"]["criteria"] == {
        "shipping": "outbound shipments",
        "receiving": "inbound deliveries",
        "unclear": None,
    }
    assert questions["has_lot"] == {"type": "noul", "instructions": "Do the headers include a lot code column?"}
    assert questions["risk"]["criteria"] == ["low", "medium", "high"]
    (request,) = seen["requests"]
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"


def test_text_answers_in_question_order_with_confidence(script, capsys):
    code, out, err, logs = _run(script, capsys, ARGV)

    assert code == 0, err
    lines = out.strip().splitlines()
    assert lines[0].startswith("Jev (jev-1.13.0, request req_ask, ")
    assert lines[1] == "  cte [choice]: shipping (confidence 0.91; shipping 0.91, receiving 0.06, unclear 0.03)"
    assert lines[2] == "  has_lot [noul]: yes (p(yes)=0.97)"
    assert lines[3] == "  risk [score]: 0.40 on 0..2 ~ low (confidence 0.80)"
    assert FAKE_KEY not in out + err + json.dumps(logs, default=str)


def test_json_output(script, capsys):
    code, out, _, _ = _run(script, capsys, [*ARGV, "--json"])

    assert code == 0
    report = json.loads(out)
    assert report["request_id"] == "req_ask"
    assert report["answers"]["cte"]["choice"] == "shipping"
    assert report["answers"]["has_lot"] == {"type": "noul", "probability_yes": 0.97}
    assert report["answers"]["risk"]["legend"] == {"0": "low", "1": "medium", "2": "high"}


def test_plain_text_state_and_stdin(script, capsys):
    seen: dict = {}
    argv = ["--state-file", "-", "--noul", "has_lot", "Is a lot code column present?"]
    code, _, err, _ = _run(script, capsys, argv, seen=seen, stdin=io.StringIO("Ship Dte, Cust Name, Lot No."))

    assert code == 0, err
    assert seen["bodies"][0]["state"] == "Ship Dte, Cust Name, Lot No."


def test_questions_file(script, capsys, tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"has_lot": {"type": "noul", "instructions": "Lot code column present?"}}))
    seen: dict = {}

    code, _, err, _ = _run(script, capsys, ["--state", "x", "--questions-file", str(path)], seen=seen)

    assert code == 0, err
    assert seen["bodies"][0]["questions"] == {"has_lot": {"type": "noul", "instructions": "Lot code column present?"}}


@pytest.mark.parametrize(
    "argv,message",
    [
        (["--state", "x"], "ask at least one question"),
        (["--state", "x", "--choice", "q", "Pick", "only"], "at least two OPTIONs"),
        (["--state", "x", "--choice", "q", "Pick", "a", "a"], "option names must be distinct"),
        (["--state", "x", "--noul", "q", "A?", "--noul", "q", "B?"], "duplicate question id"),
        (["--state", "x", "--score", "q", "How?", "one"], "2 to 10 LEVELs"),
        (["--noul", "q", "A?"], "one of the arguments --state --state-file is required"),
    ],
)
def test_usage_errors_send_nothing(script, capsys, argv, message):
    seen: dict = {}
    code, out, err, _ = _run(script, capsys, argv, seen=seen)

    assert code == 1
    assert message in err
    assert "bodies" not in seen


def test_without_a_key_nothing_is_sent(script, capsys):
    seen: dict = {}
    code, _, err, _ = _run(script, capsys, ARGV, env={}, seen=seen)

    assert code == 2
    assert "TYPESAFE_API_KEY is not set" in err
    assert "bodies" not in seen


def test_prompted_key_is_used_and_never_printed(script, capsys):
    seen: dict = {}
    code, out, err, logs = _run(
        script,
        capsys,
        [*ARGV, "--prompt-key"],
        env={"REGENGINE_JEV_MAX_RETRIES": "0"},
        seen=seen,
        read_key=lambda prompt: f"  {FAKE_KEY}\n",
    )

    assert code == 0, err
    assert seen["requests"][0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in out + err + json.dumps(logs, default=str)


def test_vendor_failure_exits_3(script, capsys):
    code, out, err, _ = _run(script, capsys, ARGV, status=503)

    assert code == 3
    assert "unavailable: server_error" in err
    assert out == ""


def test_missing_package_says_how_to_run_it():
    """Run by a Python without the repo's packages: exit 2 with the fix, not a traceback."""
    code = (
        "import runpy, sys\n"
        "sys.modules['typesafe_sdk'] = None\n"
        "sys.argv = ['jev_ask.py', '--state', 'x', '--noul', 'q', 'A?']\n"
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, **ENV},
        timeout=120,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert "typesafe_sdk is not installed. Nothing was sent." in result.stderr
    assert "venv/bin/python" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
