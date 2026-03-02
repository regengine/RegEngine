from __future__ import annotations

from datetime import date
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.analysis import (
    calculate_dir,
    classify_risk,
    drift_detection,
    exposure_score,
    regression_proxy,
    threshold_sensitivity,
)
from app.models import (
    AuditExportRequest,
    AuditExportResponse,
    CKGSummaryResponse,
    FairLendingAnalyzeRequest,
    FairLendingAnalyzeResponse,
    ModelChangeRequest,
    ModelRecordResponse,
    ModelRegistrationRequest,
    RegulationMapRequest,
    RegulationMapResponse,
    RiskSummaryResponse,
    ValidationRequest,
)
from app.regulatory_intelligence import generate_obligations
from app.security import stable_hash, tokenize_pii, utc_now
from app.store import DEFAULT_TENANT_ID, STORE


logger = logging.getLogger("compliance-api")

router = APIRouter(prefix="/v1", tags=["fair-lending-compliance-os"])


def tenant_id_dependency(
    x_tenant_id: str = Header(default=DEFAULT_TENANT_ID, alias="X-Tenant-Id"),
) -> str:
    try:
        return str(UUID(x_tenant_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="X-Tenant-Id must be a valid UUID") from error


@router.post("/regulatory/map", response_model=RegulationMapResponse)
async def map_regulation(
    request: RegulationMapRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> RegulationMapResponse:
    obligations = generate_obligations(request)
    regulation_id = STORE.save_regulatory_map(tenant_id=tenant_id, request=request.model_dump(), generated_obligations=obligations)
    logger.info(
        "regulation_mapped",
        extra={
            "tenant": tenant_id,
            "regulation_id": regulation_id,
            "citation": request.citation,
        },
    )
    return RegulationMapResponse(regulation_id=regulation_id, obligations=obligations)


@router.post("/models", response_model=ModelRecordResponse)
async def register_model(
    request: ModelRegistrationRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> ModelRecordResponse:
    model = STORE.register_model(tenant_id, request)
    logger.info(
        "model_registered",
        extra={
            "tenant": tenant_id,
            "model": tokenize_pii(request.id),
            "owner": tokenize_pii(request.owner),
        },
    )
    return model


@router.get("/models/{model_id}", response_model=ModelRecordResponse)
async def get_model(
    model_id: str,
    tenant_id: str = Depends(tenant_id_dependency),
) -> ModelRecordResponse:
    model = STORE.get_model(tenant_id, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.post("/models/{model_id}/validations")
async def add_validation(
    model_id: str,
    request: ValidationRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> dict:
    if not STORE.get_model(tenant_id, model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    row = STORE.add_validation(tenant_id, model_id, request)
    return {"validation_id": row["id"], "status": row["status"]}


@router.post("/models/{model_id}/changes")
async def add_model_change(
    model_id: str,
    request: ModelChangeRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> dict:
    if not STORE.get_model(tenant_id, model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    row = STORE.add_model_change(tenant_id, model_id, request)
    return {
        "change_id": row["id"],
        "requires_revalidation": row["requires_revalidation"],
    }


@router.post("/fair-lending/analyze", response_model=FairLendingAnalyzeResponse)
async def analyze_fair_lending(
    request: FairLendingAnalyzeRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> FairLendingAnalyzeResponse:
    dir_results, min_dir = calculate_dir(request.groups)

    regression_result = None
    if "regression" in request.analysis_type:
        regression_result = regression_proxy(request.groups)

    drift_results = []
    if "drift" in request.analysis_type:
        drift_results = drift_detection(request.historical_approval_rates)

    flags = classify_risk(min_dir=min_dir, regression=regression_result, drift_results=drift_results)
    sensitivity = threshold_sensitivity(min_dir)
    analyzed_at = utc_now()

    saved = STORE.save_compliance_result(
        tenant_id=tenant_id,
        request=request,
        analyzed_at=analyzed_at,
        min_dir=min_dir,
        dir_results=[result.model_dump() for result in dir_results],
        regression_result=regression_result,
        drift_results=drift_results,
        risk_level=flags.risk_level,
        recommended_action=flags.recommended_action,
        regression_bias_flag=flags.regression_bias_flag,
        drift_flag=flags.drift_flag,
    )

    logger.info(
        "fair_lending_analysis_completed",
        extra={
            "tenant": tenant_id,
            "model": tokenize_pii(request.model_id),
            "analysis_id": saved.id,
            "risk_level": flags.risk_level,
        },
    )

    return FairLendingAnalyzeResponse(
        model_id=request.model_id,
        analysis_id=saved.id,
        dir_results=dir_results,
        regression_bias_flag=flags.regression_bias_flag,
        drift_flag=flags.drift_flag,
        risk_level=flags.risk_level,
        recommended_action=flags.recommended_action,
        threshold_sensitivity=sensitivity,
        regression_result=regression_result,
        drift_results=drift_results,
        analyzed_at=analyzed_at,
    )


@router.post("/audit/export", response_model=AuditExportResponse)
async def export_audit_artifact(
    request: AuditExportRequest,
    tenant_id: str = Depends(tenant_id_dependency),
) -> AuditExportResponse:
    latest = STORE.latest_compliance_result(tenant_id=tenant_id, model_id=request.model_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No compliance result found for model")

    model = STORE.get_model(tenant_id, request.model_id)
    model_version = model.version if model else "unknown"

    package_payload = {
        "regulation_citation": "Fair Lending corpus (ECOA/FHA/CFPB/Interagency)",
        "control_description": "DIR, regression proxy, drift monitoring",
        "test_methodology": {
            "dir": "Disparate Impact Ratio",
            "regression": latest.regression_result.model_dump() if latest.regression_result else None,
            "drift": [entry.model_dump() for entry in latest.drift_results],
        },
        "statistical_output": {
            "dir_results": latest.dir_results,
            "risk_level": latest.risk_level,
            "recommended_action": latest.recommended_action,
        },
        "model_version": model_version,
        "timestamp": latest.analyzed_at.isoformat(),
        "reviewer_sign_off": request.reviewer,
    }
    hash_sha256 = stable_hash(package_payload)

    artifact = STORE.save_audit_artifact(
        tenant_id=tenant_id,
        request=request,
        reviewer_token=tokenize_pii(request.reviewer),
        hash_sha256=hash_sha256,
        metadata={
            "immutable": "true",
            "versioned": "true",
            "audit_trail": "enabled",
        },
    )

    return AuditExportResponse(
        artifact_id=artifact.id,
        model_id=artifact.model_id,
        output_type=artifact.output_type,
        version=artifact.version,
        immutable=True,
        hash_sha256=artifact.hash_sha256,
        generated_at=artifact.generated_at,
        metadata=artifact.metadata,
    )


@router.get("/risk/summary", response_model=RiskSummaryResponse)
async def risk_summary(
    model_id: str,
    tenant_id: str = Depends(tenant_id_dependency),
) -> RiskSummaryResponse:
    latest = STORE.latest_compliance_result(tenant_id, model_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No compliance result found for model")

    recency_days = max(0, (utc_now().date() - latest.analyzed_at.date()).days)
    score = exposure_score(
        min_dir=latest.min_dir,
        regression_result=latest.regression_result,
        drift_results=latest.drift_results,
        recency_days=recency_days,
    )

    if latest.min_dir < 0.75:
        dir_status = "Red"
    elif latest.min_dir < 0.80:
        dir_status = "Yellow"
    else:
        dir_status = "Green"

    if latest.drift_flag:
        drift_status = "Yellow"
    else:
        drift_status = "Green"

    if score >= 70:
        overall = "High"
    elif score >= 40:
        overall = "Medium"
    else:
        overall = "Low"

    return RiskSummaryResponse(
        overall_fair_lending_risk=overall,
        dir_status=dir_status,
        regression_bias_flag=latest.regression_bias_flag,
        drift_status=drift_status,
        last_tested=latest.analyzed_at.date(),
        exposure_score=score,
    )


@router.get("/ckg/summary", response_model=CKGSummaryResponse)
async def ckg_summary(
    tenant_id: str = Depends(tenant_id_dependency),
) -> CKGSummaryResponse:
    return CKGSummaryResponse(**STORE.ckg_summary(tenant_id))


@router.get("/scope-wall")
async def scope_wall() -> dict:
    return {
        "in_scope": [
            "Fair lending regulatory intelligence",
            "Bias and disparate impact testing",
            "Model governance for underwriting models",
            "Audit artifact generation",
            "Executive fair lending risk scoring",
        ],
        "out_of_scope": [
            "AML rules engine",
            "KYC onboarding",
            "Complaint systems",
            "Vendor risk tracking",
            "Multi-industry modules",
        ],
        "timestamp": date.today().isoformat(),
    }
