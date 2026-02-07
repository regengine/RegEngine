"""
NUCLEAR VERTICAL

This module implements NRC-aligned compliance evidence features.

⚠️  CRITICAL: Any changes here MUST preserve:
    - Snapshot immutability (10 CFR 50 App B, Criterion XVII)
    - Attribution (server-side enforcement)
    - Retention and legal hold (10 CFR 73.54, 10 CFR 72.174)
    - Safety mode enforcement (fail-safe during corruption)

📚 Documentation:
    - docs/verticals/nuclear/README.md
    - docs/verticals/nuclear/cfr_traceability_matrix.md
    - docs/verticals/nuclear/sprint_backlog.md

🚫 This module does NOT:
    - Ensure nuclear safety (that's the customer's QA program)
    - Control reactor operations (out-of-band evidence layer only)
    - Guarantee NRC compliance (evidence infrastructure, not programs)
    - Replace licensing processes (supports, does not substitute)

🎯 Regulatory Alignment:
    - 10 CFR 50 Appendix B (Quality Assurance - Criterion XVII)
    - 10 CFR 73.54 (Cybersecurity)
    - 10 CFR 72.174 (Decommissioning Records)

⚖️  Compliance Claims (Approved):
    "RegEngine provides a compliance evidence layer that helps nuclear 
    operators meet NRC recordkeeping and cybersecurity documentation 
    obligations under 10 CFR. It operates out-of-band, preserves evidence 
    immutably, and supports inspection and discovery."

📋 Change Control:
    Modifications to Sprint 0-2 components require:
    1. CFR justification
    2. Review against docs/verticals/nuclear/cfr_traceability_matrix.md
    3. Update to sprint_backlog.md
    4. Regulatory counsel review (for Sprint 0-1)

Last Updated: 2026-01-25
Version: 1.0
"""

from .engine import NuclearComplianceEngine
from .models import NuclearComplianceRecord
from .verification import VerificationService
from .safety_mode import SafetyModeEnforcer

__all__ = [
    "NuclearComplianceEngine",
    "NuclearComplianceRecord",
    "VerificationService",
    "SafetyModeEnforcer",
]

# Version info for regulatory tracking
__version__ = "1.0.0-sprint0"
__cfr_aligned__ = ["10CFR50AppB", "10CFR73.54", "10CFR72.174"]
__regulatory_status__ = "development"  # development | sprint0_complete | production
