"""Experimental FDA recall alert projection, disabled by default.

Recall notices are external alerts, not evidence that a CTE occurred. The
legacy Kafka topic has no consumer. Enable only after a reviewed consumer
contract exists; unknown identifiers are never synthesized.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from .models import EnforcementItem, SourceType

logger = structlog.get_logger("fda_fsma_transformer")


class FSMAEventTransformer:
    """Extract known fields from FDA recall alerts for experimental review.

    These payloads are not CTEs or traceability evidence. No graph consumer is
    connected; batch publication requires an explicit experimental opt-in.
    """

    # FSMA Kafka Topic
    FSMA_TOPIC = "fsma.events.extracted"

    def transform(self, item: EnforcementItem) -> Optional[Dict[str, Any]]:
        """Transform an EnforcementItem into an external-alert payload.

        Args:
            item: FDA enforcement item (recall, warning letter, etc.)

        Returns:
            External-alert dict, or None if not transformable
        """
        # Only transform FDA recalls for now
        if item.source_type != SourceType.FDA_RECALL:
            logger.debug("skipping_non_recall", source_type=item.source_type)
            return None

        try:
            return self._transform_recall(item)
        except Exception as e:
            logger.error("transform_failed", error=str(e), source_id=item.source_id)
            return None

    def _transform_recall(self, item: EnforcementItem) -> Dict[str, Any]:
        """Transform an FDA recall into FSMA event format."""
        raw_data = item.raw_data or {}

        # Only preserve a TLC explicitly present in the source
        recall_number = raw_data.get("recall_number", item.source_id)
        tlc = self._source_text(raw_data, "traceability_lot_code")

        # Extract facility info from raw data
        facility_gln = self._extract_gln(raw_data)
        facility_name = item.affected_companies[0] if item.affected_companies else None

        # Map classification to risk level
        classification = raw_data.get("classification", "")
        risk_flags = self._classification_to_risk_flags(classification)

        # Create FSMA event payload
        event_id = f"fda-recall-{item.source_id}-{uuid4().hex[:8]}"
        event_date = item.published_date.strftime("%Y-%m-%d")
        event_time = item.published_date.strftime("%H:%M:%SZ")

        fsma_event = {
            "event_id": event_id,
            "event_type": "FSMA_RECALL_ALERT",
            "cte_type": None,  # A recall notice does not establish a receiving event.
            "is_traceability_evidence": False,
            "event_date": event_date,
            "event_time": event_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Lot information
            "lot": {
                "tlc": tlc,
                "product_description": self._get_product_description(item),
                "quantity": self._parse_quantity(raw_data.get("product_quantity", "")),
                "unit_of_measure": self._source_text(raw_data, "unit_of_measure"),
            },
            # Facility information
            "facility": {
                "gln": facility_gln,
                "name": facility_name,
                "city": raw_data.get("city", ""),
                "state": raw_data.get("state", ""),
                "country": self._source_text(raw_data, "country"),
                "facility_type": None,
            },
            # Source document (FDA recall page)
            "document": {
                "document_id": f"fda-recall-{recall_number}",
                "document_type": "FDA_RECALL",
                "source_uri": item.url,
                "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
            },
            # FSMA-specific metadata
            "fsma_metadata": {
                "recall_number": recall_number,
                "classification": classification,
                "severity": item.severity.value,
                "reason_for_recall": item.summary,
                "distribution_pattern": raw_data.get("distribution_pattern", ""),
                "status": raw_data.get("status"),
                "voluntary_mandated": raw_data.get("voluntary_mandated", ""),
                "risk_flags": risk_flags,
            },
            # Confidence and validation
            # Completeness of directly supplied traceability fields, not a
            # calibrated probability that the notice describes a valid CTE.
            "confidence": sum(
                bool(v)
                for v in (
                    tlc,
                    facility_gln,
                    facility_name,
                    item.affected_products,
                    raw_data.get("product_quantity"),
                    raw_data.get("unit_of_measure"),
                )
            )
            / 6,
            "confidence_basis": "source_field_completeness",
            "source": "fda_recall_scraper",
            "requires_review": True,
        }

        logger.info(
            "recall_transformed",
            event_id=event_id,
            tlc=tlc,
            classification=classification,
            severity=item.severity.value,
        )

        return fsma_event

    @staticmethod
    def _source_text(raw_data: Dict[str, Any], key: str) -> Optional[str]:
        value = raw_data.get(key)
        return value.strip() or None if isinstance(value, str) else None

    def _extract_gln(self, raw_data: Dict[str, Any]) -> Optional[str]:
        """Accept only an explicitly supplied, GS1-valid location number."""
        from shared.fsma_validation import verify_gs1_check_digit

        gln = self._source_text(raw_data, "gln")
        if gln and re.fullmatch(r"[0-9]{13}", gln) and verify_gs1_check_digit(gln):
            return gln
        return None

    def _get_product_description(self, item: EnforcementItem) -> Optional[str]:
        """Extract product description from enforcement item."""
        if item.affected_products:
            return "; ".join(item.affected_products[:3])  # Max 3 products
        return None

    def _parse_quantity(self, quantity_str: str) -> Optional[float]:
        """Parse product quantity from FDA string format."""
        if quantity_str is None:
            return None
        if not isinstance(quantity_str, str):
            # openFDA JSON sometimes carries a bare number. Coerce so a
            # numeric payload does not drop the whole recall event.
            quantity_str = str(quantity_str)
        if not quantity_str:
            return None

        # Try to extract numeric value
        numbers = re.findall(r"[\d,]+\.?\d*", quantity_str)
        if numbers:
            try:
                return float(numbers[0].replace(",", ""))
            except ValueError:
                pass
        return None

    def _classification_to_risk_flags(self, classification: str) -> List[str]:
        """Map FDA classification to FSMA risk flags."""
        flags = []

        if classification == "Class I":
            flags.extend(["FDA_CLASS_I", "IMMEDIATE_ACTION", "CRITICAL_RECALL"])
        elif classification == "Class II":
            flags.extend(["FDA_CLASS_II", "HIGH_PRIORITY"])
        elif classification == "Class III":
            flags.append("FDA_CLASS_III")

        return flags

    def transform_batch(self, items: List[EnforcementItem]) -> List[Dict[str, Any]]:
        """Transform a batch of enforcement items.

        Args:
            items: List of enforcement items

        Returns:
            List of FSMA event dicts (excludes non-transformable items)
        """
        if os.getenv("REGENGINE_ENABLE_EXPERIMENTAL_RECALL_EVENTS") != "1":
            return []
        events = []
        for item in items:
            event = self.transform(item)
            if event:
                events.append(event)

        logger.info(
            "batch_transformed",
            input_count=len(items),
            output_count=len(events),
        )

        return events


# Singleton instance
_transformer_instance: Optional[FSMAEventTransformer] = None


def get_fsma_transformer() -> FSMAEventTransformer:
    """Get the singleton transformer instance."""
    global _transformer_instance
    if _transformer_instance is None:
        _transformer_instance = FSMAEventTransformer()
    return _transformer_instance
