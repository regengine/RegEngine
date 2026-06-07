"""Serialization of extraction results to graph events and FSMAEvent dicts."""

from typing import Any, Dict, List

import structlog

from ..fsma_types import CTE, FSMAExtractionResult

logger = structlog.get_logger("fsma-extractor")


class GraphEventSerializationMixin:
    """Conversion of FSMAExtractionResult to downstream event payloads."""

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
            # #1122 — thread tenant_id through routing envelopes so
            # graph.update / nlp.needs_review consumers can enforce
            # tenant scoping without re-reading the Kafka headers.
            "tenant_id": result.tenant_id,
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
