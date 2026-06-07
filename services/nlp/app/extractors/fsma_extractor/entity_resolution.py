"""KDE entity resolution: GLN role mapping, regex KDE extraction, normalizers."""

import re
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from ..fsma_types import KDE

logger = structlog.get_logger("fsma-extractor")


class EntityResolutionMixin:
    """Pass 3 helpers: regex-based KDE extraction and entity normalization."""

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

        # #1119 — positional fallback is BOL-shaped: first GLN tends to
        # be the shipper, second the consignee. That heuristic is
        # defensible for ship_from / ship_to because BOLs almost always
        # print Ship-From in the header block and Ship-To in the body.
        # It is NOT defensible for ``tlc_source_gln``: the TLC source
        # (originator / packer / processor — FSMA §1.1320 KDE) is only
        # the Ship-From when the supplier is also the packer. For co-
        # packed products, distribution hubs, or any multi-hop supply
        # chain, equating the two sends recall investigators to the
        # wrong facility. Leave ``tlc_source_gln`` unset here; an
        # explicit "TLC Source / Lot Owner / Packer / Packed By" label
        # is the ONLY path to populating it (see the labeled-pattern
        # loop above). Missing TLC source surfaces downstream as a
        # visible HITL warning — correctness > recall.
        if unique_glns:
            roles.setdefault("ship_from_gln", normalize(unique_glns[0]))
            if len(unique_glns) > 1:
                roles.setdefault("ship_to_gln", normalize(unique_glns[1]))
            # Intentionally do NOT infer tlc_source_gln from document
            # order. If the labeled pattern above failed, log a warning
            # so operators can route the document to HITL review.
            if "tlc_source_gln" not in roles:
                logger.warning(
                    "tlc_source_gln_unlabeled_fallback_skipped",
                    issue="1119",
                    unique_gln_count=len(unique_glns),
                    reason=(
                        "positional fallback would conflate ship_from with "
                        "tlc_source; packer != shipper in multi-hop chains"
                    ),
                )

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

    def _extract_gtin_from_tlc(self, tlc: str) -> Optional[str]:
        """Extract GTIN-14 prefix from Traceability Lot Code if present."""
        if not tlc:
            return None
        # TLC format: GTIN-14 + variable lot (e.g., "00012345678901-Lot-123")
        if re.match(r"^\d{14}", tlc):
            return tlc[:14]
        return None

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
