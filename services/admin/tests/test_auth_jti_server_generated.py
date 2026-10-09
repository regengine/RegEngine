"""Low-severity audit fix: token jti must be generated server-side.

Caller-supplied ``jti`` values risk collisions: two callers minting with the
same id would revoke (or replay) each other's token. ``create_access_token``
must always mint a fresh server-side jti and ignore any caller value.
"""

from __future__ import annotations


def test_caller_supplied_jti_is_ignored():
    from services.admin.app.auth_utils import create_access_token, decode_access_token

    tok = create_access_token({"sub": "abc", "jti": "caller-chosen-id"})
    payload = decode_access_token(tok)
    assert payload["jti"] != "caller-chosen-id"
    assert payload["jti"]


def test_same_caller_jti_mints_distinct_ids():
    from services.admin.app.auth_utils import create_access_token, decode_access_token

    tok_a = create_access_token({"sub": "abc", "jti": "shared-id"})
    tok_b = create_access_token({"sub": "abc", "jti": "shared-id"})
    jti_a = decode_access_token(tok_a)["jti"]
    jti_b = decode_access_token(tok_b)["jti"]
    assert jti_a != jti_b


def test_tokens_without_jti_still_get_one():
    from services.admin.app.auth_utils import create_access_token, decode_access_token

    tok = create_access_token({"sub": "abc"})
    assert decode_access_token(tok)["jti"]
