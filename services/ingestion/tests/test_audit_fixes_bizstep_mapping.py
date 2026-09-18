"""Regression tests for #2815 — EPCIS bizStep → CTE mapping divergence.

Context
-------
``epcis/persistence.py`` writes TWO rows for the same EPCIS event inside
ONE transaction:

  * the legacy ``fsma.cte_events`` row, whose ``event_type`` comes from
    ``app.epcis.normalization._EVENT_TYPE_MAP`` — a 17-entry EXACT URI
    lookup that rejects anything unmapped (#1153), and
  * the canonical ``fsma.traceability_events`` row (the table FDA exports
    read), whose ``event_type`` came from a 6-entry FUZZY SUBSTRING loop in
    ``shared.canonical_event.normalize_epcis_event`` with
    ``cte_type = CTEType.RECEIVING`` as a silent default.

Five real bizSteps disagreed between the two, and every one of them landed
in the canonical table as ``receiving``:

  urn:fsma:traceability:transformation             ("transforming" is not a
                                                    substring of
                                                    "transformation")
  urn:fsma:traceability:initial_packing            (key was "commissioning")
  urn:fsma:traceability:first_land_based_receiving (matched the "receiving"
                                                    substring)
  urn:epcglobal:cbv:bizstep:packing                (no key matched)
  urn:epcglobal:cbv:bizstep:storing                (no key matched)

This module pins the fix:

  1. Every key in the authoritative ``_EVENT_TYPE_MAP`` round-trips through
     the canonical resolver to the matching ``CTEType``.
  2. The two maps cover EXACTLY the same key set (drift guard — the
     canonical map is a hand-maintained mirror because a real import would
     be circular; see the comment on ``BIZSTEP_TO_CTE_TYPE``).
  3. The five previously-broken URIs resolve correctly, and specifically no
     longer resolve to ``receiving``.
  4. An unmapped bizStep RAISES instead of defaulting to ``receiving``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from services.ingestion.app.epcis.normalization import _EVENT_TYPE_MAP  # noqa: E402
from shared.canonical_event import (  # noqa: E402
    BIZSTEP_TO_CTE_TYPE,
    CTEType,
    UnmappedBizStepError,
    _resolve_bizstep_to_cte_type,
    normalize_epcis_event,
)

TENANT_ID = "11111111-2222-3333-4444-555555555555"

# ``_EVENT_TYPE_MAP`` values that are NOT one of the 7 FSMA 204 §1.1310 CTEs.
# "growing" has no ``CTEType`` member and is rejected by the
# ``fsma.traceability_events`` event_type CHECK constraint
# (V043__canonical_traceability_events.sql), so it cannot be represented in
# the canonical store at all — the resolver raises rather than coercing it
# into a neighbouring CTE.
_NON_CANONICAL_CTE_STRINGS = {"growing"}

# The five bizSteps that silently became ``receiving`` before the fix.
_PREVIOUSLY_BROKEN = {
    "urn:fsma:traceability:transformation": CTEType.TRANSFORMATION,
    "urn:fsma:traceability:initial_packing": CTEType.INITIAL_PACKING,
    "urn:fsma:traceability:first_land_based_receiving": CTEType.FIRST_LAND_BASED_RECEIVING,
    "urn:epcglobal:cbv:bizstep:packing": CTEType.INITIAL_PACKING,
    "urn:epcglobal:cbv:bizstep:storing": CTEType.COOLING,
}


def _epcis_event(biz_step: str) -> dict:
    """Minimal EPCIS event that satisfies the #1249 quantity contract."""
    return {
        "type": "ObjectEvent",
        "eventTime": "2026-06-15T14:00:00Z",
        "bizStep": biz_step,
        "epcList": ["urn:epc:id:sgtin:061414100001.ABC123"],
        "extension": {"quantityList": [{"quantity": 42, "uom": "cases"}]},
    }


# ---------------------------------------------------------------------------
# 1 + 2. Full round-trip over the authoritative map, and drift guard
# ---------------------------------------------------------------------------


def test_canonical_map_covers_exactly_the_authoritative_key_set() -> None:
    """Drift guard.

    ``shared.canonical_event.BIZSTEP_TO_CTE_TYPE`` is a hand-maintained
    mirror of ``app.epcis.normalization._EVENT_TYPE_MAP`` (importing the
    real thing is a hard circular import — see the module comment). If the
    two ever diverge again, the canonical FDA-export table starts
    disagreeing with the legacy CTE table for the same event. Fail loudly.
    """
    assert set(BIZSTEP_TO_CTE_TYPE) == set(_EVENT_TYPE_MAP), (
        "bizStep map drift between shared.canonical_event and "
        "services.ingestion.app.epcis.normalization: "
        f"only-canonical={sorted(set(BIZSTEP_TO_CTE_TYPE) - set(_EVENT_TYPE_MAP))} "
        f"only-normalization={sorted(set(_EVENT_TYPE_MAP) - set(BIZSTEP_TO_CTE_TYPE))}"
    )


@pytest.mark.parametrize("uri", sorted(_EVENT_TYPE_MAP))
def test_every_authoritative_uri_round_trips(uri: str) -> None:
    """ALL keys of ``_EVENT_TYPE_MAP`` resolve to the matching ``CTEType``.

    The two entries whose authoritative value is ``growing`` have no
    ``CTEType`` member and no canonical DB representation — they must raise,
    never silently become a different CTE.
    """
    expected_value = _EVENT_TYPE_MAP[uri]

    if expected_value in _NON_CANONICAL_CTE_STRINGS:
        with pytest.raises(UnmappedBizStepError):
            _resolve_bizstep_to_cte_type(uri)
        return

    resolved = _resolve_bizstep_to_cte_type(uri)
    assert isinstance(resolved, CTEType)
    assert resolved.value == expected_value, (
        f"{uri}: canonical resolver says {resolved.value!r}, "
        f"authoritative _EVENT_TYPE_MAP says {expected_value!r}"
    )


@pytest.mark.parametrize("uri", sorted(_EVENT_TYPE_MAP))
def test_every_authoritative_uri_round_trips_end_to_end(uri: str) -> None:
    """Same assertion, but through the public ``normalize_epcis_event``."""
    expected_value = _EVENT_TYPE_MAP[uri]
    event = _epcis_event(uri)

    if expected_value in _NON_CANONICAL_CTE_STRINGS:
        with pytest.raises(UnmappedBizStepError):
            normalize_epcis_event(event, TENANT_ID)
        return

    canonical = normalize_epcis_event(event, TENANT_ID)
    assert canonical.event_type.value == expected_value
    assert canonical.epcis_biz_step == uri


# ---------------------------------------------------------------------------
# 3. The five URIs that were silently corrupted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("uri,expected", sorted(_PREVIOUSLY_BROKEN.items()))
def test_previously_broken_uris_no_longer_become_receiving(uri: str, expected: CTEType) -> None:
    canonical = normalize_epcis_event(_epcis_event(uri), TENANT_ID)
    assert canonical.event_type is expected
    # The specific corruption: all five used to land as RECEIVING.
    if expected is not CTEType.RECEIVING:
        assert canonical.event_type is not CTEType.RECEIVING


def test_previously_broken_uris_agree_with_legacy_normalization() -> None:
    """The whole point of #2815: both writers must agree on one event."""
    for uri, expected in _PREVIOUSLY_BROKEN.items():
        assert _EVENT_TYPE_MAP[uri] == expected.value
        assert normalize_epcis_event(_epcis_event(uri), TENANT_ID).event_type.value == _EVENT_TYPE_MAP[uri]


# ---------------------------------------------------------------------------
# 4. No silent default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "biz_step",
    [
        "urn:epcglobal:cbv:bizstep:not-a-real-step",
        "urn:epcglobal:cbv:bizstep:inspecting",
        "urn:fsma:traceability:teleporting",
        "receiving_dock",  # would have substring-matched "receiving" before
        "transshipping",  # would have substring-matched "shipping" before
        "totally bogus",
        "",
        "   ",
        None,
    ],
)
def test_unmapped_bizstep_raises_instead_of_defaulting_to_receiving(biz_step) -> None:
    with pytest.raises(UnmappedBizStepError):
        _resolve_bizstep_to_cte_type(biz_step)


def test_unmapped_bizstep_raises_from_normalize_epcis_event() -> None:
    event = _epcis_event("urn:epcglobal:cbv:bizstep:not-a-real-step")
    with pytest.raises(UnmappedBizStepError) as exc:
        normalize_epcis_event(event, TENANT_ID)
    # The message must name the offending value and the refusal.
    assert "not-a-real-step" in str(exc.value)
    assert "receiving" in str(exc.value)


def test_unmapped_bizstep_error_is_a_value_error() -> None:
    """Callers already wrap ``normalize_epcis_event`` in ``except
    ValueError`` for the #1249 quantity contract — keep that working."""
    assert issubclass(UnmappedBizStepError, ValueError)


# ---------------------------------------------------------------------------
# Backwards compatibility: the documented "or direct value" form
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token", sorted(t.value for t in CTEType))
def test_bare_canonical_cte_token_still_accepted(token: str) -> None:
    """``normalize_epcis_event`` has always documented "bizStep URI or
    direct value", and non-EPCIS callers/tests pass e.g. ``"shipping"``.
    Still an EXACT match against the CTEType value set — never a
    substring."""
    assert _resolve_bizstep_to_cte_type(token).value == token


def test_uri_lookup_is_case_insensitive_but_not_fuzzy() -> None:
    assert _resolve_bizstep_to_cte_type("URN:EPCGLOBAL:CBV:BIZSTEP:STORING") is CTEType.COOLING
    with pytest.raises(UnmappedBizStepError):
        # Trailing junk is NOT a substring hit any more.
        _resolve_bizstep_to_cte_type("urn:epcglobal:cbv:bizstep:storing-and-more")
