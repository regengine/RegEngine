"""
Tenant Isolation Tests for Gaming Service

Verifies that:
1. tenant_id columns exist in all tables
2. Transaction logs are properly isolated by tenant
3. Self-exclusion records are properly isolated by tenant
4. Responsible gaming alerts are properly isolated by tenant
5. Cross-tenant data leakage is prevented
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
    TransactionLog,
    SelfExclusionRecord,
    ResponsibleGamingAlert
)


@pytest.mark.security
class TestTenantIsolation:
    """Test tenant isolation in Gaming service"""

    @pytest.mark.asyncio
    async def test_transaction_log_has_tenant_id(self):
        """Verify TransactionLog has tenant_id column"""
        assert hasattr(TransactionLog, 'tenant_id')
        
        # Verify it's indexed
        table = TransactionLog.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ TransactionLog has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_self_exclusion_record_has_tenant_id(self):
        """Verify SelfExclusionRecord has tenant_id column"""
        assert hasattr(SelfExclusionRecord, 'tenant_id')
        
        table = SelfExclusionRecord.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ SelfExclusionRecord has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_responsible_gaming_alert_has_tenant_id(self):
        """Verify ResponsibleGamingAlert has tenant_id column"""
        assert hasattr(ResponsibleGamingAlert, 'tenant_id')
        
        table = ResponsibleGamingAlert.__table__
        tenant_column = table.c.tenant_id
        assert tenant_column.index is True
        print("✅ ResponsibleGamingAlert has indexed tenant_id")

    @pytest.mark.asyncio
    async def test_all_models_have_tenant_id(self):
        """Verify all Gaming models have tenant_id for multi-tenancy"""
        models = [TransactionLog, SelfExclusionRecord, ResponsibleGamingAlert]
        
        for model in models:
            assert hasattr(model, 'tenant_id'), f"{model.__name__} missing tenant_id"
            table = model.__table__
            tenant_column = table.c.tenant_id
            assert tenant_column.index is True, f"{model.__name__} tenant_id not indexed"
        
        print(f"✅ All {len(models)} Gaming models have indexed tenant_id")

    @pytest.mark.asyncio
    async def test_tenant_id_columns_not_nullable(self):
        """Verify tenant_id columns are NOT NULL for data integrity"""
        models = [TransactionLog, SelfExclusionRecord, ResponsibleGamingAlert]
        
        for model in models:
            table = model.__table__
            tenant_column = table.c.tenant_id
            assert tenant_column.nullable is False, f"{model.__name__} tenant_id should be NOT NULL"
        
        print("✅ All tenant_id columns are NOT NULL")

    # Skipped tests require database connection
    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_tenant_transaction_isolation(self, db_session):
        """Test transaction logs are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create transaction for tenant A
        txn_a = TransactionLog(
            tenant_id=tenant_a,
            player_id="PLAYER-A-001",
            transaction_type="WAGER",
            amount_cents=1000,
            game_id="GAME-SLOTS-001",
            jurisdiction="NEVADA",
            timestamp=datetime.utcnow(),
            content_hash="a" * 64
        )
        
        # Create transaction for tenant B
        txn_b = TransactionLog(
            tenant_id=tenant_b,
            player_id="PLAYER-B-001",
            transaction_type="PAYOUT",
            amount_cents=5000,
            game_id="GAME-POKER-001",
            jurisdiction="NEW_JERSEY",
            timestamp=datetime.utcnow(),
            content_hash="b" * 64
        )
        
        db_session.add_all([txn_a, txn_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(TransactionLog).where(
            TransactionLog.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        txns_a = results.scalars().all()
        
        assert len(txns_a) == 1
        assert txns_a[0].player_id == "PLAYER-A-001"
        print("✅ Tenant A sees only their transactions")
        
        # Query for tenant B only
        stmt = select(TransactionLog).where(
            TransactionLog.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        txns_b = results.scalars().all()
        
        assert len(txns_b) == 1
        assert txns_b[0].player_id == "PLAYER-B-001"
        print("✅ Tenant B sees only their transactions")

    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_tenant_self_exclusion_isolation(self, db_session):
        """Test self-exclusion records are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create self-exclusion for tenant A
        exclusion_a = SelfExclusionRecord(
            tenant_id=tenant_a,
            player_id="PLAYER-A-EXCLUDED",
            duration_days=365,
            reason="Personal request",
            effective_date=datetime.utcnow(),
            status="ACTIVE"
        )
        
        # Create self-exclusion for tenant B
        exclusion_b = SelfExclusionRecord(
            tenant_id=tenant_b,
            player_id="PLAYER-B-EXCLUDED",
            duration_days=90,
            reason="Cooling off period",
            effective_date=datetime.utcnow(),
            status="ACTIVE"
        )
        
        db_session.add_all([exclusion_a, exclusion_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(SelfExclusionRecord).where(
            SelfExclusionRecord.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        exclusions_a = results.scalars().all()
        
        assert len(exclusions_a) == 1
        assert exclusions_a[0].duration_days == 365
        print("✅ Tenant A sees only their self-exclusions")
        
        # Query for tenant B only
        stmt = select(SelfExclusionRecord).where(
            SelfExclusionRecord.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        exclusions_b = results.scalars().all()
        
        assert len(exclusions_b) == 1
        assert exclusions_b[0].duration_days == 90
        print("✅ Tenant B sees only their self-exclusions")

    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_tenant_alert_isolation(self, db_session):
        """Test responsible gaming alerts are isolated by tenant"""
        tenant_a = uuid4()
        tenant_b = uuid4()
        
        # Create alert for tenant A
        alert_a = ResponsibleGamingAlert(
            tenant_id=tenant_a,
            player_id="PLAYER-A-RISKY",
            alert_type="HIGH_FREQUENCY",
            risk_score=85,
            detection_data={"sessions_per_day": 15},
            status="PENDING"
        )
        
        # Create alert for tenant B
        alert_b = ResponsibleGamingAlert(
            tenant_id=tenant_b,
            player_id="PLAYER-B-RISKY",
            alert_type="LOSS_CHASING",
            risk_score=72,
            detection_data={"consecutive_losses": 10},
            status="REVIEWED"
        )
        
        db_session.add_all([alert_a, alert_b])
        await db_session.commit()
        
        # Query for tenant A only
        stmt = select(ResponsibleGamingAlert).where(
            ResponsibleGamingAlert.tenant_id == tenant_a
        )
        results = await db_session.execute(stmt)
        alerts_a = results.scalars().all()
        
        assert len(alerts_a) == 1
        assert alerts_a[0].risk_score == 85
        print("✅ Tenant A sees only their alerts")
        
        # Query for tenant B only
        stmt = select(ResponsibleGamingAlert).where(
            ResponsibleGamingAlert.tenant_id == tenant_b
        )
        results = await db_session.execute(stmt)
        alerts_b = results.scalars().all()
        
        assert len(alerts_b) == 1
        assert alerts_b[0].risk_score == 72
        print("✅ Tenant B sees only their alerts")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Gaming Service Tenant Isolation Test Suite")
    print("="*60 + "\n")
    
    # Run model structure tests
    test_suite = TestTenantIsolation()
    
    import asyncio
    asyncio.run(test_suite.test_transaction_log_has_tenant_id())
    asyncio.run(test_suite.test_self_exclusion_record_has_tenant_id())
    asyncio.run(test_suite.test_responsible_gaming_alert_has_tenant_id())
    asyncio.run(test_suite.test_all_models_have_tenant_id())
    asyncio.run(test_suite.test_tenant_id_columns_not_nullable())
    
    print("\n" + "="*60)
    print("✅ All model structure tests passed!")
    print("="*60)
    print("\n⚠️  Deploy Gaming DB schema to enable full isolation tests")
