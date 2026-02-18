import hashlib
from typing import List
import asyncio
from app.models import AnalysisSummary, AnalysisRisk
from app.notifications import notify_hazard # Import notification service
from app.audit import HIPAAAuditLogger

class AnalysisEngine:
    """
    Analyzes documents to produce compliance insights.
    
    Currently implements a deterministic simulation based on document ID 
    to provide consistent feedback without requiring full NLP pipeline integration.
    """
    
    async def analyze_document(self, document_id: str) -> AnalysisSummary:
        # Deterministic simulation based on document_id hash
        # ensuring consistent results for the same document
        
        # Calculate pseudo-random values from hash
        h = int(hashlib.sha256(document_id.encode()).hexdigest(), 16)
        
        # Normalize score 0-100
        risk_score = (h % 100)
        
        # Simulate extraction counts
        obligations = 5 + (h % 30)
        missing_dates = h % 5
        
        risks = []
        
        # Determine risks based on the deterministic score
        if risk_score > 80:
            risks.append(AnalysisRisk(
                id="RISK-001", 
                description="Regulatory deadline missing for critical obligation", 
                severity="CRITICAL"
            ))
            risks.append(AnalysisRisk(
                id="RISK-002", 
                description="Jurisdiction mismatch detected", 
                severity="HIGH"
            ))
        elif risk_score > 60:
             risks.append(AnalysisRisk(
                 id="RISK-003", 
                 description="Ambiguous obligation terms detected", 
                 severity="HIGH"
             ))
        elif risk_score > 40:
             risks.append(AnalysisRisk(
                 id="RISK-004", 
                 description="Low confidence extraction for tables", 
                 severity="MEDIUM"
             ))
        
        # Healthcare PHI Detection (Simulated based on hash)
        if h % 7 == 0:
            phi_risk = AnalysisRisk(
                id="PHI-001",
                description="Unredacted PHI Detected: SSN Pattern found on page 3",
                severity="CRITICAL"
            )
            risks.insert(0, phi_risk)
            risk_score = 95 # Override score to critical
            obligations += 12 # Higher complexity
            
            # Log the PHI detection to the audit trail
            HIPAAAuditLogger.log_phi_detection(
                document_id=document_id,
                risk_description=phi_risk.description,
                severity=phi_risk.severity
            )
        
        # Log general analysis access for audit trail
        HIPAAAuditLogger.log_access(document_id, "SYSTEM_ANALYSIS")
        
        summary = AnalysisSummary(
            document_id=document_id,
            status="COMPLETE",
            risk_score=risk_score,
            obligations_count=obligations,
            missing_dates_count=missing_dates,
            critical_risks=risks
        )

        # Trigger notification (fire and forget or await)
        # We await it here to ensure it's sent, but in prod could be background task
        await notify_hazard(summary)

        return summary
