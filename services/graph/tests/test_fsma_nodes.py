"""Focused unit tests for services/graph/app/models/fsma_nodes.py.

Pure unit tests: node dataclasses, hash helpers, Cypher templates and
graph constraints. No Neo4j, no network.
"""

import hashlib

from services.graph.app.models.fsma_nodes import (
    FSMA_CONSTRAINTS,
    CTEType,
    Document,
    Facility,
    FacilityType,
    FoodItem,
    FSMARelationships,
    Lot,
    TraceEvent,
    compute_chain_hash,
    compute_document_hash,
    compute_event_hash,
    compute_facility_hash,
    compute_lot_hash,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestHashHelpers:
    def test_compute_event_hash_canonical_form(self):
        assert compute_event_hash("evt-1", "SHIPPING", "2024-01-10") == _sha256("evt-1|SHIPPING|2024-01-10")

    def test_compute_chain_hash_uses_genesis_when_none(self):
        event_hash = "abc123"
        assert compute_chain_hash(None, event_hash) == _sha256(f"GENESIS|{event_hash}")
        assert compute_chain_hash("", event_hash) == _sha256(f"GENESIS|{event_hash}")

    def test_compute_chain_hash_chains(self):
        assert compute_chain_hash("prev", "cur") == _sha256("prev|cur")

    def test_compute_lot_hash_scoped_by_tenant(self):
        assert compute_lot_hash("TLC-1", "tenant-a") == _sha256("TLC-1|tenant-a")
        assert compute_lot_hash("TLC-1", "tenant-a") != compute_lot_hash("TLC-1", "tenant-b")
        assert compute_lot_hash("TLC-1") == _sha256("TLC-1|")

    def test_compute_facility_hash_prefers_gln_then_fda_then_name(self):
        assert compute_facility_hash(gln="GLN", fda_registration="FDA", name="N") == _sha256("facility|GLN")
        assert compute_facility_hash(fda_registration="FDA", name="N") == _sha256("facility|FDA")
        assert compute_facility_hash(name="N") == _sha256("facility|N")

    def test_compute_document_hash(self):
        assert compute_document_hash("doc-1", "BOL") == _sha256("doc-1|BOL")


class TestLot:
    def test_post_init_derives_hash_but_keeps_explicit(self):
        assert Lot(tlc="TLC-1", tenant_id="t").sha256_hash == compute_lot_hash("TLC-1", "t")
        assert Lot(tlc="TLC-1", sha256_hash="keep").sha256_hash == "keep"

    def test_node_properties_omits_unset_but_keeps_hashes(self):
        lot = Lot(tlc="TLC-1", tenant_id="t", chain_hash="ch")
        props = lot.node_properties
        assert props["tlc"] == "TLC-1"
        assert props["tenant_id"] == "t"
        assert props["sha256_hash"] == compute_lot_hash("TLC-1", "t")
        assert props["chain_hash"] == "ch"
        assert "gtin" not in props
        assert "quantity" not in props

    def test_merge_cypher_scoped_by_tenant(self):
        cypher = Lot.merge_cypher()
        assert "MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id})" in cypher

    def test_assigned_by_cypher_prefers_gln(self):
        lot = Lot(tlc="TLC-1", tenant_id="t", tlc_source_gln="GLN-1", tlc_source_fda_reg="FDA-1")
        cypher, params = lot.assigned_by_cypher()
        assert "gln: $source_gln" in cypher
        assert params == {"tlc": "TLC-1", "tenant_id": "t", "source_gln": "GLN-1"}

    def test_assigned_by_cypher_falls_back_to_fda_reg(self):
        lot = Lot(tlc="TLC-1", tenant_id="t", tlc_source_fda_reg="FDA-1")
        cypher, params = lot.assigned_by_cypher()
        assert "fda_registration: $source_fda_reg" in cypher
        assert params["source_fda_reg"] == "FDA-1"

    def test_assigned_by_cypher_none_without_source(self):
        assert Lot(tlc="TLC-1", tenant_id="t").assigned_by_cypher() is None

    def test_tlc_source_validation(self):
        assert Lot(tlc="T").has_valid_tlc_source() is False
        assert Lot(tlc="T", tlc_source_gln="G").has_valid_tlc_source() is True
        assert Lot.validate_tlc_source_for_event("TRANSFORMATION") is True
        assert Lot.validate_tlc_source_for_event("CREATION") is True
        assert Lot.validate_tlc_source_for_event("INITIAL_PACKING") is True
        assert Lot.validate_tlc_source_for_event("SHIPPING") is False


class TestTraceEvent:
    def test_post_init_derives_event_hash(self):
        event = TraceEvent(event_id="e1", type=CTEType.SHIPPING, event_date="2024-01-10")
        assert event.sha256_hash == compute_event_hash("e1", "SHIPPING", "2024-01-10")

    def test_set_chain_hash_returns_and_stores(self):
        event = TraceEvent(event_id="e1", type=CTEType.SHIPPING, event_date="2024-01-10")
        chained = event.set_chain_hash(None)
        assert chained == compute_chain_hash(None, event.sha256_hash)
        assert event.chain_hash == chained

    def test_set_chain_hash_without_event_hash_raises(self):
        event = TraceEvent(event_id="e1", type=CTEType.SHIPPING, event_date="2024-01-10")
        event.sha256_hash = None
        try:
            event.set_chain_hash(None)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError when sha256_hash is None")

    def test_node_properties_includes_hashes(self):
        event = TraceEvent(event_id="e1", type=CTEType.RECEIVING, event_date="2024-01-11", tenant_id="t")
        event.set_chain_hash("prev")
        props = event.node_properties
        assert props["event_id"] == "e1"
        assert props["type"] == "RECEIVING"
        assert props["sha256_hash"] == compute_event_hash("e1", "RECEIVING", "2024-01-11")
        assert props["chain_hash"] == compute_chain_hash("prev", props["sha256_hash"])

    def test_create_cypher_mentions_properties(self):
        assert "$properties" in TraceEvent.create_cypher()


class TestFacility:
    def test_post_init_derives_hash(self):
        facility = Facility(gln="GLN-1", name="Farm")
        assert facility.sha256_hash == compute_facility_hash(gln="GLN-1", fda_registration=None, name="Farm")

    def test_identifier_prefers_gln(self):
        assert Facility(gln="G", fda_registration="F", name="N").identifier == "G"
        assert Facility(fda_registration="F", name="N").identifier == "F"
        assert Facility(name="N").identifier == "N"

    def test_node_properties_includes_facility_type_value(self):
        props = Facility(name="Farm", facility_type=FacilityType.FARM, tenant_id="t").node_properties
        assert props["facility_type"] == "FARM"
        assert props["name"] == "Farm"

    def test_merge_cypher_templates_exist(self):
        assert "gln: $gln" in Facility.merge_cypher()
        assert "name: $name" in Facility.merge_by_name_cypher()


class TestFoodItemAndDocument:
    def test_food_item_properties(self):
        item = FoodItem(name="Romaine", gtin="GTIN-1", tenant_id="t")
        props = item.node_properties
        assert props == {"name": "Romaine", "gtin": "GTIN-1", "tenant_id": "t"}
        assert "MERGE (p:FoodItem" in FoodItem.merge_cypher()

    def test_document_post_init_and_properties(self):
        doc = Document(document_id="d1", document_type="BOL", tenant_id="t")
        assert doc.sha256_hash == compute_document_hash("d1", "BOL")
        props = doc.node_properties
        assert props["document_id"] == "d1"
        assert props["sha256_hash"] == compute_document_hash("d1", "BOL")
        assert "MERGE (d:Document" in Document.merge_cypher()


class TestRelationshipsAndConstraints:
    def test_all_relationship_templates_are_tenant_scoped(self):
        templates = [
            FSMARelationships.LOT_UNDERWENT_EVENT,
            FSMARelationships.EVENT_PRODUCED_LOT,
            FSMARelationships.EVENT_CONSUMED_LOT,
            FSMARelationships.EVENT_OCCURRED_AT,
            FSMARelationships.SHIPPED_FROM,
            FSMARelationships.SHIPPED_TO,
            FSMARelationships.LOT_IS_PRODUCT,
            FSMARelationships.DOCUMENT_EVIDENCES,
            FSMARelationships.LOT_ASSIGNED_BY_GLN,
            FSMARelationships.LOT_ASSIGNED_BY_FDA_REG,
        ]
        for template in templates:
            assert "tenant_id: $tenant_id" in template, template

    def test_constraints_cover_tenant_scoped_uniqueness(self):
        joined = "\n".join(FSMA_CONSTRAINTS)
        assert "(l.tlc, l.tenant_id) IS UNIQUE" in joined
        assert "(e.event_id, e.tenant_id) IS UNIQUE" in joined
        assert "(d.document_id, d.tenant_id) IS UNIQUE" in joined
