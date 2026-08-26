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
    from app.epcis import persistence as persistence_mod

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
    from app.epcis import persistence as persistence_mod

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
