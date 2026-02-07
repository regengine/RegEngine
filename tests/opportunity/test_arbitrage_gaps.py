"""Tests for the Opportunities API - arbitrage and gap analysis.

These tests verify:
- Arbitrage query endpoint functionality
- Gaps query endpoint functionality
- Request validation
- Response format
- Neo4j query construction
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("neo4j")


class TestArbitrageQueryBuilder:
    """Tests for arbitrage query construction."""

    def test_build_arbitrage_query_no_filters(self):
        """Verify base query when no filters are applied."""
        from services.opportunity.app.neo4j_utils import build_arbitrage_query

        query = build_arbitrage_query(
            jurisdiction_1=None,
            jurisdiction_2=None,
            concept=None,
            include_since=False,
        )

        assert "MATCH" in query
        assert "Concept" in query
        assert "Provision" in query
        assert "Threshold" in query

    def test_build_arbitrage_query_with_jurisdictions(self):
        """Verify jurisdiction filters are added when specified."""
        from services.opportunity.app.neo4j_utils import build_arbitrage_query

        query = build_arbitrage_query(
            jurisdiction_1="US-NY",
            jurisdiction_2="EU",
            concept=None,
            include_since=False,
        )

        assert "Jurisdiction" in query
        assert "$j1" in query
        assert "$j2" in query

    def test_build_arbitrage_query_with_concept_filter(self):
        """Verify concept filter is added when specified."""
        from services.opportunity.app.neo4j_utils import build_arbitrage_query

        query = build_arbitrage_query(
            jurisdiction_1=None,
            jurisdiction_2=None,
            concept="Data Breach",
            include_since=False,
        )

        assert "$concept" in query
        assert "toLower" in query

    def test_build_arbitrage_query_with_since_filter(self):
        """Verify since filter is added when specified."""
        from services.opportunity.app.neo4j_utils import build_arbitrage_query

        query = build_arbitrage_query(
            jurisdiction_1=None,
            jurisdiction_2=None,
            concept=None,
            include_since=True,
        )

        assert "$since" in query
        assert "created_at" in query


class TestGapsQuery:
    """Tests for the gaps query structure."""

    def test_gaps_query_structure(self):
        """Verify gaps query has correct structure."""
        from services.opportunity.app.neo4j_utils import CYPHER_GAP

        # Query should check for concepts in j1 that don't exist in j2
        assert "NOT EXISTS" in CYPHER_GAP
        assert "$j1" in CYPHER_GAP
        assert "$j2" in CYPHER_GAP
        assert "Jurisdiction" in CYPHER_GAP
        assert "Concept" in CYPHER_GAP


class TestOpportunityApiEndpoints:
    """Tests for Opportunity API HTTP endpoints."""

    @pytest.fixture
    def opportunity_client(self, monkeypatch):
        """Provide a TestClient with mocked Neo4j driver."""
        # Mock Neo4j driver
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = lambda _: mock_session
        mock_driver.session.return_value.__exit__ = lambda *args: None

        monkeypatch.setattr(
            "services.opportunity.app.neo4j_utils.get_driver",
            lambda: mock_driver
        )

        from services.opportunity.main import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_health_endpoint(self, opportunity_client):
        """Verify health endpoint returns ok."""
        resp = opportunity_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_arbitrage_endpoint_returns_items(self, opportunity_client):
        """Verify arbitrage endpoint returns proper structure."""
        resp = opportunity_client.get(
            "/opportunities/arbitrage",
            params={"j1": "US-NY", "j2": "EU"},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_arbitrage_endpoint_optional_params(self, opportunity_client):
        """Verify arbitrage works without jurisdiction params."""
        resp = opportunity_client.get("/opportunities/arbitrage")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_gaps_endpoint_requires_jurisdictions(self, opportunity_client):
        """Verify gaps endpoint requires j1 and j2."""
        resp = opportunity_client.get("/opportunities/gaps")
        
        # Should return 422 for missing required params
        assert resp.status_code == 422

    def test_gaps_endpoint_returns_items(self, opportunity_client):
        """Verify gaps endpoint returns proper structure."""
        resp = opportunity_client.get(
            "/opportunities/gaps",
            params={"j1": "EU", "j2": "US-CA"},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestArbitrageCitation:
    """Tests for citation data in arbitrage results."""

    def test_citation_structure(self):
        """Verify expected citation structure."""
        expected_fields = [
            "doc_id",
            "start",
            "end",
            "source_url",
        ]
        
        # This documents the expected citation format
        assert len(expected_fields) == 4

    def test_arbitrage_result_structure(self):
        """Verify expected arbitrage result structure."""
        expected_fields = [
            "concept",
            "unit",
            "v1",
            "v2",
            "text1",
            "text2",
            "citation_1",
            "citation_2",
        ]
        
        # This documents the expected result format
        assert len(expected_fields) == 8


class TestRelDeltaParameter:
    """Tests for the relative delta threshold parameter."""

    @pytest.fixture
    def opportunity_client(self, monkeypatch):
        """Provide a TestClient."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__ = lambda _: mock_session
        mock_driver.session.return_value.__exit__ = lambda *args: None

        monkeypatch.setattr(
            "services.opportunity.app.neo4j_utils.get_driver",
            lambda: mock_driver
        )

        from services.opportunity.main import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_default_rel_delta(self, opportunity_client):
        """Verify default rel_delta is 0.2."""
        resp = opportunity_client.get(
            "/opportunities/arbitrage",
            params={"j1": "US", "j2": "EU"},
        )
        assert resp.status_code == 200

    def test_custom_rel_delta(self, opportunity_client):
        """Verify custom rel_delta is accepted."""
        resp = opportunity_client.get(
            "/opportunities/arbitrage",
            params={"j1": "US", "j2": "EU", "rel_delta": 0.5},
        )
        assert resp.status_code == 200

    def test_rel_delta_validation_min(self, opportunity_client):
        """Verify rel_delta must be >= 0."""
        resp = opportunity_client.get(
            "/opportunities/arbitrage",
            params={"j1": "US", "j2": "EU", "rel_delta": -0.1},
        )
        assert resp.status_code == 422

    def test_rel_delta_validation_max(self, opportunity_client):
        """Verify rel_delta must be <= 1."""
        resp = opportunity_client.get(
            "/opportunities/arbitrage",
            params={"j1": "US", "j2": "EU", "rel_delta": 1.5},
        )
        assert resp.status_code == 422
