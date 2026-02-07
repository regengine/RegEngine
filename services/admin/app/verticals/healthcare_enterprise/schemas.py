from typing import Optional, List
from pydantic import BaseModel, Field

class HealthcareEnterpriseMetadata(BaseModel):
    """
    Metadata for a Hospital/Systems CRM installation.
    """
    hospital_system_id: str = Field(description="Internal ID of the parent system")
    tier: str = Field(default="standard", description="standard, premium, or platinum")
    active_directories_connected: bool = Field(default=False)
    monitor_vip_lists: bool = Field(default=True)
    custom_risk_threshold: float = Field(default=0.75)
    
class RiskStatusResponse(BaseModel):
    overall_risk_score: float # 0.0 to 1.0 (1.0 = Max Risk)
    active_alerts: int
    critical_breaches: int
    monitored_users: int
    top_risks: List[str]
    compliance_status: str # 'compliant', 'at_risk', 'breached'
