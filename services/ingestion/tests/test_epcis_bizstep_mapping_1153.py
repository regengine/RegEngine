"""Regression tests for issue #1153 — EPCIS bizStep → FSMA CTE mapping.

Before the fix, ``_EVENT_TYPE_MAP`` in
``services/ingestion/app/epcis/normalization.py`` was missing the
``growing`` CTE entirely, and unmapped bizSteps silently defaulted to
``receiving``. A ``growing`` event therefore showed up as a ``receiving``
event in the compliance graph and broke FSMA 204 recall lookback.

The fix (landed on main before this regression suite) added every FSMA
204 CTE to the map and made unmapped bizSteps raise ``HTTPException 400``
instead of quietly reclassifying. These tests lock in that behavior:

- Every FSMA 204 CTE has at least one bizStep URI that maps to it.
- Every URI in ``_EVENT_TYPE_MAP`` round-trips to the expected CTE.
- An unmapped URI raises ``HTTPException 400`` (not a silent default).
- An empty / missing bizStep raises ``HTTPException 400``.

Why unit tests and not HTTP: the defect is in the pure mapping function
``_normalize_epcis_to_cte``. Keeping the test at that layer makes the
regression obvious from a one-line stacktrace if the map is ever
regressed — no TestClient setup, no test-harness flake surface.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.ingestion.app.epcis.normalization import (
    _EVENT_TYPE_MAP,
    _normalize_epcis_to_cte,
)


# The seven FSMA 204 Critical Tracking Events (CTEs) every compliant
# traceability graph must be able to represent. A fix for #1153 that
# omits any of these from the map would silently drop that CTE class
# from recall lookback — a direct FDA 24-hour response failure.
_FSMA_204_CTES = frozenset({
    "growing",
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    # transformation is the eighth tracked event type — not one of the
    # seven CTEs under the regulation but required by the canonical
    # event schema and FSMA reconciliation paths.
    "transformation",
})


def _event_with_bizstep(biz_step: str) -> dict:
    """Minimal EPCIS event shell that exercises ``_normalize_epcis_to_cte``
    without tripping other field validation. Extract helpers tolerate
    missing lists / dicts, so we only need to set ``bizStep``."""
    return {
        "type": "ObjectEvent",
        "eventTime": "2026-04-18T09:30:00.000-05:00",
        "eventTimeZoneOffset": "-05:00",
        "action": "OBSERVE",
        "bizStep": biz_step,
        "ilmd": {
            "cbvmda:lotNumber": "LOT-1153",
            "fsma:traceabilityLotCode": "00012345678901-LOT1153",
        },
    }


# ── All seven FSMA CTEs are representable ───────────────────────────────────


class TestEveryFsmaCteIsMapped_Issue1153:
    """If any CTE ends up with no bizStep URI mapping to it, ingestion
    for that CTE class is impossible and FDA lookback for that event
    type breaks. Lock in coverage of every one."""

    @pytest.mark.parametrize("cte_name", sorted(_FSMA_204_CTES))
    def test_cte_is_reachable_from_some_bizstep(self, cte_name):
        mapped_ctes = set(_EVENT_TYPE_MAP.values())
        assert cte_name in mapped_ctes, (
            f"#1153: FSMA CTE '{cte_name}' has no bizStep URI mapping. "
            f"Ingestion cannot produce this CTE class — recall lookback "
            f"for '{cte_name}' events is broken."
        )

    def test_growing_cte_specifically_present(self):
        """The defect that opened #1153 was specifically the missing
        'growing' CTE. This keeps that one pinned even if someone
        regresses the broader set."""
        assert "growing" in set(_EVENT_TYPE_MAP.values()), (
            "#1153: the 'growing' CTE must be reachable from at least "
            "one bizStep URI."
        )


# ── Every mapped URI round-trips to the expected CTE ────────────────────────


class TestEveryMappedBizStepRoundTrips_Issue1153:
    """Every URI in ``_EVENT_TYPE_MAP`` must actually produce its mapped
    CTE when fed through ``_normalize_epcis_to_cte``. A silent rewrite
    in that function would defeat the whole mapping."""

    @pytest.mark.parametrize(
        "biz_step,expected_cte",
        sorted(_EVENT_TYPE_MAP.items()),
    )
    def test_bizstep_maps_to_expected_cte(self, biz_step, expected_cte):
        event = _event_with_bizstep(biz_step)
        normalized = _normalize_epcis_to_cte(event)
        assert normalized["event_type"] == expected_cte, (
            f"#1153: bizStep {biz_step!r} should map to {expected_cte!r}, "
            f"got {normalized['event_type']!r}"
        )

    def test_mapped_bizsteps_carry_epcis_biz_step_field(self):
        """The normalized event must preserve the original bizStep so
        downstream audit can see the raw URI (compliance-forensic
        requirement). Spot-check the growing path."""
        event = _event_with_bizstep("urn:fsma:traceability:growing")
        normalized = _normalize_epcis_to_cte(event)
        assert normalized["epcis_biz_step"] == "urn:fsma:traceability:growing"
        assert normalized["event_type"] == "growing"


# ── Unmapped bizSteps raise 400 instead of silently defaulting ──────────────


class TestUnmappedBizStepRejected_Issue1153:
    """Pre-fix, any unmapped or misspelled bizStep fell through to
    'receiving'. Post-fix, it must raise HTTPException 400 with enough
    detail for the client to correct the URI."""

    def test_unknown_cbv_bizstep_raises_400(self):
        event = _event_with_bizstep(
            "urn:epcglobal:cbv:bizstep:not-a-real-step",
        )
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte(event)
        assert excinfo.value.status_code == 400
        detail = excinfo.value.detail
        assert detail["error"] == "unmapped_bizstep"
        assert detail["bizStep"] == "urn:epcglobal:cbv:bizstep:not-a-real-step"

    def test_empty_bizstep_raises_400(self):
        event = _event_with_bizstep("")
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte(event)
        assert excinfo.value.status_code == 400

    def test_missing_bizstep_raises_400(self):
        """No bizStep key at all — should still fail loudly, not default
        to receiving."""
        event = {
            "type": "ObjectEvent",
            "eventTime": "2026-04-18T09:30:00.000-05:00",
            "action": "OBSERVE",
            # no bizStep
        }
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte(event)
        assert excinfo.value.status_code == 400

    def test_unmapped_error_detail_lists_allowed_bizsteps(self):
        """The 400 detail must help the client fix the URI — the old
        silent-default was a UX problem too. Lock in that the allowed
        list is attached."""
        event = _event_with_bizstep(
            "urn:epcglobal:cbv:bizstep:not-a-real-step",
        )
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte(event)
        detail = excinfo.value.detail
        assert "allowed_bizsteps" in detail
        assert "urn:epcglobal:cbv:bizstep:receiving" in detail["allowed_bizsteps"]
        assert "urn:fsma:traceability:growing" in detail["allowed_bizsteps"]

    def test_misspelled_bizstep_is_not_silently_received(self):
        """Concrete example from the issue: typo → must NOT fall through
        to 'receiving'."""
        event = _event_with_bizstep("urn:epcglobal:cbv:bizstep:recieving")  # typo
        with pytest.raises(HTTPException):
            _normalize_epcis_to_cte(event)


# ── Cross-check: unused map entries are still structurally valid ────────────


class TestMapStructuralInvariants_Issue1153:
    def test_no_bizstep_maps_to_none_or_empty(self):
        for biz_step, cte in _EVENT_TYPE_MAP.items():
            assert cte, f"{biz_step!r} maps to empty CTE {cte!r}"
            assert isinstance(cte, str)

    def test_no_duplicate_keys(self):
        """Defensive: dict-literal duplicates silently win-last. This
        asserts the construction didn't eat an intended URI."""
        # The dict itself can't hold dupes; this assertion is structural.
        assert len(_EVENT_TYPE_MAP) == len(set(_EVENT_TYPE_MAP.keys()))

    def test_every_mapped_cte_is_in_fsma_204_set(self):
        """The map's values must stay within the canonical FSMA CTE set.
        A stray value (e.g. 'widget_received') would mean ingestion is
        producing event_types that downstream rules don't know about."""
        unexpected = set(_EVENT_TYPE_MAP.values()) - _FSMA_204_CTES
        assert not unexpected, (
            f"#1153: bizStep map contains non-FSMA CTEs: {unexpected}. "
            f"Downstream rules/fsma_rules.json won't match these."
        )
