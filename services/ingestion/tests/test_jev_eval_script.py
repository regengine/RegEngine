"""``scripts/jev_eval.py``: score Jev on labelled RegEngine header rows.

Contract pinned here (offline, ``httpx2.MockTransport``; nothing reaches the
network):

* The shipped cases file is valid: every label is a real CTE or canonical
  field, every labelled header is one the route would ask about, and the
  seven templates are added with their own CTE.
* Both questions go through the route's own question sets; the file-CTE
  question is skipped where the route skips it (per-row CTE column).
* Scoring: accuracy over answers; per swept threshold, how many answers
  would be applied and how many of those are wrong; the recommendation is
  the lowest swept threshold at or above the artifact floor with no wrong
  applied answer.
* Only header rows leave the process, and the key is never printed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx2
import pytest
import structlog
from shared.jev.cte_classification import QUESTION_ID

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "jev_eval.py"
FAKE_KEY = "ts-eval-test-key-9d2b"  # pragma: allowlist secret
ENV = {"TYPESAFE_API_KEY": FAKE_KEY, "REGENGINE_JEV_MAX_RETRIES": "0"}


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("jev_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev_eval"] = module
    spec.loader.exec_module(module)
    return module


def _choice(choice: str, confidence: float) -> dict:
    return {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": {choice: confidence}}


def _oracle(script, cases, *, wrong: dict | None = None, confidence: float = 0.97, seen: dict | None = None):
    """Answer every question with its first acceptable label, except the ``wrong`` overrides.

    ``wrong`` maps ``(case_id, subject)`` to ``(answer, confidence)``.
    """
    wrong = wrong or {}
    cte_by_headers = {tuple(c.headers): c for c in cases}

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.setdefault("bodies", []).append(body)
        state = body["state"]
        case = cte_by_headers[tuple(state["csv_headers"])]
        answers = {}
        for question_id in body["questions"]:
            if question_id == QUESTION_ID:
                answer, conf = wrong.get((case.id, "(file)"), (sorted(case.cte)[0], confidence))
            else:
                header = state["columns_to_map"][int(question_id.split("_")[1])]["header"]
                expected = case.mappings.get(header)
                default = (sorted(expected)[0], confidence) if expected else ("no_match", 0.99)
                answer, conf = wrong.get((case.id, header), default)
            answers[question_id] = _choice(answer, conf)
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_eval"},
            json={"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 50, "output_tokens": 1}},
        )

    return httpx2.MockTransport(handler)


def _run(script, capsys, argv, *, env=ENV, transport=None):
    with structlog.testing.capture_logs() as logs:
        code = script.main(argv, env=env, transport=transport)
    out, err = capsys.readouterr()
    return code, out, err, logs


# ---------------------------------------------------------------------------
# The shipped cases file
# ---------------------------------------------------------------------------


def test_shipped_cases_are_valid_and_every_label_is_asked(script):
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)

    assert [c.id for c in cases[:7]] == [
        "template-harvesting",
        "template-cooling",
        "template-initial_packing",
        "template-shipping",
        "template-receiving",
        "template-transformation",
        "template-first_land_based_receiving",
    ]
    for case in cases[:7]:
        assert case.cte == frozenset({case.id.removeprefix("template-")})
    assert len(cases) >= 20
    assert sum(len(c.mappings) for c in cases) >= 80
    assert script.recognized_labels(cases) == []
    # Header rows only: a case carries no values.
    raw = json.loads(script.DEFAULT_CASES.read_text())
    assert all(set(case) <= {"id", "headers", "cte", "mappings"} for case in raw["cases"])


@pytest.mark.parametrize(
    "case,message",
    [
        ({"id": "a", "headers": ["X"], "cte": "growing"}, "unknown label(s) growing"),
        ({"id": "a", "headers": ["X"], "mappings": {"X": "lot"}}, "unknown label(s) lot"),
        ({"id": "a", "headers": ["X"], "mappings": {"Y": "quantity"}}, "headers not in the row: Y"),
        ({"id": "a", "headers": []}, "'headers' must be a non-empty list"),
        ({"headers": ["X"]}, "needs a string 'id'"),
    ],
)
def test_invalid_cases_are_a_usage_error_and_send_nothing(script, capsys, tmp_path, case, message):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [case]}))

    code, out, err, _ = _run(script, capsys, ["--cases", str(path), "--no-templates"])

    assert code == 1
    assert message in err
    assert out == ""


def test_duplicate_ids_are_rejected(script, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [{"id": "a", "headers": ["X"]}, {"id": "a", "headers": ["Y"]}]}))
    with pytest.raises(script._UsageError, match="duplicate id"):
        script.load_cases(path, templates=False)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_all_correct_run_recommends_the_floor_and_sends_headers_only(script, capsys):
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)
    seen: dict = {}

    code, out, err, logs = _run(script, capsys, ["--json"], transport=_oracle(script, cases, seen=seen))

    assert code == 0, err
    report = json.loads(out)
    assert report["cases"] == len(cases)
    for kind in ("file_cte", "header_mapping"):
        summary = report[kind]
        assert summary["accuracy"] == 1.0
        assert summary["wrong_at_current_threshold"] == []
        assert summary["recommended_auto_apply"] == 0.85
    # The per-row-events case has a CTE column: the file question is not asked for it.
    assert not any(a["case_id"] == "per-row-events" and a["kind"] == "file_cte" for a in report["answers"])
    # Every request carried a header row and nothing else from a file.
    for body in seen["bodies"]:
        assert set(body["state"]) <= {"csv_headers", "columns_to_map"}
        for column in body["state"].get("columns_to_map", []):
            assert "sample_values" not in column
    assert FAKE_KEY not in out + err + json.dumps(logs, default=str)


def test_a_confident_wrong_answer_raises_the_recommendation(script, capsys):
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)
    wrong = {
        ("dc-receiving-log", "(file)"): ("shipping", 0.93),
        ("erp-shipping-log", "Lot No."): ("reference_document", 0.96),
    }

    code, out, err, _ = _run(script, capsys, ["--json"], transport=_oracle(script, cases, wrong=wrong))

    assert code == 0, err
    report = json.loads(out)
    cte = report["file_cte"]
    assert cte["correct"] == cte["answered"] - 1
    # 0.93 is wrong and applied at 0.85 and 0.90, not at 0.95.
    rows = {row["threshold"]: row for row in cte["sweep"]}
    assert rows[0.9]["wrong"] == 1 and rows[0.95]["wrong"] == 0
    assert cte["recommended_auto_apply"] == 0.95
    assert cte["wrong_at_current_threshold"] == [
        {"case": "dc-receiving-log", "subject": "(file)", "answer": "shipping", "expected": ["receiving"]}
    ]
    mapping = report["header_mapping"]
    assert {row["threshold"]: row["wrong"] for row in mapping["sweep"]}[0.95] == 1
    # Every other applied mapping sits at 0.97, so only 0.98 excludes the wrong one, and
    # at 0.98 nothing is applied at all: no threshold is both safe and useful.
    assert {row["threshold"]: row["applied"] for row in mapping["sweep"]}[0.98] == 0
    assert mapping["recommended_auto_apply"] is None


def test_declining_is_never_an_applied_error(script, capsys):
    # mixed_or_unclear on a single-CTE file is wrong but applies nothing:
    # it lowers accuracy and coverage, never precision.
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)
    wrong = {("cooler-log", "(file)"): ("mixed_or_unclear", 0.99)}

    code, out, _, _ = _run(script, capsys, ["--json"], transport=_oracle(script, cases, wrong=wrong))

    report = json.loads(out)["file_cte"]
    assert report["correct"] == report["answered"] - 1
    assert all(row["wrong"] == 0 for row in report["sweep"])
    assert report["wrong_at_current_threshold"] == []


def test_text_report_names_the_wrong_answers(script, capsys):
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)
    wrong = {("fresh-cut-production", "(file)"): ("shipping", 0.99)}

    code, out, _, _ = _run(script, capsys, [], transport=_oracle(script, cases, wrong=wrong))

    assert code == 0
    assert "File CTE: " in out and "Header mapping: " in out
    assert "WRONG at current threshold: fresh-cut-production (file): shipping (expected transformation)" in out
    assert "recommended auto-apply threshold: none on this data (keep apply off)" in out


# ---------------------------------------------------------------------------
# Configuration and failures
# ---------------------------------------------------------------------------


def test_without_a_key_nothing_is_sent_and_it_exits_2(script, capsys):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(500)

    code, out, err, _ = _run(script, capsys, [], env={}, transport=httpx2.MockTransport(handler))

    assert code == 2
    assert calls == []
    assert "TYPESAFE_API_KEY is not set" in err


def test_prompted_key_is_used_and_never_printed(script, capsys):
    cases = script.load_cases(script.DEFAULT_CASES, templates=True)
    with structlog.testing.capture_logs() as logs:
        code = script.main(
            ["--prompt-key"],
            env={"REGENGINE_JEV_MAX_RETRIES": "0"},
            transport=_oracle(script, cases),
            read_key=lambda prompt: f" {FAKE_KEY}\n",
        )
    out, err = capsys.readouterr()
    assert code == 0, err
    assert FAKE_KEY not in out + err + json.dumps(logs, default=str)


def test_vendor_failure_exits_3(script, capsys):
    transport = httpx2.MockTransport(lambda request: httpx2.Response(503, text="down"))

    code, out, err, _ = _run(script, capsys, ["--json"], transport=transport)

    assert code == 3
    assert json.loads(out)["file_cte"]["answered"] == 0
    assert "some requests failed" in err
