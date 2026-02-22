"""
FSMA 204 Graph Node Models for Neo4j.

Defines the node schemas for food supply chain traceability:
- Lot: A specific batch of product with a Traceability Lot Code (TLC)
- TraceEvent: A Critical Tracking Event (CTE) - Shipping, Receiving, Transformation, Creation
- Facility: A physical location (Farm, Processor, Distributor, Retailer)
- FoodItem: Abstract product type
- Document: Source document for audit trail
"""

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
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Lot node."""
        return """
        MERGE (l:Lot {tlc: $tlc})
        ON CREATE SET l += $properties, l.created_at = datetime()
        ON MATCH SET l += $properties
        RETURN l
        """

    def assigned_by_cypher(self) -> Optional[str]:
        """
        Generate Cypher to create ASSIGNED_BY relationship to TLC Source Facility.

        Returns None if neither tlc_source_gln nor tlc_source_fda_reg is set.
        Uses GLN-based matching if available, otherwise falls back to FDA registration.

        FSMA 204 requires that CREATION, INITIAL_PACKING, and TRANSFORMATION events
        must identify the entity that assigned the Traceability Lot Code.
        """
        if self.tlc_source_gln:
            return f"""
            MATCH (l:Lot {{tlc: '{self.tlc}'}})
            MERGE (f:Facility {{gln: '{self.tlc_source_gln}'}})
            ON CREATE SET f.name = 'TLC-Source-{self.tlc_source_gln}', f.created_at = datetime()
            MERGE (l)-[:ASSIGNED_BY]->(f)
            RETURN l, f
            """
        elif self.tlc_source_fda_reg:
            return f"""
            MATCH (l:Lot {{tlc: '{self.tlc}'}})
            MERGE (f:Facility {{fda_registration: '{self.tlc_source_fda_reg}'}})
            ON CREATE SET f.name = 'TLC-Source-FDA-{self.tlc_source_fda_reg}', f.created_at = datetime()
            MERGE (l)-[:ASSIGNED_BY]->(f)
            RETURN l, f
            """
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
    """

    event_id: str  # Unique event identifier
    type: CTEType
    event_date: str  # ISO date YYYY-MM-DD
    event_time: Optional[str] = None  # ISO time HH:MM:SSZ
    description: Optional[str] = None
    document_id: Optional[str] = None  # Source document reference
    confidence: Optional[float] = None
    tenant_id: Optional[str] = None

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
        return props

    @staticmethod
    def create_cypher() -> str:
        """Return Cypher CREATE statement for TraceEvent node."""
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
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Facility node."""
        return """
        MERGE (f:Facility {gln: $gln})
        ON CREATE SET f += $properties, f.created_at = datetime()
        ON MATCH SET f += $properties
        RETURN f
        """

    @staticmethod
    def merge_by_name_cypher() -> str:
        """Return Cypher MERGE statement for Facility by name (when no GLN)."""
        return """
        MERGE (f:Facility {name: $name})
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
        MERGE (p:FoodItem {name: $name})
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
        return props

    @staticmethod
    def merge_cypher() -> str:
        """Return Cypher MERGE statement for Document node."""
        return """
        MERGE (d:Document {document_id: $document_id})
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
    "CREATE CONSTRAINT facility_gln_unique IF NOT EXISTS FOR (f:Facility) REQUIRE f.gln IS UNIQUE",
    "CREATE CONSTRAINT trace_event_id_unique IF NOT EXISTS FOR (e:TraceEvent) REQUIRE e.event_id IS UNIQUE",
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.document_id IS UNIQUE",
    # TLC Source indexes - support FSMA 204 mandate for tracking lot assignment provenance
    "CREATE INDEX lot_tlc_source_gln_idx IF NOT EXISTS FOR (l:Lot) ON (l.tlc_source_gln)",
    "CREATE INDEX lot_tlc_source_fda_idx IF NOT EXISTS FOR (l:Lot) ON (l.tlc_source_fda_reg)",
    # Performance indexes
    "CREATE INDEX lot_tenant_idx IF NOT EXISTS FOR (l:Lot) ON (l.tenant_id)",
    "CREATE INDEX event_date_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.event_date)",
    "CREATE INDEX event_type_idx IF NOT EXISTS FOR (e:TraceEvent) ON (e.type)",
    "CREATE INDEX facility_fda_reg_idx IF NOT EXISTS FOR (f:Facility) ON (f.fda_registration)",
]
