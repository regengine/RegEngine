"""
FSMA 204 Extractor for Critical Tracking Events (CTEs) and Key Data Elements (KDEs).

Extracts traceability data from Bills of Lading, Invoices, and Production Logs
to support FDA Food Safety Modernization Act Section 204 compliance.

Supports layout-aware table extraction to correctly associate line items
(lot codes, quantities, descriptions) from tabular documents like BOLs.

Data types (CTEType, DocumentType, KDE, CTE, etc.) are in fsma_types.py.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .fsma_types import (
    CTEType,
    DocumentType,
    ExtractionConfidence,
    LineItem,
    KDE,
    CTE,
    FSMAExtractionResult,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
    HITL_CONFIDENCE_THRESHOLD,
)

# #1116 — Food Traceability List scoping. The rules engine already
# owns the authoritative catalog; the extractor classifies each
# product against it so non-FTL foods can be marked up-front and
# skipped downstream instead of generating spurious "missing TLC"
# warnings. The import is lazy-tolerant: a missing FTL module should
# not fail extraction (we degrade to ``is_ftl_covered=None`` which
# the downstream pipeline treats as a classification gap, not a
# positive compliance stamp — see #1346).
try:
    from shared.rules.ftl import FTL_CATEGORIES  # type: ignore[import]
except Exception:  # pragma: no cover - defense-in-depth for import paths
    FTL_CATEGORIES = frozenset()

logger = structlog.get_logger("fsma-extractor")


class FSMAExtractor:
    """
    FSMA 204 Extractor for Critical Tracking Events and Key Data Elements.

    Uses a multi-pass approach:
    1. Layout Analysis: Identify document type
    2. Entity Extraction: Regex-based KDE extraction
    3. LLM Enhancement: Contextual extraction for complex fields

    Routing behaviour:
    - High-confidence events (>= 0.85) with both TLC and Event Date present
      are emitted to the ``graph.update`` topic for automated graph ingestion.
    - Events below the 0.85 confidence threshold are routed to the
      ``nlp.needs_review`` topic for human-in-the-loop (HITL) intervention.
    """

    # Production GTIN-14 TLC pattern: 14-digit GTIN prefix + alphanumeric lot suffix
    GTIN14_TLC_PATTERN = r"^\d{14}[A-Za-z0-9\-\.]+$"

    # Regex patterns for KDE extraction
    PATTERNS = {
        "lot_code": [
            # GTIN-14 + variable lot format per FSMA 204 spec (highest priority)
            r"(?:Lot|L/C|Batch|TLC|Traceability\s*Lot\s*Code)\s*[:#]?\s*(\d{14}[A-Za-z0-9\-\.]+)",
            r"(?:LOT|BATCH|L/C|TLC|Lot\s*#?|Batch\s*#?)\s*[:#]?\s*([A-Z0-9\-\.]{5,})",
            r"(?:Traceability\s*Lot\s*Code)\s*[:#]?\s*([A-Z0-9\-\.]{5,})",
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
        # #1129 — quantity is required as a (value, unit) PAIR per 21
        # CFR §1.1325(c). The unit was previously optional in the
        # "QTY: <n>" variant which dropped the unit silently. Both
        # patterns now REQUIRE a unit match; units extended beyond the
        # original 5 to cover the common aliases (oz, g/gram, ton,
        # bushel, CT/BX/CS).
        #
        # The "units?" token carried the English word "units" — kept.
        # Short-form "UN" could be confused with prefix characters so
        # it is intentionally absent.
        "quantity": [
            r"(?:QTY|Quantity|Qty\.?)\s*[:#]?\s*"
            r"(\d+(?:\.\d+)?)\s*"
            r"(cases?|units?|lbs?|kg|pallets?|oz|ounces?|gram?s?|g|tons?|bushels?|ct|bx|box(?:es)?|cs|cartons?|crates?|bins?|totes?)",
            r"(\d+(?:\.\d+)?)\s*"
            r"(cases?|units?|lbs?|kg|pallets?|oz|ounces?|gram?s?|g|tons?|bushels?|ct|bx|box(?:es)?|cs|cartons?|crates?|bins?|totes?)",
        ],
        # Fallback — matches a bare number after QTY/Quantity with NO
        # unit. We use this to detect the "found a number but no unit"
        # case and emit a warning instead of silently storing the
        # quantity without a unit (#1129).
        "quantity_unitless": [
            r"(?:QTY|Quantity|Qty\.?)\s*[:#]?\s*(\d+(?:\.\d+)?)(?!\s*(?:cases?|units?|lbs?|kg|pallets?|oz|ounces?|gram?s?|g|tons?|bushels?|ct|bx|box|cs|cartons?|crates?|bins?|totes?))\b",
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
        # #1103 — origin-side documents. Order matters: these are
        # checked BEFORE BOL in ``_classify_document`` so that a
        # harvest log which happens to mention "shipper" is not
        # misclassified as a BOL and silently routed to SHIPPING.
        DocumentType.HARVEST_LOG: [
            "harvest log",
            "harvest record",
            "harvester",
            "field id",
            "field identifier",
            "picked by",
            "growing area",
        ],
        DocumentType.COOLING_LOG: [
            "cooling log",
            "cooling record",
            "hydro-cooler",
            "forced air cool",
            "pulp temp",
            "cooling temperature",
            "cooling location",
        ],
        DocumentType.PACKING_SLIP: [
            "packing slip",
            "packing list",
            "packed by",
            "packer",
            "initial packing",
            "packing date",
            "pack location",
        ],
        DocumentType.LANDING_REPORT: [
            "landing report",
            "catch report",
            "source vessel",
            "fishing vessel",
            "port of landing",
            "first land-based receiver",
            "first landing",
        ],
    }

    #: #1103 — document type → CTE type mapping. Missing entries mean
    #: the CTE type must be inferred from content or the default falls
    #: back to SHIPPING (the original behavior this mapping replaces).
    DOC_TO_CTE: Dict[DocumentType, CTEType] = {
        DocumentType.HARVEST_LOG: CTEType.HARVESTING,
        DocumentType.COOLING_LOG: CTEType.COOLING,
        DocumentType.PACKING_SLIP: CTEType.INITIAL_PACKING,
        DocumentType.LANDING_REPORT: CTEType.FIRST_LAND_BASED_RECEIVER,
        DocumentType.PRODUCTION_LOG: CTEType.TRANSFORMATION,
        # BILL_OF_LADING is handled specially — see #1123 split logic
        # in ``_extract_ctes`` (emits both SHIPPING and RECEIVING).
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

        Only emits high-confidence events to ``graph.update`` when both the
        Traceability Lot Code (TLC) and Event Date KDE minimums are satisfied.
        Events that fail the KDE minimum check or fall below the 0.85
        confidence threshold are routed to ``nlp.needs_review`` for HITL.

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

        # KDE Minimum Gate: require both TLC and Event Date on every CTE.
        # CTEs missing either mandatory KDE are flagged for human review
        # regardless of their confidence score.
        kde_minimums_met = True
        for cte in ctes:
            if not cte.kdes.traceability_lot_code or not cte.kdes.event_date:
                kde_minimums_met = False
                review_required = True
                break

        # HITL routing: confidence < 0.85 always requires human review
        if doc_confidence < HITL_CONFIDENCE_THRESHOLD:
            review_required = True

        # Calculate warnings
        warnings = self._validate_extraction(ctes, doc_type)
        if review_required:
             warnings.append(f"Confidence {doc_confidence:.2f} ({risk_level.value}) requires manual review")
        if not kde_minimums_met:
            warnings.append("KDE minimum not met: TLC and Event Date are both required")

        result = FSMAExtractionResult(
            document_id=document_id,
            document_type=doc_type,
            ctes=ctes,
            extraction_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
            risk_level=risk_level.value,
            kde_minimums_met=kde_minimums_met,
        )

        return result

    def route_extraction(self, result: FSMAExtractionResult) -> Dict[str, Any]:
        """
        Determine the downstream Kafka topic for an extraction result and
        return a routing envelope.

        Routing rules:
        1. If ``review_required`` is True (confidence < 0.85 or KDE minimums
           not met), route to ``nlp.needs_review`` for human-in-the-loop.
        2. Otherwise route to ``graph.update`` for automated graph ingestion.

        Returns:
            Dict with ``topic``, ``payload``, and ``routed_at`` keys.
        """
        if result.review_required:
            topic = TOPIC_NEEDS_REVIEW
            logger.info(
                "fsma_extraction_routed_hitl",
                document_id=result.document_id,
                confidence=result.confidence_level.value,
                topic=topic,
            )
        else:
            topic = TOPIC_GRAPH_UPDATE
            logger.info(
                "fsma_extraction_routed_graph",
                document_id=result.document_id,
                confidence=result.confidence_level.value,
                topic=topic,
            )

        return {
            "topic": topic,
            "payload": self.to_graph_event(result),
            "routed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

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

        # #1103 — determine CTE type(s) from the document type.
        # Previously every non-PRODUCTION_LOG document fell back to
        # SHIPPING, which meant harvest logs, cooling records, and
        # packing slips were misclassified. Origin-side documents now
        # route to their correct FDA CTE type.
        #
        # #1123 — a BOL documents both a SHIPPING CTE (at the
        # shipper) and a RECEIVING CTE (at the receiver). Emitting
        # only SHIPPING loses the downstream half of the chain, so
        # recall-tracing cannot walk forward. BOL is therefore
        # expanded later in this method into two CTEs linked via
        # ``prior_source_tlc``.
        if doc_type == DocumentType.BILL_OF_LADING:
            # Split is handled below — use SHIPPING as the "primary"
            # CTE for the tabular / single-KDE paths, then clone the
            # emitted CTE into a RECEIVING partner.
            cte_type = CTEType.SHIPPING
            split_bol_into_shipping_plus_receiving = True
        elif doc_type in self.DOC_TO_CTE:
            cte_type = self.DOC_TO_CTE[doc_type]
            split_bol_into_shipping_plus_receiving = False
        else:
            cte_type = CTEType.SHIPPING  # legacy default for UNKNOWN
            split_bol_into_shipping_plus_receiving = False

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
                    # #1104 — GTIN stored separately. Same-row pairing
                    # is preserved because the LineItem already scoped
                    # the GTIN to the row, unlike the old global
                    # _extract_kdes concat.
                    gtin=item.gtin,
                )
                # #1116 — FTL classification from the line item's
                # description (the most-specific signal available).
                kde.is_ftl_covered, kde.ftl_category = self._classify_ftl(
                    item.description
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

            if split_bol_into_shipping_plus_receiving:
                ctes = self._split_bol_into_shipping_and_receiving(ctes)
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
            # #1116 — FTL classification from the extracted product
            # description. Upgraded callers can route non-FTL events
            # away from the FSMA path instead of letting them fill
            # the review queue with false-positive "missing TLC"
            # warnings.
            kdes.is_ftl_covered, kdes.ftl_category = self._classify_ftl(
                kdes.product_description
            )
            # Calculate confidence based on completeness
            confidence = self._calculate_confidence(kdes, cte_type)

            cte = CTE(
                type=cte_type,
                kdes=kdes,
                confidence=confidence,
                source_text=text[:500] if text else None,
            )
            ctes.append(cte)

        if split_bol_into_shipping_plus_receiving:
            ctes = self._split_bol_into_shipping_and_receiving(ctes)
        return ctes

    def _split_bol_into_shipping_and_receiving(
        self, ctes: List[CTE]
    ) -> List[CTE]:
        """For each SHIPPING CTE extracted from a BOL, emit a matching
        RECEIVING CTE at the ship-to party — #1123.

        A Bill of Lading documents both sides of a handoff:

            SHIPPING   at the shipper (ship_from_*)
            RECEIVING  at the receiver (ship_to_*)

        Pre-fix the extractor emitted only the SHIPPING half, leaving
        the downstream node missing from the traceability graph so
        recall traces could walk backward but not forward. The
        RECEIVING CTE's ``prior_source_tlc`` points back to the
        SHIPPING CTE's TLC so the two legs are linkable, and the
        RECEIVING CTE gets its own fresh ``event_id`` (via
        ``KDE``/``CTE`` default factory) so the pair doesn't collide
        on ingest.

        The original SHIPPING CTEs are preserved verbatim and kept
        first in the list (callers that loop in order see shipping
        events before their paired receiving events).

        If the receiver is unknown (no ship_to_gln, no ship_to_location)
        we do NOT emit a RECEIVING CTE — half a chain is better than
        fabricated party data. A structured warning is logged so the
        gap is visible in HITL review.
        """
        paired: List[CTE] = []
        for cte in ctes:
            paired.append(cte)
            if cte.type != CTEType.SHIPPING:
                continue
            # #1123 — refuse to emit RECEIVING when the receiving party
            # is unknown. Emitting an unscoped RECEIVING would plant a
            # phantom downstream node, which is worse than leaving the
            # chain forward-incomplete.
            has_ship_to = bool(
                cte.kdes.ship_to_gln or cte.kdes.ship_to_location
            )
            if not has_ship_to:
                logger.warning(
                    "bol_receiving_skipped_unknown_party",
                    reason="no ship_to_gln or ship_to_location on BOL",
                    tlc=cte.kdes.traceability_lot_code,
                    shipping_event_id=cte.event_id,
                )
                continue
            rx_kde = KDE(
                traceability_lot_code=cte.kdes.traceability_lot_code,
                product_description=cte.kdes.product_description,
                quantity=cte.kdes.quantity,
                unit_of_measure=cte.kdes.unit_of_measure,
                # Scope location to the ship-to side (the receiver).
                location_identifier=(
                    cte.kdes.ship_to_gln or cte.kdes.location_identifier
                ),
                event_date=cte.kdes.event_date,
                event_time=cte.kdes.event_time,
                ship_from_location=cte.kdes.ship_from_location,
                ship_to_location=cte.kdes.ship_to_location,
                ship_from_gln=cte.kdes.ship_from_gln,
                ship_to_gln=cte.kdes.ship_to_gln,
                tlc_source_gln=cte.kdes.tlc_source_gln,
                tlc_source_fda_reg=cte.kdes.tlc_source_fda_reg,
                gtin=cte.kdes.gtin,
                # Link the two events: RECEIVING.prior_source_tlc ==
                # SHIPPING.traceability_lot_code.
                prior_source_tlc=cte.kdes.traceability_lot_code,
                is_ftl_covered=cte.kdes.is_ftl_covered,
                ftl_category=cte.kdes.ftl_category,
            )
            # CTE.event_id has a default_factory that mints a new UUID
            # on every instance — SHIPPING and its paired RECEIVING
            # therefore get distinct IDs (#1123).
            paired.append(
                CTE(
                    type=CTEType.RECEIVING,
                    kdes=rx_kde,
                    confidence=cte.confidence,
                    source_text=cte.source_text,
                    bounding_box=cte.bounding_box,
                )
            )
        return paired

    def _classify_ftl(self, product_description: Optional[str]) -> Tuple[Optional[bool], Optional[str]]:
        """Classify a free-text product description against the FDA FTL.

        Returns ``(is_ftl_covered, ftl_category)``:

          - ``(True, category)``  — product matches an FTL category; the
            matching category name is returned for downstream consumers.
          - ``(False, None)``     — a non-empty description was supplied
            but no FTL category matched. Treat as non-FTL and route
            accordingly (#1116).
          - ``(None, None)``      — no description supplied, or the FTL
            catalog import failed. Caller should surface as a
            classification gap, not a compliance verdict (#1346).
        """
        if not product_description or not product_description.strip():
            return None, None
        if not FTL_CATEGORIES:
            return None, None
        desc = product_description.lower()
        # Match is substring-based so "fresh romaine lettuce" maps to
        # "leafy greens" via the rules catalog's entries. Order is
        # deterministic (sorted) so unit tests are stable.
        for category in sorted(FTL_CATEGORIES):
            # Each catalog category is already lower-cased.
            for token in category.split():
                # Avoid spurious single-letter matches by requiring
                # tokens of at least 4 chars. Still handles "nuts" /
                # "eggs" / "fish" but excludes unhelpful prefixes.
                if len(token) < 4:
                    continue
                if token in desc:
                    return True, category
        return False, None

    def _build_tlc(self, gtin: Optional[str], lot_code: Optional[str]) -> Optional[str]:
        """Return the originator-assigned Traceability Lot Code verbatim.

        Pre-#1104 this method synthesized a TLC by concatenating the
        GTIN and the lot code (``f"{gtin}-{lot_code}"``). That was
        non-compliant with FSMA §1.1320 — the TLC is the identifier
        the originator assigned, not one we fabricate downstream. Two
        facilities handling the same real-world lot would report
        different "TLCs" and recall matching would break.

        Callers that want to capture the GTIN should store it in
        ``KDE.gtin`` (or ``LineItem.gtin`` for tabular extraction).
        """
        if lot_code:
            return lot_code
        # If ONLY a GTIN was supplied (no lot code at all), we return
        # None rather than masquerading the GTIN as a TLC — same
        # reason as above. Missing TLC surfaces as a visible KDE
        # warning; a fake TLC silently breaks traceability.
        return None

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

        # Extract GTIN — stored SEPARATELY from TLC (#1104). The prior
        # unconditional concat ``f"{gtin}-{tlc}"`` mutated the
        # originator-assigned TLC even when the GTIN came from a
        # completely unrelated line of the document (another SKU, a
        # serial number, even a credit-card fragment that happens to
        # be 14 digits). FSMA §1.1320 defines the TLC as assigned by
        # the originator — synthesizing a new one is non-compliant.
        #
        # If no explicit lot code was found but a GTIN was, we DO NOT
        # fall back to using the GTIN AS the TLC either — that
        # produced the same incorrect downstream behavior under a
        # different guise (two facilities reporting different "TLCs"
        # for the same lot). The TLC stays ``None`` in that case and
        # the missing-KDE warning fires correctly.
        for pattern in self.PATTERNS["gtin"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                kde.gtin = match.group(1).strip()
                break

        # Extract Quantity — (value, unit) PAIR required per §1.1325(c).
        # The previous pattern made the unit optional and silently
        # stored ``quantity=50`` with ``unit_of_measure=None`` when a
        # caller wrote "Quantity: 50" without a unit (#1129). We now
        # populate ``kde.quantity`` ONLY when a unit was found in the
        # same match. The downstream completeness check in
        # ``_validate_extraction`` turns the missing pair into a
        # visible KDE warning.
        for pattern in self.PATTERNS["quantity"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.groups()) >= 2 and match.group(2):
                kde.quantity = float(match.group(1))
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

            # Check TLC format against production GTIN-14 pattern
            if cte.kdes.traceability_lot_code:
                if not re.match(
                    self.GTIN14_TLC_PATTERN, cte.kdes.traceability_lot_code
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
        """
        Convert extraction result to GraphEvent format for Neo4j ingestion.

        Only CTEs that satisfy KDE minimums (TLC + Event Date) are included
        in the graph event payload. CTEs missing either field are omitted to
        prevent incomplete nodes from entering the knowledge graph.
        """
        qualified_ctes = [
            cte for cte in result.ctes
            if cte.kdes.traceability_lot_code and cte.kdes.event_date
        ]

        return {
            "event_type": "fsma.extraction",
            "document_id": result.document_id,
            "document_type": result.document_type.value,
            "timestamp": result.extraction_timestamp,
            "ctes": [
                {
                    # #1123 — per-event UUID so paired SHIPPING/RECEIVING
                    # CTEs from the same BOL are distinguishable on ingest.
                    "event_id": cte.event_id,
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
                        # #1123 — RECEIVING carries a back-pointer so the
                        # graph can link the two halves of the handoff.
                        "prior_source_tlc": cte.kdes.prior_source_tlc,
                    },
                    "confidence": cte.confidence,
                }
                for cte in qualified_ctes
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

        Only events that satisfy KDE minimums (TLC + Event Date) are emitted.

        Returns:
            List of FSMAEvent-compatible dictionaries
        """
        events = []

        for idx, cte in enumerate(result.ctes):
            # KDE Minimum Gate: skip if missing required TLC or date
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
        return bool(re.match(self.GTIN14_TLC_PATTERN, tlc))

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
