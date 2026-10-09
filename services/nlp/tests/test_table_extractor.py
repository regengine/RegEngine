"""Focused tests for services/nlp/app/extractors/table_extractor.py.

Covers the main public behavior without loading any deep learning models:
dataclass helpers, plain-text table heuristics, the pdfplumber fallback,
the oversize-PDF guard, and the no-backend empty result.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from services.nlp.app.extractors import table_extractor as te_module
from services.nlp.app.extractors.table_extractor import (
    BoundingBox,
    DetectedTable,
    TableCell,
    TableExtractor,
    TableRow,
)


def _make_extractor(**kwargs):
    """Build an extractor without touching GPU or model downloads."""
    kwargs.setdefault("use_gpu", False)
    return TableExtractor(**kwargs)


class TestBoundingBox:
    def test_to_dict_round_trip(self):
        box = BoundingBox(x_min=1.0, y_min=2.0, x_max=3.0, y_max=4.0)
        assert box.to_dict() == {"x_min": 1.0, "y_min": 2.0, "x_max": 3.0, "y_max": 4.0}

    def test_contains_point_inside_and_outside(self):
        box = BoundingBox(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0)
        assert box.contains_point(5.0, 5.0) is True
        assert box.contains_point(0.0, 0.0) is True
        assert box.contains_point(11.0, 5.0) is False
        assert box.contains_point(5.0, -1.0) is False

    def test_overlaps_detects_shared_area(self):
        left = BoundingBox(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0)
        middle = BoundingBox(x_min=5.0, y_min=0.0, x_max=15.0, y_max=10.0)
        far = BoundingBox(x_min=50.0, y_min=50.0, x_max=60.0, y_max=60.0)
        assert left.overlaps(middle) is True
        assert left.overlaps(far) is False

    def test_overlaps_zero_area_is_false(self):
        degenerate = BoundingBox(x_min=5.0, y_min=5.0, x_max=5.0, y_max=5.0)
        other = BoundingBox(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0)
        assert degenerate.overlaps(other) is False


class TestRowAndTableHelpers:
    def test_row_text_skips_empty_cells(self):
        row = TableRow(
            row_index=0,
            cells=[
                TableCell(text="Romaine", row_index=0, col_index=0),
                TableCell(text="", row_index=0, col_index=1),
                TableCell(text="LOT-A", row_index=0, col_index=2),
            ],
        )
        assert row.text == "Romaine LOT-A"

    def test_headers_returns_first_row_or_none(self):
        row = TableRow(row_index=0, cells=[TableCell(text="Item", row_index=0, col_index=0)])
        assert DetectedTable(page_number=1, rows=[row]).headers == row
        assert DetectedTable(page_number=1, rows=[]).headers is None


class TestExtractorInit:
    def test_use_gpu_false_forces_cpu(self):
        assert _make_extractor(use_gpu=False).device == "cpu"

    def test_explicit_device_is_kept(self):
        assert _make_extractor(device="cpu").device == "cpu"


class TestExtractTablesFromText:
    def test_tab_separated_block_becomes_one_table(self):
        text = "Item\tLot\tQty\nRomaine\tLOT-A\t50 cases\nSpinach\tLOT-B\t75 cases\n"
        tables = _make_extractor().extract_tables_from_text(text)
        assert len(tables) == 1
        assert len(tables[0].rows) == 3
        assert tables[0].rows[0].text == "Item\tLot\tQty"

    def test_blank_line_splits_tables(self):
        text = "A\tB\tC\nD\tE\tF\n\nG\tH\tI\nJ\tK\tL\n"
        tables = _make_extractor().extract_tables_from_text(text)
        assert len(tables) == 2
        assert [len(t.rows) for t in tables] == [2, 2]

    def test_edge_empty_and_single_row_yield_no_tables(self):
        extractor = _make_extractor()
        assert extractor.extract_tables_from_text("") == []
        assert extractor.extract_tables_from_text("Just a normal sentence.\n") == []
        assert extractor.extract_tables_from_text("Only\tone\trow\n") == []

    def test_looks_like_table_row_heuristics(self):
        extractor = _make_extractor()
        assert extractor._looks_like_table_row("Romaine   LOT-A   50 cases") is True
        assert extractor._looks_like_table_row("Shipped 50 cases today") is True
        assert extractor._looks_like_table_row("Just a normal sentence.") is False


@contextmanager
def _force_pdfplumber_only():
    """Force extract_tables_from_pdf down the pdfplumber fallback path."""
    with (
        patch.object(te_module, "_TORCH_AVAILABLE", False),
        patch.object(te_module, "_TRANSFORMERS_AVAILABLE", False),
        patch.object(te_module, "_PDF2IMAGE_AVAILABLE", False),
        patch.object(te_module, "_PDFPLUMBER_AVAILABLE", True),
    ):
        yield


def _fake_pdfplumber_open(pages_data):
    """Build a mock pdfplumber.open whose pages yield the given table data."""
    mock_pdf = MagicMock()
    mock_pages = []
    for table_data in pages_data:
        page = MagicMock()
        page.extract_tables.return_value = [table_data]
        mock_pages.append(page)
    mock_pdf.pages = mock_pages
    opener = MagicMock()
    opener.__enter__.return_value = mock_pdf
    opener.__exit__.return_value = False
    return opener


class TestExtractTablesFromPdf:
    def test_oversize_pdf_raises_before_any_backend(self):
        from services.nlp.app.text_loader import MAX_DOC_BYTES

        extractor = _make_extractor()
        with pytest.raises(ValueError, match="size limit"):
            extractor.extract_tables_from_pdf(b"\x00" * (MAX_DOC_BYTES + 1))

    def test_pdfplumber_fallback_builds_rows_and_cells(self):
        extractor = _make_extractor()
        opener = _fake_pdfplumber_open([[["Item", "Lot"], ["Romaine", "LOT-A"]]])
        with _force_pdfplumber_only(), patch("pdfplumber.open", return_value=opener):
            tables = extractor.extract_tables_from_pdf(b"%PDF-1.4 fake")
        assert len(tables) == 1
        assert tables[0].page_number == 1
        assert len(tables[0].rows) == 2
        assert tables[0].headers.text == "Item Lot"
        cell = tables[0].rows[1].cells[1]
        assert (cell.text, cell.row_index, cell.col_index) == ("LOT-A", 1, 1)

    def test_pdfplumber_pages_filter_skips_unrequested_pages(self):
        extractor = _make_extractor()
        opener = _fake_pdfplumber_open(
            [[["P1A", "P1B"]], [["P2A", "P2B"]]],
        )
        with _force_pdfplumber_only(), patch("pdfplumber.open", return_value=opener):
            tables = extractor.extract_tables_from_pdf(b"%PDF-1.4 fake", pages=[2])
        assert len(tables) == 1
        assert tables[0].page_number == 2
        assert tables[0].rows[0].text == "P2A P2B"

    def test_no_backend_returns_empty_list(self):
        extractor = _make_extractor()
        with (
            patch.object(te_module, "_TORCH_AVAILABLE", False),
            patch.object(te_module, "_TRANSFORMERS_AVAILABLE", False),
            patch.object(te_module, "_PDF2IMAGE_AVAILABLE", False),
            patch.object(te_module, "_PDFPLUMBER_AVAILABLE", False),
        ):
            assert extractor.extract_tables_from_pdf(b"%PDF-1.4 fake") == []
