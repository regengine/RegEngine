"""
Tests for FSMA 204 Mock Recall Automation Engine.

Sprint 8: Validates recall drill execution, SLA tracking, and scheduling.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.graph.app.fsma_recall import (
    AffectedFacility,
    MockRecallEngine,
    RecallDrill,
    RecallResult,
    RecallSeverity,
    RecallStatus,
    RecallType,
    ScheduledDrill,
    SLAStatus,
    create_mock_recall,
    get_recall_engine,
    get_recall_history,
    get_recall_readiness,
    reset_recall_engine,
)

# ============================================================================
# RECALL DRILL TESTS
# ============================================================================


class TestRecallDrill:
    """Tests for RecallDrill dataclass."""

    def test_drill_creation(self):
        """Test basic drill creation."""
        drill = RecallDrill(
            drill_id="drill_test123",
            tenant_id="tenant_1",
            created_at=datetime.utcnow(),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )

        assert drill.drill_id == "drill_test123"
        assert drill.tenant_id == "tenant_1"
        assert drill.drill_type == RecallType.FORWARD_TRACE
        assert drill.severity == RecallSeverity.CLASS_II
        assert drill.status == RecallStatus.PENDING

    def test_drill_auto_id_generation(self):
        """Test automatic drill ID generation."""
        drill = RecallDrill(
            drill_id="",
            tenant_id="tenant_1",
            created_at=datetime.utcnow(),
            drill_type=RecallType.FULL_TRACE,
            severity=RecallSeverity.CLASS_I,
        )

        assert drill.drill_id.startswith("drill_")
        assert len(drill.drill_id) == 18  # drill_ + 12 hex chars

    def test_drill_duration_calculation(self):
        """Test duration calculation for completed drill."""
        now = datetime.utcnow()
        drill = RecallDrill(
            drill_id="drill_test123",
            tenant_id="tenant_1",
            created_at=now - timedelta(minutes=10),
            drill_type=RecallType.BACKWARD_TRACE,
            severity=RecallSeverity.CLASS_III,
            started_at=now - timedelta(minutes=5),
            completed_at=now,
        )

        assert drill.duration_seconds is not None
        assert abs(drill.duration_seconds - 300) < 1  # ~5 minutes

    def test_sla_status_met(self):
        """Test SLA status when completed within 24 hours."""
        now = datetime.utcnow()
        drill = RecallDrill(
            drill_id="drill_test123",
            tenant_id="tenant_1",
            created_at=now,
            drill_type=RecallType.FULL_TRACE,
            severity=RecallSeverity.CLASS_II,
            status=RecallStatus.COMPLETED,
            started_at=now - timedelta(hours=1),
            completed_at=now,
        )

        assert drill.sla_status == SLAStatus.MET

    def test_sla_status_breached(self):
        """Test SLA status when exceeds 24 hours."""
        now = datetime.utcnow()
        drill = RecallDrill(
            drill_id="drill_test123",
            tenant_id="tenant_1",
            created_at=now - timedelta(hours=26),
            drill_type=RecallType.FULL_TRACE,
            severity=RecallSeverity.CLASS_II,
            status=RecallStatus.COMPLETED,
            started_at=now - timedelta(hours=26),
            completed_at=now,
        )

        assert drill.sla_status == SLAStatus.BREACHED

    def test_drill_to_dict(self):
        """Test drill serialization."""
        drill = RecallDrill(
            drill_id="drill_test123",
            tenant_id="tenant_1",
            created_at=datetime(2024, 1, 15, 10, 30, 0),
            drill_type=RecallType.TARGETED,
            severity=RecallSeverity.CLASS_II,
            target_lot="LOT-001",
            initiated_by="user_123",
        )

        data = drill.to_dict()

        assert data["drill_id"] == "drill_test123"
        assert data["tenant_id"] == "tenant_1"
        assert data["drill_type"] == "targeted"
        assert data["severity"] == "class_ii"
        assert data["target_lot"] == "LOT-001"
        assert data["initiated_by"] == "user_123"
        assert data["status"] == "pending"


class TestRecallResult:
    """Tests for RecallResult dataclass."""

    def test_result_creation(self):
        """Test basic result creation."""
        result = RecallResult(
            drill_id="drill_test123",
            success=True,
            lots_traced=10,
            facilities_identified=5,
            total_time_seconds=45.5,
            sla_compliant=True,
        )

        assert result.drill_id == "drill_test123"
        assert result.success is True
        assert result.lots_traced == 10
        assert result.facilities_identified == 5
        assert result.sla_compliant is True

    def test_result_with_affected_facilities(self):
        """Test result with affected facilities list."""
        facilities = [
            AffectedFacility(
                gln="1234567890123",
                name="Test Processor",
                facility_type="processor",
                lots_affected=["LOT-001", "LOT-002"],
                quantity_affected=150.0,
            ),
            AffectedFacility(
                gln="9876543210987",
                name="Test Distributor",
                facility_type="distributor",
                lots_affected=["LOT-001"],
                quantity_affected=50.0,
            ),
        ]

        result = RecallResult(
            drill_id="drill_test123",
            success=True,
            affected_facilities=facilities,
        )

        assert len(result.affected_facilities) == 2
        assert result.affected_facilities[0].name == "Test Processor"

    def test_result_to_dict(self):
        """Test result serialization."""
        result = RecallResult(
            drill_id="drill_test123",
            success=True,
            lots_traced=5,
            facilities_identified=3,
            trace_time_seconds=10.5,
            export_time_seconds=2.3,
            total_time_seconds=12.8,
            sla_compliant=True,
            data_completeness_pct=95.5,
        )

        data = result.to_dict()

        assert data["drill_id"] == "drill_test123"
        assert data["success"] is True
        assert data["lots_traced"] == 5
        assert data["trace_time_seconds"] == 10.5
        assert data["sla_compliant"] is True

    def test_result_get_summary(self):
        """Test abbreviated summary generation."""
        result = RecallResult(
            drill_id="drill_test123",
            success=True,
            lots_traced=10,
            facilities_identified=5,
            total_time_seconds=30.0,
            sla_compliant=True,
            data_completeness_pct=98.5,
            errors=["warning1"],
            warnings=["warning2"],
        )

        summary = result.get_summary()

        assert summary["drill_id"] == "drill_test123"
        assert summary["lots_traced"] == 10
        assert "errors" not in summary  # Summary should be abbreviated


# ============================================================================
# MOCK RECALL ENGINE TESTS
# ============================================================================


class TestMockRecallEngine:
    """Tests for MockRecallEngine class."""

    def setup_method(self):
        """Reset engine before each test."""
        reset_recall_engine()
        self.engine = MockRecallEngine()

    def test_create_drill(self):
        """Test creating a new drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
            target_lot="LOT-2024-001",
        )

        assert drill.tenant_id == "tenant_1"
        assert drill.drill_type == RecallType.FORWARD_TRACE
        assert drill.target_lot == "LOT-2024-001"
        assert drill.status == RecallStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_drill_forward_trace(self):
        """Test executing a forward trace drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            target_lot="LOT-001",
        )

        result = await self.engine.execute_drill(drill)

        assert result.success is True
        assert result.lots_traced > 0
        assert drill.status == RecallStatus.COMPLETED
        assert drill.started_at is not None
        assert drill.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_drill_backward_trace(self):
        """Test executing a backward trace drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.BACKWARD_TRACE,
            target_lot="FINISHED-001",
        )

        result = await self.engine.execute_drill(drill)

        assert result.success is True
        assert result.max_depth_backward > 0

    @pytest.mark.asyncio
    async def test_execute_drill_full_trace(self):
        """Test executing a full (bidirectional) trace drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
            target_lot="MID-LOT-001",
        )

        result = await self.engine.execute_drill(drill)

        assert result.success is True
        assert result.max_depth_forward > 0
        assert result.max_depth_backward > 0

    @pytest.mark.asyncio
    async def test_execute_drill_mass_balance(self):
        """Test executing a mass balance drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.MASS_BALANCE,
            target_lot="LOT-001",
        )

        result = await self.engine.execute_drill(drill)

        assert result.success is True
        assert len(result.warnings) > 0  # Should have mass balance warning

    @pytest.mark.asyncio
    async def test_execute_drill_targeted(self):
        """Test executing a targeted facility drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.TARGETED,
            target_facility_gln="1234567890123",
            target_lot="LOT-001",
        )

        result = await self.engine.execute_drill(drill)

        assert result.success is True
        assert any(f.gln == "1234567890123" for f in result.affected_facilities)

    @pytest.mark.asyncio
    async def test_drill_sla_compliance(self):
        """Test that drill correctly tracks SLA compliance."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            target_lot="LOT-001",
        )

        result = await self.engine.execute_drill(drill)

        # Drill execution should be fast (well under 24 hours)
        assert result.sla_compliant is True
        assert result.total_time_seconds < 60  # Should complete in under a minute

    @pytest.mark.asyncio
    async def test_get_drill_history(self):
        """Test retrieving drill history."""
        # Create and execute multiple drills
        for i in range(5):
            drill = self.engine.create_drill(
                tenant_id="tenant_1",
                drill_type=RecallType.FORWARD_TRACE,
                target_lot=f"LOT-{i}",
            )
            await self.engine.execute_drill(drill)

        history = self.engine.get_drill_history("tenant_1")

        assert len(history) == 5
        # Should be sorted by creation time (most recent first)
        assert history[0].target_lot == "LOT-4"

    @pytest.mark.asyncio
    async def test_get_drill_history_with_limit(self):
        """Test history with result limit."""
        for i in range(10):
            drill = self.engine.create_drill(
                tenant_id="tenant_1",
                drill_type=RecallType.FORWARD_TRACE,
            )
            await self.engine.execute_drill(drill)

        history = self.engine.get_drill_history("tenant_1", limit=3)

        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_drill_history_status_filter(self):
        """Test history filtering by status."""
        drill1 = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )
        await self.engine.execute_drill(drill1)

        drill2 = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.BACKWARD_TRACE,
        )
        # Don't execute drill2, leave as pending

        completed = self.engine.get_drill_history(
            "tenant_1", status_filter=RecallStatus.COMPLETED
        )

        assert len(completed) == 1
        assert completed[0].status == RecallStatus.COMPLETED

    def test_get_specific_drill(self):
        """Test retrieving a specific drill by ID."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
        )

        retrieved = self.engine.get_drill("tenant_1", drill.drill_id)

        assert retrieved is not None
        assert retrieved.drill_id == drill.drill_id

    def test_get_nonexistent_drill(self):
        """Test retrieving non-existent drill returns None."""
        result = self.engine.get_drill("tenant_1", "nonexistent_id")
        assert result is None

    def test_cancel_pending_drill(self):
        """Test cancelling a pending drill."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )

        success = self.engine.cancel_drill(drill)

        assert success is True
        assert drill.status == RecallStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_drill_fails(self):
        """Test that cancelling a completed drill fails."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )
        await self.engine.execute_drill(drill)

        success = self.engine.cancel_drill(drill)

        assert success is False
        assert drill.status == RecallStatus.COMPLETED


# ============================================================================
# SLA METRICS TESTS
# ============================================================================


class TestSLAMetrics:
    """Tests for SLA compliance metrics."""

    def setup_method(self):
        """Reset engine before each test."""
        reset_recall_engine()
        self.engine = MockRecallEngine()

    def test_initial_sla_metrics(self):
        """Test initial SLA metrics for new tenant."""
        metrics = self.engine.get_sla_metrics("new_tenant")

        assert metrics["total_drills"] == 0
        assert metrics["sla_compliance_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_sla_metrics_after_drill(self):
        """Test SLA metrics update after drill execution."""
        drill = self.engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )
        await self.engine.execute_drill(drill)

        metrics = self.engine.get_sla_metrics("tenant_1")

        assert metrics["total_drills"] == 1
        assert metrics["successful_drills"] == 1
        assert metrics["sla_compliant_drills"] == 1
        assert metrics["sla_compliance_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_sla_metrics_accumulation(self):
        """Test SLA metrics accumulate across multiple drills."""
        for _ in range(5):
            drill = self.engine.create_drill(
                tenant_id="tenant_1",
                drill_type=RecallType.FORWARD_TRACE,
            )
            await self.engine.execute_drill(drill)

        metrics = self.engine.get_sla_metrics("tenant_1")

        assert metrics["total_drills"] == 5
        assert metrics["avg_trace_time"] > 0


# ============================================================================
# SCHEDULING TESTS
# ============================================================================


class TestRecallScheduling:
    """Tests for recall drill scheduling."""

    def setup_method(self):
        """Reset engine before each test."""
        reset_recall_engine()
        self.engine = MockRecallEngine()

    def test_create_schedule(self):
        """Test creating a drill schedule."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
            frequency_days=90,
            severity=RecallSeverity.CLASS_II,
        )

        assert schedule.tenant_id == "tenant_1"
        assert schedule.drill_type == RecallType.FULL_TRACE
        assert schedule.frequency_days == 90
        assert schedule.enabled is True

    def test_schedule_next_run_calculation(self):
        """Test next run time is calculated correctly."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            frequency_days=30,
        )

        now = datetime.utcnow()
        expected_next = now + timedelta(days=30)

        # Allow 1 second tolerance
        assert abs((schedule.next_run - expected_next).total_seconds()) < 1

    def test_list_schedules(self):
        """Test listing all schedules for tenant."""
        self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            frequency_days=30,
        )
        self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.BACKWARD_TRACE,
            frequency_days=90,
        )

        schedules = self.engine.get_schedules("tenant_1")

        assert len(schedules) == 2

    def test_get_specific_schedule(self):
        """Test retrieving a specific schedule."""
        created = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
        )

        retrieved = self.engine.get_schedule("tenant_1", created.schedule_id)

        assert retrieved is not None
        assert retrieved.schedule_id == created.schedule_id

    def test_update_schedule_enabled(self):
        """Test updating schedule enabled status."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )

        self.engine.update_schedule(schedule, enabled=False)

        assert schedule.enabled is False

    def test_update_schedule_frequency(self):
        """Test updating schedule frequency."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            frequency_days=30,
        )

        self.engine.update_schedule(schedule, frequency_days=60)

        assert schedule.frequency_days == 60

    def test_delete_schedule(self):
        """Test deleting a schedule."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )
        schedule_id = schedule.schedule_id

        success = self.engine.delete_schedule("tenant_1", schedule_id)

        assert success is True
        assert self.engine.get_schedule("tenant_1", schedule_id) is None

    def test_check_due_schedules(self):
        """Test finding schedules that are due."""
        # Create schedule with past next_run
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            frequency_days=1,
        )
        # Manually set next_run to past
        schedule.next_run = datetime.utcnow() - timedelta(hours=1)

        due = self.engine.check_due_schedules("tenant_1")

        assert len(due) == 1
        assert due[0].schedule_id == schedule.schedule_id

    @pytest.mark.asyncio
    async def test_execute_scheduled_drill(self):
        """Test executing a drill from schedule."""
        schedule = self.engine.create_schedule(
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
            frequency_days=90,
        )

        drill = await self.engine.execute_scheduled_drill(schedule)

        assert drill.status == RecallStatus.COMPLETED
        assert drill.reason == "scheduled_drill"
        assert schedule.last_run is not None
        assert schedule.last_result == drill.drill_id


# ============================================================================
# READINESS REPORT TESTS
# ============================================================================


class TestReadinessReport:
    """Tests for FDA recall readiness report."""

    def setup_method(self):
        """Reset engine before each test."""
        reset_recall_engine()
        self.engine = MockRecallEngine()

    def test_readiness_report_empty(self):
        """Test readiness report for tenant with no drills."""
        report = self.engine.get_readiness_report("new_tenant")

        assert report["tenant_id"] == "new_tenant"
        assert "sla_compliance" in report
        assert "drill_metrics" in report
        assert "recommendations" in report

    @pytest.mark.asyncio
    async def test_readiness_report_with_drills(self):
        """Test readiness report after executing drills."""
        # Execute some drills
        for _ in range(3):
            drill = self.engine.create_drill(
                tenant_id="tenant_1",
                drill_type=RecallType.FULL_TRACE,
            )
            await self.engine.execute_drill(drill)

        report = self.engine.get_readiness_report("tenant_1")

        assert report["drill_metrics"]["total_drills"] == 3
        assert report["drill_metrics"]["completed_drills"] == 3

    def test_readiness_report_recommendations(self):
        """Test that report includes relevant recommendations."""
        # New tenant with no drills should get recommendation
        report = self.engine.get_readiness_report("new_tenant")

        assert len(report["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_readiness_report_compliant_status(self):
        """Test readiness status when compliant."""
        # Execute drills to establish compliance
        for _ in range(5):
            drill = self.engine.create_drill(
                tenant_id="tenant_1",
                drill_type=RecallType.FULL_TRACE,
            )
            await self.engine.execute_drill(drill)

        report = self.engine.get_readiness_report("tenant_1")

        assert report["sla_compliance"]["rate_pct"] == 100.0


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Reset engine before each test."""
        reset_recall_engine()

    def test_get_recall_engine_singleton(self):
        """Test that get_recall_engine returns same instance."""
        engine1 = get_recall_engine()
        engine2 = get_recall_engine()

        assert engine1 is engine2

    def test_reset_recall_engine(self):
        """Test that reset creates new instance."""
        engine1 = get_recall_engine()
        reset_recall_engine()
        engine2 = get_recall_engine()

        assert engine1 is not engine2

    @pytest.mark.asyncio
    async def test_create_mock_recall(self):
        """Test convenience function for creating and executing drill."""
        result = await create_mock_recall(
            tenant_id="tenant_1",
            drill_type="forward_trace",
            severity="class_ii",
            target_lot="LOT-001",
        )

        assert "drill_id" in result
        assert result["status"] == "completed"
        assert "result" in result

    @pytest.mark.asyncio
    async def test_get_recall_history_function(self):
        """Test convenience function for getting history."""
        # Create a drill first
        await create_mock_recall(
            tenant_id="tenant_1",
            drill_type="full_trace",
        )

        history = get_recall_history("tenant_1")

        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_get_recall_readiness_function(self):
        """Test convenience function for readiness report."""
        report = get_recall_readiness("tenant_1")

        assert "tenant_id" in report
        assert "sla_compliance" in report
        assert "recommendations" in report


# ============================================================================
# AFFECTED FACILITY TESTS
# ============================================================================


class TestAffectedFacility:
    """Tests for AffectedFacility dataclass."""

    def test_facility_creation(self):
        """Test basic facility creation."""
        facility = AffectedFacility(
            gln="1234567890123",
            name="Test Processor",
            facility_type="processor",
            lots_affected=["LOT-001", "LOT-002"],
            quantity_affected=100.0,
        )

        assert facility.gln == "1234567890123"
        assert facility.name == "Test Processor"
        assert len(facility.lots_affected) == 2
        assert facility.quantity_affected == 100.0

    def test_facility_default_values(self):
        """Test facility default values."""
        facility = AffectedFacility(
            gln="1234567890123",
            name="Test",
            facility_type="distributor",
            lots_affected=[],
            quantity_affected=0.0,
        )

        assert facility.unit_of_measure == "cases"
        assert facility.contact_info is None
        assert facility.notification_status == "pending"


# ============================================================================
# SCHEDULED DRILL TESTS
# ============================================================================


class TestScheduledDrill:
    """Tests for ScheduledDrill dataclass."""

    def test_scheduled_drill_creation(self):
        """Test basic scheduled drill creation."""
        schedule = ScheduledDrill(
            schedule_id="sched_test123",
            tenant_id="tenant_1",
            drill_type=RecallType.FULL_TRACE,
            severity=RecallSeverity.CLASS_II,
            frequency_days=90,
            next_run=datetime.utcnow() + timedelta(days=90),
        )

        assert schedule.schedule_id == "sched_test123"
        assert schedule.frequency_days == 90
        assert schedule.enabled is True

    def test_scheduled_drill_to_dict(self):
        """Test schedule serialization."""
        schedule = ScheduledDrill(
            schedule_id="sched_test123",
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_I,
            frequency_days=30,
            next_run=datetime(2024, 3, 15, 10, 0, 0),
            target_strategy="rotating",
        )

        data = schedule.to_dict()

        assert data["schedule_id"] == "sched_test123"
        assert data["drill_type"] == "forward_trace"
        assert data["severity"] == "class_i"
        assert data["frequency_days"] == 30
        assert data["target_strategy"] == "rotating"
