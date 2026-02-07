import logging
from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class EvidenceRequest(BaseModel):
    control_id: str
    evidence_type: str # 'config_snapshot', 'policy_doc', 'access_review'
    status: str # 'collected', 'missing', 'expired'
    last_collected: datetime

class TrustCenterStatus(BaseModel):
    overall_health: int # 0-100
    passing_controls: int
    failing_controls: int
    public_status: str # 'Operational', 'Degraded'

class EvidenceCollector:
    """
    Automates SOC 2 evidence gathering (Simulated).
    Powering the 'Trust Center' view.
    """

    def check_readiness(self, evidence_items: List[EvidenceRequest]) -> TrustCenterStatus:
        passing = 0
        failing = 0
        
        for item in evidence_items:
            if item.status == 'collected':
                passing += 1
            else:
                failing += 1
        
        total = passing + failing
        score = int((passing / total) * 100) if total > 0 else 0
        
        status_label = "Operational"
        if score < 90:
            status_label = "At Risk"
        if score < 70:
            status_label = "Degraded"

        return TrustCenterStatus(
            overall_health=score,
            passing_controls=passing,
            failing_controls=failing,
            public_status=status_label
        )
