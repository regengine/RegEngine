"""QA5: input-validation fixes for shared/input_validation.py."""

import pytest
from shared.input_validation import (
    InjectionAttemptError,
    InjectionRule,
    IntegerField,
    TextContentField,
    ValidationError,
    validate_input,
)


def test_validate_input_propagates_sanitized_values_sync() -> None:
    @validate_input(note=TextContentField(allow_html=False))
    def save(note: str) -> str:
        return note

    assert save("<b>x</b>") == "x"


def test_validate_input_propagates_sanitized_values_async() -> None:
    import asyncio

    @validate_input(note=TextContentField(allow_html=False))
    async def save(note: str) -> str:
        return note

    assert asyncio.run(save("<i>y</i>")) == "y"


def test_integer_field_rejects_non_integral_float() -> None:
    with pytest.raises(ValidationError):
        IntegerField().validate(3.9, "qty")


def test_integer_field_accepts_integral_values() -> None:
    assert IntegerField().validate(3, "qty") == 3
    assert IntegerField().validate(3.0, "qty") == 3
    assert IntegerField().validate("4", "qty") == 4


def test_integer_field_rejects_bool_and_decimal_strings() -> None:
    with pytest.raises(ValidationError):
        IntegerField().validate(True, "qty")
    with pytest.raises(ValidationError):
        IntegerField().validate("3.5", "qty")


def test_injection_rule_rejects_comment_obfuscated_union_select() -> None:
    with pytest.raises(InjectionAttemptError):
        InjectionRule().validate("1 UNION/**/SELECT password FROM users", "q")


def test_injection_rule_still_accepts_plain_text() -> None:
    assert InjectionRule().validate("quarterly union picnic schedule", "q") == (
        "quarterly union picnic schedule"
    )
