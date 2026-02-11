"""
Tenant Isolation Tests for Aerospace Service

Verifies that:
1. tenant_id columns exist in all tables
2. FAI reports, baselines, and NADCAP evidence are properly isolated by tenant
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
    FAIReport,
    ConfigurationBaseline,
    NADCAPEvidence
)


@pytest.mark.security
class TestTenantIsolation:
    """Test tenant isolation in Aerospace service"""

    @pytest.mark.asyncio
    async def test_fai_report_has_tenant_id(self):
        """Verify FAIReport has tenant_id column"""
        assert hasattr(FAIReport, 'tenant_id')
        
        # Verify it's indexed
        table = FAIReport.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ FAIReport has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_configuration_baseline_has_tenant_id(self):
        """Verify ConfigurationBaseline has tenant_id column"""
        assert hasattr(ConfigurationBaseline, 'tenant_id')
        
        table = ConfigurationBaseline.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ ConfigurationBaseline has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_nadcap_evidence_has_tenant_id(self):
        """Verify NADCAPEvidence has tenant_id column"""
        assert hasattr(NADCAPEvidence, 'tenant_id')
        
        table = NADCAPEvidence.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ NADCAPEvidence has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_all_models_have_tenant_id(self):
        """Verify all aerospace models have tenant_id column"""
        models = [FAIReport, ConfigurationBaseline, NADCAPEvidence]
        
        for model in models:
            assert hasattr(model, 'tenant_id'), f"{model.__name__} missing tenant_id"
            table = model.__table__
            tenant_column = table.c.tenant_id
            assert tenant_column.index is True, f"{model.__name__} tenant_id not indexed"
        
        print(f"✅ All {len(models)} aerospace models have indexed tenant_id")

    # Skipped tests require database connection
    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_tenant_fai_isolation(self, db_session):
        """Test FAI reports are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create FAI report for tenant A
        fai_a = FAIReport(
            id=1,
            tenant_id=tenant_a,
            part_number="PN-12345-A",
            part_name="Wing Bracket",
            drawing_number="DWG-001",
            drawing_revision="A",
            customer_name="Customer A",
            form1_data={"test": "data"},
            form2_data=[{"test": "data"}],
            form3_data=[{"test": "data"}],
            inspection_method="ACTUAL",
            inspection_date=datetime.utcnow(),
            inspector_name="Inspector A",
            content_hash="a" * 64,
            approval_status="PENDING"
        )
        
        # Create FAI report for tenant B
        fai_b = FAIReport(
            id=2,
            tenant_id=tenant_b,
            part_number="PN-12345-B",
            part_name="Wing Bracket",
            drawing_number="DWG-001",
            drawing_revision="A",
            customer_name="Customer B",
            form1_data={"test": "data"},
            form2_data=[{"test": "data"}],
            form3_data=[{"test": "data"}],
            inspection_method="ACTUAL",
            inspection_date=datetime.utcnow(),
            inspector_name="Inspector B",
            content_hash="b" * 64,
            approval_status="PENDING"
        )
        
        db_session.add_all([fai_a, fai_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(FAIReport).where(FAIReport.tenant_id == tenant_a)
        results = await db_session.execute(stmt)
        reports_a = results.scalars().all()
        
        assert len(reports_a) == 1
        assert reports_a[0].part_number == "PN-12345-A"
        print("✅ Tenant A sees only their FAI reports")
        
        # Query for tenant B only
        stmt = select(FAIReport).where(FAIReport.tenant_id == tenant_b)
        results = await db_session.execute(stmt)
        reports_b = results.scalars().all()
        
        assert len(reports_b) == 1
        assert reports_b[0].part_number == "PN-12345-B"
        print("✅ Tenant B sees only their FAI reports")

    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_tenant_baseline_isolation(self, db_session):
        """Test configuration baselines are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create baseline for tenant A
        baseline_a = ConfigurationBaseline(
            id=1,
            tenant_id=tenant_a,
            assembly_id="ASM-A-001",
            assembly_name="Assembly A",
            serial_number="SN-A-001",
            baseline_data={"components": []},
            baseline_hash="a" * 64,
            manufacturing_date=datetime.utcnow(),
            lifecycle_status="ACTIVE"
        )
        
        # Create baseline for tenant B
        baseline_b = ConfigurationBaseline(
            id=2,
            tenant_id=tenant_b,
            assembly_id="ASM-B-001",
            assembly_name="Assembly B",
            serial_number="SN-B-001",
            baseline_data={"components": []},
            baseline_hash="b" * 64,
            manufacturing_date=datetime.utcnow(),
            lifecycle_status="ACTIVE"
        )
        
        db_session.add_all([baseline_a, baseline_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(ConfigurationBaseline).where(
            ConfigurationBaseline.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        baselines_a = results.scalars().all()
        
        assert len(baselines_a) == 1
        assert baselines_a[0].assembly_id == "ASM-A-001"
        print("✅ Tenant A sees only their baselines")
        
        # Query for tenant B only
        stmt = select(ConfigurationBaseline).where(
            ConfigurationBaseline.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        baselines_b = results.scalars().all()
        
        assert len(baselines_b) == 1
        assert baselines_b[0].assembly_id == "ASM-B-001"
        print("✅ Tenant B sees only their baselines")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Aerospace Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_fai_report_has_tenant_id())
    asyncio.run(test_suite.test_configuration_baseline_has_tenant_id())
    asyncio.run(test_suite.test_nadcap_evidence_has_tenant_id())
    asyncio.run(test_suite.test_all_models_have_tenant_id())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
    print("\n⚠️  Database connection required for full isolation tests")
