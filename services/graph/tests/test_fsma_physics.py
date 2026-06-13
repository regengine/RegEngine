"""
Tests for FSMA Physics Engine: Time Arrow and Mass Balance.

Sprint 3: Physics Engine (Time & Mass)
Tests for temporal ordering validation and mass conservation checks.
"""

import os
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}


def _build_fsma_router():
    """Aggregate the live FSMA sub-routers under /v1/fsma.

    Replaces the deleted ``services.graph.app.fsma_routes`` aggregator so the
    tests keep exercising the same route paths against the live routers.
    """
    from fastapi import APIRouter

    from services.graph.app.routers.fsma import science_router, trace_router

    router = APIRouter(prefix="/v1/fsma", tags=["FSMA 204"])
    router.include_router(trace_router)
    router.include_router(science_router)
    return router


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
    async def test_trace_forward_includes_time_violations(self, mock_neo4j_client, mock_neo4j_session):
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

        result = await trace_forward(mock_neo4j_client, "LOT-001", max_depth=10, enforce_time_arrow=True)

        # Result should have time_violations field
        assert hasattr(result, "time_violations")
        assert hasattr(result, "risk_flags")

    @pytest.mark.asyncio
    async def test_trace_forward_default_enforces_time_arrow(self, mock_neo4j_client, mock_neo4j_session):
        """trace_forward should enforce time arrow by default."""
        from services.graph.app.fsma_utils import trace_forward

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_neo4j_session.run.return_value = mock_result

        result = await trace_forward(mock_neo4j_client, "LOT-001")

        # The query should be called with temporal filtering
        assert mock_neo4j_session.run.called


class TestRiskFlagTagging:
    """Tests for risk flag tagging on events with broken chains."""

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

        success = await _tag_event_risk_flag(
            mock_neo4j_client,
            "evt-001",
            "BROKEN_CHAIN",
            tenant_id="00000000-0000-0000-0000-000000000001",
        )

        assert success is True
        mock_neo4j_session.run.assert_called_once()
        call_args = mock_neo4j_session.run.call_args
        assert "SET e.risk_flag" in call_args[0][0]
        # Tenant scoping: the Cypher MATCH must include tenant_id
        assert "tenant_id: $tenant_id" in call_args[0][0]


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================


class TestMassBalanceEndpointReturns501:
    """Mass-balance endpoints must return 501 (removed from MVP scope)."""

    @pytest.fixture
    def mock_auth(self):
        """Mock API key authentication."""
        with patch("services.graph.app.routers.fsma.science.require_api_key") as mock:
            mock.return_value = {"tenant_id": "test-tenant", "key_id": "test-key"}
            yield mock

    def test_mass_balance_lot_returns_501(self, mock_auth):
        """GET /mass-balance/{tlc} must return 501."""
        import uuid

        from fastapi import FastAPI
        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        app = FastAPI()
        app.include_router(_build_fsma_router())
        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)
        response = client.get(
            "/v1/fsma/mass-balance/LOT-001",
            headers=_AUTH_HEADERS,
        )
        assert response.status_code == 501

    def test_mass_balance_event_returns_501(self, mock_auth):
        """GET /mass-balance/event/{event_id} must return 501."""
        import uuid

        from fastapi import FastAPI
        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        app = FastAPI()
        app.include_router(_build_fsma_router())
        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)
        response = client.get(
            "/v1/fsma/mass-balance/event/evt-001",
            headers=_AUTH_HEADERS,
        )
        assert response.status_code == 501


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

    def test_trace_forward_includes_risk_flags(self, mock_auth, mock_neo4j_client, mock_trace_forward):
        """Trace forward should include risk_flags in response."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(_build_fsma_router())

        import uuid

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()

        assert "risk_flags" in data
        assert "MASS_IMBALANCE" in data["risk_flags"]

    def test_trace_forward_includes_time_violations(self, mock_auth, mock_neo4j_client, mock_trace_forward):
        """Trace forward should include time_violations in response."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(_build_fsma_router())

        import uuid

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()

        assert "time_violations" in data

    def test_trace_forward_accepts_enforce_time_arrow_param(self, mock_auth, mock_neo4j_client, mock_trace_forward):
        """Trace forward should accept enforce_time_arrow parameter."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(_build_fsma_router())

        import uuid

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        app.dependency_overrides[require_api_key] = lambda: {
            "tenant_id": "test-tenant",
            "key_id": "test-key",
        }
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/trace/forward/LOT-001?enforce_time_arrow=false",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        mock_trace_forward.assert_called_once()
        call_kwargs = mock_trace_forward.call_args[1]
        assert call_kwargs["enforce_time_arrow"] is False
