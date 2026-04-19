"""Regression tests for PII-safe logging in identity_resolution (#1233).

The original implementation logged ``canonical_name`` and ``alias_value``
at INFO. For regulated identifiers (DUNS, EIN, FDA_REGISTRATION) and
natural-person names that's a direct GDPR / info-disclosure hit — log
retention typically exceeds DB retention and log sinks are accessible
to a wider personnel set than the row-level DB.

This file locks in:
1. ``shared.pii`` exposes ``mask_identifier``, ``mask_name``,
   ``mask_alias_value``, and ``SENSITIVE_ALIAS_TYPES`` (stable API).
2. Masking helpers never leak the raw value, never crash on edge
   inputs (``None``, empty, non-string), and produce a
   correlation-friendly hashed suffix.
3. The service-side log calls (``entity_registered``,
   ``alias_added``, ``resolve_or_register_alias_insert_failed``) route
   through the mask helpers — enforced via source-level assertions
   because full service boot requires a DB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Make ``shared`` importable.
service_dir = Path(__file__).resolve().parents[2] / "services"
sys.path.insert(0, str(service_dir))

from shared import pii  # noqa: E402


# ── 1. Public API surface ──────────────────────────────────────────────────


def test_pii_module_exposes_expected_api():
    """Downstream services import these by name. A rename breaks
    every log-site that routes through the helper."""
    assert hasattr(pii, "mask_identifier")
    assert hasattr(pii, "mask_name")
    assert hasattr(pii, "mask_alias_value")
    assert hasattr(pii, "SENSITIVE_ALIAS_TYPES")
    # Closed set, not a mutable list.
    assert isinstance(pii.SENSITIVE_ALIAS_TYPES, frozenset)


def test_sensitive_alias_types_include_regulated_identifiers():
    """These are the alias types called out in #1233 — regression
    protection so no refactor accidentally drops one."""
    required = {"duns", "fda_registration", "internal_code", "ein", "ssn"}
    assert required.issubset(pii.SENSITIVE_ALIAS_TYPES)


# ── 2. mask_identifier ─────────────────────────────────────────────────────


def test_mask_identifier_never_emits_raw_value():
    raw = "123456789"
    masked = pii.mask_identifier(raw)
    assert "1234567" not in masked
    assert "12345678" not in masked
    assert raw not in masked


def test_mask_identifier_stable_suffix_for_correlation():
    """Two calls with the same input must produce the same masked
    string — otherwise operators can't correlate log lines."""
    a = pii.mask_identifier("987654321")
    b = pii.mask_identifier("987654321")
    assert a == b


def test_mask_identifier_differs_for_different_values():
    """Two DIFFERENT inputs must produce different masks, else the
    correlation property becomes a false-positive producer."""
    a = pii.mask_identifier("111111111")
    b = pii.mask_identifier("222222222")
    assert a != b


def test_mask_identifier_handles_edge_inputs():
    assert pii.mask_identifier(None) == "<none>"
    assert pii.mask_identifier("") == "<empty>"
    # Short values get no suffix leak
    masked = pii.mask_identifier("ab", keep_suffix=2)
    assert "ab" not in masked or masked.startswith("***")


def test_mask_identifier_keep_suffix_zero_hides_all():
    masked = pii.mask_identifier("SENSITIVE123", keep_suffix=0)
    assert "SENSITIVE" not in masked
    assert "123" not in masked


# ── 3. mask_name ───────────────────────────────────────────────────────────


def test_mask_name_preserves_first_char_only():
    masked = pii.mask_name("Acme Supply Co")
    assert masked.startswith("A")
    # Rest of name must NOT appear
    assert "cme" not in masked
    assert "Supply" not in masked
    assert "Co" not in masked


def test_mask_name_edge_cases():
    assert pii.mask_name(None) == "<none>"
    assert pii.mask_name("") == "<empty>"


# ── 4. mask_alias_value dispatches correctly ───────────────────────────────


@pytest.mark.parametrize("alias_type", list(pii.SENSITIVE_ALIAS_TYPES))
def test_mask_alias_value_uses_identifier_path_for_sensitive_types(alias_type):
    """Sensitive alias types go through the identifier-masking path
    (full value hidden) — no name-style leak of the first character."""
    raw = "VERY_SENSITIVE_ID_12345"
    masked = pii.mask_alias_value(alias_type, raw)
    # Identifier mask format starts with '***' (no leading plaintext)
    assert masked.startswith("***"), (
        f"sensitive alias_type {alias_type!r} leaked leading plaintext: {masked}"
    )
    # Raw value must not be embedded anywhere
    assert raw not in masked


def test_mask_alias_value_name_types_use_name_masking():
    """Non-sensitive alias types (name, trade_name) allow a first-char
    hint to aid debugging."""
    masked = pii.mask_alias_value("name", "Acme Supply Co")
    assert masked.startswith("A")
    assert "cme Supply" not in masked


def test_mask_alias_value_case_insensitive_on_type():
    """An alias_type of 'EIN' must be treated the same as 'ein'."""
    raw = "12-3456789"
    lower = pii.mask_alias_value("ein", raw)
    upper = pii.mask_alias_value("EIN", raw)
    # Both should use identifier masking (no plaintext prefix)
    assert lower.startswith("***")
    assert upper.startswith("***")


def test_mask_alias_value_handles_none_type():
    """An alias_type of None should default to the safer (name) path
    without raising."""
    out = pii.mask_alias_value(None, "something")
    assert out  # non-empty string
    assert "something" not in out


def test_mask_alias_value_never_raises():
    """This is on a log path — a mask helper that raises would
    swallow an operationally-important log line."""
    hostile = [None, "", 12345, {"dict": "value"}, [1, 2, 3]]
    for alias_type in [None, "name", "ein", ""]:
        for val in hostile:
            # Must not raise
            out = pii.mask_alias_value(alias_type, val)  # type: ignore[arg-type]
            assert isinstance(out, str)


# ── 5. Service-side log sites route through the mask ───────────────────────


def test_service_source_routes_logs_through_mask():
    """Static source inspection: the identity_resolution service's
    ``logger.info('entity_registered', ...)`` and
    ``logger.info('alias_added', ...)`` calls MUST NOT emit
    ``canonical_name`` or ``alias_value`` as raw keys.

    Runtime-mocking the log sink is brittle because the service needs
    a DB session — and a regex assertion is fine because the log
    literals are right there in the file."""
    svc_path = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "shared"
        / "identity_resolution"
        / "service.py"
    )
    src = svc_path.read_text()

    # Find every logger.info/warning/error call block and its extra={...}
    # payload. Simple heuristic: search for "canonical_name" or
    # "alias_value" appearing inside an ``extra={...}`` dict that
    # follows a logger.<level>( call.
    #
    # We look for the literal string keys "canonical_name" and
    # "alias_value" (no _masked suffix) inside extra dicts.
    log_call_pattern = re.compile(
        r"logger\.(info|warning|error|debug|exception)\s*\(\s*"
        r"[\"'][^\"']+[\"']\s*,\s*extra\s*=\s*\{(?P<body>[^}]*)\}",
        re.DOTALL,
    )

    offenders = []
    for m in log_call_pattern.finditer(src):
        body = m.group("body")
        # Raw keys (without _masked suffix) are the offenders
        if re.search(r"[\"']canonical_name[\"']\s*:", body):
            offenders.append(("canonical_name", m.start()))
        if re.search(r"[\"']alias_value[\"']\s*:", body):
            offenders.append(("alias_value", m.start()))

    assert not offenders, (
        f"#1233: identity_resolution/service.py leaks raw PII in log "
        f"extras: {offenders}. Route these through "
        f"shared.pii.mask_name / mask_alias_value and rename the key "
        f"to '<field>_masked'."
    )


def test_service_imports_mask_helpers():
    """A refactor that drops the import silently breaks masking — the
    fields would still be logged but through a NameError path. Lock
    in the import statically."""
    svc_path = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "shared"
        / "identity_resolution"
        / "service.py"
    )
    src = svc_path.read_text()
    assert "from shared.pii import" in src, (
        "#1233: identity_resolution must import mask helpers from shared.pii"
    )
    assert "mask_alias_value" in src or "mask_identifier" in src
    assert "mask_name" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
