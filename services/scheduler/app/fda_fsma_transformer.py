"""FDA Recall to FSMA Event Transformer.

Converts FDA recall EnforcementItems into FSMA TraceEvents for graph ingestion.
This bridges the scheduler's FDA scrapers to the graph service's FSMA consumer.

FSMA 204 Context:
- FDA recalls often involve products that require 24-hour traceability
- Class I and II recalls are CRITICAL/HIGH severity and trigger immediate trace requirements
- We create RECEIVING events at the affected facilities to enable forward/backward trace
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from .models import EnforcementItem, EnforcementSeverity, SourceType

logger = structlog.get_logger("fda_fsma_transformer")


class FSMAEventTransformer:
    """Transforms FDA enforcement items into FSMA-compatible events.
    
    This transformer extracts FSMA-relevant data from FDA recalls and creates
    TraceEvent-compatible payloads that can be consumed by the graph service.
    """
    
    # FSMA CTE Types
    CTE_RECEIVING = "RECEIVING"
    CTE_SHIPPING = "SHIPPING"
    
    # FSMA Kafka Topic
    FSMA_TOPIC = "fsma.events.extracted"
    
    def transform(self, item: EnforcementItem) -> Optional[Dict[str, Any]]:
        """Transform an EnforcementItem into an FSMA event payload.
        
        Args:
            item: FDA enforcement item (recall, warning letter, etc.)
            
        Returns:
            FSMA-compatible event dict, or None if not transformable
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
        
        # Generate a unique TLC from recall data
        recall_number = raw_data.get("recall_number", item.source_id)
        tlc = self._generate_tlc(recall_number, item.affected_products)
        
        # Extract facility info from raw data
        facility_gln = self._extract_gln(raw_data)
        facility_name = item.affected_companies[0] if item.affected_companies else "Unknown Facility"
        
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
            "cte_type": self.CTE_RECEIVING,  # Recalls trigger receiving investigations
            "event_date": event_date,
            "event_time": event_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            
            # Lot information
            "lot": {
                "tlc": tlc,
                "product_description": self._get_product_description(item),
                "quantity": self._parse_quantity(raw_data.get("product_quantity", "")),
                "unit_of_measure": "units",  # FDA doesn't always specify
            },
            
            # Facility information
            "facility": {
                "gln": facility_gln,
                "name": facility_name,
                "city": raw_data.get("city", ""),
                "state": raw_data.get("state", ""),
                "country": "US",
                "facility_type": "PROCESSOR",  # Most recalls are from processors
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
                "status": raw_data.get("status", "Ongoing"),
                "voluntary_mandated": raw_data.get("voluntary_mandated", ""),
                "risk_flags": risk_flags,
            },
            
            # Confidence and validation
            "confidence": 0.95 if classification else 0.85,
            "source": "fda_recall_scraper",
            "requires_review": item.severity == EnforcementSeverity.CRITICAL,
        }
        
        logger.info(
            "recall_transformed",
            event_id=event_id,
            tlc=tlc,
            classification=classification,
            severity=item.severity.value,
        )
        
        return fsma_event
    
    def _generate_tlc(self, recall_number: str, products: List[str]) -> str:
        """Generate a Traceability Lot Code from recall data.
        
        FSMA 204 requires a unique TLC for each lot. We generate one from
        the recall number and first product description.
        """
        product_str = products[0] if products else "unknown"
        # Create a hash-based TLC to ensure uniqueness
        hash_input = f"{recall_number}:{product_str}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()
        
        # Format: FDA-YEAR-RECALLNUM-HASH
        year = datetime.now().year
        clean_recall = re.sub(r'[^A-Za-z0-9]', '', recall_number)[:12]
        
        return f"FDA-{year}-{clean_recall}-{hash_suffix}"
    
    def _extract_gln(self, raw_data: Dict[str, Any]) -> str:
        """Extract or generate a GLN from recall data.
        
        FDA doesn't provide GLNs, so we generate a placeholder that can be
        matched later if the real facility is ingested.
        """
        # Create a stable GLN-like identifier from firm info
        firm_name = raw_data.get("recalling_firm", "")
        state = raw_data.get("state", "XX")
        
        if firm_name:
            # Create a hash-based GLN placeholder (13 digits)
            hash_input = f"{firm_name}:{state}"
            hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest()[:12], 16)
            return f"FDA{hash_val % 10**10:010d}"
        
        return f"FDAUNKNOWN{uuid4().hex[:3].upper()}"
    
    def _get_product_description(self, item: EnforcementItem) -> str:
        """Extract product description from enforcement item."""
        if item.affected_products:
            return "; ".join(item.affected_products[:3])  # Max 3 products
        return item.title[:200] if item.title else "FDA Recalled Product"
    
    def _parse_quantity(self, quantity_str: str) -> Optional[float]:
        """Parse product quantity from FDA string format."""
        if not quantity_str:
            return None
        
        # Try to extract numeric value
        numbers = re.findall(r'[\d,]+\.?\d*', quantity_str)
        if numbers:
            try:
                return float(numbers[0].replace(',', ''))
            except ValueError:
                pass
        return None
    
    def _classification_to_risk_flags(self, classification: str) -> List[str]:
        """Map FDA classification to FSMA risk flags."""
        flags = []
        
        if "Class I" in classification:
            flags.extend(["FDA_CLASS_I", "IMMEDIATE_ACTION", "CRITICAL_RECALL"])
        elif "Class II" in classification:
            flags.extend(["FDA_CLASS_II", "HIGH_PRIORITY"])
        elif "Class III" in classification:
            flags.append("FDA_CLASS_III")
        
        return flags
    
    def transform_batch(self, items: List[EnforcementItem]) -> List[Dict[str, Any]]:
        """Transform a batch of enforcement items.
        
        Args:
            items: List of enforcement items
            
        Returns:
            List of FSMA event dicts (excludes non-transformable items)
        """
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
