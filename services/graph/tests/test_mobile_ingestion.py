"""
Tests for Mobile Field Capture CTE Ingestion Endpoint.
"""

import os
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j.exceptions import ClientError

# Add local path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client for persistence tests."""
    with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_instance.session.return_value.__aenter__.return_value.run = AsyncMock()
        mock.return_value = mock_instance
        mock.get_tenant_database_name.return_value = "test-db"
        yield mock_instance


@pytest.fixture
def mock_validation():
    """Mock identifier validation utilities."""
    with (
        patch("services.graph.app.routers.fsma.traceability.validate_tlc") as mock_tlc,
        patch("services.graph.app.routers.fsma.traceability.validate_gln") as mock_gln,
        patch("services.graph.app.routers.fsma.traceability.validate_gtin") as mock_gtin,
    ):
        mock_tlc.return_value = MagicMock(is_valid=True)
        mock_gln.return_value = MagicMock(is_valid=True)
        mock_gtin.return_value = MagicMock(is_valid=True)
        yield mock_tlc, mock_gln, mock_gtin


# =============================================================================
# TESTS
# =============================================================================


def test_log_traceability_event_success(mock_neo4j_client, mock_validation):
    """Verify that a valid mobile event is successfully validated and persisted."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)

    # Mock dependencies
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

    client = TestClient(app)

    payload = {
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

    with (
        patch("shared.canonical_persistence.CanonicalEventStore") as mock_store_cls,
        patch("shared.database.SessionLocal") as mock_session_local,
    ):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        response = client.post("/event", json=payload, headers=_AUTH_HEADERS)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
    data = response.json()
    assert data["status"] == "success"
    assert "event_id" in data
    assert data["tlc"] == "TLC-2024-001"

    mock_store_cls.assert_called_once_with(mock_db, dual_write=True)
    mock_store_cls.return_value.persist_event.assert_called_once()
    persisted = mock_store_cls.return_value.persist_event.call_args.args[0]
    assert persisted.quantity == 24.0
    assert persisted.unit_of_measure == "cases"
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()

    # Check that persistence was triggered correctly
    mock_run = mock_neo4j_client.session.return_value.__aenter__.return_value.run
    assert mock_run.call_count == 5  # TraceEvent, Lot, Facility, and 2 Relationships


def test_log_traceability_event_without_quantity_is_not_bridged(mock_neo4j_client, mock_validation):
    """A capture with no quantity or unit is stored in Neo4j as captured and
    is NOT written to the canonical store with ``1.0`` / ``"each"`` in place
    of the values the operator never entered."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")
    client = TestClient(app)

    payload = {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "TLC-2024-001",
        "location_identifier": "0614141000036",
        "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
    }

    with (
        patch("shared.canonical_persistence.CanonicalEventStore") as mock_store_cls,
        patch("shared.database.SessionLocal") as mock_session_local,
    ):
        mock_session_local.return_value = MagicMock()
        response = client.post("/event", json=payload, headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.json()
    mock_store_cls.return_value.persist_event.assert_not_called()
    mock_run = mock_neo4j_client.session.return_value.__aenter__.return_value.run
    assert mock_run.call_count == 5


def test_log_traceability_event_missing_responsible_party_contact(mock_neo4j_client, mock_validation):
    """Verify that missing responsible_party_contact returns 422 (plan point of contact per 21 CFR 1.1315(a)(4); see #3040)."""
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)

    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

    client = TestClient(app)

    payload = {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "TLC-2024-001",
        "location_identifier": "0614141000036",
        # responsible_party_contact intentionally omitted
    }

    response = client.post("/event", json=payload, headers=_AUTH_HEADERS)

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.json()}"

    # Verify no persistence occurred
    mock_neo4j_client.session.return_value.__aenter__.return_value.run.assert_not_called()


def test_log_traceability_event_invalid_tlc(mock_neo4j_client, mock_validation):
    """Verify that identity validation failures are handled with 400 Bad Request."""
    mock_tlc, _, _ = mock_validation
    mock_tlc.return_value = MagicMock(
        is_valid=False, errors=[MagicMock(message="Format violation: TLC must be alphanumeric")]
    )

    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)

    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID("00000000-0000-0000-0000-000000000001")

    client = TestClient(app)

    payload = {
        "event_type": "RECEIVING",
        "event_date": "2026-02-22",
        "tlc": "!!!INVALID!!!",
        "location_identifier": "0614141000036",
        "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
    }

    response = client.post("/event", json=payload, headers=_AUTH_HEADERS)

    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.json()}"
    assert "Invalid TLC" in response.json()["detail"]
    assert "Format violation" in response.json()["detail"]

    # Verify no persistence occurred
    mock_neo4j_client.session.return_value.__aenter__.return_value.run.assert_not_called()


# =============================================================================
# #2941 — Cypher parameter-binding regression net
#
# The ``mock_neo4j_client`` fixture above stubs ``session.run`` with a bare
# ``AsyncMock()``, which accepts any kwargs. That is what let the mobile
# capture handler ship while binding none of the ``$tenant_id`` parameters
# its MERGE templates declare: the suite could not observe the omission.
#
# The stub below mirrors real Neo4j instead — a RUN whose statement
# references a ``$param`` that is absent from the bound parameter set is
# answered with ``Neo.ClientError.Statement.ParameterMissing``.
# =============================================================================

_CYPHER_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

_MOBILE_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


class _ParameterCheckingRun:
    """Async ``session.run`` double that enforces Neo4j's binding contract.

    Records every ``(query, params)`` pair, and raises the same error class
    the driver raises when a referenced parameter was never bound. Because
    ``ClientError`` is a ``neo4j.exceptions.Neo4jError``, the route's
    ``except (neo4j.exceptions.Neo4jError, ConnectionError)`` handler turns
    it into the same HTTP 500 a real database would produce.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, query, **params):
        missing = sorted(set(_CYPHER_PARAM_RE.findall(query)) - set(params))
        if missing:
            raise ClientError(f"Expected parameter(s): {', '.join(missing)}")
        self.calls.append((query, params))
        return MagicMock()


@pytest.fixture
def strict_neo4j_client():
    """Neo4j client mock whose session enforces Cypher parameter binding."""
    with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock:
        runner = _ParameterCheckingRun()
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.session.return_value.__aenter__.return_value.run = runner
        mock.return_value = mock_instance
        mock.get_tenant_database_name.return_value = "test-db"
        yield runner


def _build_mobile_app() -> FastAPI:
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": str(_MOBILE_TENANT)}
    app.dependency_overrides[get_current_tenant_id] = lambda: _MOBILE_TENANT
    return app


_MOBILE_PAYLOAD = {
    "event_type": "RECEIVING",
    "event_date": "2026-02-22",
    "tlc": "TLC-2024-001",
    "location_identifier": "0614141000036",
    "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
    "product_description": "Green Spinach 10oz",
    "gtin": "10614141000019",
    # Exercises the Document.merge_cypher() call site as well.
    "image_data": "iVBORw0KGgoAAAANSUhEUg==",
}


def test_mobile_capture_binds_every_parameter_its_cypher_declares(strict_neo4j_client, mock_validation):
    """#2941: every ``$param`` in each statement must be bound at the call site.

    On unfixed source the Lot/Facility/Document MERGE templates declare
    ``$tenant_id`` that the handler never binds, so a real Neo4j answers
    ``ParameterMissing`` and the endpoint 500s on every request -- after the
    TraceEvent CREATE has already deposited an orphan node.
    """
    client = TestClient(_build_mobile_app())

    with (
        patch("shared.canonical_persistence.CanonicalEventStore"),
        patch("shared.database.SessionLocal") as mock_session_local,
    ):
        mock_session_local.return_value = MagicMock()
        response = client.post("/event", json=_MOBILE_PAYLOAD, headers=_AUTH_HEADERS)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Belt and braces: assert the contract directly rather than trusting that
    # the stub was reached, so the test cannot pass by never running Cypher.
    assert strict_neo4j_client.calls, "no Cypher was executed"
    for query, params in strict_neo4j_client.calls:
        missing = sorted(set(_CYPHER_PARAM_RE.findall(query)) - set(params))
        assert not missing, f"unbound parameter(s) {missing} in statement:\n{query}"


def test_mobile_capture_binds_authenticated_tenant_to_merge_templates(strict_neo4j_client, mock_validation):
    """#2941: the bound ``tenant_id`` must come from the authenticated context.

    Guards the isolation property, not just the presence of the kwarg: a
    body-supplied or placeholder tenant would let a caller MERGE into another
    tenant's Lot/Facility/Document namespace.
    """
    client = TestClient(_build_mobile_app())

    with (
        patch("shared.canonical_persistence.CanonicalEventStore"),
        patch("shared.database.SessionLocal") as mock_session_local,
    ):
        mock_session_local.return_value = MagicMock()
        response = client.post("/event", json=_MOBILE_PAYLOAD, headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.text

    merges = {
        label: params
        for label, marker in (
            ("Lot", "MERGE (l:Lot"),
            ("Facility", "MERGE (f:Facility"),
            ("Document", "MERGE (d:Document"),
        )
        for query, params in strict_neo4j_client.calls
        if marker in query
    }
    assert set(merges) == {"Lot", "Facility", "Document"}, f"missing MERGE call sites: {sorted(merges)}"

    for label, params in merges.items():
        assert params["tenant_id"] == str(_MOBILE_TENANT), f"{label} MERGE bound the wrong tenant: {params!r}"
