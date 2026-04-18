"""
Regression tests for issues #1331 and #1092:

  - #1331 (closed): `erasure_routes.py` called
    `DataRetentionManager.anonymize_audit_logs` with keyword args
    `resource_type` and `record_id` that the method does not accept.
    Calling the endpoint raised TypeError and /v1/account/erasure
    returned 500 for every caller.

  - #1092 (this PR): even after #1331's fix, the erasure endpoint
    called ``AuditActor(actor_email=...)`` — the dataclass field is
    named ``email``, not ``actor_email`` — which raised TypeError
    before the retention layer was reached.  And the batch
    ``anonymize_audit_logs`` was the wrong semantic for a user-
    initiated GDPR right-to-erasure (it targets rows past the 24-
    month retention threshold, not a specific user).

This test locks in that the route now calls the per-user helper
``anonymize_audit_logs_for_user`` with the correct kwargs and that
``AuditActor`` is constructed with the real field name.
"""

from __future__ import annotations

import inspect


def test_anonymize_audit_logs_signature_has_expected_parameters():
    """Lock in the DataRetentionManager.anonymize_audit_logs signature
    so the (still-supported) batch method cannot be silently renamed.

    If a future PR changes this signature, this test fails loudly
    rather than producing a runtime TypeError if a caller re-adopts
    the batch variant.
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


def test_anonymize_audit_logs_for_user_exists_with_correct_signature():
    """GDPR #1092: the per-user method must exist and take (db,
    user_id, tenant_id, *, actor).  If this signature changes, the
    erasure route breaks silently, so lock it in."""
    from shared.data_retention import DataRetentionManager

    sig = inspect.signature(
        DataRetentionManager.anonymize_audit_logs_for_user
    )
    params = sig.parameters
    assert "db" in params
    assert "user_id" in params
    assert "tenant_id" in params
    assert "actor" in params
    # ``actor`` must be keyword-only — passing it positionally is a
    # readability anti-pattern for a security-critical API.
    assert params["actor"].kind == inspect.Parameter.KEYWORD_ONLY


def test_erasure_route_calls_per_user_anonymize_with_correct_kwargs():
    """Inspect the erasure route source to ensure the #1092 fix has
    landed.

    This is a thin guard: we do not exercise the full request path
    (the admin service has a larger test harness for that) but we do
    assert that the call in erasure_routes.py matches the shared
    per-user signature.
    """
    import pathlib

    source_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app"
        / "erasure_routes.py"
    )
    source = source_path.read_text()

    # The fix uses the per-user variant.
    assert "anonymize_audit_logs_for_user(" in source, (
        "erasure_routes.py must call anonymize_audit_logs_for_user "
        "(per-user GDPR variant) to match the #1092 fix"
    )

    # The call site passes user_id= and tenant_id=
    idx = source.find("anonymize_audit_logs_for_user(")
    tail = source[idx : idx + 800]
    assert "user_id=" in tail
    assert "tenant_id=" in tail
    assert "actor=" in tail

    # AuditActor must be constructed with `email=` (the real field),
    # not the invalid `actor_email=` (which raised TypeError and
    # silently broke every erasure request even after #1441).
    assert "actor_email=" not in source, (
        "AuditActor has no `actor_email` field -- use `email=`"
    )
    assert "email=mask_email(" in source, (
        "erasure_routes.py must construct AuditActor(email=mask_email(...))"
    )
