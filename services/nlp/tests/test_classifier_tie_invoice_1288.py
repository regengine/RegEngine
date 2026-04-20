"""
Regression tests for #1288 — document classifier tie handling and invoice
mis-classification.

Before the fix:
- A tie between two document types silently resolved to whichever dict key
  Python's ``max()`` happened to return first (BILL_OF_LADING / SHIPPING).
- Invoices with no explicit BOL indicators were still classified as INVOICE
  but the CTE type emitted for them was SHIPPING because INVOICE was absent
  from ``DOC_TO_CTE``.

After the fix:
- Ties return ``DocumentType.UNKNOWN`` and log a warning.
- UNKNOWN extractions always set ``review_required=True`` regardless of
  numeric confidence.
- INVOICE extractions always set ``review_required=True`` and carry a
  structured warning in ``result.warnings``.
- Unambiguous BOL documents still produce SHIPPING + RECEIVING CTEs.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import CTEType, DocumentType

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def extractor():
    return FSMAExtractor()


# ---------------------------------------------------------------------------
# Tie-handling
# ---------------------------------------------------------------------------

# This document scores identically for BOL (consignee, ship to) and INVOICE
# (payment terms, total due) — each scores exactly 2.  Before the fix,
# Python's dict-ordering meant max() silently returned BILL_OF_LADING.
TIE_TEXT = """
Ship to: Buyer Corp
Consignee: Buyer Corp
Payment Terms: Net 30
Total Due: $500.00
Lot: TIE-LOT-001
Quantity: 10 cases
Date: 2025-11-05
"""

UNAMBIGUOUS_BOL_TEXT = """
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

INVOICE_TEXT = """
INVOICE #INV-2025-9999
Invoice Date: 2025-11-05
Bill To: Restaurant Supply Co.
Sold To: Bistro Palace
PO Number: PO-8765
Payment Terms: Net 30
Subtotal: $1,500.00
Total Due: $1,500.00

Product: Fresh Cut Spinach
Lot: SP-2025-1105
Quantity: 100 units
Date: 2025-11-05
"""


class TestClassifierTieHandling:
    """#1288 — tie between two document types must return UNKNOWN."""

    def test_tie_returns_unknown(self, extractor):
        """When two document types score equally, _classify_document returns UNKNOWN."""
        doc_type = extractor._classify_document(TIE_TEXT)
        assert doc_type == DocumentType.UNKNOWN, (
            f"Expected UNKNOWN on tie, got {doc_type}"
        )

    def test_tie_extraction_sets_review_required(self, extractor):
        """An extraction from a tie document must always require review."""
        result = extractor.extract(TIE_TEXT, "tie-doc-001", tenant_id=TENANT)
        assert result.review_required is True

    def test_tie_extraction_carries_warning(self, extractor):
        """Tie result must include a human-readable warning in warnings list."""
        result = extractor.extract(TIE_TEXT, "tie-doc-002", tenant_id=TENANT)
        warning_text = " ".join(result.warnings).lower()
        # The UNKNOWN-document warning is appended in ``extract`` (#1288).
        assert "could not be determined" in warning_text or "unknown" in warning_text, (
            f"Expected tie/unknown warning, got: {result.warnings}"
        )

    def test_unambiguous_bol_still_shipping(self, extractor):
        """Unambiguous BOL document must still produce at least one SHIPPING CTE."""
        result = extractor.extract(UNAMBIGUOUS_BOL_TEXT, "bol-doc-001", tenant_id=TENANT)
        assert result.document_type == DocumentType.BILL_OF_LADING
        cte_types = {cte.type for cte in result.ctes}
        assert CTEType.SHIPPING in cte_types, (
            f"Expected SHIPPING CTE from BOL, got: {cte_types}"
        )


class TestInvoiceClassification:
    """#1288 — invoices must not produce SHIPPING CTEs."""

    def test_invoice_classified_as_invoice(self, extractor):
        """Document with invoice-only keywords must classify as INVOICE."""
        doc_type = extractor._classify_document(INVOICE_TEXT)
        assert doc_type == DocumentType.INVOICE

    def test_invoice_ctes_not_shipping(self, extractor):
        """CTEs extracted from an invoice must not have type SHIPPING."""
        result = extractor.extract(INVOICE_TEXT, "inv-doc-001", tenant_id=TENANT)
        # If CTEs were emitted they MUST NOT be typed SHIPPING.
        for cte in result.ctes:
            assert cte.type != CTEType.SHIPPING, (
                f"Invoice produced a SHIPPING CTE — was not expected (#1288)"
            )

    def test_invoice_review_required(self, extractor):
        """Invoice extractions must unconditionally set review_required=True."""
        result = extractor.extract(INVOICE_TEXT, "inv-doc-002", tenant_id=TENANT)
        assert result.review_required is True

    def test_invoice_carries_warning(self, extractor):
        """Invoice result must include a structured HITL warning."""
        result = extractor.extract(INVOICE_TEXT, "inv-doc-003", tenant_id=TENANT)
        combined = " ".join(result.warnings).lower()
        assert "invoice" in combined and ("hitl" in combined or "review" in combined), (
            f"Expected invoice-routing warning, got: {result.warnings}"
        )
