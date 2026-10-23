"""Data-free drift checks for the two official bizStep mappings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.epcis.normalization import _EVENT_TYPE_MAP  # noqa: E402
from shared.canonical_event import (  # noqa: E402
    BIZSTEP_TO_CTE_TYPE,
    CTEType,
    UnmappedBizStepError,
    _resolve_bizstep_to_cte_type,
)

_NON_CANONICAL_CTE_STRINGS = {"growing"}
_PREVIOUSLY_BROKEN = {
    "urn:fsma:traceability:transformation": CTEType.TRANSFORMATION,
    "urn:fsma:traceability:initial_packing": CTEType.INITIAL_PACKING,
    "urn:fsma:traceability:first_land_based_receiving": CTEType.FIRST_LAND_BASED_RECEIVING,
    "urn:epcglobal:cbv:bizstep:packing": CTEType.INITIAL_PACKING,
    "urn:epcglobal:cbv:bizstep:storing": CTEType.COOLING,
}


def test_canonical_map_covers_exactly_the_authoritative_key_set() -> None:
    assert set(BIZSTEP_TO_CTE_TYPE) == set(_EVENT_TYPE_MAP)


@pytest.mark.parametrize("uri", sorted(_EVENT_TYPE_MAP))
def test_every_authoritative_uri_round_trips(uri: str) -> None:
    expected_value = _EVENT_TYPE_MAP[uri]
    if expected_value in _NON_CANONICAL_CTE_STRINGS:
        with pytest.raises(UnmappedBizStepError):
            _resolve_bizstep_to_cte_type(uri)
    else:
        assert _resolve_bizstep_to_cte_type(uri).value == expected_value


@pytest.mark.parametrize("uri,expected", sorted(_PREVIOUSLY_BROKEN.items()))
def test_previously_broken_uris_no_longer_become_receiving(uri: str, expected: CTEType) -> None:
    resolved = _resolve_bizstep_to_cte_type(uri)
    assert resolved is expected
    assert resolved is not CTEType.RECEIVING


def test_previously_broken_uris_agree_with_legacy_normalization() -> None:
    for uri, expected in _PREVIOUSLY_BROKEN.items():
        assert _EVENT_TYPE_MAP[uri] == expected.value
        assert _resolve_bizstep_to_cte_type(uri).value == _EVENT_TYPE_MAP[uri]


@pytest.mark.parametrize("biz_step", ["", "   ", None])
def test_unmapped_bizstep_raises_instead_of_defaulting_to_receiving(biz_step) -> None:
    with pytest.raises(UnmappedBizStepError):
        _resolve_bizstep_to_cte_type(biz_step)


def test_unmapped_bizstep_error_is_a_value_error() -> None:
    assert issubclass(UnmappedBizStepError, ValueError)


@pytest.mark.parametrize("token", sorted(t.value for t in CTEType))
def test_bare_canonical_cte_token_still_accepted(token: str) -> None:
    assert _resolve_bizstep_to_cte_type(token).value == token


def test_uri_lookup_is_case_insensitive_but_not_fuzzy() -> None:
    uri = next(iter(_EVENT_TYPE_MAP))
    assert _resolve_bizstep_to_cte_type(uri.upper()).value == _EVENT_TYPE_MAP[uri]
    with pytest.raises(UnmappedBizStepError):
        _resolve_bizstep_to_cte_type(uri + "/")
