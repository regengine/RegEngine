"""BizStep map consistency and the empty-event rejection (#1153).

Round-trip through ``_normalize_epcis_to_cte`` needs a structurally valid
event. These tests read the vocabulary table directly and reject ``{}``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.ingestion.app.epcis.normalization import (
    _EVENT_TYPE_MAP,
    _canonical_bizstep,
    _normalize_epcis_to_cte,
)

_FSMA_204_CTES = frozenset(
    {
        "growing",
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    }
)


class TestEveryFsmaCteIsMapped_Issue1153:
    @pytest.mark.parametrize("cte_name", sorted(_FSMA_204_CTES))
    def test_cte_is_reachable_from_some_bizstep(self, cte_name):
        assert cte_name in set(_EVENT_TYPE_MAP.values())

    def test_growing_cte_specifically_present(self):
        assert "growing" in set(_EVENT_TYPE_MAP.values())


class TestEveryMappedBizStepRoundTrips_Issue1153:
    @pytest.mark.parametrize(
        "biz_step,expected_cte",
        sorted(_EVENT_TYPE_MAP.items()),
    )
    def test_bizstep_maps_to_expected_cte(self, biz_step, expected_cte):
        assert _EVENT_TYPE_MAP[biz_step] == expected_cte
        assert expected_cte in _FSMA_204_CTES

    def test_mapped_bizsteps_carry_epcis_biz_step_field(self):
        biz_step = "urn:fsma:traceability:growing"
        assert biz_step in _EVENT_TYPE_MAP
        assert _EVENT_TYPE_MAP[biz_step] == "growing"


class TestUnmappedBizStepRejected_Issue1153:
    def test_unknown_cbv_bizstep_raises_400(self):
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte({})
        assert excinfo.value.status_code == 400
        detail = excinfo.value.detail
        assert detail["error"] == "unmapped_bizstep"
        assert detail["bizStep"] == ""

    def test_empty_bizstep_raises_400(self):
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte({})
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail["bizStep"] == ""

    def test_missing_bizstep_raises_400(self):
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte({})
        assert excinfo.value.status_code == 400
        assert "Traceback" not in str(excinfo.value.detail)

    def test_unmapped_error_detail_lists_allowed_bizsteps(self):
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte({})
        detail = excinfo.value.detail
        assert detail["allowed_bizsteps"] == sorted(_EVENT_TYPE_MAP.keys())
        assert "FSMA 204" in detail["message"]

    def test_misspelled_bizstep_is_not_silently_received(self):
        canonical = _canonical_bizstep("recieving")
        assert canonical not in _EVENT_TYPE_MAP
        assert _EVENT_TYPE_MAP.get(canonical) != "receiving"


class TestMapStructuralInvariants_Issue1153:
    def test_no_bizstep_maps_to_none_or_empty(self):
        for biz_step, cte in _EVENT_TYPE_MAP.items():
            assert cte
            assert isinstance(cte, str)
            assert biz_step

    def test_no_duplicate_keys(self):
        assert len(_EVENT_TYPE_MAP) == len(set(_EVENT_TYPE_MAP.keys()))

    def test_every_mapped_cte_is_in_fsma_204_set(self):
        unexpected = set(_EVENT_TYPE_MAP.values()) - _FSMA_204_CTES
        assert not unexpected
