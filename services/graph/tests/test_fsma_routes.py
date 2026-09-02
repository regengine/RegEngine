"""
Tests for FSMA 204 API Routes.
"""

# Mock shared.auth before importing routes
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}


def _fake_api_key(tenant_id):
    """An APIKey object whose ``tenant_id`` the #2511 reconciliation reads.

    The compliance gap handlers compare ``api_key.tenant_id`` against the
    middleware tenant, so the override must expose a ``.tenant_id``
    attribute (a plain dict would resolve to None and 403).
    """
    from datetime import datetime, timezone

    from shared.auth import APIKey

    return APIKey(
        key_id="test-key",
        key_hash="",
        name="test",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
    )


def _build_fsma_router():
    """Aggregate the live FSMA sub-routers under /v1/fsma.

    Replaces the deleted ``services.graph.app.fsma_routes`` aggregator so the
    tests keep exercising the same route paths against the live routers.
    """
    from fastapi import APIRouter

    from services.graph.app.routers.fsma import (
        compliance_router,
        metrics_router,
        science_router,
        trace_router,
    )

    router = APIRouter(prefix="/v1/fsma", tags=["FSMA 204"])
    router.include_router(trace_router)
    router.include_router(science_router)
    router.include_router(compliance_router)
    router.include_router(metrics_router)
    return router


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client at all route module locations."""
    with (
        patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock_trace,
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient") as mock_comp,
        patch("services.graph.app.routers.fsma.science.Neo4jClient", create=True) as mock_sci,
    ):
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        for m in [mock_trace, mock_comp, mock_sci]:
            m.return_value = mock_instance
            m.get_tenant_database_name.return_value = "test-db"
            m.get_global_database_name.return_value = "test-db"
        yield mock_instance


@pytest.fixture
def mock_trace_forward():
    """Mock trace_forward function."""
    with (
        patch("services.graph.app.routers.fsma.traceability.trace_forward", new_callable=AsyncMock) as mock_t,
        patch("services.graph.app.routers.fsma.compliance.trace_forward", new_callable=AsyncMock) as mock_c,
    ):
        from services.graph.app.fsma_utils import TraceResult

        result = TraceResult(
            lot_id="LOT-2024-001",
            direction="forward",
            facilities=[
                {
                    "gln": "1234567890123",
                    "name": "Fresh Foods Distribution",
                    "address": "123 Warehouse St",
                    "facility_type": "DISTRIBUTOR",
                }
            ],
            events=[
                {
                    "event_id": "evt-001",
                    "type": "SHIPPING",
                    "event_date": "2024-01-15",
                    "confidence": 0.95,
                }
            ],
            lots=[
                {
                    "tlc": "LOT-2024-002",
                    "product_description": "Romaine Lettuce 12ct",
                    "quantity": 50,
                    "unit_of_measure": "cases",
                }
            ],
            total_quantity=50.0,
            query_time_ms=12.5,
            hop_count=2,
            # Physics Engine additions
            time_violations=None,
            risk_flags=None,
        )
        mock_t.return_value = result
        mock_c.return_value = result
        yield mock_t


@pytest.fixture
def mock_trace_backward():
    """Mock trace_backward function."""
    with (
        patch("services.graph.app.routers.fsma.traceability.trace_backward", new_callable=AsyncMock) as mock_t,
        patch("services.graph.app.routers.fsma.compliance.trace_backward", new_callable=AsyncMock) as mock_c,
    ):
        from services.graph.app.fsma_utils import TraceResult

        result = TraceResult(
            lot_id="LOT-2024-002",
            direction="backward",
            facilities=[
                {
                    "gln": "9876543210123",
                    "name": "Organic Farms Inc",
                    "address": "456 Farm Rd",
                    "facility_type": "GROWER",
                }
            ],
            events=[
                {
                    "event_id": "evt-002",
                    "type": "RECEIVING",
                    "event_date": "2024-01-10",
                    "confidence": 0.92,
                }
            ],
            lots=[
                {
                    "tlc": "LOT-2024-001",
                    "product_description": "Raw Lettuce",
                    "quantity": 100,
                    "unit_of_measure": "lbs",
                }
            ],
            total_quantity=100.0,
            query_time_ms=8.3,
            hop_count=1,
            # Physics Engine additions
            time_violations=None,
            risk_flags=None,
        )
        mock_t.return_value = result
        mock_c.return_value = result
        yield mock_t


@pytest.fixture
def mock_find_gaps():
    """Mock find_gaps function."""
    with patch("services.graph.app.routers.fsma.compliance.find_gaps", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {
                "event_id": "evt-003",
                "type": "TRANSFORMATION",
                "event_date": None,
                "document_id": "doc-001",
                "gaps": ["missing_date"],
            }
        ]
        yield mock


@pytest.fixture
def mock_get_lot_timeline():
    """Mock get_lot_timeline function."""
    with patch("services.graph.app.routers.fsma.traceability.get_lot_timeline", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {
                "event_id": "evt-001",
                "type": "RECEIVING",
                "event_date": "2024-01-10",
                "event_time": "08:00:00",
                "confidence": 0.95,
                "facility": {"name": "Warehouse A", "gln": "1111111111111"},
            },
            {
                "event_id": "evt-002",
                "type": "TRANSFORMATION",
                "event_date": "2024-01-11",
                "event_time": "14:30:00",
                "confidence": 0.88,
                "facility": {"name": "Processing Plant", "gln": "2222222222222"},
            },
            {
                "event_id": "evt-003",
                "type": "SHIPPING",
                "event_date": "2024-01-12",
                "event_time": "16:00:00",
                "confidence": 0.92,
                "facility": {"name": "Warehouse A", "gln": "1111111111111"},
            },
        ]
        yield mock


class TestTraceForwardEndpoint:
    """Tests for /v1/fsma/trace/forward/{tlc}"""

    def test_trace_forward_success(self, mock_neo4j_client, mock_trace_forward):
        """Test successful forward trace."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/trace/forward/LOT-2024-001",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-001"
        assert data["direction"] == "forward"
        assert len(data["facilities"]) == 1
        assert data["facilities"][0]["gln"] == "1234567890123"
        assert data["hop_count"] == 2

    def test_trace_forward_with_max_depth(self, mock_neo4j_client, mock_trace_forward):
        """Test forward trace with custom max_depth."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/trace/forward/LOT-2024-001?max_depth=5",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        mock_trace_forward.assert_called_once()


class TestTraceBackwardEndpoint:
    """Tests for /v1/fsma/trace/backward/{tlc}"""

    def test_trace_backward_success(self, mock_neo4j_client, mock_trace_backward):
        """Test successful backward trace."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/trace/backward/LOT-2024-002",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-002"
        assert data["direction"] == "backward"
        assert len(data["source_lots"]) == 1


class TestTimelineEndpoint:
    """Tests for /v1/fsma/timeline/{tlc}"""

    def test_timeline_success(self, mock_neo4j_client, mock_get_lot_timeline):
        """Test lot timeline retrieval."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/timeline/LOT-2024-001",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "LOT-2024-001"
        assert len(data["events"]) == 3
        # Events should be in chronological order
        dates = [e["event_date"] for e in data["events"]]
        assert dates == sorted(dates)


class TestExportEndpoints:
    """Tests for CSV export endpoints."""

    def test_export_trace_csv(self, mock_neo4j_client, mock_trace_forward):
        """Test trace CSV export."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/export/trace/LOT-2024-001?direction=forward",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "fsma_trace_forward_LOT-2024-001" in response.headers["content-disposition"]

        # Verify CSV content
        content = response.content.decode("utf-8")
        lines = content.strip().split("\n")
        assert len(lines) >= 1  # At least header
        assert "Traceability Lot Code" in lines[0]

    def test_export_trace_csv_is_not_a_cartesian_product(self, mock_neo4j_client):
        """#2945: the route must emit one row per observed association.

        The old inline writer nested ``for event in result.events`` inside
        ``for lot in result.lots`` with no join key (2 lots x 3 events = 6
        rows) and stamped the first GLN-bearing facility on every row. This
        pins the route to ``build_trace_csv_rows`` so the wiring cannot
        regress independently of the exporter's own unit tests.
        """
        import csv as csv_mod
        import io
        import uuid

        from fastapi import FastAPI
        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        from services.graph.app.fsma_utils import TraceResult

        fac_pack = {"gln": "0614141000005", "name": "Packhouse", "address": "1 Grower Way"}
        fac_dc = {"gln": "0614141000029", "name": "Regional DC", "address": "9 Dock St"}
        lot_a = {"tlc": "LOT-A", "product_description": "Romaine", "quantity": 40, "unit_of_measure": "cases"}
        lot_b = {"tlc": "LOT-B", "product_description": "Spinach", "quantity": 18, "unit_of_measure": "cases"}
        evt_1 = {"event_id": "evt-1", "type": "HARVESTING", "event_date": "2026-03-01", "confidence": 0.97}
        evt_2 = {"event_id": "evt-2", "type": "SHIPPING", "event_date": "2026-03-04", "confidence": 0.91}
        evt_3 = {"event_id": "evt-3", "type": "RECEIVING", "event_date": "2026-03-06", "confidence": 0.88}

        result = TraceResult(
            lot_id="LOT-A",
            direction="forward",
            facilities=[fac_pack, fac_dc],
            events=[evt_1, evt_2, evt_3],
            lots=[lot_a, lot_b],
            total_quantity=58.0,
            query_time_ms=2.0,
            hop_count=4,
            trace_rows=[
                {"lot": lot_a, "event": evt_1, "facility": fac_pack},
                {"lot": lot_a, "event": evt_2, "facility": fac_pack},
                {"lot": lot_b, "event": evt_3, "facility": fac_dc},
            ],
        )

        with patch(
            "services.graph.app.routers.fsma.compliance.trace_forward",
            new_callable=AsyncMock,
            return_value=result,
        ):
            app = FastAPI()
            app.include_router(_build_fsma_router())
            app.dependency_overrides[require_api_key] = lambda: {
                "tenant_id": "test-tenant",
                "key_id": "test-key",
            }
            app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")
            client = TestClient(app)

            response = client.get(
                "/v1/fsma/export/trace/LOT-A?direction=forward",
                headers=_AUTH_HEADERS,
            )

        assert response.status_code == 200
        reader = csv_mod.reader(io.StringIO(response.content.decode("utf-8-sig")))
        rows = [row for row in reader if row]
        header, data_rows = rows[0], rows[1:]

        assert len(data_rows) == 3, (
            f"#2945: 2 lots x 3 events must produce 3 association rows, not a "
            f"6-row cartesian product. Got {len(data_rows)}: {data_rows!r}"
        )

        tlc_idx = header.index("Traceability Lot Code (TLC)")
        type_idx = header.index("Event Type")
        gln_idx = header.index("Facility GLN")
        emitted = {(r[tlc_idx], r[type_idx], r[gln_idx]) for r in data_rows}
        assert emitted == {
            ("LOT-A", "HARVESTING", "0614141000005"),
            ("LOT-A", "SHIPPING", "0614141000005"),
            ("LOT-B", "RECEIVING", "0614141000029"),
        }, f"#2945: fabricated lot/event/facility associations in FDA CSV: {sorted(emitted)}"

    def test_export_recall_contacts(self, mock_neo4j_client, mock_trace_forward):
        """Test recall contacts CSV export."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

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
            "/v1/fsma/export/recall-contacts/LOT-2024-001",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "recall_contacts" in response.headers["content-disposition"]

        content = response.content.decode("utf-8")
        assert "Facility Name" in content
        assert "Global Location Number" in content


class TestGapAnalysisEndpoints:
    """Tests for gap analysis endpoints."""

    def test_get_gaps(self, mock_neo4j_client, mock_find_gaps):
        """Test gap analysis retrieval."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

        import uuid

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        # #2511: the gap handlers reconcile the api_key tenant against the
        # middleware tenant. Override with an APIKey object whose tenant
        # matches the middleware tenant (the agreement case).
        app.dependency_overrides[require_api_key] = lambda: _fake_api_key("00000000-0000-0000-0000-000000000001")
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/gaps",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_gaps"] == 1
        assert data["summary"]["missing_date"] == 1

    def test_export_gaps_csv(self, mock_neo4j_client, mock_find_gaps):
        """Test gaps CSV export."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)

        import uuid

        from shared.auth import require_api_key
        from shared.middleware import get_current_tenant_id

        # #2511: see test_get_gaps — api_key tenant must match middleware.
        app.dependency_overrides[require_api_key] = lambda: _fake_api_key("00000000-0000-0000-0000-000000000001")
        app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

        client = TestClient(app)

        response = client.get(
            "/v1/fsma/export/gaps",
            headers=_AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

        content = response.content.decode("utf-8")
        assert "Event ID" in content
        assert "Missing Fields" in content


class TestHealthEndpoint:
    """Tests for FSMA health endpoint."""

    def test_health(self):
        """Test FSMA health endpoint (no auth required)."""
        from fastapi import FastAPI

        fsma_router = _build_fsma_router()

        app = FastAPI()
        app.include_router(fsma_router)
        client = TestClient(app)

        response = client.get("/v1/fsma/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["module"] == "fsma-204"
