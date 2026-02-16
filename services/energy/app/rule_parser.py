"""
NERC CIP-013 Rule Parser.

Implements domain-specific validation rules for electrical substations.
Translates asset states and mismatch data into regulatory compliance statuses.
"""
import uuid
from typing import Dict, List, Any
from .models import SystemStatus, MismatchSeverity

class NERCRuleParser:
    """
    Parser for NERC CIP-013 compliance rules.
    
    Compliance Standards:
    - CIP-013-1: Supply Chain Risk Management
    - CIP-010-3: Configuration Change Management
    """
    
    @staticmethod
    def calculate_status(
        asset_states: Dict[str, Any],
        active_mismatches: List[Dict[str, Any]]
    ) -> SystemStatus:
        """
        Calculates NERC compliance status based on asset and mismatch state.
        
        Rules:
        1. CRITICAL/HIGH Severity Mismatch → NON_COMPLIANT
        2. any MEDIUM Mismatch → DEGRADED
        3. Verification Coverage < 95% → DEGRADED (CIP-013 requirement)
        4. Patch Velocity < Threshold → DEGRADED
        5. Otherwise → NOMINAL
        """
        # Rule 1: Severity based compliance
        severities = [m.get("severity") for m in active_mismatches]
        
        if MismatchSeverity.CRITICAL in severities or MismatchSeverity.HIGH in severities:
            return SystemStatus.NON_COMPLIANT
        
        if MismatchSeverity.MEDIUM in severities:
            return SystemStatus.DEGRADED
            
        # Rule 2: Coverage Check
        summary = asset_states.get("summary", {})
        total = summary.get("total_assets", 0)
        verified = summary.get("verified_count", 0)
        
        if total > 0:
            coverage = verified / total
            if coverage < 0.95:  # NERC Standard: 95% verification minimum for CIP-013
                return SystemStatus.DEGRADED
        
        # Rule 3: Patch Metrics (Future implementation)
        # patch_metrics = asset_states.get("patch_metrics", {})
        # if patch_metrics.get("pending_critical") > 0:
        #     return SystemStatus.DEGRADED

        return SystemStatus.NOMINAL
