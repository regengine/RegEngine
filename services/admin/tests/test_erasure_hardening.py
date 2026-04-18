"""
Regression tests for issue #1331:
  - `erasure_routes.py` called `DataRetentionManager.anonymize_audit_logs`
    with keyword args `resource_type` and `record_id` that the method
    does not accept. Calling the endpoint raised TypeError and the
    /v1/account/erasure endpoint returned 500 for every caller.

This test locks in the correct signature -- `anonymize_audit_logs` is
now called with `retention_policy` and `actor`, matching the
`services/shared/data_retention.py` API.

We test the caller surface only (the erasure route). The shared
``data_retention`` module is not modified here; see
``services/shared/data_retention.py`` and PR #1436 for parallel work
on that file.
"""

from __future__ import annotations

import inspect

import pytest


def test_anonymize_audit_logs_signature_has_expected_parameters():
    """Lock in the DataRetentionManager.anonymize_audit_logs signature
    so the erasure caller does not break if kwargs are renamed.

    If a future PR changes this signature without updating
    erasure_routes.py, this test fails loudly rather than producing a
    runtime TypeError when a user hits /v1/account/erasure.
    """
    from shared.data_retention import DataRetentionManager

    sig = inspect.signature(DataRetentionManager.anonymize_audit_logs)
    params = set(sig.parameters.keys())

    # The method takes (self, db, retention_policy, actor)
    assert "db" in params
    assert "retention_policy" in params
    assert "actor" in params
    # The old (wrong) call used `resource_type` and `record_id`; make
    # sure those are NOT on the signature so the mistake is loud.
    assert "resource_type" not in params
    assert "record_id" not in params


def test_erasure_route_calls_anonymize_with_correct_kwargs():
    """Inspect the erasure route source to ensure the fix has landed.

    This is a thin guard: we do not exercise the full request path
    (the admin service has a larger test harness for that) but we do
    assert that the call in erasure_routes.py matches the shared
    signature.
    """
    import pathlib

    source_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app"
        / "erasure_routes.py"
    )
    source = source_path.read_text()

    # The fix uses `retention_policy=` and `actor=`
    assert "retention_policy=" in source, (
        "erasure_routes.py must call anonymize_audit_logs with "
        "retention_policy kwarg to match data_retention.py signature"
    )
    # Prior broken call used resource_type= on anonymize_audit_logs
    # (the signature only accepts retention_policy/actor). If it
    # reappears, fail.
    # We check the specific call region to avoid false positives on
    # process_deletion_request which does accept resource_type.
    # Simplest check: the literal mistake pattern must not exist.
    assert "anonymize_audit_logs(\n" in source or "anonymize_audit_logs(" in source
    # The call site should NOT pass resource_type nor record_id to
    # anonymize_audit_logs -- we check by looking at the call tokens
    # immediately following `manager.anonymize_audit_logs`.
    idx = source.find("anonymize_audit_logs(")
    # Skip to the next matching close paren depth, limited scan
    tail = source[idx : idx + 600]
    # find closing paren for the call
    # Simple bound: look for "actor=" which should appear, and
    # the call should NOT contain "record_id=user_id" as a kwarg
    assert "actor=actor" in tail
    assert "record_id=user_id" not in tail
