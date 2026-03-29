"""
PCOS (Production Compliance OS) Package

Domain models, schemas, and enums for the Production Compliance OS add-on module.
Designed for small film/TV production companies in California/LA.

This package re-exports everything from submodules for backward compatibility.
"""

# Re-export enums
from .enums import (
    LocationType,
    ClassificationType,
    TaskStatus,
    GateState,
    EntityType,
    OwnerPayMode,
    RegistrationType,
    InsuranceType,
    EvidenceType,
    ProjectType,
    Jurisdiction,
)

# Re-export ORM models
from .orm import (
    PCOSCompanyModel,
    PCOSCompanyRegistrationModel,
    PCOSInsurancePolicyModel,
    PCOSSafetyPolicyModel,
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSPermitPacketModel,
    PCOSPersonModel,
    PCOSEngagementModel,
    PCOSTimecardModel,
    PCOSTaskModel,
    PCOSTaskEventModel,
    PCOSEvidenceModel,
    PCOSGateEvaluationModel,
    PCOSBudgetModel,
    PCOSBudgetLineItemModel,
    PCOSUnionRateCheckModel,
    PCOSTaxCreditApplicationModel,
    PCOSQualifiedSpendCategoryModel,
    PCOSTaxCreditRuleModel,
    PCOSFormTemplateModel,
    PCOSGeneratedFormModel,
    PCOSClassificationAnalysisModel,
    PCOSQuestionnaireResponseModel,
    PCOSClassificationExemptionModel,
    PCOSDocumentRequirementModel,
    PCOSEngagementDocumentModel,
    PCOSVisaCategoryModel,
    PCOSPersonVisaStatusModel,
    PCOSRuleEvaluationModel,
    PCOSComplianceSnapshotModel,
    PCOSAuditEventModel,
)

# Re-export Pydantic schemas
from .schemas import (
    AddressSchema,
    CompanyCreateSchema,
    CompanyUpdateSchema,
    CompanyResponseSchema,
    ProjectCreateSchema,
    ProjectUpdateSchema,
    ProjectResponseSchema,
    LocationCreateSchema,
    LocationResponseSchema,
    EngagementCreateSchema,
    EngagementResponseSchema,
    TimecardCreateSchema,
    TimecardResponseSchema,
    TaskResponseSchema,
    TaskUpdateSchema,
    GateEvaluationResponseSchema,
    EvidenceCreateSchema,
    EvidenceResponseSchema,
    PersonCreateSchema,
    PersonResponseSchema,
)

# Re-export authority & fact lineage models
from .authority import (
    PCOSAuthorityDocumentModel,
    PCOSExtractedFactModel,
    PCOSFactCitationModel,
)

# Re-export schema governance models
from .schema_governance import (
    SchemaVersionModel,
    PCOSAnalysisRunModel,
)

# Unified router — includes all PCOS sub-routers
from fastapi import APIRouter

router = APIRouter(prefix="/v1/pcos")

from .dashboard import router as _dashboard
from .entities import router as _entities
from .gate import router as _gate
from .evidence import router as _evidence
from .budget import router as _budget
from .compliance import router as _compliance
from .governance import router as _governance

router.include_router(_dashboard)
router.include_router(_entities)
router.include_router(_gate)
router.include_router(_evidence)
router.include_router(_budget)
router.include_router(_compliance)
router.include_router(_governance)

__all__ = [
    "router",
    # Enums
    "LocationType",
    "ClassificationType",
    "TaskStatus",
    "GateState",
    "EntityType",
    "OwnerPayMode",
    "RegistrationType",
    "InsuranceType",
    "EvidenceType",
    "ProjectType",
    "Jurisdiction",
    # ORM Models
    "PCOSCompanyModel",
    "PCOSCompanyRegistrationModel",
    "PCOSInsurancePolicyModel",
    "PCOSSafetyPolicyModel",
    "PCOSProjectModel",
    "PCOSLocationModel",
    "PCOSPermitPacketModel",
    "PCOSPersonModel",
    "PCOSEngagementModel",
    "PCOSTimecardModel",
    "PCOSTaskModel",
    "PCOSTaskEventModel",
    "PCOSEvidenceModel",
    "PCOSGateEvaluationModel",
    "PCOSBudgetModel",
    "PCOSBudgetLineItemModel",
    "PCOSUnionRateCheckModel",
    "PCOSTaxCreditApplicationModel",
    "PCOSQualifiedSpendCategoryModel",
    "PCOSTaxCreditRuleModel",
    "PCOSFormTemplateModel",
    "PCOSGeneratedFormModel",
    "PCOSClassificationAnalysisModel",
    "PCOSQuestionnaireResponseModel",
    "PCOSClassificationExemptionModel",
    "PCOSDocumentRequirementModel",
    "PCOSEngagementDocumentModel",
    "PCOSVisaCategoryModel",
    "PCOSPersonVisaStatusModel",
    "PCOSRuleEvaluationModel",
    "PCOSComplianceSnapshotModel",
    "PCOSAuditEventModel",
    # Pydantic Schemas
    "AddressSchema",
    "CompanyCreateSchema",
    "CompanyUpdateSchema",
    "CompanyResponseSchema",
    "ProjectCreateSchema",
    "ProjectUpdateSchema",
    "ProjectResponseSchema",
    "LocationCreateSchema",
    "LocationResponseSchema",
    "EngagementCreateSchema",
    "EngagementResponseSchema",
    "TimecardCreateSchema",
    "TimecardResponseSchema",
    "TaskResponseSchema",
    "TaskUpdateSchema",
    "GateEvaluationResponseSchema",
    "EvidenceCreateSchema",
    "EvidenceResponseSchema",
    "PersonCreateSchema",
    "PersonResponseSchema",
    # Authority & Fact Lineage
    "PCOSAuthorityDocumentModel",
    "PCOSExtractedFactModel",
    "PCOSFactCitationModel",
    # Schema Governance
    "SchemaVersionModel",
    "PCOSAnalysisRunModel",
]
