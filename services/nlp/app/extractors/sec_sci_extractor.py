"""
SEC Regulation SCI Extractor

Specialized extractor for SEC Regulation Systems Compliance and Integrity (SCI).
Handles systems compliance requirements for securities market infrastructure.

Source: https://www.sec.gov/rules/final/2014/34-73639.pdf
"""

import os
import sys
from pathlib import Path
from typing import List
from uuid import UUID

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.schemas import ExtractionPayload, ObligationType, Threshold


class SECSCIExtractor:
    """
    Domain-specific extractor for SEC Regulation SCI.

    Extracts:
    - Systems capacity planning requirements
    - Change management procedures
    - Incident notification obligations
    - Business continuity-disaster recovery testing
    """

    JURISDICTION = "US-SEC"
    FRAMEWORK = "Regulation SCI"

    def extract_obligations(
        self,
        text: str,
        document_id: UUID,
        tenant_id: UUID,
    ) -> List[ExtractionPayload]:
        """
        Extract SEC Regulation SCI obligations from regulatory text.

        Args:
            text: Regulatory document text
            document_id: UUID of source document
            tenant_id: UUID of tenant

        Returns:
            List of ExtractionPayload objects
        """
        import re
        from datetime import datetime, timezone

        extractions = []

        # SEC Regulation SCI-specific patterns for market infrastructure
        patterns = [
            # Systems Capacity and Resilience (Rule 1001)
            {
                "pattern": r"Rule 1001.*?capacity.*?SCI entity.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "CAPACITY_RESILIENCE",
                "action_label": "must maintain systems capacity and resilience",
            },
            # Change Management (Rule 1002)
            {
                "pattern": r"Rule 1002.*?change.*?(management|control).*?SCI entity.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "CHANGE_MANAGEMENT",
                "action_label": "must enforce change management controls",
            },
            # Incident Notification (Rule 1002(b))
            {
                "pattern": r"Rule 1002.*?incident.*?(notification|notify|report).*?SCI entity.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "INCIDENT_NOTIFICATION",
                "action_label": "must notify the Commission of SCI incidents",
            },
            # Business Continuity (Rule 1003)
            {
                "pattern": r"Rule 1003.*?(business continuity|disaster recovery).*?SCI entity.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "BUSINESS_CONTINUITY",
                "action_label": "must maintain business continuity plans",
            },
            # Redundant backup/secondary systems (Rule 1003(b))
            {
                "pattern": r"Rule 1003.*?(?P<requirement>(?:requires|shall|must)[^.]{0,240}?(?:backup|redundant)[^.]*\.)",
                "obligation_type": ObligationType.MUST,
                "category": "BACKUP_RESILIENCE",
                "action_label": "must maintain redundant backup systems",
            },
            # Systems Testing (Rule 1003(b))
            {
                "pattern": r"Rule 1003.*?testing.*?SCI entity.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "SYSTEMS_TESTING",
                "action_label": "must conduct SCI systems testing",
            },
            # Circuit Breaker Requirements
            {
                "pattern": r"circuit breaker.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "CIRCUIT_BREAKER",
                "action_label": "must enforce circuit breaker safeguards",
            },
            # Market Data Requirements
            {
                "pattern": r"market data.*?dissemination.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "MARKET_DATA",
                "action_label": "must ensure market data dissemination reliability",
            },
            # Order Entry and Execution
            {
                "pattern": r"order (entry|execution|routing).*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "ORDER_PROCESSING",
                "action_label": "must secure order processing pipelines",
            },
        ]

        for pattern_config in patterns:
            matches = re.finditer(
                pattern_config["pattern"], text, re.IGNORECASE | re.DOTALL
            )
            for match in matches:
                requirement_text = match.group("requirement").strip()

                # Extract thresholds if present
                thresholds = self._extract_thresholds(requirement_text)

                extraction = ExtractionPayload(
                    subject="SCI entities",
                    action=pattern_config.get(
                        "action_label", "must comply with Regulation SCI"
                    ),
                    object=requirement_text,
                    obligation_type=pattern_config["obligation_type"],
                    thresholds=thresholds,
                    jurisdiction=self.JURISDICTION,
                    jurisdiction_codes=[self.JURISDICTION],
                    attributes={
                        "document_id": str(document_id),
                        "tenant_id": str(tenant_id),
                        "framework": self.FRAMEWORK,
                        "category": pattern_config["category"],
                        "extractor": "SECSCIExtractor",
                    },
                    confidence_score=0.88,  # High confidence for explicit SEC SCI patterns
                    source_text=requirement_text,
                    source_offset=match.start(),
                )
                extractions.append(extraction)

        return extractions

    def _extract_thresholds(self, text: str) -> List[Threshold]:
        """Extract numeric thresholds from requirement text."""
        import re

        thresholds = []

        # Time-based thresholds (e.g., "within 30 minutes", "no later than 24 hours")
        time_patterns = [
            r"within\s+(\d+)\s+(minute|hour|day)s?",
            r"no\s+later\s+than\s+(\d+)\s+(minute|hour|day)s?",
            r"immediately.*?but.*?no\s+later\s+than\s+(\d+)\s+(minute|hour|day)s?",
        ]

        for pattern in time_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                value = float(match.group(1))
                unit = match.group(2).lower()

                # Convert to minutes for standardization
                if unit == "hour":
                    value *= 60
                elif unit == "day":
                    value *= 1440

                thresholds.append(
                    Threshold(
                        value=value,
                        operator="<=",
                        unit="minutes",
                        context=match.group(0),
                    )
                )

        # Percentage thresholds (e.g., "99.9% uptime", "at least 95% capacity")
        percentage_patterns = [
            r"(\d+(?:\.\d+)?)\s*%\s*(uptime|availability|capacity)",
            r"at\s+least\s+(\d+(?:\.\d+)?)\s*%",
        ]

        for pattern in percentage_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                value = float(match.group(1))

                thresholds.append(
                    Threshold(
                        value=value,
                        operator=">=",
                        unit="percent",
                        context=match.group(0),
                    )
                )

        return thresholds

    @staticmethod
    def get_regulatory_metadata() -> dict:
        """Return metadata about SEC Regulation SCI for reference."""
        return {
            "framework": "Regulation SCI",
            "full_name": "Regulation Systems Compliance and Integrity",
            "jurisdiction": "US-SEC",
            "authority": "U.S. Securities and Exchange Commission",
            "effective_date": "2015-11-03",
            "scope": "SCI entities (exchanges, clearing agencies, ATSs, plan processors)",
            "key_requirements": [
                "Systems Capacity and Resilience (Rule 1001)",
                "Change Management (Rule 1002)",
                "Incident Notification (Rule 1002(b))",
                "Business Continuity and Disaster Recovery (Rule 1003)",
                "Systems Review and Testing (Rule 1003(b))",
            ],
            "url": "https://www.sec.gov/rules/final/2014/34-73639.pdf",
        }
