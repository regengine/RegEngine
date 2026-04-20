"""Coverage closure for ``app/password_policy.py`` — 76% -> 100%.

SEC-009 is the NIST SP 800-63B compliance anchor for admin-service account
hardening. The module enforces length, character-class, repetition, personal-
information, and breach-corpus checks. Any uncovered branch is a silent
failure mode: a weak password slipping through the policy check means the
attacker only has to beat Supabase (or the reset-token guard) before owning
the tenant.

This file pins every missing line from the baseline run:

    41         — breach-corpus loader succeeds when the blocklist file exists
    62-64     — ``PasswordPolicyError.__init__`` stores violations + message
    93        — short-password violation
    96        — over-max-length violation
    100       — missing-uppercase violation
    103       — missing-lowercase violation
    106       — missing-digit violation
    109       — missing-special-character violation
    113       — 3+ consecutive-identical-chars violation
    125       — non-email personal-info context branch (username/name)
    129       — personal-information-substring violation
    133       — common-password (blocklist) violation
    157       — ``validate_password`` raises ``PasswordPolicyError``
    170-171   — ``check_password_strength`` dict shape
    180       — ``get_policy_requirements`` dict shape

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest


# The admin service uses `app.*` as the import root for its own modules
# (see other tests under services/admin/tests). We stay consistent by
# importing through the package path that is already sys.path-rooted.
service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

from services.admin.app.password_policy import (  # noqa: E402
    PasswordPolicy,
    PasswordPolicyError,
    check_password_strength,
    get_policy_requirements,
    validate_password,
)
from services.admin.app import password_policy as pp  # noqa: E402


# ---------------------------------------------------------------------------
# PasswordPolicyError construction (lines 62-64)
# ---------------------------------------------------------------------------


def test_password_policy_error_joins_violations_with_semicolons():
    """The exception keeps the raw list and builds a human-readable message."""
    err = PasswordPolicyError(["too short", "missing digit"])
    assert err.violations == ["too short", "missing digit"]
    assert err.message == "too short; missing digit"
    # Exception chain picks up the joined string.
    assert str(err) == "too short; missing digit"


def test_password_policy_error_single_violation():
    err = PasswordPolicyError(["only one"])
    assert err.violations == ["only one"]
    assert err.message == "only one"


# ---------------------------------------------------------------------------
# Per-rule validation branches (lines 93, 96, 100, 103, 106, 109, 113)
# ---------------------------------------------------------------------------


def test_validate_flags_short_password():
    """Line 93: password shorter than min_length produces the length message."""
    policy = PasswordPolicy()
    violations = policy.validate("Ab1!x")
    assert any("at least" in v and "characters" in v for v in violations), violations


def test_validate_flags_over_max_length():
    """Line 96: password longer than max_length produces a max-length message."""
    # Use a compact policy so we can craft a password that ONLY violates max length.
    policy = PasswordPolicy(
        min_length=4,
        max_length=8,
        require_uppercase=False,
        require_lowercase=False,
        require_digit=False,
        require_special=False,
    )
    violations = policy.validate("abcdefghijklmno")  # 15 chars, no repetitions of 3
    assert violations == ["Password must not exceed 8 characters"]


def test_validate_flags_missing_uppercase():
    """Line 100: require_uppercase is true and no A-Z appears."""
    policy = PasswordPolicy()
    violations = policy.validate("lowercase-only-123!")
    assert "Password must contain at least one uppercase letter" in violations


def test_validate_flags_missing_lowercase():
    """Line 103: require_lowercase is true and no a-z appears."""
    policy = PasswordPolicy()
    violations = policy.validate("UPPERCASE-ONLY-123!")
    assert "Password must contain at least one lowercase letter" in violations


def test_validate_flags_missing_digit():
    """Line 106: require_digit is true and no digit appears."""
    policy = PasswordPolicy()
    violations = policy.validate("NoDigitsHereAtAll!")
    assert "Password must contain at least one digit" in violations


def test_validate_flags_missing_special():
    """Line 109: require_special is true and the special-char regex misses."""
    policy = PasswordPolicy()
    violations = policy.validate("NoSpecialChar123ABC")
    assert "Password must contain at least one special character" in violations


def test_validate_flags_three_consecutive_repeats():
    """Line 113: ``(.)\\1\\1`` catches triple-character runs."""
    policy = PasswordPolicy()
    # Triple 'a' in the middle; satisfies length + upper + lower + digit + special.
    violations = policy.validate("Goodaaa1!Longenough")
    assert (
        "Password must not contain more than 2 consecutive identical characters"
        in violations
    )


def test_validate_allows_double_but_not_triple_repeats():
    """Defensive: two in a row must NOT trip the repetition rule."""
    policy = PasswordPolicy()
    # 'oo' is fine; the rest of the string is intentionally strong.
    violations = policy.validate("Goodoop1!Longenough")
    assert not any("consecutive" in v for v in violations), violations


# ---------------------------------------------------------------------------
# Personal-information branches (lines 125, 129)
# ---------------------------------------------------------------------------


def test_validate_flags_username_substring_in_password():
    """Line 125 + 129: non-email fields are wrapped as ``[value]`` and checked."""
    policy = PasswordPolicy()
    # Pwd contains the username "christopher" (>3 chars).
    violations = policy.validate(
        "Christopher-Is-Strong-1!",
        user_context={"username": "christopher"},
    )
    assert "Password must not contain your username" in violations


def test_validate_flags_first_name_and_last_name_substrings():
    """Line 125 covers first_name and last_name the same way as username."""
    policy = PasswordPolicy()
    violations = policy.validate(
        "Smithson-Alpha-12!",
        user_context={"first_name": "smit", "last_name": "Smithson"},
    )
    # both match: substring on lowercase compare
    assert violations.count("Password must not contain your first_name") == 1
    assert violations.count("Password must not contain your last_name") == 1


def test_validate_flags_email_local_part_substring():
    """Email branch (already partially covered) — local-part must still fire."""
    policy = PasswordPolicy()
    violations = policy.validate(
        "Christopher-Strong-1!",
        user_context={"email": "christopher@example.com"},
    )
    assert "Password must not contain your email" in violations


def test_validate_email_with_short_local_part_is_skipped():
    """Local-part 3 chars or fewer must not participate (length gate at L119/L123)."""
    policy = PasswordPolicy()
    violations = policy.validate(
        "Proper-Strong-Pass-1!",
        user_context={"email": "me@example.com"},  # local 'me' too short
    )
    assert not any("email" in v for v in violations), violations


def test_validate_personal_info_short_value_skipped():
    """user_context value of length <= 3 must not trigger the personal-info check."""
    policy = PasswordPolicy()
    violations = policy.validate(
        "Proper-Strong-Pass-1!",
        user_context={"username": "abc"},  # too short -> skipped
    )
    assert not any("username" in v for v in violations), violations


def test_validate_personal_info_missing_value_skipped():
    """Falsy/missing context values short-circuit the personal-info loop."""
    policy = PasswordPolicy()
    violations = policy.validate(
        "Proper-Strong-Pass-1!",
        user_context={"username": None, "email": ""},
    )
    assert not any(
        "username" in v or "email" in v for v in violations
    ), violations


# ---------------------------------------------------------------------------
# Blocklist check (line 133)
# ---------------------------------------------------------------------------


def test_validate_flags_common_password_verbatim():
    """Line 133: lowercased password in blocklist -> 'too common' violation."""
    policy = PasswordPolicy()
    violations = policy.validate("password")
    assert "Password is too common and easily guessed" in violations


def test_validate_flags_common_password_case_insensitive():
    """The check lowercases before lookup."""
    policy = PasswordPolicy()
    violations = policy.validate("Password123".lower().upper()[:11])  # noqa: F841
    # Use a simpler assertion on a known entry:
    violations2 = policy.validate("REGENGINE")
    assert "Password is too common and easily guessed" in violations2


# ---------------------------------------------------------------------------
# validate_password raise path (line 157)
# ---------------------------------------------------------------------------


def test_validate_password_passes_for_strong_input():
    """No violations -> no exception raised."""
    # Well outside the blocklist and all rules satisfied.
    validate_password("Correct-Horse-Battery-Staple-9!")


def test_validate_password_raises_on_violation():
    """Line 157: a violating password triggers PasswordPolicyError."""
    with pytest.raises(PasswordPolicyError) as ei:
        validate_password("short")
    # Multiple violations — at least one about length.
    assert any("at least" in v for v in ei.value.violations)


def test_validate_password_accepts_custom_policy_override():
    """The ``policy`` kwarg overrides the module default."""
    relaxed = PasswordPolicy(
        min_length=3,
        max_length=64,
        require_uppercase=False,
        require_lowercase=False,
        require_digit=False,
        require_special=False,
        blocked_passwords=set(),
    )
    # Would fail default policy; passes the relaxed one.
    validate_password("abc", policy=relaxed)


def test_validate_password_propagates_user_context():
    """The user_context kwarg flows through to ``PasswordPolicy.validate``."""
    with pytest.raises(PasswordPolicyError) as ei:
        validate_password(
            "Christopher-Strong-1!",
            user_context={"username": "christopher"},
        )
    assert any("username" in v for v in ei.value.violations)


# ---------------------------------------------------------------------------
# check_password_strength (lines 170-171)
# ---------------------------------------------------------------------------


def test_check_password_strength_reports_valid_and_strong():
    """Lines 170-171: no violations -> valid=True, strength=strong."""
    result = check_password_strength("Correct-Horse-Battery-Staple-9!")
    assert result == {
        "valid": True,
        "violations": [],
        "strength": "strong",
    }


def test_check_password_strength_reports_weak_with_violations():
    """Violations list is surfaced alongside a 'weak' label."""
    result = check_password_strength("short")
    assert result["valid"] is False
    assert result["strength"] == "weak"
    assert isinstance(result["violations"], list)
    assert len(result["violations"]) >= 1


def test_check_password_strength_forwards_user_context():
    """user_context must flow through so personal-info checks fire."""
    result = check_password_strength(
        "Christopher-Strong-1!",
        user_context={"username": "christopher"},
    )
    assert result["valid"] is False
    assert any("username" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# get_policy_requirements (line 180)
# ---------------------------------------------------------------------------


def test_get_policy_requirements_returns_current_module_settings():
    """Line 180: shape is stable + matches the module-level knobs."""
    reqs = get_policy_requirements()
    assert reqs == {
        "min_length": pp.MIN_LENGTH,
        "max_length": pp.MAX_LENGTH,
        "require_uppercase": pp.REQUIRE_UPPERCASE,
        "require_lowercase": pp.REQUIRE_LOWERCASE,
        "require_digit": pp.REQUIRE_DIGIT,
        "require_special": pp.REQUIRE_SPECIAL,
        "no_repetition": True,
        "no_personal_info": True,
    }


# ---------------------------------------------------------------------------
# Blocklist loader success path (line 41)
# ---------------------------------------------------------------------------


def test_load_blocklist_reads_file_when_present(tmp_path, monkeypatch):
    """Line 41: when the blocklist file exists, entries are stripped + lowered.

    We reload the module with ``_BLOCKLIST_PATH`` pointed at a fixture file to
    exercise the file-read branch (the FileNotFoundError fallback is already
    covered by the production environment, which has no file).
    """
    fixture = tmp_path / "common_passwords.txt"
    fixture.write_text("HUNTER2\n  PASSW0RD  \n\n  \nletmein\n")

    # Patch at the module level so the subsequent _load_blocklist() call sees it.
    monkeypatch.setattr(pp, "_BLOCKLIST_PATH", fixture)
    loaded = pp._load_blocklist()

    assert "hunter2" in loaded
    assert "passw0rd" in loaded
    assert "letmein" in loaded
    # Empty + whitespace-only lines are dropped.
    assert "" not in loaded
    # Values are lowercased.
    assert "HUNTER2" not in loaded


def test_load_blocklist_falls_back_when_file_missing(tmp_path, monkeypatch):
    """FileNotFoundError path returns the inline frozenset (line 44-52)."""
    missing = tmp_path / "does_not_exist.txt"
    monkeypatch.setattr(pp, "_BLOCKLIST_PATH", missing)
    loaded = pp._load_blocklist()

    # Inline fallback contains known weak passwords.
    assert "password" in loaded
    assert "regengine" in loaded
    assert isinstance(loaded, frozenset)
