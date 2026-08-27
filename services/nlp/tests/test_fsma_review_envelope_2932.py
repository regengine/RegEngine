"""Regression tests for #2932 — the HITL review envelope must carry the
CTEs that triggered review.

``route_extraction`` used to build the ``nlp.needs_review`` payload with
``to_graph_event``, whose whole job is to drop CTEs missing the KDE
minimums (TLC + Event Date). So a document routed to review *because* a
CTE lacked its event date produced a review item from which that CTE had
been filtered out — and the partial extraction was persisted nowhere else.

The review branch now uses ``to_review_event``, which emits every CTE plus
a per-CTE ``missing_kdes`` list. The ``graph.update`` branch is unchanged.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import (
    CTEType,
    DocumentType,
    FSMAExtractor,
)
from services.nlp.app.extractors.fsma_types import (
    CTE,
    KDE,
    ExtractionConfidence,
    FSMAExtractionResult,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"

# A BOL identical in shape to the golden sample except that the Ship Date
# line is absent, so the extracted CTE has a TLC but no event date — the
# KDE-minimum gate fires and the document is routed to HITL.
SAMPLE_BOL_NO_DATE = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123

Ship To: Metro Distribution Center

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
"""


@pytest.fixture
def extractor():
    return FSMAExtractor(confidence_threshold=0.85)


def _cte(tlc=None, event_date=None, cte_type=CTEType.SHIPPING, confidence=0.9):
    return CTE(
        type=cte_type,
        kdes=KDE(traceability_lot_code=tlc, event_date=event_date),
        confidence=confidence,
    )


def _result(ctes, review_required):
    return FSMAExtractionResult(
        document_id="doc-2932",
        tenant_id=TENANT_ID,
        document_type=DocumentType.BILL_OF_LADING,
        ctes=ctes,
        extraction_timestamp="2026-01-01T00:00:00Z",
        confidence_level=(
            ExtractionConfidence.LOW if review_required else ExtractionConfidence.HIGH
        ),
        review_required=review_required,
    )


class TestReviewEnvelopeCarriesDeficientCTEs:
    """The review payload must contain the CTEs that triggered review."""

    def test_dateless_bol_routes_to_review_with_its_cte(self, extractor):
        result = extractor.extract(SAMPLE_BOL_NO_DATE, "doc-2932-a", tenant_id=TENANT_ID)

        # Precondition: extraction produced a CTE with a TLC but no date.
        assert result.ctes
        assert result.ctes[0].kdes.traceability_lot_code == "L-2025-1105-A"
        assert result.ctes[0].kdes.event_date is None
        assert result.review_required is True

        envelope = extractor.route_extraction(result)

        assert envelope["topic"] == "nlp.needs_review"
        payload_ctes = envelope["payload"]["ctes"]
        # Pre-fix this list was empty — the reviewer got nothing to complete.
        assert len(payload_ctes) == len(result.ctes)
        assert payload_ctes[0]["kdes"]["traceability_lot_code"] == "L-2025-1105-A"
        assert payload_ctes[0]["kdes"]["product_description"] == "Romaine Lettuce Hearts 12ct"
        assert payload_ctes[0]["event_id"] == result.ctes[0].event_id

    def test_review_payload_names_the_missing_kdes(self, extractor):
        result = extractor.extract(SAMPLE_BOL_NO_DATE, "doc-2932-b", tenant_id=TENANT_ID)

        envelope = extractor.route_extraction(result)

        assert envelope["payload"]["ctes"][0]["missing_kdes"] == ["event_date"]

    def test_missing_kdes_lists_both_minimums_when_both_absent(self, extractor):
        result = _result([_cte(tlc=None, event_date=None)], review_required=True)

        envelope = extractor.route_extraction(result)

        assert envelope["topic"] == "nlp.needs_review"
        assert envelope["payload"]["ctes"][0]["missing_kdes"] == [
            "traceability_lot_code",
            "event_date",
        ]

    def test_qualified_ctes_survive_alongside_deficient_ones(self, extractor):
        qualified = _cte(tlc="LOT-OK", event_date="2025-11-05")
        deficient = _cte(tlc="LOT-GAP", event_date=None)
        result = _result([qualified, deficient], review_required=True)

        payload_ctes = extractor.route_extraction(result)["payload"]["ctes"]

        assert [c["kdes"]["traceability_lot_code"] for c in payload_ctes] == [
            "LOT-OK",
            "LOT-GAP",
        ]
        # A graph-eligible CTE reports no gaps.
        assert payload_ctes[0]["missing_kdes"] == []
        assert payload_ctes[1]["missing_kdes"] == ["event_date"]

    def test_review_envelope_keeps_graph_envelope_shape(self, extractor):
        result = _result([_cte(tlc="LOT-GAP", event_date=None)], review_required=True)

        review_event = extractor.to_review_event(result)
        graph_event = extractor.to_graph_event(result)

        assert set(review_event) == set(graph_event)
        assert review_event["event_type"] == "fsma.extraction"
        assert review_event["tenant_id"] == TENANT_ID
        assert review_event["risk_assessment"]["review_required"] is True


class TestGraphPathUnchanged:
    """``graph.update`` must keep the qualified-only filter."""

    def test_graph_route_emits_only_qualified_ctes(self, extractor):
        qualified = _cte(tlc="LOT-OK", event_date="2025-11-05")
        deficient = _cte(tlc="LOT-GAP", event_date=None)
        result = _result([qualified, deficient], review_required=False)

        envelope = extractor.route_extraction(result)

        assert envelope["topic"] == "graph.update"
        payload_ctes = envelope["payload"]["ctes"]
        assert len(payload_ctes) == 1
        assert payload_ctes[0]["kdes"]["traceability_lot_code"] == "LOT-OK"
        # The graph envelope carries no review-only annotation.
        assert "missing_kdes" not in payload_ctes[0]

    def test_to_graph_event_still_filters_a_review_required_result(self, extractor):
        result = _result([_cte(tlc="LOT-GAP", event_date=None)], review_required=True)

        assert extractor.to_graph_event(result)["ctes"] == []
