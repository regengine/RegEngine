"""Tests for #1323 (stable hash) and #1324 (rejected validation status).

Issue #1332 (first-event chain race) is already CLOSED — skipped here.

#1323 — product_description must NOT affect the event hash or idempotency key.
#1324 — store_event must set validation_status='rejected' when validator_results
         contains a REJECT-severity entry, and must NOT write a hash_chain row.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from services.shared.cte_persistence.hashing import (
    compute_event_hash,
    compute_idempotency_key,
)
from services.shared.cte_persistence.core import (
    VALIDATION_STATUS_REJECTED,
    VALIDATION_STATUS_VALID,
    VALIDATION_STATUS_WARNING,
    _REJECT_SEVERITIES,
)


# ===========================================================================
# #1323 — product_description excluded from event hash
# ===========================================================================


class TestStableHashNoProductDescription_Issue1323:
    """Regression: #1323.

    Re-ingesting the same logical event with a different product_description
    (translation, reformatting) must produce the SAME SHA-256 hash so that
    dedup and chain verification do not break.
    """

    _BASE_KWARGS: Dict[str, Any] = dict(
        event_id="evt-1323-base",
        event_type="receiving",
        tlc="TLC-LOT-001",
        quantity=100.0,
        unit_of_measure="kg",
        location_gln="0614141123452",
        location_name="Warehouse A",
        timestamp="2026-04-01T10:00:00+00:00",
        kdes={},
    )

    def test_different_descriptions_same_hash(self):
        """Core regression: two ingest calls for the same event with different
        product_description values must produce identical SHA-256 hashes."""
        h1 = compute_event_hash(product_description="Romaine Lettuce", **self._BASE_KWARGS)
        h2 = compute_event_hash(product_description="Laitue Romaine (FR)", **self._BASE_KWARGS)
        assert h1 == h2, (
            "product_description should not affect the event hash; "
            "re-ingestion with a reformatted description must not create a new hash"
        )

    def test_empty_description_same_hash(self):
        """Empty description must produce the same hash as non-empty."""
        h1 = compute_event_hash(product_description="", **self._BASE_KWARGS)
        h2 = compute_event_hash(product_description="Any description here", **self._BASE_KWARGS)
        assert h1 == h2

    def test_stable_identifiers_do_affect_hash(self):
        """Sanity: changing a stable identifier (tlc, event_type) MUST produce
        a different hash — otherwise dedup is useless."""
        h_base = compute_event_hash(product_description="desc", **self._BASE_KWARGS)
        # Different TLC
        h_diff_tlc = compute_event_hash(
            product_description="desc",
            **{**self._BASE_KWARGS, "tlc": "TLC-LOT-999"},
        )
        assert h_base != h_diff_tlc, "Changing tlc must produce a different hash"

        # Different event_type
        h_diff_type = compute_event_hash(
            product_description="desc",
            **{**self._BASE_KWARGS, "event_type": "shipping"},
        )
        assert h_base != h_diff_type, "Changing event_type must produce a different hash"

    def test_compute_idempotency_key_unchanged(self):
        """compute_idempotency_key never included product_description — confirm
        it still doesn't (belt-and-suspenders check that we didn't accidentally
        add it while fixing #1323)."""
        k1 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-001",
            timestamp="2026-04-01T10:00:00+00:00",
            source="api",
            kdes={},
        )
        # product_description is not a parameter — calling with same args
        # always returns the same key regardless of what caller passes.
        k2 = compute_idempotency_key(
            event_type="receiving",
            tlc="TLC-001",
            timestamp="2026-04-01T10:00:00+00:00",
            source="api",
            kdes={},
        )
        assert k1 == k2


# ===========================================================================
# #1324 — validation_status='rejected' when validator returns REJECT severity
# ===========================================================================


class TestValidationStatusRejected_Issue1324:
    """Regression: #1324.

    When store_event receives a validator_results list containing at least one
    entry with REJECT severity, it must:
      1. Persist the event row with validation_status='rejected'.
      2. NOT write a hash_chain row for the rejected event.
      3. Return a StoreResult with success=False and the rejection reasons
         in the errors field.
    """

    def _make_session(self) -> MagicMock:
        """Build a minimal SQLAlchemy session mock that satisfies store_event."""
        session = MagicMock()

        # execute().fetchone() returns None → no existing idempotency match,
        # then None → no chain head (first event), then None for any further
        # fetchone calls.
        execute_result = MagicMock()
        execute_result.fetchone.return_value = None
        session.execute.return_value = execute_result

        # begin_nested() for savepoint — not needed for rejected path but
        # shouldn't crash if called.
        session.begin_nested.return_value = MagicMock()

        return session

    def _call_store_event(
        self,
        session: MagicMock,
        validator_results: Optional[List[Dict[str, Any]]] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
    ):
        from services.shared.cte_persistence.core import CTEPersistence

        persistence = CTEPersistence(session)
        return persistence.store_event(
            tenant_id="tenant-1324",
            event_type="receiving",
            traceability_lot_code="TLC-1324",
            product_description="Romaine Lettuce",
            quantity=50.0,
            unit_of_measure="kg",
            event_timestamp="2026-04-01T10:00:00+00:00",
            source="api",
            kdes={"temperature_c": 4.0},
            alerts=alerts or [],
            validator_results=validator_results or [],
        )

    # --- Happy path: no validators → valid ---

    def test_no_validators_status_valid(self):
        session = self._make_session()
        result = self._call_store_event(session)
        # Locate the cte_events INSERT call and extract the validation_status param
        _assert_insert_status(session, VALIDATION_STATUS_VALID)

    def test_alerts_only_status_warning(self):
        session = self._make_session()
        alerts = [{"alert_type": "missing_kde", "severity": "warning", "message": "Missing temp"}]
        result = self._call_store_event(session, alerts=alerts)
        _assert_insert_status(session, VALIDATION_STATUS_WARNING)

    # --- Rejection path ---

    def test_reject_severity_sets_rejected_status(self):
        """validator_results with severity='reject' → validation_status='rejected'."""
        session = self._make_session()
        result = self._call_store_event(
            session,
            validator_results=[{"severity": "reject", "reason": "Missing required KDE: location_gln"}],
        )
        assert result.success is False, "Rejected event must return success=False"
        assert result.errors, "Rejected event must have non-empty errors list"
        assert "Missing required KDE: location_gln" in result.errors[0]
        _assert_insert_status(session, VALIDATION_STATUS_REJECTED)

    def test_error_severity_sets_rejected_status(self):
        """severity='error' (alternate casing) is also a hard rejection."""
        session = self._make_session()
        result = self._call_store_event(
            session,
            validator_results=[{"severity": "error", "reason": "CTE type not permitted for this product"}],
        )
        assert result.success is False
        _assert_insert_status(session, VALIDATION_STATUS_REJECTED)

    def test_rejected_event_not_in_hash_chain(self):
        """No hash_chain INSERT must occur for a rejected event."""
        session = self._make_session()
        self._call_store_event(
            session,
            validator_results=[{"severity": "REJECT", "reason": "Mandatory field absent"}],
        )
        _assert_no_chain_insert(session)

    def test_warning_severity_not_rejected(self):
        """severity='warning' must NOT trigger rejection — event is stored as valid
        (no alerts supplied, so the status is 'valid', not 'rejected')."""
        session = self._make_session()
        result = self._call_store_event(
            session,
            validator_results=[{"severity": "warning", "reason": "Temperature slightly off"}],
        )
        assert result.success is True, "Warning-severity validator must not cause rejection"
        # No alerts were supplied, so the event status is 'valid' not 'warning'.
        # 'warning' status only applies when alerts are present.
        _assert_insert_status(session, VALIDATION_STATUS_VALID)

    def test_multiple_reject_reasons_all_in_errors(self):
        """All rejection reasons from multiple REJECT validators appear in errors."""
        session = self._make_session()
        result = self._call_store_event(
            session,
            validator_results=[
                {"severity": "reject", "reason": "Reason A"},
                {"severity": "reject", "reason": "Reason B"},
            ],
        )
        assert len(result.errors) == 2
        assert "Reason A" in result.errors
        assert "Reason B" in result.errors

    def test_reject_severity_constants(self):
        """Confirm that the documented severity strings are all in _REJECT_SEVERITIES."""
        for sev in ("reject", "REJECT", "error", "ERROR"):
            assert sev in _REJECT_SEVERITIES, f"{sev!r} should be a reject severity"
        for sev in ("warning", "WARNING", "info", "INFO"):
            assert sev not in _REJECT_SEVERITIES, f"{sev!r} should not be a reject severity"


# ===========================================================================
# Helpers
# ===========================================================================


def _get_insert_calls(session: MagicMock) -> List[Any]:
    """Return all session.execute calls whose SQL contains INSERT INTO fsma.cte_events."""
    calls = []
    for c in session.execute.call_args_list:
        args = c.args or ()
        if args:
            sql_arg = args[0]
            sql_text = str(sql_arg) if not isinstance(sql_arg, str) else sql_arg
            if "INSERT INTO fsma.cte_events" in sql_text:
                calls.append(c)
    return calls


def _assert_insert_status(session: MagicMock, expected_status: str) -> None:
    """Assert that the cte_events INSERT was called with the expected validation_status."""
    inserts = _get_insert_calls(session)
    assert inserts, "Expected an INSERT INTO fsma.cte_events call"
    # The params dict is the second positional arg to session.execute()
    last_insert = inserts[-1]
    params = last_insert.args[1] if len(last_insert.args) > 1 else {}
    actual = params.get("validation_status")
    assert actual == expected_status, (
        f"Expected validation_status={expected_status!r}, got {actual!r}"
    )


def _assert_no_chain_insert(session: MagicMock) -> None:
    """Assert that no INSERT INTO fsma.hash_chain call was made."""
    for c in session.execute.call_args_list:
        args = c.args or ()
        if args:
            sql_arg = args[0]
            sql_text = str(sql_arg) if not isinstance(sql_arg, str) else sql_arg
            if "INSERT INTO fsma.hash_chain" in sql_text:
                raise AssertionError(
                    "hash_chain INSERT must NOT occur for a rejected event, "
                    f"but found call: {c}"
                )


# ===========================================================================
# #1324 batch path — store_events_batch must also honour validator_results
# ===========================================================================


class TestBatchValidationStatusRejected_Issue1324:
    """Regression (batch path): #1324.

    store_events_batch must read each event's ``validator_results`` list
    and set ``validation_status='rejected'`` for any event with a
    REJECT-severity entry. Rejected events must still be persisted (for
    audit) but must NOT appear in chain_rows or kde_rows.
    """

    _NOW = "2026-04-01T10:00:00+00:00"

    def _make_session(self) -> MagicMock:
        session = MagicMock()
        execute_result = MagicMock()
        execute_result.fetchone.return_value = None
        execute_result.fetchall.return_value = []
        session.execute.return_value = execute_result
        session.begin_nested.return_value = MagicMock()
        return session

    def _base_event(self, tlc: str = "TLC-BATCH-001", **overrides) -> Dict[str, Any]:
        evt: Dict[str, Any] = {
            "event_type": "receiving",
            "traceability_lot_code": tlc,
            "product_description": "Spinach",
            "quantity": 10.0,
            "unit_of_measure": "kg",
            "event_timestamp": self._NOW,
        }
        evt.update(overrides)
        return evt

    def _call_batch(self, session: MagicMock, events: List[Dict[str, Any]]) -> List:
        from services.shared.cte_persistence.core import CTEPersistence
        persistence = CTEPersistence(session)
        return persistence.store_events_batch("tenant-batch-1324", events)

    # -----------------------------------------------------------------------
    # Happy path
    # -----------------------------------------------------------------------

    def test_no_validator_results_batch_status_valid(self):
        """Event without validator_results → validation_status='valid'."""
        session = self._make_session()
        results = self._call_batch(session, [self._base_event()])
        assert len(results) == 1
        assert results[0].success is True
        # Find the cte_events INSERT and assert validation_status key value
        found = False
        for c in session.execute.call_args_list:
            args = c.args or ()
            if args and "INSERT INTO fsma.cte_events" in str(args[0]):
                # Batch INSERT uses positional param keys like :vs_0
                params = args[1] if len(args) > 1 else {}
                assert params.get("vs_0") == VALIDATION_STATUS_VALID, (
                    f"Expected 'valid', got {params.get('vs_0')!r}"
                )
                found = True
        assert found, "Expected an INSERT INTO fsma.cte_events call"

    # -----------------------------------------------------------------------
    # Rejection path
    # -----------------------------------------------------------------------

    def test_reject_severity_batch_status_rejected(self):
        """Event with severity='reject' → validation_status='rejected', success=False."""
        session = self._make_session()
        evt = self._base_event(
            validator_results=[{"severity": "reject", "reason": "Bad TLC format"}]
        )
        results = self._call_batch(session, [evt])
        assert len(results) == 1
        result = results[0]
        assert result.success is False, "Batch rejected event must return success=False"
        assert result.errors, "Batch rejected event must have non-empty errors"
        assert "Bad TLC format" in result.errors[0]
        # The batch INSERT params use :vs_0
        for c in session.execute.call_args_list:
            args = c.args or ()
            if args and "INSERT INTO fsma.cte_events" in str(args[0]):
                params = args[1] if len(args) > 1 else {}
                actual = params.get("vs_0")
                assert actual == VALIDATION_STATUS_REJECTED, (
                    f"Expected 'rejected', got {actual!r}"
                )

    def test_rejected_batch_event_not_in_chain(self):
        """No hash_chain INSERT must occur when all batch events are rejected."""
        session = self._make_session()
        evt = self._base_event(
            validator_results=[{"severity": "ERROR", "reason": "Mandatory field absent"}]
        )
        self._call_batch(session, [evt])
        for c in session.execute.call_args_list:
            args = c.args or ()
            if args and "INSERT INTO fsma.hash_chain" in str(args[0]):
                raise AssertionError(
                    "hash_chain INSERT must NOT occur for a rejected batch event"
                )

    def test_rejected_batch_event_is_still_persisted(self):
        """Rejected events must still produce an INSERT INTO fsma.cte_events call."""
        session = self._make_session()
        evt = self._base_event(
            validator_results=[{"severity": "reject", "reason": "Missing GLN"}]
        )
        self._call_batch(session, [evt])
        insert_calls = [
            c for c in session.execute.call_args_list
            if c.args and "INSERT INTO fsma.cte_events" in str(c.args[0])
        ]
        assert insert_calls, "Rejected event must still be INSERTed into cte_events (audit trail)"

    def test_mixed_batch_rejected_and_valid(self):
        """A batch with one rejected and one valid event: each gets correct status."""
        session = self._make_session()
        valid_evt = self._base_event(tlc="TLC-VALID")
        rejected_evt = self._base_event(
            tlc="TLC-REJECTED",
            validator_results=[{"severity": "reject", "reason": "Invalid unit"}],
        )
        results = self._call_batch(session, [valid_evt, rejected_evt])
        assert len(results) == 2
        # Valid event result
        assert results[0].success is True
        assert not results[0].errors
        # Rejected event result
        assert results[1].success is False
        assert "Invalid unit" in results[1].errors[0]

    def test_warning_severity_not_rejected_batch(self):
        """severity='warning' in validator_results must not trigger rejection in batch."""
        session = self._make_session()
        evt = self._base_event(
            validator_results=[{"severity": "warning", "reason": "Temp slightly off"}]
        )
        results = self._call_batch(session, [evt])
        assert results[0].success is True
        for c in session.execute.call_args_list:
            args = c.args or ()
            if args and "INSERT INTO fsma.cte_events" in str(args[0]):
                params = args[1] if len(args) > 1 else {}
                actual = params.get("vs_0")
                assert actual == VALIDATION_STATUS_VALID, (
                    f"Warning severity must not set 'rejected'; got {actual!r}"
                )
