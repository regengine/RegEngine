"""
FSMA 204 Graph Node Models for Neo4j.

Defines the node schemas for food supply chain traceability:
- Lot: A specific batch of product with a Traceability Lot Code (TLC)
- TraceEvent: A Critical Tracking Event (CTE) - Shipping, Receiving, Transformation, Creation
- Facility: A physical location (Farm, Processor, Distributor, Retailer)
- FoodItem: Abstract product type
- Document: Source document for audit trail

Every node that participates in the tamper-evident hash chain exposes
``sha256_hash`` and ``chain_hash`` properties, mirroring the columns in
``fsma.cte_events`` and the ``fsma.hash_chain`` ledger table
(see ``migrations/V002__fsma_cte_persistence.sql``).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class CTEType(str, Enum):
    """Critical Tracking Event Types per FSMA 204."""

    SHIPPING = "SHIPPING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"
    CREATION = "CREATION"
    INITIAL_PACKING = "INITIAL_PACKING"


class FacilityType(str, Enum):
    """Types of facilities in the food supply chain."""

    FARM = "FARM"
    PROCESSOR = "PROCESSOR"
    DISTRIBUTOR = "DISTRIBUTOR"
    RETAILER = "RETAILER"
    RESTAURANT = "RESTAURANT"
    WAREHOUSE = "WAREHOUSE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Hash-chaining helpers
# ---------------------------------------------------------------------------

_GENESIS_HASH = "GENESIS"


def _compute_sha256(canonical: str) -> str:
    """Return hex-encoded SHA-256 of *canonical* (UTF-8)."""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_event_hash(event_id: str, event_type: str, event_date: str) -> str:
    """
    Compute the per-event SHA-256 hash (``sha256_hash`` column).

    The canonical form is the pipe-delimited concatenation of the three
    immutable identity fields, matching the SQL-side convention in
    ``fsma.cte_events.sha256_hash``.
    """
    canonical = f"{event_id}|{event_type}|{event_date}"
    return _compute_sha256(canonical)


def compute_chain_hash(previous_chain_hash: Optional[str], event_hash: str) -> str:
    """
    Compute the chained hash: ``SHA-256(previous_chain_hash | event_hash)``.

    Uses ``GENESIS`` as the seed when *previous_chain_hash* is ``None``
    (first event in the tenant chain).
    """
    prev = previous_chain_hash or _GENESIS_HASH
    return _compute_sha256(f"{prev}|{event_hash}")


def compute_lot_hash(tlc: str, tenant_id: Optional[str] = None) -> str:
    """Compute a content-addressable hash for a Lot node."""
    canonical = f"{tlc}|{tenant_id or ''}"
    return _compute_sha256(canonical)


def compute_facility_hash(
    gln: Optional[str] = None,
    fda_registration: Optional[str] = None,
    name: str = "",
) -> str:
    """Compute a content-addressable hash for a Facility node."""
    identifier = gln or fda_registration or name
    return _compute_sha256(f"facility|{identifier}")


def compute_document_hash(document_id: str, document_type: str) -> str:
    """Compute a content-addressable hash for a Document node."""
    return _compute_sha256(f"{document_id}|{document_type}")


# ---------------------------------------------------------------------------
# Node models
# ---------------------------------------------------------------------------


@dataclass
class Lot:
    """
    A specific batch of product identified by a Traceability Lot Code (TLC).

    Neo4j Label: Lot

    FSMA 204 TLC Source Mandate:
    The tlc_source_gln and tlc_source_fda_reg fields track the entity that
    assigned this lot code. Required for TRANSFORMATION, INITIAL_PACKING,
    and CREATION events.
    """

    tlc: str  # Traceability Lot Code (primary key)
    gtin: Optional[str] = None  # GS1 Global Trade Item Number
    product_description: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    created_at: Optional[str] = None
    tenant_id: Optional[str] = None
    # TLC Source fields - required for TRANSFORMATION/INITIAL_PACKING/CREATION
    tlc_source_gln: Optional[str] = None  # GLN of facility that assigned the TLC
    tlc_source_fda_reg: Optional[str] = None  # FDA Registration of TLC source facility
    # Merkle hash-chain integrity
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None

    def __post_init__(self) -> None:
        """Derive sha256_hash if not explicitly provided."""
        if self.sha256_hash is None:
            self.sha256_hash = compute_lot_hash(self.tlc, self.tenant_id)

    # Cypher properties
    @property
    def node_properties(self) -> Dict[str, Any]:
        """Return properties for Neo4j node creation."""
        props = {"tlc": self.tlc}
        if self.gtin:
            props["gtin"] = self.gtin
        if self.product_description:
            props["product_description"] = self.product_description
        if self.quantity is not None:
            props["quantity"] = self.quantity
        if self.unit_of_measure:
            props["unit_of_measure"] = self.unit_of_measure
        if self.created_at:
            props["created_at"] = self.created_at
        if self.tenant_id:
            props["tenant_id"] = self.tenant_id
        if self.tlc_source_gln:
            props["tlc_source_gln"] = self.tlc_source_gln
        if self.tlc_source_fda_reg:
            props["tlc_source_fda_reg"] = self.tlc_source_fda_reg
        # Hash-chain fields -- always written so the graph stays verifiable
        if self.sha256_hash:
            props["sha256_hash"] = self.sha256_hash
        if self.chain_hash:
            props["chain_hash"] = self.chain_hash
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Lot node."""
        return """
        MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id})
        ON CREATE SET l += $properties, l.created_at = datetime()
        ON MATCH SET l += $properties
        RETURN l
        """

    def assigned_by_cypher(self) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        Generate Cypher to create ASSIGNED_BY relationship to TLC Source Facility.

        Returns None if neither tlc_source_gln nor tlc_source_fda_reg is set.
        Returns a (cypher, params) tuple using parameterised queries to prevent
        Cypher injection.  Uses GLN-based matching if available, otherwise falls
        back to FDA registration.

        FSMA 204 requires that CREATION, INITIAL_PACKING, and TRANSFORMATION events
        must identify the entity that assigned the Traceability Lot Code.
        """
        if self.tlc_source_gln:
            cypher = """
            MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id})
            MERGE (f:Facility {gln: $source_gln, tenant_id: $tenant_id})
            ON CREATE SET f.name = 'TLC-Source-' + $source_gln, f.created_at = datetime()
            MERGE (l)-[:ASSIGNED_BY]->(f)
            RETURN l, f
            """
            params = {
                "tlc": self.tlc,
                "tenant_id": self.tenant_id,
                "source_gln": self.tlc_source_gln,
            }
            return cypher, params
        elif self.tlc_source_fda_reg:
            cypher = """
            MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id})
            MERGE (f:Facility {fda_registration: $source_fda_reg, tenant_id: $tenant_id})
            ON CREATE SET f.name = 'TLC-Source-FDA-' + $source_fda_reg, f.created_at = datetime()
            MERGE (l)-[:ASSIGNED_BY]->(f)
            RETURN l, f
            """
            params = {
                "tlc": self.tlc,
                "tenant_id": self.tenant_id,
                "source_fda_reg": self.tlc_source_fda_reg,
            }
            return cypher, params
        return None

    def has_valid_tlc_source(self) -> bool:
        """Check if this Lot has a valid TLC source identifier."""
        return bool(self.tlc_source_gln or self.tlc_source_fda_reg)

    @staticmethod
    def validate_tlc_source_for_event(cte_type: str) -> bool:
        """
        Check if TLC source validation is required for the given CTE type.

        Per FSMA 204, TLC source is mandatory for:
        - CREATION: Initial assignment of TLC at the farm/source
        - INITIAL_PACKING: First packing of product with TLC
        - TRANSFORMATION: Creation of new TLC from input lots
        """
        return cte_type in {"CREATION", "INITIAL_PACKING", "TRANSFORMATION"}


@dataclass
class TraceEvent:
    """
    A Critical Tracking Event (CTE) representing movement or transformation.

    Neo4j Label: TraceEvent

    Hash-chain fields:
      - ``sha256_hash``: SHA-256 of the canonical event form
        (``event_id|type|event_date``).
      - ``chain_hash``: ``SHA-256(previous_chain_hash | sha256_hash)``
        linking this event to the append-only hash chain ledger.
    """

    event_id: str  # Unique event identifier
    type: CTEType
    event_date: str  # ISO date YYYY-MM-DD
    event_time: Optional[str] = None  # ISO time HH:MM:SSZ
    description: Optional[str] = None
    document_id: Optional[str] = None  # Source document reference
    confidence: Optional[float] = None
    tenant_id: Optional[str] = None
    responsible_party_contact: Optional[str] = None  # FSMA 204 KDE
    # Merkle hash-chain integrity
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None

    def __post_init__(self) -> None:
        """Derive sha256_hash from identity fields if not provided."""
        if self.sha256_hash is None:
            event_type = (
                self.type.value if isinstance(self.type, CTEType) else str(self.type)
            )
            self.sha256_hash = compute_event_hash(
                self.event_id, event_type, self.event_date
            )

    def set_chain_hash(self, previous_chain_hash: Optional[str]) -> str:
        """
        Compute and store the chain_hash given the predecessor's chain_hash.

        Returns the newly computed chain_hash so it can be forwarded to the
        next event in sequence.
        """
        if self.sha256_hash is None:
            raise ValueError("sha256_hash must be set before computing chain_hash")
        self.chain_hash = compute_chain_hash(previous_chain_hash, self.sha256_hash)
        return self.chain_hash

    @property
    def node_properties(self) -> Dict[str, Any]:
        """Return properties for Neo4j node creation."""
        props = {
            "event_id": self.event_id,
            "type": self.type.value if isinstance(self.type, CTEType) else self.type,
            "event_date": self.event_date,
        }
        if self.event_time:
            props["event_time"] = self.event_time
        if self.description:
            props["description"] = self.description
        if self.document_id:
            props["document_id"] = self.document_id
        if self.confidence is not None:
            props["confidence"] = self.confidence
        if self.tenant_id:
            props["tenant_id"] = self.tenant_id
        # Hash-chain fields
        if self.sha256_hash:
            props["sha256_hash"] = self.sha256_hash
        if self.chain_hash:
            props["chain_hash"] = self.chain_hash
        return props

    @staticmethod
    def create_cypher() -> str:
        """Return Cypher CREATE statement for TraceEvent node.

        NOTE: tenant_id isolation depends on the caller including
        ``tenant_id`` in the ``$properties`` map.  All call-sites must
        ensure ``tenant_id`` is present before executing this statement.
        """
        return """
        CREATE (e:TraceEvent $properties)
        SET e.created_at = datetime()
        RETURN e
        """


@dataclass
class Facility:
    """
    A physical location in the supply chain.

    Neo4j Label: Facility
    """

    gln: Optional[str] = None  # GS1 Global Location Number (13 digits)
    fda_registration: Optional[str] = None  # FDA Facility Registration
    name: str = ""
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "US"
    facility_type: FacilityType = FacilityType.UNKNOWN
    tenant_id: Optional[str] = None
    # Merkle hash-chain integrity
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None

    def __post_init__(self) -> None:
        """Derive sha256_hash if not explicitly provided."""
        if self.sha256_hash is None:
            self.sha256_hash = compute_facility_hash(
                gln=self.gln,
                fda_registration=self.fda_registration,
                name=self.name,
            )

    @property
    def identifier(self) -> str:
        """Return the primary identifier (GLN preferred, then FDA reg, then name)."""
        return self.gln or self.fda_registration or self.name

    @property
    def node_properties(self) -> Dict[str, Any]:
        """Return properties for Neo4j node creation."""
        props = {"name": self.name}
        if self.gln:
            props["gln"] = self.gln
        if self.fda_registration:
            props["fda_registration"] = self.fda_registration
        if self.address:
            props["address"] = self.address
        if self.city:
            props["city"] = self.city
        if self.state:
            props["state"] = self.state
        if self.country:
            props["country"] = self.country
        props["facility_type"] = (
            self.facility_type.value
            if isinstance(self.facility_type, FacilityType)
            else self.facility_type
        )
        if self.tenant_id:
            props["tenant_id"] = self.tenant_id
        if self.sha256_hash:
            props["sha256_hash"] = self.sha256_hash
        if self.chain_hash:
            props["chain_hash"] = self.chain_hash
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Facility node."""
        return """
        MERGE (f:Facility {gln: $gln, tenant_id: $tenant_id})
        ON CREATE SET f += $properties, f.created_at = datetime()
        ON MATCH SET f += $properties
        RETURN f
        """

    @staticmethod
    def merge_by_name_cypher() -> str:
        """Return Cypher MERGE statement for Facility by name (when no GLN)."""
        return """
        MERGE (f:Facility {name: $name, tenant_id: $tenant_id})
        ON CREATE SET f += $properties, f.created_at = datetime()
        ON MATCH SET f += $properties
        RETURN f
        """


@dataclass
class FoodItem:
    """
    Abstract product type (e.g., "Romaine Lettuce").

    Neo4j Label: FoodItem
    """

    gtin: Optional[str] = None  # GS1 GTIN if available
    name: str = ""
    category: Optional[str] = None  # e.g., "Produce", "Dairy"
    fda_product_code: Optional[str] = None
    tenant_id: Optional[str] = None

    @property
    def node_properties(self) -> Dict[str, Any]:
        """Return properties for Neo4j node creation."""
        props = {"name": self.name}
        if self.gtin:
            props["gtin"] = self.gtin
        if self.category:
            props["category"] = self.category
        if self.fda_product_code:
            props["fda_product_code"] = self.fda_product_code
        if self.tenant_id:
            props["tenant_id"] = self.tenant_id
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for FoodItem node."""
        return """
        MERGE (p:FoodItem {name: $name, tenant_id: $tenant_id})
        ON CREATE SET p += $properties, p.created_at = datetime()
        ON MATCH SET p += $properties
        RETURN p
        """


@dataclass
class Document:
    """
    Source document for audit trail (BOL, Invoice, etc.).

    Neo4j Label: Document
    """

    document_id: str
    document_type: str  # BOL, INVOICE, PRODUCTION_LOG
    source_uri: Optional[str] = None  # S3 or file path
    raw_content: Optional[str] = None  # Storage for Base64 or specific fact extraction results
    extraction_timestamp: Optional[str] = None
    tenant_id: Optional[str] = None
    # Merkle hash-chain integrity
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None

    def __post_init__(self) -> None:
        """Derive sha256_hash if not explicitly provided."""
        if self.sha256_hash is None:
            self.sha256_hash = compute_document_hash(
                self.document_id, self.document_type
            )

    @property
    def node_properties(self) -> Dict[str, Any]:
        """Return properties for Neo4j node creation."""
        props = {
            "document_id": self.document_id,
            "document_type": self.document_type,
        }
        if self.source_uri:
            props["source_uri"] = self.source_uri
        if self.raw_content:
            props["raw_content"] = self.raw_content
        if self.extraction_timestamp:
            props["extraction_timestamp"] = self.extraction_timestamp
        if self.tenant_id:
            props["tenant_id"] = self.tenant_id
        if self.sha256_hash:
            props["sha256_hash"] = self.sha256_hash
        if self.chain_hash:
            props["chain_hash"] = self.chain_hash
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Document node."""
        return """
        MERGE (d:Document {document_id: $document_id, tenant_id: $tenant_id})
        ON CREATE SET d += $properties, d.created_at = datetime()
        ON MATCH SET d += $properties
        RETURN d
        """


# =============================================================================
# Relationship Patterns
# =============================================================================


class FSMARelationships:
    """Cypher templates for FSMA relationship creation."""

    # Lot underwent a TraceEvent
    LOT_UNDERWENT_EVENT = """
    MATCH (l:Lot {tlc: $tlc})
    MATCH (e:TraceEvent {event_id: $event_id})
    MERGE (l)-[:UNDERWENT]->(e)
    """

    # TraceEvent produced a Lot (transformation output)
    EVENT_PRODUCED_LOT = """
    MATCH (e:TraceEvent {event_id: $event_id})
    MATCH (l:Lot {tlc: $tlc})
    MERGE (e)-[:PRODUCED]->(l)
    """

    # TraceEvent consumed a Lot (transformation input)
    EVENT_CONSUMED_LOT = """
    MATCH (e:TraceEvent {event_id: $event_id})
    MATCH (l:Lot {tlc: $tlc})
    MERGE (e)-[:CONSUMED]->(l)
    """

    # TraceEvent occurred at a Facility
    EVENT_OCCURRED_AT = """
    MATCH (e:TraceEvent {event_id: $event_id})
    MATCH (f:Facility {gln: $gln})
    MERGE (e)-[:OCCURRED_AT]->(f)
    """

    # Shipping: From facility shipped to event, event shipped to destination
    SHIPPED_FROM = """
    MATCH (f:Facility {gln: $from_gln})
    MATCH (e:TraceEvent {event_id: $event_id})
    MERGE (f)-[:SHIPPED]->(e)
    """

    SHIPPED_TO = """
    MATCH (e:TraceEvent {event_id: $event_id})
    MATCH (f:Facility {gln: $to_gln})
    MERGE (e)-[:SHIPPED_TO]->(f)
    """

    # Lot is an instance of FoodItem
    LOT_IS_PRODUCT = """
    MATCH (l:Lot {tlc: $tlc})
    MATCH (p:FoodItem {name: $product_name})
    MERGE (l)-[:IS_PRODUCT]->(p)
    """

    # Document evidences TraceEvent
    DOCUMENT_EVIDENCES = """
    MATCH (d:Document {document_id: $document_id})
    MATCH (e:TraceEvent {event_id: $event_id})
    MERGE (d)-[:EVIDENCES]->(e)
    """

    # Lot assigned by Facility (TLC Source relationship)
    # Links a Lot to the Facility that assigned its Traceability Lot Code
    LOT_ASSIGNED_BY_GLN = """
    MATCH (l:Lot {tlc: $tlc})
    MATCH (f:Facility {gln: $gln})
    MERGE (l)-[:ASSIGNED_BY]->(f)
    """

    LOT_ASSIGNED_BY_FDA_REG = """
    MATCH (l:Lot {tlc: $tlc})
    MATCH (f:Facility {fda_registration: $fda_reg})
    MERGE (l)-[:ASSIGNED_BY]->(f)
    """


# =============================================================================
# Graph Constraints (Run once on DB setup)
# =============================================================================

FSMA_CONSTRAINTS = [
    # Uniqueness constraints
    "CREATE CONSTRAINT lot_tlc_tenant_unique IF NOT EXISTS FOR (l:Lot) REQUIRE (l.tlc, l.tenant_id) IS UNIQUE",
    "CREATE CONSTRAINT facility_gln_tenant_unique IF NOT EXISTS FOR (f:Facility) REQUIRE (f.gln, f.tenant_id) IS UNIQUE",
    "CREATE CONSTRAINT trace_event_id_tenant_unique IF NOT EXISTS FOR (e:TraceEvent) REQUIRE (e.event_id, e.tenant_id) IS UNIQUE",
    "CREATE CONSTRAINT document_id_tenant_unique IF NOT EXISTS FOR (d:Document) REQUIRE (d.document_id, d.tenant_id) IS UNIQUE",
    # TLC Source indexes - support FSMA 204 mandate for tracking lot assignment provenance
    "CREATE INDEX lot_tlc_source_gln_idx IF NOT EXISTS FOR (l:Lot) ON (l.tlc_source_gln)",
    "CREATE INDEX lot_tlc_source_fda_idx IF NOT EXISTS FOR (l:Lot) ON (l.tlc_source_fda_reg)",
    # Hash-chain indexes - support verification queries against the graph
    "CREATE INDEX event_sha256_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.sha256_hash)",
    "CREATE INDEX event_chain_hash_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.chain_hash)",
    "CREATE INDEX lot_sha256_idx IF NOT EXISTS FOR (l:Lot) ON (l.sha256_hash)",
    # Performance indexes
    "CREATE INDEX lot_tenant_idx IF NOT EXISTS FOR (l:Lot) ON (l.tenant_id)",
    "CREATE INDEX event_date_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.event_date)",
    "CREATE INDEX event_type_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.type)",
    "CREATE INDEX facility_fda_reg_idx IF NOT EXISTS FOR (f:Facility) ON (f.fda_registration)",
]
