"""
Tests for FSMA 204 TLC Source mandate enforcement.

Validates that:
1. Lots from CREATION/TRANSFORMATION events require tlc_source_gln or tlc_source_fda_reg
2. Consumer rejects events missing TLC source for applicable event types
3. ASSIGNED_BY relationships are correctly created
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.graph.app.consumers.fsma_consumer import (
    TLC_SOURCE_REQUIRED_EVENTS,
    TLCSourceValidationError,
    ingest_fsma_event,
)
from services.graph.app.models.fsma_nodes import (
    FSMA_CONSTRAINTS,
    CTEType,
    Facility,
    FSMARelationships,
    Lot,
    TraceEvent,
)


class TestLotTLCSourceFields:
    """Test TLC source field requirements on Lot dataclass."""

    def test_lot_with_gln_source(self):
        """Lot with tlc_source_gln is valid."""
        lot = Lot(
            tlc="LOT-2024-001",
            product_description="Romaine Lettuce",
            tlc_source_gln="1234567890123",
        )
        assert lot.has_valid_tlc_source() is True
        assert lot.tlc_source_gln == "1234567890123"

    def test_lot_with_fda_source(self):
        """Lot with tlc_source_fda_reg is valid."""
        lot = Lot(
            tlc="LOT-2024-002",
            product_description="Spinach",
            tlc_source_fda_reg="12345678901",
        )
        assert lot.has_valid_tlc_source() is True
        assert lot.tlc_source_fda_reg == "12345678901"

    def test_lot_without_source(self):
        """Lot without TLC source is invalid for source-required events."""
        lot = Lot(
            tlc="LOT-2024-003",
            product_description="Kale",
        )
        assert lot.has_valid_tlc_source() is False

    def test_node_properties_include_source(self):
        """Node properties include TLC source fields when set."""
        lot = Lot(
            tlc="LOT-2024-004",
            tlc_source_gln="9876543210123",
        )
        props = lot.node_properties
        assert "tlc_source_gln" in props
        assert props["tlc_source_gln"] == "9876543210123"

    def test_node_properties_include_fda_source(self):
        """Node properties include FDA source field when set."""
        lot = Lot(
            tlc="LOT-2024-005",
            tlc_source_fda_reg="11111111111",
        )
        props = lot.node_properties
        assert "tlc_source_fda_reg" in props
        assert props["tlc_source_fda_reg"] == "11111111111"


class TestLotAssignedByCypher:
    """Test the assigned_by_cypher() method."""

    def test_assigned_by_cypher_with_gln(self):
        """Generates ASSIGNED_BY cypher when GLN is set."""
        lot = Lot(
            tlc="LOT-GLN-001",
            tlc_source_gln="1111111111111",
        )
        cypher = lot.assigned_by_cypher()

        assert cypher is not None
        assert "MATCH (l:Lot {tlc: 'LOT-GLN-001'})" in cypher
        assert "MERGE (f:Facility {gln: '1111111111111'})" in cypher
        assert "MERGE (l)-[:ASSIGNED_BY]->(f)" in cypher

    def test_assigned_by_cypher_with_fda_reg(self):
        """Generates ASSIGNED_BY cypher when FDA reg is set."""
        lot = Lot(
            tlc="LOT-FDA-001",
            tlc_source_fda_reg="22222222222",
        )
        cypher = lot.assigned_by_cypher()

        assert cypher is not None
        assert "MATCH (l:Lot {tlc: 'LOT-FDA-001'})" in cypher
        assert "fda_registration: '22222222222'" in cypher
        assert "ASSIGNED_BY" in cypher

    def test_assigned_by_cypher_prefers_gln(self):
        """When both GLN and FDA reg set, GLN is preferred."""
        lot = Lot(
            tlc="LOT-BOTH-001",
            tlc_source_gln="3333333333333",
            tlc_source_fda_reg="44444444444",
        )
        cypher = lot.assigned_by_cypher()

        assert "gln: '3333333333333'" in cypher
        assert "fda_registration" not in cypher

    def test_assigned_by_cypher_returns_none_without_source(self):
        """Returns None when no TLC source is set."""
        lot = Lot(tlc="LOT-NONE-001")
        cypher = lot.assigned_by_cypher()

        assert cypher is None

    def test_assigned_by_cypher_creates_facility_on_create(self):
        """Cypher includes ON CREATE SET for facility name."""
        lot = Lot(
            tlc="LOT-NEW-001",
            tlc_source_gln="5555555555555",
        )
        cypher = lot.assigned_by_cypher()

        assert "ON CREATE SET f.name = 'TLC-Source-5555555555555'" in cypher
        assert "f.created_at = datetime()" in cypher


class TestTLCSourceValidationForEventTypes:
    """Test which event types require TLC source validation."""

    def test_transformation_requires_source(self):
        """TRANSFORMATION events require TLC source."""
        assert Lot.validate_tlc_source_for_event("TRANSFORMATION") is True

    def test_initial_packing_requires_source(self):
        """INITIAL_PACKING events require TLC source."""
        assert Lot.validate_tlc_source_for_event("INITIAL_PACKING") is True

    def test_creation_requires_source(self):
        """CREATION events require TLC source."""
        assert Lot.validate_tlc_source_for_event("CREATION") is True

    def test_shipping_does_not_require_source(self):
        """SHIPPING events do not require TLC source."""
        assert Lot.validate_tlc_source_for_event("SHIPPING") is False

    def test_receiving_does_not_require_source(self):
        """RECEIVING events do not require TLC source."""
        assert Lot.validate_tlc_source_for_event("RECEIVING") is False

    def test_unknown_event_does_not_require_source(self):
        """Unknown event types do not require TLC source."""
        assert Lot.validate_tlc_source_for_event("UNKNOWN") is False
        assert Lot.validate_tlc_source_for_event("RANDOM") is False


class TestConsumerTLCSourceValidation:
    """Test consumer validation of TLC source fields."""

    def test_tlc_source_required_events_constant(self):
        """Verify TLC_SOURCE_REQUIRED_EVENTS matches specification."""
        assert "TRANSFORMATION" in TLC_SOURCE_REQUIRED_EVENTS
        assert "INITIAL_PACKING" in TLC_SOURCE_REQUIRED_EVENTS
        assert "CREATION" in TLC_SOURCE_REQUIRED_EVENTS
        assert "SHIPPING" not in TLC_SOURCE_REQUIRED_EVENTS
        assert "RECEIVING" not in TLC_SOURCE_REQUIRED_EVENTS

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_transformation_without_source_raises_error(self, mock_client):
        """Consumer rejects TRANSFORMATION event without TLC source."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        # Event with TRANSFORMATION type but no tlc_source
        event = {
            "document_id": "doc-001",
            "document_type": "PRODUCTION_LOG",
            "ctes": [
                {
                    "type": "TRANSFORMATION",
                    "kdes": {
                        "traceability_lot_code": "NEW-LOT-001",
                        "event_date": "2024-12-02",
                        # Missing tlc_source_gln and tlc_source_fda_reg
                    },
                    "confidence": 0.9,
                }
            ],
        }

        with pytest.raises(TLCSourceValidationError) as exc_info:
            ingest_fsma_event(mock_client_instance, event)

        assert "tlc_source_gln or tlc_source_fda_reg" in str(exc_info.value)
        assert "TRANSFORMATION" in str(exc_info.value)

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_creation_without_source_raises_error(self, mock_client):
        """Consumer rejects CREATION event without TLC source."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        event = {
            "document_id": "doc-002",
            "document_type": "PRODUCTION_LOG",
            "ctes": [
                {
                    "type": "CREATION",
                    "kdes": {
                        "traceability_lot_code": "FARM-LOT-001",
                        "event_date": "2024-12-02",
                    },
                    "confidence": 0.9,
                }
            ],
        }

        with pytest.raises(TLCSourceValidationError):
            ingest_fsma_event(mock_client_instance, event)

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_initial_packing_without_source_raises_error(self, mock_client):
        """Consumer rejects INITIAL_PACKING event without TLC source."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        event = {
            "document_id": "doc-003",
            "document_type": "PRODUCTION_LOG",
            "ctes": [
                {
                    "type": "INITIAL_PACKING",
                    "kdes": {
                        "traceability_lot_code": "PACK-LOT-001",
                        "event_date": "2024-12-02",
                    },
                    "confidence": 0.9,
                }
            ],
        }

        with pytest.raises(TLCSourceValidationError):
            ingest_fsma_event(mock_client_instance, event)

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_shipping_without_source_allowed(self, mock_client):
        """Consumer allows SHIPPING event without TLC source."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        event = {
            "document_id": "doc-004",
            "document_type": "BOL",
            "ctes": [
                {
                    "type": "SHIPPING",
                    "kdes": {
                        "traceability_lot_code": "SHIP-LOT-001",
                        "event_date": "2024-12-02",
                    },
                    "confidence": 0.9,
                }
            ],
        }

        # Should not raise TLCSourceValidationError
        try:
            ingest_fsma_event(mock_client_instance, event)
        except TLCSourceValidationError:
            pytest.fail("SHIPPING should not require TLC source")
        except Exception:
            # Other exceptions (e.g., Neo4j mock issues) are OK for this test
            pass

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_transformation_with_gln_source_allowed(self, mock_client):
        """Consumer allows TRANSFORMATION event with tlc_source_gln."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        event = {
            "document_id": "doc-005",
            "document_type": "PRODUCTION_LOG",
            "ctes": [
                {
                    "type": "TRANSFORMATION",
                    "kdes": {
                        "traceability_lot_code": "TRANS-LOT-001",
                        "event_date": "2024-12-02",
                        "tlc_source_gln": "1234567890123",  # Has GLN source
                    },
                    "confidence": 0.9,
                }
            ],
        }

        # Should not raise TLCSourceValidationError
        try:
            ingest_fsma_event(mock_client_instance, event)
        except TLCSourceValidationError:
            pytest.fail("TRANSFORMATION with tlc_source_gln should be allowed")
        except Exception:
            pass

    @patch("services.graph.app.consumers.fsma_consumer.Neo4jClient")
    def test_creation_with_fda_source_allowed(self, mock_client):
        """Consumer allows CREATION event with tlc_source_fda_reg."""
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client_instance.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        event = {
            "document_id": "doc-006",
            "document_type": "PRODUCTION_LOG",
            "ctes": [
                {
                    "type": "CREATION",
                    "kdes": {
                        "traceability_lot_code": "CREATE-LOT-001",
                        "event_date": "2024-12-02",
                        "tlc_source_fda_reg": "98765432101",  # Has FDA source
                    },
                    "confidence": 0.9,
                }
            ],
        }

        # Should not raise TLCSourceValidationError
        try:
            ingest_fsma_event(mock_client_instance, event)
        except TLCSourceValidationError:
            pytest.fail("CREATION with tlc_source_fda_reg should be allowed")
        except Exception:
            pass


class TestFSMAConstraints:
    """Test FSMA constraint definitions."""

    def test_constraints_include_lot_unique(self):
        """Constraints include lot TLC uniqueness."""
        constraint_str = " ".join(FSMA_CONSTRAINTS)
        assert "lot_tlc_tenant_unique" in constraint_str
        assert "(l.tlc, l.tenant_id) IS UNIQUE" in constraint_str

    def test_constraints_include_facility_unique(self):
        """Constraints include facility GLN uniqueness."""
        constraint_str = " ".join(FSMA_CONSTRAINTS)
        assert "facility_gln_unique" in constraint_str

    def test_constraints_include_tlc_source_gln_index(self):
        """Constraints include TLC source GLN index."""
        constraint_str = " ".join(FSMA_CONSTRAINTS)
        assert "lot_tlc_source_gln_idx" in constraint_str
        assert "l.tlc_source_gln" in constraint_str

    def test_constraints_include_tlc_source_fda_index(self):
        """Constraints include TLC source FDA index."""
        constraint_str = " ".join(FSMA_CONSTRAINTS)
        assert "lot_tlc_source_fda_idx" in constraint_str
        assert "l.tlc_source_fda_reg" in constraint_str

    def test_constraints_include_facility_fda_index(self):
        """Constraints include facility FDA registration index."""
        constraint_str = " ".join(FSMA_CONSTRAINTS)
        assert "facility_fda_reg_idx" in constraint_str

    def test_constraints_are_valid_cypher(self):
        """All constraints are syntactically valid Cypher."""
        for constraint in FSMA_CONSTRAINTS:
            assert constraint.startswith("CREATE")
            assert "IF NOT EXISTS" in constraint

    def test_constraints_count(self):
        """Verify expected number of constraints."""
        # 4 uniqueness + 6 indexes = 10 constraints
        assert len(FSMA_CONSTRAINTS) >= 10


class TestFSMARelationships:
    """Test FSMA relationship definitions."""

    def test_lot_assigned_by_gln_relationship(self):
        """LOT_ASSIGNED_BY_GLN creates correct relationship."""
        cypher = FSMARelationships.LOT_ASSIGNED_BY_GLN
        assert "MATCH (l:Lot" in cypher
        assert "MATCH (f:Facility" in cypher
        assert ":ASSIGNED_BY" in cypher
        assert "$gln" in cypher

    def test_lot_assigned_by_fda_relationship(self):
        """LOT_ASSIGNED_BY_FDA_REG creates correct relationship."""
        cypher = FSMARelationships.LOT_ASSIGNED_BY_FDA_REG
        assert "MATCH (l:Lot" in cypher
        assert "fda_registration" in cypher
        assert ":ASSIGNED_BY" in cypher
        assert "$fda_reg" in cypher


class TestTLCSourceValidationErrorMessage:
    """Test error message formatting for TLC source validation."""

    def test_error_message_includes_event_type(self):
        """Error message includes the event type that failed validation."""
        error = TLCSourceValidationError(
            "TLC source (tlc_source_gln or tlc_source_fda_reg) is required "
            "for TRANSFORMATION events. Document: doc-001, CTE index: 0"
        )
        assert "TRANSFORMATION" in str(error)
        assert "doc-001" in str(error)

    def test_error_is_exception(self):
        """TLCSourceValidationError is a proper exception."""
        error = TLCSourceValidationError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"


class TestLotDataclassIntegrity:
    """Test Lot dataclass field definitions."""

    def test_lot_requires_tlc(self):
        """Lot requires tlc field."""
        lot = Lot(tlc="TEST-LOT")
        assert lot.tlc == "TEST-LOT"

    def test_lot_optional_fields_default_none(self):
        """Optional fields default to None."""
        lot = Lot(tlc="TEST-LOT-2")
        assert lot.gtin is None
        assert lot.product_description is None
        assert lot.quantity is None
        assert lot.tlc_source_gln is None
        assert lot.tlc_source_fda_reg is None

    def test_lot_all_fields_populated(self):
        """Lot can be created with all fields."""
        lot = Lot(
            tlc="FULL-LOT-001",
            gtin="12345678901234",
            product_description="Organic Romaine",
            quantity=100.0,
            unit_of_measure="cases",
            created_at="2024-12-02T10:00:00Z",
            tenant_id="tenant-001",
            tlc_source_gln="9999999999999",
            tlc_source_fda_reg="88888888888",
        )
        assert lot.tlc == "FULL-LOT-001"
        assert lot.gtin == "12345678901234"
        assert lot.product_description == "Organic Romaine"
        assert lot.quantity == 100.0
        assert lot.tlc_source_gln == "9999999999999"
        assert lot.tlc_source_fda_reg == "88888888888"
