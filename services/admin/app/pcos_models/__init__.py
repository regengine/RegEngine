"""
Production Compliance OS (PCOS) Domain Models

Re-exports all models and schemas for backward compatibility.
``from app.pcos_models import PCOSProjectModel`` continues to work.
"""

# ORM Models — Company
from .company import (
    PCOSCompanyModel,
    PCOSCompanyRegistrationModel,
    PCOSInsurancePolicyModel,
    PCOSSafetyPolicyModel,
)

# ORM Models — Production
from .production import (
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSPermitPacketModel,
    PCOSPersonModel,
    PCOSEngagementModel,
    PCOSTimecardModel,
)

# ORM Models — Tasks & Evidence
from .tasks import (
    PCOSTaskModel,
    PCOSTaskEventModel,
    PCOSEvidenceModel,
    PCOSGateEvaluationModel,
)

# ORM Models — Financial
from .financial import (
    PCOSBudgetModel,
    PCOSBudgetLineItemModel,
    PCOSUnionRateCheckModel,
    PCOSTaxCreditApplicationModel,
    PCOSQualifiedSpendCategoryModel,
    PCOSTaxCreditRuleModel,
    PCOSFormTemplateModel,
    PCOSGeneratedFormModel,
)

# ORM Models — Compliance & Classification
from .compliance import (
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

# ORM Models — Authority & Analysis
from .authority import (
    PCOSAuthorityDocumentModel,
    PCOSExtractedFactModel,
    PCOSFactCitationModel,
    SchemaVersionModel,
    PCOSAnalysisRunModel,
)

# Pydantic Schemas
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

# Re-export enums for backward compatibility
from ..pcos_enums import (  # noqa: F401
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

__all__ = [
    # Company
    "PCOSCompanyModel", "PCOSCompanyRegistrationModel",
    "PCOSInsurancePolicyModel", "PCOSSafetyPolicyModel",
    # Production
    "PCOSProjectModel", "PCOSLocationModel", "PCOSPermitPacketModel",
    "PCOSPersonModel", "PCOSEngagementModel", "PCOSTimecardModel",
    # Tasks
    "PCOSTaskModel", "PCOSTaskEventModel", "PCOSEvidenceModel", "PCOSGateEvaluationModel",
    # Financial
    "PCOSBudgetModel", "PCOSBudgetLineItemModel", "PCOSUnionRateCheckModel",
    "PCOSTaxCreditApplicationModel", "PCOSQualifiedSpendCategoryModel",
    "PCOSTaxCreditRuleModel", "PCOSFormTemplateModel", "PCOSGeneratedFormModel",
    # Compliance
    "PCOSClassificationAnalysisModel", "PCOSQuestionnaireResponseModel",
    "PCOSClassificationExemptionModel", "PCOSDocumentRequirementModel",
    "PCOSEngagementDocumentModel", "PCOSVisaCategoryModel", "PCOSPersonVisaStatusModel",
    "PCOSRuleEvaluationModel", "PCOSComplianceSnapshotModel", "PCOSAuditEventModel",
    # Authority
    "PCOSAuthorityDocumentModel", "PCOSExtractedFactModel", "PCOSFactCitationModel",
    "SchemaVersionModel", "PCOSAnalysisRunModel",
    # Schemas
    "AddressSchema", "CompanyCreateSchema", "CompanyUpdateSchema", "CompanyResponseSchema",
    "ProjectCreateSchema", "ProjectUpdateSchema", "ProjectResponseSchema",
    "LocationCreateSchema", "LocationResponseSchema",
    "EngagementCreateSchema", "EngagementResponseSchema",
    "TimecardCreateSchema", "TimecardResponseSchema",
    "TaskResponseSchema", "TaskUpdateSchema", "GateEvaluationResponseSchema",
    "EvidenceCreateSchema", "EvidenceResponseSchema",
    "PersonCreateSchema", "PersonResponseSchema",
    # Enums
    "LocationType", "ClassificationType", "TaskStatus", "GateState",
    "EntityType", "OwnerPayMode", "RegistrationType", "InsuranceType",
    "EvidenceType", "ProjectType", "Jurisdiction",
]
