import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AccessLogEntry(BaseModel):
    timestamp: datetime
    user_id: str
    role: str
    patient_id: str
    record_type: str  # e.g., "clinical_notes", "demographics"
    action: str       # "view", "edit", "print"
    is_vip: bool = False

class BreachRiskAlert(BaseModel):
    severity: str     # HIGH, MEDIUM, LOW
    description: str
    evidence_logs: List[AccessLogEntry]
    recommended_action: str

class BreachRiskCalculator:
    """
    Heuristic engine to detect 'Unusual Access Patterns' in ePHI logs.
    Implements the 'Breach Risk Calculator' from the Vertical Expansion Plan.
    """

    def analyze_access_pattern(self, logs: List[AccessLogEntry]) -> List[BreachRiskAlert]:
        alerts = []
        
        # 1. Check for VIP Snooping (High Severity)
        # Condition: Multiple staff accessing a VIP record in a short window
        vip_accesses = [log for log in logs if log.is_vip]
        if vip_accesses:
            # Group by patient
            by_patient = {}
            for log in vip_accesses:
                by_patient.setdefault(log.patient_id, []).append(log)
            
            for patient_id, patient_logs in by_patient.items():
                unique_users = {log.user_id for log in patient_logs}
                if len(unique_users) > 3: # Threshold: >3 distinct staff members
                    alerts.append(BreachRiskAlert(
                        severity="HIGH",
                        description=f"Potential VIP Snooping: {len(unique_users)} distinct staff members accessed VIP Patient {patient_id}.",
                        evidence_logs=patient_logs,
                        recommended_action="Lock record immediately and initiate Privacy Officer review."
                    ))

    
        # 2. Check for "Clinical Mismatch" (Medium Severity)
        # Condition: Non-clinical staff accessing clinical notes
        non_clinical_roles = {"billing", "admin", "reception"}
        suspicious_access = []
        for log in logs:
            if log.role in non_clinical_roles and log.record_type == "clinical_notes":
                suspicious_access.append(log)
        
        if suspicious_access:
            alerts.append(BreachRiskAlert(
                severity="MEDIUM",
                description=f"Clinical Mismatch: {len(suspicious_access)} instances of non-clinical staff viewing clinical notes.",
                evidence_logs=suspicious_access,
                recommended_action="Review Role-Based Access Controls (RBAC) implementation."
            ))
            
        return alerts

    def evaluate_project_risk(self, project_id: str, recent_logs: List[AccessLogEntry]) -> int:
        """
        Returns a risk score (0-100) for the project based on logs.
        """
        alerts = self.analyze_access_pattern(recent_logs)
        score = 0
        for alert in alerts:
            if alert.severity == "HIGH":
                score += 50
            elif alert.severity == "MEDIUM":
                score += 20
            elif alert.severity == "LOW":
                score += 5
        
        return min(score, 100)
