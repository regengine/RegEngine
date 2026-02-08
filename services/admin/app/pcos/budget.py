"""
PCOS Budget Router — Budget CRUD, rate validation, tax credits, fringe analysis.
"""
from __future__ import annotations
import uuid as uuid_module
from datetime import datetime
from typing import Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from ._shared import get_pcos_tenant_context
from ..pcos_models import (
    PCOSProjectModel, PCOSBudgetModel, PCOSBudgetLineItemModel,
    PCOSUnionRateCheckModel, PCOSTaxCreditApplicationModel,
    PCOSQualifiedSpendCategoryModel,
)

logger = structlog.get_logger("pcos.budget")
router = APIRouter(tags=["PCOS Budget"])

@router.post("/projects/{project_id}/budgets", status_code=status.HTTP_201_CREATED)
def upload_budget(project_id: uuid_module.UUID, budget_data: dict, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Create a budget record from parsed spreadsheet data."""
    db, tenant_id = ctx
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.execute(PCOSBudgetModel.__table__.update().where(PCOSBudgetModel.project_id == project_id).where(PCOSBudgetModel.tenant_id == tenant_id).where(PCOSBudgetModel.is_active == True).values(is_active=False))
    compliance_count = 0; critical_count = 0
    for dept in budget_data.get("departments", []):
        for item in dept.get("lineItems", []):
            flags = item.get("complianceFlags", [])
            compliance_count += len(flags)
            if any("misclassification" in f or "critical" in f for f in flags):
                critical_count += 1
    budget = PCOSBudgetModel(tenant_id=tenant_id, project_id=project_id, source_file_name=budget_data.get("fileName", "budget.xlsx"), grand_total=budget_data.get("grandTotal", 0), subtotal=budget_data.get("subtotal", 0), contingency_amount=budget_data.get("contingency", 0), contingency_percent=budget_data.get("contingencyPercent", 0), detected_location=budget_data.get("location", "CA"), status="active", is_active=True, compliance_issue_count=compliance_count, critical_issue_count=critical_count, risk_score=min(100, critical_count * 25 + compliance_count * 5))
    db.add(budget); db.flush()
    line_number = 0
    for dept in budget_data.get("departments", []):
        for item in dept.get("lineItems", []):
            line_number += 1
            li = PCOSBudgetLineItemModel(tenant_id=tenant_id, budget_id=budget.id, row_number=line_number, cost_code=item.get("costCode"), department=dept.get("name"), description=item.get("description", "Unknown"), rate=item.get("rate", 0), quantity=item.get("quantity", 1), extension=item.get("extension", 0), classification=item.get("classification"), role_category=item.get("roleCategory"), deal_memo_status=item.get("dealMemoStatus"), compliance_flags=item.get("complianceFlags", []), raw_row_data=item)
            db.add(li)
    db.commit(); db.refresh(budget)
    logger.info("budget_created", budget_id=str(budget.id), project_id=str(project_id), grand_total=float(budget.grand_total), line_item_count=line_number)
    return {"id": str(budget.id), "project_id": str(project_id), "grand_total": float(budget.grand_total), "line_item_count": line_number, "compliance_issue_count": compliance_count, "risk_score": budget.risk_score, "created_at": budget.created_at.isoformat()}

@router.get("/projects/{project_id}/budgets")
def list_project_budgets(project_id: uuid_module.UUID, active_only: bool = Query(True), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """List all budgets for a project."""
    db, tenant_id = ctx
    query = select(PCOSBudgetModel).where(PCOSBudgetModel.project_id == project_id, PCOSBudgetModel.tenant_id == tenant_id)
    if active_only:
        query = query.where(PCOSBudgetModel.is_active == True)
    budgets = db.execute(query.order_by(PCOSBudgetModel.created_at.desc())).scalars().all()
    return [{"id": str(b.id), "source_file_name": b.source_file_name, "grand_total": float(b.grand_total), "subtotal": float(b.subtotal), "contingency_percent": float(b.contingency_percent) if b.contingency_percent else 0, "detected_location": b.detected_location, "is_active": b.is_active, "compliance_issue_count": b.compliance_issue_count, "risk_score": b.risk_score, "created_at": b.created_at.isoformat()} for b in budgets]

@router.get("/budgets/{budget_id}")
def get_budget(budget_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get a budget with all line items."""
    db, tenant_id = ctx
    budget = db.execute(select(PCOSBudgetModel).where(PCOSBudgetModel.id == budget_id, PCOSBudgetModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    line_items = db.execute(select(PCOSBudgetLineItemModel).where(PCOSBudgetLineItemModel.budget_id == budget_id).order_by(PCOSBudgetLineItemModel.row_number)).scalars().all()
    departments = {}
    for item in line_items:
        dept = item.department or "Uncategorized"
        if dept not in departments:
            departments[dept] = {"name": dept, "lineItems": [], "subtotal": 0}
        departments[dept]["lineItems"].append({"id": str(item.id), "costCode": item.cost_code, "description": item.description, "rate": float(item.rate) if item.rate else 0, "quantity": float(item.quantity) if item.quantity else 1, "extension": float(item.extension), "classification": item.classification, "roleCategory": item.role_category, "dealMemoStatus": item.deal_memo_status, "complianceFlags": item.compliance_flags or []})
        departments[dept]["subtotal"] += float(item.extension)
    return {"id": str(budget.id), "project_id": str(budget.project_id), "source_file_name": budget.source_file_name, "grand_total": float(budget.grand_total), "subtotal": float(budget.subtotal), "contingency_amount": float(budget.contingency_amount) if budget.contingency_amount else 0, "contingency_percent": float(budget.contingency_percent) if budget.contingency_percent else 0, "detected_location": budget.detected_location, "is_active": budget.is_active, "compliance_issue_count": budget.compliance_issue_count, "critical_issue_count": budget.critical_issue_count, "risk_score": budget.risk_score, "departments": list(departments.values()), "created_at": budget.created_at.isoformat()}

@router.post("/budgets/{budget_id}/validate-rates")
def validate_budget_rates(budget_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Run union rate validation on all line items in a budget."""
    from ..union_rate_checker import UnionRateChecker
    db, tenant_id = ctx
    budget = db.execute(select(PCOSBudgetModel).where(PCOSBudgetModel.id == budget_id, PCOSBudgetModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    line_items = db.execute(select(PCOSBudgetLineItemModel).where(PCOSBudgetLineItemModel.budget_id == budget_id)).scalars().all()
    checker = UnionRateChecker()
    results = []; non_compliant_count = 0; total_shortfall = 0
    for item in line_items:
        if not item.rate or item.rate <= 0:
            continue
        check = checker.check_rate(role_category=item.role_category or item.description, actual_rate=float(item.rate), budget_total=float(budget.grand_total))
        rate_check = PCOSUnionRateCheckModel(tenant_id=tenant_id, line_item_id=item.id, union_code=check.union_code, role_category=check.role_category, minimum_rate=check.minimum_rate, actual_rate=check.actual_rate, is_compliant=check.is_compliant, shortfall_amount=check.shortfall_amount, fringe_percent_required=check.fringe_percent_required, fringe_amount_required=check.fringe_amount_required, rate_table_version=check.rate_table_version, rate_table_effective_date=check.rate_table_effective_date, notes=check.notes)
        db.add(rate_check)
        if not check.is_compliant:
            non_compliant_count += 1; total_shortfall += float(check.shortfall_amount)
        results.append({"line_item_id": str(item.id), "description": item.description, **check.to_dict()})
    db.commit()
    logger.info("budget_rates_validated", budget_id=str(budget_id), total_checked=len(results), non_compliant=non_compliant_count, total_shortfall=total_shortfall)
    return {"budget_id": str(budget_id), "rate_table_version": checker.version, "rate_table_effective_date": checker.effective_date.isoformat() if checker.effective_date else None, "total_checked": len(results), "compliant_count": len(results) - non_compliant_count, "non_compliant_count": non_compliant_count, "total_shortfall": total_shortfall, "results": results}

@router.get("/budgets/{budget_id}/rate-checks")
def get_budget_rate_checks(budget_id: uuid_module.UUID, non_compliant_only: bool = Query(False), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get stored rate check results for a budget."""
    db, tenant_id = ctx
    query = select(PCOSUnionRateCheckModel, PCOSBudgetLineItemModel.description).join(PCOSBudgetLineItemModel).where(PCOSBudgetLineItemModel.budget_id == budget_id).where(PCOSUnionRateCheckModel.tenant_id == tenant_id)
    if non_compliant_only:
        query = query.where(PCOSUnionRateCheckModel.is_compliant == False)
    rows = db.execute(query).all()
    return [{"id": str(check.id), "line_item_id": str(check.line_item_id), "description": description, "union_code": check.union_code, "role_category": check.role_category, "minimum_rate": float(check.minimum_rate), "actual_rate": float(check.actual_rate), "is_compliant": check.is_compliant, "shortfall_amount": float(check.shortfall_amount) if check.shortfall_amount else 0, "fringe_percent_required": float(check.fringe_percent_required) if check.fringe_percent_required else None, "rate_table_version": check.rate_table_version, "notes": check.notes} for check, description in rows]

@router.get("/projects/{project_id}/tax-credits")
def get_project_tax_credits(project_id: uuid_module.UUID, budget_id: Optional[uuid_module.UUID] = Query(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Analyze a project's budget for CA Film Tax Credit 4.0 eligibility."""
    from ..tax_credit_engine import analyze_budget_for_tax_credit
    db, tenant_id = ctx
    if budget_id:
        budget = db.execute(select(PCOSBudgetModel).where(PCOSBudgetModel.id == budget_id).where(PCOSBudgetModel.project_id == project_id).where(PCOSBudgetModel.tenant_id == tenant_id)).scalar_one_or_none()
    else:
        budget = db.execute(select(PCOSBudgetModel).where(PCOSBudgetModel.project_id == project_id).where(PCOSBudgetModel.tenant_id == tenant_id).where(PCOSBudgetModel.is_active == True)).scalar_one_or_none()
    if not budget:
        raise HTTPException(404, "No budget found for this project")
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id).where(PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    line_items = db.execute(select(PCOSBudgetLineItemModel).where(PCOSBudgetLineItemModel.budget_id == budget.id).where(PCOSBudgetLineItemModel.tenant_id == tenant_id)).scalars().all()
    project_info = {"is_ca_registered": True, "ca_filming_days_pct": 100, "is_independent": budget.grand_total < 3000000, "is_relocating": False, "ca_jobs_ratio": 0.85}
    if budget.detected_location:
        is_ca = budget.detected_location.upper() in ("CA", "CALIFORNIA")
        project_info["ca_filming_days_pct"] = 100 if is_ca else 0
    items_for_analysis = [{"id": str(item.id), "department": item.department or "99", "description": item.description, "role": item.description, "total_cost": float(item.total_cost) if item.total_cost else 0} for item in line_items]
    analysis_result = analyze_budget_for_tax_credit(float(budget.grand_total), items_for_analysis, project_info)
    existing_app = db.execute(select(PCOSTaxCreditApplicationModel).where(PCOSTaxCreditApplicationModel.project_id == project_id).where(PCOSTaxCreditApplicationModel.budget_id == budget.id).where(PCOSTaxCreditApplicationModel.program_code == "CA_FTC_4.0").where(PCOSTaxCreditApplicationModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not existing_app:
        existing_app = PCOSTaxCreditApplicationModel(tenant_id=tenant_id, project_id=project_id, budget_id=budget.id, program_code=analysis_result["program_code"], program_name=analysis_result["program_name"], program_year=analysis_result["program_year"])
        db.add(existing_app)
    existing_app.eligibility_status = "eligible" if analysis_result["eligibility"]["is_eligible"] else "ineligible"
    existing_app.eligibility_score = analysis_result["eligibility"]["score"]
    existing_app.requirements_met = analysis_result["eligibility"]["requirements_met"]
    existing_app.rule_pack_version = analysis_result["rule_pack_version"]
    existing_app.evaluated_at = datetime.utcnow()
    existing_app.evaluation_details = analysis_result
    if "credit_calculation" in analysis_result:
        calc = analysis_result["credit_calculation"]
        existing_app.base_credit_rate = calc["base_rate"]
        existing_app.uplift_rate = calc["uplift_rate"]
        existing_app.total_credit_rate = calc["total_rate"]
        existing_app.actual_qualified_spend = calc["qualified_spend"]
        existing_app.estimated_credit_amount = calc["estimated_credit"]
        existing_app.qualified_spend_pct = calc["qualified_spend"] / (calc["qualified_spend"] + calc["non_qualified_spend"]) * 100 if (calc["qualified_spend"] + calc["non_qualified_spend"]) > 0 else 0
        db.execute(delete(PCOSQualifiedSpendCategoryModel).where(PCOSQualifiedSpendCategoryModel.application_id == existing_app.id))
        for cat in calc["spend_categories"]:
            spend_cat = PCOSQualifiedSpendCategoryModel(tenant_id=tenant_id, application_id=existing_app.id, category_code=cat["code"], category_name=cat["name"], total_spend=cat["total"], qualified_spend=cat["qualified"], non_qualified_spend=cat["non_qualified"], qualification_status=cat["status"], qualification_reason=cat["reason"], line_item_count=cat["line_item_count"])
            db.add(spend_cat)
    db.commit()
    analysis_result["application_id"] = str(existing_app.id)
    analysis_result["budget_id"] = str(budget.id)
    analysis_result["project_id"] = str(project_id)
    analysis_result["budget_total"] = float(budget.grand_total)
    return analysis_result

@router.get("/budgets/{budget_id}/fringe-analysis")
def analyze_budget_fringes(budget_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Analyze fringe and payroll tax requirements for a budget."""
    from ..fringe_calculator import calculate_budget_fringes
    db, tenant_id = ctx
    budget = db.execute(select(PCOSBudgetModel).where(PCOSBudgetModel.id == budget_id).where(PCOSBudgetModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not budget:
        raise HTTPException(404, "Budget not found")
    line_items = db.execute(select(PCOSBudgetLineItemModel).where(PCOSBudgetLineItemModel.budget_id == budget_id).where(PCOSBudgetLineItemModel.tenant_id == tenant_id)).scalars().all()
    items_for_analysis = [{"id": str(item.id), "department": item.department or "99", "description": item.description, "total_cost": float(item.total_cost) if item.total_cost else 0} for item in line_items]
    budgeted_fringes = sum(float(item.total_cost or 0) for item in line_items if str(item.department or "").startswith("8"))
    result = calculate_budget_fringes(items_for_analysis, budgeted_fringes)
    result["budget_id"] = str(budget_id)
    result["budget_total"] = float(budget.grand_total)
    result["budgeted_fringes_detected"] = budgeted_fringes
    return result
