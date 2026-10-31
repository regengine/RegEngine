"""
RegEngine SDK Data Models

Deserialisation contract (#2933): the dataclass constructors are strict —
an unrecognised keyword raises ``TypeError`` rather than silently dropping a
field. Server payloads, whose key names differ from the SDK field names, are
mapped by the ``from_api`` classmethods (``Record``, ``Facility``,
``TimelineEvent``), which ignore keys the SDK does not model. The remaining
models keep a kwargs constructor that reads every field through
``kwargs.get``, so unknown keys are likewise ignored and no field is unset.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


def _first(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first present, non-None value among ``keys``.

    Lets a model read both the canonical server key
    (``traceability_lot_code``) and any short alias (``tlc``) — the same
    alias handling ``verify_records._first`` uses.
    """
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return default


class CTEType(str, Enum):
    """Critical Tracking Event types per FSMA 204."""

    HARVESTING = "HARVESTING"
    COOLING = "COOLING"
    INITIAL_PACKING = "INITIAL_PACKING"
    FIRST_LAND_BASED_RECEIVING = "FIRST_LAND_BASED_RECEIVING"
    SHIPPING = "SHIPPING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"


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

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "Record":
        """Build a ``Record`` from a ``GET /api/v1/records`` response row.

        The canonical endpoint emits the server's key names (``event_id``,
        ``event_type``, ``traceability_lot_code``, ...); this maps them onto
        the SDK field names and ignores keys the SDK does not model.
        """
        return cls(
            id=_first(payload, "event_id", "id", default=""),
            tlc=_first(payload, "traceability_lot_code", "tlc", default=""),
            cte_type=_first(payload, "event_type", "cte_type", default=""),
            location=_first(payload, "from_facility_reference", "location", default=""),
            quantity=_first(payload, "quantity", default=0.0),
            quantity_uom=_first(payload, "unit_of_measure", "quantity_uom", default=""),
            event_date=_first(payload, "event_timestamp", "event_date", default=""),
            product_description=_first(payload, "product_reference", "product_description"),
            reference_document=_first(payload, "reference_document"),
            input_tlcs=_first(payload, "input_tlcs"),
            created_at=_first(payload, "created_at"),
            hash=_first(payload, "sha256_hash", "hash"),
        )


@dataclass
class Facility:
    """A facility in the supply chain."""

    id: str
    gln: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    facility_type: Optional[str] = None

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "Facility":
        """Build a ``Facility`` from a facility object in a trace response.

        Trace results carry ``gln``/``name``/``address``/``phone``/``facility_type``
        with no separate identifier, so ``id`` falls back to the GLN. Keys
        the SDK does not model are ignored.
        """
        gln = _first(payload, "gln", default="")
        return cls(
            id=_first(payload, "facility_id", "id", default=gln),
            gln=gln,
            name=_first(payload, "name", default=""),
            address=_first(payload, "address"),
            phone=_first(payload, "phone"),
            facility_type=_first(payload, "facility_type", "type"),
        )


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

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "TimelineEvent":
        """Build a ``TimelineEvent`` from a timeline response entry.

        ``GET /api/v1/fsma/traceability/timeline/{tlc}`` emits ``type``,
        ``event_date`` and a nested ``facility`` object (or ``None``); the
        facility name supplies ``location``. Unknown keys are ignored.
        """
        facility = payload.get("facility") or {}
        return cls(
            cte=_first(payload, "type", "cte_type", "cte", default=""),
            date=_first(payload, "event_date", "date", default=""),
            location=_first(payload, "location") or _first(facility, "name", "gln", default=""),
            quantity=_first(payload, "quantity"),
            description=_first(payload, "description", "product_description"),
        )


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
