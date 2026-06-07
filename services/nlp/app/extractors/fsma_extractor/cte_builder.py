"""CTE construction, BOL shipping/receiving split, confidence and validation."""

import re
from typing import Dict, List, Optional

import structlog

# F-NLP-2: redact PII before persisting raw text snippets. ``redact_pii`` is
# applied ONLY at stored-snippet assignment — never before the regex pass —
# so it does not mutilate GLNs / lot codes that pattern-match phone numbers.
from shared.pii import redact_pii

from ..fsma_types import CTE, CTEType, DocumentType, KDE, LineItem

logger = structlog.get_logger("fsma-extractor")


class CTEBuilderMixin:
    """CTE assembly from line items / full text, plus confidence scoring."""

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

        if doc_type == DocumentType.INVOICE:
            return ctes

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
                    source_text=redact_pii(text[:500]) if text else None,  # F-NLP-2
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
                source_text=redact_pii(text[:500]) if text else None,  # F-NLP-2
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

    # Field weights for confidence calculation (#1286).
    # High-priority KDEs (weight=3): traceability_lot_code, event_date, location_identifier
    # Medium-priority KDEs (weight=2): quantity, product_description
    # All other required fields default to weight=1.
    _FIELD_WEIGHTS: Dict[str, int] = {
        "traceability_lot_code": 3,
        "event_date": 3,
        "location_identifier": 3,
        "quantity": 2,
        "product_description": 2,
    }
    _KDE_FIELD_WEIGHTS = _FIELD_WEIGHTS

    def _calculate_confidence(self, kde: KDE, cte_type: CTEType) -> float:
        """
        Calculate extraction confidence as a weighted average of KDE completeness.

        Fields are weighted by regulatory importance (#1286):
        - traceability_lot_code, event_date, location_identifier → weight 3
        - quantity, product_description → weight 2
        - all other required fields → weight 1

        Result = sum(weight for present fields) / sum(weights for all required fields).
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
        total_weight = sum(self._FIELD_WEIGHTS.get(f, 1) for f in fields)
        weighted_found = sum(
            self._FIELD_WEIGHTS.get(f, 1)
            for f in fields
            if getattr(kde, f, None) is not None
        )

        if total_weight == 0:
            return 0.0

        score = round(weighted_found / total_weight, 2)
        missing_high_priority = any(
            self._FIELD_WEIGHTS.get(f, 1) >= 3 and getattr(kde, f, None) is None
            for f in fields
        )
        if missing_high_priority:
            return min(score, 0.5)
        return score

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
