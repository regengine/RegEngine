"""Break-it regressions for shared FSMA and auth helpers.

Boundary values, null tenant/helper guards, and helper misuse. Each test
fails on the pre-fix code (which raised raw TypeError/AttributeError or
silently dropped sanitized values) and passes with the fail-closed guards.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from shared.api_key_store import set_api_key_lookup_context
from shared.auth import APIKey, APIKeyStore, verify_jurisdiction_access
from shared.fsma_validation import (
    IdentifierType,
    calculate_gs1_check_digit,
    detect_identifier_type,
    extract_company_prefix,
    normalize_gtin,
    validate_gln,
    validate_gtin,
    validate_identifier,
    validate_sscc,
    verify_gs1_check_digit,
)
from shared.input_validation import (
    EmailField,
    IdentifierField,
    TextContentField,
    ValidationError,
    validate_input,
)
from shared.permissions import has_permission, permission_implies


def _api_key(**overrides):
    base = {
        "key_id": "test-key",
        "key_hash": "hash",
        "name": "test",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "created_at": datetime.now(timezone.utc),
        "allowed_jurisdictions": ["US"],
    }
    base.update(overrides)
    return APIKey(**base)


# --- validate_input decorator applies validated values ---------------------


def test_decorator_applies_sanitized_value_sync() -> None:
    @validate_input(name=TextContentField(allow_html=False))
    def greet(name: str) -> str:
        return name

    assert greet("<b>hi</b>") == "hi"


def test_decorator_applies_sanitized_value_positional() -> None:
    @validate_input(name=TextContentField(allow_html=False))
    def greet(name: str) -> str:
        return name

    assert greet("<i>hello</i>") == "hello"


async def test_decorator_applies_sanitized_value_async() -> None:
    @validate_input(name=TextContentField(allow_html=False))
    async def greet(name: str) -> str:
        return name

    assert await greet("<b>hi</b>") == "hi"


def test_decorator_still_rejects_invalid() -> None:
    @validate_input(email=EmailField())
    def send_email(email: str) -> str:
        return email

    with pytest.raises(ValidationError):
        send_email(email="not-an-email")
    assert send_email(email="user@example.com") == "user@example.com"


def test_decorator_normalizes_identifier() -> None:
    @validate_input(user_id=IdentifierField())
    def get_user(user_id: str) -> str:
        return user_id

    assert get_user(user_id="user-123") == "user-123"


# --- permissions helpers fail closed on helper misuse ----------------------


def test_permission_implies_none_grant_is_false() -> None:
    assert permission_implies(None, "read") is False  # type: ignore[arg-type]


def test_permission_implies_non_string_grant_is_false() -> None:
    assert permission_implies(123, "read") is False  # type: ignore[arg-type]
    assert permission_implies("read", None) is False  # type: ignore[arg-type]


def test_has_permission_skips_junk_entries() -> None:
    assert has_permission([None, "exchange.read"], "exchange.read") is True
    assert has_permission([None], "read") is False
    assert has_permission([123], "read") is False
    assert has_permission([], "read") is False


def test_permission_wildcards_still_work() -> None:
    assert permission_implies("*", "fda.export") is True
    assert permission_implies("fda.*", "fda.export") is True
    assert permission_implies("admin", "simulations.write") is False


# --- fsma_validation helpers fail closed on null/mistyped input ------------


def test_normalize_gtin_none_raises_value_error() -> None:
    with pytest.raises(ValueError):
        normalize_gtin(None)  # type: ignore[arg-type]


def test_normalize_gtin_still_works() -> None:
    assert normalize_gtin("4006381333931") == "04006381333931"


def test_extract_company_prefix_none_raises_value_error() -> None:
    with pytest.raises(ValueError):
        extract_company_prefix(None)  # type: ignore[arg-type]


def test_calculate_check_digit_mistyped_raises_value_error() -> None:
    with pytest.raises(ValueError):
        calculate_gs1_check_digit(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        calculate_gs1_check_digit(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        calculate_gs1_check_digit("12A")


def test_verify_check_digit_non_string_is_false() -> None:
    assert verify_gs1_check_digit(None) is False  # type: ignore[arg-type]
    assert verify_gs1_check_digit(123) is False  # type: ignore[arg-type]
    assert verify_gs1_check_digit("4006381333931") is True


def test_detect_identifier_type_none_is_unknown() -> None:
    assert detect_identifier_type(None) is IdentifierType.UNKNOWN  # type: ignore[arg-type]


def test_validate_identifier_none_fails_closed() -> None:
    result = validate_identifier(None)  # type: ignore[arg-type]
    assert result.is_valid is False


def test_validate_gln_gtin_sscc_mistyped_fail_closed() -> None:
    assert validate_gln(123).is_valid is False  # type: ignore[arg-type]
    assert validate_gtin(None).is_valid is False  # type: ignore[arg-type]
    assert validate_sscc(["x"]).is_valid is False  # type: ignore[arg-type]


def test_tlc_strict_boundary() -> None:
    from shared.fsma_validation import validate_tlc

    assert validate_tlc("00012345678901", strict=True).is_valid is False
    assert validate_tlc("00012345678901-LotA", strict=True).is_valid is True


# --- auth key stores fail closed on non-string credentials -----------------


def test_memory_store_validate_key_mistyped_returns_none() -> None:
    store = APIKeyStore()
    assert store.validate_key(None) is None  # type: ignore[arg-type]
    assert store.validate_key("") is None
    assert store.validate_key(12345) is None  # type: ignore[arg-type]
    assert store.validate_key(["x"]) is None  # type: ignore[arg-type]
    assert store.validate_key("Bearer abc") is None


def test_memory_store_round_trip_still_works() -> None:
    store = APIKeyStore()
    raw, meta = store.create_key(name="k", tenant_id="tid")
    assert store.validate_key(raw) is not None
    assert store.validate_key(raw + "tampered") is None


def test_lookup_context_mistyped_returns_none() -> None:
    class _Session:
        def execute(self, *args, **kwargs):
            raise AssertionError("must not touch the DB for invalid input")

    assert set_api_key_lookup_context(_Session(), None) is None  # type: ignore[arg-type]
    assert set_api_key_lookup_context(_Session(), 12345) is None  # type: ignore[arg-type]


def test_rate_limit_exact_boundary() -> None:
    store = APIKeyStore()
    key_id = "boundary-key"
    allowed = sum(store.check_rate_limit(key_id, 5) for _ in range(6))
    assert allowed == 5


def test_rate_limit_concurrent_hammer_never_exceeds_limit() -> None:
    store = APIKeyStore()
    key_id = "race-key"
    results = []
    lock = threading.Lock()

    def hammer() -> None:
        for _ in range(20):
            verdict = store.check_rate_limit(key_id, 10)
            with lock:
                results.append(verdict)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 10


# --- jurisdiction guard fails closed ---------------------------------------


def test_jurisdiction_mistyped_request_is_403_not_500() -> None:
    key = _api_key()
    for bad in (None, 123, ""):
        with pytest.raises(HTTPException) as exc:
            verify_jurisdiction_access(key, bad)  # type: ignore[arg-type]
        assert exc.value.status_code == 403


def test_jurisdiction_skips_non_string_entitlements() -> None:
    key = APIKey(
        key_id="k",
        key_hash="h",
        name="n",
        tenant_id="tid",
        created_at=datetime.now(timezone.utc),
        allowed_jurisdictions=["US", "US-CA"],
    )
    object.__setattr__(key, "allowed_jurisdictions", ["US", None, "US-CA"])
    verify_jurisdiction_access(key, "US-CA")
    with pytest.raises(HTTPException) as exc:
        verify_jurisdiction_access(key, "US-TX")
    assert exc.value.status_code == 403


def test_jurisdiction_federal_root_still_allowed() -> None:
    verify_jurisdiction_access(_api_key(), "US")
