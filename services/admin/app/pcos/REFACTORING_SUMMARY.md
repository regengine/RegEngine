# PCOS Models Refactoring Summary

## What Was Done

The monolithic `pcos_models.py` (2,231 lines) has been split into logical modules within the `pcos/` package for better organization and maintainability.

## New Structure

```
app/
├── pcos_models.py (backward compatibility shim, 15 lines)
└── pcos/
    ├── __init__.py (172 lines) - re-exports all models
    ├── enums.py (117 lines) - 11 enum types
    ├── orm.py (1,516 lines) - 31 SQLAlchemy ORM models
    ├── schemas.py (337 lines) - 20 Pydantic request/response schemas
    ├── authority.py (189 lines) - 3 fact lineage models
    ├── schema_governance.py (116 lines) - 2 schema governance models
    ├── entities.py (596 lines) - entity models
    ├── compliance.py (262 lines) - compliance/rule models
    ├── budget.py (176 lines) - budget analysis models
    ├── evidence.py (131 lines) - evidence locker models
    ├── gate.py (142 lines) - gate evaluation models
    ├── governance.py (170 lines) - governance models
    ├── dashboard.py (102 lines) - dashboard models
    └── _shared.py (39 lines) - shared utilities
```

## Module Breakdown

### enums.py
11 enum types for domain constants:
- LocationType, ClassificationType, TaskStatus
- GateState, EntityType, OwnerPayMode
- RegistrationType, InsuranceType
- EvidenceType, ProjectType, Jurisdiction

### orm.py
31 SQLAlchemy ORM models covering:
- Company & legal structure (PCOSCompanyModel, PCOSCompanyRegistrationModel)
- Insurance (PCOSInsurancePolicyModel, PCOSSafetyPolicyModel)
- Projects & locations (PCOSProjectModel, PCOSLocationModel)
- Permits (PCOSPermitPacketModel)
- People & engagements (PCOSPersonModel, PCOSEngagementModel, PCOSTimecardModel)
- Compliance tasks (PCOSTaskModel, PCOSTaskEventModel)
- Evidence (PCOSEvidenceModel)
- Gates (PCOSGateEvaluationModel)
- Budget & tax credits (PCOSBudgetModel, PCOSBudgetLineItemModel, PCOSUnionRateCheckModel, PCOSTaxCreditApplicationModel)
- Forms & analysis (PCOSFormTemplateModel, PCOSGeneratedFormModel, PCOSClassificationAnalysisModel, etc.)
- Visa & compliance snapshots (PCOSVisaCategoryModel, PCOSRuleEvaluationModel, PCOSComplianceSnapshotModel, PCOSAuditEventModel)

### schemas.py
20 Pydantic request/response models for API endpoints:
- AddressSchema
- Company schemas (Create, Update, Response)
- Project schemas (Create, Update, Response)
- Location schemas (Create, Response)
- Engagement schemas (Create, Response)
- Timecard schemas (Create, Response)
- Task schemas (Response, Update)
- GateEvaluation, Evidence, Person schemas

### authority.py
Fact lineage and citation tracking:
- PCOSAuthorityDocumentModel
- PCOSExtractedFactModel
- PCOSFactCitationModel

### schema_governance.py
Schema versioning and analysis run tracking:
- SchemaVersionModel
- PCOSAnalysisRunModel

### Other modules
Existing modules for specific domains:
- entities.py, compliance.py, budget.py, evidence.py
- gate.py, governance.py, dashboard.py, _shared.py

## Backward Compatibility

The original `pcos_models.py` now acts as a backward compatibility shim:

```python
"""Backward compatibility shim for PCOS models."""
from app.pcos import *  # noqa: F401,F403
```

This means:
- Old imports still work: `from app.pcos_models import PCOSProjectModel`
- New imports are preferred: `from app.pcos import PCOSProjectModel`
- The package's `__init__.py` re-exports everything, so both work seamlessly

## Migration Path

No migration needed immediately. However, codebases should gradually update imports to:
```python
# Prefer this
from app.pcos import PCOSProjectModel, ProjectCreateSchema
from app.pcos import LocationType, GateState
```

Instead of:
```python
# This still works but is deprecated
from app.pcos_models import PCOSProjectModel, ProjectCreateSchema
```

## Benefits

1. **Logical Organization**: Related models are grouped by domain (enums, orm, schemas, authority, governance)
2. **Maintainability**: Smaller, focused files are easier to navigate and modify
3. **Discoverability**: Clear module names indicate what each contains
4. **Backward Compatible**: No breaking changes to existing code
5. **Scalability**: Easier to add new models without inflating a single file

## Notes

- All imports use relative paths within the pcos package
- The orm.py module imports enums for type hints
- The __init__.py centralizes all exports for easy discovery
- The original 2,231-line file is now split across ~4,000 lines but organized into logical modules
