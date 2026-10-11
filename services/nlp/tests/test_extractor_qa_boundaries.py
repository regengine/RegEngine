"""Boundary and contract tests for services/nlp/app/extractors/ (fleet QA pass).

Covers gaps the existing suite leaves open:

* FSMA ``extract`` input boundaries: missing tenant variants, non-string
  text. The tenant-missing cases pin the documented ``E_MISSING_TENANT_ID``
  contract; the non-string cases prove the failure is a clear TypeError
  instead of an AttributeError deep inside classification.
* ``_ClassificationResult`` whole-object compatibility: hashability and
  ``.value`` / ``.name`` passthrough so future callers that forget to
  unpack still get DocumentType behavior instead of TypeError.
* Serializer completeness: the graph/review envelope must carry the GTIN
  and FTL scoping the extractor computed (#1104, #1116), and
  ``to_fsma_events`` must prefer the separately stored ``KDE.gtin`` over
  re-deriving it from the TLC prefix, plus carry ``tenant_id`` like the
  shared FSMAEvent schema allows.
* Extractor registry: known frameworks resolve, unknown ones raise.
* LLM extractor input boundaries: blank text short-circuits without
  spending an LLM call; None text raises TypeError; None jurisdiction
  maps to UNKNOWN.
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from services.nlp.app.extractors import get_extractor
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
from services.nlp.app.extractors.llm_extractor import LLMGenerativeExtractor

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

BOL_TEXT = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123
Consignee: Metro Distribution Center
Carrier: FastFreight LLC
Ship To: Metro DC
Ship From: Fresh Farms Warehouse
Ship Date: 11/05/2025
Freight: standard

Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
Date: 2025-11-05
"""


@pytest.fixture
def extractor():
    return FSMAExtractor()


def _result(ctes, review_required):
    return FSMAExtractionResult(
        document_id="doc-qa",
        tenant_id=TENANT,
        document_type=DocumentType.BILL_OF_LADING,
        ctes=ctes,
        extraction_timestamp="2026-01-01T00:00:00Z",
        confidence_level=(
            ExtractionConfidence.LOW if review_required else ExtractionConfidence.HIGH
        ),
        review_required=review_required,
    )


# ---------------------------------------------------------------------------
# FSMA extract input boundaries
# ---------------------------------------------------------------------------


class TestFSMAExtractInputBoundaries:
    def test_empty_tenant_raises_missing_tenant(self, extractor):
        with pytest.raises(ValueError, match="E_MISSING_TENANT_ID"):
            extractor.extract(BOL_TEXT, "doc-1", tenant_id="")

    def test_whitespace_tenant_raises_missing_tenant(self, extractor):
        with pytest.raises(ValueError, match="E_MISSING_TENANT_ID"):
            extractor.extract(BOL_TEXT, "doc-2", tenant_id="   ")

    def test_none_text_raises_typeerror(self, extractor):
        with pytest.raises(TypeError):
            extractor.extract(None, "doc-3", tenant_id=TENANT)

    def test_non_string_text_raises_typeerror(self, extractor):
        with pytest.raises(TypeError):
            extractor.extract(12345, "doc-4", tenant_id=TENANT)


# ---------------------------------------------------------------------------
# _ClassificationResult whole-object compatibility
# ---------------------------------------------------------------------------


class TestClassificationResultCompat:
    def test_unpacked_first_element_is_plain_document_type(self, extractor):
        doc_type, warning = extractor._classify_document(BOL_TEXT)
        assert type(doc_type) is DocumentType
        assert warning is None

    def test_whole_result_is_hashable_and_matches_enum(self, extractor):
        whole = extractor._classify_document(BOL_TEXT)
        assert hash(whole) == hash(DocumentType.BILL_OF_LADING)
        assert whole in {DocumentType.BILL_OF_LADING, DocumentType.INVOICE}

    def test_whole_result_exposes_value_and_name(self, extractor):
        whole = extractor._classify_document(BOL_TEXT)
        assert whole.value == "BOL"
        assert whole.name == "BILL_OF_LADING"

    def test_tie_warning_surfaced_on_unpack(self, extractor):
        tie_text = (
            "Ship to: Buyer Corp\nConsignee: Buyer Corp\n"
            "Payment Terms: Net 30\nTotal Due: $500.00\n"
        )
        doc_type, warning = extractor._classify_document(tie_text)
        assert doc_type == DocumentType.UNKNOWN
        assert warning is not None and "ambiguous" in warning.lower()


# ---------------------------------------------------------------------------
# Serializer completeness (GTIN, FTL, tenant)
# ---------------------------------------------------------------------------


class TestSerializerCompleteness:
    def _ftl_result(self):
        kde = KDE(
            traceability_lot_code="LOT-123",
            event_date="2025-11-05",
            gtin="00012345678901",
            product_description="Romaine Lettuce",
            is_ftl_covered=True,
            ftl_category="leafy greens",
        )
        return _result(
            [CTE(type=CTEType.SHIPPING, kdes=kde, confidence=0.9)],
            review_required=False,
        )

    def test_graph_envelope_carries_gtin_and_ftl(self, extractor):
        payload = extractor.to_graph_event(self._ftl_result())
        kdes = payload["ctes"][0]["kdes"]
        assert kdes["gtin"] == "00012345678901"
        assert kdes["is_ftl_covered"] is True
        assert kdes["ftl_category"] == "leafy greens"

    def test_review_envelope_carries_gtin_and_ftl(self, extractor):
        payload = extractor.to_review_event(self._ftl_result())
        kdes = payload["ctes"][0]["kdes"]
        assert kdes["gtin"] == "00012345678901"
        assert kdes["is_ftl_covered"] is True
        assert kdes["ftl_category"] == "leafy greens"

    def test_fsma_event_product_gtin_prefers_kde_gtin(self, extractor):
        events = extractor.to_fsma_events(self._ftl_result())
        assert events[0]["product"]["gtin"] == "00012345678901"

    def test_fsma_event_product_gtin_falls_back_to_tlc_prefix(self, extractor):
        kde = KDE(
            traceability_lot_code="00012345678901Lot-123",
            event_date="2025-11-05",
            product_description="Romaine Lettuce",
        )
        result = _result(
            [CTE(type=CTEType.SHIPPING, kdes=kde, confidence=0.9)],
            review_required=False,
        )
        events = extractor.to_fsma_events(result)
        assert events[0]["product"]["gtin"] == "00012345678901"

    def test_fsma_event_carries_tenant_id(self, extractor):
        events = extractor.to_fsma_events(self._ftl_result())
        assert events[0]["tenant_id"] == TENANT


# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------


class TestExtractorRegistry:
    def test_fsma_framework_resolves(self):
        assert isinstance(get_extractor("FSMA-204"), FSMAExtractor)

    def test_generic_framework_resolves(self):
        with patch(
            "services.nlp.app.extractors.llm_extractor.LLMClientFactory.create"
        ) as factory:
            factory.return_value = Mock(model="test-model")
            assert isinstance(get_extractor("GENERIC"), LLMGenerativeExtractor)

    def test_unknown_framework_raises(self):
        with pytest.raises(ValueError, match="Unknown extractor framework"):
            get_extractor("NOPE-999")


# ---------------------------------------------------------------------------
# LLM extractor input boundaries
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    with patch(
        "services.nlp.app.extractors.llm_extractor.LLMClientFactory.create"
    ) as factory:
        mock = Mock()
        mock.model = "test-model"
        factory.return_value = mock
        yield mock


class TestLLMExtractorInputBoundaries:
    def test_empty_text_short_circuits_without_llm_call(self, mock_client):
        mock_client.generate.return_value = json.dumps({"results": []})
        extractor = LLMGenerativeExtractor()
        assert extractor.extract("", "US") == []
        mock_client.generate.assert_not_called()

    def test_whitespace_text_short_circuits_without_llm_call(self, mock_client):
        mock_client.generate.return_value = json.dumps({"results": []})
        extractor = LLMGenerativeExtractor()
        assert extractor.extract("   \n  ", "US") == []
        mock_client.generate.assert_not_called()

    def test_none_text_raises_typeerror(self, mock_client):
        extractor = LLMGenerativeExtractor()
        with pytest.raises(TypeError):
            extractor.extract(None, "US")

    def test_none_jurisdiction_maps_to_unknown(self, mock_client):
        mock_client.generate.return_value = json.dumps({"results": []})
        extractor = LLMGenerativeExtractor()
        extractor.extract("Some regulation text about food safety.", None)
        args, _ = mock_client.generate.call_args
        assert "JURISDICTION: UNKNOWN" in args[0]
