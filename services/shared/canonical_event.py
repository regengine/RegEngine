"""
Canonical TraceabilityEvent Model.

This is the ONE internal truth model for all FSMA 204 compliance operations.
Every ingestion path (webhook API, CSV upload, XLSX import, EPCIS document,
EDI message) normalizes into this model before persistence.

Downstream services — rules engine, FDA export, graph sync, exception queue,
request-response workflow — consume ONLY this model.

Design principles:
    1. Raw source preserved alongside normalized form (dual payload)
    2. Provenance metadata tracks who/when/how/what-version
    3. Amendment chains are explicit (supersedes_event_id)
    4. Schema is versioned for forward compatibility
    5. KDEs are structured dicts, not key-value pairs

Usage:
    from shared.canonical_event import TraceabilityEvent, normalize_webhook_event

    canonical = normalize_webhook_event(webhook_event, tenant_id, source="webhook_api")
    # canonical is now a TraceabilityEvent ready for persistence
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("canonical-event")

# ---------------------------------------------------------------------------
# Raw-payload size limits (#1290)
# ---------------------------------------------------------------------------
#
# ``raw_payload`` preserves the supplier record verbatim for evidentiary
# chain. But "verbatim" must not mean "unbounded": a 10 MB supplier JSON
# would block the persist transaction, bloat backups, and — combined
# with any downstream template that renders ``raw_payload`` fields
# without escaping — open a stored-XSS vector.
#
# Two knobs:
#
# - ``RAW_PAYLOAD_DEFAULT_MAX_BYTES`` (256 KiB): the default soft cap.
#   Real FSMA 204 records are a few KB each — a 256 KiB envelope is
#   already 10× the 95th-percentile observed record in staging. Can be
#   overridden per deployment via ``REGENGINE_RAW_PAYLOAD_MAX_BYTES``
#   (e.g. for a tenant with unusually verbose EPCIS extensions).
#
# - ``RAW_PAYLOAD_HARD_CEILING_BYTES`` (1 MiB): the absolute maximum.
#   Environment overrides larger than this are clamped. Meant as a
#   backstop against an operator accidentally setting the env var to
#   a value large enough to re-open the DoS/resource-exhaustion risk.
#
# Oversized payloads raise ``ValueError`` at ``prepare_for_persistence``
# time. We deliberately do NOT silently truncate — the whole point of
# ``raw_payload`` is that it's the unmodified source-of-truth; a
# truncated copy is worse than no copy (audit would think it has
# the original but doesn't).

RAW_PAYLOAD_DEFAULT_MAX_BYTES = 256 * 1024          # 256 KiB
RAW_PAYLOAD_HARD_CEILING_BYTES = 1024 * 1024        # 1 MiB


def _raw_payload_max_bytes() -> int:
    """Resolve the effective raw_payload size cap.

    Reads ``REGENGINE_RAW_PAYLOAD_MAX_BYTES`` once per call (so tests and
    hot-reload operators can adjust at runtime). Invalid values fall back
    to the default with a warning; operator overrides above the hard
    ceiling are clamped, also with a warning — we'd rather log noise
    than let a typo (e.g. ``100000000`` meant as ``100_000`` bytes) open
    a DoS vector.
    """
    raw = os.environ.get("REGENGINE_RAW_PAYLOAD_MAX_BYTES")
    if raw is None:
        return RAW_PAYLOAD_DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "raw_payload_max_bytes_invalid env=%r; falling back to default %d",
            raw, RAW_PAYLOAD_DEFAULT_MAX_BYTES,
        )
        return RAW_PAYLOAD_DEFAULT_MAX_BYTES
    if value <= 0:
        logger.warning(
            "raw_payload_max_bytes_non_positive env=%r; falling back to default %d",
            raw, RAW_PAYLOAD_DEFAULT_MAX_BYTES,
        )
        return RAW_PAYLOAD_DEFAULT_MAX_BYTES
    if value > RAW_PAYLOAD_HARD_CEILING_BYTES:
        logger.warning(
            "raw_payload_max_bytes_clamped env=%d ceiling=%d",
            value, RAW_PAYLOAD_HARD_CEILING_BYTES,
        )
        return RAW_PAYLOAD_HARD_CEILING_BYTES
    return value


class RawPayloadTooLargeError(ValueError):
    """Raised when ``raw_payload`` exceeds the configured size cap (#1290).

    A ``ValueError`` subclass so existing ``except ValueError`` branches
    in ingestion keep working — but recognisable to tests and logs as
    the specific size-cap rejection.
    """

    def __init__(self, size_bytes: int, max_bytes: int):
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"raw_payload serialized size {size_bytes} bytes exceeds "
            f"max {max_bytes} bytes (#1290). Set "
            f"REGENGINE_RAW_PAYLOAD_MAX_BYTES to override, up to "
            f"{RAW_PAYLOAD_HARD_CEILING_BYTES} bytes."
        )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CTEType(str, Enum):
    """Critical Tracking Event types per FSMA 204 §1.1310."""
    HARVESTING = "harvesting"
    COOLING = "cooling"
    INITIAL_PACKING = "initial_packing"
    FIRST_LAND_BASED_RECEIVING = "first_land_based_receiving"
    SHIPPING = "shipping"
    RECEIVING = "receiving"
    TRANSFORMATION = "transformation"


class EventStatus(str, Enum):
    """Lifecycle status of a canonical event."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DRAFT = "draft"


class IngestionSource(str, Enum):
    """Known ingestion source systems."""
    WEBHOOK_API = "webhook_api"
    CSV_UPLOAD = "csv_upload"
    XLSX_UPLOAD = "xlsx_upload"
    EPCIS_API = "epcis_api"
    EPCIS_XML = "epcis_xml"
    EDI = "edi"
    MANUAL = "manual"
    MOBILE_CAPTURE = "mobile_capture"
    SUPPLIER_PORTAL = "supplier_portal"
    LEGACY_V002 = "legacy_v002"


class IngestionRunStatus(str, Enum):
    """Processing state of an ingestion batch."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceDocumentType(str, Enum):
    """Types of evidence documents."""
    BOL = "bol"
    INVOICE = "invoice"
    LAB_REPORT = "lab_report"
    PHOTO = "photo"
    TEMPERATURE_LOG = "temperature_log"
    PRODUCTION_RECORD = "production_record"
    PURCHASE_ORDER = "purchase_order"
    CERTIFICATE = "certificate"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Provenance Metadata
# ---------------------------------------------------------------------------

class ProvenanceMetadata(BaseModel):
    """
    Structured provenance for a canonical event.

    Answers: Where did this record come from? How was it normalized?
    What confidence do we have in the mapping?
    """
    source_file_hash: Optional[str] = None
    source_file_name: Optional[str] = None
    ingestion_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    mapper_name: str = "unknown"
    mapper_version: str = "1.0.0"
    normalization_rules_applied: List[str] = Field(default_factory=list)
    original_format: str = "unknown"  # json, csv, xlsx, epcis_xml, epcis_json, edi
    extraction_confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Ingestion Run
# ---------------------------------------------------------------------------

class IngestionRun(BaseModel):
    """Batch provenance — one row per file upload, API call, or EPCIS document."""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID

    source_system: IngestionSource
    source_file_name: Optional[str] = None
    source_file_hash: Optional[str] = None
    source_file_size: Optional[int] = None

    record_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0

    mapper_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    status: IngestionRunStatus = IngestionRunStatus.PROCESSING

    initiated_by: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical TraceabilityEvent
# ---------------------------------------------------------------------------

# #1197: ``SCHEMA_VERSION`` is the integer dispatch version of the
# canonical TraceabilityEvent envelope. It is NOT a semver string — it is
# a monotonically-increasing integer used by consumers to decide whether
# an in-flight message (Kafka topic, task_queue row, outbox entry) is
# understood. Bump this ONLY when the wire format changes in a way that
# requires a migration branch at the consumer. Cosmetic additive changes
# (a new optional field with a safe default) do NOT require a bump; a
# rename, type change, or removal DOES.
#
# Legacy semver strings ("1.0.0", "1.0", "v1") from pre-#1197 events
# deserialize as integer ``1`` — see the ``_coerce_schema_version``
# validator below. This preserves backward compat so old rows in
# ``fsma.traceability_events`` (where the column is TEXT) still hydrate
# cleanly into the Pydantic model.
SCHEMA_VERSION = 1

# #1197: ``KNOWN_VERSIONS`` is the set of envelope versions the current
# process knows how to consume. ``parse_traceability_event`` refuses any
# payload whose ``schema_version`` is not in this set — a loud failure
# is better than a silent "we dropped 20 unknown-version events" data
# loss. Extend this set on the SAME commit that adds consumer handling
# for the new version.
KNOWN_VERSIONS: frozenset[int] = frozenset({1})

# #1197: Legacy semver values from pre-envelope rows. Mapped to integer
# ``1`` on deserialization so old ``fsma.traceability_events`` rows
# (DB column is ``TEXT NOT NULL DEFAULT '1.0.0'``) hydrate cleanly
# without a data migration. New producers emit the integer form.
_LEGACY_SCHEMA_VERSION_STRINGS: frozenset[str] = frozenset({
    "1.0.0", "1.0", "1", "v1", "v1.0", "v1.0.0",
})


class TraceabilityEvent(BaseModel):
    """
    The canonical traceability event — RegEngine's single internal truth model.

    Every ingestion path normalizes into this object. Downstream services
    consume ONLY this model, never format-specific payloads.

    Implements PRD Workstream A requirements:
    - Dual payload preservation (raw_payload + normalized_payload)
    - Structured provenance metadata
    - Amendment chain via supersedes_event_id
    - Schema versioning
    - Confidence scoring
    """

    # Identity
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID

    # Envelope schema version (#1197).
    #
    # Placed near the top of the class so consumers that peek at raw
    # JSON (without hydrating the full model) see it up front. Integer
    # rather than semver string — consumers dispatch on equality with
    # ``KNOWN_VERSIONS``, not range-comparison, so an int is both
    # cheaper and unambiguous. See the module-level ``SCHEMA_VERSION``
    # docstring for bump semantics.
    schema_version: int = SCHEMA_VERSION

    # Source provenance
    source_system: IngestionSource
    source_record_id: Optional[str] = None
    source_file_id: Optional[UUID] = None
    ingestion_run_id: Optional[UUID] = None

    # Event classification
    event_type: CTEType

    # Temporal
    event_timestamp: datetime
    event_timezone: str = "UTC"

    # Product + Lot
    product_reference: Optional[str] = None
    lot_reference: Optional[str] = None
    traceability_lot_code: str = Field(..., min_length=3)
    # #1249: ge=0 (not gt=0). A zero quantity is a legitimate FSMA value —
    # empty-pallet receipt, full-recall correction, zero-loss inspection —
    # and must round-trip through the canonical store. The old gt=0
    # constraint caused silent divergence between ``fsma.cte_events``
    # (which stored the true zero) and ``traceability_events`` (where
    # the validator raised and the write was swallowed by a best-effort
    # try/except). FDA exports run off the canonical store, so a zero
    # event that vanished from canonical was a regulator-visible gap.
    quantity: float = Field(..., ge=0)
    unit_of_measure: str

    # Entity + Facility references
    from_entity_reference: Optional[str] = None
    to_entity_reference: Optional[str] = None
    from_facility_reference: Optional[str] = None
    to_facility_reference: Optional[str] = None

    # Transport
    transport_reference: Optional[str] = None

    # Structured KDEs
    kdes: Dict[str, Any] = Field(default_factory=dict)

    # Dual payload preservation
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    normalized_payload: Dict[str, Any] = Field(default_factory=dict)

    # Provenance
    provenance_metadata: ProvenanceMetadata = Field(
        default_factory=lambda: ProvenanceMetadata()
    )

    # Quality
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    status: EventStatus = EventStatus.ACTIVE

    # Amendment chain
    supersedes_event_id: Optional[UUID] = None

    # Integrity (computed during persistence)
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None
    idempotency_key: Optional[str] = None

    # EPCIS interop
    epcis_event_type: Optional[str] = None
    epcis_action: Optional[str] = None
    epcis_biz_step: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    amended_at: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True}

    @field_validator("schema_version", mode="before")
    @classmethod
    def _coerce_schema_version(cls, v: Any) -> int:
        """Accept legacy semver strings and ``None`` on deserialization (#1197).

        Before this issue the field was ``str`` with values like
        ``"1.0.0"`` persisted to ``fsma.traceability_events.schema_version``
        (a TEXT column). To avoid a backfill migration, we accept those
        legacy strings here and coerce them to integer ``1`` — the
        version they correspond to.

        ``None`` and missing both fall through to the ``int = 1`` default
        via Pydantic's normal default handling; this validator only runs
        when a value was explicitly provided, so an explicit ``None``
        (e.g. from a JSON row where the column was NULL) also normalises
        to ``1``.

        Unknown strings raise — we'd rather break loudly on a version we
        don't understand than silently map it to ``1`` and merge two
        incompatible schemas.
        """
        if v is None:
            return SCHEMA_VERSION
        if isinstance(v, bool):
            # bool is a subclass of int in Python — reject before the
            # int branch swallows True/False as 1/0.
            raise ValueError(f"schema_version must be int, got bool: {v!r}")
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            stripped = v.strip()
            if stripped in _LEGACY_SCHEMA_VERSION_STRINGS:
                return 1
            # Try to parse "2", "3", etc. — a producer that used a
            # plain numeric string for a valid integer version should
            # still work. But "2.1" (semver for a version we don't
            # know) must fail rather than silently floor.
            try:
                return int(stripped)
            except ValueError:
                raise ValueError(
                    f"schema_version string not recognised: {v!r}. "
                    f"Known legacy strings: {sorted(_LEGACY_SCHEMA_VERSION_STRINGS)}"
                )
        raise TypeError(f"schema_version must be int or legacy str, got {type(v).__name__}")

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        """Parse any reasonable timestamp format to datetime."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        if isinstance(v, str):
            # Handle Z suffix
            v = v.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                import dateutil.parser
                dt = dateutil.parser.parse(v, fuzzy=False)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
        raise ValueError(f"Cannot parse timestamp: {v}")

    def compute_sha256_hash(self) -> str:
        """Compute SHA-256 of canonical form for integrity verification."""
        canonical = "|".join([
            str(self.event_id),
            self.event_type.value,
            self.traceability_lot_code,
            self.product_reference or "",
            str(self.quantity),
            self.unit_of_measure,
            self.from_facility_reference or "",
            self.to_facility_reference or "",
            self.event_timestamp.isoformat(),
            json.dumps(self.kdes, sort_keys=True, default=str),
        ])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compute_idempotency_key(self) -> str:
        """Compute deduplication key from content-addressable fields.

        Uses ``default=str`` on ``json.dumps`` for the same reason
        ``compute_event_hash`` above does and ``compute_idempotency_key``
        in ``shared.cte_persistence.hashing`` does (#1313): a KDE
        carrying a ``datetime`` or ``Decimal`` otherwise raises
        ``TypeError`` mid-insert and loses the event. ``str()`` coercion
        is locale/version-fragile and a future improvement is to
        normalize KDE values to JSON-safe primitives before hashing —
        tracked with the cte_persistence retirement work (#1335).

        NOTE: this formula diverges from
        ``cte_persistence.hashing.compute_idempotency_key`` by using
        ``from_facility`` + ``to_facility`` instead of
        ``location_gln`` + ``location_name``. The dedup semantics are
        therefore DIFFERENT: the same real-world event persisted via
        both paths produces different keys in each table. This is
        intentional during dual-write — each table dedups independently
        with its own scope — but it means ``cte_events`` and
        ``traceability_events`` are NOT reconcilable by idempotency_key
        alone. Cross-table reconciliation should use ``sha256_hash``.
        """
        canonical = json.dumps(
            {
                "event_type": self.event_type.value,
                "tlc": self.traceability_lot_code,
                "timestamp": self.event_timestamp.isoformat(),
                "source": self.source_system.value,
                "from_facility": self.from_facility_reference or "",
                "to_facility": self.to_facility_reference or "",
                "kdes": self.kdes,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def build_normalized_payload(self) -> Dict[str, Any]:
        """Build the normalized payload dict for storage."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value,
            "traceability_lot_code": self.traceability_lot_code,
            "product_reference": self.product_reference,
            "lot_reference": self.lot_reference,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "event_timestamp": self.event_timestamp.isoformat(),
            "event_timezone": self.event_timezone,
            "from_entity_reference": self.from_entity_reference,
            "to_entity_reference": self.to_entity_reference,
            "from_facility_reference": self.from_facility_reference,
            "to_facility_reference": self.to_facility_reference,
            "transport_reference": self.transport_reference,
            "kdes": self.kdes,
            "schema_version": self.schema_version,
        }

    def prepare_for_persistence(self) -> "TraceabilityEvent":
        """
        Finalize the event for storage: compute hashes, build normalized payload.

        Call this after normalization but before writing to the database.

        #1290: enforces the raw_payload size cap BEFORE hashing so an
        oversized event is rejected at prep time rather than wasting
        chain-hash computation and a per-tenant advisory lock. The
        check is a measure against (a) DoS via 10 MB supplier JSONs
        blocking the persist transaction, and (b) stored XSS in any
        audit UI that renders raw_payload fields — a bounded payload
        bounds the attacker's blast radius.
        """
        self._enforce_raw_payload_size()
        self.sha256_hash = self.compute_sha256_hash()
        self.idempotency_key = self.compute_idempotency_key()
        self.normalized_payload = self.build_normalized_payload()
        return self

    def _enforce_raw_payload_size(self) -> None:
        """Reject oversized ``raw_payload`` (#1290).

        Serializes once with the same ``default=str`` that the writer
        uses, so the size we check is the size we'd actually persist.
        Silent truncation is explicitly rejected: the whole point of
        ``raw_payload`` is an unmodified source-of-truth; a truncated
        copy is worse than none because auditors would assume fidelity.
        """
        if not self.raw_payload:
            return
        max_bytes = _raw_payload_max_bytes()
        # Matches the writer's serialization exactly so the bytes we
        # measure are the bytes we'd write.
        serialized = json.dumps(self.raw_payload, default=str)
        size = len(serialized.encode("utf-8"))
        if size > max_bytes:
            raise RawPayloadTooLargeError(size, max_bytes)


# ---------------------------------------------------------------------------
# Envelope-version dispatch (#1197)
# ---------------------------------------------------------------------------
#
# Cross-service messaging (Kafka, fsma.task_queue, graph_outbox) exposes
# a latency window between a producer bumping the canonical schema and
# every consumer redeploying. Without a version stamp, new-shape events
# land in old-shape parsers and either crash loudly or — worse — parse
# into a truncated object and silently drop the added fields. Both modes
# are hostile for an audit log.
#
# ``parse_traceability_event`` is the single entry point consumers should
# call to hydrate a raw payload. It:
#
#   1. Normalises the input to a dict (bytes → JSON, str → JSON, dict
#      passthrough). Matches the surface area of
#      ``TraceabilityEvent.model_validate_json`` / ``model_validate``.
#   2. Peeks at ``schema_version`` BEFORE validation. A missing field
#      defaults to 1 — legacy events that predate the envelope were all
#      effectively v1, and rejecting them would delete audit history
#      at deploy time.
#   3. Refuses unknown versions with a ``ValueError`` carrying the
#      ``schema_version_unsupported:<v>`` tag. The prefix is grep-friendly
#      for metrics and DLQ taxonomy so operators can count these.
#   4. Delegates to ``TraceabilityEvent.model_validate`` for the actual
#      field-level validation.
#
# The helper is deliberately lightweight — consumers do not have to
# adopt it to benefit from the new field, but they SHOULD migrate on
# their own schedule. The #1197 PR updates only 1-2 demonstration call
# sites; the rest is a staged rollout.


def parse_traceability_event(payload: Any) -> "TraceabilityEvent":
    """Dispatch parse for a canonical ``TraceabilityEvent`` payload (#1197).

    Accepts ``bytes``, ``str``, or ``dict``. Peeks at ``schema_version``
    (default 1 when absent — see module docstring for the legacy path)
    and refuses values not in :data:`KNOWN_VERSIONS` with
    ``ValueError("schema_version_unsupported:<v>")``.

    This is the RECOMMENDED entry point for any consumer that reads
    ``TraceabilityEvent`` from a wire format (Kafka message value,
    task_queue ``payload`` JSON, graph_outbox row, webhook replay). It
    does NOT replace :meth:`TraceabilityEvent.model_validate` for
    in-process construction — use the constructor for those.

    Parameters
    ----------
    payload:
        ``bytes`` / ``str`` — parsed as JSON then validated.
        ``dict`` — validated directly (no copy; the caller keeps
        ownership of the dict, but the Pydantic model does its own
        internal conversion so mutations after the call do not affect
        the returned model).

    Raises
    ------
    ValueError
        If the JSON is unparseable, if ``schema_version`` is a value
        outside :data:`KNOWN_VERSIONS`, or if field-level validation
        fails (propagated from Pydantic).
    TypeError
        If ``payload`` is not ``bytes``/``str``/``dict``.
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"traceability_event_payload_not_json: {exc}") from exc
    elif isinstance(payload, str):
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"traceability_event_payload_not_json: {exc}") from exc
    elif isinstance(payload, dict):
        raw = payload
    else:
        raise TypeError(
            f"parse_traceability_event expected bytes/str/dict, "
            f"got {type(payload).__name__}"
        )

    if not isinstance(raw, dict):
        raise ValueError(
            f"traceability_event_payload_not_object: got {type(raw).__name__}"
        )

    # Peek at the envelope version without triggering full validation.
    # We MUST normalise the peeked value through the same coercion the
    # Pydantic field uses so that "1.0.0" (a legacy string) is compared
    # against KNOWN_VERSIONS as integer 1 rather than a raw string that
    # is trivially not-in-set.
    raw_version = raw.get("schema_version", SCHEMA_VERSION)
    try:
        peeked = TraceabilityEvent._coerce_schema_version(raw_version)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"schema_version_unsupported:{raw_version!r} "
            f"(coercion failed: {exc})"
        ) from exc

    if peeked not in KNOWN_VERSIONS:
        raise ValueError(f"schema_version_unsupported:{peeked}")

    return TraceabilityEvent.model_validate(raw)


# ---------------------------------------------------------------------------
# Evidence Attachment
# ---------------------------------------------------------------------------

class EvidenceAttachment(BaseModel):
    """Source document linked to a canonical event for evidentiary chain."""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_id: UUID

    document_type: EvidenceDocumentType
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    storage_uri: Optional[str] = None
    storage_bucket: Optional[str] = None

    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    extraction_status: str = "pending"

    uploaded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Normalization Functions
# ---------------------------------------------------------------------------

def normalize_webhook_event(
    event: Any,
    tenant_id: str,
    source: str = "webhook_api",
    raw_payload: Optional[Dict[str, Any]] = None,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent:
    """
    Normalize a webhook IngestEvent into a canonical TraceabilityEvent.

    This is the bridge between the existing webhook ingestion format
    and the canonical model. The raw webhook payload is preserved verbatim.
    """
    # Build raw payload from webhook event if not provided
    if raw_payload is None:
        raw_payload = {
            "cte_type": event.cte_type.value if hasattr(event.cte_type, "value") else event.cte_type,
            "source": source,
            "traceability_lot_code": event.traceability_lot_code,
            "product_description": event.product_description,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "location_gln": event.location_gln,
            "location_name": event.location_name,
            "timestamp": event.timestamp,
            "kdes": event.kdes,
        }
        if hasattr(event, "input_traceability_lot_codes") and event.input_traceability_lot_codes:
            raw_payload["input_traceability_lot_codes"] = event.input_traceability_lot_codes

    # Extract facility references from KDEs
    kdes = dict(event.kdes) if event.kdes else {}
    kdes.setdefault("ingest_source", source)

    # Promote input_traceability_lot_codes into kdes so _create_transformation_links()
    # can find them under the expected "input_lot_codes" key.  The webhook model keeps
    # this as a top-level field; canonical persistence looks inside kdes.
    if hasattr(event, "input_traceability_lot_codes") and event.input_traceability_lot_codes:
        kdes.setdefault("input_lot_codes", event.input_traceability_lot_codes)
    from_facility = (
        event.location_gln
        or kdes.get("ship_from_gln")
        or kdes.get("ship_from_location")
        or event.location_name
    )
    to_facility = (
        kdes.get("ship_to_gln")
        or kdes.get("ship_to_location")
        or kdes.get("receiving_location")
    )

    # For shipping/receiving, map directional references
    event_type_val = event.cte_type.value if hasattr(event.cte_type, "value") else event.cte_type
    if event_type_val == "shipping":
        from_facility = from_facility or event.location_name
    elif event_type_val == "receiving":
        to_facility = to_facility or event.location_name or event.location_gln

    # Build provenance
    provenance = ProvenanceMetadata(
        mapper_name="webhook_v2_normalizer",
        mapper_version="1.0.0",
        original_format="json",
        normalization_rules_applied=["webhook_kde_extraction", "facility_reference_mapping"],
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id=None,
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=CTEType(event_type_val),
        event_timestamp=event.timestamp,
        product_reference=event.product_description,
        lot_reference=event.traceability_lot_code,
        traceability_lot_code=event.traceability_lot_code,
        quantity=event.quantity,
        unit_of_measure=event.unit_of_measure,

        from_facility_reference=from_facility,
        to_facility_reference=to_facility,
        from_entity_reference=kdes.get("ship_from_entity") or kdes.get("harvester_business_name"),
        to_entity_reference=kdes.get("ship_to_entity") or kdes.get("immediate_previous_source"),
        transport_reference=kdes.get("carrier") or kdes.get("transport_reference"),

        kdes=kdes,
        raw_payload=raw_payload,
        provenance_metadata=provenance,
    )

    return canonical.prepare_for_persistence()


def _extract_epcis_quantity(
    epcis_data: Dict[str, Any],
) -> tuple[Optional[float], Optional[str]]:
    """Extract (quantity, uom) from an EPCIS event.

    Handles both the real EPCIS 2.0 shape —
    ``extension.quantityList[0].quantity`` — and the flattened
    ``quantity.value`` shape used by some test harnesses and legacy
    webhook shims. Returns ``(None, None)`` when no quantity is present
    so the caller can decide how to respond (reject vs. preserve vs.
    default). #1249: this function must never fabricate a value — the
    whole point of the fix is that silent 1.0 defaulting falsified FDA
    traceability records.
    """
    # Real EPCIS 2.0 shape — quantityList is nested under extension
    # (some shims put it at the top level, handle both).
    quantity_list = (
        epcis_data.get("extension", {}).get("quantityList")
        or epcis_data.get("quantityList")
        or []
    )
    if quantity_list and isinstance(quantity_list, list) and isinstance(quantity_list[0], dict):
        raw = quantity_list[0].get("quantity")
        uom = quantity_list[0].get("uom")
        if raw is not None:
            try:
                return float(raw), uom
            except (TypeError, ValueError):
                return None, uom

    # Flattened legacy / test shape — quantity.value
    flat = epcis_data.get("quantity")
    if isinstance(flat, dict):
        raw = flat.get("value")
        uom = flat.get("uom")
        if raw is not None:
            try:
                return float(raw), uom
            except (TypeError, ValueError):
                return None, uom

    return None, None


def _require_epcis_quantity(epcis_data: Dict[str, Any]) -> float:
    """Return the EPCIS quantity or raise :class:`ValueError`.

    Callers that need a definitive numeric quantity (the canonical
    store, FDA export, rules engine) use this wrapper so a missing or
    non-numeric value is loud rather than silently defaulted. #1249.
    """
    value, _uom = _extract_epcis_quantity(epcis_data)
    if value is None:
        raise ValueError(
            "EPCIS event has no numeric quantity — cannot emit canonical "
            "TraceabilityEvent. Supply quantity via extension.quantityList "
            "or reject the event before normalization (#1249)."
        )
    return value


def normalize_epcis_event(
    epcis_data: Dict[str, Any],
    tenant_id: str,
    ingestion_run_id: Optional[str] = None,
) -> TraceabilityEvent:
    """
    Normalize an EPCIS 2.0 event dict into a canonical TraceabilityEvent.

    Maps EPCIS vocabulary (bizStep, readPoint, bizLocation) to canonical fields.

    #1249 — quantity handling:
      * Extracts quantity from ``extension.quantityList[0]`` (real EPCIS
        shape) OR ``quantity.value`` (flattened shape). Either path can
        carry the value; whichever is present wins.
      * If no quantity is present or the value is non-numeric, raises
        :class:`ValueError`. We no longer default to 1 — the old default
        silently fabricated FDA traceability records.
      * Zero is preserved (consistent with FSMAEvent ``ge=0`` and the
        updated canonical constraint).
    """
    # Map EPCIS bizStep to CTE type
    biz_step = epcis_data.get("bizStep", "")
    event_type_map = {
        "shipping": CTEType.SHIPPING,
        "receiving": CTEType.RECEIVING,
        "commissioning": CTEType.INITIAL_PACKING,
        "transforming": CTEType.TRANSFORMATION,
        "harvesting": CTEType.HARVESTING,
        "cooling": CTEType.COOLING,
    }
    # Extract CTE type from bizStep URI or direct value
    cte_type = CTEType.RECEIVING  # default
    for key, val in event_type_map.items():
        if key in biz_step.lower():
            cte_type = val
            break

    # Extract identifiers
    epc_list = epcis_data.get("epcList", [])
    tlc = ""
    gtin = None
    for epc in epc_list:
        if "sgtin" in epc.lower() or "lgtin" in epc.lower():
            # Extract GTIN and serial/lot from EPC URI
            parts = epc.rsplit(".", 1)
            if len(parts) == 2:
                tlc = parts[-1]
                gtin_part = parts[0].rsplit(":", 1)
                if gtin_part:
                    gtin = gtin_part[-1]
    if not tlc:
        tlc = epcis_data.get("traceability_lot_code", epcis_data.get("lotNumber", "UNKNOWN"))

    # Build KDEs from EPCIS extensions
    kdes: Dict[str, Any] = {}
    if gtin:
        kdes["gtin"] = gtin
    extensions = epcis_data.get("ilmd", {})
    extensions.update(epcis_data.get("extension", {}))
    for k, v in extensions.items():
        kdes[k] = v

    provenance = ProvenanceMetadata(
        mapper_name="epcis_normalizer",
        mapper_version="1.0.0",
        original_format="epcis_json" if not epcis_data.get("_xml_source") else "epcis_xml",
        normalization_rules_applied=["epcis_bizstep_mapping", "epc_uri_parsing"],
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.EPCIS_API,
        source_record_id=epcis_data.get("eventID"),
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=cte_type,
        event_timestamp=epcis_data.get("eventTime", datetime.now(timezone.utc).isoformat()),
        event_timezone=epcis_data.get("eventTimeZoneOffset", "UTC"),

        product_reference=epcis_data.get("productDescription", kdes.get("gtin", "")),
        lot_reference=tlc,
        traceability_lot_code=tlc if len(tlc) >= 3 else f"EPCIS-{tlc or 'UNKNOWN'}",
        # #1249: extract from real EPCIS shape; do NOT fabricate on missing.
        # Raising here forces ingestion code to surface the problem rather
        # than silently producing a 1.0-quantity canonical row.
        quantity=_require_epcis_quantity(epcis_data),
        unit_of_measure=_extract_epcis_quantity(epcis_data)[1] or "each",

        from_facility_reference=epcis_data.get("readPoint", {}).get("id") if isinstance(epcis_data.get("readPoint"), dict) else epcis_data.get("readPoint"),
        to_facility_reference=epcis_data.get("bizLocation", {}).get("id") if isinstance(epcis_data.get("bizLocation"), dict) else epcis_data.get("bizLocation"),

        kdes=kdes,
        raw_payload=epcis_data,
        provenance_metadata=provenance,

        epcis_event_type=epcis_data.get("type", epcis_data.get("eventType")),
        epcis_action=epcis_data.get("action"),
        epcis_biz_step=biz_step,
    )

    return canonical.prepare_for_persistence()


def normalize_csv_row(
    row: Dict[str, Any],
    tenant_id: str,
    column_mapping: Dict[str, str],
    ingestion_run_id: Optional[str] = None,
    source_file_name: Optional[str] = None,
    row_number: Optional[int] = None,
) -> TraceabilityEvent:
    """
    Normalize a CSV/XLSX row dict into a canonical TraceabilityEvent.

    column_mapping maps source column names to canonical field names.
    Unmapped columns are stored in kdes.
    """
    # Apply column mapping
    mapped: Dict[str, Any] = {}
    kdes: Dict[str, Any] = {}
    for src_col, value in row.items():
        if src_col in column_mapping:
            mapped[column_mapping[src_col]] = value
        else:
            # Unmapped columns become KDEs
            if value is not None and str(value).strip():
                kdes[src_col] = value

    # Required fields with fallbacks
    event_type_raw = str(mapped.get("event_type", "receiving")).lower().strip()
    cte_type_map = {
        "harvest": "harvesting", "harvesting": "harvesting",
        "cool": "cooling", "cooling": "cooling",
        "pack": "initial_packing", "initial_packing": "initial_packing",
        "initial packing": "initial_packing",
        "first_land_based_receiving": "first_land_based_receiving",
        "ship": "shipping", "shipping": "shipping",
        "receive": "receiving", "receiving": "receiving",
        "transform": "transformation", "transformation": "transformation",
    }
    event_type = cte_type_map.get(event_type_raw, "receiving")

    rules_applied = ["csv_column_mapping"]
    confidence = 1.0

    # Detect if event type was inferred
    if event_type_raw not in cte_type_map:
        rules_applied.append("event_type_inference")
        confidence = 0.7

    provenance = ProvenanceMetadata(
        source_file_name=source_file_name,
        mapper_name="csv_normalizer",
        mapper_version="1.0.0",
        original_format="csv",
        normalization_rules_applied=rules_applied,
        extraction_confidence=confidence,
    )

    canonical = TraceabilityEvent(
        tenant_id=UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id,
        source_system=IngestionSource.CSV_UPLOAD,
        source_record_id=str(row_number) if row_number is not None else None,
        ingestion_run_id=UUID(ingestion_run_id) if ingestion_run_id else None,

        event_type=CTEType(event_type),
        event_timestamp=mapped.get("event_timestamp", mapped.get("timestamp", datetime.now(timezone.utc).isoformat())),

        product_reference=mapped.get("product_description", mapped.get("product_reference", "")),
        lot_reference=mapped.get("lot_reference", mapped.get("traceability_lot_code", "")),
        traceability_lot_code=mapped.get("traceability_lot_code", mapped.get("tlc", "UNKNOWN")),
        quantity=float(mapped.get("quantity", 1)),
        unit_of_measure=str(mapped.get("unit_of_measure", "each")).lower(),

        from_facility_reference=mapped.get("from_facility_reference", mapped.get("ship_from_location", mapped.get("location_gln"))),
        to_facility_reference=mapped.get("to_facility_reference", mapped.get("ship_to_location")),
        from_entity_reference=mapped.get("from_entity_reference"),
        to_entity_reference=mapped.get("to_entity_reference"),
        transport_reference=mapped.get("transport_reference", mapped.get("carrier")),

        kdes=kdes,
        raw_payload=row,
        provenance_metadata=provenance,
        confidence_score=confidence,
    )

    return canonical.prepare_for_persistence()
