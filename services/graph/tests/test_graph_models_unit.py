"""Unit QA for ``services/graph/app/models`` (base, fsma_nodes, tenant_nodes).

Covers real behavior with no Neo4j server: hash helpers, node property
maps, Cypher tenant scoping, TLC source mandate checks, and the response
envelope. Each tenant-boundary test pins the convention that every MATCH
and MERGE key carries ``tenant_id`` alongside the business identifier,
so a refactor cannot silently reopen a cross-tenant write.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.models.base import ResponseEnvelope, ResponseMeta
from services.graph.app.models.fsma_nodes import (
    CTEType,
    Document,
    Facility,
    FacilityType,
    FoodItem,
    Lot,
    TraceEvent,
    compute_chain_hash,
    compute_document_hash,
    compute_event_hash,
    compute_facility_hash,
    compute_lot_hash,
)
from services.graph.app.models.tenant_nodes import (
    OverlayRelationships,
    RegulationOverride,
    TenantOverlay,
)


def _sha(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# -- Hash helpers -----------------------------------------------------------


def test_compute_event_hash_matches_documented_canonical_form():
    assert compute_event_hash("E1", "SHIPPING", "2026-01-05") == _sha("E1|SHIPPING|2026-01-05")


def test_compute_event_hash_is_deterministic_and_sensitive():
    first = compute_event_hash("E1", "SHIPPING", "2026-01-05")
    assert compute_event_hash("E1", "SHIPPING", "2026-01-05") == first
    assert compute_event_hash("E2", "SHIPPING", "2026-01-05") != first
    assert compute_event_hash("E1", "RECEIVING", "2026-01-05") != first
    assert compute_event_hash("E1", "SHIPPING", "2026-01-06") != first


def test_compute_chain_hash_uses_genesis_seed_for_first_event():
    assert compute_chain_hash(None, "eventhash") == _sha("GENESIS|eventhash")


def test_compute_chain_hash_empty_string_is_not_genesis():
    # An empty predecessor hash means a broken read, not a first event.
    # Folding it into GENESIS would mask the broken link.
    assert compute_chain_hash("", "eventhash") == _sha("|eventhash")
    assert compute_chain_hash("", "eventhash") != compute_chain_hash(None, "eventhash")


def test_compute_chain_hash_chains_off_predecessor():
    assert compute_chain_hash("prevchain", "eventhash") == _sha("prevchain|eventhash")


def test_compute_lot_hash_is_scoped_by_tenant():
    assert compute_lot_hash("TLC-1", "tenant-a") == compute_lot_hash("TLC-1", "tenant-a")
    assert compute_lot_hash("TLC-1", "tenant-a") != compute_lot_hash("TLC-1", "tenant-b")
    assert compute_lot_hash("TLC-1", "tenant-a") != compute_lot_hash("TLC-2", "tenant-a")


def test_compute_facility_hash_prefers_gln_then_fda_then_name():
    assert compute_facility_hash(gln="G", fda_registration="F", name="N") == _sha("facility|G")
    assert compute_facility_hash(gln=None, fda_registration="F", name="N") == _sha("facility|F")
    assert compute_facility_hash(gln=None, fda_registration=None, name="N") == _sha("facility|N")


def test_compute_document_hash_covers_id_and_type():
    assert compute_document_hash("D1", "BOL") == _sha("D1|BOL")
    assert compute_document_hash("D1", "BOL") != compute_document_hash("D1", "INVOICE")


# -- TraceEvent -------------------------------------------------------------


def test_trace_event_derives_hash_from_identity_fields():
    event = TraceEvent(event_id="E1", type=CTEType.SHIPPING, event_date="2026-01-05")
    assert event.sha256_hash == compute_event_hash("E1", "SHIPPING", "2026-01-05")


def test_trace_event_keeps_explicit_hash():
    event = TraceEvent(event_id="E1", type=CTEType.SHIPPING, event_date="2026-01-05", sha256_hash="pinned")
    assert event.sha256_hash == "pinned"


def test_trace_event_set_chain_hash_stores_and_returns_genesis_first():
    event = TraceEvent(event_id="E1", type=CTEType.SHIPPING, event_date="2026-01-05")
    chained = event.set_chain_hash(None)
    assert chained == compute_chain_hash(None, event.sha256_hash)
    assert event.chain_hash == chained


def test_trace_event_chain_links_to_predecessor():
    first = TraceEvent(event_id="E1", type=CTEType.SHIPPING, event_date="2026-01-05")
    first.set_chain_hash(None)
    second = TraceEvent(event_id="E2", type=CTEType.RECEIVING, event_date="2026-01-06")
    second.set_chain_hash(first.chain_hash)
    assert second.chain_hash == compute_chain_hash(first.chain_hash, second.sha256_hash)
    assert second.chain_hash != compute_chain_hash(None, second.sha256_hash)


def test_trace_event_properties_keep_zero_confidence_and_tenant():
    event = TraceEvent(
        event_id="E1",
        type=CTEType.SHIPPING,
        event_date="2026-01-05",
        confidence=0.0,
        tenant_id="tenant-a",
    )
    props = event.node_properties
    assert props["confidence"] == 0.0
    assert props["tenant_id"] == "tenant-a"
    assert props["type"] == "SHIPPING"
    assert props["sha256_hash"] == event.sha256_hash


def test_trace_event_properties_omit_unset_tenant():
    event = TraceEvent(event_id="E1", type=CTEType.SHIPPING, event_date="2026-01-05")
    assert "tenant_id" not in event.node_properties
    assert "chain_hash" not in event.node_properties


def test_trace_event_create_cypher_is_plain_create_over_properties():
    cypher = TraceEvent.create_cypher()
    assert "CREATE" in cypher
    assert "$properties" in cypher
    assert "MERGE" not in cypher


# -- Lot --------------------------------------------------------------------


def test_lot_derives_tenant_scoped_hash():
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a")
    assert lot.sha256_hash == compute_lot_hash("TLC-1", "tenant-a")


def test_lot_properties_keep_zero_quantity_and_hash_fields():
    lot = Lot(tlc="TLC-1", quantity=0.0, tenant_id="tenant-a", chain_hash="chain-1")
    props = lot.node_properties
    assert props["quantity"] == 0.0
    assert props["tenant_id"] == "tenant-a"
    assert props["sha256_hash"] == lot.sha256_hash
    assert props["chain_hash"] == "chain-1"


def test_lot_merge_cypher_keys_on_tlc_and_tenant():
    cypher = " ".join(Lot.merge_cypher().split())
    assert "MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id})" in cypher


def test_lot_assigned_by_cypher_prefers_gln_over_fda():
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a", tlc_source_gln="G1", tlc_source_fda_reg="F1")
    cypher, params = lot.assigned_by_cypher()
    assert "source_gln" in cypher
    assert params == {"tlc": "TLC-1", "tenant_id": "tenant-a", "source_gln": "G1"}


def test_lot_assigned_by_cypher_falls_back_to_fda_registration():
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a", tlc_source_fda_reg="F1")
    cypher, params = lot.assigned_by_cypher()
    assert "source_fda_reg" in cypher
    assert params["source_fda_reg"] == "F1"
    assert params["tenant_id"] == "tenant-a"


def test_lot_assigned_by_cypher_returns_none_without_source():
    assert Lot(tlc="TLC-1", tenant_id="tenant-a").assigned_by_cypher() is None


def test_lot_assigned_by_cypher_keeps_values_parameterised():
    hostile = 'G1"}) MATCH (n) DETACH DELETE n //'
    lot = Lot(tlc="TLC-1", tenant_id="tenant-a", tlc_source_gln=hostile)
    cypher, params = lot.assigned_by_cypher()
    assert hostile not in cypher
    assert params["source_gln"] == hostile


def test_lot_tlc_source_required_for_creation_packing_transformation():
    for cte in ("CREATION", "INITIAL_PACKING", "TRANSFORMATION"):
        assert Lot.validate_tlc_source_for_event(cte) is True


def test_lot_tlc_source_not_required_for_movement_events():
    for cte in ("SHIPPING", "RECEIVING", "HARVESTING", "COOLING", "FIRST_LAND_BASED_RECEIVING"):
        assert Lot.validate_tlc_source_for_event(cte) is False


def test_lot_tlc_source_check_accepts_enum_and_any_case():
    assert Lot.validate_tlc_source_for_event(CTEType.CREATION) is True
    assert Lot.validate_tlc_source_for_event(CTEType.TRANSFORMATION) is True
    assert Lot.validate_tlc_source_for_event(CTEType.SHIPPING) is False
    assert Lot.validate_tlc_source_for_event("creation") is True
    assert Lot.validate_tlc_source_for_event("initial_packing") is True
    assert Lot.validate_tlc_source_for_event("transformation") is True
    assert Lot.validate_tlc_source_for_event("shipping") is False
    assert Lot.validate_tlc_source_for_event("not-a-cte") is False


def test_lot_has_valid_tlc_source_rejects_blank_values():
    assert Lot(tlc="T").has_valid_tlc_source() is False
    assert Lot(tlc="T", tlc_source_gln="").has_valid_tlc_source() is False
    assert Lot(tlc="T", tlc_source_gln="   ").has_valid_tlc_source() is False
    assert Lot(tlc="T", tlc_source_gln="G1").has_valid_tlc_source() is True
    assert Lot(tlc="T", tlc_source_fda_reg="F1").has_valid_tlc_source() is True


# -- Facility, FoodItem, Document --------------------------------------------


def test_facility_identifier_prefers_gln_then_fda_then_name():
    assert Facility(gln="G", fda_registration="F", name="N").identifier == "G"
    assert Facility(fda_registration="F", name="N").identifier == "F"
    assert Facility(name="N").identifier == "N"


def test_facility_properties_serialise_type_and_tenant():
    facility = Facility(gln="G1", name="Farm", facility_type=FacilityType.FARM, tenant_id="tenant-a")
    props = facility.node_properties
    assert props["gln"] == "G1"
    assert props["facility_type"] == "FARM"
    assert props["tenant_id"] == "tenant-a"
    assert props["sha256_hash"] == facility.sha256_hash


def test_facility_merge_cyphers_key_on_tenant():
    gln_cypher = " ".join(Facility.merge_cypher().split())
    assert "MERGE (f:Facility {gln: $gln, tenant_id: $tenant_id})" in gln_cypher
    name_cypher = " ".join(Facility.merge_by_name_cypher().split())
    assert "MERGE (f:Facility {name: $name, tenant_id: $tenant_id})" in name_cypher


def test_food_item_properties_and_merge_carry_tenant():
    item = FoodItem(name="Romaine", gtin="123", category="Produce", tenant_id="tenant-a")
    props = item.node_properties
    assert props == {"name": "Romaine", "gtin": "123", "category": "Produce", "tenant_id": "tenant-a"}
    merge = " ".join(FoodItem.merge_cypher().split())
    assert "MERGE (p:FoodItem {name: $name, tenant_id: $tenant_id})" in merge


def test_document_derives_hash_and_merge_carries_tenant():
    doc = Document(document_id="D1", document_type="BOL", tenant_id="tenant-a")
    assert doc.sha256_hash == compute_document_hash("D1", "BOL")
    assert doc.node_properties["tenant_id"] == "tenant-a"
    merge = " ".join(Document.merge_cypher().split())
    assert "MERGE (d:Document {document_id: $document_id, tenant_id: $tenant_id})" in merge


# -- Tenant overlay nodes ----------------------------------------------------


def test_tenant_overlay_properties_and_merge_carry_tenant():
    overlay = TenantOverlay(tenant_id="tenant-a", name="overlay", description="desc")
    assert overlay.node_properties == {
        "tenant_id": "tenant-a",
        "name": "overlay",
        "description": "desc",
    }
    merge = " ".join(TenantOverlay.merge_cypher().split())
    assert "MERGE (t:TenantOverlay {tenant_id: $tenant_id})" in merge


def test_regulation_override_properties_carry_tenant():
    override = RegulationOverride(
        override_id="O1",
        rule_id="R1",
        parameter="threshold",
        value="5",
        tenant_id="tenant-a",
    )
    props = override.node_properties
    assert props["tenant_id"] == "tenant-a"
    assert props["override_id"] == "O1"


def test_regulation_override_merge_keys_on_override_and_tenant():
    # override_id alone is not unique across tenants: without the tenant
    # predicate one tenant's write would match and overwrite another
    # tenant's override node.
    merge = " ".join(RegulationOverride.merge_cypher().split())
    assert "MERGE (r:RegulationOverride {override_id: $override_id, tenant_id: $tenant_id})" in merge


def test_tenant_has_override_scopes_both_ends_by_tenant():
    # If the override MATCH omits tenant_id, a tenant can link its overlay
    # to another tenant's override when override_id values collide.
    flat = " ".join(OverlayRelationships.TENANT_HAS_OVERRIDE.split())
    assert flat.count("tenant_id: $tenant_id") >= 2
    assert "MATCH (r:RegulationOverride {override_id: $override_id, tenant_id: $tenant_id})" in flat


# -- Response envelope -------------------------------------------------------


def test_response_meta_defaults_to_utc_now():
    meta = ResponseMeta()
    assert meta.timestamp.tzinfo is not None
    assert meta.version == "1.0.0"
    assert meta.request_id is None


def test_response_envelope_carries_data_and_fresh_meta():
    first = ResponseEnvelope(data={"hello": "world"})
    second = ResponseEnvelope(data={"hello": "world"})
    assert first.data == {"hello": "world"}
    assert isinstance(first.meta, ResponseMeta)
    assert first.meta is not second.meta
