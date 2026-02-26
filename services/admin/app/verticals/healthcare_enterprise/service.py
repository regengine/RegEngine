from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.sqlalchemy_models import VerticalProjectModel, VerticalRuleInstanceModel
from .schemas import HealthcareEnterpriseMetadata, RiskStatusResponse
# Import the Logic Component we moved earlier:
from .breach_calculator import BreachRiskCalculator, AccessLogEntry

class HealthcareEnterpriseService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.rule_pack_id = "crm_v1"

    def _load_rule_pack(self) -> Dict[str, Any]:
        """
        Loads the surveillance/monitoring rules.
        """
        current_dir = Path(__file__).parent
        json_path = current_dir / "data" / "crm_v1.json"
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def create_crm_project(
        self, 
        tenant_id: UUID, 
        name: str, 
        metadata: HealthcareEnterpriseMetadata, 
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Onboards a new Hospital System to the Clinical Risk Monitor.
        """
        # 1. Create Project
        project = VerticalProjectModel(
            tenant_id=tenant_id,
            name=name,
            vertical="healthcare_enterprise",
            vertical_metadata=metadata.dict(),
            created_by=user_id
        )
        self.db.add(project)
        self.db.flush()
        
        # 2. Instantiate Surveillance Rules
        rule_pack = self._load_rule_pack()
        created_rules = []
        
        for category in rule_pack["categories"]:
            for rule in category["rules"]:
                # Default status for Surveillance is "ACTIVE" (Green means monitoring, Red means breach)
                # But to align with the framework, we'll start as "GRAY" (Pending Data)
                instance = VerticalRuleInstanceModel(
                    project_id=project.id,
                    rule_id=rule["id"],
                    status="gray"
                )
                self.db.add(instance)
                created_rules.append(rule)
        
        self.db.commit()
        
        return {
            "id": str(project.id),
            "name": name,
            "status": "active",
            "rule_count": len(created_rules)
        }

    async def get_risk_status(self, project_id: UUID) -> RiskStatusResponse:
        """
        Calculates the aggregate Risk Score (0.0 - 1.0) based on active alerts.
        """
        # 1. SECURITY GATE: Fetch project to trigger RLS enforcement
        project = self.db.query(VerticalProjectModel).filter(VerticalProjectModel.id == project_id).first()
        if not project:
            # If RLS is working, an unauthorized tenant will get None here.
            raise HTTPException(status_code=404, detail="Project not found or access denied")
        
        # 2. Simulate Logic Check via BreachCalculator
        # In production, we'd feed real access logs here.
        # For the demo, we'll generate a synthetic check.
        calculator = BreachRiskCalculator()
        
        # Simulate some logs based on "monitor_vip_lists" metadata? 
        # We'd need to fetch project metadata first.
        # Assuming high risk for demo purposes if not configured.
        
        mock_logs = [
             AccessLogEntry(
                 user_id="u1", 
                 record_id="rec_vip_1", 
                 patient_id="PT-VIP-001",
                 record_type="demographics",
                 timestamp=datetime.now(), 
                 role="nurse", 
                 action="view",
                 is_vip=True
             ),
             AccessLogEntry(
                 user_id="u1", 
                 record_id="rec_vip_2", 
                 patient_id="PT-VIP-001",
                 record_type="clinical_notes",
                 timestamp=datetime.now(), 
                 role="nurse", 
                 action="view",
                 is_vip=True
             )
        ]
        
        alerts = calculator.analyze_access_pattern(mock_logs)
        
        # 3. Calculate Score
        # Base score 0.1 (baseline risk)
        # + 0.2 per High severity alert
        risk_score = 0.1 + (len(alerts) * 0.2)
        risk_score = min(risk_score, 1.0)
        
        compliance_status = "compliant"
        if risk_score > 0.4: compliance_status = "at_risk"
        if risk_score > 0.8: compliance_status = "breached"
        
        return RiskStatusResponse(
            overall_risk_score=risk_score,
            active_alerts=len(alerts),
            critical_breaches=sum(1 for a in alerts if "VIP" in a), # Simplistic check
            monitored_users=142, # Matches UI mockup
            top_risks=[a for a in alerts],
            compliance_status=compliance_status
        )

    def get_live_logs(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Returns simulated live access stream matching the UI mockup.
        """
        # SECURITY GATE: Trigger RLS
        project = self.db.query(VerticalProjectModel).filter(VerticalProjectModel.id == project_id).first()
        if not project:
             raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Mocking the specific data requested by user
        return [
            {"time": "10:42:01", "user": "Dr. House (MD)", "action": "VIEW record VIP_001", "status": "FLAGGED"},
            {"time": "10:41:55", "user": "Nurse Jackie (RN)", "action": "EDIT record P-9921", "status": "NORMAL"},
            {"time": "10:41:12", "user": "Admin Bill (Admin)", "action": "EXPORT record VIP_001", "status": "CRITICAL"},
            {"time": "10:40:45", "user": "Dr. Grey (MD)", "action": "VIEW record P-3321", "status": "NORMAL"},
            {"time": "10:39:22", "user": "Receptionist (Staff)", "action": "VIEW record P-1123", "status": "NORMAL"},
        ]

    def get_heatmap_data(self, project_id: UUID) -> List[Dict[str, Any]]:
        """
        Returns departmental risk data matching UI mockup.
        """
        # SECURITY GATE: Trigger RLS
        project = self.db.query(VerticalProjectModel).filter(VerticalProjectModel.id == project_id).first()
        if not project:
             raise HTTPException(status_code=404, detail="Project not found or access denied")

        return [
            {"dept": "ICU (Intensive Care)", "risk": 12, "detail": "Normal Access Patterns"},
            {"dept": "ER (Emergency)", "risk": 85, "detail": "VIP Snooping / Mixed Role Access"},
            {"dept": "Psychiatry", "risk": 45, "detail": "Normal Access Patterns"},
            {"dept": "Admin / Billing", "risk": 92, "detail": "VIP Snooping / Mixed Role Access"},
            {"dept": "Pediatrics", "risk": 5, "detail": "Normal Access Patterns"},
        ]
