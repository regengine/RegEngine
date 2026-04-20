"""Regression tests for #1104 — preserve originator-assigned TLC.

Background
----------
21 CFR §1.1320 defines the Traceability Lot Code (TLC) as the
identifier **assigned by the originator** of the lot. The extractor's
pre-fix ``_extract_kdes`` unconditionally rewrote that TLC as
``f"{gtin}-{lot_code}"`` whenever any 14-digit number appeared
anywhere in the document — even from an unrelated row, a different
SKU, or a stray credit-card fragment that happened to be 14 digits.

Two facilities handling the same real-world lot would therefore emit
different "TLCs," breaking the downstream traceability graph and the
recall-matching join. The fix stops gluing GTIN into the TLC, stores
the GTIN on its own ``KDE.gtin`` field, and preserves the originator's
TLC verbatim. The row-scoped table extraction at
``services/nlp/app/extractors/fsma_extractor.py:602`` was already
correct — GTIN there is scoped to its row via ``LineItem.gtin`` and is
not touched by the fix.

The three tests below are the minimum regression guard demanded by
the issue:

* ``test_explicit_tlc_preserved_with_unrelated_gtin_in_doc`` — global
  extraction path (``_extract_kdes``) keeps the TLC verbatim and
  stores the GTIN separately.
* ``test_row_scoped_gtin_still_works`` — the table-row pairing
  continues to associate GTIN and lot within a single row without
  gluing them together.
* ``test_no_tlc_field_gets_row_gtin_fallback`` — when the document has
  no explicit TLC keyword, the row-scoped synthesis still produces a
  usable lot code (no GTIN-glue fallback).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo root importable so ``services.nlp.*`` resolves.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import (
    CTEType,
    DocumentType,
    LineItem,
)


@pytest.fixture
def extractor() -> FSMAExtractor:
    return FSMAExtractor(confidence_threshold=0.85)


class TestTLCOriginatorPreserved_Issue1104:
    """The originator-assigned TLC must survive extraction verbatim."""

    def test_explicit_tlc_preserved_with_unrelated_gtin_in_doc(
        self, extractor: FSMAExtractor
    ):
        """An explicit TLC field + an unrelated 14-digit number in the
        document must produce ``traceability_lot_code == 'LOT-ABC-123'``
        with the GTIN captured separately on ``KDE.gtin``.

        Pre-fix behavior concatenated them into
        ``"01234567890128-LOT-ABC-123"`` — a synthesized TLC that no
        other facility could reproduce, breaking FSMA §1.1320.
        """
        text = "TLC: LOT-ABC-123\nGTIN: 01234567890128"

        kde = extractor._extract_kdes(text)

        assert kde.traceability_lot_code == "LOT-ABC-123", (
            f"TLC must be preserved verbatim; got "
            f"{kde.traceability_lot_code!r}. 21 CFR §1.1320 defines the "
            "TLC as assigned by the originator — synthesizing "
            "'<gtin>-<lot>' is non-compliant (#1104)."
        )
        assert kde.gtin == "01234567890128", (
            f"GTIN must be stored separately on KDE.gtin; got "
            f"{kde.gtin!r} (#1104)."
        )
        # Defensive: the old concat pattern must not reappear.
        assert "01234567890128" not in (kde.traceability_lot_code or ""), (
            "GTIN digits leaked into the TLC — #1104 regression"
        )

    def test_row_scoped_gtin_still_works(self, extractor: FSMAExtractor):
        """Row-scoped extraction (the table path at fsma_extractor.py:602)
        continues to scope GTIN to the same row as the lot code and
        stores it on ``LineItem.gtin`` / ``KDE.gtin`` without fusing
        it into the TLC.

        This is the pattern the fix explicitly preserved — it was the
        correct model for GTIN/lot association all along. The global
        ``_extract_kdes`` path was rewritten to behave the same way.
        """
        row_text = (
            "Romaine Lettuce  GTIN: 00012345678901  LOT: L-2024-A  50 cases"
        )

        # Row-scoped primitives used by _process_tables_to_line_items.
        lot = extractor._extract_from_row(row_text, extractor.PATTERNS["lot_code"])
        gtin = extractor._extract_from_row(row_text, extractor.PATTERNS["gtin"])
        assert lot == "L-2024-A"
        assert gtin == "00012345678901"

        # _build_tlc returns the originator's lot verbatim, ignoring the
        # row's GTIN — the GTIN stays on the LineItem/KDE.
        assert extractor._build_tlc(gtin, lot) == "L-2024-A", (
            "Row-scoped _build_tlc must preserve the originator's lot "
            "code verbatim (#1104)."
        )

        # End-to-end: a LineItem produces a CTE whose KDE has both the
        # verbatim TLC and the separate GTIN.
        item = LineItem(
            description="Romaine Lettuce",
            lot_code=lot,
            gtin=gtin,
            quantity=50.0,
            unit_of_measure="cases",
        )
        ctes = extractor._extract_ctes(
            text=row_text,
            doc_type=DocumentType.BILL_OF_LADING,
            line_items=[item],
        )
        shipping = next(c for c in ctes if c.type is CTEType.SHIPPING)
        assert shipping.kdes.traceability_lot_code == "L-2024-A"
        assert shipping.kdes.gtin == "00012345678901"

    def test_no_tlc_field_gets_row_gtin_fallback(self, extractor: FSMAExtractor):
        """When a document has NO explicit TLC keyword, the row-scoped
        extraction path still applies — a lot code found on the same
        row as a description becomes the originator's identifier.

        There is intentionally no "GTIN fallback" into the TLC: an
        unpaired GTIN never masquerades as a TLC (that was the same
        underlying #1104 bug in a different guise — different facilities
        would still disagree on the "TLC" of the same lot). The lot on
        the row is the only acceptable source.
        """
        # Document has no "TLC:" / "Traceability Lot Code:" field.
        # Row-scoped heuristic must still recover the lot code from the
        # tabular line, and the downstream KDE must carry it verbatim.
        text = (
            "PACKING SLIP\n"
            "Romaine Lettuce Hearts        LOT: L-2024-ORIG-7   50 cases\n"
        )

        line_items = extractor._extract_line_items_heuristic(text)
        assert line_items, (
            "Row-scoped heuristic must recover a line item even when no "
            "'TLC:' label is present (#1104)."
        )
        item = line_items[0]
        assert item.lot_code == "L-2024-ORIG-7"

        # The CTE's TLC is the verbatim row lot; there is no synthesized
        # fallback derived from a stray GTIN.
        ctes = extractor._extract_ctes(
            text=text,
            doc_type=DocumentType.PACKING_SLIP,
            line_items=line_items,
        )
        assert ctes, "Row-scoped extraction must produce at least one CTE."
        tlc = ctes[0].kdes.traceability_lot_code
        assert tlc == "L-2024-ORIG-7", (
            f"Row-scoped synthesis must emit the verbatim lot as the "
            f"TLC; got {tlc!r} (#1104)."
        )

        # And when no lot code is present at all, _build_tlc returns
        # None rather than masquerading a GTIN as a TLC.
        assert extractor._build_tlc(gtin="01234567890128", lot_code=None) is None, (
            "An unpaired GTIN must not be promoted to a TLC — that was "
            "the same #1104 defect in a different guise."
        )
