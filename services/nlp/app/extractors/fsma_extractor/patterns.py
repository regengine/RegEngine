"""Regex patterns and document-type indicator tables for the FSMA extractor.

Class-level constants live on ``ExtractionPatternsMixin`` so they remain
accessible as ``FSMAExtractor.PATTERNS`` / ``self.PATTERNS`` exactly as
before the package split.
"""

from typing import Dict

from ..fsma_types import CTEType, DocumentType


class ExtractionPatternsMixin:
    """Pattern/constant definitions shared by all FSMAExtractor passes."""

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
            # #1119 — "Packed By" was listed in the FDA-Reg variant but
            # missing here, which meant a BOL with "Ship From: GLN X /
            # Packed By: GLN Y" would drop Y and let the positional
            # fallback silently mirror X into both slots. Parallel
            # alternation with the FDA-Reg variant restores labeled
            # precedence for packer GLNs.
            r"(?:TLC\s*Source|Traceability\s*Lot\s*Source|Lot\s*Owner|Packer|Packed\s*By)[^\d]{0,40}?(?:GLN|Location\s*ID)?\s*[:#]?\s*(\d{13})",
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
