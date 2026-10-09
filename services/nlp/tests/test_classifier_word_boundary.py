"""Word-boundary doc-type matching for the FSMA extractor classifier.

Before the fix, ``_classify_document`` scored indicators with plain
substring matching (``ind in text_lower``). Short indicators then fired
inside unrelated words: ``bol`` in ``symbol``/``bolstered`` classified a
memo as a BILL_OF_LADING, and ``inv`` in ``inventory`` classified it as
an INVOICE. Scores now anchor each indicator on ``\\b`` word boundaries.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import DocumentType


@pytest.fixture
def extractor():
    return FSMAExtractor()


class TestWordBoundaryMatching:
    """Substring indicators must not fire inside unrelated words."""

    def test_bol_substring_does_not_classify_as_bol(self, extractor):
        """``bol`` inside ``symbol``/``bolstered`` is not a BOL indicator."""
        doc_type = extractor._classify_document("The symbol bolstered the shipment.")
        assert doc_type == DocumentType.UNKNOWN, f"Expected UNKNOWN, got {doc_type}"

    def test_inv_substring_does_not_classify_as_invoice(self, extractor):
        """``inv`` inside ``inventory`` is not an INVOICE indicator."""
        doc_type = extractor._classify_document("Annual inventory of envelopes.")
        assert doc_type == DocumentType.UNKNOWN, f"Expected UNKNOWN, got {doc_type}"

    def test_standalone_bol_still_matches(self, extractor):
        """A real standalone BOL token must still classify as BOL."""
        doc_type = extractor._classify_document("BOL Number: BOL-2024-001")
        assert doc_type == DocumentType.BILL_OF_LADING

    def test_phrase_indicator_still_matches(self, extractor):
        """A multi-word indicator must still match on whole words."""
        doc_type = extractor._classify_document("Ship To: Metro Distribution Center")
        assert doc_type == DocumentType.BILL_OF_LADING
