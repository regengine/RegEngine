"""Layout-aware tabular extraction (Pass 2) for the FSMA extractor.

Supports layout-aware table extraction to correctly associate line items
(lot codes, quantities, descriptions) from tabular documents like BOLs.
"""

import re
from typing import Any, List, Optional, Tuple

import structlog

from ..fsma_types import LineItem

logger = structlog.get_logger("fsma-extractor")


class TabularExtractionMixin:
    """Pass 2: layout-aware tabular extraction and row-scoped entity pulls."""

    @property
    def table_extractor(self):
        """Lazy-load the table extractor to avoid heavy imports on startup."""
        if self._table_extractor is None:
            try:
                from ..table_extractor import TableExtractor

                self._table_extractor = TableExtractor()
            except ImportError as e:
                logger.warning("table_extractor_unavailable", error=str(e))
                self._table_extractor = False  # Mark as unavailable
        return self._table_extractor if self._table_extractor else None

    def _extract_tabular_data(self, text: str, pdf_bytes: Optional[bytes] = None) -> List[LineItem]:
        """
        Extract line items from tabular data in the document.

        Uses layout-aware table extraction to correctly associate
        lot codes, quantities, and descriptions that appear on the same row.

        Args:
            text: Document text content
            pdf_bytes: Optional raw PDF bytes for enhanced extraction

        Returns:
            List of LineItem objects with correctly grouped entities
        """
        line_items = []

        # Try PDF-based extraction first (more accurate)
        if pdf_bytes and self.table_extractor:
            try:
                tables = self.table_extractor.extract_tables_from_pdf(pdf_bytes)
                line_items = self._process_tables_to_line_items(tables)
                if line_items:
                    logger.info("tabular_extraction_pdf", items=len(line_items))
                    return line_items
            except Exception as e:
                logger.warning("pdf_table_extraction_failed", error=str(e))

        # Fall back to text-based table detection
        if self.table_extractor:
            try:
                tables = self.table_extractor.extract_tables_from_text(text)
                line_items = self._process_tables_to_line_items(tables)
                if line_items:
                    logger.info("tabular_extraction_text", items=len(line_items))
                    return line_items
            except Exception as e:
                logger.warning("text_table_extraction_failed", error=str(e))

        # Final fallback: heuristic row-based extraction
        line_items = self._extract_line_items_heuristic(text)
        logger.info("tabular_extraction_heuristic", items=len(line_items))

        return line_items

    def _process_tables_to_line_items(self, tables: List[Any]) -> List[LineItem]:
        """Convert detected tables to LineItem objects."""
        line_items = []

        for table in tables:
            # Skip header row if detected
            start_row = 1 if len(table.rows) > 1 else 0

            for row in table.rows[start_row:]:
                row_text = row.text

                # Extract entities from this row only
                lot_code = self._extract_from_row(row_text, self.PATTERNS["lot_code"])
                gtin = self._extract_from_row(row_text, self.PATTERNS["gtin"])
                qty_match = self._extract_quantity_from_row(row_text)
                description = self._extract_description_from_row(row_text)

                # Only create line item if we found meaningful data
                if description or lot_code:
                    item = LineItem(
                        description=description or "Unknown Product",
                        lot_code=lot_code,
                        quantity=qty_match[0] if qty_match else None,
                        unit_of_measure=qty_match[1] if qty_match else None,
                        gtin=gtin,
                        row_index=row.row_index,
                        bounding_box=(row.bounding_box.to_dict() if row.bounding_box else None),
                        confidence=0.9 if lot_code and description else 0.7,
                    )
                    line_items.append(item)

        return line_items

    def _extract_line_items_heuristic(self, text: str) -> List[LineItem]:
        """
        Heuristic extraction of line items from text.

        Only extracts when product description AND lot code appear on the SAME line.
        This prevents false positives on documents where fields are on separate lines.

        Looks for patterns like:
        - "Romaine Lettuce    LOT-A-2024    50 cases"
        - "Romaine Lettuce (Lot A)    50 cases"
        - NOT: "Product: Romaine\nLot: ABC123\nQty: 50" (separate lines)
        """
        line_items = []
        lines = text.split("\n")

        # Stricter pattern: requires explicit "LOT" or "BATCH" keyword followed by code
        # Pattern for tabular rows with lot label
        tabular_row_pattern = re.compile(
            r"^(?P<desc>[A-Za-z][A-Za-z0-9\s,\-]{3,50}?)"  # Description (3-50 chars)
            r"\s+"  # Column separation: one or more whitespace chars. The
            # LOT/BATCH/TLC keyword anchors the split, so single-space rows
            # ("Romaine Lettuce LOT-A-2024 50 cases") match too.
            r"(?:LOT|BATCH|TLC)[:\s#-]*(?P<lot>[A-Za-z0-9\-\.]{3,})"  # Lot keyword + code
            r"(?:\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>cases?|units?|lbs?|kg|ea|pallets?)?)?",  # Optional quantity
            re.IGNORECASE,
        )

        # Alternative: parenthetical lot in product name (e.g., "Romaine (Lot A)")
        inline_lot_pattern = re.compile(
            r"^(?P<desc>[A-Za-z][A-Za-z0-9\s,\-]+?)"  # Description
            r"\s*\((?:Lot|Batch)\s*[:\s]*(?P<lot>[A-Za-z0-9\-\.]+)\)"  # Lot in parens with keyword
            r"(?:\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>cases?|units?|lbs?|kg|ea|pallets?)?)?",  # Optional qty
            re.IGNORECASE,
        )

        for idx, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 15:  # Min length for a real line item
                continue

            # Skip document title/header lines
            lower_line = line.lower()
            if any(
                skip in lower_line
                for skip in [
                    "bill of lading",
                    "invoice",
                    "purchase order",
                    "item description",
                    "lot code",
                    "quantity",
                    "------",
                    "shipper:",
                    "ship to:",
                    "ship from:",
                    "carrier:",
                    "sold to:",
                    "bill to:",
                    "production",
                    "batch record",
                ]
            ):
                continue

            # Skip lines that are just a label: "Product:", "Lot:", etc.
            if re.match(
                r"^(Product|Lot|Batch|Quantity|Qty|GTIN|Date|GLN|FDA)\s*[:#]",
                line,
                re.IGNORECASE,
            ):
                continue

            # Try tabular row pattern first (needs LOT/BATCH keyword)
            match = tabular_row_pattern.match(line)
            if match:
                lot_code = match.group("lot")
                desc = match.group("desc").strip() if match.group("desc") else None

                if lot_code and desc and len(desc) >= 3:
                    item = LineItem(
                        description=desc[:100],
                        lot_code=lot_code,
                        quantity=(float(match.group("qty")) if match.group("qty") else None),
                        unit_of_measure=(match.group("unit").lower() if match.group("unit") else None),
                        row_index=idx,
                        confidence=0.75,
                    )
                    line_items.append(item)
                    continue

            # Try inline lot pattern (e.g., "Romaine (Lot A)")
            match = inline_lot_pattern.match(line)
            if match:
                lot_code = match.group("lot")
                desc = match.group("desc").strip() if match.group("desc") else None

                if lot_code and desc and len(desc) >= 3:
                    item = LineItem(
                        description=desc[:100],
                        lot_code=lot_code,
                        quantity=(float(match.group("qty")) if match.group("qty") else None),
                        unit_of_measure=(match.group("unit").lower() if match.group("unit") else None),
                        row_index=idx,
                        confidence=0.75,
                    )
                    line_items.append(item)

        return line_items

    def _extract_from_row(self, row_text: str, patterns: List[str]) -> Optional[str]:
        """Extract first match from patterns within a single row."""
        for pattern in patterns:
            match = re.search(pattern, row_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_quantity_from_row(self, row_text: str) -> Optional[Tuple[float, str]]:
        """Extract quantity and unit from a single row."""
        for pattern in self.PATTERNS["quantity"]:
            match = re.search(pattern, row_text, re.IGNORECASE)
            if match:
                qty = float(match.group(1))
                unit = match.group(2).lower() if len(match.groups()) > 1 and match.group(2) else None
                return (qty, unit)
        return None

    def _extract_description_from_row(self, row_text: str) -> Optional[str]:
        """Extract product description from a row, avoiding lot/quantity patterns."""
        # Remove lot codes and quantities to isolate description
        cleaned = row_text

        # Remove lot patterns
        for pattern in self.PATTERNS["lot_code"]:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove quantity patterns
        for pattern in self.PATTERNS["quantity"]:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove GTIN patterns
        for pattern in self.PATTERNS["gtin"]:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Clean up remaining text
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"^[\s\-:,]+|[\s\-:,]+$", "", cleaned)

        if cleaned and len(cleaned) >= 3:
            return cleaned[:100]
        return None
