import pytest
import pytest_asyncio
from uuid import uuid4
import json
import zipfile
import io
from app.verticals.healthcare.service import HealthcareVerticalService, HealthcareRuleStatus
from app.verticals.healthcare.schemas import HealthcareProjectMetadata, FacilityType

@pytest.mark.asyncio
async def test_evaluate_safety_status(mock_db_session):
    service = HealthcareVerticalService(mock_db_session)
    project_id = uuid4()
    
    # helper to create rule dict
    def make_rules(statuses):
        return [
            {"id": "CLIN-01", "name": "License Verification", "status": statuses.get("CLIN-01", HealthcareRuleStatus.GREEN)},
            {"id": "DATA-01", "name": "Access Controls", "status": statuses.get("DATA-01", HealthcareRuleStatus.GREEN)},
            {"id": "GOV-01", "name": "Nonprofit Status", "status": statuses.get("GOV-01", HealthcareRuleStatus.GREEN)},
            {"id": "GOV-03", "name": "FTCA Readiness", "status": statuses.get("GOV-03", HealthcareRuleStatus.GREEN)},
            {"id": "OPS-01", "name": "Incident Log", "status": statuses.get("OPS-01", HealthcareRuleStatus.GREEN)},
        ]

    # Scenario 1: All Green -> Green
    rules = make_rules({})
    status = await service.evaluate_safety_status(project_id, rules)
    assert status == HealthcareRuleStatus.GREEN

    # Scenario 2: One Critical Red -> Red
    rules = make_rules({"CLIN-01": HealthcareRuleStatus.RED}) # License Verification is Critical
    status = await service.evaluate_safety_status(project_id, rules)
    assert status == HealthcareRuleStatus.RED

    # Scenario 3: One High Red -> Red
    rules = make_rules({"GOV-01": HealthcareRuleStatus.RED}) # Nonprofit Status is High
    status = await service.evaluate_safety_status(project_id, rules)
    assert status == HealthcareRuleStatus.RED

    # Scenario 4: One Medium Red -> Green (since tolerance is > 3)
    rules = make_rules({"GOV-03": HealthcareRuleStatus.RED}) # FTCA is Medium
    status = await service.evaluate_safety_status(project_id, rules)
    assert status == HealthcareRuleStatus.GREEN

    # Scenario 5: Multiple Medium Reds logic check
    rules_3_mediums = [
        {"id": "GOV-03", "status": HealthcareRuleStatus.RED},
        {"id": "OPS-01", "status": HealthcareRuleStatus.RED},
        {"id": "OPS-02", "status": HealthcareRuleStatus.RED},
        {"id": "CLIN-01", "status": HealthcareRuleStatus.GREEN},
        {"id": "DATA-01", "status": HealthcareRuleStatus.GREEN},
    ]
    status = await service.evaluate_safety_status(project_id, rules_3_mediums)
    assert status == HealthcareRuleStatus.GREEN # 3 is not > 3

@pytest.mark.asyncio
async def test_create_clinic_project(mock_db_session):
    service = HealthcareVerticalService(mock_db_session)
    metadata = HealthcareProjectMetadata(
        facility_type=FacilityType.FREE_CLINIC,
        state="CA",
        dispenses_medication=True,
        operating_state="active",
        annual_patient_volume=500
    )
    
    result = await service.create_clinic_project(uuid4(), "Test Clinic", metadata)
    
    assert result["vertical"] == "healthcare"
    assert result["metadata"]["dispenses_medication"] is True
    # Base rules (9) + Med rules (2) = 11
    assert result["rule_count"] == 11 

@pytest.mark.asyncio
async def test_create_clinic_project_no_meds(mock_db_session):
    service = HealthcareVerticalService(mock_db_session)
    metadata = HealthcareProjectMetadata(
        facility_type=FacilityType.FREE_CLINIC,
        state="CA",
        dispenses_medication=False,
        operating_state="active",
        annual_patient_volume=500
    )
    
    result = await service.create_clinic_project(uuid4(), "Test Clinic", metadata)
    # Base rules only (9)
    assert result["rule_count"] == 9

@pytest.mark.asyncio
async def test_log_evidence_integrity(mock_db_session):
    service = HealthcareVerticalService(mock_db_session)
    tenant_id = uuid4()
    project_id = uuid4()
    
    # Test Data
    evidence_data = {"filename": "license.pdf", "uploaded_by": "user_123"}
    
    # 1. Log Evidence
    content_hash = await service.log_evidence(
        tenant_id, project_id, "CLIN-01", "document", evidence_data
    )
    
    # 2. Verify Hash (SHA-256 of sorted JSON)
    import hashlib
    expected_payload = json.dumps(evidence_data, sort_keys=True)
    expected_hash = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    
    assert content_hash == expected_hash
    assert len(content_hash) == 64 # SHA-256 length

@pytest.mark.asyncio
async def test_generate_lifeboat_archive(mock_db_session):
    service = HealthcareVerticalService(mock_db_session)
    tenant_id = uuid4()
    project_id = uuid4()
    
    # Generate Zip Bytes
    zip_bytes = await service.generate_lifeboat_archive(tenant_id, project_id)
    assert zip_bytes is not None
    assert len(zip_bytes) > 0
    
    # Verify Zip Structure
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Check required files exist
        files = z.namelist()
        assert "clinic_metadata.json" in files
        assert "compliance_status.json" in files
        assert "README.txt" in files
        assert any(f.startswith("evidence/") for f in files)
        
        # Verify Metadata Content
        with z.open("clinic_metadata.json") as f:
            meta = json.load(f)
            assert meta["tenant_id"] == str(tenant_id)
            assert meta["project_id"] == str(project_id)
            assert "software_version" in meta
            
        # Verify Status Content
        with z.open("compliance_status.json") as f:
            status_list = json.load(f)
            assert isinstance(status_list, list)
            assert len(status_list) > 0
            assert "id" in status_list[0]
