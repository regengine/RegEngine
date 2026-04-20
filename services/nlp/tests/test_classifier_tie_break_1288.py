"""
Tests for #1288 — document classifier must not silently default to SHIPPING
on ties or for invoice documents.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import CTEType, DocumentType


@pytest.fixture
def extractor():
    return FSMAExtractor(confidence_threshold=0.85)


# ---------------------------------------------------------------------------
# Tie-break: equal scores → UNKNOWN, no SHIPPING CTE emitted
# ---------------------------------------------------------------------------

TIED_TEXT = """
bill of lading
bol
b/l
shipper
consignee
carrier
freight
ship to
ship from
invoice
inv
bill to
sold to
purchase order
po number
payment terms
subtotal
total due
"""


def test_tie_break_returns_unknown(extractor):
    """When BOL and INVOICE score equally, _classify_document must return UNKNOWN."""
    doc_type = extractor._classify_document(TIED_TEXT)
    assert doc_type == DocumentType.UNKNOWN, (
        f"Expected UNKNOWN on tie, got {doc_type}"
    )


def test_tie_break_produces_no_ctes(extractor):
    """A tied document must not emit any CTEs (and especially not SHIPPING)."""
    ctes = extractor._extract_ctes(TIED_TEXT, DocumentType.UNKNOWN, [])
    assert ctes == [], f"Expected no CTEs for UNKNOWN doc type, got {ctes}"


def test_tie_break_no_shipping_cte_in_result(extractor):
    """Full extraction on a tied document must not produce a SHIPPING CTE."""
    result = extractor.extract(
        text=TIED_TEXT,
        document_id="test-tie-1288",
        tenant_id="tenant-abc",
    )
    shipping_ctes = [c for c in result.ctes if c.type == CTEType.SHIPPING]
    assert shipping_ctes == [], (
        f"Expected no SHIPPING CTEs for ambiguous document, got {shipping_ctes}"
    )


# ---------------------------------------------------------------------------
# Invoice: classified as INVOICE, ctes=[], no SHIPPING
# ---------------------------------------------------------------------------

INVOICE_TEXT = """
INVOICE #INV-2025-9999
Bill To: Acme Grocers LLC
Payment Terms: Net 30
Purchase Order: PO-1234
Subtotal: $4,500.00
Total Due: $4,500.00

Product: Fresh Romaine Hearts
Lot: L-2025-ABC
Qty: 200 cases
"""


def test_invoice_classified_as_invoice(extractor):
    """Invoice keywords should win; doc type must be INVOICE not UNKNOWN."""
    doc_type = extractor._classify_document(INVOICE_TEXT)
    assert doc_type == DocumentType.INVOICE, (
        f"Expected INVOICE doc type, got {doc_type}"
    )


def test_invoice_extract_ctes_returns_empty(extractor):
    """_extract_ctes called with INVOICE doc type must return []."""
    ctes = extractor._extract_ctes(INVOICE_TEXT, DocumentType.INVOICE, [])
    assert ctes == [], f"Expected no CTEs for INVOICE, got {ctes}"


def test_invoice_full_extraction_no_shipping_cte(extractor):
    """Full extract() on invoice must have doc_type=INVOICE and zero SHIPPING CTEs."""
    result = extractor.extract(
        text=INVOICE_TEXT,
        document_id="test-invoice-1288",
        tenant_id="tenant-abc",
    )
    assert result.document_type == DocumentType.INVOICE, (
        f"Expected document_type=INVOICE, got {result.document_type}"
    )
    shipping_ctes = [c for c in result.ctes if c.type == CTEType.SHIPPING]
    assert shipping_ctes == [], (
        f"Invoice must not produce SHIPPING CTEs, got {shipping_ctes}"
    )


# ---------------------------------------------------------------------------
# Regression: unambiguous BOL → SHIPPING CTE still works
# ---------------------------------------------------------------------------

CLEAN_BOL_TEXT = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123
Consignee: Metro Distribution Center
Carrier: FastFreight LLC
Freight terms: prepaid
Ship To: Metro DC, 123 Main St
Ship From: Farm Gate, Rural Rd

Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
Ship Date: 2025-11-05
"""


def test_unambiguous_bol_classified_as_bol(extractor):
    """A clear BOL must classify as BILL_OF_LADING."""
    doc_type = extractor._classify_document(CLEAN_BOL_TEXT)
    assert doc_type == DocumentType.BILL_OF_LADING, (
        f"Expected BILL_OF_LADING, got {doc_type}"
    )


def test_unambiguous_bol_emits_shipping_cte(extractor):
    """A clean BOL must still produce a SHIPPING CTE."""
    result = extractor.extract(
        text=CLEAN_BOL_TEXT,
        document_id="test-bol-regression-1288",
        tenant_id="tenant-abc",
    )
    assert result.document_type == DocumentType.BILL_OF_LADING
    shipping_ctes = [c for c in result.ctes if c.type == CTEType.SHIPPING]
    assert len(shipping_ctes) >= 1, (
        "Unambiguous BOL must produce at least one SHIPPING CTE"
    )
