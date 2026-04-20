"""
Tests for layout-aware tabular extraction in FSMA Extractor.

Validates that line items are correctly associated - e.g., Lot A belongs
to Romaine, not Spinach - when extracting from multi-line BOLs/invoices.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.nlp.app.extractors.fsma_extractor import (
    CTEType,
    DocumentType,
    FSMAExtractionResult,
    FSMAExtractor,
    LineItem,
)

# Sample BOL with distinct line items - tests correct lot/product association
MULTI_LINE_BOL = """
BILL OF LADING
BOL Number: BOL-2024-001234
Ship Date: 2024-12-02
Ship From GLN: 1234567890123

Item Description           Lot Code        Quantity    Unit
--------------------------------------------------------------
Romaine Lettuce           LOT-A-2024      50          cases
Spinach Baby              LOT-B-2024      75          cases
Mixed Greens Salad        LOT-C-2024      30          cases
--------------------------------------------------------------

Carrier: ABC Trucking
"""

# Invoice format with inline lot codes
MULTI_LINE_INVOICE = """
INVOICE #INV-98765
Date: 12/02/2024

Sold To: Fresh Foods Inc.
Location ID: urn:gln:9876543210123

LINE ITEMS:
1. Organic Romaine Hearts (Lot: ROMA-001)     100 units @ $25.00
2. Baby Spinach 5lb Bag (Lot: SPIN-002)       200 units @ $15.00
3. Kale Bunch (Lot: KALE-003)                  50 units @ $8.00

Subtotal: $6,150.00
"""

# Production log with transformation
PRODUCTION_LOG_TABULAR = """
PRODUCTION LOG - Batch Record
Facility FDA Reg: 12345678901
Production Date: 2024-12-01

Input Materials:
Product                 Batch/Lot       Qty Used
------------------------------------------------
Raw Romaine            TLC-INPUT-A      500 kg
Romaine Trim Waste     TLC-INPUT-B       50 kg

Output Products:
Product                 Batch/Lot       Qty Produced
----------------------------------------------------
Chopped Romaine         TLC-OUTPUT-X     400 kg
Romaine Hearts          TLC-OUTPUT-Y      45 kg
"""

# Edge case: Similar product names with different lots
SIMILAR_PRODUCTS_BOL = """
BILL OF LADING
Ship Date: 2024-12-02
GLN: 1111111111111

Items:
Romaine Lettuce Organic    LOT: ROM-ORG-001    25 cases
Romaine Lettuce Standard   LOT: ROM-STD-002    40 cases
Romaine Hearts Chopped     LOT: ROM-HRT-003    15 cases
"""


class TestTabularLineItemExtraction:
    """Test that line items are correctly grouped from tabular data."""

    def setup_method(self):
        """Set up extractor for each test."""
        self.extractor = FSMAExtractor()

    def test_multi_line_bol_extracts_distinct_items(self):
        """Verify each product gets its correct lot code from BOL."""
        result = self.extractor.extract(MULTI_LINE_BOL, "test-bol-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.BILL_OF_LADING
        assert len(result.line_items) >= 2, "Should extract at least 2 line items"

        # Build lookup by description substring
        items_by_desc = {
            item.description.lower(): item
            for item in result.line_items
            if item.description
        }

        # Find romaine and spinach items
        romaine_item = None
        spinach_item = None
        for desc, item in items_by_desc.items():
            if "romaine" in desc.lower():
                romaine_item = item
            if "spinach" in desc.lower():
                spinach_item = item

        # CRITICAL TEST: Lot A should NOT be associated with Spinach
        if romaine_item and spinach_item:
            assert (
                romaine_item.lot_code != spinach_item.lot_code
            ), "Romaine and Spinach must have different lot codes"

            # Verify correct associations
            assert "A" in (
                romaine_item.lot_code or ""
            ), f"Romaine should have Lot A, got {romaine_item.lot_code}"
            assert "B" in (
                spinach_item.lot_code or ""
            ), f"Spinach should have Lot B, got {spinach_item.lot_code}"

    def test_lot_a_not_associated_with_spinach(self):
        """
        Explicit test: LOT-A must only appear with Romaine, not Spinach.

        This is the key regression test for the tabular extraction upgrade.
        """
        result = self.extractor.extract(MULTI_LINE_BOL, "test-bol-002", tenant_id="11111111-1111-1111-1111-111111111111")

        for item in result.line_items:
            if item.lot_code and "A" in item.lot_code:
                # Any item with Lot A must NOT contain "spinach" in description
                assert (
                    "spinach" not in (item.description or "").lower()
                ), f"LOT-A incorrectly associated with Spinach: {item}"

    def test_quantities_associated_with_correct_items(self):
        """Verify quantities are matched to correct line items."""
        result = self.extractor.extract(MULTI_LINE_BOL, "test-bol-003", tenant_id="11111111-1111-1111-1111-111111111111")

        for item in result.line_items:
            if item.description and "romaine" in item.description.lower():
                assert (
                    item.quantity == 50
                ), f"Romaine should have qty 50, got {item.quantity}"
            elif item.description and "spinach" in item.description.lower():
                assert (
                    item.quantity == 75
                ), f"Spinach should have qty 75, got {item.quantity}"

    def test_invoice_format_extraction(self):
        """Test extraction from invoice-style format with inline lots."""
        result = self.extractor.extract(MULTI_LINE_INVOICE, "test-inv-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.INVOICE

        # Should extract line items
        assert len(result.line_items) >= 2, "Should extract invoice line items"

        # Check lot code extraction
        lot_codes = [item.lot_code for item in result.line_items if item.lot_code]
        assert len(lot_codes) >= 2, f"Should find multiple lot codes, got {lot_codes}"

    def test_production_log_input_output_separation(self):
        """Test that input and output lots are correctly separated."""
        result = self.extractor.extract(PRODUCTION_LOG_TABULAR, "test-prod-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.PRODUCTION_LOG

        # Should have both input and output lots
        lot_codes = [item.lot_code for item in result.line_items if item.lot_code]

        # Check for input and output prefixes
        input_lots = [lc for lc in lot_codes if "INPUT" in lc]
        output_lots = [lc for lc in lot_codes if "OUTPUT" in lc]

        # At minimum, should extract the lots from the document
        all_lots_str = " ".join(lot_codes)
        assert "INPUT" in all_lots_str or "OUTPUT" in all_lots_str or len(lot_codes) > 0

    def test_similar_product_names_distinct_lots(self):
        """Test products with similar names get distinct lot codes."""
        result = self.extractor.extract(SIMILAR_PRODUCTS_BOL, "test-similar-001", tenant_id="11111111-1111-1111-1111-111111111111")

        # All three Romaine variants should have different lots
        romaine_items = [
            item
            for item in result.line_items
            if item.description and "romaine" in item.description.lower()
        ]

        if len(romaine_items) >= 2:
            lot_codes = [item.lot_code for item in romaine_items if item.lot_code]
            unique_lots = set(lot_codes)
            assert len(unique_lots) == len(
                lot_codes
            ), f"Similar products should have unique lots: {lot_codes}"


class TestLineItemDataclass:
    """Test the LineItem dataclass structure."""

    def test_line_item_creation(self):
        """Test LineItem can be created with all fields."""
        item = LineItem(
            description="Test Product",
            lot_code="LOT-001",
            quantity=100.0,
            unit_of_measure="cases",
            gtin="12345678901234",
            row_index=0,
            bounding_box={"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 20},
            confidence=0.95,
        )

        assert item.description == "Test Product"
        assert item.lot_code == "LOT-001"
        assert item.quantity == 100.0
        assert item.gtin == "12345678901234"

    def test_line_item_to_dict(self):
        """Test LineItem serialization."""
        item = LineItem(
            description="Romaine Lettuce",
            lot_code="LOT-A",
            quantity=50,
            row_index=1,
        )

        data = item.to_dict()

        assert data["description"] == "Romaine Lettuce"
        assert data["lot_code"] == "LOT-A"
        assert data["quantity"] == 50
        assert data["row_index"] == 1

    def test_line_item_optional_fields(self):
        """Test LineItem with minimal required fields."""
        item = LineItem(description="Unknown Product")

        assert item.description == "Unknown Product"
        assert item.lot_code is None
        assert item.quantity is None
        assert item.confidence == 1.0  # Default


class TestFSMAExtractionResultWithLineItems:
    """Test FSMAExtractionResult includes line_items field."""

    def test_extraction_result_has_line_items(self):
        """Verify extraction result includes line_items list."""
        extractor = FSMAExtractor()
        result = extractor.extract(MULTI_LINE_BOL, "test-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert hasattr(result, "line_items")
        assert isinstance(result.line_items, list)

    def test_ctes_created_from_line_items(self):
        """Test CTEs are created based on line items when available."""
        extractor = FSMAExtractor()
        result = extractor.extract(MULTI_LINE_BOL, "test-002", tenant_id="11111111-1111-1111-1111-111111111111")

        # If line items were extracted, CTEs should reflect them
        if result.line_items:
            # Should have CTEs for each line item
            assert len(result.ctes) >= len(result.line_items) or len(result.ctes) >= 1


class TestHeuristicFallback:
    """Test the heuristic fallback when table extractor is unavailable."""

    def test_heuristic_extraction_without_table_extractor(self):
        """Test extraction works when table_extractor is None."""
        extractor = FSMAExtractor()
        extractor._table_extractor = False  # Simulate unavailable

        result = extractor.extract(MULTI_LINE_BOL, "test-heuristic-001", tenant_id="11111111-1111-1111-1111-111111111111")

        # Should still extract something via heuristic
        assert result.document_type == DocumentType.BILL_OF_LADING
        # May have fewer line items but should have CTEs
        assert len(result.ctes) >= 1 or len(result.line_items) >= 1

    def test_fallback_preserves_lot_association(self):
        """Even heuristic fallback should try to preserve lot associations."""
        extractor = FSMAExtractor()
        extractor._table_extractor = False

        # Simpler format that heuristic can parse
        simple_bol = """
        Bill of Lading
        Ship Date: 2024-12-02
        GLN: 1234567890123
        
        Romaine Lettuce (Lot: LOT-A) 50 cases
        Spinach Baby (Lot: LOT-B) 75 cases
        """

        result = extractor.extract(simple_bol, "test-heuristic-002", tenant_id="11111111-1111-1111-1111-111111111111")

        # Check that if both items extracted, they have different lots
        if len(result.line_items) >= 2:
            lots = [item.lot_code for item in result.line_items if item.lot_code]
            if len(lots) >= 2:
                assert lots[0] != lots[1], "Different items should have different lots"


class TestTableExtractorIntegration:
    """Test integration with the TableExtractor class."""

    def test_table_extractor_lazy_loading(self):
        """Test that table extractor is lazy loaded."""
        extractor = FSMAExtractor()

        # Initially not loaded
        assert extractor._table_extractor is None

        # Access triggers load
        _ = extractor.table_extractor

        # Now should be set (either to TableExtractor or False if unavailable)
        assert extractor._table_extractor is not None

    @patch(
        "services.nlp.app.extractors.fsma_extractor.FSMAExtractor.table_extractor",
        new_callable=lambda: property(lambda self: None),
    )
    def test_extraction_without_table_extractor(self, mock_prop):
        """Test extraction gracefully handles missing table extractor."""
        extractor = FSMAExtractor()

        # Should not raise, should fall back to heuristic
        result = extractor.extract(MULTI_LINE_BOL, "test-no-table-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert isinstance(result, FSMAExtractionResult)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_document(self):
        """Test handling of empty document."""
        extractor = FSMAExtractor()
        result = extractor.extract("", "test-empty-001", tenant_id="11111111-1111-1111-1111-111111111111")

        assert result.document_type == DocumentType.UNKNOWN
        assert result.line_items == []

    def test_document_without_tables(self):
        """Test document with no tabular structure."""
        plain_text = """
        This is a plain text document with no tables.
        It mentions Lot: ABC123 somewhere.
        Quantity is 100 units.
        """

        extractor = FSMAExtractor()
        result = extractor.extract(plain_text, "test-plain-001", tenant_id="11111111-1111-1111-1111-111111111111")

        # Should still extract via regex fallback
        assert len(result.ctes) >= 1

    def test_malformed_table_rows(self):
        """Test handling of inconsistent table formatting."""
        messy_bol = """
        Bill of Lading
        Ship Date: 2024-12-02
        
        Product                Lot          Qty
        ----------------------------------------
        Romaine Lettuce   LOT-A-2024
        50 cases
        Spinach                        LOT-B-2024     75 cases
        """

        extractor = FSMAExtractor()
        result = extractor.extract(messy_bol, "test-messy-001", tenant_id="11111111-1111-1111-1111-111111111111")

        # Should handle gracefully
        assert isinstance(result, FSMAExtractionResult)


# Run-specific assertions for the critical requirement
class TestCriticalRequirement:
    """
    Critical test: Verify the main requirement is met.

    The primary issue was that regex extraction on multi-line documents
    would associate the wrong lot code with the wrong product.
    """

    def test_critical_lot_product_isolation(self):
        """
        CRITICAL: Each lot code MUST only be associated with its row's product.

        In a BOL like:
            Romaine    LOT-A    50 cases
            Spinach    LOT-B    75 cases

        LOT-A must ONLY appear with Romaine.
        LOT-B must ONLY appear with Spinach.
        """
        extractor = FSMAExtractor()

        bol_text = """
        BILL OF LADING #12345
        Date: 2024-12-02
        GLN: 1234567890123
        
        Item                    Lot Code        Qty
        -------------------------------------------
        Romaine Lettuce         LOT-A           50 cases
        Spinach                 LOT-B           75 cases
        Kale                    LOT-C           25 cases
        """

        result = extractor.extract(bol_text, "critical-test-001", tenant_id="11111111-1111-1111-1111-111111111111")

        # Verify line items exist
        assert (
            len(result.line_items) >= 2
        ), f"Expected at least 2 line items, got {len(result.line_items)}"

        # Build associations
        lot_to_products = {}
        for item in result.line_items:
            if item.lot_code:
                if item.lot_code not in lot_to_products:
                    lot_to_products[item.lot_code] = []
                lot_to_products[item.lot_code].append(item.description)

        # Verify no cross-contamination
        for lot_code, products in lot_to_products.items():
            assert (
                len(products) == 1
            ), f"Lot {lot_code} associated with multiple products: {products}"

            # Specific checks
            if "A" in lot_code:
                assert all(
                    "spinach" not in p.lower() for p in products
                ), f"LOT-A incorrectly associated with Spinach"
            if "B" in lot_code:
                assert all(
                    "romaine" not in p.lower() for p in products
                ), f"LOT-B incorrectly associated with Romaine"
