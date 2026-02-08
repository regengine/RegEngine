"""
PCOS Compliance Router — Forms, worker classification, paperwork, snapshots, audit.
"""
from __future__ import annotations
import uuid as uuid_module
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ._shared import get_pcos_tenant_context
from ..pcos_models import (
    PCOSProjectModel, PCOSLocationModel, PCOSPersonModel, PCOSEngagementModel,
    PCOSFormTemplateModel, PCOSGeneratedFormModel,
    PCOSClassificationAnalysisModel, PCOSClassificationExemptionModel,
    PCOSDocumentRequirementModel, PCOSEngagementDocumentModel,
    PCOSVisaCategoryModel, PCOSPersonVisaStatusModel,
    PCOSComplianceSnapshotModel, PCOSRuleEvaluationModel, PCOSAuditEventModel,
)

logger = structlog.get_logger("pcos.compliance")
router = APIRouter(tags=["PCOS Compliance"])

# === FORM AUTO-FILL ===

@router.get("/projects/{project_id}/forms/filmla")
def get_filmla_permit_form(project_id: uuid_module.UUID, location_id: Optional[uuid_module.UUID] = Query(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Generate pre-filled FilmLA permit application data."""
    from ..filmla_form_generator import generate_filmla_form
    from ..pcos_models import PCOSCompanyModel, PCOSInsurancePolicyModel
    db, tenant_id = ctx
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    company = db.execute(select(PCOSCompanyModel).where(PCOSCompanyModel.id == project.company_id, PCOSCompanyModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Company not found for project")
    if location_id:
        location = db.execute(select(PCOSLocationModel).where(PCOSLocationModel.id == location_id, PCOSLocationModel.project_id == project_id, PCOSLocationModel.tenant_id == tenant_id)).scalar_one_or_none()
    else:
        location = db.execute(select(PCOSLocationModel).where(PCOSLocationModel.project_id == project_id, PCOSLocationModel.tenant_id == tenant_id).limit(1)).scalar_one_or_none()
    if not location:
        raise HTTPException(404, "No location found for project. Add a location first.")
    insurance = db.execute(select(PCOSInsurancePolicyModel).where(PCOSInsurancePolicyModel.company_id == company.id, PCOSInsurancePolicyModel.tenant_id == tenant_id, PCOSInsurancePolicyModel.status == "active").limit(1)).scalar_one_or_none()
    project_data = {"name": project.name, "code": project.code, "project_type": project.project_type, "start_date": project.start_date.isoformat() if project.start_date else None, "end_date": project.end_date.isoformat() if project.end_date else None}
    company_data = {"name": company.name, "primary_contact_name": company.primary_contact_name, "primary_contact_phone": company.primary_contact_phone, "primary_contact_email": company.primary_contact_email, "address_line1": company.address_line1, "city": company.city, "state": company.state, "zip": company.zip}
    location_data = {"name": location.name, "address_line1": location.address_line1, "city": location.city, "state": location.state, "zip": location.zip, "estimated_crew_size": location.estimated_crew_size, "parking_spaces_needed": location.parking_spaces_needed, "has_generator": location.has_generator, "has_special_effects": location.has_special_effects, "shoot_dates": [d.isoformat() for d in (location.shoot_dates or [])]}
    insurance_data = None
    if insurance:
        insurance_data = {"carrier_name": insurance.carrier_name, "policy_number": insurance.policy_number, "expiration_date": insurance.expiration_date.isoformat() if insurance.expiration_date else None}
    form_result = generate_filmla_form(project_data, company_data, location_data, insurance_data)
    template = db.execute(select(PCOSFormTemplateModel).where(PCOSFormTemplateModel.template_code == "FILMLA_PERMIT", PCOSFormTemplateModel.is_active == True)).scalar_one_or_none()
    if template:
        existing = db.execute(select(PCOSGeneratedFormModel).where(PCOSGeneratedFormModel.project_id == project_id, PCOSGeneratedFormModel.location_id == location.id, PCOSGeneratedFormModel.template_id == template.id, PCOSGeneratedFormModel.tenant_id == tenant_id)).scalar_one_or_none()
        if not existing:
            existing = PCOSGeneratedFormModel(tenant_id=tenant_id, project_id=project_id, template_id=template.id, location_id=location.id, requires_signature=template.requires_signature)
            db.add(existing)
        existing.source_data_snapshot = form_result["source_data_snapshot"]
        existing.status = "ready" if form_result["is_complete"] else "draft"
        db.commit()
        form_result["generated_form_id"] = str(existing.id)
    form_result["project_id"] = str(project_id)
    form_result["location_id"] = str(location.id)
    return form_result

# === WORKER CLASSIFICATION ===

@router.post("/engagements/{engagement_id}/classify")
def classify_engagement(engagement_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Analyze an engagement for worker classification using CA AB5 ABC Test."""
    from ..abc_test_evaluator import analyze_engagement_classification
    from ..pcos_models import PCOSCompanyModel
    db, tenant_id = ctx
    engagement = db.execute(select(PCOSEngagementModel).where(PCOSEngagementModel.id == engagement_id, PCOSEngagementModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(404, "Engagement not found")
    person = db.execute(select(PCOSPersonModel).where(PCOSPersonModel.id == engagement.person_id, PCOSPersonModel.tenant_id == tenant_id)).scalar_one_or_none()
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == engagement.project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    company = None
    if project:
        company = db.execute(select(PCOSCompanyModel).where(PCOSCompanyModel.id == project.company_id, PCOSCompanyModel.tenant_id == tenant_id)).scalar_one_or_none()
    exemptions = db.execute(select(PCOSClassificationExemptionModel).where(PCOSClassificationExemptionModel.is_active == True)).scalars().all()
    exemptions_list = [{"exemption_code": e.exemption_code, "exemption_name": e.exemption_name, "exemption_category": e.exemption_category, "qualifying_criteria": e.qualifying_criteria, "description": e.description} for e in exemptions]
    engagement_data = {"role_title": engagement.role_title, "department": engagement.department, "classification": engagement.classification, "pay_rate": float(engagement.pay_rate) if engagement.pay_rate else None, "pay_type": engagement.pay_type, "sets_own_methods": engagement.classification == "contractor", "sets_own_schedule": engagement.pay_type != "hourly", "supervision_level": "minimal" if engagement.classification == "contractor" else "medium", "training_provided": engagement.classification == "employee"}
    person_data = {}
    if person:
        person_data = {"has_business_entity": person.preferred_classification == "contractor", "other_client_count": 0, "owns_equipment": False, "advertises_services": False}
    company_data = {}
    if company:
        company_data = {"name": company.name, "business_type": "production"}
    result = analyze_engagement_classification(engagement_data, person_data, company_data, questionnaire_responses=None, exemptions=exemptions_list)
    analysis = PCOSClassificationAnalysisModel(tenant_id=tenant_id, engagement_id=engagement_id, rule_version=result["rule_version"], prong_a_passed=result["prong_a"]["passed"], prong_a_score=result["prong_a"]["score"], prong_a_factors=result["prong_a"]["factors"], prong_a_reasoning=result["prong_a"]["reasoning"], prong_b_passed=result["prong_b"]["passed"], prong_b_score=result["prong_b"]["score"], prong_b_factors=result["prong_b"]["factors"], prong_b_reasoning=result["prong_b"]["reasoning"], prong_c_passed=result["prong_c"]["passed"], prong_c_score=result["prong_c"]["score"], prong_c_factors=result["prong_c"]["factors"], prong_c_reasoning=result["prong_c"]["reasoning"], overall_result=result["overall_result"], overall_score=result["overall_score"], confidence_level=result["confidence"], risk_level=result["risk_level"], risk_factors=result["risk_factors"], recommended_action=result["recommended_action"], exemption_applicable=result.get("exemption", {}).get("is_applicable", False) if result.get("exemption") else False, exemption_type=result.get("exemption", {}).get("type") if result.get("exemption") else None)
    db.add(analysis); db.commit()
    result["analysis_id"] = str(analysis.id)
    result["engagement_id"] = str(engagement_id)
    return result

@router.get("/engagements/{engagement_id}/classification")
def get_engagement_classification(engagement_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get the most recent classification analysis for an engagement."""
    db, tenant_id = ctx
    analysis = db.execute(select(PCOSClassificationAnalysisModel).where(PCOSClassificationAnalysisModel.engagement_id == engagement_id, PCOSClassificationAnalysisModel.tenant_id == tenant_id).order_by(PCOSClassificationAnalysisModel.analyzed_at.desc()).limit(1)).scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "No classification analysis found")
    return {"analysis_id": str(analysis.id), "engagement_id": str(engagement_id), "overall_result": analysis.overall_result, "overall_score": analysis.overall_score, "confidence": analysis.confidence_level, "risk_level": analysis.risk_level, "risk_factors": analysis.risk_factors, "recommended_action": analysis.recommended_action, "analyzed_at": analysis.analyzed_at.isoformat(), "prong_a": {"passed": analysis.prong_a_passed, "score": analysis.prong_a_score, "reasoning": analysis.prong_a_reasoning}, "prong_b": {"passed": analysis.prong_b_passed, "score": analysis.prong_b_score, "reasoning": analysis.prong_b_reasoning}, "prong_c": {"passed": analysis.prong_c_passed, "score": analysis.prong_c_score, "reasoning": analysis.prong_c_reasoning}, "exemption_applicable": analysis.exemption_applicable, "exemption_type": analysis.exemption_type}

# === PAPERWORK TRACKING ===

@router.get("/projects/{project_id}/paperwork-status")
def get_project_paperwork_status(project_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get paperwork completion status for all engagements in a project."""
    db, tenant_id = ctx
    engagements = db.execute(select(PCOSEngagementModel).where(PCOSEngagementModel.project_id == project_id, PCOSEngagementModel.tenant_id == tenant_id)).scalars().all()
    if not engagements:
        return {"project_id": str(project_id), "engagements": [], "overall_completion_pct": 0, "total_pending": 0, "total_received": 0}
    requirements = db.execute(select(PCOSDocumentRequirementModel).where(PCOSDocumentRequirementModel.is_active == True)).scalars().all()
    engagement_statuses = []; total_docs = 0; total_received = 0; total_pending = 0
    for eng in engagements:
        person = db.execute(select(PCOSPersonModel).where(PCOSPersonModel.id == eng.person_id, PCOSPersonModel.tenant_id == tenant_id)).scalar_one_or_none()
        visa_status = None
        if person:
            visa_status = db.execute(select(PCOSPersonVisaStatusModel).where(PCOSPersonVisaStatusModel.person_id == person.id, PCOSPersonVisaStatusModel.tenant_id == tenant_id).limit(1)).scalar_one_or_none()
        is_minor = person.date_of_birth is not None if person else False
        has_visa = visa_status is not None
        applicable_reqs = []
        for req in requirements:
            if req.applies_to_classification not in (None, "both", eng.classification):
                continue
            if req.applies_to_minor and not is_minor:
                continue
            if req.applies_to_visa_holder and not has_visa:
                continue
            applicable_reqs.append(req)
        existing_docs = db.execute(select(PCOSEngagementDocumentModel).where(PCOSEngagementDocumentModel.engagement_id == eng.id, PCOSEngagementDocumentModel.tenant_id == tenant_id)).scalars().all()
        doc_map = {str(d.requirement_id): d for d in existing_docs}
        docs = []; eng_received = 0; eng_pending = 0
        for req in applicable_reqs:
            doc = doc_map.get(str(req.id))
            s = doc.status if doc else "pending"
            if s in ("received", "verified"):
                eng_received += 1
            else:
                eng_pending += 1
            docs.append({"requirement_code": req.requirement_code, "requirement_name": req.requirement_name, "document_type": req.document_type, "is_required": req.is_required, "status": s, "received_at": doc.received_at.isoformat() if doc and doc.received_at else None})
        total = eng_received + eng_pending
        completion_pct = (eng_received / total * 100) if total > 0 else 0
        engagement_statuses.append({"engagement_id": str(eng.id), "person_name": f"{person.first_name} {person.last_name}" if person else "Unknown", "role_title": eng.role_title, "classification": eng.classification, "documents": docs, "received_count": eng_received, "pending_count": eng_pending, "completion_pct": round(completion_pct, 1)})
        total_docs += total; total_received += eng_received; total_pending += eng_pending
    overall_pct = (total_received / total_docs * 100) if total_docs > 0 else 0
    return {"project_id": str(project_id), "engagements": engagement_statuses, "overall_completion_pct": round(overall_pct, 1), "total_docs": total_docs, "total_received": total_received, "total_pending": total_pending}

@router.get("/people/{person_id}/visa-timeline")
def get_person_visa_timeline(person_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get visa status and timeline warnings for a person."""
    db, tenant_id = ctx
    person = db.execute(select(PCOSPersonModel).where(PCOSPersonModel.id == person_id, PCOSPersonModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Person not found")
    visa_status = db.execute(select(PCOSPersonVisaStatusModel).where(PCOSPersonVisaStatusModel.person_id == person_id, PCOSPersonVisaStatusModel.tenant_id == tenant_id).order_by(PCOSPersonVisaStatusModel.created_at.desc()).limit(1)).scalar_one_or_none()
    if not visa_status:
        return {"person_id": str(person_id), "person_name": f"{person.first_name} {person.last_name}", "has_visa_record": False, "is_us_citizen_assumed": True, "warnings": []}
    visa_category = None
    if visa_status.visa_category_id:
        visa_category = db.execute(select(PCOSVisaCategoryModel).where(PCOSVisaCategoryModel.id == visa_status.visa_category_id)).scalar_one_or_none()
    warnings = []; today = date.today()
    if visa_status.expiration_date:
        days = (visa_status.expiration_date - today).days
        if days < 0:
            warnings.append({"type": "critical", "message": f"Visa expired {abs(days)} days ago", "action": "Cannot work legally; engagement must be terminated"})
        elif days <= 30:
            warnings.append({"type": "high", "message": f"Visa expires in {days} days", "action": "Initiate renewal immediately"})
        elif days <= 90:
            warnings.append({"type": "medium", "message": f"Visa expires in {days} days", "action": "Begin renewal planning"})
    if visa_status.i94_expiration:
        i94_days = (visa_status.i94_expiration - today).days
        if i94_days < 0:
            warnings.append({"type": "critical", "message": "I-94 expired - unlawful presence accruing", "action": "Consult immigration attorney immediately"})
        elif i94_days <= 30:
            warnings.append({"type": "high", "message": f"I-94 expires in {i94_days} days", "action": "Plan departure or extension before expiry"})
    if visa_status.ead_expiration:
        ead_days = (visa_status.ead_expiration - today).days
        if ead_days < 0:
            warnings.append({"type": "critical", "message": "EAD expired - work authorization invalid", "action": "Cannot work until EAD renewed"})
        elif ead_days <= 90:
            warnings.append({"type": "medium", "message": f"EAD expires in {ead_days} days", "action": "File renewal application"})
    if visa_status.employer_restricted and visa_category and visa_category.employer_specific:
        warnings.append({"type": "info", "message": "Visa is employer-specific", "action": f"Worker authorized only for: {visa_status.restricted_to_employer or 'Current employer'}"})
    return {"person_id": str(person_id), "person_name": f"{person.first_name} {person.last_name}", "has_visa_record": True, "visa_code": visa_status.visa_code, "visa_name": visa_category.visa_name if visa_category else visa_status.visa_code, "status": visa_status.status, "is_work_authorized": visa_status.is_work_authorized, "expiration_date": visa_status.expiration_date.isoformat() if visa_status.expiration_date else None, "i94_expiration": visa_status.i94_expiration.isoformat() if visa_status.i94_expiration else None, "ead_expiration": visa_status.ead_expiration.isoformat() if visa_status.ead_expiration else None, "employer_restricted": visa_status.employer_restricted, "warnings": warnings, "warning_count": len(warnings), "has_critical_warning": any(w["type"] == "critical" for w in warnings)}

# === COMPLIANCE SNAPSHOTS ===

@router.post("/projects/{project_id}/compliance-snapshots")
def create_compliance_snapshot(project_id: uuid_module.UUID, snapshot_type: str = Query("manual"), snapshot_name: Optional[str] = Query(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Create a point-in-time compliance snapshot for a project."""
    from ..compliance_snapshot_service import ComplianceSnapshotService
    db, tenant_id = ctx
    service = ComplianceSnapshotService(db, tenant_id)
    return service.create_snapshot(project_id=project_id, snapshot_type=snapshot_type, snapshot_name=snapshot_name, trigger_reason="Manual snapshot via API")

@router.get("/projects/{project_id}/compliance-snapshots")
def list_compliance_snapshots(project_id: uuid_module.UUID, limit: int = Query(10, le=50), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """List compliance snapshots for a project."""
    db, tenant_id = ctx
    snapshots = db.execute(select(PCOSComplianceSnapshotModel).where(PCOSComplianceSnapshotModel.project_id == project_id, PCOSComplianceSnapshotModel.tenant_id == tenant_id).order_by(PCOSComplianceSnapshotModel.created_at.desc()).limit(limit)).scalars().all()
    return [{"id": str(s.id), "snapshot_type": s.snapshot_type, "snapshot_name": s.snapshot_name, "compliance_status": s.compliance_status, "overall_score": s.overall_score, "rules_evaluated": s.total_rules_evaluated, "passed": s.rules_passed, "failed": s.rules_failed, "warnings": s.rules_warning, "is_attested": s.is_attested, "created_at": s.created_at.isoformat()} for s in snapshots]

@router.get("/compliance-snapshots/{snapshot_id}")
def get_compliance_snapshot(snapshot_id: uuid_module.UUID, include_evaluations: bool = Query(False), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get a compliance snapshot with optional rule evaluations."""
    db, tenant_id = ctx
    snapshot = db.execute(select(PCOSComplianceSnapshotModel).where(PCOSComplianceSnapshotModel.id == snapshot_id, PCOSComplianceSnapshotModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    result = {"id": str(snapshot.id), "project_id": str(snapshot.project_id), "snapshot_type": snapshot.snapshot_type, "snapshot_name": snapshot.snapshot_name, "compliance_status": snapshot.compliance_status, "overall_score": snapshot.overall_score, "total_rules_evaluated": snapshot.total_rules_evaluated, "rules_passed": snapshot.rules_passed, "rules_failed": snapshot.rules_failed, "rules_warning": snapshot.rules_warning, "category_scores": snapshot.category_scores, "delta_summary": snapshot.delta_summary, "project_state": snapshot.project_state, "is_attested": snapshot.is_attested, "attested_at": snapshot.attested_at.isoformat() if snapshot.attested_at else None, "created_at": snapshot.created_at.isoformat()}
    if include_evaluations:
        evaluations = db.execute(select(PCOSRuleEvaluationModel).where(PCOSRuleEvaluationModel.snapshot_id == snapshot_id).order_by(PCOSRuleEvaluationModel.rule_category)).scalars().all()
        result["evaluations"] = [{"id": str(e.id), "rule_code": e.rule_code, "rule_name": e.rule_name, "rule_category": e.rule_category, "entity_type": e.entity_type, "result": e.result, "severity": e.severity, "message": e.message, "source_authorities": e.source_authorities} for e in evaluations]
    return result

@router.get("/compliance-snapshots/{snapshot_id_1}/compare/{snapshot_id_2}")
def compare_snapshots(snapshot_id_1: uuid_module.UUID, snapshot_id_2: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Compare two compliance snapshots."""
    from ..compliance_snapshot_service import ComplianceSnapshotService
    db, tenant_id = ctx
    return ComplianceSnapshotService(db, tenant_id).compare_snapshots(snapshot_id_1, snapshot_id_2)

# === AUDIT PACK ===

@router.get("/projects/{project_id}/audit-pack")
def get_audit_pack(project_id: uuid_module.UUID, snapshot_id: Optional[uuid_module.UUID] = Query(None), include_evidence: bool = Query(True), include_budget: bool = Query(True), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Generate a comprehensive audit pack for a project."""
    from ..audit_pack_service import AuditPackService
    db, tenant_id = ctx
    return AuditPackService(db, tenant_id).generate_audit_pack(project_id=project_id, snapshot_id=snapshot_id, include_evidence_list=include_evidence, include_budget_summary=include_budget)

@router.post("/compliance-snapshots/{snapshot_id}/attest")
def attest_snapshot(snapshot_id: uuid_module.UUID, attestation_notes: Optional[str] = Query(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Attest to a compliance snapshot's accuracy."""
    db, tenant_id = ctx
    snapshot = db.execute(select(PCOSComplianceSnapshotModel).where(PCOSComplianceSnapshotModel.id == snapshot_id, PCOSComplianceSnapshotModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    if snapshot.is_attested:
        raise HTTPException(400, "Snapshot already attested")
    snapshot.is_attested = True
    snapshot.attested_at = datetime.now(timezone.utc)
    snapshot.attestation_notes = attestation_notes
    audit_event = PCOSAuditEventModel(tenant_id=tenant_id, project_id=snapshot.project_id, event_type="attestation", event_action="created", entity_type="compliance_snapshot", entity_id=snapshot.id, event_data={"snapshot_type": snapshot.snapshot_type, "compliance_status": snapshot.compliance_status, "overall_score": snapshot.overall_score, "attestation_notes": attestation_notes})
    db.add(audit_event); db.commit()
    return {"snapshot_id": str(snapshot_id), "is_attested": True, "attested_at": snapshot.attested_at.isoformat(), "message": "Snapshot successfully attested"}

@router.get("/projects/{project_id}/audit-events")
def list_audit_events(project_id: uuid_module.UUID, event_type: Optional[str] = Query(None), limit: int = Query(50, le=100), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """List audit events for a project."""
    db, tenant_id = ctx
    query = select(PCOSAuditEventModel).where(PCOSAuditEventModel.project_id == project_id, PCOSAuditEventModel.tenant_id == tenant_id)
    if event_type:
        query = query.where(PCOSAuditEventModel.event_type == event_type)
    events = db.execute(query.order_by(PCOSAuditEventModel.created_at.desc()).limit(limit)).scalars().all()
    return [{"id": str(e.id), "event_type": e.event_type, "event_action": e.event_action, "entity_type": e.entity_type, "entity_id": str(e.entity_id) if e.entity_id else None, "event_data": e.event_data, "created_at": e.created_at.isoformat()} for e in events]
