"""APIKeyResponse model must tolerate NULL values on nullable DB columns.

Regression test for the admin keys 500/400 bug: `POST /v1/admin/keys`
returned HTTP 500 and `GET /v1/admin/keys` returned HTTP 400 because
`APIKeyResponse.model_validate(row)` rejected rows where
``allowed_jurisdictions``, ``rate_limit_per_*``, ``scopes``, or
``total_requests`` were NULL — even though the Python-side defaults
on the SQLAlchemy columns made those defaults the expected value.

The fix adds pydantic ``@field_validator(mode='before')`` that coerces
NULL → the same default the ORM would have applied on insert.
"""
from datetime import datetime, timezone

import pytest

from shared.api_key_store import APIKeyResponse


def _row(**overrides):
    """Build a duck-typed object that pydantic v2 can ``from_attributes`` from."""

    class _Row:
        pass

    row = _Row()
    base = dict(
        key_id="rge_test",
        key_prefix="rge_test_xx",
        name="test-key",
        description=None,
        tenant_id="5946c58f-ddf9-4db0-9baa-acb11c6fce91",
        billing_tier=None,
        allowed_jurisdictions=["US"],
        scopes=["*"],
        rate_limit_per_minute=60,
        rate_limit_per_hour=1000,
        rate_limit_per_day=10000,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        last_used_at=None,
        total_requests=0,
    )
    base.update(overrides)
    for k, v in base.items():
        setattr(row, k, v)
    return row


def test_null_allowed_jurisdictions_coerces_to_empty_list():
    r = APIKeyResponse.model_validate(_row(allowed_jurisdictions=None))
    assert r.allowed_jurisdictions == []


def test_null_scopes_coerces_to_empty_list():
    r = APIKeyResponse.model_validate(_row(scopes=None))
    assert r.scopes == []


@pytest.mark.parametrize(
    "field,expected",
    [
        ("rate_limit_per_minute", 60),
        ("rate_limit_per_hour", 1000),
        ("rate_limit_per_day", 10000),
        ("total_requests", 0),
    ],
)
def test_null_int_fields_coerce_to_defaults(field, expected):
    r = APIKeyResponse.model_validate(_row(**{field: None}))
    assert getattr(r, field) == expected


def test_all_nullable_fields_null_at_once():
    """The real-world 500 case — a row with every nullable column NULL."""
    r = APIKeyResponse.model_validate(
        _row(
            allowed_jurisdictions=None,
            scopes=None,
            rate_limit_per_minute=None,
            rate_limit_per_hour=None,
            rate_limit_per_day=None,
            total_requests=None,
        )
    )
    assert r.allowed_jurisdictions == []
    assert r.scopes == []
    assert r.rate_limit_per_minute == 60
    assert r.rate_limit_per_hour == 1000
    assert r.rate_limit_per_day == 10000
    assert r.total_requests == 0


def test_non_null_values_pass_through_unchanged():
    """The validator must only rescue NULLs — real values untouched."""
    r = APIKeyResponse.model_validate(
        _row(
            allowed_jurisdictions=["US", "EU"],
            scopes=["webhooks.ingest", "read"],
            rate_limit_per_minute=120,
            rate_limit_per_hour=2000,
            rate_limit_per_day=20000,
            total_requests=42,
        )
    )
    assert r.allowed_jurisdictions == ["US", "EU"]
    assert r.scopes == ["webhooks.ingest", "read"]
    assert r.rate_limit_per_minute == 120
    assert r.rate_limit_per_hour == 2000
    assert r.rate_limit_per_day == 20000
    assert r.total_requests == 42
