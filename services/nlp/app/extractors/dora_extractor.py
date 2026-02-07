"""
DORA (Digital Operational Resilience Act) Extractor

Specialized extractor for EU Digital Operational Resilience Act provisions.
Handles ICT risk management, incident reporting, and third-party oversight
requirements for financial entities.

Source: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554
"""

import os
import sys
from pathlib import Path
from typing import List
from uuid import UUID

# Use APP_HOME env var or calculate from file location
_app_home = os.environ.get("APP_HOME", str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, _app_home)

from shared.schemas import ExtractionPayload, ObligationType, Threshold


class DORAExtractor:
    """
    Domain-specific extractor for DORA (Digital Operational Resilience Act).

    Extracts:
    - ICT risk management framework requirements
    - Third-party ICT service provider oversight
    - Digital operational resilience testing
    - ICT-related incident reporting
    """

    JURISDICTION = "EU"
    FRAMEWORK = "DORA"

    def extract_obligations(
        self,
        text: str,
        document_id: UUID,
        tenant_id: UUID,
    ) -> List[ExtractionPayload]:
        """
        Extract DORA obligations from regulatory text.

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

        # DORA-specific patterns for operational resilience requirements
        patterns = [
            # ICT Risk Management Framework (Article 6)
            {
                "pattern": r"Article 6.*?ICT risk management framework.*?Financial entities shall.*?(maintain|establish|implement).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "ICT_RISK_MANAGEMENT",
            },
            # Third-Party Provider Management (Chapter V)
            {
                "pattern": r"Article \d+.*?third-party.*?ICT.*?provider.*?Financial entities shall.*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "THIRD_PARTY_OVERSIGHT",
            },
            # Incident Reporting (Article 17-23)
            {
                "pattern": r"Article (17|18|19|20|21|22|23).*?incident.*?Financial entities shall.*?(report|notify).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "INCIDENT_REPORTING",
            },
            # Resilience Testing (Article 24-27)
            {
                "pattern": r"Article (24|25|26|27).*?(testing|test).*?Financial entities shall.*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "RESILIENCE_TESTING",
            },
            # Operational Resilience
            {
                "pattern": r"operational resilience.*?Financial entities.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "OPERATIONAL_RESILIENCE",
            },
            # Crypto-Asset Service Providers
            {
                "pattern": r"crypto-asset.*?service provider.*?(shall|must).*?(?P<requirement>[^.]{50,300}\.)",
                "obligation_type": ObligationType.MUST,
                "category": "CRYPTO_ASSET_REQUIREMENTS",
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
                    document_id=document_id,
                    tenant_id=tenant_id,
                    obligation_text=requirement_text,
                    obligation_type=pattern_config["obligation_type"],
                    confidence=0.85,  # High confidence for explicit DORA patterns
                    source_offset=match.start(),
                    extracted_at=datetime.now(timezone.utc),
                    thresholds=thresholds,
                    metadata={
                        "framework": "DORA",
                        "jurisdiction": "EU",
                        "category": pattern_config["category"],
                    },
                )
                extractions.append(extraction)

        return extractions

    def _extract_thresholds(self, text: str) -> List[Threshold]:
        """Extract numeric thresholds from requirement text."""
        import re

        thresholds = []

        # Pattern for time-based thresholds (e.g., "within 4 hours", "no later than 24 hours")
        time_patterns = [
            r"within\s+(\d+)\s+(hour|day|week)s?",
            r"no\s+later\s+than\s+(\d+)\s+(hour|day|week)s?",
            r"at\s+least\s+(\d+)\s+(hour|day|week)s?",
        ]

        for pattern in time_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                value = float(match.group(1))
                unit = match.group(2).lower()

                # Convert to hours for standardization
                if unit == "day":
                    value *= 24
                elif unit == "week":
                    value *= 168

                thresholds.append(
                    Threshold(
                        value=value, operator="<=", unit="hours", context=match.group(0)
                    )
                )

        return thresholds

    @staticmethod
    def get_regulatory_metadata() -> dict:
        """Return metadata about DORA for reference."""
        return {
            "framework": "DORA",
            "full_name": "Digital Operational Resilience Act",
            "jurisdiction": "EU",
            "authority": "European Parliament and Council",
            "effective_date": "2025-01-17",
            "scope": "Financial entities operating in the EU",
            "key_requirements": [
                "ICT Risk Management (Chapter II)",
                "ICT-Related Incident Reporting (Chapter III)",
                "Digital Operational Resilience Testing (Chapter IV)",
                "Third-Party ICT Service Provider Management (Chapter V)",
            ],
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554",
        }
