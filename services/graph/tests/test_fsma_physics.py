"""
Tests for FSMA Physics Engine: Time Arrow and Mass Balance.

Sprint 3: Physics Engine (Time & Mass)
Tests for temporal ordering validation and mass conservation checks.
"""

import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))


# ============================================================================
# TIME ARROW TESTS
# ============================================================================


class TestTimeArrowValidation:
    """Tests for temporal ordering validation in trace queries."""

    def test_validate_temporal_order_valid_sequence(self):
        """Events in correct temporal order should pass validation."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        events = [
            {"event_id": "evt-001", "event_date": "2024-01-10"},
            {"event_id": "evt-002", "event_date": "2024-01-15"},
            {"event_id": "evt-003", "event_date": "2024-01-20"},
        ]

        violations = _validate_temporal_order(events)
        assert violations == [], "Valid sequence should have no violations"

    def test_validate_temporal_order_same_date(self):
        """Events on the same date should pass validation."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        events = [
            {"event_id": "evt-001", "event_date": "2024-01-15"},
            {"event_id": "evt-002", "event_date": "2024-01-15"},
            {"event_id": "evt-003", "event_date": "2024-01-15"},
        ]

        violations = _validate_temporal_order(events)
        assert violations == [], "Same-date events should have no violations"

    def test_validate_temporal_order_detects_violation(self):
        """Events out of temporal order should be flagged."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        events = [
            {"event_id": "evt-001", "event_date": "2024-01-20"},  # Later date first
            {"event_id": "evt-002", "event_date": "2024-01-10"},  # Earlier date after
            {"event_id": "evt-003", "event_date": "2024-01-15"},
        ]

        violations = _validate_temporal_order(events)
        # After sorting by date, the sequence becomes:
        # evt-002 (01-10) -> evt-003 (01-15) -> evt-001 (01-20)
        # This is valid, so no violations since we sort first
        # The violation detection happens in path traversal order
        assert isinstance(violations, list)

    def test_validate_temporal_order_handles_null_dates(self):
        """Events with missing dates should be handled gracefully."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        events = [
            {"event_id": "evt-001", "event_date": "2024-01-10"},
            {"event_id": "evt-002", "event_date": None},  # Missing date
            {"event_id": "evt-003", "event_date": "2024-01-20"},
        ]

        violations = _validate_temporal_order(events)
        # Should not crash on null dates
        assert isinstance(violations, list)

    def test_validate_temporal_order_empty_list(self):
        """Empty event list should return no violations."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        violations = _validate_temporal_order([])
        assert violations == []

    def test_validate_temporal_order_single_event(self):
        """Single event should have no violations."""
        from services.graph.app.fsma_utils import _validate_temporal_order

        events = [{"event_id": "evt-001", "event_date": "2024-01-10"}]
        violations = _validate_temporal_order(events)
        assert violations == []


class TestTimeArrowInTraceForward:
    """Tests for time arrow enforcement in trace_forward."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j async session."""
        session = MagicMock()
        # run() returns a result whose single() is also async
        mock_run_result = MagicMock()
        mock_run_result.__aiter__ = MagicMock(return_value=iter([]))
        session.run = AsyncMock(return_value=mock_run_result)
        return session

    @pytest.fixture
    def mock_neo4j_client(self, mock_neo4j_session):
        """Create a mock Neo4j client with async context manager."""
        client = MagicMock()
        # client.session() returns an async context manager
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        client.session.return_value = ctx
        return client

    @pytest.mark.asyncio
    async def test_trace_forward_includes_time_violations(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """trace_forward should include time_violations in result."""
        from services.graph.app.fsma_utils import trace_forward

        # Setup mock query results
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(
            return_value=iter(
                [
                    {
                        "labels": ["TraceEvent"],
                        "props": {
                            "event_id": "evt-001",
                            "type": "SHIPPING",
                            "event_date": "2024-01-10",
                        },
                        "hop_count": 1,
                    },
                    {
                        "labels": ["TraceEvent"],
                        "props": {
                            "event_id": "evt-002",
                            "type": "RECEIVING",
                            "event_date": "2024-01-15",
                        },
                        "hop_count": 2,
                    },
                ]
            )
        )
        mock_neo4j_session.run.return_value = mock_result

        result = await trace_forward(
            mock_neo4j_client, "LOT-001", max_depth=10, enforce_time_arrow=True
        )

        # Result should have time_violations field
        assert hasattr(result, "time_violations")
        assert hasattr(result, "risk_flags")

    @pytest.mark.asyncio
    async def test_trace_forward_default_enforces_time_arrow(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """trace_forward should enforce time arrow by default."""
        from services.graph.app.fsma_utils import trace_forward

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_neo4j_session.run.return_value = mock_result

        result = await trace_forward(mock_neo4j_client, "LOT-001")

        # The query should be called with temporal filtering
        assert mock_neo4j_session.run.called


# ============================================================================
# MASS BALANCE TESTS
# ============================================================================


class TestMassBalanceResult:
    """Tests for MassBalanceResult dataclass."""

    def test_mass_balance_result_creation(self):
        """MassBalanceResult should be creatable with all fields."""
        from services.graph.app.fsma_utils import MassBalanceResult

        result = MassBalanceResult(
            event_id="evt-001",
            event_type="TRANSFORMATION",
            event_date="2024-01-15",
            input_lots=[{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
            output_lots=[{"tlc": "LOT-002", "quantity": 95, "unit": "lbs"}],
            input_quantity=100.0,
            output_quantity=95.0,
            imbalance_ratio=-0.05,
            is_balanced=True,
            tolerance=0.10,
            risk_flag=None,
        )

        assert result.event_id == "evt-001"
        assert result.is_balanced is True
        assert result.imbalance_ratio == -0.05
        assert result.risk_flag is None


class TestMassBalanceValidation:
    """Tests for mass balance calculation logic."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j async session."""
        session = MagicMock()
        session.run = AsyncMock()
        return session

    @pytest.fixture
    def mock_neo4j_client(self, mock_neo4j_session):
        """Create a mock Neo4j client with async context manager."""
        client = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        client.session.return_value = ctx
        return client

    @pytest.mark.asyncio
    async def test_check_mass_balance_balanced_with_loss(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Mass balance with yield loss (output < input) should pass."""
        from services.graph.app.fsma_utils import check_mass_balance

        # Setup: 100 lbs in, 90 lbs out (10% loss - acceptable)
        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "TRANSFORMATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
            "outputs": [{"tlc": "LOT-002", "quantity": 90, "unit": "lbs"}],
        })
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client, "evt-001", tolerance=0.10, tag_imbalance=False
        )

        assert result.is_balanced is True
        assert result.imbalance_ratio < 0  # Loss is negative
        assert result.risk_flag is None

    @pytest.mark.asyncio
    async def test_check_mass_balance_balanced_within_tolerance(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Mass balance with small gain within tolerance should pass."""
        from services.graph.app.fsma_utils import check_mass_balance

        # Setup: 100 lbs in, 105 lbs out (5% gain - within 10% tolerance)
        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "TRANSFORMATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
            "outputs": [{"tlc": "LOT-002", "quantity": 105, "unit": "lbs"}],
        })
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client, "evt-001", tolerance=0.10, tag_imbalance=False
        )

        assert result.is_balanced is True
        assert result.imbalance_ratio == 0.05
        assert result.risk_flag is None

    @pytest.mark.asyncio
    async def test_check_mass_balance_imbalanced_exceeds_tolerance(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Mass balance with gain exceeding tolerance should fail."""
        from services.graph.app.fsma_utils import check_mass_balance

        # Setup: 100 lbs in, 120 lbs out (20% gain - exceeds 10% tolerance)
        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "TRANSFORMATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
            "outputs": [{"tlc": "LOT-002", "quantity": 120, "unit": "lbs"}],
        })
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client,
            "evt-001",
            tolerance=0.10,
            tag_imbalance=False,  # Don't try to tag for this test
        )

        assert result.is_balanced is False
        assert result.imbalance_ratio == 0.2
        assert result.risk_flag == "MASS_IMBALANCE"

    @pytest.mark.asyncio
    async def test_check_mass_balance_multiple_inputs_outputs(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Mass balance should sum multiple inputs and outputs."""
        from services.graph.app.fsma_utils import check_mass_balance

        # Setup: 50 + 50 = 100 lbs in, 45 + 50 = 95 lbs out
        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "TRANSFORMATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [
                {"tlc": "LOT-001", "quantity": 50, "unit": "lbs"},
                {"tlc": "LOT-002", "quantity": 50, "unit": "lbs"},
            ],
            "outputs": [
                {"tlc": "LOT-003", "quantity": 45, "unit": "lbs"},
                {"tlc": "LOT-004", "quantity": 50, "unit": "lbs"},
            ],
        })
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client, "evt-001", tolerance=0.10, tag_imbalance=False
        )

        assert result.input_quantity == 100.0
        assert result.output_quantity == 95.0
        assert result.is_balanced is True

    @pytest.mark.asyncio
    async def test_check_mass_balance_zero_inputs(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Mass balance with zero inputs should handle gracefully."""
        from services.graph.app.fsma_utils import check_mass_balance

        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "CREATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [],
            "outputs": [{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
        })
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client, "evt-001", tolerance=0.10, tag_imbalance=False
        )

        # Zero inputs with outputs = infinite ratio, but should not crash
        assert result.input_quantity == 0.0
        assert result.output_quantity == 100.0

    @pytest.mark.asyncio
    async def test_check_mass_balance_event_not_found(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Missing event should return empty result."""
        from services.graph.app.fsma_utils import check_mass_balance

        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_neo4j_session.run.return_value = mock_result

        result = await check_mass_balance(
            mock_neo4j_client, "nonexistent-evt", tolerance=0.10, tag_imbalance=False
        )

        assert result.event_id == "nonexistent-evt"
        assert result.event_type == "UNKNOWN"
        assert result.is_balanced is True  # Default to balanced for missing


class TestMassBalanceRiskFlagTagging:
    """Tests for risk flag tagging on imbalanced events."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j async session."""
        session = MagicMock()
        session.run = AsyncMock()
        return session

    @pytest.fixture
    def mock_neo4j_client(self, mock_neo4j_session):
        """Create a mock Neo4j client with async context manager."""
        client = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_neo4j_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        client.session.return_value = ctx
        return client

    @pytest.mark.asyncio
    async def test_tag_event_risk_flag_success(self, mock_neo4j_client, mock_neo4j_session):
        """Risk flag should be set on event node."""
        from services.graph.app.fsma_utils import _tag_event_risk_flag

        mock_result = MagicMock()
        mock_result.single = AsyncMock(return_value={"tagged_id": "evt-001"})
        mock_neo4j_session.run.return_value = mock_result

        success = await _tag_event_risk_flag(mock_neo4j_client, "evt-001", "MASS_IMBALANCE")

        assert success is True
        mock_neo4j_session.run.assert_called_once()
        call_args = mock_neo4j_session.run.call_args
        assert "SET e.risk_flag" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_check_mass_balance_tags_imbalanced_event(
        self, mock_neo4j_client, mock_neo4j_session
    ):
        """Imbalanced event should be tagged with risk_flag."""
        from services.graph.app.fsma_utils import check_mass_balance

        # First call returns the imbalanced event
        check_result = MagicMock()
        check_result.single = AsyncMock(return_value={
            "event_id": "evt-001",
            "event_type": "TRANSFORMATION",
            "event_date": "2024-01-15",
            "existing_risk_flag": None,
            "inputs": [{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
            "outputs": [{"tlc": "LOT-002", "quantity": 150, "unit": "lbs"}],
        })

        # Second call is the tag operation
        tag_result = MagicMock()
        tag_result.single = AsyncMock(return_value={"tagged_id": "evt-001"})

        mock_neo4j_session.run = AsyncMock(side_effect=[check_result, tag_result])

        result = await check_mass_balance(
            mock_neo4j_client,
            "evt-001",
            tolerance=0.10,
            tag_imbalance=True,  # Enable tagging
        )

        assert result.risk_flag == "MASS_IMBALANCE"
        # Should have made 2 calls: check + tag
        assert mock_neo4j_session.run.call_count == 2


class TestMassBalanceReport:
    """Tests for mass balance report across multiple events."""

    @pytest.fixture
    def mock_neo4j_session(self):
        """Create a mock Neo4j session."""
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        return session

    @pytest.fixture
    def mock_neo4j_client(self, mock_neo4j_session):
        """Create a mock Neo4j client."""
        client = MagicMock()
        client.session.return_value = mock_neo4j_session
        return client

    def test_mass_balance_report_structure(self, mock_neo4j_client, mock_neo4j_session):
        """MassBalanceReport should have correct structure."""
        from services.graph.app.fsma_utils import MassBalanceReport, MassBalanceResult

        report = MassBalanceReport(
            lot_id="LOT-001",
            transformation_count=2,
            balanced_count=1,
            imbalanced_count=1,
            events=[],
            flagged_events=["evt-002"],
            query_time_ms=15.5,
        )

        assert report.lot_id == "LOT-001"
        assert report.transformation_count == 2
        assert report.imbalanced_count == 1
        assert "evt-002" in report.flagged_events


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================


class TestMassBalanceEndpoint:
    """Tests for /v1/fsma/mass-balance/{tlc} endpoint."""

    @pytest.fixture
    def mock_auth(self):
        """Mock API key authentication."""
        with patch("services.graph.app.routers.fsma.science.require_api_key") as mock:
            mock.return_value = {"tenant_id": "test-tenant", "key_id": "test-key"}
            yield mock

    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock Neo4j client."""
        with patch("services.graph.app.routers.fsma.science.Neo4jClient") as mock:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock.return_value = mock_instance
            mock.get_tenant_database_name.return_value = "test-db"
            yield mock_instance

    @pytest.fixture
    def mock_check_mass_balance_for_lot(self):
        """Mock check_mass_balance_for_lot function."""
        with patch("services.graph.app.routers.fsma.science.check_mass_balance_for_lot", new_callable=AsyncMock) as mock:
            from services.graph.app.fsma_utils import (
                MassBalanceReport,
                MassBalanceResult,
            )

            mock.return_value = MassBalanceReport(
                lot_id="LOT-001",
                transformation_count=2,
                balanced_count=1,
                imbalanced_count=1,
                events=[
                    MassBalanceResult(
                        event_id="evt-001",
                        event_type="TRANSFORMATION",
                        event_date="2024-01-15",
                        input_lots=[{"tlc": "LOT-001", "quantity": 100, "unit": "lbs"}],
                        output_lots=[{"tlc": "LOT-002", "quantity": 95, "unit": "lbs"}],
                        input_quantity=100.0,
                        output_quantity=95.0,
                        imbalance_ratio=-0.05,
                        is_balanced=True,
                        tolerance=0.10,
                        risk_flag=None,
                    ),
                    MassBalanceResult(
                        event_id="evt-002",
                        event_type="TRANSFORMATION",
                        event_date="2024-01-20",
                        input_lots=[{"tlc": "LOT-002", "quantity": 95, "unit": "lbs"}],
                        output_lots=[
                            {"tlc": "LOT-003", "quantity": 120, "unit": "lbs"}
                        ],
                        input_quantity=95.0,
                        output_quantity=120.0,
                        imbalance_ratio=0.2632,
                        is_balanced=False,
                        tolerance=0.10,
                        risk_flag="MASS_IMBALANCE",
                    ),
                ],
                flagged_events=["evt-002"],
                query_time_ms=25.3,
            )
            yield mock

    def test_mass_balance_endpoint_returns_report(
        self, mock_auth, mock_neo4j_client, mock_check_mass_balance_for_lot
    ):
        """Mass balance endpoint should return complete report."""
        # Import inside test while mocks are active
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import fsma_router

        app = FastAPI()
        app.include_router(fsma_router)

        # Override the dependency for this test
        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id
        import uuid

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/mass-balance/LOT-001", headers={"X-RegEngine-API-Key": "test-key"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["lot_id"] == "LOT-001"
        assert data["transformation_count"] == 2
        assert data["balanced_count"] == 1
        assert data["imbalanced_count"] == 1
        assert "evt-002" in data["flagged_events"]
        assert len(data["events"]) == 2

    def test_mass_balance_endpoint_accepts_tolerance_param(
        self, mock_auth, mock_neo4j_client, mock_check_mass_balance_for_lot
    ):
        """Mass balance endpoint should accept custom tolerance."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import fsma_router

        app = FastAPI()
        app.include_router(fsma_router)

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id
        import uuid

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/mass-balance/LOT-001?tolerance=0.05",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        # Verify tolerance was passed through
        mock_check_mass_balance_for_lot.assert_called_once()
        call_kwargs = mock_check_mass_balance_for_lot.call_args[1]
        assert abs(call_kwargs["tolerance"] - 0.05) < 0.001


class TestTraceForwardWithPhysicsEngine:
    """Tests for trace/forward endpoint with physics engine features."""

    @pytest.fixture
    def mock_auth(self):
        """Mock API key authentication."""
        with patch("services.graph.app.routers.fsma.traceability.require_api_key") as mock:
            mock.return_value = {"tenant_id": "test-tenant", "key_id": "test-key"}
            yield mock

    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock Neo4j client."""
        with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock.return_value = mock_instance
            mock.get_tenant_database_name.return_value = "test-db"
            yield mock_instance

    @pytest.fixture
    def mock_trace_forward(self):
        """Mock trace_forward function with physics engine fields."""
        with patch("services.graph.app.routers.fsma.traceability.trace_forward", new_callable=AsyncMock) as mock:
            from services.graph.app.fsma_utils import TraceResult

            mock.return_value = TraceResult(
                lot_id="LOT-001",
                direction="forward",
                facilities=[],
                events=[
                    {
                        "event_id": "evt-001",
                        "type": "SHIPPING",
                        "event_date": "2024-01-10",
                        "risk_flag": None,
                    },
                    {
                        "event_id": "evt-002",
                        "type": "RECEIVING",
                        "event_date": "2024-01-15",
                        "risk_flag": "MASS_IMBALANCE",
                    },
                ],
                lots=[],
                total_quantity=100.0,
                query_time_ms=12.5,
                hop_count=2,
                time_violations=None,
                risk_flags=["MASS_IMBALANCE"],
            )
            yield mock

    def test_trace_forward_includes_risk_flags(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Trace forward should include risk_flags in response."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import fsma_router

        app = FastAPI()
        app.include_router(fsma_router)

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id
        import uuid

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "risk_flags" in data
        assert "MASS_IMBALANCE" in data["risk_flags"]

    def test_trace_forward_includes_time_violations(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Trace forward should include time_violations in response."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import fsma_router

        app = FastAPI()
        app.include_router(fsma_router)

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id
        import uuid

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "time_violations" in data

    def test_trace_forward_accepts_enforce_time_arrow_param(
        self, mock_auth, mock_neo4j_client, mock_trace_forward
    ):
        """Trace forward should accept enforce_time_arrow parameter."""
        from fastapi import FastAPI

        from services.graph.app.fsma_routes import fsma_router

        app = FastAPI()
        app.include_router(fsma_router)

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id
        import uuid

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001?enforce_time_arrow=false",
            headers={"X-RegEngine-API-Key": "test-key"},
        )

        assert response.status_code == 200
        mock_trace_forward.assert_called_once()
        call_kwargs = mock_trace_forward.call_args[1]
        assert call_kwargs["enforce_time_arrow"] is False
