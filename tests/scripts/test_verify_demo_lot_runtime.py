from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.request import Request

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_demo_lot_runtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_demo_lot_runtime", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def scenario(**overrides):
    value = {
        "id": "demo-lot-0412-three-missing-ship-tos",
        "tenant_id": "system",
        "name": "DEMO-LOT-0412: Three missing ship-tos block packet score",
        "outcome": "Blocked shipping destinations",
        "records": "7 CTE records",
        "csv": "cte_type,traceability_lot_code\nshipping,DEMO-LOT-0412",
        "created_at": "2026-04-30T00:00:00+00:00",
        "built_in": True,
    }
    value.update(overrides)
    return value


def json_response(payload, *, status: int = 200) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"), status=status)


def opener_returning(response: FakeResponse, captured: list[Request] | None = None):
    def open_request(request: Request, *, timeout: float):
        assert timeout > 0
        if captured is not None:
            captured.append(request)
        return response

    return open_request


def credential_env(value: str = "unit-key") -> dict[str, str]:
    return {"REGENGINE_API_KEY": value}  # pragma: allowlist secret


def test_success_uses_get_and_emits_only_sanitized_evidence() -> None:
    credential = "sensitive-unit-key"
    captured: list[Request] = []
    evidence = mod.verify_runtime(
        env=credential_env(credential),
        open_request=opener_returning(
            json_response([scenario(), scenario(id="unrelated", csv="private-customer-csv")]),
            captured,
        ),
    )

    assert len(captured) == 1
    request = captured[0]
    assert request.get_method() == "GET"
    assert request.get_header("X-regengine-api-key") == credential
    assert evidence == {
        "endpoint": mod.DEFAULT_ENDPOINT,
        "scenario": {
            "built_in": True,
            "csv_contains_demo_lot": True,
            "id": "demo-lot-0412-three-missing-ship-tos",
            "records": "7 CTE records",
            "tenant_id": "system",
        },
        "status": "verified",
    }
    rendered = json.dumps(evidence)
    assert credential not in rendered
    assert "private-customer-csv" not in rendered
    assert "\"csv\"" not in rendered


def test_missing_environment_key_fails_before_network() -> None:
    called = False

    def open_request(_request: Request, *, timeout: float):
        nonlocal called
        called = True
        raise AssertionError(timeout)

    with pytest.raises(mod.VerificationError, match="REGENGINE_API_KEY is required"):
        mod.verify_runtime(env={}, open_request=open_request)

    assert called is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://regengine-production.up.railway.app/api/v1/inflow-workbench/scenarios",
        "https://example.com/api/v1/inflow-workbench/scenarios",
        "https://regengine-production.up.railway.app:444/api/v1/inflow-workbench/scenarios",
        "https://regengine-production.up.railway.app/api/v1/inflow-workbench/scenarios?tenant_id=other",
        "https://regengine-production.up.railway.app/api/v1/inflow-workbench/runs",
    ],
)
def test_unapproved_endpoint_fails_before_network(endpoint: str) -> None:
    called = False

    def open_request(_request: Request, *, timeout: float):
        nonlocal called
        called = True
        raise AssertionError(timeout)

    with pytest.raises(mod.VerificationError, match="approved production endpoint"):
        mod.verify_runtime(
            env=credential_env(),
            endpoint=endpoint,
            open_request=open_request,
        )

    assert called is False


def test_non_200_response_fails_without_body_disclosure() -> None:
    with pytest.raises(mod.VerificationError, match="HTTP 503") as exc_info:
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(
                FakeResponse(b'{"detail":"private-provider-error"}', status=503)
            ),
        )

    assert "private-provider-error" not in str(exc_info.value)


def test_malformed_json_fails_without_body_disclosure() -> None:
    with pytest.raises(mod.VerificationError, match="valid JSON") as exc_info:
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(FakeResponse(b"private-not-json")),
        )

    assert "private-not-json" not in str(exc_info.value)


@pytest.mark.parametrize("payload", [{}, {"scenarios": []}, None, "not-a-list"])
def test_non_array_payload_fails(payload) -> None:
    with pytest.raises(mod.VerificationError, match="JSON array"):
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(json_response(payload)),
        )


def test_missing_scenario_fails() -> None:
    with pytest.raises(mod.VerificationError, match="missing"):
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(json_response([scenario(id="other")])),
        )


def test_duplicate_scenario_fails() -> None:
    with pytest.raises(mod.VerificationError, match="duplicate"):
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(json_response([scenario(), scenario()])),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"tenant_id": "other"}, "tenant_id"),
        ({"built_in": False}, "built_in"),
        ({"built_in": 1}, "built_in"),
        ({"records": "6 CTE records"}, "records"),
        ({"csv": "cte_type,traceability_lot_code\nshipping,OTHER-LOT"}, "CSV marker"),
        ({"csv": None}, "CSV marker"),
    ],
)
def test_mismatched_scenario_fields_fail(overrides, message: str) -> None:
    with pytest.raises(mod.VerificationError, match=message):
        mod.verify_runtime(
            env=credential_env(),
            open_request=opener_returning(json_response([scenario(**overrides)])),
        )


def test_main_never_prints_api_key_or_full_csv(capsys: pytest.CaptureFixture[str]) -> None:
    credential = "sensitive-unit-key"
    exit_code = mod.main(
        [],
        env=credential_env(credential),
        open_request=opener_returning(json_response([scenario()])),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert credential not in captured.out + captured.err
    assert "cte_type,traceability_lot_code" not in captured.out + captured.err
    assert json.loads(captured.out)["scenario"]["csv_contains_demo_lot"] is True
