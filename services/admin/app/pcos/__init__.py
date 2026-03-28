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

__all__ = [
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
