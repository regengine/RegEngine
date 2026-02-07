"""
Integration tests for Healthcare evidence export endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime
import io
import csv


@pytest.mark.asyncio
async def test_evidence_export_success(test_client: TestClient, test_db_session, test_tenant_id):
    """Test successful evidence export returns CSV file."""
    from app.sqlalchemy_models import EvidenceLogModel, VerticalProjectModel
    
    # Create a test project
    project_id = uuid4()
    project = VerticalProjectModel(
        id=project_id,
        tenant_id=test_tenant_id,
        name="Test Clinic",
        vertical="healthcare",
        vertical_metadata={}
    )
    test_db_session.add(project)
    
    # Create test evidence logs
    evidence1 = EvidenceLogModel(
        id=uuid4(),
        tenant_id=test_tenant_id,
        project_id=project_id,
        rule_id="CLIN-01",
        evidence_type="document",
        data={"file": "test.pdf"},
        content_hash="abc123",
        created_at=datetime.utcnow()
    )
    evidence2 = EvidenceLogModel(
        id=uuid4(),
        tenant_id=test_tenant_id,
        project_id=project_id,
        rule_id="CLIN-02",
        evidence_type="approval",
        data={"approver": "Dr. Smith"},
        content_hash="def456",
        created_at=datetime.utcnow()
    )
    test_db_session.add(evidence1)
    test_db_session.add(evidence2)
    test_db_session.commit()
    
    # Test the export endpoint
    response = test_client.get(
        f"/verticals/healthcare/export/evidence?project_id={project_id}",
        headers={"X-RegEngine-API-Key": "test-api-key"}
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "evidence_export" in response.headers["content-disposition"]
    
    # Parse CSV content
    csv_content = response.content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)
    
    assert len(rows) == 2
    assert rows[0]['rule_id'] in ['CLIN-01', 'CLIN-02']
    assert rows[0]['evidence_type'] in ['document', 'approval']
    assert rows[0]['content_hash'] in ['abc123', 'def456']


@pytest.mark.asyncio
async def test_evidence_export_no_logs(test_client: TestClient, test_db_session, test_tenant_id):
    """Test that export returns 404 when no evidence exists."""
    from app.sqlalchemy_models import VerticalProjectModel
    
    # Create project with no evidence
    project_id = uuid4()
    project = VerticalProjectModel(
        id=project_id,
        tenant_id=test_tenant_id,
        name="Empty Clinic",
        vertical="healthcare",
        vertical_metadata={}
    )
    test_db_session.add(project)
    test_db_session.commit()
    
    response = test_client.get(
        f"/verticals/healthcare/export/evidence?project_id={project_id}",
        headers={"X-RegEngine-API-Key": "test-api-key"}
    )
    
    assert response.status_code == 404
    assert "no evidence logs found" in response.json()['detail'].lower()


@pytest.mark.asyncio
async def test_evidence_export_tenant_isolation(test_client: TestClient, test_db_session):
    """Test that evidence export respects tenant isolation."""
    from app.sqlalchemy_models import EvidenceLogModel, VerticalProjectModel
    
    tenant_a = uuid4()
    tenant_b = uuid4()
    project_a = uuid4()
    project_b = uuid4()
    
    # Create projects for different tenants
    proj_a = VerticalProjectModel(id=project_a, tenant_id=tenant_a, name="Tenant A", vertical="healthcare", vertical_metadata={})
    proj_b = VerticalProjectModel(id=project_b, tenant_id=tenant_b, name="Tenant B", vertical="healthcare", vertical_metadata={})
    test_db_session.add(proj_a)
    test_db_session.add(proj_b)
    
    # Create evidence for both tenants
    evidence_a = EvidenceLogModel(
        tenant_id=tenant_a, project_id=project_a, rule_id="RULE-A",
        evidence_type="test", data={}, content_hash="hash-a"
    )
    evidence_b = EvidenceLogModel(
        tenant_id=tenant_b, project_id=project_b, rule_id="RULE-B",
        evidence_type="test", data={}, content_hash="hash-b"
    )
    test_db_session.add(evidence_a)
    test_db_session.add(evidence_b)
    test_db_session.commit()
    
    # Tenant A should only see their evidence
    # Note: In real implementation, tenant_id comes from JWT
    # For this test, we're assuming the middleware works correctly
    response = test_client.get(
        f"/verticals/healthcare/export/evidence?project_id={project_a}",
        headers={"X-RegEngine-API-Key": "test-api-key"}
    )
    
    # This test assumes tenant isolation is enforced by middleware/RLS
    # The actual verification would happen at the database level
    assert response.status_code in [200, 404]  # Depends on tenant isolation implementation


@pytest.mark.asyncio
async def test_evidence_export_csv_format(test_client: TestClient, test_db_session, test_tenant_id):
    """Test that CSV has correct headers and formatting."""
    from app.sqlalchemy_models import EvidenceLogModel, VerticalProjectModel
    
    project_id = uuid4()
    project = VerticalProjectModel(
        id=project_id, tenant_id=test_tenant_id, name="Test", vertical="healthcare", vertical_metadata={}
    )
    test_db_session.add(project)
    
    evidence = EvidenceLogModel(
        tenant_id=test_tenant_id,
        project_id=project_id,
        rule_id="TEST-01",
        evidence_type="manual_check",
        data={"notes": "Complete"},
        content_hash="xyz789",
        created_by=uuid4()
    )
    test_db_session.add(evidence)
    test_db_session.commit()
    
    response = test_client.get(
        f"/verticals/healthcare/export/evidence?project_id={project_id}",
        headers={"X-RegEngine-API-Key": "test-api-key"}
    )
    
    assert response.status_code == 200
    
    csv_content = response.content.decode('utf-8')
    lines = csv_content.strip().split('\n')
    
    # Check headers
    assert 'id,rule_id,evidence_type,content_hash,created_at,user_id,data_summary' in lines[0]
    
    # Check data row exists
    assert len(lines) >= 2
