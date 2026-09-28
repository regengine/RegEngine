#!/usr/bin/env python3
"""Verify the DEMO-LOT-0412 built-in scenario through the production API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ENDPOINT = "https://regengine-production.up.railway.app/api/v1/inflow-workbench/scenarios"
EXPECTED_SCENARIO_ID = "demo-lot-0412-three-missing-ship-tos"
EXPECTED_TENANT_ID = "system"
EXPECTED_RECORDS = "7 CTE records"
EXPECTED_CSV_MARKER = "DEMO-LOT-0412"
REQUEST_TIMEOUT_SECONDS = 20.0

_APPROVED_HOST = "regengine-production.up.railway.app"
_APPROVED_PATH = "/api/v1/inflow-workbench/scenarios"


class VerificationError(RuntimeError):
    """A sanitized verification failure safe to print to an operator."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _default_open_request(request: Request, *, timeout: float):
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


def _validate_endpoint(endpoint: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise VerificationError("endpoint is not an approved production endpoint") from exc

    if (
        parsed.scheme != "https"
        or parsed.hostname != _APPROVED_HOST
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != _APPROVED_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise VerificationError("endpoint is not an approved production endpoint")


def _verified_scenario(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise VerificationError("response must be a JSON array")
    if any(not isinstance(item, dict) for item in payload):
        raise VerificationError("response JSON array must contain only objects")

    matches = [item for item in payload if item.get("id") == EXPECTED_SCENARIO_ID]
    if not matches:
        raise VerificationError("expected DEMO-LOT-0412 scenario is missing")
    if len(matches) != 1:
        raise VerificationError("expected DEMO-LOT-0412 scenario is duplicated")

    scenario = matches[0]
    if scenario.get("tenant_id") != EXPECTED_TENANT_ID:
        raise VerificationError("DEMO-LOT-0412 scenario tenant_id mismatch")
    if scenario.get("built_in") is not True:
        raise VerificationError("DEMO-LOT-0412 scenario built_in mismatch")
    if scenario.get("records") != EXPECTED_RECORDS:
        raise VerificationError("DEMO-LOT-0412 scenario records mismatch")
    csv_text = scenario.get("csv")
    if not isinstance(csv_text, str) or EXPECTED_CSV_MARKER not in csv_text:
        raise VerificationError("DEMO-LOT-0412 scenario CSV marker mismatch")

    return {
        "built_in": True,
        "csv_contains_demo_lot": True,
        "id": EXPECTED_SCENARIO_ID,
        "records": EXPECTED_RECORDS,
        "tenant_id": EXPECTED_TENANT_ID,
    }


def verify_runtime(
    *,
    env: Mapping[str, str],
    endpoint: str = DEFAULT_ENDPOINT,
    open_request: Callable[..., Any] = _default_open_request,
) -> dict[str, Any]:
    api_key = env.get("REGENGINE_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise VerificationError("REGENGINE_API_KEY is required")
    if any(not character.isprintable() for character in api_key):
        raise VerificationError("REGENGINE_API_KEY contains invalid characters")

    _validate_endpoint(endpoint)
    request = Request(
        endpoint,
        headers={"Accept": "application/json", "X-RegEngine-API-Key": api_key},
        method="GET",
    )

    try:
        with open_request(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise VerificationError(f"production scenarios endpoint returned HTTP {status}")
            body = response.read()
    except VerificationError:
        raise
    except HTTPError as exc:
        raise VerificationError(f"production scenarios endpoint returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, HTTPException):
        raise VerificationError("production scenarios endpoint request failed") from None

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerificationError("production scenarios response was not valid JSON") from exc

    return {
        "endpoint": endpoint,
        "scenario": _verified_scenario(payload),
        "status": "verified",
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    open_request: Callable[..., Any] = _default_open_request,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args(argv)

    try:
        evidence = verify_runtime(
            env=os.environ if env is None else env,
            endpoint=args.endpoint,
            open_request=open_request,
        )
    except VerificationError as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
