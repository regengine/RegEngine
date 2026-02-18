"""
Tenant Isolation Tests for Manufacturing Service

Verifies that:
1. tenant_id columns exist in all tables
2. Data is properly isolated by tenant
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
    NonConformanceReport,
    CorrectiveAction,
    SupplierQualityIssue,
    AuditFinding
)


@pytest.mark.security
class TestTenantIsolation:
    """Test tenant isolation in Manufacturing service"""

    @pytest.mark.asyncio
    async def test_ncr_model_has_tenant_id(self):
        """Verify NonConformanceReport model has tenant_id column"""
        assert hasattr(NonConformanceReport, 'tenant_id')
        
        # Verify it's indexed
        table = NonConformanceReport.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ NonConformanceReport has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_corrective_action_model_has_tenant_id(self):
        """Verify CorrectiveAction model has tenant_id column"""
        assert hasattr(CorrectiveAction, 'tenant_id')
        
        table = CorrectiveAction.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ CorrectiveAction has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_supplier_quality_issue_model_has_tenant_id(self):
        """Verify SupplierQualityIssue model has tenant_id column"""
        assert hasattr(SupplierQualityIssue, 'tenant_id')
        
        table = SupplierQualityIssue.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ SupplierQualityIssue has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_audit_finding_model_has_tenant_id(self):
        """Verify AuditFinding model has tenant_id column"""
        assert hasattr(AuditFinding, 'tenant_id')
        
        table = AuditFinding.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ AuditFinding has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_all_models_have_tenant_id_indexed(self):
        """Verify all manufacturing models have indexed tenant_id"""
        models = [
            NonConformanceReport,
            CorrectiveAction,
            SupplierQualityIssue,
            AuditFinding
        ]
        
        for model in models:
            assert hasattr(model, 'tenant_id'), f"{model.__name__} missing tenant_id"
            table = model.__table__
            tenant_column = table.c.tenant_id
            assert tenant_column.index is True, f"{model.__name__} tenant_id not indexed"
        
        print(f"✅ All {len(models)} manufacturing models have indexed tenant_id")

    # Skipped tests require database connection
    @pytest.mark.skip(reason="Requires database with manufacturing schema")
    @pytest.mark.asyncio
    async def test_tenant_ncr_isolation(self, db_session):
        """Test NCRs are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create NCR for tenant A
        ncr_a = NonConformanceReport(
            tenant_id=tenant_a,
            ncr_number="NCR-A-001",
            detected_date=datetime.utcnow(),
            detected_by="Inspector A",
            detection_source="INTERNAL_AUDIT",
            description="Defect in part A",
            severity="MAJOR",
            status="OPEN"
        )
        
        # Create NCR for tenant B
        ncr_b = NonConformanceReport(
            tenant_id=tenant_b,
            ncr_number="NCR-B-001",
            detected_date=datetime.utcnow(),
            detected_by="Inspector B",
            detection_source="CUSTOMER_COMPLAINT",
            description="Defect in part B",
            severity="CRITICAL",
            status="OPEN"
        )
        
        db_session.add_all([ncr_a, ncr_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(NonConformanceReport).where(
            NonConformanceReport.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        ncrs_a = results.scalars().all()
        
        assert len(ncrs_a) == 1
        assert ncrs_a[0].ncr_number == "NCR-A-001"
        print("✅ Tenant A sees only their NCRs")
        
        # Query for tenant B only
        stmt = select(NonConformanceReport).where(
            NonConformanceReport.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        ncrs_b = results.scalars().all()
        
        assert len(ncrs_b) == 1
        assert ncrs_b[0].ncr_number == "NCR-B-001"
        print("✅ Tenant B sees only their NCRs")

    @pytest.mark.skip(reason="Requires database with manufacturing schema")
    @pytest.mark.asyncio
    async def test_tenant_capa_isolation(self, db_session):
        """Test CAPAs are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create NCRs first
        ncr_a = NonConformanceReport(
            tenant_id=tenant_a,
            ncr_number="NCR-A-002",
            detected_date=datetime.utcnow(),
            detected_by="Inspector A",
            detection_source="INTERNAL_AUDIT",
            description="Issue A",
            severity="MINOR",
            status="CAPA_IN_PROGRESS"
        )
        
        ncr_b = NonConformanceReport(
            tenant_id=tenant_b,
            ncr_number="NCR-B-002",
            detected_date=datetime.utcnow(),
            detected_by="Inspector B",
            detection_source="PROCESS_MONITORING",
            description="Issue B",
            severity="MAJOR",
            status="CAPA_IN_PROGRESS"
        )
        
        db_session.add_all([ncr_a, ncr_b])
        await db_session.flush()
        
        # Create CAPAs for each tenant
        capa_a = CorrectiveAction(
            tenant_id=tenant_a,
            ncr_id=ncr_a.id,
            action_type="CORRECTIVE",
            description="Fix issue A",
            assigned_to="Engineer A",
            due_date=datetime.utcnow(),
            implementation_status="IN_PROGRESS"
        )
        
        capa_b = CorrectiveAction(
            tenant_id=tenant_b,
            ncr_id=ncr_b.id,
            action_type="PREVENTIVE",
            description="Prevent issue B",
            assigned_to="Engineer B",
            due_date=datetime.utcnow(),
            implementation_status="PENDING"
        )
        
        db_session.add_all([capa_a, capa_b])
        await db_session.commit()
        
        # Query for tenant A CAPAs only
        stmt = select(CorrectiveAction).where(
            CorrectiveAction.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        capas_a = results.scalars().all()
        
        assert len(capas_a) == 1
        assert capas_a[0].assigned_to == "Engineer A"
        print("✅ Tenant A sees only their CAPAs")
        
        # Query for tenant B CAPAs only
        stmt = select(CorrectiveAction).where(
            CorrectiveAction.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        capas_b = results.scalars().all()
        
        assert len(capas_b) == 1
        assert capas_b[0].assigned_to == "Engineer B"
        print("✅ Tenant B sees only their CAPAs")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Manufacturing Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_ncr_model_has_tenant_id())
    asyncio.run(test_suite.test_corrective_action_model_has_tenant_id())
    asyncio.run(test_suite.test_supplier_quality_issue_model_has_tenant_id())
    asyncio.run(test_suite.test_audit_finding_model_has_tenant_id())
    asyncio.run(test_suite.test_all_models_have_tenant_id_indexed())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
    print("\n⚠️  Deploy manufacturing schema to enable full isolation tests")
