"""Tests for ``AuditExportRequest`` reviewer-hint hardening (#1125).

Issue #1125 flagged that the reviewer token coming off an audit-export
request was being trusted as the authoritative reviewer identity for
attestation logging. The authoritative identity is now derived from
the authenticated principal, and the ``reviewer`` field on the request
body is only a *hint* — auditors may annotate who they intend the
reviewer to be, but it never feeds the sign-off record directly.

Because the hint may still be rendered in admin UIs or used as a
graph node key, it is validated against a narrow character class so a
malicious payload (HTML, CRLF, quote, control characters) can't land
even if a future handler accidentally echoes it back.

These tests verify:

* Happy path values pass.
* Long values past ``max_length`` are rejected.
* HTML / XSS payloads are rejected.
* CRLF / control-character payloads are rejected.
* Short values below ``min_length`` are rejected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
for key in list(sys.modules):
    if key == "app" or key.startswith("app.") or key == "main":
        del sys.modules[key]
sys.path.insert(0, str(service_dir))

from pydantic import ValidationError

from app.models import AuditExportRequest


BASE_OK = {"model_id": "risk-model-v1", "output_type": "regulator_examination_package"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reviewer",
    [
        "Jane Doe",
        "Dr. A. Smith",
        "reviewer_01",
        "Jane O'Neill",
        "reviewer@example.com",
        "Ada, Lovelace",
        "A-B_C.D 01",
    ],
)
def test_reviewer_accepts_well_formed_values(reviewer: str) -> None:
    model = AuditExportRequest(**BASE_OK, reviewer=reviewer)
    assert model.reviewer == reviewer


# ---------------------------------------------------------------------------
# Rejection surface — HTML / XSS / formula injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reviewer",
    [
        "<script>alert(1)</script>",
        "Jane<script>",
        'Jane"</script><script>alert(1)</script>',
        "Jane & Mallory",  # ampersand is not in the whitelist
        "=WEBSERVICE(\"http://evil/\")",  # CSV formula vector
        "+CMD()",
        "Jane|Mallory",  # shell-pipe
        "Jane;DROP TABLE users",
    ],
)
def test_reviewer_rejects_injection_payloads(reviewer: str) -> None:
    # ``@`` is intentionally allowed so email-shaped reviewer hints
    # round-trip; the CSV formula defence for ``@`` lives at the
    # :func:`safe_cell` boundary, not at input validation.
    with pytest.raises(ValidationError) as exc_info:
        AuditExportRequest(**BASE_OK, reviewer=reviewer)
    assert "reviewer" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Rejection surface — control characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reviewer",
    [
        "Jane\r\nSet-Cookie: x=1",
        "Jane\nRole: admin",
        "Jane\t",
        "Jane\x00Mallory",
        "Jane\x07",
    ],
)
def test_reviewer_rejects_control_characters(reviewer: str) -> None:
    with pytest.raises(ValidationError):
        AuditExportRequest(**BASE_OK, reviewer=reviewer)


# ---------------------------------------------------------------------------
# Rejection surface — length bounds
# ---------------------------------------------------------------------------


def test_reviewer_rejects_too_short() -> None:
    with pytest.raises(ValidationError):
        AuditExportRequest(**BASE_OK, reviewer="J")


def test_reviewer_rejects_too_long() -> None:
    # ``max_length=120`` per model — 121 A's exceeds the Pydantic
    # constraint before the regex validator even runs.
    with pytest.raises(ValidationError):
        AuditExportRequest(**BASE_OK, reviewer="A" * 121)


def test_reviewer_exactly_at_max_length_passes() -> None:
    value = "A" * 120
    model = AuditExportRequest(**BASE_OK, reviewer=value)
    assert model.reviewer == value


# ---------------------------------------------------------------------------
# Ensure the error message does not echo the payload back into the
# response body (no reflection).
# ---------------------------------------------------------------------------


def test_reviewer_error_does_not_echo_payload() -> None:
    payload = "<script>alert('pwn')</script>"
    with pytest.raises(ValidationError) as exc_info:
        AuditExportRequest(**BASE_OK, reviewer=payload)
    # Pydantic includes the input in ``input`` field by default, but
    # the *message* text we author must not do its own echo.
    message = "\n".join(
        err.get("msg", "") for err in exc_info.value.errors()
    )
    assert "<script>" not in message
    assert "alert" not in message
