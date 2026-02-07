from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.database import get_session
from app.dependencies import get_current_tenant
from sqlalchemy.orm import Session
from uuid import UUID

# Import Vertical Logic Services
# from .healthcare.breach_calculator import BreachRiskCalculator, AccessLogEntry # MOVED TO ENTERPRISE
# from .healthcare.breach_calculator import BreachRiskCalculator, AccessLogEntry # MOVED TO ENTERPRISE
from .healthcare_enterprise.breach_calculator import BreachRiskCalculator, AccessLogEntry
from .healthcare_enterprise.service import HealthcareEnterpriseService
from .healthcare_enterprise.schemas import HealthcareEnterpriseMetadata, RiskStatusResponse

from .finance.reconciliation_bot import ReconciliationBot, TransactionRecord, InventoryLog
from .gaming.risk_scorer import PlayerRiskScorer, DepositEvent
from .energy.supply_chain import SupplyChainValidator, SoftwareAsset, VendorPatch
from .technology.evidence_collector import EvidenceCollector, EvidenceRequest

router = APIRouter(prefix="/verticals", tags=["Verticals"])

# --- HEALTHCARE (MSCF: Public Interest) ---
# Purely administrative. No surveillance.

# --- HEALTHCARE (ENTERPRISE: Clinical Risk) ---
@router.post("/healthcare-enterprise/projects")
async def create_enterprise_project(
    name: str, 
    metadata: HealthcareEnterpriseMetadata,
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    [CRM] Onboard a Hospital System to the Clinical Risk Monitor.
    """
    service = HealthcareEnterpriseService(db)
    return await service.create_crm_project(tenant_id, name, metadata)

@router.get("/healthcare-enterprise/{project_id}/risk")
async def get_enterprise_risk(
    project_id: UUID, 
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
) -> RiskStatusResponse:
    """
    [CRM] Get Real-time Risk Score for a Hospital System.
    """
    service = HealthcareEnterpriseService(db)
    return await service.get_risk_status(project_id)

@router.get("/healthcare-enterprise/{project_id}/logs")
async def get_enterprise_logs(
    project_id: UUID,
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    [CRM] Get Live Access Logs for the Risk Monitor.
    """
    service = HealthcareEnterpriseService(db)
    return service.get_live_logs(project_id)

@router.get("/healthcare-enterprise/{project_id}/heatmap")
async def get_enterprise_heatmap(
    project_id: UUID,
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    [CRM] Get Departmental Risk Heatmap data.
    """
    service = HealthcareEnterpriseService(db)
    return service.get_heatmap_data(project_id)

@router.post("/healthcare-enterprise/analyze-breach-risk")
def analyze_healthcare_breach(logs: List[AccessLogEntry]):
    """
    [ENTERPRISE ONLY] Analyze access logs for VIP snooping or clinical mismatch.
    NOT FOR USE IN MSCF CONTEXT.
    """
    calculator = BreachRiskCalculator()
    alerts = calculator.analyze_access_pattern(logs)
    return {"alerts": alerts, "count": len(alerts)}

from fastapi.responses import StreamingResponse
from .healthcare.service import HealthcareVerticalService
import io

@router.get("/healthcare/export/lifeboat")
async def export_healthcare_lifeboat(
    project_id: UUID, 
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    Download a 'Lifeboat' ZIP archive of the clinic's state.
    Constitution 5.1: Survivable Stack.
    """
    service = HealthcareVerticalService() # In real app, inject this
    zip_bytes = await service.generate_lifeboat_archive(tenant_id, project_id)
    
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=lifeboat_export_{project_id}.zip"}
    )

@router.get("/healthcare/export/evidence")
async def export_healthcare_evidence(
    project_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    db: Session = Depends(get_session)
):
    """
    Export all evidence logs for a healthcare project as CSV.
    
    Returns a CSV file with:
    - Evidence ID
    - Rule ID  
    - Evidence type
    - Content hash
    - Timestamp
    - User ID (if applicable)
    """
    from app.sqlalchemy_models import EvidenceLogModel
    from sqlalchemy import select
    import csv
    
    # Fetch all evidence logs for this project
    stmt = (
        select(EvidenceLogModel)
        .where(EvidenceLogModel.project_id == project_id)
        .where(EvidenceLogModel.tenant_id == tenant_id)
        .order_by(EvidenceLogModel.created_at.desc())
    )
    
    result = db.execute(stmt)
    logs = result.scalars().all()
    
    if not logs:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No evidence logs found for this project")
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'id', 'rule_id', 'evidence_type', 'content_hash', 'created_at', 'user_id', 'data_summary'
    ])
    writer.writeheader()
    
    for log in logs:
        writer.writerow({
            'id': str(log.id),
            'rule_id': log.rule_id,
            'evidence_type': log.evidence_type,
            'content_hash': log.content_hash,
            'created_at': log.created_at.isoformat(),
            'user_id': str(log.user_id) if log.user_id else '',
            'data_summary': str(log.data)[:100] if log.data else ''  # First 100 chars
        })
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=evidence_export_{project_id}.csv"
        }
    )


from .healthcare.schemas import HealthcareProjectMetadata, FacilityType

@router.get("/healthcare/status")
async def get_healthcare_status(
    dispenses_medication: bool = False,
    has_paid_staff: bool = False,
    facility_type: FacilityType = FacilityType.FREE_CLINIC,
    state: str = "CA",
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    [MSCF] Calculate safety status based on clinic metadata.
    This creates an ephemeral check of the rule engine.
    """
    service = HealthcareVerticalService(db_session=db)
    
    # 1. Reconstruct Metadata
    metadata = HealthcareProjectMetadata(
        facility_type=facility_type,
        state=state,
        dispenses_medication=dispenses_medication,
        has_paid_staff=has_paid_staff,
        operating_state="active"
    )
    
    # 2. Get Rules & Evaluate
    rules = service._get_applicable_rules(metadata)
    # Using a dummy project ID for status check is fine as it doesn't write to DB for status
    overall_status = await service.evaluate_safety_status(UUID("00000000-0000-0000-0000-000000000000"), rules)
    
    # 3. Format Response for Dashboard props
    # Use default pillars but fill in the calculated statuses
    pillars = [
        {
            "title": "Governance",
            "status": "yellow", # Mock aggregation
            "controls": [r for r in rules if r['id'].startswith("GOV")]
        },
        {
            "title": "Clinical Authority",
            "status": "green",
            "controls": [r for r in rules if r['id'].startswith("CLIN")]
        },
        {
            "title": "Patient Data Safety",
            "status": "red",
            "controls": [r for r in rules if r['id'].startswith("DATA")]
        },
        {
            "title": "Operational Resilience",
            "status": "yellow",
            "controls": [r for r in rules if r['id'].startswith("OPS")]
        }
    ]
    
    if dispenses_medication:
        pillars.append({
            "title": "Medication Safety",
            "status": "red",
            "controls": [r for r in rules if r['id'].startswith("MED")]
        })
        
    return {
        "overall": overall_status,
        "pillars": pillars,
        "timestamp": "now"
    }

@router.post("/healthcare/projects")
async def create_healthcare_project(
    name: str,
    metadata: HealthcareProjectMetadata,
    db: Session = Depends(get_session),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    [MSCF] Create a new Clinic Project and instantiate rules.
    Persists to database.
    """
    service = HealthcareVerticalService(db_session=db)
    
    result = await service.create_clinic_project(
        tenant_id=tenant_id,
        name=name,
        metadata=metadata
    )
    return result

# --- FINANCE ---
@router.post("/finance/reconcile")
def run_finance_reconciliation(transactions: List[TransactionRecord], inventory: List[InventoryLog]):
    """Run SOX 404 reconciliation check."""
    bot = ReconciliationBot()
    issues = bot.reconcile_sales(transactions, inventory)
    return {"issues": issues, "balanced": len(issues) == 0}

# --- GAMING ---
@router.post("/gaming/risk-score")
def calculate_player_risk(deposits: List[DepositEvent]):
    """Detect AML patterns like structuring."""
    scorer = PlayerRiskScorer()
    alerts = scorer.analyze_deposits(deposits)
    return {"alerts": alerts, "high_risk_players": [a.player_ids for a in alerts]}

# --- ENERGY ---
@router.post("/energy/validate-firmware")
def validate_energy_assets(assets: List[SoftwareAsset], patches: List[VendorPatch]):
    """Verify NERC CIP supply chain integrity."""
    validator = SupplyChainValidator()
    alerts = validator.validate_hashes(assets, patches)
    return {"violations": alerts, "compliant": len(alerts) == 0}

# --- TECHNOLOGY ---
@router.post("/technology/trust-status")
def get_trust_center_status(evidence: List[EvidenceRequest]):
    """Calculate SOC 2 Trust Center health."""
    collector = EvidenceCollector()
    status = collector.check_readiness(evidence)
    return status
