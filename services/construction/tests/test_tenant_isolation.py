"""
Tenant Isolation Tests for Construction Service

Verifies that:
1. tenant_id columns exist in all tables
2. BIM, OSHA, and Subcontractor records are properly isolated by tenant
3. Cross-tenant data leakage is prevented
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy import select

# Import models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (
    BIMChangeRecord,
    OSHASafetyInspection,
    SubcontractorCertification
)


class TestTenantIsolation:
    """Test tenant isolation in Construction service"""

    @pytest.mark.asyncio
    async def test_bim_model_has_tenant_id(self):
        """Verify BIMChangeRecord has tenant_id column"""
        assert hasattr(BIMChangeRecord, 'tenant_id')
        
        # Verify it's indexed
        table = BIMChangeRecord.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ BIMChangeRecord has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_osha_model_has_tenant_id(self):
        """Verify OSHASafetyInspection has tenant_id column"""
        assert hasattr(OSHASafetyInspection, 'tenant_id')
        
        table = OSHASafetyInspection.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ OSHASafetyInspection has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_subcontractor_model_has_tenant_id(self):
        """Verify SubcontractorCertification has tenant_id column"""
        assert hasattr(SubcontractorCertification, 'tenant_id')
        
        table = SubcontractorCertification.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ SubcontractorCertification has indexed tenant_id")

    def test_tenant_bim_isolation(self, db_session):
        """Test BIM change records are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create BIM record for tenant A
        bim_a = BIMChangeRecord(
            tenant_id=tenant_a,
            project_id="PROJ-A-001",
            project_name="Project Alpha",
            change_number="CHG-A-001",
            change_type="DESIGN_REVISION",
            description="Design revision for tenant A",
            file_name="design_v1.rvt",
            file_version="1.0",
            file_hash="a" * 64,
            submitted_by="user_a@example.com",
            submission_date=datetime.utcnow(),
            status="PENDING"
        )
        
        # Create BIM record for tenant B
        bim_b = BIMChangeRecord(
            tenant_id=tenant_b,
            project_id="PROJ-B-001",
            project_name="Project Beta",
            change_number="CHG-B-001",
            change_type="CHANGE_ORDER",
            description="Change order for tenant B",
            file_name="design_v2.rvt",
            file_version="2.0",
            file_hash="b" * 64,
            submitted_by="user_b@example.com",
            submission_date=datetime.utcnow(),
            status="APPROVED"
        )
        
        db_session.add_all([bim_a, bim_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(BIMChangeRecord).where(
            BIMChangeRecord.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        bim_records_a = results.scalars().all()
        
        assert len(bim_records_a) == 1
        assert bim_records_a[0].project_id == "PROJ-A-001"
        assert bim_records_a[0].change_number == "CHG-A-001"
        print("✅ Tenant A sees only their BIM records")
        
        # Query for tenant B only
        stmt = select(BIMChangeRecord).where(
            BIMChangeRecord.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        bim_records_b = results.scalars().all()
        
        assert len(bim_records_b) == 1
        assert bim_records_b[0].project_id == "PROJ-B-001"
        assert bim_records_b[0].change_number == "CHG-B-001"
        print("✅ Tenant B sees only their BIM records")

    def test_tenant_osha_isolation(self, db_session):
        """Test OSHA inspection records are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create OSHA inspection for tenant A
        osha_a = OSHASafetyInspection(
            tenant_id=tenant_a,
            project_id="PROJ-A-001",
            inspection_date=datetime.utcnow(),
            inspector_name="Inspector A",
            inspection_type="WEEKLY",
            osha_subpart="Subpart M",
            violations_found=2,
            violation_severity="SERIOUS",
            violation_description="Fall protection violations",
            corrective_action_required=True,
            corrective_action_description="Install additional guardrails",
            corrective_action_due_date=datetime.utcnow() + timedelta(days=7),
            status="OPEN"
        )
        
        # Create OSHA inspection for tenant B
        osha_b = OSHASafetyInspection(
            tenant_id=tenant_b,
            project_id="PROJ-B-001",
            inspection_date=datetime.utcnow(),
            inspector_name="Inspector B",
            inspection_type="MONTHLY",
            osha_subpart="Subpart L",
            violations_found=0,
            status="CLOSED"
        )
        
        db_session.add_all([osha_a, osha_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(OSHASafetyInspection).where(
            OSHASafetyInspection.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        osha_records_a = results.scalars().all()
        
        assert len(osha_records_a) == 1
        assert osha_records_a[0].project_id == "PROJ-A-001"
        assert osha_records_a[0].violations_found == 2
        print("✅ Tenant A sees only their OSHA inspections")
        
        # Query for tenant B only
        stmt = select(OSHASafetyInspection).where(
            OSHASafetyInspection.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        osha_records_b = results.scalars().all()
        
        assert len(osha_records_b) == 1
        assert osha_records_b[0].project_id == "PROJ-B-001"
        assert osha_records_b[0].violations_found == 0
        print("✅ Tenant B sees only their OSHA inspections")

    def test_tenant_subcontractor_isolation(self, db_session):
        """Test subcontractor certifications are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create subcontractor cert for tenant A
        cert_a = SubcontractorCertification(
            tenant_id=tenant_a,
            subcontractor_name="Contractor A LLC",
            subcontractor_code="CA-001",
            certification_type="OSHA_30",
            certification_number="OSHA-A-123456",
            issue_date=datetime.utcnow() - timedelta(days=365),
            expiration_date=datetime.utcnow() + timedelta(days=365),
            document_hash="c" * 64,
            is_active=True,
            verification_status="VERIFIED"
        )
        
        # Create subcontractor cert for tenant B
        cert_b = SubcontractorCertification(
            tenant_id=tenant_b,
            subcontractor_name="Contractor B Corp",
            subcontractor_code="CB-001",
            certification_type="LICENSE",
            certification_number="LIC-B-789012",
            issue_date=datetime.utcnow() - timedelta(days=730),
            expiration_date=datetime.utcnow() + timedelta(days=30),
            document_hash="d" * 64,
            is_active=True,
            verification_status="PENDING"
        )
        
        db_session.add_all([cert_a, cert_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(SubcontractorCertification).where(
            SubcontractorCertification.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        certs_a = results.scalars().all()
        
        assert len(certs_a) == 1
        assert certs_a[0].subcontractor_name == "Contractor A LLC"
        assert certs_a[0].certification_type == "OSHA_30"
        print("✅ Tenant A sees only their subcontractor certifications")
        
        # Query for tenant B only
        stmt = select(SubcontractorCertification).where(
            SubcontractorCertification.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        certs_b = results.scalars().all()
        
        assert len(certs_b) == 1
        assert certs_b[0].subcontractor_name == "Contractor B Corp"
        assert certs_b[0].certification_type == "LICENSE"
        print("✅ Tenant B sees only their subcontractor certifications")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Construction Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_bim_model_has_tenant_id())
    asyncio.run(test_suite.test_osha_model_has_tenant_id())
    asyncio.run(test_suite.test_subcontractor_model_has_tenant_id())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
