"""
FSMA 204 Extractor for Critical Tracking Events (CTEs) and Key Data Elements (KDEs).

Extracts traceability data from Bills of Lading, Invoices, and Production Logs
to support FDA Food Safety Modernization Act Section 204 compliance.

Supports layout-aware table extraction to correctly associate line items
(lot codes, quantities, descriptions) from tabular documents like BOLs.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger("fsma-extractor")


class CTEType(str, Enum):
    """Critical Tracking Event Types per FSMA 204."""

    SHIPPING = "SHIPPING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"
    CREATION = "CREATION"


class DocumentType(str, Enum):
    """Supported document types for FSMA extraction."""

    BILL_OF_LADING = "BOL"
    INVOICE = "INVOICE"
    PRODUCTION_LOG = "PRODUCTION_LOG"
    UNKNOWN = "UNKNOWN"


class ExtractionConfidence(str, Enum):
    """
    Model Risk Management confidence levels per SR 11-7.
    
    Used to gate automated acceptance of extracted data.
    """
    HIGH = "HIGH"      # >= 0.95: Auto-accept
    MEDIUM = "MEDIUM"  # 0.85 - 0.95: Manual review required
    LOW = "LOW"        # < 0.85: Reject/Queue for deep review


@dataclass
class LineItem:
    """
    A single line item extracted from a tabular document.

    Groups related entities (lot_code, description, quantity) that appear
    on the same row of a BOL, invoice, or similar document.
    """

    description: str
    lot_code: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    gtin: Optional[str] = None
    row_index: int = 0
    bounding_box: Optional[Dict[str, float]] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "description": self.description,
            "lot_code": self.lot_code,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "gtin": self.gtin,
            "row_index": self.row_index,
            "bounding_box": self.bounding_box,
            "confidence": self.confidence,
        }


@dataclass
class KDE:
    """Key Data Element extracted from a document."""

    traceability_lot_code: Optional[str] = None
    product_description: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    location_identifier: Optional[str] = None  # GS1 GLN or FDA Reg #
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    ship_from_location: Optional[str] = None
    ship_to_location: Optional[str] = None
    tlc_source_gln: Optional[str] = None
    tlc_source_fda_reg: Optional[str] = None
    ship_from_gln: Optional[str] = None
    ship_to_gln: Optional[str] = None


@dataclass
class CTE:
    """Critical Tracking Event with associated KDEs."""

    type: CTEType
    kdes: KDE
    confidence: float
    source_text: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None


@dataclass
class FSMAExtractionResult:
    """Result of FSMA extraction from a document."""

    document_id: str
    document_type: DocumentType
    ctes: List[CTE]
    extraction_timestamp: str
    raw_text: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    line_items: List[LineItem] = field(
        default_factory=list
    )  # Tabular extraction results
    confidence_level: ExtractionConfidence = ExtractionConfidence.LOW
    review_required: bool = True


class FSMAExtractor:
    """
    FSMA 204 Extractor for Critical Tracking Events and Key Data Elements.

    Uses a multi-pass approach:
    1. Layout Analysis: Identify document type
    2. Entity Extraction: Regex-based KDE extraction
    3. LLM Enhancement: Contextual extraction for complex fields
    """

    # Regex patterns for KDE extraction
    PATTERNS = {
        "lot_code": [
            r"(?:LOT|BATCH|L/C|TLC|Lot\s*#?|Batch\s*#?)\s*[:#]?\s*([A-Z0-9\-\.]{5,})",
            r"(?:Traceability\s*Lot\s*Code)\s*[:#]?\s*([A-Z0-9\-\.]{5,})",
            # GTIN-14 + variable lot format per FSMA 204 spec
            r"(?:Lot|L/C|Batch)\s*[:#]?\s*(\d{14}[A-Za-z0-9\-\.]+)",
        ],
        "gtin": [
            r"(?:GTIN|UPC|EAN)\s*[:#]?\s*(\d{8,14})",
            r"\(01\)(\d{14})",  # GS1 AI (01)
            # Standalone 14-digit GTIN
            r"(?<!\d)(\d{14})(?!\d)",
        ],
        "sku": [
            r"(?:SKU|Stock\s*Keeping\s*Unit|Item\s*#?|Part\s*#?)\s*[:#]?\s*([A-Z0-9\-\.]{3,20})",
            r"(?:Product\s*Code|Code)\s*[:#]?\s*([A-Z0-9\-\.]{3,20})",
        ],
        "quantity": [
            r"(?:QTY|Quantity|Qty\.?)\s*[:#]?\s*(\d+(?:\.\d+)?)\s*(cases?|units?|lbs?|kg|pallets?)?",
            r"(\d+(?:\.\d+)?)\s*(cases?|units?|lbs?|kg|pallets?)",
        ],
        "gln": [
            r"(?:GLN|Location\s*ID)\s*[:#]?\s*(\d{13})",
            r"urn:gln:(\d{13})",
        ],
        "tlc_source_gln": [
            r"(?:TLC\s*Source|Traceability\s*Lot\s*Source|Lot\s*Owner|Packer)[^\d]{0,40}?(?:GLN|Location\s*ID)?\s*[:#]?\s*(\d{13})",
        ],
        "tlc_source_fda_reg": [
            r"(?:TLC\s*Source|Traceability\s*Lot\s*Source|Lot\s*Owner|Packer|Packed\s*By)[^\d]{0,80}?FDA\s*(?:Reg|Registration)\s*[:#]?\s*(\d{9,12})",
        ],
        "ship_from_gln": [
            r"(?:Ship\s*From|Shipper)[^\d]{0,60}?(?:GLN|Location\s*ID)?\s*[:#]?\s*(\d{13})",
        ],
        "ship_to_gln": [
            r"(?:Ship\s*To|Consignee|Deliver\s*To)[^\d]{0,60}?(?:GLN|Location\s*ID)?\s*[:#]?\s*(\d{13})",
        ],
        "date": [
            r"(?:Date|Ship\s*Date|Receive\s*Date)\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{4}-\d{2}-\d{2})",  # ISO format
        ],
        "fda_reg": [
            r"(?:FDA\s*Reg|Registration)\s*[:#]?\s*(\d{11})",
        ],
    }

    # Regex for validating TLC format (GTIN-14 + variable lot)
    TLC_FORMAT_REGEX = r"^\d{14}[A-Za-z0-9\-\.]+$"

    # Document type indicators
    DOC_TYPE_INDICATORS = {
        DocumentType.BILL_OF_LADING: [
            "bill of lading",
            "bol",
            "b/l",
            "shipper",
            "consignee",
            "carrier",
            "freight",
            "ship to",
            "ship from",
        ],
        DocumentType.INVOICE: [
            "invoice",
            "inv",
            "bill to",
            "sold to",
            "purchase order",
            "po number",
            "payment terms",
            "subtotal",
            "total due",
        ],
        DocumentType.PRODUCTION_LOG: [
            "production",
            "batch record",
            "manufacturing",
            "processing",
            "lot record",
            "quality control",
            "qc",
            "kill step",
        ],
    }

    def __init__(
        self, 
        confidence_threshold: float = 0.85,
        threshold_high: float = 0.95,
        threshold_medium: float = 0.85
    ):
        """
        Initialize the FSMA Extractor.

        Args:
            confidence_threshold: Legacy parameter (deprecated)
            threshold_high: Confidence score for HIGH risk level (Auto-accept)
            threshold_medium: Confidence score for MEDIUM risk level (Manual Review)
        """
        self.confidence_threshold = confidence_threshold
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium
        self._table_extractor = None  # Lazy-loaded
        logger.info(
            "fsma_extractor_initialized", 
            threshold_high=threshold_high,
            threshold_medium=threshold_medium
        )

    @property
    def table_extractor(self):
        """Lazy-load the table extractor to avoid heavy imports on startup."""
        if self._table_extractor is None:
            try:
                from .table_extractor import TableExtractor

                self._table_extractor = TableExtractor()
            except ImportError as e:
                logger.warning("table_extractor_unavailable", error=str(e))
                self._table_extractor = False  # Mark as unavailable
        return self._table_extractor if self._table_extractor else None

        return self._table_extractor if self._table_extractor else None

    def _determine_risk_level(self, confidence: float) -> ExtractionConfidence:
        """Map numerical confidence to SR 11-7 risk levels."""
        if confidence >= self.threshold_high:
            return ExtractionConfidence.HIGH
        elif confidence >= self.threshold_medium:
            return ExtractionConfidence.MEDIUM
        return ExtractionConfidence.LOW

    def extract(
        self, text: str, document_id: str, pdf_bytes: Optional[bytes] = None
    ) -> FSMAExtractionResult:
        """
        Extract FSMA CTEs and KDEs from document text.

        Args:
            text: Raw text content from document
            document_id: Unique identifier for the document
            pdf_bytes: Optional raw PDF bytes for layout-aware table extraction

        Returns:
            FSMAExtractionResult with extracted CTEs and line_items
        """
        logger.info("fsma_extraction_started", document_id=document_id)

        # Pass 1: Document Type Classification
        doc_type = self._classify_document(text)
        logger.debug("document_classified", doc_type=doc_type.value)

        # Pass 2: Layout-aware tabular extraction (if available)
        line_items = self._extract_tabular_data(text, pdf_bytes)

        # Pass 3: Entity Extraction (fallback/supplement to tabular)
        ctes = self._extract_ctes(text, doc_type, line_items)

        # Calculate overall document confidence (conservative: min of CTEs)
        doc_confidence = 0.0
        if ctes:
            doc_confidence = min(cte.confidence for cte in ctes)
        elif line_items:
             # Fallback if only line items but no full CTEs (rare)
             doc_confidence = 0.7 
        
        # Determine risk level
        risk_level = self._determine_risk_level(doc_confidence)
        review_required = risk_level != ExtractionConfidence.HIGH

        # Calculate warnings
        warnings = self._validate_extraction(ctes, doc_type)
        if review_required:
             warnings.append(f"Confidence {doc_confidence:.2f} ({risk_level.value}) requires manual review")

        result = FSMAExtractionResult(
            document_id=document_id,
            document_type=doc_type,
            ctes=ctes,
            extraction_timestamp=datetime.utcnow().isoformat() + "Z",
            raw_text=text[:1000] if text else None,  # Store first 1000 chars
            warnings=warnings,
            line_items=line_items,
            confidence_level=risk_level,
            review_required=review_required
        )

        logger.info(
            "fsma_extraction_completed",
            document_id=document_id,
            cte_count=len(ctes),
            line_item_count=len(line_items),
            warnings=len(warnings),
            confidence=doc_confidence,
            risk_level=risk_level.value
        )

        return result

    def _classify_document(self, text: str) -> DocumentType:
        """Classify document type based on content indicators."""
        text_lower = text.lower()

        scores = {}
        for doc_type, indicators in self.DOC_TYPE_INDICATORS.items():
            score = sum(1 for ind in indicators if ind in text_lower)
            scores[doc_type] = score

        if max(scores.values()) == 0:
            return DocumentType.UNKNOWN

        return max(scores, key=lambda k: scores[k])

    def _extract_tabular_data(
        self, text: str, pdf_bytes: Optional[bytes] = None
    ) -> List[LineItem]:
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
                        bounding_box=(
                            row.bounding_box.to_dict() if row.bounding_box else None
                        ),
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
            r"\s{2,}"  # At least 2 whitespace chars (indicates column separation)
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
                        quantity=(
                            float(match.group("qty")) if match.group("qty") else None
                        ),
                        unit_of_measure=(
                            match.group("unit").lower() if match.group("unit") else None
                        ),
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
                        quantity=(
                            float(match.group("qty")) if match.group("qty") else None
                        ),
                        unit_of_measure=(
                            match.group("unit").lower() if match.group("unit") else None
                        ),
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
                unit = (
                    match.group(2).lower()
                    if len(match.groups()) > 1 and match.group(2)
                    else None
                )
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

    def _extract_ctes(
        self,
        text: str,
        doc_type: DocumentType,
        line_items: Optional[List[LineItem]] = None,
    ) -> List[CTE]:
        """
        Extract CTEs based on document type.

        Args:
            text: Document text
            doc_type: Classified document type
            line_items: Pre-extracted line items from tabular extraction
        """
        ctes = []

        # Determine CTE type based on document
        if doc_type == DocumentType.BILL_OF_LADING:
            cte_type = CTEType.SHIPPING
        elif doc_type == DocumentType.PRODUCTION_LOG:
            cte_type = CTEType.TRANSFORMATION
        else:
            cte_type = CTEType.SHIPPING  # Default

        # If we have line items with sufficient data, create CTEs from them
        # Otherwise fall back to global extraction
        useful_line_items = [
            item
            for item in (line_items or [])
            if item.lot_code and (item.quantity is not None or item.description)
        ]

        if useful_line_items and len(useful_line_items) > 0:
            for item in useful_line_items:
                kde = KDE(
                    traceability_lot_code=self._build_tlc(item.gtin, item.lot_code),
                    product_description=item.description,
                    quantity=item.quantity,
                    unit_of_measure=item.unit_of_measure,
                )
                # Extract common fields from full text
                self._populate_shared_kdes(kde, text)

                confidence = self._calculate_confidence(kde, cte_type)

                cte = CTE(
                    type=cte_type,
                    kdes=kde,
                    confidence=confidence,
                    source_text=text[:500] if text else None,
                    bounding_box=item.bounding_box,
                )
                ctes.append(cte)

            return ctes

        # Fallback: Extract KDEs from full text (original behavior)
        kdes = self._extract_kdes(text)

        # Only create CTE if we found at least one meaningful KDE
        has_meaningful_kde = (
            kdes.traceability_lot_code
            or kdes.quantity is not None
            or kdes.location_identifier
            or kdes.event_date
        )

        if has_meaningful_kde:
            # Calculate confidence based on completeness
            confidence = self._calculate_confidence(kdes, cte_type)

            cte = CTE(
                type=cte_type,
                kdes=kdes,
                confidence=confidence,
                source_text=text[:500] if text else None,
            )
            ctes.append(cte)

        return ctes

    def _build_tlc(self, gtin: Optional[str], lot_code: Optional[str]) -> Optional[str]:
        """Build Traceability Lot Code from GTIN and lot code."""
        if gtin and lot_code:
            return f"{gtin}-{lot_code}"
        return lot_code or gtin

    def _extract_gln_roles(self, text: str) -> Dict[str, str]:
        """Extract GLNs and map them to roles based on document context."""
        roles: Dict[str, str] = {}

        def normalize(gln_value: str) -> str:
            return f"urn:gln:{gln_value}"

        def normalize_fda(reg_value: str) -> str:
            return f"fda:{reg_value}"

        # Explicit TLC Source / Lot Owner / Packer label has highest precedence
        for pattern in self.PATTERNS.get("tlc_source_gln", []):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                roles["tlc_source_gln"] = normalize(match.group(1))
                break

        # TLC Source FDA Registration cues near packing/ownership language
        for pattern in self.PATTERNS.get("tlc_source_fda_reg", []):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                roles["tlc_source_fda_reg"] = normalize_fda(match.group(1))
                break

        # Ship From / header level GLN
        for pattern in self.PATTERNS.get("ship_from_gln", []):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                roles["ship_from_gln"] = normalize(match.group(1))
                break

        # Ship To block GLN
        for pattern in self.PATTERNS.get("ship_to_gln", []):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                roles["ship_to_gln"] = normalize(match.group(1))
                break

        # Fallback: sequential GLNs across the document for mapping
        gln_occurrences: List[str] = []
        for pattern in self.PATTERNS.get("gln", []):
            gln_occurrences.extend(
                [m.group(1) for m in re.finditer(pattern, text, re.IGNORECASE)]
            )

        unique_glns: List[str] = []
        for gln_value in gln_occurrences:
            if gln_value not in unique_glns:
                unique_glns.append(gln_value)

        if unique_glns:
            roles.setdefault("ship_from_gln", normalize(unique_glns[0]))
            if len(unique_glns) > 1:
                roles.setdefault("ship_to_gln", normalize(unique_glns[1]))
            roles.setdefault("tlc_source_gln", normalize(unique_glns[0]))

        return roles

    def _populate_shared_kdes(self, kde: KDE, text: str) -> None:
        """Populate shared KDE fields from full document text."""
        gln_roles = self._extract_gln_roles(text)

        kde.tlc_source_gln = kde.tlc_source_gln or gln_roles.get("tlc_source_gln")
        kde.tlc_source_fda_reg = kde.tlc_source_fda_reg or gln_roles.get(
            "tlc_source_fda_reg"
        )
        kde.ship_from_gln = kde.ship_from_gln or gln_roles.get("ship_from_gln")
        kde.ship_to_gln = kde.ship_to_gln or gln_roles.get("ship_to_gln")

        # Extract GLN if not already set, prioritizing TLC Source then Ship From/To
        if not kde.location_identifier:
            for candidate in [
                kde.tlc_source_gln,
                kde.tlc_source_fda_reg,
                kde.ship_from_gln,
                kde.ship_to_gln,
            ]:
                if candidate:
                    kde.location_identifier = candidate
                    break
        if not kde.location_identifier:
            for pattern in self.PATTERNS["gln"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    kde.location_identifier = f"urn:gln:{match.group(1)}"
                    break

        # Try FDA Reg if no GLN
        if not kde.location_identifier:
            for pattern in self.PATTERNS["fda_reg"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    kde.location_identifier = f"fda:{match.group(1)}"
                    break

        # Extract Date if not already set
        if not kde.event_date:
            for pattern in self.PATTERNS["date"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    kde.event_date = self._normalize_date(match.group(1))
                    break

    def _extract_kdes(self, text: str) -> KDE:
        """Extract Key Data Elements using regex patterns."""
        kde = KDE()

        gln_roles = self._extract_gln_roles(text)
        kde.tlc_source_gln = gln_roles.get("tlc_source_gln")
        kde.tlc_source_fda_reg = gln_roles.get("tlc_source_fda_reg")
        kde.ship_from_gln = gln_roles.get("ship_from_gln")
        kde.ship_to_gln = gln_roles.get("ship_to_gln")

        # Extract Lot Code / TLC
        for pattern in self.PATTERNS["lot_code"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                kde.traceability_lot_code = match.group(1).strip()
                break

        # Extract GTIN (append to TLC if found)
        for pattern in self.PATTERNS["gtin"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                gtin = match.group(1).strip()
                if kde.traceability_lot_code:
                    kde.traceability_lot_code = f"{gtin}-{kde.traceability_lot_code}"
                else:
                    kde.traceability_lot_code = gtin
                break

        # Extract Quantity
        for pattern in self.PATTERNS["quantity"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                kde.quantity = float(match.group(1))
                if len(match.groups()) > 1 and match.group(2):
                    kde.unit_of_measure = match.group(2).lower()
                break

        # Extract GLN
        for candidate in [
            gln_roles.get("tlc_source_gln"),
            gln_roles.get("tlc_source_fda_reg"),
            gln_roles.get("ship_from_gln"),
            gln_roles.get("ship_to_gln"),
        ]:
            if candidate:
                kde.location_identifier = candidate
                break
        if not kde.location_identifier:
            for pattern in self.PATTERNS["gln"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    kde.location_identifier = f"urn:gln:{match.group(1)}"
                    break

        # Try FDA Reg if no GLN
        if not kde.location_identifier:
            for pattern in self.PATTERNS["fda_reg"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    kde.location_identifier = f"fda:{match.group(1)}"
                    break

        # Extract Date
        for pattern in self.PATTERNS["date"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                kde.event_date = self._normalize_date(match.group(1))
                break

        # Extract product description (heuristic: look for common patterns)
        product_match = re.search(
            r"(?:Product|Item|Description)\s*[:#]?\s*([A-Za-z0-9\s\-,]+?)(?:\n|$)",
            text,
            re.IGNORECASE,
        )
        if product_match:
            kde.product_description = product_match.group(1).strip()[:100]

        return kde

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date string to ISO format."""
        # Try common formats
        formats = [
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%y",
            "%m-%d-%y",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return date_str  # Return as-is if no format matches

    def _calculate_confidence(self, kde: KDE, cte_type: CTEType) -> float:
        """
        Calculate extraction confidence based on KDE completeness.

        FSMA 204 requires specific KDEs for each CTE type.
        """
        required_fields = {
            CTEType.SHIPPING: [
                "traceability_lot_code",
                "quantity",
                "location_identifier",
                "event_date",
            ],
            CTEType.RECEIVING: [
                "traceability_lot_code",
                "quantity",
                "location_identifier",
                "event_date",
            ],
            CTEType.TRANSFORMATION: [
                "traceability_lot_code",
                "product_description",
                "event_date",
            ],
            CTEType.CREATION: [
                "traceability_lot_code",
                "product_description",
                "event_date",
                "location_identifier",
            ],
        }

        fields = required_fields.get(cte_type, required_fields[CTEType.SHIPPING])
        found = sum(1 for f in fields if getattr(kde, f, None) is not None)

        return round(found / len(fields), 2)

    def _validate_extraction(
        self, ctes: List[CTE], doc_type: DocumentType
    ) -> List[str]:
        """Generate warnings for incomplete or suspicious extractions."""
        warnings = []

        if not ctes:
            warnings.append("No CTEs extracted from document")
            return warnings

        for i, cte in enumerate(ctes):
            prefix = f"CTE[{i}]"

            # Check TLC format (GTIN-14 + alphanumeric)
            if cte.kdes.traceability_lot_code:
                if not re.match(
                    r"^\d{14}[A-Za-z0-9\-\.]+$", cte.kdes.traceability_lot_code
                ):
                    if not re.match(
                        r"^[A-Za-z0-9\-\.]{5,}$", cte.kdes.traceability_lot_code
                    ):
                        warnings.append(
                            f"{prefix}: TLC format may not be GS1 compliant"
                        )
            else:
                warnings.append(f"{prefix}: Missing Traceability Lot Code (CRITICAL)")

            # Check confidence
            if cte.confidence < self.confidence_threshold:
                warnings.append(
                    f"{prefix}: Low confidence ({cte.confidence:.0%}) - requires review"
                )

            # Check required fields
            if not cte.kdes.event_date:
                warnings.append(f"{prefix}: Missing event date")

            if not cte.kdes.location_identifier:
                warnings.append(f"{prefix}: Missing location identifier (GLN/FDA Reg)")

        return warnings

    def to_graph_event(self, result: FSMAExtractionResult) -> Dict[str, Any]:
        """Convert extraction result to GraphEvent format for Neo4j ingestion."""
        return {
            "event_type": "fsma.extraction",
            "document_id": result.document_id,
            "document_type": result.document_type.value,
            "timestamp": result.extraction_timestamp,
            "ctes": [
                {
                    "type": cte.type.value,
                    "kdes": {
                        "traceability_lot_code": cte.kdes.traceability_lot_code,
                        "product_description": cte.kdes.product_description,
                        "quantity": cte.kdes.quantity,
                        "unit_of_measure": cte.kdes.unit_of_measure,
                        "location_identifier": cte.kdes.location_identifier,
                        "tlc_source_gln": cte.kdes.tlc_source_gln,
                        "tlc_source_fda_reg": cte.kdes.tlc_source_fda_reg,
                        "ship_from_gln": cte.kdes.ship_from_gln,
                        "ship_to_gln": cte.kdes.ship_to_gln,
                        "event_date": cte.kdes.event_date,
                        "event_time": cte.kdes.event_time,
                    },
                    "confidence": cte.confidence,
                }
                for cte in result.ctes
            ],
            "warnings": result.warnings,
            "risk_assessment": {
                "level": result.confidence_level.value,
                "review_required": result.review_required
            }
        }

    def _extract_sku_fallback(self, text: str) -> Optional[str]:
        """
        Extract SKU with fallback heuristics.

        Attempts:
        1. Explicit SKU/Item patterns
        2. Product code patterns
        3. Heuristic: alphanumeric codes near product descriptions
        """
        # Try explicit patterns first
        for pattern in self.PATTERNS.get("sku", []):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback heuristic: look for alphanumeric codes in product description context
        # Pattern: alphanumeric with dashes, 6-12 chars, near "product" or description text
        product_context = re.search(
            r"(?:Product|Item|Description)[:\s]+(?:[^A-Z0-9]*)?([A-Z]{2,4}[\-]?\d{3,8})",
            text,
            re.IGNORECASE,
        )
        if product_context:
            return product_context.group(1).strip()

        return None

    def _extract_gtin_fallback(self, text: str) -> Optional[str]:
        """
        Extract GTIN with fallback heuristics.

        Attempts:
        1. Explicit GTIN/UPC/EAN patterns
        2. GS1-128 barcode Application Identifier (01)
        3. Heuristic: 14-digit number in product context
        """
        # Try explicit patterns first
        for pattern in self.PATTERNS.get("gtin", []):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                gtin = match.group(1).strip()
                # Pad to 14 digits if shorter
                if len(gtin) < 14:
                    gtin = gtin.zfill(14)
                return gtin

        return None

    def to_fsma_events(self, result: FSMAExtractionResult) -> List[Dict[str, Any]]:
        """
        Convert extraction result to list of FSMAEvent dictionaries.

        Each CTE/line item becomes an FSMAEvent with:
        - tlc: Traceability Lot Code
        - cte_type: SHIPPING (default)
        - date: Event date
        - quantity, unit, product, ship_from, ship_to
        - raw_row_index: Row index for tabular sources
        - kdes: List of all 7 extracted KDEs with confidence

        Returns:
            List of FSMAEvent-compatible dictionaries
        """
        events = []

        for idx, cte in enumerate(result.ctes):
            # Skip if missing required TLC or date
            if not cte.kdes.traceability_lot_code or not cte.kdes.event_date:
                logger.debug(
                    "fsma_event_skipped_missing_required",
                    index=idx,
                    has_tlc=bool(cte.kdes.traceability_lot_code),
                    has_date=bool(cte.kdes.event_date),
                )
                continue

            # Build product description
            product = None
            if cte.kdes.product_description:
                product = {
                    "text": cte.kdes.product_description,
                    "sku": self._extract_sku_fallback(result.raw_text or ""),
                    "gtin": self._extract_gtin_from_tlc(cte.kdes.traceability_lot_code),
                }

            # Build locations
            ship_from = None
            if cte.kdes.ship_from_gln:
                gln = self._extract_gln_from_urn(cte.kdes.ship_from_gln)
                ship_from = {"gln": gln, "name": None, "address": None}

            ship_to = None
            if cte.kdes.ship_to_gln:
                gln = self._extract_gln_from_urn(cte.kdes.ship_to_gln)
                ship_to = {"gln": gln, "name": None, "address": None}

            # Build KDE list with confidence scores
            kdes = self._build_kde_list(cte, result)

            # Get raw_row_index from line_items if available
            raw_row_index = None
            if idx < len(result.line_items):
                raw_row_index = result.line_items[idx].row_index

            event = {
                "tlc": cte.kdes.traceability_lot_code,
                "cte_type": cte.type.value,
                "date": cte.kdes.event_date,
                "quantity": cte.kdes.quantity,
                "unit": cte.kdes.unit_of_measure,
                "product": product,
                "ship_from": ship_from,
                "ship_to": ship_to,
                "document_source": result.document_id,
                "document_hash": None,  # Can be populated by caller
                "raw_row_index": raw_row_index,
                "kdes": kdes,
            }
            events.append(event)

        logger.info(
            "fsma_events_generated", count=len(events), document_id=result.document_id
        )
        return events

    def _extract_gtin_from_tlc(self, tlc: str) -> Optional[str]:
        """Extract GTIN-14 prefix from Traceability Lot Code if present."""
        if not tlc:
            return None
        # TLC format: GTIN-14 + variable lot (e.g., "00012345678901-Lot-123")
        if re.match(r"^\d{14}", tlc):
            return tlc[:14]
        return None

    def _build_kde_list(
        self, cte: CTE, result: FSMAExtractionResult
    ) -> List[Dict[str, Any]]:
        """
        Build list of 7 KDEs with confidence scores.

        The 7 required KDEs per FSMA 204:
        1. TLC (Traceability Lot Code)
        2. Quantity
        3. Product Description
        4. Unit of Measure
        5. Ship-From Location
        6. Ship-To Location
        7. Date
        """
        kdes = []
        base_confidence = cte.confidence

        # KDE 1: TLC
        if cte.kdes.traceability_lot_code:
            kdes.append(
                {
                    "name": "traceability_lot_code",
                    "value": cte.kdes.traceability_lot_code,
                    "confidence": base_confidence,
                }
            )

        # KDE 2: Quantity
        if cte.kdes.quantity is not None:
            kdes.append(
                {
                    "name": "quantity",
                    "value": str(cte.kdes.quantity),
                    "confidence": base_confidence
                    * 0.95,  # Slightly lower for numeric extraction
                }
            )

        # KDE 3: Product Description
        if cte.kdes.product_description:
            kdes.append(
                {
                    "name": "product_description",
                    "value": cte.kdes.product_description,
                    "confidence": base_confidence * 0.9,
                }
            )

        # KDE 4: Unit of Measure
        if cte.kdes.unit_of_measure:
            kdes.append(
                {
                    "name": "unit_of_measure",
                    "value": cte.kdes.unit_of_measure,
                    "confidence": base_confidence * 0.95,
                }
            )

        # KDE 5: Ship-From Location
        if cte.kdes.ship_from_gln:
            kdes.append(
                {
                    "name": "ship_from_location",
                    "value": cte.kdes.ship_from_gln,
                    "confidence": base_confidence * 0.9,
                }
            )

        # KDE 6: Ship-To Location
        if cte.kdes.ship_to_gln:
            kdes.append(
                {
                    "name": "ship_to_location",
                    "value": cte.kdes.ship_to_gln,
                    "confidence": base_confidence * 0.9,
                }
            )

        # KDE 7: Date
        if cte.kdes.event_date:
            kdes.append(
                {
                    "name": "event_date",
                    "value": cte.kdes.event_date,
                    "confidence": base_confidence * 0.95,
                }
            )

        return kdes

    def validate_tlc_format(self, tlc: str) -> bool:
        r"""
        Validate TLC format against FSMA 204 specification.

        Expected format: GTIN-14 + variable alphanumeric lot code
        Pattern: ^\d{14}[A-Za-z0-9\-\.]+$

        Args:
            tlc: Traceability Lot Code to validate

        Returns:
            True if TLC matches expected format
        """
        if not tlc:
            return False
        return bool(re.match(self.TLC_FORMAT_REGEX, tlc))

    @staticmethod
    def _extract_gln_from_urn(value: Optional[str]) -> Optional[str]:
        """
        Extract GLN from URN format if present.

        Args:
            value: GLN value, possibly in urn:gln:XXXXXXXXXXXXXX format

        Returns:
            Plain GLN string or None
        """
        if not value:
            return None
        if value.startswith("urn:gln:"):
            return value.replace("urn:gln:", "")
        return value
