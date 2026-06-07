"""
FSMA 204 Extractor for Critical Tracking Events (CTEs) and Key Data Elements (KDEs).

Extracts traceability data from Bills of Lading, Invoices, and Production Logs
to support FDA Food Safety Modernization Act Section 204 compliance.

Supports layout-aware table extraction to correctly associate line items
(lot codes, quantities, descriptions) from tabular documents like BOLs.

Data types (CTEType, DocumentType, KDE, CTE, etc.) are in fsma_types.py.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

# F-NLP-2: redact PII before persisting raw text snippets. ``redact_pii`` is
# applied ONLY at stored-snippet assignment — never before the regex pass —
# so it does not mutilate GLNs / lot codes that pattern-match phone numbers.
from shared.pii import redact_pii

from ..fsma_types import (
    DocumentType,
    ExtractionConfidence,
    FSMAExtractionResult,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
    HITL_CONFIDENCE_THRESHOLD,
)
from .classification import DocumentClassificationMixin
from .cte_builder import CTEBuilderMixin
from .entity_resolution import EntityResolutionMixin
from .patterns import ExtractionPatternsMixin
from .serialization import GraphEventSerializationMixin
from .tabular import TabularExtractionMixin

logger = structlog.get_logger("fsma-extractor")


class FSMAExtractor(
    ExtractionPatternsMixin,
    DocumentClassificationMixin,
    TabularExtractionMixin,
    EntityResolutionMixin,
    CTEBuilderMixin,
    GraphEventSerializationMixin,
):
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

    def _determine_risk_level(self, confidence: float) -> ExtractionConfidence:
        """Map numerical confidence to SR 11-7 risk levels."""
        if confidence >= self.threshold_high:
            return ExtractionConfidence.HIGH
        elif confidence >= self.threshold_medium:
            return ExtractionConfidence.MEDIUM
        return ExtractionConfidence.LOW

    def extract(
        self,
        text: str,
        document_id: str,
        *,
        tenant_id: str,
        pdf_bytes: Optional[bytes] = None,
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
            tenant_id: Keyword-only, required (#1122). The originating tenant's
                UUID. Forces every caller to make an explicit tenant decision —
                no "default" / "unknown" fallback is permitted. Empty string
                raises ValueError because downstream writes cannot safely
                proceed without tenant scoping.
            pdf_bytes: Optional raw PDF bytes for layout-aware table extraction

        Returns:
            FSMAExtractionResult with extracted CTEs and line_items

        Raises:
            ValueError: with code ``E_MISSING_TENANT_ID`` when tenant_id is
                empty or falsy. The sentinel error code makes it grep-able
                in logs so SRE can spot a regressed caller immediately.
        """
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("E_MISSING_TENANT_ID")
        logger.info(
            "fsma_extraction_started",
            document_id=document_id,
            tenant_id=tenant_id,
        )

        # Pass 1: Document Type Classification (#1288 — tuple-compatible return)
        doc_type, classify_warning = self._classify_document(text)
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
        if doc_type in {DocumentType.UNKNOWN, DocumentType.INVOICE}:
            review_required = True

        # Calculate warnings
        warnings = self._validate_extraction(ctes, doc_type)
        if classify_warning:
            warnings.append(classify_warning)
        if doc_type == DocumentType.INVOICE:
            warnings.append("Invoice document routed to HITL review; no CTE emitted automatically")
        if review_required:
             warnings.append(f"Confidence {doc_confidence:.2f} ({risk_level.value}) requires manual review")
        if not kde_minimums_met:
            warnings.append("KDE minimum not met: TLC and Event Date are both required")

        result = FSMAExtractionResult(
            document_id=document_id,
            tenant_id=tenant_id,
            document_type=doc_type,
            ctes=ctes,
            extraction_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            # F-NLP-2: redact PII on the stored snippet (post-regex-pass).
            raw_text=redact_pii(text[:1000]) if text else None,
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
