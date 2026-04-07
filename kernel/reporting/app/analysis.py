import hashlib
from typing import List
import asyncio
from app.models import AnalysisSummary, AnalysisRisk
from app.notifications import notify_hazard # Import notification service

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
