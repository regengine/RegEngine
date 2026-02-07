"""
Tenant Isolation Tests for Energy Service

Verifies that:
1. tenant_id columns exist in all tables
2. Snapshots are properly isolated by tenant
3. Cross-tenant data leakage is prevented
"""

import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy import select

# Import models
import sys
sys.path.insert(0, '/Users/christophersellers/Desktop/RegEngine/services/energy')

from app.database import (
    ComplianceSnapshotModel,
    MismatchModel,
    AttestationModel
)


class TestTenantIsolation:
    """Test tenant isolation in Energy service"""

    @pytest.mark.asyncio
    async def test_snapshot_model_has_tenant_id(self):
        """Verify ComplianceSnapshotModel has tenant_id column"""
        assert hasattr(ComplianceSnapshotModel, 'tenant_id')
        
        # Verify it's indexed
        table = ComplianceSnapshotModel.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ ComplianceSnapshotModel has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_mismatch_model_has_tenant_id(self):
        """Verify MismatchModel has tenant_id column"""
        assert hasattr(MismatchModel, 'tenant_id')
        
        table = MismatchModel.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ MismatchModel has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_attestation_model_has_tenant_id(self):
        """Verify AttestationModel has tenant_id column"""
        assert hasattr(AttestationModel, 'tenant_id')
        
        table = AttestationModel.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ AttestationModel has indexed tenant_id")

    # Skipped tests require database connection
    @pytest.mark.skip(reason="Requires database with V005 migration")
    @pytest.mark.asyncio
    async def test_tenant_snapshot_isolation(self, db_session):
        """Test snapshots are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create snapshot for tenant A
        snapshot_a = ComplianceSnapshotModel(
            id=uuid4(),
            tenant_id=tenant_a,
            created_at=datetime.utcnow(),
            snapshot_time=datetime.utcnow(),
            substation_id="SUB-A-001",
            facility_name="Facility A",
            system_status="NOMINAL",
            asset_states={"test": "data"},
            esp_config={},
            patch_metrics={},
            active_mismatches=[],
            generated_by="SYSTEM_AUTO",
            trigger_event="INITIAL_BASELINE",
            content_hash="a" * 64,
            signature_hash="b" * 64
        )
        
        # Create snapshot for tenant B
        snapshot_b = ComplianceSnapshotModel(
            id=uuid4(),
            tenant_id=tenant_b,
            created_at=datetime.utcnow(),
            snapshot_time=datetime.utcnow(),
            substation_id="SUB-B-001",
            facility_name="Facility B",
            system_status="NOMINAL",
            asset_states={"test": "data"},
            esp_config={},
            patch_metrics={},
            active_mismatches=[],
            generated_by="SYSTEM_AUTO",
            trigger_event="INITIAL_BASELINE",
            content_hash="c" * 64,
            signature_hash="d" * 64
        )
        
        db_session.add_all([snapshot_a, snapshot_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(ComplianceSnapshotModel).where(
            ComplianceSnapshotModel.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        snapshots_a = results.scalars().all()
        
        assert len(snapshots_a) == 1
        assert snapshots_a[0].substation_id == "SUB-A-001"
        print("✅ Tenant A sees only their snapshots")
        
        # Query for tenant B only
        stmt = select(ComplianceSnapshotModel).where(
            ComplianceSnapshotModel.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        snapshots_b = results.scalars().all()
        
        assert len(snapshots_b) == 1
        assert snapshots_b[0].substation_id == "SUB-B-001"
        print("✅ Tenant B sees only their snapshots")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Energy Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_snapshot_model_has_tenant_id())
    asyncio.run(test_suite.test_mismatch_model_has_tenant_id())
    asyncio.run(test_suite.test_attestation_model_has_tenant_id())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
    print("\n⚠️  Deploy V005 migration to Energy DB to enable full isolation tests")
