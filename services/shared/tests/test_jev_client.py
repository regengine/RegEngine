"""Offline tests for the TypeSafe "Jev" wrapper in ``services/shared/jev``.

Every test uses ``httpx2.MockTransport`` so nothing reaches the network. The
contract under test:

* disabled without ``TYPESAFE_API_KEY`` (or with the kill switch) and the
  caller learns that through ``JevUnavailable("disabled")``;
* the request on the wire carries ``state``, ``model`` and the questions
  exactly as the SDK serialises them;
* answers convert to plain, JSON-safe results with evidence attached;
* every SDK failure becomes ``JevUnavailable`` with a stable ``reason``;
* the state never appears in RegEngine's own log records, and a successful
  call leaves a stdlib ``jev_answered`` line (production drops structlog INFO
  without a sampled trace, so this is how an operator sees the key works);
* settings parse defensively and never raise on the request path.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx2
import pytest
import structlog
from shared.jev import (
    ConfidenceBand,
    ConfidenceThresholds,
    JevDecider,
    JevSettings,
    JevUnavailable,
    band_for_confidence,
    get_jev_decider,
    guard_sdk_logging,
    reset_jev_decider,
    settings as jev_settings,
)
from typesafe_sdk import Choice, Noul

STATE = {"source_header": "Lot #", "sample_values": ["A1", "B2"]}
QUESTIONS = {
    "field": Choice(instructions="Which canonical field?", criteria={"lot_code": None, "no_match": None}),
    "is_date": Noul(instructions="Is the column a date?"),
    "severity": {"type": "score", "instructions": "How severe?", "criteria": ["low", "medium", "high"]},
}
GOOD_BODY = {
    "model": "jev-1.14.0",
    "answers": {
        "field": {
            "type": "choice",
            "choice": "lot_code",
            "confidence": 0.93,
            "probabilities": {"lot_code": 0.93, "no_match": 0.07},
        },
        "is_date": {"type": "noul", "noul": 0.04},
        "severity": {
            "type": "score",
            "score": 1.4,
            "confidence": 0.41,
            "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5},
            "legend": {"0": "low", "1": "medium", "2": "high"},
        },
    },
    "usage": {"input_tokens": 57, "output_tokens": 3},
}


def _settings(**overrides) -> JevSettings:
    base = {"api_key": "test-key", "max_retries": 0, "timeout_seconds": 1.0}  # pragma: allowlist secret
    base.update(overrides)
    return JevSettings(**base)


def _decider(handler, **overrides) -> JevDecider:
    transport = httpx2.MockTransport(handler)
    return JevDecider(_settings(**overrides), transport=transport, async_transport=transport)


def _ok(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, headers={"x-typesafe-request-id": "req_abc"}, json=GOOD_BODY)


@pytest.fixture(autouse=True)
def _fresh_default_decider():
    reset_jev_decider()
    yield
    reset_jev_decider()


# ---------------------------------------------------------------------------
# Enablement
# ---------------------------------------------------------------------------


def test_disabled_without_api_key_raises_before_any_request():
    calls = []

    def handler(request):
        calls.append(request)
        return _ok(request)

    decider = _decider(handler, api_key=None)
    assert decider.enabled is False
    with pytest.raises(JevUnavailable) as excinfo:
        decider.ask(STATE, QUESTIONS, purpose="header_mapping")
    assert excinfo.value.reason == "disabled"
    assert excinfo.value.purpose == "header_mapping"
    assert calls == []


def test_kill_switch_disables_even_with_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "abc")
    monkeypatch.setenv("REGENGINE_JEV_ENABLED", "false")
    assert JevSettings.from_env().enabled is False
    monkeypatch.setenv("REGENGINE_JEV_ENABLED", "1")
    assert JevSettings.from_env().enabled is True


def test_default_decider_reads_environment(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert get_jev_decider().enabled is False
    reset_jev_decider()
    monkeypatch.setenv("TYPESAFE_API_KEY", "abc")
    assert get_jev_decider().enabled is True
    assert get_jev_decider() is get_jev_decider()


# ---------------------------------------------------------------------------
# Wire format and answer conversion
# ---------------------------------------------------------------------------


def test_request_carries_state_model_and_questions():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return _ok(request)

    _decider(handler, model="jev-1.14.0").ask(STATE, QUESTIONS, purpose="header_mapping")

    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["state"] == STATE
    assert seen["body"]["model"] == "jev-1.14.0"
    assert seen["body"]["questions"]["field"] == {
        "type": "choice",
        "instructions": "Which canonical field?",
        "criteria": {"lot_code": None, "no_match": None},
    }
    assert seen["body"]["questions"]["is_date"] == {"type": "noul", "instructions": "Is the column a date?"}
    assert seen["body"]["questions"]["severity"]["criteria"] == ["low", "medium", "high"]


def test_base_url_override_is_honoured():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return _ok(request)

    _decider(handler, base_url="https://gateway.example.test/typesafe/").ask("x", QUESTIONS, purpose="p")
    assert seen["url"] == "https://gateway.example.test/typesafe/v1/systemone"


def test_answers_convert_to_plain_results_with_evidence():
    answers = _decider(_ok).ask(STATE, QUESTIONS, purpose="header_mapping", questions_version="2")

    field = answers.choices["field"]
    assert field.choice == "lot_code"
    assert field.confidence == pytest.approx(0.93)
    assert field.probabilities == {"lot_code": pytest.approx(0.93), "no_match": pytest.approx(0.07)}
    assert answers.nouls["is_date"].probability == pytest.approx(0.04)
    severity = answers.scores["severity"]
    assert severity.score == pytest.approx(1.4)
    assert severity.probabilities == {0: pytest.approx(0.1), 1: pytest.approx(0.4), 2: pytest.approx(0.5)}
    assert severity.legend == {0: "low", 1: "medium", 2: "high"}

    evidence = answers.evidence
    assert evidence.provider == "typesafe"
    assert evidence.purpose == "header_mapping"
    assert evidence.questions_version == "2"
    assert evidence.requested_model == "jev-1.14.0"
    assert evidence.model == "jev-1.14.0"
    assert evidence.request_id == "req_abc"
    assert evidence.question_ids == ("field", "is_date", "severity")
    assert evidence.input_tokens == 57
    assert evidence.output_tokens == 3
    assert evidence.latency_ms >= 0
    assert evidence.sdk_version

    # Evidence and answers must round-trip through JSON for persistence.
    dumped = json.loads(json.dumps(answers.to_dict()))
    assert dumped["evidence"]["request_id"] == "req_abc"
    assert dumped["choices"]["field"]["choice"] == "lot_code"
    assert dumped["scores"]["severity"]["legend"] == {"0": "low", "1": "medium", "2": "high"}


def test_versioned_model_mismatch_is_unavailable():
    def handler(request):
        body = json.loads(json.dumps(GOOD_BODY))
        body["model"] = "jev-1.13.0"
        return httpx2.Response(200, json=body)

    with pytest.raises(JevUnavailable) as error:
        _decider(handler).ask(STATE, QUESTIONS, purpose="header_mapping")
    assert error.value.reason == "invalid_response"


def test_out_of_range_confidences_and_probabilities_are_clamped():
    body = json.loads(json.dumps(GOOD_BODY))
    body["answers"]["field"].update(confidence=1.0000001, probabilities={"lot_code": 1.2, "no_match": -0.2})
    body["answers"]["is_date"]["noul"] = 1.5
    body["answers"]["severity"]["confidence"] = -0.01

    answers = _decider(lambda request: httpx2.Response(200, json=body)).ask(STATE, QUESTIONS, purpose="p")

    assert answers.choices["field"].confidence == 1.0
    assert answers.choices["field"].probabilities == {"lot_code": 1.0, "no_match": 0.0}
    assert answers.nouls["is_date"].probability == 1.0
    assert answers.scores["severity"].confidence == 0.0


@pytest.mark.parametrize("value,expected", [(float("nan"), 0.0), (float("inf"), 0.0), (float("-inf"), 0.0), (0.5, 0.5)])
def test_non_finite_values_read_as_no_confidence(value, expected):
    from shared.jev.client import _unit

    assert _unit(value) == expected


def test_missing_request_id_header_is_tolerated():
    def handler(request):
        return httpx2.Response(200, json=GOOD_BODY)

    answers = _decider(handler).ask(STATE, QUESTIONS, purpose="p")
    assert answers.evidence.request_id is None


def test_async_twin_returns_same_shape():
    answers = asyncio.run(_decider(_ok).ask_async(STATE, QUESTIONS, purpose="header_mapping"))
    assert answers.choices["field"].choice == "lot_code"
    assert answers.evidence.request_id == "req_abc"


# ---------------------------------------------------------------------------
# Failure modes degrade to JevUnavailable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,body,reason",
    [
        (401, {"error": "invalid api key"}, "auth"),
        (403, {"error": "forbidden"}, "auth"),
        (400, {"error": "bad"}, "bad_request"),
        (422, {"detail": [{"loc": ["body", "questions"], "msg": "invalid"}]}, "bad_request"),
        (429, {"error": "slow down"}, "rate_limited"),
        (500, "boom", "server_error"),
        (503, "down", "server_error"),
        (529, "overloaded", "server_error"),
    ],
)
def test_http_errors_become_unavailable(status, body, reason):
    def handler(request):
        if isinstance(body, str):
            return httpx2.Response(status, text=body, headers={"x-typesafe-request-id": "req_err"})
        return httpx2.Response(status, json=body, headers={"x-typesafe-request-id": "req_err"})

    with pytest.raises(JevUnavailable) as excinfo:
        _decider(handler).ask(STATE, QUESTIONS, purpose="header_mapping")
    assert excinfo.value.reason == reason
    assert excinfo.value.status == status
    assert excinfo.value.request_id == "req_err"


def test_timeout_and_connection_errors_become_unavailable():
    def timeout(request):
        raise httpx2.ReadTimeout("slow")

    def refused(request):
        raise httpx2.ConnectError("refused")

    with pytest.raises(JevUnavailable) as excinfo:
        _decider(timeout).ask(STATE, QUESTIONS, purpose="p")
    assert excinfo.value.reason == "timeout"
    with pytest.raises(JevUnavailable) as excinfo:
        _decider(refused).ask(STATE, QUESTIONS, purpose="p")
    assert excinfo.value.reason == "connection"


def test_malformed_success_body_becomes_unavailable():
    def handler(request):
        return httpx2.Response(200, json={"model": "m", "answers": {"field": {"type": "choice", "choice": "x"}}})

    with pytest.raises(JevUnavailable) as excinfo:
        _decider(handler).ask(STATE, QUESTIONS, purpose="p")
    assert excinfo.value.reason == "invalid_response"


def test_retries_are_bounded_by_settings():
    attempts = []

    def handler(request):
        attempts.append(request.headers.get("x-typesafe-retry-count"))
        return httpx2.Response(503, text="down")

    with pytest.raises(JevUnavailable):
        _decider(handler, max_retries=2).ask(STATE, QUESTIONS, purpose="p")
    assert len(attempts) == 3


# ---------------------------------------------------------------------------
# Logging hygiene
# ---------------------------------------------------------------------------


def test_state_never_reaches_regengine_logs():
    secret_state = {"source_header": "Supplier Tax ID", "sample_values": ["SECRET-VALUE-9"]}

    def failing(request):
        return httpx2.Response(503, text="down")

    with structlog.testing.capture_logs() as records:
        _decider(_ok).ask(secret_state, QUESTIONS, purpose="header_mapping")
        with pytest.raises(JevUnavailable):
            _decider(failing).ask(secret_state, QUESTIONS, purpose="header_mapping")

    events = {record["event"] for record in records}
    assert "jev.answered" in events
    assert "jev.unavailable" in events
    assert "SECRET-VALUE-9" not in json.dumps(records, default=str)
    assert "Supplier Tax ID" not in json.dumps(records, default=str)


def test_answered_calls_leave_a_stdlib_line_that_production_keeps(caplog):
    """Production drops structlog INFO without a sampled trace; stdlib INFO passes.

    A working key must therefore leave a ``jev_answered`` stdlib line, with the
    request id to look up at TypeSafe and no state, header or key in it. A
    failed call must not leave one (its structlog warning is kept as it is).
    """
    secret_state = {"source_header": "Supplier Tax ID", "sample_values": ["SECRET-VALUE-9"]}

    def failing(request):
        return httpx2.Response(503, text="down")

    with caplog.at_level(logging.INFO, logger="jev"):
        _decider(_ok).ask(secret_state, QUESTIONS, purpose="header_mapping")
        with pytest.raises(JevUnavailable):
            _decider(failing).ask(secret_state, QUESTIONS, purpose="header_mapping")

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("jev_answered ")]
    assert len(lines) == 1
    (line,) = lines
    assert "purpose=header_mapping" in line
    assert "model=jev-1.14.0" in line
    assert "request_id=req_abc" in line
    assert "questions=3" in line
    assert "input_tokens=57 output_tokens=3" in line
    assert "SECRET-VALUE-9" not in caplog.text
    assert "Supplier Tax ID" not in caplog.text
    assert "test-key" not in caplog.text


def test_sdk_logger_is_capped_unless_operator_opted_in(monkeypatch):
    sdk_logger = logging.getLogger("typesafe_sdk")
    original = sdk_logger.level
    try:
        monkeypatch.delenv("TYPESAFE_LOG_LEVEL", raising=False)
        sdk_logger.setLevel(logging.DEBUG)
        guard_sdk_logging()
        assert sdk_logger.getEffectiveLevel() == logging.INFO

        monkeypatch.setenv("TYPESAFE_LOG_LEVEL", "debug")
        sdk_logger.setLevel(logging.DEBUG)
        guard_sdk_logging()
        assert sdk_logger.getEffectiveLevel() == logging.DEBUG
    finally:
        sdk_logger.setLevel(original)


# ---------------------------------------------------------------------------
# Settings and routing policy
# ---------------------------------------------------------------------------


def test_settings_defaults_pin_model_and_short_timeouts():
    settings = JevSettings.from_env({})
    assert settings.api_key is None
    assert settings.enabled is False
    assert settings.model == jev_settings.DEFAULT_MODEL == "jev-1.14.0"
    assert settings.timeout_seconds == 5.0
    assert settings.max_retries == 1
    assert settings.retry_budget_seconds == pytest.approx(11.0)
    assert settings.thresholds == ConfidenceThresholds(auto_apply=0.90, review=0.50)


def test_settings_parse_overrides_and_strip_whitespace():
    settings = JevSettings.from_env(
        {
            "TYPESAFE_API_KEY": "  key  ",
            "TYPESAFE_DEFAULT_MODEL": "jev-latest",
            "TYPESAFE_BASE_URL": "https://gw.example.test",
            "REGENGINE_JEV_TIMEOUT_SECONDS": "2.5",
            "REGENGINE_JEV_MAX_RETRIES": "3",
            "REGENGINE_JEV_AUTO_APPLY_CONFIDENCE": "0.95",
            "REGENGINE_JEV_REVIEW_CONFIDENCE": "0.6",
        }
    )
    assert settings.api_key == "key"  # pragma: allowlist secret
    assert settings.model == "jev-latest"
    assert settings.base_url == "https://gw.example.test"
    assert settings.timeout_seconds == 2.5
    assert settings.max_retries == 3
    assert settings.thresholds == ConfidenceThresholds(auto_apply=0.95, review=0.6)


def test_public_summary_says_whether_a_key_is_set_never_the_key():
    secret = "ts-summary-key-4c1d"  # pragma: allowlist secret
    summary = JevSettings.from_env(
        {"TYPESAFE_API_KEY": secret, "REGENGINE_JEV_APPLY_FILE_CTE_TYPE": "1"}
    ).public_summary()

    assert summary == {
        "enabled": True,
        "key_present": True,
        "kill_switch": False,
        "model": "jev-1.14.0",
        "apply_header_mappings": False,
        "apply_file_cte_type": True,
        "header_sample_values": 0,
    }
    assert secret not in repr(summary)
    off = JevSettings.from_env({"TYPESAFE_API_KEY": secret, "REGENGINE_JEV_ENABLED": "0"}).public_summary()
    assert off["enabled"] is False and off["key_present"] is True and off["kill_switch"] is True
    assert JevSettings.from_env({}).public_summary()["key_present"] is False


def test_settings_repr_never_contains_the_api_key():
    secret = "ts-live-SENTINEL-0123456789abcdef"  # pragma: allowlist secret
    settings = JevSettings.from_env({"TYPESAFE_API_KEY": secret})
    assert settings.enabled is True
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert "api_key" not in repr(settings)


@pytest.mark.parametrize(
    "env",
    [
        {"REGENGINE_JEV_TIMEOUT_SECONDS": "fast"},
        {"REGENGINE_JEV_TIMEOUT_SECONDS": "-1"},
        {"REGENGINE_JEV_MAX_RETRIES": "many"},
        {"REGENGINE_JEV_MAX_RETRIES": "99"},
        {"REGENGINE_JEV_AUTO_APPLY_CONFIDENCE": "1.5"},
        {"REGENGINE_JEV_AUTO_APPLY_CONFIDENCE": "0.3", "REGENGINE_JEV_REVIEW_CONFIDENCE": "0.6"},
    ],
)
def test_invalid_settings_fall_back_to_defaults_without_raising(env):
    settings = JevSettings.from_env({"TYPESAFE_API_KEY": "k", **env})
    assert settings.timeout_seconds == 5.0
    assert settings.max_retries == 1
    assert settings.thresholds == ConfidenceThresholds(auto_apply=0.90, review=0.50)


def test_confidence_bands_follow_thresholds():
    thresholds = ConfidenceThresholds(auto_apply=0.9, review=0.5)
    assert band_for_confidence(1.0, thresholds) is ConfidenceBand.AUTO_APPLY
    assert band_for_confidence(0.9, thresholds) is ConfidenceBand.AUTO_APPLY
    assert band_for_confidence(0.89, thresholds) is ConfidenceBand.REVIEW
    assert band_for_confidence(0.5, thresholds) is ConfidenceBand.REVIEW
    assert band_for_confidence(0.49, thresholds) is ConfidenceBand.REJECT
    assert band_for_confidence(0.0, thresholds) is ConfidenceBand.REJECT


def test_threshold_ordering_is_validated():
    with pytest.raises(ValueError):
        ConfidenceThresholds(auto_apply=0.4, review=0.6)
    with pytest.raises(ValueError):
        ConfidenceThresholds(auto_apply=1.2, review=0.5)
