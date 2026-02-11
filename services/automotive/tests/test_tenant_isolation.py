"""
Tenant Isolation Tests for Automotive Service

Verifies that:
1. tenant_id columns exist in all tables
2. PPAP submissions, elements, and audits are properly isolated by tenant
3. Cross-tenant data leakage is prevented
"""

import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy import select

# Import models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (
    PPAPSubmission,
    PPAPElement,
    LPAAudit
)


@pytest.mark.security
class TestTenantIsolation:
    """Test tenant isolation in Automotive service"""

    @pytest.mark.asyncio
    async def test_ppap_submission_model_has_tenant_id(self):
        """Verify PPAPSubmission has tenant_id column"""
        assert hasattr(PPAPSubmission, 'tenant_id')
        
        # Verify it's indexed
        table = PPAPSubmission.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ PPAPSubmission has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_ppap_element_model_has_tenant_id(self):
        """Verify PPAPElement has tenant_id column"""
        assert hasattr(PPAPElement, 'tenant_id')
        
        table = PPAPElement.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ PPAPElement has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_lpa_audit_model_has_tenant_id(self):
        """Verify LPAAudit has tenant_id column"""
        assert hasattr(LPAAudit, 'tenant_id')
        
        table = LPAAudit.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ LPAAudit has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_ppap_submission_tenant_isolation(self, db_session):
        """Test PPAP submissions are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create submission for tenant A
        submission_a = PPAPSubmission(
            tenant_id=tenant_a,
            part_number="PART-A-001",
            part_name="Automotive Part A",
            submission_level=3,
            oem_customer="OEM Customer A",
            submission_date=datetime.utcnow(),
            approval_status="PENDING"
        )
        
        # Create submission for tenant B
        submission_b = PPAPSubmission(
            tenant_id=tenant_b,
            part_number="PART-B-001",
            part_name="Automotive Part B",
            submission_level=3,
            oem_customer="OEM Customer B",
            submission_date=datetime.utcnow(),
            approval_status="APPROVED"
        )
        
        db_session.add_all([submission_a, submission_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(PPAPSubmission).where(
            PPAPSubmission.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        submissions_a = results.scalars().all()
        
        assert len(submissions_a) == 1
        assert submissions_a[0].part_number == "PART-A-001"
        print("✅ Tenant A sees only their PPAP submissions")
        
        # Query for tenant B only
        stmt = select(PPAPSubmission).where(
            PPAPSubmission.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        submissions_b = results.scalars().all()
        
        assert len(submissions_b) == 1
        assert submissions_b[0].part_number == "PART-B-001"
        print("✅ Tenant B sees only their PPAP submissions")

    @pytest.mark.asyncio
    async def test_ppap_element_tenant_isolation(self, db_session):
        """Test PPAP elements are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create submissions for both tenants
        submission_a = PPAPSubmission(
            tenant_id=tenant_a,
            part_number="PART-A-002",
            part_name="Part A2",
            submission_level=3,
            oem_customer="OEM A",
            submission_date=datetime.utcnow(),
            approval_status="PENDING"
        )
        submission_b = PPAPSubmission(
            tenant_id=tenant_b,
            part_number="PART-B-002",
            part_name="Part B2",
            submission_level=3,
            oem_customer="OEM B",
            submission_date=datetime.utcnow(),
            approval_status="PENDING"
        )
        
        db_session.add_all([submission_a, submission_b])
        db_session.commit()
        db_session.refresh(submission_a)
        db_session.refresh(submission_b)
        
        # Create elements for tenant A
        element_a = PPAPElement(
            tenant_id=tenant_a,
            submission_id=submission_a.id,
            element_type="PART_SUBMISSION_WARRANT",
            filename="psw_tenant_a.pdf",
            content_hash="a" * 64,
            file_size_bytes=1024
        )
        
        # Create elements for tenant B
        element_b = PPAPElement(
            tenant_id=tenant_b,
            submission_id=submission_b.id,
            element_type="PART_SUBMISSION_WARRANT",
            filename="psw_tenant_b.pdf",
            content_hash="b" * 64,
            file_size_bytes=2048
        )
        
        db_session.add_all([element_a, element_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(PPAPElement).where(
            PPAPElement.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        elements_a = results.scalars().all()
        
        assert len(elements_a) == 1
        assert elements_a[0].filename == "psw_tenant_a.pdf"
        print("✅ Tenant A sees only their PPAP elements")
        
        # Query for tenant B only
        stmt = select(PPAPElement).where(
            PPAPElement.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        elements_b = results.scalars().all()
        
        assert len(elements_b) == 1
        assert elements_b[0].filename == "psw_tenant_b.pdf"
        print("✅ Tenant B sees only their PPAP elements")

    @pytest.mark.asyncio
    async def test_lpa_audit_tenant_isolation(self, db_session):
        """Test LPA audits are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create audit for tenant A
        audit_a = LPAAudit(
            tenant_id=tenant_a,
            audit_date=datetime.utcnow(),
            layer="MANAGEMENT",
            part_number="PART-A-003",
            process_step="Welding Process",
            question="Are welding parameters within specification?",
            result="PASS",
            auditor_name="Auditor A"
        )
        
        # Create audit for tenant B
        audit_b = LPAAudit(
            tenant_id=tenant_b,
            audit_date=datetime.utcnow(),
            layer="FRONTLINE",
            part_number="PART-B-003",
            process_step="Assembly Process",
            question="Are torque specifications being followed?",
            result="FAIL",
            auditor_name="Auditor B",
            corrective_action="Re-train operators on torque procedures"
        )
        
        db_session.add_all([audit_a, audit_b])
        db_session.commit()
        
        # Query for tenant A only
        stmt = select(LPAAudit).where(
            LPAAudit.tenant_id == tenant_a
        )
        results = db_session.execute(stmt)
        audits_a = results.scalars().all()
        
        assert len(audits_a) == 1
        assert audits_a[0].part_number == "PART-A-003"
        assert audits_a[0].result == "PASS"
        print("✅ Tenant A sees only their LPA audits")
        
        # Query for tenant B only
        stmt = select(LPAAudit).where(
            LPAAudit.tenant_id == tenant_b
        )
        results = db_session.execute(stmt)
        audits_b = results.scalars().all()
        
        assert len(audits_b) == 1
        assert audits_b[0].part_number == "PART-B-003"
        assert audits_b[0].result == "FAIL"
        print("✅ Tenant B sees only their LPA audits")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Automotive Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_ppap_submission_model_has_tenant_id())
    asyncio.run(test_suite.test_ppap_element_model_has_tenant_id())
    asyncio.run(test_suite.test_lpa_audit_model_has_tenant_id())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
    print("\n⚠️  Database isolation tests require pytest with db fixtures")
