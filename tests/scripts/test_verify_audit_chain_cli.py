"""The audit CLI must reject missing or misleading verification responses."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security/verify_audit_chain.sh"


def run_cli(tmp_path, payload, status="200"):
    response = tmp_path / "response.json"
    response.write_text(json.dumps(payload))
    curl = tmp_path / "curl"
    curl.write_text("""#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then shift; cp "$RESPONSE" "$1"; fi
  shift
done
printf '%s' "$STATUS"
""")
    curl.chmod(0o755)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "AUDIT_TOKEN": "synthetic-test-token",
            "RESPONSE": str(response),
            "STATUS": status,
        },
        capture_output=True,
        text=True,
    )


def valid_response():
    return {
        "integrity": {
            "chain_verification": {"valid": True, "total_entries": 2, "verified": 2, "errors": [], "first_break": None}
        }
    }


def test_explicit_complete_verification_passes(tmp_path):
    result = run_cli(tmp_path, valid_response())
    assert result.returncode == 0
    assert "Verified 2 / 2 entries" in result.stdout


@pytest.mark.parametrize(
    "payload", [{}, {"integrity": {}}, {"integrity": None}, {"integrity": {"chain_verification": None}}]
)
def test_missing_verification_fails(tmp_path, payload):
    result = run_cli(tmp_path, payload)
    assert result.returncode != 0
    assert "integrity verified" not in result.stdout


@pytest.mark.parametrize(
    "field,value",
    [
        ("valid", False),
        ("valid", "true"),
        ("verified", 1),
        ("verified", True),
        ("total_entries", 0),
        ("errors", [{"error": "private-detail"}]),
        ("first_break", 1),
    ],
)
def test_invalid_or_partial_verification_fails_without_private_details(tmp_path, field, value):
    payload = valid_response()
    payload["integrity"]["chain_verification"][field] = value
    result = run_cli(tmp_path, payload)
    assert result.returncode != 0
    assert "private-detail" not in result.stdout + result.stderr


def test_api_failure_does_not_dump_private_response(tmp_path):
    result = run_cli(tmp_path, {"detail": "private-customer-data"}, "403")
    assert result.returncode != 0
    assert "private-customer-data" not in result.stdout + result.stderr
