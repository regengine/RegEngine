"""856 carrier extraction reads TD5 by element position.

A live run exported ``Carrier: 2`` to the FDA CSV for ``TD5**2*ColdExpress``.
The extractor took the first non-empty element, which was TD502, the
identification code qualifier. Only TD503 (identification code) and TD505
(routing text) name a carrier. Inputs are the synthetic corpus fixture with
its TD5 segment replaced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.edi_ingestion.extractors import _extract_856_fields  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402

FIXTURE = service_dir / "tests" / "fixtures" / "edi_corpus" / "asn_856.edi"
FIXTURE_TD5 = "TD5**2*ColdExpress"


def _carrier_for(td5_segments: str) -> str | None:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert FIXTURE_TD5 in raw
    return _extract_856_fields(_parse_x12_segments(raw.replace(FIXTURE_TD5, td5_segments)))["carrier"]


@pytest.mark.parametrize(
    ("td5", "expected"),
    [
        pytest.param("TD5**2*ColdExpress", "ColdExpress", id="td503-after-qualifier"),
        pytest.param("TD5*B*2*FDEG*M*FedEx Ground", "FDEG", id="td503-beats-routing-text"),
        pytest.param("TD5****M*Cold Chain Route", "Cold Chain Route", id="td505-fallback"),
        pytest.param("TD5**2* *M* ", None, id="blank-elements-are-unset"),
    ],
)
def test_carrier_comes_from_td503_then_td505(td5: str, expected: str | None) -> None:
    assert _carrier_for(td5) == expected


@pytest.mark.parametrize(
    "td5",
    [
        pytest.param("TD5**2", id="qualifier-only"),
        pytest.param("TD5****M", id="transport-method-only"),
    ],
)
def test_qualifier_and_method_codes_are_not_carriers(td5: str) -> None:
    assert _carrier_for(td5) is None


def test_first_td5_naming_a_carrier_wins() -> None:
    carrier = _carrier_for("TD5**2~TD5**2*ColdExpress~TD5**2*SecondCarrier")
    assert carrier == "ColdExpress"
