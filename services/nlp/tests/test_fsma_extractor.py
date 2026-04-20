"""Tests for FSMA 204 Extractor."""

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


@pytest.fixture
def extractor():
    return FSMAExtractor(confidence_threshold=0.85)


SAMPLE_BOL_TEXT = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123

Ship To: Metro Distribution Center
Ship Date: 11/05/2025

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
"""

SAMPLE_INVOICE_TEXT = """
INVOICE #INV-2025-1234
Bill To: Restaurant Supply Co.
PO Number: PO-8765

Product: Fresh Cut Spinach
Batch #: BATCH-2025-1105-B
Qty: 100 units
Date: 2025-11-05
"""

SAMPLE_PRODUCTION_LOG = """
PRODUCTION BATCH RECORD
Manufacturing Date: 2025-11-04
Quality Control Approved

Lot Record: LOT-2025-1104-PROD
Product: Chopped Romaine Mix
Kill Step: Chlorine Wash 50ppm
Output Qty: 200 cases
"""

SAMPLE_TLC_SOURCE_FDA = """
Packed By: Sunshine Produce Co. (TLC Source) FDA Reg 12345678901
Lot: TLC-98765
Quantity: 20 cases
Date: 2025-11-05
"""


class TestDocumentClassification:
    """Test document type classification."""

    def test_classify_bill_of_lading(self, extractor):
        """Test BOL document classification."""
        doc_type = extractor._classify_document(SAMPLE_BOL_TEXT)
        assert doc_type == DocumentType.BILL_OF_LADING

    def test_classify_invoice(self, extractor):
        """Test invoice document classification."""
        doc_type = extractor._classify_document(SAMPLE_INVOICE_TEXT)
        assert doc_type == DocumentType.INVOICE

    def test_classify_production_log(self, extractor):
        """Test production log document classification."""
        doc_type = extractor._classify_document(SAMPLE_PRODUCTION_LOG)
        assert doc_type == DocumentType.PRODUCTION_LOG

    def test_classify_unknown(self, extractor):
        """Test unknown document type."""
        doc_type = extractor._classify_document("Random text with no indicators")
        assert doc_type == DocumentType.UNKNOWN


class TestLotCodeExtraction:
    """Test extraction of Traceability Lot Codes."""

    def test_extract_lot_code_from_bol(self, extractor):
        """Test extraction of Lot Code from BOL."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert len(result.ctes) > 0
        assert result.ctes[0].kdes.traceability_lot_code is not None
        # Should combine GTIN + Lot
        assert "L-2025-1105-A" in result.ctes[0].kdes.traceability_lot_code

    def test_extract_batch_code(self, extractor):
        """#1288 — invoices are not CTE events.  The extractor must return
        document_type=INVOICE and an empty CTE list rather than routing
        invoice data into a SHIPPING CTE."""
        result = extractor.extract(SAMPLE_INVOICE_TEXT, "test-doc-002", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type.value == "INVOICE"
        assert result.ctes == [], (
            "Invoice documents must not produce CTE events (#1288)"
        )

    def test_gtin_not_prepended_to_lot(self, extractor):
        """Regression guard for #1104 — the TLC must be preserved
        verbatim from the document. Pre-fix, any 14-digit number in
        the document was concatenated in front of the lot code,
        mutating the originator-assigned TLC and breaking traceability
        (21 CFR §1.1320 defines the TLC as assigned by the originator).
        GTIN is now stored separately in ``KDE.gtin``."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-003", tenant_id="11111111-1111-1111-1111-111111111111")

        tlc = result.ctes[0].kdes.traceability_lot_code
        assert tlc is not None
        assert not tlc.startswith("00012345678901"), (
            f"TLC was mutated by GTIN prepend: {tlc!r} — #1104 regression"
        )
        # GTIN is now stored on its own KDE field.
        assert result.ctes[0].kdes.gtin == "00012345678901"


class TestQuantityExtraction:
    """Test extraction of quantity and unit."""

    def test_extract_quantity_from_bol(self, extractor):
        """Test extraction of quantity from BOL."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-004", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].kdes.quantity == 50.0
        assert result.ctes[0].kdes.unit_of_measure == "cases"

    def test_extract_quantity_from_invoice(self, extractor):
        """#1288 — invoices are not CTE events; no CTE is emitted so there is
        no quantity to assert against.  Verify the document is recognised as an
        INVOICE and produces zero CTEs rather than a phantom SHIPPING CTE."""
        result = extractor.extract(SAMPLE_INVOICE_TEXT, "test-doc-005", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type.value == "INVOICE"
        assert result.ctes == [], "Invoice must not produce CTE events (#1288)"


class TestLocationExtraction:
    """Test extraction of location identifiers."""

    def test_extract_gln(self, extractor):
        """Test extraction of GLN location identifier."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-006", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].kdes.location_identifier == "urn:gln:1234567890123"

    def test_missing_location(self, extractor):
        """Test warning when location is missing.

        Plain lot/quantity text has no doc-type indicators so it classifies as
        UNKNOWN (#1288 — no silent SHIPPING fallback). The extractor emits no
        CTEs but the result still carries review warnings.
        """
        text = "Lot: L-2025-001\nQuantity: 50 cases"
        result = extractor.extract(text, "test-doc-007", tenant_id="11111111-1111-1111-1111-111111111111")

        # Document type is unresolved → no CTEs emitted
        assert result.document_type == DocumentType.UNKNOWN
        assert result.ctes == []
        # A review warning must still be present
        assert len(result.warnings) > 0


class TestDateExtraction:
    """Test extraction and normalization of dates."""

    def test_extract_date_mm_dd_yyyy(self, extractor):
        """Test extraction of MM/DD/YYYY date format."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-008", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].kdes.event_date == "2025-11-05"

    def test_extract_date_iso(self, extractor):
        """#1288 — invoices produce no CTEs; verify INVOICE classification
        rather than attempting to read a CTE date that no longer exists."""
        result = extractor.extract(SAMPLE_INVOICE_TEXT, "test-doc-009", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type.value == "INVOICE"
        assert result.ctes == []


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_high_confidence_with_all_fields(self, extractor):
        """Test high confidence when all required fields present."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-010", tenant_id="11111111-1111-1111-1111-111111111111")

        # BOL has lot code, quantity, location, date = 4/4 required fields
        assert result.ctes[0].confidence >= 0.75

    def test_low_confidence_with_missing_fields(self, extractor):
        """#1288 — minimal text with no doc-type indicators classifies as UNKNOWN
        and emits no CTEs (rather than a silent SHIPPING CTE at low confidence).
        Verify the result is flagged for review."""
        text = "Lot: L-2025-001"  # No doc-type keywords → UNKNOWN
        result = extractor.extract(text, "test-doc-011", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.UNKNOWN
        assert result.ctes == []
        assert result.review_required is True


class TestWarnings:
    """Test warning generation."""

    def test_warnings_for_missing_tlc(self, extractor):
        """Test warnings generated for missing TLC.

        'Ship Date' + 'Quantity' has no doc-type indicators (#1288), so the
        extractor now returns UNKNOWN with no CTEs.  The result should still
        carry at least one review warning.
        """
        text = "Ship Date: 11/05/2025\nQuantity: 50 cases"
        result = extractor.extract(text, "test-doc-012", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.UNKNOWN
        assert result.ctes == []
        assert len(result.warnings) > 0

    def test_warnings_for_low_confidence(self, extractor):
        """Test warnings for unclassifiable / low-confidence documents (#1288).

        A minimal doc with no recognised indicators now returns UNKNOWN + no CTEs
        instead of a low-confidence SHIPPING CTE.
        """
        text = "Lot: ABC123"  # Minimal document — no doc-type keywords
        result = extractor.extract(text, "test-doc-013", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.UNKNOWN
        assert result.ctes == []
        assert result.review_required is True

    def test_no_cte_warning(self, extractor):
        """Test warning when no CTEs can be extracted."""
        text = ""
        result = extractor.extract(text, "test-doc-014", tenant_id="11111111-1111-1111-1111-111111111111")

        assert any("No CTEs extracted" in w for w in result.warnings)


class TestCTETypeAssignment:
    """Test CTE type assignment based on document type."""

    def test_cte_type_shipping_for_bol(self, extractor):
        """Test CTE type assignment for BOL."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-015", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].type == CTEType.SHIPPING

    def test_cte_type_transformation_for_production(self, extractor):
        """Test CTE type assignment for production log."""
        result = extractor.extract(SAMPLE_PRODUCTION_LOG, "test-doc-016", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].type == CTEType.TRANSFORMATION


class TestGraphEventConversion:
    """Test conversion to graph event format."""

    def test_to_graph_event_format(self, extractor):
        """Test conversion to graph event format."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-017", tenant_id="11111111-1111-1111-1111-111111111111")
        graph_event = extractor.to_graph_event(result)

        assert graph_event["event_type"] == "fsma.extraction"
        assert graph_event["document_type"] == "BOL"
        assert len(graph_event["ctes"]) > 0
        assert "traceability_lot_code" in graph_event["ctes"][0]["kdes"]

    def test_graph_event_has_timestamp(self, extractor):
        """Test that graph event includes timestamp."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-018", tenant_id="11111111-1111-1111-1111-111111111111")
        graph_event = extractor.to_graph_event(result)

        assert "timestamp" in graph_event
        assert graph_event["timestamp"].endswith("Z")


class TestTLCSourceFDARegistration:
    """Test extraction of TLC Source FDA registration numbers."""

    def test_extract_tlc_source_fda_reg(self, extractor):
        """Ensure FDA Reg near TLC source cues is captured."""
        result = extractor.extract(SAMPLE_TLC_SOURCE_FDA, "test-doc-024", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.ctes[0].kdes.tlc_source_fda_reg == "fda:12345678901"
        # With no GLN present, FDA reg should backfill location identifier
        assert result.ctes[0].kdes.location_identifier == "fda:12345678901"

    def test_graph_event_includes_tlc_source_fda_reg(self, extractor):
        """Graph event should emit TLC source FDA registration."""
        result = extractor.extract(SAMPLE_TLC_SOURCE_FDA, "test-doc-025", tenant_id="11111111-1111-1111-1111-111111111111")
        graph_event = extractor.to_graph_event(result)

        assert graph_event["ctes"][0]["kdes"]["tlc_source_fda_reg"] == "fda:12345678901"


class TestTLCFormatValidation:
    """Test TLC format validation and warnings."""

    def test_non_gs1_tlc_warning(self, extractor):
        """Test that non-GS1 compliant TLCs generate warnings."""
        text = "Lot: ABC\nDate: 2025-11-05"  # Too short
        result = extractor.extract(text, "test-doc-019", tenant_id="11111111-1111-1111-1111-111111111111")

        # Should extract but warn about format
        if result.ctes and result.ctes[0].kdes.traceability_lot_code:
            assert any("GS1 compliant" in w or "Missing" in w for w in result.warnings)

    def test_valid_format_no_warning(self, extractor):
        """#1288 — text with GTIN/Lot/Qty/GLN/Date but no doc-type keywords
        is now UNKNOWN with no CTEs.  Validate doc type is UNKNOWN rather
        than asserting a CTE that no longer exists."""
        text = "GTIN: 00012345678901\nLot: LOT-2025-A\nQuantity: 50 cases\nGLN: 1234567890123\nDate: 2025-11-05"
        result = extractor.extract(text, "test-doc-020", tenant_id="11111111-1111-1111-1111-111111111111")

        # No recognised doc-type indicators → UNKNOWN, no CTE emitted
        assert result.document_type == DocumentType.UNKNOWN
        assert result.ctes == []


class TestExtractionResult:
    """Test FSMAExtractionResult structure."""

    def test_result_has_document_id(self, extractor):
        """Test that result includes document ID."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "my-custom-doc-id", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_id == "my-custom-doc-id"

    def test_result_has_document_type(self, extractor):
        """Test that result includes document type."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-021", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.BILL_OF_LADING

    def test_result_has_timestamp(self, extractor):
        """Test that result includes extraction timestamp."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-022", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.extraction_timestamp is not None
        assert result.extraction_timestamp.endswith("Z")

    def test_result_stores_raw_text(self, extractor):
        """Test that result stores raw text (truncated)."""
        result = extractor.extract(SAMPLE_BOL_TEXT, "test-doc-023", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.raw_text is not None
        assert len(result.raw_text) <= 1000


# Sample BOL with GTIN-14 + Lot format for 7 KDE testing
SAMPLE_BOL_WITH_GTIN14 = """
BILL OF LADING
Shipper: Fresh Farms Inc.
Ship From GLN: 1234567890123
Ship To GLN: 9876543210987

Ship To: Metro Distribution Center
Ship Date: 11/05/2025

ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Lot: 00012345678901Lot-123
Quantity: 50 cases
"""


class TestSevenKDEExtraction:
    """Test extraction of all 7 required KDEs per FSMA 204."""

    def test_extract_7_kdes_from_bol(self, extractor):
        """Test that 7 KDEs are extracted with confidence > 0."""
        result = extractor.extract(SAMPLE_BOL_WITH_GTIN14, "test-doc-kde-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert len(result.ctes) > 0
        cte = result.ctes[0]

        # Check TLC
        assert cte.kdes.traceability_lot_code is not None

        # Check Quantity
        assert cte.kdes.quantity == 50.0

        # Check Unit
        assert cte.kdes.unit_of_measure == "cases"

        # Check Product Description
        assert cte.kdes.product_description is not None

        # Check Date
        assert cte.kdes.event_date == "2025-11-05"

        # Check confidence > 0
        assert cte.confidence > 0

    def test_fsma_events_output(self, extractor):
        """Test to_fsma_events outputs events with 7 KDEs."""
        result = extractor.extract(SAMPLE_BOL_WITH_GTIN14, "test-doc-kde-002", tenant_id="11111111-1111-1111-1111-111111111111")
        events = extractor.to_fsma_events(result)

        # Should have at least one event
        assert len(events) > 0
        event = events[0]

        # Check required fields
        assert event["tlc"] is not None
        assert event["date"] is not None
        assert event["cte_type"] == "SHIPPING"

        # Check KDEs list
        kdes = event["kdes"]
        assert len(kdes) > 0

        # All KDEs should have confidence > 0
        for kde in kdes:
            assert "name" in kde
            assert "value" in kde
            assert kde.get("confidence", 0) > 0

    def test_tlc_format_gtin14_lot(self, extractor):
        """#1288 — minimal text with no doc-type indicators is now UNKNOWN,
        no CTE is emitted.  Use a full BOL context to test TLC extraction."""
        bol_text = (
            "BILL OF LADING\nShipper: Acme\nConsignee: Market\n"
            "Carrier: FreightCo\nShip To: DC\n"
            "Lot: 00012345678901Lot-123\nDate: 2025-11-05"
        )
        result = extractor.extract(bol_text, "test-doc-kde-003", tenant_id="11111111-1111-1111-1111-111111111111")

        assert len(result.ctes) > 0
        tlc = result.ctes[0].kdes.traceability_lot_code
        assert tlc is not None
        # Should contain GTIN-14 prefix or lot suffix
        assert tlc.startswith("00012345678901") or "Lot-123" in tlc


class TestTLCFormatValidationMethod:
    """Test TLC format validation method."""

    def test_validate_tlc_format_valid(self, extractor):
        """Test validation of valid GTIN-14 + lot TLC."""
        assert extractor.validate_tlc_format("00012345678901Lot-123") is True
        assert extractor.validate_tlc_format("00012345678901-ABC.DEF") is True

    def test_validate_tlc_format_invalid(self, extractor):
        """Test validation of invalid TLC formats."""
        assert extractor.validate_tlc_format("ABC123") is False
        assert extractor.validate_tlc_format("123456") is False
        assert extractor.validate_tlc_format("") is False
        assert extractor.validate_tlc_format(None) is False

    def test_validate_tlc_format_edge_cases(self, extractor):
        """Test TLC validation edge cases."""
        # Only 14 digits without lot suffix - should fail
        assert extractor.validate_tlc_format("00012345678901") is False
        # Valid with minimal lot suffix
        assert extractor.validate_tlc_format("00012345678901A") is True


class TestSKUGTINFallback:
    """Test SKU and GTIN fallback heuristics."""

    def test_extract_sku_from_text(self, extractor):
        """Test SKU extraction with fallback."""
        text = "SKU: ROM-12CT\nProduct: Romaine Lettuce"
        sku = extractor._extract_sku_fallback(text)
        assert sku == "ROM-12CT"

    def test_extract_gtin_fallback(self, extractor):
        """Test GTIN extraction with fallback."""
        text = "GTIN: 00012345678901\nLot: L-2025"
        gtin = extractor._extract_gtin_fallback(text)
        assert gtin == "00012345678901"

    def test_extract_gtin_from_tlc(self, extractor):
        """Test GTIN extraction from TLC."""
        gtin = extractor._extract_gtin_from_tlc("00012345678901-Lot-123")
        assert gtin == "00012345678901"

        # No GTIN prefix
        gtin = extractor._extract_gtin_from_tlc("Lot-123")
        assert gtin is None
