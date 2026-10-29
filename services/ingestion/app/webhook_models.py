"""
Webhook Ingestion Models.

Pydantic models for the webhook ingestion endpoint.
Defines the payload structure for external systems to push
FSMA 204 traceability events into RegEngine.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from shared.fsma_validation import calculate_gs1_check_digit, is_location_description_complete

_gln_logger = logging.getLogger("gln-validation")


def validate_gln(gln: str) -> tuple[bool, str | None]:
    """Validate a GS1 Global Location Number (13-digit with mod-10 check digit).

    Returns (is_valid, error_message). Standalone helper for use outside Pydantic.
    Delegates the GS1 mod-10 check-digit math to the shared canonical helper so
    ingestion and the rest of the platform share a single source of truth.
    """
    clean = re.sub(r"\D", "", gln)
    if len(clean) != 13:
        return False, f"GLN must be exactly 13 digits, got {len(clean)}"
    expected = calculate_gs1_check_digit(clean[:-1])
    if int(clean[-1]) != expected:
        return False, f"GLN check digit invalid: expected {expected}, got {clean[-1]}"
    return True, None


class WebhookCTEType(str, Enum):
    """CTE types accepted by the webhook endpoint.

    The 7 canonical FSMA 204 CTEs (per 21 CFR 1.1310) are: harvesting,
    cooling, initial_packing, first_land_based_receiving, shipping,
    receiving, transformation.  GROWING is accepted for ingest
    backwards-compatibility but normalizes to farm metadata, not a CTE.
    """

    GROWING = "growing"  # legacy/internal — not an FDA-defined CTE
    HARVESTING = "harvesting"
    COOLING = "cooling"
    INITIAL_PACKING = "initial_packing"
    FIRST_LAND_BASED_RECEIVING = "first_land_based_receiving"
    SHIPPING = "shipping"
    RECEIVING = "receiving"
    TRANSFORMATION = "transformation"


# Valid units of measure for FSMA 204 traceability records
VALID_UNITS_OF_MEASURE = {
    "lbs",
    "kg",
    "oz",
    "g",
    "tons",
    "mt",  # weight
    "cases",
    "cartons",
    "boxes",
    "crates",
    "bins",  # containers
    "pallets",
    "totes",
    "bags",
    "sacks",  # bulk
    "each",
    "units",
    "pieces",
    "count",  # discrete
    "gallons",
    "liters",
    "barrels",
    "bushels",  # volume
}


# The ingest contract version advertised to integrators (notably the
# inflow-lab simulator, which pins the same value in app/contract.py).
# Bump BOTH sides together whenever the wire contract changes in a way an
# integrator must react to: this REQUIRED_KDES_BY_CTE table, required
# headers (API key / tenant / Idempotency-Key / HMAC), payload shape, or
# validation semantics. Exposed via /health as inflow_contract_version so
# deployed instances can detect skew; the Inflow Lab Contract CI asserts
# cross-repo equality.
INFLOW_CONTRACT_VERSION = "2"


# Required KDEs per CTE type (§1.1325–§1.1350)
REQUIRED_KDES_BY_CTE: Dict[WebhookCTEType, List[str]] = {
    WebhookCTEType.HARVESTING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "harvest_date",
        "location_name",
        "reference_document",  # §1.1325(a)(1)(viii)
    ],
    WebhookCTEType.COOLING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "cooling_date",
        "location_name",
        "reference_document",  # §1.1325(b)(1)(vii)
    ],
    WebhookCTEType.INITIAL_PACKING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "packing_date",
        "location_name",
        "reference_document",  # §1.1330(a)(16)
        "harvester_business_name",  # §1.1330(a)(7)
        "harvester_business_phone",  # §1.1330(a)(7); contract v2
    ],
    WebhookCTEType.FIRST_LAND_BASED_RECEIVING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "landing_date",
        "receiving_location",
        "reference_document",  # §1.1335(g)
    ],
    WebhookCTEType.SHIPPING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "ship_date",
        "ship_from_location",
        "ship_to_location",
        "reference_document",  # §1.1340(a)(8)
        "tlc_source_reference",  # §1.1340(a)(7)
    ],
    WebhookCTEType.RECEIVING: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "receive_date",
        "receiving_location",
        "immediate_previous_source",  # §1.1345(a)(4)
        "reference_document",  # §1.1345(a)(8)
        "tlc_source_reference",  # §1.1345(a)(7)
    ],
    WebhookCTEType.TRANSFORMATION: [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "transformation_date",
        "location_name",
        "reference_document",  # §1.1350(a)(2)(vi)
    ],
}


class IngestEvent(BaseModel):
    """A single CTE event to ingest."""

    _edi_allow_incomplete_location: bool = PrivateAttr(default=False)

    cte_type: WebhookCTEType = Field(..., description="Critical Tracking Event type")
    traceability_lot_code: str = Field(..., description="Traceability Lot Code (TLC)", min_length=3)
    product_description: str = Field(..., description="Human-readable product name", min_length=1, max_length=500)
    quantity: float = Field(..., description="Numeric quantity", gt=0, allow_inf_nan=False)
    unit_of_measure: str = Field(..., description="Unit (cases, lbs, kg, pallets, etc.)")
    location_gln: Optional[str] = Field(None, description="GS1 Global Location Number (13 digits)")
    location_name: Optional[str] = Field(None, description="Human-readable location name")
    location_phone: Optional[str] = Field(None, description="Business phone number")
    location_address: Optional[str] = Field(None, description="Physical location address")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the event")
    kdes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional Key Data Elements (temperature, carrier, PO, field ID, etc.)"
    )
    input_traceability_lot_codes: Optional[list[str]] = Field(
        None,
        description=(
            "For transformation CTEs (21 CFR §1.1350): list of input TLCs that were "
            "combined/transformed into the new traceability_lot_code. Required per "
            "§1.1350(a)(1) to link each new TLC to all input TLCs."
        ),
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Ensure timestamp is parseable and within reasonable bounds."""
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")

        if dt.tzinfo is None:
            # Naive timestamps are assumed UTC, mirroring the ingest
            # replay-window check (webhook_router_v2/security.py). Without
            # this the aware/naive comparison below raises a bare TypeError
            # (HTTP 500) instead of a 422 validation error.
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        # Allow historical events for FSMA 204 §1.1455(d) 2-year retention backfill.
        # Events older than 90 days are accepted but flagged via _historical_warning.
        # Reject events more than 24 hours in the future (clock skew)
        if dt > now + timedelta(hours=24):
            raise ValueError(f"Event timestamp {v} is more than 24 hours in the future.")
        return v

    @field_validator("location_gln")
    @classmethod
    def validate_gln_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate GLN is 13 digits with valid GS1 check digit.

        Warning-only: logs invalid GLNs but accepts them to avoid
        breaking existing imports. Use validate_gln() for strict checks.
        """
        if v is None or v.strip() == "":
            return v
        clean = re.sub(r"\D", "", v)
        is_valid, error_msg = (
            validate_gln(clean) if len(clean) == 13 else (False, f"GLN must be exactly 13 digits, got {len(clean)}")
        )
        if not is_valid:
            strict = os.getenv("STRICT_GLN_VALIDATION", "true").lower() == "true"
            if strict:
                raise ValueError(f"Invalid GLN: {error_msg}")
            _gln_logger.warning("invalid_gln value=%s error=%s (strict mode disabled)", v, error_msg)
            return clean if len(clean) == 13 else v
        return clean

    @field_validator("unit_of_measure")
    @classmethod
    def validate_unit_of_measure(cls, v: str) -> str:
        """Validate unit of measure against known FSMA 204 units.

        Warning-only: unknown units are logged but accepted so that
        abbreviated or misspelled values (e.g. "bx", "ea", "lbs.")
        don't crash the entire row. The CSV ingest layer normalises
        common aliases before reaching this validator; this guard exists
        for direct API callers.
        """
        normalized = v.strip().lower()
        if normalized not in VALID_UNITS_OF_MEASURE:
            import logging as _logging

            _logging.getLogger("uom-validation").warning(
                "unknown_unit value=%s accepted_as_is=true valid=%s",
                v,
                ",".join(sorted(VALID_UNITS_OF_MEASURE)),
            )
            # Accept it — KDE completeness checks will flag it to the user
            return normalized
        return normalized

    @model_validator(mode="after")
    def require_location(self) -> "IngestEvent":
        """Require one complete location description or GLN per 21 CFR 1.1310."""

        # A-2170: only internally constructed EDI events may accept incomplete locations.
        if self._edi_allow_incomplete_location and self.kdes.get("location_incomplete") is True:
            _gln_logger.warning("location_incomplete accepted=true")
            return self

        def first_nonblank(*values: Any) -> Optional[str]:
            return next((value for value in values if isinstance(value, str) and value.strip()), None)

        for prefix in ("location", "ship_from", "ship_to", "receiving"):

            def description_field(field: str) -> Optional[str]:
                top_level = getattr(self, f"location_{field}") if prefix == "location" else None
                legacy_name = self.kdes.get(f"{prefix}_location") if field == "name" else None
                return first_nonblank(top_level, self.kdes.get(f"{prefix}_{field}"), legacy_name)

            if is_location_description_complete(
                gln=first_nonblank(self.location_gln, self.kdes.get(f"{prefix}_gln")),
                name=description_field("name"),
                phone=description_field("phone"),
                address=description_field("address"),
            ):
                return self
        raise ValueError(
            "FSMA 204 requires (name AND phone AND address) OR GLN for at least one location per CTE (21 CFR 1.1310)."
        )


class WebhookPayload(BaseModel):
    """Webhook ingestion payload — the top-level request body."""

    source: str = Field(
        ...,
        description="Source system identifier (sensitech, tive, erp, manual, custom)",
        min_length=1,
    )
    events: List[IngestEvent] = Field(
        ...,
        description="List of CTE events to ingest (max 500 per batch)",
        min_length=1,
        max_length=500,
    )
    tenant_id: Optional[str] = Field(None, description="Tenant identifier (auto-detected from API key if not provided)")


class EventResult(BaseModel):
    """Result for a single ingested event."""

    traceability_lot_code: str
    cte_type: str
    status: str  # "accepted" or "rejected"
    event_id: Optional[str] = None
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Response from the webhook ingestion endpoint."""

    accepted: int = 0
    rejected: int = 0
    total: int = 0
    events: List[EventResult] = Field(default_factory=list)
    ingestion_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ingestion_run_id: Optional[str] = Field(
        None,
        description=(
            "fsma.ingestion_runs id when the upload was retained as an ingestion run (file uploads): "
            "the receipt that ties every accepted event back to the verbatim source file and its SHA-256."
        ),
    )


class CsvRowDispositionEntry(BaseModel):
    """One accounted-for CSV input row or header/field decision (SEL-549).

    Every physical data row the partner file presented must appear here as
    accepted, rejected, flagged, or skipped — never silently dropped.
    ``guessed_value`` is omitted on purpose: partner cell values must not
    leave the ingest path via logs or API responses.
    """

    row_number: int = Field(
        ...,
        description="CSV line number (header is 1; data starts at 2). 0 means a file-level header decision.",
    )
    disposition: str = Field(
        ...,
        description="accepted | rejected | flagged | skipped",
    )
    reason: str = Field(..., description="Machine-readable reason code for this decision.")
    field: Optional[str] = Field(
        default=None,
        description="Column or field name involved, when the decision is field-scoped.",
    )
    detail: Optional[str] = Field(
        default=None,
        description="Human-readable detail. Never includes cell values or secrets.",
    )
    guessed_as: Optional[str] = Field(
        default=None,
        description="Canonical field a partner column was mapped/guessed into, when applicable.",
    )


class HeaderMappingSuggestionResult(BaseModel):
    """One Jev suggestion for a CSV column the parser did not recognise.

    ``applied`` is true only when deterministic code copied the column under
    ``canonical_field`` for this upload (see ``shared.jev.header_mapping``);
    otherwise ``blocked_reason`` says why the suggestion stayed advisory.
    """

    source_header: str = Field(..., description="Column header as it appeared in the file.")
    source_key: str = Field(..., description="Normalised column key the parser sees.")
    canonical_field: Optional[str] = Field(None, description="Suggested canonical FSMA 204 field; null for no match.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Jev confidence in the selected field.")
    band: str = Field(..., description="Confidence band: auto_apply, review, or reject.")
    applied: bool = Field(False, description="Whether the mapping was applied to this upload's rows.")
    blocked_reason: Optional[str] = Field(None, description="Why the mapping was not applied, when it was not.")


class HeaderMappingEngineResult(BaseModel):
    """Provenance for the header-mapping suggestions on a CSV upload."""

    provider: str = Field("typesafe", description="Suggestion provider.")
    status: str = Field(..., description="ok, no_unrecognized_headers, unavailable:<reason>, or error.")
    model: Optional[str] = Field(None, description="Model that answered, as reported by the provider.")
    request_id: Optional[str] = Field(None, description="Provider request id for the call.")
    questions_version: Optional[str] = Field(None, description="Version of the question set that was asked.")
    apply_enabled: bool = Field(False, description="Whether auto-apply of AUTO_APPLY-band mappings is switched on.")
    auto_apply_confidence: Optional[float] = Field(None, description="Lower bound of the auto_apply band.")
    review_confidence: Optional[float] = Field(None, description="Lower bound of the review band.")
    artifacts_recorded: int = Field(0, description="Advisory field_mapping_suggestion artifacts queued for review.")


class CteTypeSuggestionResult(BaseModel):
    """Jev's answer to "which CTE does every row of this CSV file record?".

    Asked only when the upload declared no ``cte_type`` and no column gives
    rows their own CTE (``shared.jev.cte_classification``). ``applied`` is
    true only when deterministic code used ``cte_type`` as the file's
    fallback CTE; otherwise ``blocked_reason`` says why the answer stayed
    advisory, and re-uploading with ``cte_type`` set to it accepts it.
    """

    provider: str = Field("typesafe", description="Suggestion provider.")
    status: str = Field(
        ...,
        description=(
            "ok, per_row_cte_column (not asked: rows name their own CTE), no_headers, malformed_header, "
            "unavailable:<reason>, no_answer, or error."
        ),
    )
    cte_type: Optional[str] = Field(
        None, description="Suggested CTE for every row; null when the rows look mixed or unclear, or on no answer."
    )
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Jev confidence in the answer.")
    band: Optional[str] = Field(None, description="Confidence band: auto_apply, review, or reject.")
    applied: bool = Field(False, description="Whether the CTE was used for this upload's rows without one.")
    blocked_reason: Optional[str] = Field(None, description="Why the CTE was not applied, when it was not.")
    model: Optional[str] = Field(None, description="Model that answered, as reported by the provider.")
    request_id: Optional[str] = Field(None, description="Provider request id for the call.")
    questions_version: Optional[str] = Field(None, description="Version of the question that was asked.")
    apply_enabled: bool = Field(False, description="Whether applying AUTO_APPLY-band answers is switched on.")
    artifacts_recorded: int = Field(0, description="Advisory field_mapping_suggestion artifacts queued for review.")


class CsvIngestResponse(IngestResponse):
    """Response from POST /api/v1/ingest/csv (#2892).

    The CSV path is the only ingest surface that computes per-row KDE
    warnings, so the two extra fields live here rather than on the shared
    ``IngestResponse`` — the webhook endpoint would otherwise advertise a
    signal it never produces.

    Both fields carry defaults, so they stay out of the schema's
    ``required`` set: a body cached by the idempotency middleware before
    this shipped (24h TTL) still validates against the new schema when it
    is replayed.
    """

    kde_warnings: List[str] = Field(
        default_factory=list,
        description="Per-row warnings for rows missing required FSMA key data elements.",
    )
    kde_warning_count: int = Field(
        default=0,
        description="Number of entries in kde_warnings.",
    )
    # Both default so they stay out of ``required`` for the same replay
    # reason as the KDE fields above. ``header_mapping_engine`` is null when
    # the Jev integration is not configured, so the wire shape for tenants
    # without it is unchanged apart from an empty list.
    header_mapping_suggestions: List[HeaderMappingSuggestionResult] = Field(
        default_factory=list,
        description="Jev suggestions for columns the parser did not recognise (empty when not configured).",
    )
    header_mapping_engine: Optional[HeaderMappingEngineResult] = Field(
        default=None,
        description="Provenance for header_mapping_suggestions; null when the integration is not configured.",
    )
    # Null unless Jev is configured and the upload declared no cte_type, so
    # the wire shape for every other upload is unchanged.
    cte_type_suggestion: Optional[CteTypeSuggestionResult] = Field(
        default=None,
        description="Jev's suggested CTE for a file that declares none; null when not asked.",
    )

    # SEL-549: every input row accounted for. Defaults keep cached idempotent
    # bodies valid against the schema after this ships.
    row_disposition_log: List[CsvRowDispositionEntry] = Field(
        default_factory=list,
        description="Per-row (and file-level) accept/reject/flag/skip decisions; never silent drops.",
    )
    missing_columns: List[str] = Field(
        default_factory=list,
        description="Required partner columns that were absent (canonical names); empty when the header was usable.",
    )
    unrecognized_columns: List[str] = Field(
        default_factory=list,
        description="Partner columns the parser does not recognise (may still pass through into KDEs).",
    )


class RecentEventsResponse(BaseModel):
    """Response from the /recent events endpoint."""

    tenant_id: str
    events: List[dict] = Field(default_factory=list)
    total: int = 0


class ChainVerifyResponse(BaseModel):
    """Response from the /chain/verify endpoint."""

    tenant_id: str
    chain_valid: bool = False
    chain_length: int = 0
    errors: List[str] = Field(default_factory=list)
    checked_at: Optional[str] = None
