"""
RegEngine SDK Data Models
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict
from enum import Enum


class CTEType(str, Enum):
    """Critical Tracking Event types per FSMA 204."""
    GROWING = "GROWING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"
    SHIPPING = "SHIPPING"
    FIRST_LAND_RECEIVING = "FIRST_LAND_RECEIVING"
    COOLING = "COOLING"
    INITIAL_PACKING = "INITIAL_PACKING"


@dataclass
class Record:
    """A traceability record for a Critical Tracking Event."""
    id: str
    tlc: str
    cte_type: str
    location: str
    quantity: float
    quantity_uom: str
    event_date: str
    product_description: Optional[str] = None
    reference_document: Optional[str] = None
    input_tlcs: Optional[List[str]] = None
    created_at: Optional[str] = None
    hash: Optional[str] = None
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class Facility:
    """A facility in the supply chain."""
    id: str
    gln: str
    name: str
    address: Optional[str] = None
    facility_type: Optional[str] = None
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class TraceResult:
    """Result of a forward or backward trace."""
    lot_id: str
    facilities: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    source_lots: List[str] = field(default_factory=list)
    hop_count: int = 0
    trace_duration_ms: Optional[int] = None
    
    def __init__(self, **kwargs):
        self.facilities = kwargs.get("facilities", [])
        self.events = kwargs.get("events", [])
        self.source_lots = kwargs.get("source_lots", [])
        self.hop_count = kwargs.get("hop_count", 0)
        self.lot_id = kwargs.get("lot_id", "")
        self.trace_duration_ms = kwargs.get("trace_duration_ms")


@dataclass
class TimelineEvent:
    """A single event in a lot's timeline."""
    cte: str
    date: str
    location: str
    quantity: Optional[float] = None
    description: Optional[str] = None
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class FTLResult:
    """Result of FDA Food Traceability List check."""
    category: str
    covered: bool
    risk_level: str
    ctes: List[str] = field(default_factory=list)
    kdes: List[str] = field(default_factory=list)
    exclusions: Optional[str] = None
    examples: Optional[str] = None
    
    def __init__(self, **kwargs):
        self.category = kwargs.get("category", "")
        self.covered = kwargs.get("covered", False)
        self.risk_level = kwargs.get("risk_level", "")
        self.ctes = kwargs.get("ctes", [])
        self.kdes = kwargs.get("kdes", [])
        self.exclusions = kwargs.get("exclusions")
        self.examples = kwargs.get("examples")


@dataclass
class RecallDrill:
    """A mock recall drill for FSMA 204 compliance testing."""
    drill_id: str
    status: str
    target_tlc: str
    drill_type: str
    severity: str
    created_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    facilities_affected: int = 0
    
    def __init__(self, **kwargs):
        self.drill_id = kwargs.get("drill_id", kwargs.get("id", ""))
        self.status = kwargs.get("status", "")
        self.target_tlc = kwargs.get("target_tlc", "")
        self.drill_type = kwargs.get("drill_type", kwargs.get("type", ""))
        self.severity = kwargs.get("severity", "")
        self.created_at = kwargs.get("created_at", "")
        self.completed_at = kwargs.get("completed_at")
        self.duration_seconds = kwargs.get("duration_seconds")
        self.facilities_affected = kwargs.get("facilities_affected", 0)


@dataclass
class ReadinessScore:
    """FSMA 204 recall readiness assessment."""
    readiness_score: int
    recommendations: List[str] = field(default_factory=list)
    last_drill_date: Optional[str] = None
    average_drill_seconds: Optional[int] = None
    sla_compliance_percentage: float = 0.0
    
    def __init__(self, **kwargs):
        self.readiness_score = kwargs.get("readiness_score", 0)
        self.recommendations = kwargs.get("recommendations", [])
        self.last_drill_date = kwargs.get("last_drill", kwargs.get("last_drill_date"))
        self.average_drill_seconds = kwargs.get("average_completion_seconds", kwargs.get("average_drill_seconds"))
        self.sla_compliance_percentage = kwargs.get("sla_met_percentage", kwargs.get("sla_compliance_percentage", 0.0))
