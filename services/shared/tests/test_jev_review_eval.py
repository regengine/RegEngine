"""Offline safeguards for the capped, explicitly opted-in review evaluation."""

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("jev_review_eval", ROOT / "scripts" / "jev_review_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def case():
    return {
        "id": "synthetic-1",
        "mode": "mode_b",
        "cohort": "original_controls",
        "state": {},
        "expected": {"label": "insufficient"},
        "evidence_flags": {},
    }


def test_order_variant_preserves_state_and_membership_and_hides_labels():
    plan = ev.build_plan([case()])
    assert len(plan) == 4
    base, reordered = plan[:2]
    assert base["payload"]["state"] == reordered["payload"]["state"]
    assert set(base["payload"]["questions"]) == set(reordered["payload"]["questions"])
    options = base["payload"]["questions"]["q3_evidence_polarity"]["criteria"]
    reversed_options = reordered["payload"]["questions"]["q3_evidence_polarity"]["criteria"]
    assert list(options) == list(reversed(reversed_options))
    assert "expected" not in base["payload"]
    assert "evidence_flags" not in base["payload"]


def test_loaded_control_labels_and_evidence_flags_never_enter_serialized_state(tmp_path):
    original, heldout = tmp_path / "original.json", tmp_path / "heldout.json"
    original.write_text(
        json.dumps(
            [
                {
                    "id": "synthetic-source",
                    "retrieved": "2026-10-29",
                    "evidence_type": "synthetic",
                    "url": "https://example.invalid/source",
                    "evidence": "Synthetic source excerpt.",
                    "evidence_flags": {"trusted_only_marker": True},
                    "questions": [
                        {
                            "id": f"control-{index}",
                            "kind": "control",
                            "claim": f"Synthetic claim {index}.",
                            "pre_registered_expected": "contradicted",
                        }
                        for index in range(24)
                    ],
                }
            ]
        )
    )
    heldout.write_text("[]")
    cases = ev.load_cases(original, heldout)
    assert len(cases) == 24
    assert cases[0]["expected"] == {"label": "contradicted"}
    assert cases[0]["evidence_flags"] == {"authoritative_scope_verified": True}
    for item in ev.build_plan(cases):
        serialized = json.dumps(item["payload"]["state"])
        assert "Synthetic claim" in serialized
        assert "Synthetic source excerpt." in serialized
        for hidden in (
            "pre_registered_expected",
            "expected",
            "contradicted",
            "evidence_flags",
            "authoritative_scope_verified",
            "trusted_only_marker",
        ):
            assert hidden not in serialized


@pytest.fixture
def mock_response(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")
    calls = []

    def install(raw):
        class Transport:
            def open(self, request, **kwargs):
                calls.append(request.full_url)
                response = io.StringIO(json.dumps(raw))
                response.headers = {"x-typesafe-request-id": "synthetic-request"}
                return response

        monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: Transport())
        return calls

    return install


@pytest.mark.parametrize("failure", ["missing_answers", "wrong_model", "invalid_usage", "not_object", "scoring"])
def test_processing_failure_preserves_available_response_and_cannot_replay(
    failure, mock_response, monkeypatch, tmp_path
):
    plan = ev.build_plan([case()])[:1]
    raw = {
        "model": plan[0]["payload"]["model"],
        "answers": {},
        "usage": {"input_tokens": 100, "output_tokens": 10},
        "unrequested_field": "must-not-be-saved",
    }
    if failure == "missing_answers":
        del raw["answers"]
    elif failure == "wrong_model":
        raw["model"] = "wrong-model"
    elif failure == "invalid_usage":
        raw["usage"] = None
    elif failure == "not_object":
        raw = ["must-not-be-saved"]
    else:
        monkeypatch.setattr(ev, "validate_review_answers", lambda *args: None)

        def fail_scoring(*args):
            raise KeyError("must-not-be-saved")

        monkeypatch.setattr(ev, "score_result", fail_scoring)
    calls = mock_response(raw)
    with pytest.raises(RuntimeError, match="no retry"):
        ev.run(plan, tmp_path, 1)
    artifact = json.loads((tmp_path / (plan[0]["name"] + ".json")).read_text())
    assert artifact["response"] == (
        {key: raw[key] for key in ("model", "answers", "usage") if key in raw} if isinstance(raw, dict) else {}
    )
    assert artifact["processing_error"]
    assert artifact["request_id"] == "synthetic-request"
    assert "must-not-be-saved" not in json.dumps(artifact)
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["reserved_usd"] == ev.RESERVATION
    assert ledger["attempts"][0]["status"] == "processing_failed"
    assert ev.run(plan, tmp_path, 1) == ledger
    assert calls == [ev.ENDPOINT]


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("unsupported", {"label": "insufficient"}),
        ("mode_b", {}),
        ("mode_b", None),
        ("mode_b", {"label": "invented"}),
        ("mode_a", {}),
        ("mode_a", {"unknown_choice": "invented"}),
        ("mode_a", {"owner_choice": "invented"}),
    ],
)
def test_invalid_case_rejected_before_any_transport(mode, expected, monkeypatch, tmp_path):
    plan = ev.build_plan([case()])[:2]
    invalid = {**case(), "mode": mode, "expected": expected}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")
    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: pytest.fail("network constructed"))
    with pytest.raises(ValueError, match="case"):
        ev.build_plan([invalid])
    plan[-1]["case"] = invalid
    with pytest.raises(ValueError, match="case"):
        ev.run(plan, tmp_path, 1)
    assert not (tmp_path / "ledger.json").exists()


def test_contract_rejection_is_preserved_without_replay(mock_response, tmp_path):
    plan = ev.build_plan([case()])[:1]
    raw = {"model": plan[0]["payload"]["model"], "answers": {}, "usage": {"input_tokens": 100, "output_tokens": 10}}
    calls = mock_response(raw)
    ledger = ev.run(plan, tmp_path, 1)
    assert ledger["attempts"][0]["status"] == "contract_rejected"
    assert ledger["input_tokens"] == 100
    artifact = json.loads((tmp_path / (plan[0]["name"] + ".json")).read_text())
    assert artifact["response"] == raw
    assert artifact["processing_error"]
    assert ev.run(plan, tmp_path, 1) == ledger
    assert calls == [ev.ENDPOINT]


@pytest.mark.parametrize("mode", ["mode_a", "mode_b"])
def test_valid_response_is_scored_saved_and_not_replayed(mode, mock_response, tmp_path):
    fixture = {**case(), "mode": mode}
    if mode == "mode_a":
        fixture["expected"] = {"owner_choice": next(iter(ev.QUESTION_SETS[mode]["correction_owner_role"]["criteria"]))}
    plan = ev.build_plan([fixture])[:1]
    answers = {}
    for key, question in plan[0]["payload"]["questions"].items():
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 0}
        elif question["type"] == "choice":
            selected = next(iter(question["criteria"]))
            answers[key] = {
                "type": "choice",
                "choice": selected,
                "confidence": 1,
                "probabilities": {option: int(option == selected) for option in question["criteria"]},
            }
        else:
            answers[key] = {
                "type": "score",
                "score": 0,
                "confidence": 1,
                "probabilities": {str(i): int(i == 0) for i in range(len(question["criteria"]))},
                "legend": {str(i): value for i, value in enumerate(question["criteria"])},
            }
    raw = {
        "model": plan[0]["payload"]["model"],
        "answers": answers,
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }
    calls = mock_response(raw)
    ledger = ev.run(plan, tmp_path, 1)
    assert ledger["attempts"][0]["status"] == "complete"
    artifact = json.loads((tmp_path / (plan[0]["name"] + ".json")).read_text())
    assert artifact["response"] == raw
    assert artifact["matches"] and all(artifact["matches"].values())
    assert "processing_error" not in artifact
    assert ev.run(plan, tmp_path, 1) == ledger
    assert calls == [ev.ENDPOINT]


@pytest.mark.parametrize("identifier", ["../escape", "x/y", "", "a" * 81])
def test_rejects_unsafe_artifact_names(identifier):
    with pytest.raises(ValueError, match="identifier"):
        ev.build_plan([{**case(), "id": identifier}])


def test_missing_credential_sends_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: pytest.fail("network constructed"))
    with pytest.raises(RuntimeError, match="not configured"):
        ev.run(ev.build_plan([case()]), tmp_path, 1)


def test_budget_blocks_request_before_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")

    class NoNetwork:
        def open(self, *args, **kwargs):
            pytest.fail("Budget must stop the request")

    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: NoNetwork())
    with pytest.raises(RuntimeError, match="Budget exhausted"):
        ev.run(ev.build_plan([case()]), tmp_path, ev.RESERVATION / 2)


def test_timeout_retains_reservation_and_never_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-placeholder")
    calls = []

    class Timeout:
        def open(self, request, **kwargs):
            calls.append(request.full_url)
            raise TimeoutError()

    monkeypatch.setattr(ev.urllib.request, "build_opener", lambda *a: Timeout())
    plan = ev.build_plan([case()])
    with pytest.raises(RuntimeError, match="no retry"):
        ev.run(plan, tmp_path, 1)
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["reserved_usd"] == ev.RESERVATION
    assert ledger["attempts"][0]["status"] == "failed_or_ambiguous"
    with pytest.raises(RuntimeError, match="replay prohibited"):
        ev.run(plan, tmp_path, 1)
    assert calls == [ev.ENDPOINT]
    assert "test-placeholder" not in json.dumps(ledger)


def test_redirect_cannot_forward_authentication():
    with pytest.raises(RuntimeError, match="redirects"):
        ev.NoRedirect().redirect_request(None, None, 302, "", {}, "https://untrusted.invalid")
