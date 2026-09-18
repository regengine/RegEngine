"""Unsupported-but-valid CTE vocabulary must be a 422, not a 500.

Companion to test_epcis_persistence_enforcement.py, which pins the same
distinction one layer down and only under enforcement. This file covers the
HTTP edge (`_ingest_single_event`) and therefore the DEFAULT
``RULES_ENGINE_ENFORCE=off`` path, which the first #2815 follow-up missed.

Two independent code paths produce the same client-visible fault for FSMA
``growing`` / CBV ``planting`` — real bizSteps that are simply not among the
7 §1.1310 CTEs:

  * the legacy write, where ``_validate_event_type`` raises a bare
    ``ValueError`` for a non-CTE ``event_type``; and
  * the canonical dual-write, which raises ``UnmappedBizStepError`` (also a
    ``ValueError`` subclass) for the same inputs.

``_ingest_single_event`` special-cased only ``E_EPCIS_UNVALIDATED`` and let
every other ``ValueError`` fall through to a bare ``raise``, so both became
an unhandled 500.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException


def _call_ingest_raising(exc: BaseException) -> HTTPException:
    """Drive `_ingest_single_event` with `_ingest_single_event_db` raising."""
    from services.ingestion.app.epcis import persistence as persistence_mod

    original = persistence_mod._ingest_single_event_db

    def _boom(tenant_id: str, event: dict):
        raise exc

    persistence_mod._ingest_single_event_db = _boom
    try:
        with pytest.raises(HTTPException) as caught:
            persistence_mod._ingest_single_event("t-1", {"bizStep": "x"})
        return caught.value
    finally:
        persistence_mod._ingest_single_event_db = original


def test_legacy_non_cte_event_type_is_422() -> None:
    """`_validate_event_type`'s refusal is a rejection, not a server fault."""
    exc = _call_ingest_raising(
        ValueError(
            "event_type 'growing' is not a recognized FSMA 204 CTE type. "
            "Allowed: ['cooling', 'first_land_based_receiving', ...]"
        )
    )
    assert exc.status_code == 422, "a non-CTE event_type must not surface as a 500"
    assert exc.detail["error"] == "unsupported_cte_type"
    assert "growing" in exc.detail["message"]


def test_canonical_unmapped_bizstep_is_422() -> None:
    """The canonical resolver's refusal maps to the same 422.

    This path runs unguarded whenever the event is not idempotent, so it is
    reachable under the default enforcement-off configuration.
    """
    from shared.canonical_event import UnmappedBizStepError

    exc = _call_ingest_raising(
        UnmappedBizStepError(
            "bizStep 'urn:fsma:traceability:growing' maps to the non-CTE "
            "activity 'growing'"
        )
    )
    assert exc.status_code == 422
    assert exc.detail["error"] == "unsupported_cte_type"


def test_unrelated_valueerror_is_not_swallowed_into_422() -> None:
    """The guard must stay narrow.

    An unrelated ValueError is a genuine fault and must NOT be relabelled as
    a client rejection — otherwise this fix would hide real bugs behind a 422.

    It keeps its pre-existing behavior of propagating as a raw ValueError:
    the `except ValueError` branch ends in a bare `raise`, which exits the
    whole try statement, so the sibling `except Exception` fallback below it
    is deliberately not reached. That is unchanged by this fix and is
    asserted here so a future widening of the guard is caught.
    """
    from services.ingestion.app.epcis import persistence as persistence_mod

    original = persistence_mod._ingest_single_event_db

    def _boom(tenant_id: str, event: dict):
        raise ValueError("something genuinely unexpected exploded")

    persistence_mod._ingest_single_event_db = _boom
    try:
        with pytest.raises(ValueError) as caught:
            persistence_mod._ingest_single_event("t-1", {"bizStep": "x"})
        assert not isinstance(caught.value, HTTPException), (
            "an unrelated ValueError must not be relabelled as a client rejection"
        )
        assert "genuinely unexpected" in str(caught.value)
    finally:
        persistence_mod._ingest_single_event_db = original


# ---------------------------------------------------------------------------
# Phase-1 rejection (the atomic-batch framing fix)
# ---------------------------------------------------------------------------


def _event_with_bizstep(biz_step: str) -> dict:
    """Minimal EPCIS shell — extract helpers tolerate missing lists/dicts."""
    return {
        "type": "ObjectEvent",
        "eventTime": "2026-04-18T09:30:00.000-05:00",
        "eventTimeZoneOffset": "-05:00",
        "action": "OBSERVE",
        "bizStep": biz_step,
        "ilmd": {
            "cbvmda:lotNumber": "LOT-2815",
            "fsma:traceabilityLotCode": "00012345678901-LOT2815",
        },
    }


def test_persistable_cte_types_matches_the_legacy_allowed_set() -> None:
    """Drift guard.

    `_PERSISTABLE_CTE_TYPES` deliberately duplicates
    `cte_persistence.core._ALLOWED_CTE_TYPES` rather than importing it (that
    module is slated for retirement, #1335). A copy is only safe with a test
    holding the two together.
    """
    from services.ingestion.app.epcis.persistence import _PERSISTABLE_CTE_TYPES
    from shared.cte_persistence.core import _ALLOWED_CTE_TYPES

    assert _PERSISTABLE_CTE_TYPES == _ALLOWED_CTE_TYPES


@pytest.mark.parametrize(
    "biz_step",
    ["urn:fsma:traceability:growing", "urn:epcglobal:cbv:bizstep:planting"],
)
def test_non_cte_bizstep_is_rejected_in_phase_one(biz_step: str) -> None:
    """Rejected during validation, before any persistence is attempted."""
    from services.ingestion.app.epcis.persistence import _prepare_event_for_persistence

    with pytest.raises(HTTPException) as caught:
        _prepare_event_for_persistence("t-1", _event_with_bizstep(biz_step))

    assert caught.value.status_code == 422
    assert caught.value.detail["error"] == "unsupported_cte_type"
    assert "growing" in caught.value.detail["message"]


def test_atomic_batch_reports_validation_failure_not_persistence_crash() -> None:
    """The batch framing fix.

    Phase 2 wraps ANY exception as `batch_persistence_failed` ("Persistence
    failed mid-batch"), rolling the batch back and telling the client nothing
    about which event was at fault. A non-CTE bizStep is a validation
    rejection, so it must be caught in phase 1 and reported per-index — and
    it must never reach phase 2, which would need a database.
    """
    from services.ingestion.app.epcis.persistence import _ingest_batch_events_db_atomic

    batch = [
        _event_with_bizstep("urn:epcglobal:cbv:bizstep:shipping"),
        _event_with_bizstep("urn:fsma:traceability:growing"),  # index 1
    ]

    with pytest.raises(HTTPException) as caught:
        _ingest_batch_events_db_atomic("t-1", batch)

    detail = caught.value.detail
    assert detail["error"] == "batch_validation_failed", (
        f"expected a phase-1 validation rejection, got {detail.get('error')!r} "
        "— a non-CTE bizStep must not be framed as a mid-batch persistence crash"
    )
    assert detail["mode"] == "atomic"
    offending = [e for e in detail["errors"] if e["index"] == 1]
    assert offending, f"the offending index must be named: {detail['errors']}"
    assert offending[0]["status_code"] == 422
