"""QA5 deep-pass regression tests for services/graph/app/routers/.

Each test below fails on the pre-fix code and passes after the fix.
They cover real behavior at auth, tenant and error boundaries that the
existing suite only exercised with dict-shaped auth doubles.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_A_STR = str(TENANT_A)

_AUTH_HEADERS = {"X-RegEngine-API-Key": "test-key"}


def _real_api_key():
    """Build the same principal production auth returns (a model, no .get)."""
    from shared.auth import APIKey

    return APIKey(
        key_id="key-real-123",
        key_hash="deadbeef",
        name="QA key",
        tenant_id=TENANT_A_STR,
        created_at=datetime.now(timezone.utc),
    )


# ── 1. POST /fsma/recall/drill with a real APIKey principal ────────────────


class _FakeRecallEngine:
    """Minimal engine double: create/execute/get without touching Neo4j."""

    def __init__(self):
        from services.graph.app.fsma_recall import RecallDrill, RecallSeverity, RecallType

        self._drill = RecallDrill(
            drill_id="drill_qa50000001",
            tenant_id=TENANT_A_STR,
            created_at=datetime.now(timezone.utc),
            drill_type=RecallType.FORWARD_TRACE,
            severity=RecallSeverity.CLASS_II,
        )
        self.created_kwargs: dict = {}

    def create_drill(self, **kwargs):
        from services.graph.app.fsma_recall import RecallDrill

        self.created_kwargs = kwargs
        self._drill.initiated_by = kwargs.get("initiated_by", "system")
        self._drill.tenant_id = kwargs.get("tenant_id", TENANT_A_STR)
        return self._drill

    async def execute_drill(self, drill):
        from services.graph.app.fsma_recall import RecallStatus

        drill.status = RecallStatus.COMPLETED
        drill.started_at = datetime.now(timezone.utc)
        drill.completed_at = datetime.now(timezone.utc)
        return MagicMock()

    def get_drill(self, tenant_id, drill_id):
        return self._drill


def test_create_drill_with_real_apikey_principal():
    """Real principals are APIKey models (no .get): drill creation must not 500."""
    from services.graph.app.routers.fsma import recall as recall_router

    engine = _FakeRecallEngine()
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(recall_router.router)
    app.dependency_overrides[require_api_key] = _real_api_key
    app.dependency_overrides[get_current_tenant_id] = lambda: TENANT_A
    with patch.object(recall_router, "get_recall_engine", return_value=engine):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/drill",
            json={"type": "forward_trace", "severity": "class_ii", "reason": "qa_probe"},
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert engine.created_kwargs.get("initiated_by") == "key-real-123"


def test_drill_history_negative_limit_rejected():
    """limit=-3 must be a 422, not a silently truncated history page."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id

    from services.graph.app.routers.fsma import recall as recall_router

    engine = _FakeRecallEngine()
    engine_get_history = MagicMock(return_value=[])
    engine.get_drill_history = engine_get_history

    app = FastAPI()
    app.include_router(recall_router.router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": TENANT_A_STR}
    app.dependency_overrides[get_current_tenant_id] = lambda: TENANT_A
    with patch.object(recall_router, "get_recall_engine", return_value=engine):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/history?limit=-3", headers=_AUTH_HEADERS)
    assert response.status_code == 422, response.text
    engine_get_history.assert_not_called()


# ── 2. GET /fsma/compliance/score must query the tenant database ───────────


def _make_request(path="/fsma/compliance/score"):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "path": path,
        "query_string": b"",
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": MagicMock(state=MagicMock()),
    }
    return Request(scope)


async def test_compliance_score_uses_tenant_database():
    """The score query must run against reg_tenant_<uuid>, not the global DB."""
    from services.graph.app.routers.fsma import compliance as compliance_router

    constructed = {}

    class _FakeResult:
        async def single(self):
            # covered_obligations: the score query returns it since #3273.
            return {
                "total_obligations": 4,
                "controls_mapped": 2,
                "evidence_items": 0,
                "avg_effectiveness": 0.9,
                "covered_obligations": 2,
                "fresh_evidence": 0,
            }

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def run(self, query, **params):
            return _FakeResult()

    class _FakeClient:
        @staticmethod
        def get_tenant_database_name(tenant_id):
            return f"reg_tenant_{tenant_id}"

        def __init__(self, database=None):
            constructed["database"] = database

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def session(self):
            return _FakeSession()

    with patch.object(compliance_router, "Neo4jClient", _FakeClient):
        response = await compliance_router.get_compliance_score(
            request=_make_request(),
            tenant_id=TENANT_A,
            api_key={"tenant_id": TENANT_A_STR},
        )
    assert constructed["database"] == f"reg_tenant_{TENANT_A}"
    assert response.total_obligations == 4
    assert response.controls_mapped == 2


# ── 3. POST /regulations/harmonize must close the engine on failure ────────


async def test_harmonize_closes_engine_when_mapping_fails():
    """A mapping failure must still close the driver and surface a 503."""
    from fastapi import HTTPException

    from services.graph.app.routers import regulations as regulations_router

    fake_engine = MagicMock()
    fake_engine.map_requirement = AsyncMock(side_effect=RuntimeError("llm down"))
    fake_engine.close = AsyncMock()

    with patch(
        "services.graph.app.mapping_engine.MappingEngine",
        return_value=fake_engine,
    ):
        try:
            # harmonize reconciles the middleware tenant with the API-key
            # tenant first (#3316), so the principal must carry TENANT_A.
            await regulations_router.harmonize_requirement(
                request=_make_request("/regulations/harmonize/obl-1"),
                obligation_id="obl-1",
                api_key=_real_api_key(),
                tenant_id=TENANT_A,
            )
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("expected HTTPException 503")
    fake_engine.close.assert_awaited_once()


# ── 4. Lineage fallback query must scope the previous version to the tenant ─


def _lineage_session_mock(records_per_call, queries_seen):
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    calls = list(records_per_call)

    async def _run(query, **kwargs):
        queries_seen.append(query)

        async def _aiter(self):
            for record in calls.pop(0):
                yield record

        result = MagicMock()
        result.__aiter__ = _aiter
        return result

    mock_session.run = AsyncMock(side_effect=_run)
    return mock_session


def test_lineage_fallback_scopes_previous_version_to_tenant():
    """The TLC fallback lookup must not match a cross-tenant SUPERSEDES node."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id

    from services.graph.app.routes import router as graph_router

    queries_seen = []
    fallback_row = {
        "tlc": "TLC-X",
        "version": 2,
        "record_hash": "h2",
        "prev_hash": "h1",
        "created_at": "2026-01-02",
        "superseded_at": None,
        "source_document": "doc",
        "fact_type": "KDE",
        "is_current": True,
        "superseded_by": "TLC-OTHER-TENANT",
        "all_props": {"tenant_id": TENANT_A_STR},
    }
    mock_session = _lineage_session_mock([[], [fallback_row]], queries_seen)
    mock_client = MagicMock()
    mock_client.session = MagicMock(return_value=mock_session)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls = MagicMock(return_value=mock_client)
    mock_client_cls.get_tenant_database_name = MagicMock(return_value="reg_tenant_test")

    app = FastAPI()
    app.include_router(graph_router, prefix="/api/v1")
    app.dependency_overrides[require_api_key] = lambda: {
        "tenant_id": TENANT_A_STR,
        "key_id": "test-key",
    }
    app.dependency_overrides[get_current_tenant_id] = lambda: TENANT_A
    with patch(
        "services.graph.app.routers.lineage_traversal.Neo4jClient",
        mock_client_cls,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/lineage/TLC-X/history", headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.text
    assert len(queries_seen) == 2
    fallback_query = queries_seen[1]
    assert "prev.tenant_id" in fallback_query
    assert "$tenant_id" in fallback_query


# ── 5. Mobile bridge: canonical-store failure must not fail the capture ────


def _mobile_app():
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")
    return app


def _mobile_payload():
    return {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "TLC-2024-001",
        "location_identifier": "0614141000036",
        "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
        "product_description": "Green Spinach 10oz",
        "gtin": "10614141000019",
        "quantity": 24,
        "uom": "cases",
    }


def test_mobile_capture_succeeds_when_canonical_store_is_down():
    """The Neo4j write already succeeded: a Postgres outage must not 500 the capture."""
    from services.graph.app.routers.fsma import traceability as trace_router

    with patch.object(trace_router, "Neo4jClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.session.return_value.__aenter__.return_value.run = AsyncMock()
        mock_cls.return_value = mock_instance
        mock_cls.get_tenant_database_name.return_value = "test-db"
        with (
            patch("services.graph.app.routers.fsma.traceability.validate_tlc") as mock_tlc,
            patch("services.graph.app.routers.fsma.traceability.validate_gln") as mock_gln,
            patch("services.graph.app.routers.fsma.traceability.validate_gtin") as mock_gtin,
            patch("shared.database.SessionLocal", side_effect=RuntimeError("postgres down")),
        ):
            mock_tlc.return_value = MagicMock(is_valid=True)
            mock_gln.return_value = MagicMock(is_valid=True)
            mock_gtin.return_value = MagicMock(is_valid=True)
            client = TestClient(_mobile_app(), raise_server_exceptions=False)
            response = client.post("/event", json=_mobile_payload(), headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"


# ── 6. Labels batch/init must reject an invalid packer GLN before Neo4j ────


@pytest.mark.parametrize(
    ("packer_gln", "expected_status"),
    [
        # Not 13 digits: the LabelBatchInitRequest validator (#3360) rejects
        # it at the request boundary with FastAPI's 422.
        ("NOT-A-GLN", 422),
        # 13 digits with a bad GS1 check digit passes the shape check and is
        # rejected by the handler's validate_gln (#3272) with a 400.
        ("0614141000013", 400),
    ],
)
def test_labels_batch_rejects_invalid_packer_gln(packer_gln, expected_status):
    """An invalid packer GLN is a 4xx before Neo4j, not a 500 from SSCC generation."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id

    from services.graph.app.routers import labels as labels_router

    app = FastAPI()
    app.include_router(labels_router.router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": TENANT_A_STR}
    app.dependency_overrides[get_current_tenant_id] = lambda: TENANT_A
    with patch.object(labels_router, "Neo4jClient") as mock_cls:
        mock_cls.get_tenant_database_name.return_value = "test-db"
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/batch/init",
            json={
                "packer_gln": packer_gln,
                "product": {
                    "gtin": "00000012345678",
                    "description": "Test Product",
                    "expected_units": 1,
                },
                "traceability": {"lot_number": "LOT-TEST-001", "pack_date": "2024-01-01"},
                "quantity": 10,
                "unit_of_measure": "EA",
                "packaging_level": "item",
            },
            headers=_AUTH_HEADERS,
        )
    assert response.status_code == expected_status, response.text
    mock_cls.assert_not_called()
