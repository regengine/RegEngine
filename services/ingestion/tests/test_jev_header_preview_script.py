"""``scripts/jev_header_preview.py``: operator preview of Jev header-mapping suggestions.

Contract pinned here (all offline, ``httpx2.MockTransport`` like the other Jev
tests; nothing reaches the network):

* The script goes through the route's own helper
  (``_suggest_header_mappings_for_upload``), so it sends exactly what
  ``POST /api/v1/ingest/csv`` sends: the header row, only unrecognised
  columns as questions, the declared CTE name (``--cte-type``) only when no
  row can contradict it, redacted sample values only when asked, never rows.
* Output: a table (default) or JSON (``--json``) with column, suggested
  field, confidence, band, would-apply and blocked reason, plus model,
  request id and latency.
* Exit codes: 0 ok / no unrecognised headers (no request), 1 usage or file
  error (including a malformed header row, which is never sent), 2 not
  configured or switched off, 3 vendor unavailable.
* The API key never appears on stdout, stderr or in log events.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx2
import pytest
import structlog
from shared.jev.header_mapping import NO_MATCH

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "jev_header_preview.py"

FAKE_KEY = "ts-preview-test-key-7f3a9c"  # pragma: allowlist secret
BASE_ENV = {"TYPESAFE_API_KEY": FAKE_KEY, "REGENGINE_JEV_MAX_RETRIES": "0"}

# "Lot #" and "Notes" are not columns the parser knows; everything else is.
CSV_TEXT = (
    "Lot #,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document,Notes\n"
    "TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1,call 555-123-4567\n"
    "TLC-002,Chard,5,lbs,2026-04-17,Farm A,REF-2,\n"
)
CLEAN_CSV_TEXT = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document\n"
    "TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1\n"
)


def _choice(choice: str, confidence: float, **others: float) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence, **others},
    }


ANSWERS = {
    "Lot #": _choice("traceability_lot_code", 0.97, no_match=0.03),
    "Notes": _choice(NO_MATCH, 0.98, carrier=0.02),
}


def _load_script():
    spec = importlib.util.spec_from_file_location("jev_header_preview", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev_header_preview"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def _transport(seen: dict, status: int = 200) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.setdefault("requests", []).append(request)
        body = json.loads(request.content)
        seen.setdefault("bodies", []).append(body)
        if status != 200:
            return httpx2.Response(
                status, json={"error": "invalid api key"}, headers={"x-typesafe-request-id": "req_err"}
            )
        answered = {}
        for question_id in body["questions"]:
            index = int(question_id.split("_")[1])
            answered[question_id] = ANSWERS[body["state"]["columns_to_map"][index]["header"]]
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_preview"},
            json={"model": "jev-1.13.0", "answers": answered, "usage": {"input_tokens": 90, "output_tokens": 2}},
        )

    return httpx2.MockTransport(handler)


def _csv(tmp_path: Path, text: str = CSV_TEXT, name: str = "supplier.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(script, capsys, argv: list[str], *, env: dict, seen: Optional[dict] = None, status: int = 200, **kwargs):
    """Run ``main`` offline; returns (exit code, stdout, stderr, captured log events)."""
    seen = seen if seen is not None else {}
    with structlog.testing.capture_logs() as logs:
        code = script.main(argv, env=env, transport=_transport(seen, status), **kwargs)
    out, err = capsys.readouterr()
    return code, out, err, logs


def _assert_key_hidden(out: str, err: str, logs: list) -> None:
    assert FAKE_KEY not in out
    assert FAKE_KEY not in err
    assert FAKE_KEY not in json.dumps(logs, default=str)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_table_output_sends_only_the_header_row(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, logs = _run(script, capsys, [str(_csv(tmp_path))], env=BASE_ENV, seen=seen)

    assert code == 0, err
    # Exactly what the route sends: one request, the header row, unrecognised columns only, no rows.
    (body,) = seen["bodies"]
    assert body["state"]["csv_headers"] == CSV_TEXT.splitlines()[0].split(",")
    assert [c["header"] for c in body["state"]["columns_to_map"]] == ["Lot #", "Notes"]
    assert "file_cte_type" not in body["state"]
    assert all("sample_values" not in c for c in body["state"]["columns_to_map"])
    assert "TLC-001" not in json.dumps(body) and "555-123-4567" not in json.dumps(body)
    (request,) = seen["requests"]
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"

    assert "Status:  ok" in out
    assert "model jev-1.13.0 (requested jev-1.13.0), request id req_preview, latency" in out
    assert "apply to rows: off" in out
    header = next(line for line in out.splitlines() if line.startswith("column"))
    assert header.split() == ["column", "suggested_field", "confidence", "band", "would_apply", "blocked_reason"]
    lot_row = next(line for line in out.splitlines() if line.startswith("Lot #"))
    assert lot_row.split()[2:] == ["traceability_lot_code", "0.970", "auto_apply", "no", "apply_disabled"]
    notes_row = next(line for line in out.splitlines() if line.startswith("Notes"))
    assert "(no match)" in notes_row and notes_row.split()[-1] == "no_match"
    assert err == ""
    _assert_key_hidden(out, err, logs)


@pytest.mark.parametrize("simulate", [False, True])
def test_json_output_and_simulated_apply(script, capsys, tmp_path, simulate):
    argv = [str(_csv(tmp_path)), "--json"] + (["--simulate-apply"] if simulate else [])
    code, out, err, logs = _run(script, capsys, argv, env=BASE_ENV)

    assert code == 0, err
    report = json.loads(out)
    assert report["status"] == "ok" and report["exit_code"] == 0 and report["hint"] is None
    assert report["engine"]["model"] == "jev-1.13.0"
    assert report["engine"]["request_id"] == "req_preview"
    assert isinstance(report["engine"]["latency_ms"], int)
    assert report["engine"]["questions_version"] == "csv-header-mapping.v2"
    assert report["request"]["file_cte_type"] is None
    assert report["request"]["file_cte_type_dropped"] is None
    assert report["policy"] == {
        "auto_apply_confidence": 0.9,
        "review_confidence": 0.5,
        "apply_enabled": simulate,
        "simulated_apply": simulate,
    }
    assert report["request"]["unrecognized_headers"] == ["Lot #", "Notes"]
    assert report["request"]["rows_sent"] == 0
    suggestions = {s["source_header"]: s for s in report["suggestions"]}
    lot = suggestions["Lot #"]
    assert lot["canonical_field"] == "traceability_lot_code"
    assert lot["band"] == "auto_apply"
    assert lot["confidence"] == pytest.approx(0.97)
    # Same apply policy as the route: only the flag differs between the two runs.
    assert lot["would_apply"] is simulate
    assert lot["blocked_reason"] == (None if simulate else "apply_disabled")
    assert "applied" not in lot
    assert suggestions["Notes"]["canonical_field"] is None
    assert suggestions["Notes"]["would_apply"] is False
    assert suggestions["Notes"]["blocked_reason"] == "no_match"
    _assert_key_hidden(out, err, logs)


def test_current_apply_flag_is_honoured_without_simulation(script, capsys, tmp_path):
    env = {**BASE_ENV, "REGENGINE_JEV_APPLY_HEADER_MAPPINGS": "1"}
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path)), "--json"], env=env)

    assert code == 0, err
    report = json.loads(out)
    assert report["policy"]["apply_enabled"] is True and report["policy"]["simulated_apply"] is False
    assert {s["source_header"]: s["would_apply"] for s in report["suggestions"]} == {"Lot #": True, "Notes": False}


@pytest.mark.parametrize(
    "argv_extra,env_extra",
    [(["--sample-values", "2"], {}), ([], {"REGENGINE_JEV_HEADER_SAMPLE_VALUES": "2"})],
    ids=["flag", "env"],
)
def test_sample_values_are_opt_in_and_redacted_like_production(script, capsys, tmp_path, argv_extra, env_extra):
    seen: dict = {}
    argv = [str(_csv(tmp_path)), "--json", *argv_extra]
    code, out, err, _ = _run(script, capsys, argv, env={**BASE_ENV, **env_extra}, seen=seen)

    assert code == 0, err
    columns = {c["header"]: c for c in seen["bodies"][0]["state"]["columns_to_map"]}
    assert columns["Lot #"]["sample_values"] == ["TLC-001", "TLC-002"]
    assert columns["Notes"]["sample_values"] == ["call [PHONE_REDACTED]"]
    assert "555-123-4567" not in json.dumps(seen["bodies"][0])
    assert json.loads(out)["request"]["sample_values_per_column"] == 2


@pytest.mark.parametrize("declared", ["harvesting", "Harvest", " GROWING "])
def test_cte_type_is_normalised_like_the_route_and_sent_as_context(script, capsys, tmp_path, declared):
    seen: dict = {}
    code, out, err, logs = _run(
        script, capsys, [str(_csv(tmp_path)), "--json", "--cte-type", declared], env=BASE_ENV, seen=seen
    )

    assert code == 0, err
    (body,) = seen["bodies"]
    assert body["state"]["file_cte_type"] == "harvesting"
    report = json.loads(out)
    assert report["request"]["file_cte_type"] == "harvesting"
    assert report["request"]["file_cte_type_dropped"] is None
    assert report["engine"]["questions_version"] == "csv-header-mapping.v2"
    _assert_key_hidden(out, err, logs)


# The same upload with a per-row CTE column: rows can override --cte-type.
PER_ROW_CTE_CSV_TEXT = (
    "Event Type,Lot #,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document,Notes\n"
    "harvesting,TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1,\n"
)


def test_cte_type_is_withheld_when_the_file_has_a_per_row_cte_column(script, capsys, tmp_path):
    seen: dict = {}
    path = str(_csv(tmp_path, PER_ROW_CTE_CSV_TEXT))
    code, out, err, _ = _run(script, capsys, [path, "--json", "--cte-type", "harvesting"], env=BASE_ENV, seen=seen)

    assert code == 0, err
    (body,) = seen["bodies"]
    assert set(body["state"]) == {"csv_headers", "columns_to_map"}
    report = json.loads(out)
    assert report["request"]["unrecognized_headers"] == ["Lot #", "Notes"]
    assert report["request"]["file_cte_type"] is None
    assert report["request"]["file_cte_type_dropped"] == "file has a per-row CTE column: Event Type"

    code, out, err, _ = _run(script, capsys, [path, "--cte-type", "harvesting"], env=BASE_ENV)
    assert code == 0, err
    assert "CTE:     --cte-type not sent to Jev: file has a per-row CTE column: Event Type" in out
    assert "file_cte_type harvesting" not in out


def test_not_configured_still_says_a_cte_type_would_be_withheld(script, capsys, tmp_path):
    seen: dict = {}
    path = str(_csv(tmp_path, PER_ROW_CTE_CSV_TEXT))
    code, out, err, _ = _run(script, capsys, [path, "--json", "--cte-type", "harvesting"], env={}, seen=seen)

    assert code == 2
    assert "requests" not in seen
    report = json.loads(out)
    assert report["status"] == "disabled"
    assert report["request"]["file_cte_type"] is None  # nothing was sent
    assert report["request"]["file_cte_type_dropped"] == "file has a per-row CTE column: Event Type"

    code, out, err, _ = _run(script, capsys, [path, "--cte-type", "harvesting"], env={})
    assert code == 2
    assert "Sent:    nothing" in out
    assert "CTE:     --cte-type would be withheld from Jev: file has a per-row CTE column: Event Type" in out


def test_not_configured_also_reports_the_value_scan(script, capsys, tmp_path):
    # "Activity" is unrecognised, so only Jev could map it; its "receiving"
    # would still beat a declared harvesting, so the preview says so.
    text = CSV_TEXT.replace("Notes\n", "Activity\n", 1).replace("call 555-123-4567", "receiving", 1)
    path = str(_csv(tmp_path, text))
    code, out, err, _ = _run(script, capsys, [path, "--json", "--cte-type", "harvesting"], env={})

    assert code == 2
    report = json.loads(out)
    assert report["request"]["file_cte_type"] is None
    assert report["request"]["file_cte_type_dropped"] == "column Activity holds per-row CTE values"


@pytest.mark.parametrize(
    "text,argv_extra",
    [(CSV_TEXT, ["--cte-type", "harvesting"]), (PER_ROW_CTE_CSV_TEXT, [])],
    ids=["no-per-row-column", "nothing-declared"],
)
def test_not_configured_reports_no_drop_when_nothing_would_be_withheld(script, capsys, tmp_path, text, argv_extra):
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path, text)), "--json", *argv_extra], env={})

    assert code == 2
    report = json.loads(out)
    assert report["request"]["file_cte_type"] is None
    assert report["request"]["file_cte_type_dropped"] is None


def test_empty_cte_type_means_not_declared_like_the_route(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path)), "--json", "--cte-type", ""], env=BASE_ENV, seen=seen)

    assert code == 0, err
    assert "file_cte_type" not in seen["bodies"][0]["state"]
    report = json.loads(out)
    assert report["request"]["file_cte_type"] is None
    assert report["request"]["file_cte_type_dropped"] is None


def test_cte_type_appears_on_the_sent_line_of_the_table(script, capsys, tmp_path):
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path)), "--cte-type", "harvesting"], env=BASE_ENV)

    assert code == 0, err
    assert "Sent:    header row; file_cte_type harvesting; 0 redacted sample value(s)" in out


def test_unknown_cte_type_is_a_usage_error_and_sends_nothing(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, _ = _run(
        script, capsys, [str(_csv(tmp_path)), "--cte-type", "teleporting"], env=BASE_ENV, seen=seen
    )

    # Exit 1 like every other bad argument; 2 means "not configured" in this script.
    assert code == 1
    assert out == ""
    assert "requests" not in seen
    assert err.startswith("jev_header_preview: error: argument --cte-type: unknown CTE type 'teleporting'; valid: ")
    assert "shipping" in err and "first_land_based_receiving" in err


def test_no_unrecognized_headers_makes_no_request(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path, CLEAN_CSV_TEXT))], env=BASE_ENV, seen=seen)

    assert code == 0, err
    assert "requests" not in seen
    assert "Status:  no_unrecognized_headers" in out
    assert "Sent:    nothing" in out


# ---------------------------------------------------------------------------
# Not configured / unavailable
# ---------------------------------------------------------------------------


def test_not_configured_exits_2_and_sends_nothing(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path))], env={}, seen=seen)

    assert code == 2
    assert "requests" not in seen
    assert "Status:  disabled" in out
    assert "Unrecognised: Lot #, Notes" in out
    assert "TYPESAFE_API_KEY is not set" in err


def test_kill_switch_exits_2_without_printing_the_key(script, capsys, tmp_path):
    seen: dict = {}
    env = {**BASE_ENV, "REGENGINE_JEV_ENABLED": "0"}
    code, out, err, logs = _run(script, capsys, [str(_csv(tmp_path)), "--json"], env=env, seen=seen)

    assert code == 2
    assert "requests" not in seen
    assert json.loads(out)["status"] == "disabled"
    assert "REGENGINE_JEV_ENABLED" in err
    _assert_key_hidden(out, err, logs)


def test_vendor_401_exits_3_with_status_and_hint(script, capsys, tmp_path):
    seen: dict = {}
    code, out, err, logs = _run(script, capsys, [str(_csv(tmp_path))], env=BASE_ENV, seen=seen, status=401)

    assert code == 3
    assert len(seen["requests"]) == 1
    assert "Status:  unavailable:auth" in out
    (summary,) = err.strip().splitlines()
    assert summary.startswith("jev_header_preview: unavailable:auth: ")
    assert "TYPESAFE_API_KEY" in summary
    assert any(log["event"] == "jev.unavailable" and log["reason"] == "auth" for log in logs)
    _assert_key_hidden(out, err, logs)


@pytest.mark.parametrize("status,reason", [(429, "rate_limited"), (503, "server_error")])
def test_other_vendor_failures_exit_3(script, capsys, tmp_path, status, reason):
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path)), "--json"], env=BASE_ENV, status=status)

    assert code == 3
    assert json.loads(out)["status"] == f"unavailable:{reason}"
    assert f"unavailable:{reason}" in err


# ---------------------------------------------------------------------------
# Hidden key prompt
# ---------------------------------------------------------------------------


def test_prompt_key_uses_the_entered_key_for_this_run_only(script, capsys, tmp_path):
    seen: dict = {}
    prompts: list[str] = []

    def read_key(prompt: str) -> str:
        prompts.append(prompt)
        return f"  {FAKE_KEY}\n"

    env = {"REGENGINE_JEV_MAX_RETRIES": "0"}
    code, out, err, logs = _run(
        script, capsys, [str(_csv(tmp_path)), "--prompt-key"], env=env, seen=seen, read_key=read_key
    )

    assert code == 0, err
    assert prompts == [script.KEY_PROMPT]
    assert seen["requests"][0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert "TYPESAFE_API_KEY" not in env
    _assert_key_hidden(out, err, logs)


def test_prompt_key_with_nothing_entered_exits_2(script, capsys, tmp_path):
    code, out, err, _ = _run(
        script, capsys, [str(_csv(tmp_path)), "--prompt-key"], env={}, read_key=lambda prompt: "   "
    )

    assert code == 2
    assert "No key was entered" in err


# ---------------------------------------------------------------------------
# Usage and file errors
# ---------------------------------------------------------------------------


def test_usage_and_file_errors_exit_1(script, capsys, tmp_path):
    good = str(_csv(tmp_path))
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    latin1 = tmp_path / "latin1.csv"
    latin1.write_bytes("Lot #,Produit\nTLC-1,Br\xfbl\xe9e\n".encode("latin-1"))
    cases = [
        [str(tmp_path / "missing.csv")],
        [str(tmp_path)],
        [str(empty)],
        [str(latin1)],
        [good, "--sample-values", "9"],
        [good, "--sample-values", "x"],
        [good, "--cte-type", "bogus"],
        [good, "--cte-type", "  "],  # the route rejects a blank-but-not-empty form field too
        [good, "--cte-type"],
        [good, "--unknown-flag"],
        [],
    ]
    for argv in cases:
        seen: dict = {}
        code, out, err, _ = _run(script, capsys, argv, env=BASE_ENV, seen=seen)
        assert code == 1, argv
        assert out == "", argv
        assert err.startswith("jev_header_preview: error: "), argv
        assert "requests" not in seen, argv


# The review's reproduction: an unterminated quote makes the reader take the
# rest of the file, PII included, as a single "header".
OPEN_QUOTE_CSV_TEXT = '"Lot #,product_description,Notes\nTLC-1,Kale,call 555-123-4567 jane@example.com\nTLC-2,Chard,x\n'


@pytest.mark.parametrize("env", [BASE_ENV, {}], ids=["configured", "not-configured"])
def test_unterminated_quote_header_is_never_sent_or_called_no_rows(script, capsys, tmp_path, env):
    path = str(_csv(tmp_path, OPEN_QUOTE_CSV_TEXT))
    argv = [path, "--json", "--sample-values", "2", "--cte-type", "harvesting"]
    seen: dict = {}
    code, out, err, logs = _run(script, capsys, argv, env=env, seen=seen)

    assert "requests" not in seen  # zero requests reached the transport
    assert code == 1
    report = json.loads(out)
    assert report["status"] == "malformed_header" and report["exit_code"] == 1
    assert report["request"]["malformed_header_reason"] == "the header row spans 3 lines"
    assert report["request"]["unrecognized_headers"] == []
    assert report["request"]["file_cte_type"] is None and report["request"]["file_cte_type_dropped"] is None
    assert report["suggestions"] == []
    assert err.startswith(
        "jev_header_preview: malformed_header: The header row is malformed (the header row spans 3 lines)"
    )
    for text in (out, err, json.dumps(logs, default=str)):
        assert "555-123-4567" not in text and "jane@example.com" not in text

    code, out, err, _ = _run(script, capsys, [path], env=env, seen=seen)
    assert code == 1
    assert "requests" not in seen
    assert "Columns: the header row is malformed: the header row spans 3 lines" in out
    assert "Sent:    nothing" in out
    assert "no rows" not in out  # never claim rows were withheld from a request that did not happen
    assert "555-123-4567" not in out + err


def test_over_long_header_is_never_sent(script, capsys, tmp_path):
    text = CSV_TEXT.replace("Notes\n", "Notes " + "x" * 200 + "\n", 1)
    seen: dict = {}
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path, text)), "--json"], env=BASE_ENV, seen=seen)

    assert "requests" not in seen
    assert code == 1
    report = json.loads(out)
    assert report["status"] == "malformed_header"
    assert report["request"]["malformed_header_reason"] == "a header is 206 characters long (limit 128)"


def test_oversized_file_is_rejected_like_the_route(script, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "MAX_CSV_FILE_SIZE_BYTES", 10)
    code, out, err, _ = _run(script, capsys, [str(_csv(tmp_path))], env=BASE_ENV)

    assert code == 1
    assert "exceeds the upload limit" in err


# ---------------------------------------------------------------------------
# Runs from the repo root as a plain script
# ---------------------------------------------------------------------------


def test_script_runs_from_repo_root_without_pythonpath(tmp_path):
    env = {
        name: value
        for name, value in os.environ.items()
        if name != "PYTHONPATH" and not name.startswith(("TYPESAFE_", "REGENGINE_JEV_"))
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(_csv(tmp_path)), "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 2, result.stderr
    # stdout is the JSON document only: import-time and wrapper logs go to stderr.
    report = json.loads(result.stdout)
    assert report["status"] == "disabled"
    assert report["request"]["unrecognized_headers"] == ["Lot #", "Notes"]
    assert "jev_header_preview: disabled: TYPESAFE_API_KEY is not set" in result.stderr


def _subprocess_env(**extra: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if name != "PYTHONPATH" and not name.startswith(("TYPESAFE_", "REGENGINE_JEV_"))
    }
    env.update(extra)
    return env


def test_unexpected_error_never_prints_the_key_and_keeps_stdout_json(tmp_path):
    """A malformed base URL raises a non-SDK exception inside the Jev call.

    The wrapper logs it with a traceback. The CLI's renderer must print a plain
    traceback without frame locals: the frames hold the settings object and the
    request, so a locals-printing renderer would put the key on stderr.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(_csv(tmp_path)), "--json"],
        cwd=ROOT,
        env=_subprocess_env(
            TYPESAFE_API_KEY=FAKE_KEY,
            TYPESAFE_BASE_URL="https://api.example.com:abc",
            REGENGINE_JEV_MAX_RETRIES="0",
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert FAKE_KEY not in result.stdout
    assert FAKE_KEY not in result.stderr
    assert "jev.header_mapping.error" in result.stderr


def test_connection_failure_logs_to_stderr_and_exits_3(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(_csv(tmp_path)), "--json"],
        cwd=ROOT,
        env=_subprocess_env(
            TYPESAFE_API_KEY=FAKE_KEY,
            TYPESAFE_BASE_URL="http://127.0.0.1:1",
            REGENGINE_JEV_MAX_RETRIES="0",
            REGENGINE_JEV_TIMEOUT_SECONDS="2",
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 3, result.stderr
    # The wrapper's warning goes to stderr; stdout is the JSON document only.
    report = json.loads(result.stdout)
    assert report["status"] == "unavailable:connection"
    assert "jev.unavailable" in result.stderr
    assert FAKE_KEY not in result.stdout + result.stderr


def test_unparseable_base_url_host_does_not_break_the_report(script):
    assert script._host("http://[::1") is None
    assert script._host("https://gw.example.test:8443/v1") == "gw.example.test"
    assert script._host(None) is None
